"""Layout checks: what a reader would notice that the code doesn't say.

`Diagram.check()` lays the diagram out and returns a list of Issues. Each one
names the parts involved and suggests a fix, so a person or an agent can
correct the code without looking at the picture. An empty list means none of
these problems were found; it does not mean the drawing explains its idea well.

Codes:
  overlap         two shapes cover each other
  edge-crosses    an arrow or line passes through a shape it doesn't connect
  edge-overlap    two edges run along the same line (e.g. a request and its reply)
  label-overlap   an edge label sits on a shape or on another label
  text-overflow   text is wider than the box or slot it was given
  too-wide        content is wider than the diagram's width (it will be scaled down)
  too-many-tones  more than four meanings in one drawing
  crowded         more than 15 shapes: probably two ideas
  no-title        no alt text
  no-headline     no one-line takeaway
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from .nodes import Box, Cell, Circle, Edge, Free, Label, Node, Overlay, Spacer

if TYPE_CHECKING:
    from .nodes import BBox, Diagram, Placed, Rect

Level: TypeAlias = Literal["error", "warn", "info"]
Code: TypeAlias = Literal["overlap", "edge-crosses", "edge-overlap", "label-overlap", "text-overflow", "too-wide",
                          "too-many-tones", "crowded", "no-title", "no-headline"]

_ORDER: Final[dict[Level, int]] = {"error": 0, "warn": 1, "info": 2}
MAX_MEANINGS: Final = 4
MAX_SHAPES: Final = 15


@dataclass(frozen=True)
class Issue:
    level: Level
    code: Code
    message: str
    fix: str

    def __str__(self) -> str:
        return f"{self.level:5} {self.code}: {self.message}\n      fix: {self.fix}"


def _box(r: Rect, shrink: float = 0) -> BBox:
    x, y, w, h = r
    return (x + shrink, y + shrink, x + w - shrink, y + h - shrink)


def _hit(a: BBox, b: BBox) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _segment_hits(p: tuple[float, float], q: tuple[float, float], r: BBox) -> bool:
    """Liang-Barsky: does segment p-q pass through the open box r?"""
    t0, t1 = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for pk, qk in ((-dx, p[0] - r[0]), (dx, r[2] - p[0]), (-dy, p[1] - r[1]), (dy, r[3] - p[1])):
        if pk == 0:
            if qk <= 0:
                return False
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1:
            return False
    return True


Seg: TypeAlias = tuple[tuple[float, float], tuple[float, float]]


def _collinear(s1: Seg, s2: Seg, tol: float = 5, min_shared: float = 12) -> bool:
    """Do two segments lie on (nearly) the same line and share some length?"""
    (ax, ay), (bx, by) = s1
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L == 0:
        return False
    ux, uy = dx / L, dy / L
    ts: list[float] = []
    for px, py in s2:
        if abs((px - ax) * uy - (py - ay) * ux) > tol:  # distance from s1's line
            return False
        ts.append((px - ax) * ux + (py - ay) * uy)  # position along s1
    return min(max(ts), L) - max(min(ts), 0) >= min_shared


def _name(n: Node) -> str:
    return repr(n)


def _edge_name(e: Edge) -> str:
    label = getattr(e, "label", None)
    return f"{type(e).__name__}({label!r})" if label else type(e).__name__


def lint(d: Diagram, placed: Placed) -> list[Issue]:
    ctx = placed.ctx
    path_of = {id(n): p for p, n in placed.nodes}
    overlays = [p for p, n in placed.nodes if isinstance(n, Overlay)]
    leaves = [(p, n) for p, n in placed.nodes
              if not n.children() and not isinstance(n, (Spacer, Free)) and n.rect[2] > 0 and n.rect[3] > 0]
    issues: list[Issue] = []

    def under(path: str, ancestor: str) -> bool:
        return path == ancestor or path.startswith(ancestor + ".")

    # -- shapes on shapes
    for (pa, a), (pb, b) in itertools.combinations(leaves, 2):
        if any(under(pa, o) and under(pb, o) for o in overlays):
            continue
        if _hit(_box(a.rect, 3), _box(b.rect, 3)):
            issues.append(Issue("error", "overlap", f"{_name(a)} overlaps {_name(b)}",
                                "give their container more gap, or put them in different rows/columns"))

    # -- edges through shapes
    for e in placed.edges:
        pts = getattr(e, "points", None)
        if pts is None:
            continue
        ends = [n for n in getattr(e, "ends", lambda: (None, None))() if n is not None]
        end_paths = [path_of[id(n)] for n in ends if id(n) in path_of]
        segs = list(itertools.pairwise(pts()))
        for p, n in leaves:
            if any(under(p, ep) for ep in end_paths):
                continue
            r = _box(n.rect, 4)
            if any(_segment_hits(a, b, r) for a, b in segs):
                issues.append(Issue("error", "edge-crosses", f"{_edge_name(e)} passes through {_name(n)}",
                                    "reorder the row so connected things sit next to each other, route around "
                                    "with route='hv'/'vh' or via=[...], or start/end at a port like node.bottom"))

    # -- edges on top of each other
    paths = [(e, list(itertools.pairwise(pts()))) for e in placed.edges if (pts := getattr(e, "points", None))]
    for (e1, s1), (e2, s2) in itertools.combinations(paths, 2):
        if any(_collinear(a, b) for a in s1 for b in s2):
            issues.append(Issue("error", "edge-overlap", f"{_edge_name(e1)} and {_edge_name(e2)} are drawn on the "
                                "same line", "start and end them at different ports, e.g. a.at(1, 0.3) → b.at(0, 0.3) "
                                "and b.at(0, 0.7) → a.at(1, 0.7)"))

    # -- edge labels on shapes and on each other
    labels = [(e, lb) for e in placed.edges if (lb := e.label_box(ctx)) is not None]
    for e, lb in labels:
        for _, n in leaves:
            if _hit(lb, _box(n.rect, 1)):
                issues.append(Issue("error", "label-overlap", f"label of {_edge_name(e)} sits on {_name(n)}",
                                    "widen the gap between the two shapes (flow() sizes it for you), shorten the "
                                    "label, or move it with label_side= / label_at="))
    for (e1, l1), (e2, l2) in itertools.combinations(labels, 2):
        if _hit(l1, l2):
            issues.append(Issue("error", "label-overlap",
                                f"labels of {_edge_name(e1)} and {_edge_name(e2)} overlap",
                                "move one with label_at= (0..1 along the edge) or label_side="))

    # -- text wider than its slot
    for _, n in leaves:
        w = n.rect[2]
        if isinstance(n, Box):
            need = max(ctx.width(n.title, n.size, True, ctx.box_font),
                       ctx.width(n.sub, n.sub_size, False, ctx.box_font) if n.sub else 0) + 8
        elif isinstance(n, Cell):
            need = ctx.width(n.text, n.size, n.bold) + 6
        elif isinstance(n, Label):
            need = ctx.width(n.text, n.size, n.bold, n.font) - 1
        else:
            continue
        if need > w:
            issues.append(Issue("warn", "text-overflow", f"text of {_name(n)} needs {need:.0f}px, has {w:.0f}px",
                                "remove the .fixed() width, shorten the text, or split it over two lines"))

    # -- whole-diagram checks
    if d.width and placed.width > d.width + 1:
        issues.append(Issue("warn", "too-wide", f"content is {placed.width:.0f}px wide, more than width={d.width:.0f}; "
                            "it will be scaled down and the text will shrink",
                            "stack vertically (Col, flow(..., vertical=True)), use fewer items per Row, "
                            "or shorten labels"))
    if len(ctx.used) > MAX_MEANINGS:
        issues.append(Issue("warn", "too-many-tones", f"{len(ctx.used)} meanings used: {', '.join(ctx.used)}",
                            f"keep to {MAX_MEANINGS} or fewer; color only what the idea is about"))
    shapes = sum(isinstance(n, (Box, Cell, Circle)) for _, n in leaves)
    if shapes > MAX_SHAPES:
        issues.append(Issue("info", "crowded", f"{shapes} shapes in one drawing",
                            "one drawing, one idea: split it, or group details into a Region"))
    if not d.title:
        issues.append(Issue("info", "no-title", "no alt text",
                            "pass title=: one or two sentences saying what the drawing shows"))
    if not d.headline:
        issues.append(Issue("info", "no-headline", "no takeaway line",
                            "pass headline=: the one sentence the reader should remember"))

    return sorted(issues, key=lambda i: _ORDER[i.level])
