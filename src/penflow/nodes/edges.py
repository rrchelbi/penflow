"""Edges: drawn between or around nodes after layout, so they never need coordinates."""

from __future__ import annotations

import itertools
import math
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence

from ..core import Anchor, Canvas, Point
from .base import BBox, BracketSide, Ctx, LabelSide, Node, Port, Rect, Ref, Route, ToneRef, classes


def _clip(rect: Rect, toward: Point) -> Point:
    """Where the segment from rect's center toward `toward` leaves the rect."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    t = min(w / 2 / abs(dx) if dx else math.inf, h / 2 / abs(dy) if dy else math.inf)
    return (cx + dx * t, cy + dy * t)


def _center(ref: Ref) -> Point:
    if isinstance(ref, Node):
        x, y, w, h = ref.rect
        return (x + w / 2, y + h / 2)
    if isinstance(ref, Port):
        return ref.point()
    return (ref[0], ref[1])


def _end(ref: Ref, toward: Point) -> Point:
    return _clip(ref.rect, toward) if isinstance(ref, Node) else _center(ref)


def _shorten(p: Point, q: Point, d: float) -> Point:
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    if 2 * d >= L:
        return p
    return (p[0] + (q[0] - p[0]) * d / L, p[1] + (q[1] - p[1]) * d / L)


class Edge(ABC):
    """Something drawn between or around nodes after layout."""

    tone: ToneRef | None = None
    origin: str | None = None
    """Where the edge was written, for check messages. Set by the DSL."""

    @abstractmethod
    def bbox(self, ctx: Ctx) -> BBox: ...

    def label_box(self, ctx: Ctx) -> BBox | None:
        """Where the edge's label text sits, if it has one (used by Diagram.check)."""
        return None

    @abstractmethod
    def draw(self, cv: Canvas, ctx: Ctx) -> None: ...


class Arrow(Edge):
    """An arrow between two nodes (or ports, or points). The ends sit on the node
    outlines. `route="hv"` goes horizontal then vertical, "vh" the other way; `via`
    adds bend points. Labels sit above a flat segment or right of a steep one."""

    head: float = 10

    def __init__(self, a: Ref, b: Ref, label: str | None = None, tone: ToneRef | None = None,
                 dashed: bool = False, route: Route | None = None, via: Iterable[Point] = (),
                 gap: float = 6, label_at: float = 0.5, label_side: LabelSide = "auto", size: float = 13,
                 head: float | None = None) -> None:
        if route not in (None, "hv", "vh"):
            raise ValueError("route is 'hv', 'vh' or None")
        self.a, self.b, self.label, self.tone, self.dashed = a, b, label, tone, dashed
        self.route: Route | None = route
        self.label_side: LabelSide = label_side
        self.via, self.gap, self.label_at, self.size = list(via), gap, label_at, size
        if head is not None:
            self.head = head

    def points(self) -> list[Point]:
        ca, cb = _center(self.a), _center(self.b)
        mids = list(self.via)
        if self.route == "hv":
            mids = [(cb[0], ca[1])]
        elif self.route == "vh":
            mids = [(ca[0], cb[1])]
        p0 = _end(self.a, mids[0] if mids else cb)
        p1 = _end(self.b, mids[-1] if mids else ca)
        pts = [p0, *mids, p1]
        pts[0] = _shorten(pts[0], pts[1], self.gap)
        pts[-1] = _shorten(pts[-1], pts[-2], self.gap)
        return pts

    def _label_pos(self, pts: Sequence[Point]) -> tuple[float, float, Anchor]:
        segs = list(itertools.pairwise(pts))
        p, q = max(segs, key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
        mx, my = p[0] + (q[0] - p[0]) * self.label_at, p[1] + (q[1] - p[1]) * self.label_at
        side = self.label_side
        if side == "auto":
            side = "above" if abs(q[0] - p[0]) >= abs(q[1] - p[1]) else "right"
        if side == "above":
            return (mx, my - 8, "middle")
        if side == "below":
            return (mx, my + self.size + 6, "middle")
        if side == "right":
            return (mx + 8, my + 4, "start")
        return (mx - 8, my + 4, "end")

    def label_box(self, ctx: Ctx) -> BBox | None:
        """Where the label's text sits (after layout), or None without a label."""
        if not self.label:
            return None
        lx, ly, anchor = self._label_pos(self.points())
        w = ctx.width(self.label, self.size)
        x0 = {"middle": lx - w / 2, "start": lx, "end": lx - w}[anchor]
        return (x0, ly - self.size * 0.8, x0 + w, ly + self.size * 0.2)

    def ends(self) -> tuple[Node | None, Node | None]:
        """The nodes this edge connects (None for a plain point)."""
        def owner(r: Ref) -> Node | None:
            return r if isinstance(r, Node) else r.node if isinstance(r, Port) else None
        return owner(self.a), owner(self.b)

    def bbox(self, ctx: Ctx) -> BBox:
        pts = self.points()
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        lb = self.label_box(ctx)
        if lb:
            xs += [lb[0], lb[2]]
            ys += [lb[1] - self.size * 0.2, lb[3] + 4 - self.size * 0.2]
        return (min(xs), min(ys), max(xs), max(ys))

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        cls = classes(ctx.tone(self.tone))
        pts = self.points()
        for i, (p, q) in enumerate(itertools.pairwise(pts)):
            last = i == len(pts) - 2
            if self.dashed:
                _dash(cv, p, q, cls["stroke"])
                if last and self.head:
                    _head(cv, p, q, cls["stroke"], self.head)
            elif last and self.head:
                cv.arrow(p[0], p[1], q[0], q[1], cls["stroke"], head=self.head)
            else:
                cv.line(p[0], p[1], q[0], q[1], cls["stroke"], rough=1.8)
        if self.label:
            lx, ly, anchor = self._label_pos(pts)
            cv.text(lx, ly, self.label, self.size, cls["text"], anchor, halo=True)


class Line(Arrow):
    """An Arrow without a head."""

    head = 0


def _dash(cv: Canvas, p: Point, q: Point, cls: str) -> None:
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    n = max(1, int(L // 14))
    for i in range(n):
        t0, t1 = i / n, (i + 0.55) / n
        cv.line(p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0,
                p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1, cls, rough=0.6, passes=1)


def _head(cv: Canvas, p: Point, q: Point, cls: str, size: float) -> None:
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    for s in (-1, 1):
        a = ang + math.pi - s * math.radians(26 + cv.j(4))
        L = size + cv.j(2)
        cv.line(q[0], q[1], q[0] + math.cos(a) * L, q[1] + math.sin(a) * L, cls, rough=0.8, passes=1)


class Bracket(Edge):
    """A span line over (or under) a set of nodes, with a label: "quorum A"."""

    def __init__(self, nodes: Iterable[Node], label: str | None = None, side: BracketSide = "top",
                 tone: ToneRef | None = None, offset: float = 12, size: float = 14) -> None:
        if side not in ("top", "bottom"):
            raise ValueError("Bracket side is 'top' or 'bottom'")
        self.nodes, self.label, self.tone = list(nodes), label, tone
        self.side: BracketSide = side
        if not self.nodes:
            raise ValueError("Bracket needs at least one node")
        self.offset, self.size = offset, size

    def _geom(self) -> tuple[float, float, float, float, float]:
        """x0, x1, the span line's y, where the end ticks stop, the label baseline."""
        frames = [n.rect for n in self.nodes]
        x0 = min(f[0] for f in frames) - 4
        x1 = max(f[0] + f[2] for f in frames) + 4
        if self.side == "top":
            yb = min(f[1] for f in frames) - self.offset
            return x0, x1, yb, yb + 12, yb - 10
        yb = max(f[1] + f[3] for f in frames) + self.offset
        return x0, x1, yb, yb - 12, yb + self.size + 8

    def label_box(self, ctx: Ctx) -> BBox | None:
        if not self.label:
            return None
        x0, x1, _, _, ly = self._geom()
        w, cx = ctx.width(self.label, self.size, True), (x0 + x1) / 2
        return (cx - w / 2, ly - self.size * 0.8, cx + w / 2, ly + self.size * 0.2)

    def bbox(self, ctx: Ctx) -> BBox:
        x0, x1, yb, _, ly = self._geom()
        w = ctx.width(self.label or "", self.size, True)
        cx = (x0 + x1) / 2
        return (min(x0, cx - w / 2), min(yb, ly - self.size), max(x1, cx + w / 2), max(yb, ly + 4))

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        c = classes(ctx.tone(self.tone))
        x0, x1, yb, ytick, ly = self._geom()
        cv.line(x0, yb, x1, yb, c["stroke"])
        cv.line(x0, yb, x0, ytick, c["stroke"], passes=1)
        cv.line(x1, yb, x1, ytick, c["stroke"], passes=1)
        if self.label:
            cv.text((x0 + x1) / 2, ly, self.label, self.size, c["text"], weight=700, halo=True)
