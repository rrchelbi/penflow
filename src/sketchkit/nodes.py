"""Composable diagram nodes.

A diagram is a tree of nodes. Each node knows its natural size (`measure`) and
draws itself inside the frame its parent gives it (`layout`, then `draw`).
Containers (Row, Col, Grid, Region, ...) arrange children; edges (Arrow, Line,
Bracket) point at nodes and are resolved after layout, so nothing needs
coordinates:

    a, b = Box("client"), Box("server")
    Diagram(Row(a, b, gap=80), edges=[Arrow(a, b, "request")]).svg()

Modifiers (`.tone()`, `.dashed()`, `.fixed()`, `.align()`, `.link()`) change
the node in place and return it, so a node kept in a variable is the one in the
tree and edges can point at it. A node instance can appear only once in a tree;
build repeated parts with a function.
"""

from __future__ import annotations

import itertools
import math
import random
import zlib
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Final,
    Literal,
    NamedTuple,
    Self,
    TypeAlias,
    TypedDict,
    TypeGuard,
)

from .core import TONES, Anchor, Canvas, FontName, Point, ToneName, is_tone

if TYPE_CHECKING:
    from .lint import Issue

Style: TypeAlias = Literal["hand", "clean"]
Theme: TypeAlias = Literal["blog", "auto", "paper"]
ResolvedTone: TypeAlias = ToneName | Literal["accent", "soft"]
"""What a tone reference resolves to: one of the four tones, accent or soft."""
ToneRef: TypeAlias = str
"""A meaning name ("bad", or one you define) or a ResolvedTone; checked at render time."""
Align: TypeAlias = Literal["start", "center", "end", "stretch"]
Justify: TypeAlias = Literal["start", "center", "end", "between"]
TextAlign: TypeAlias = Literal["start", "center", "end"]
TrackSide: TypeAlias = Literal["above", "below"]
TickMark: TypeAlias = Literal["dot", "circle", "none"]
LabelSide: TypeAlias = Literal["auto", "above", "below", "left", "right"]
BracketSide: TypeAlias = Literal["top", "bottom"]
Route: TypeAlias = Literal["hv", "vh"]
MarkKind: TypeAlias = Literal["check", "cross"]
Rect: TypeAlias = tuple[float, float, float, float]
"""x, y, width, height."""
Size: TypeAlias = tuple[float, float]
BBox: TypeAlias = tuple[float, float, float, float]
"""x0, y0, x1, y1."""
Child: TypeAlias = "Node | str"
"""Anything a container accepts: a node, or a string that becomes a Label."""
Ref: TypeAlias = "Node | Port | Point"
"""An edge end: a node (the edge stops at its outline), a port on a node, or a point."""
MeaningSpec: TypeAlias = ResolvedTone | tuple[ResolvedTone, str]
"""A tone, or (tone, legend label)."""

DEFAULT_MEANINGS: Final[Mapping[str, MeaningSpec]] = {
    "good": "cyan", "bad": "orange", "wait": "rust", "normal": "slate"}
CIRCLED: Final = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def is_resolved_tone(name: object) -> TypeGuard[ResolvedTone]:
    return is_tone(name) or name in ("accent", "soft")


def text_width(s: str, size: float, bold: bool = False, mono: bool = False, scale: float = 1.0) -> float:
    """Approximate rendered width. No font files are read: a per-character table
    is close enough for layout, and every container leaves some slack."""
    if mono:
        return len(s) * size * 0.6
    w = 0.0
    for ch in s:
        if ch in "il.,:;'|!`·":
            f = 0.28
        elif ch in "fjrtI()[]{}-\"/ ":
            f = 0.36
        elif ch in "mwMW@%":
            f = 0.86
        elif ch in CIRCLED:
            f = 1.0
        elif ch.isupper() or ord(ch) > 0x2000:
            f = 0.66
        elif ch.isdigit():
            f = 0.56
        else:
            f = 0.53
        w += f
    return w * size * (1.06 if bold else 1.0) * scale


class Ctx:
    """Everything a render needs besides the tree: style, theme and meanings."""

    def __init__(self, style: Style = "hand", theme: Theme = "paper",
                 meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> None:
        if style not in ("hand", "clean"):
            raise ValueError(f"style must be 'hand' or 'clean', not {style!r}")
        if theme not in ("blog", "auto", "paper"):
            raise ValueError(f"theme must be 'blog', 'auto' or 'paper', not {theme!r}")
        self.style: Style = style
        self.theme: Theme = theme
        self.clean = style == "clean"
        self.meanings: dict[str, tuple[ResolvedTone, str]] = {}
        for name, v in {**DEFAULT_MEANINGS, **(meanings or {})}.items():
            tone, label = v if isinstance(v, tuple) else (v, name)
            if not is_resolved_tone(tone):
                raise ValueError(f"meaning {name!r}: unknown tone {tone!r} (use one of {', '.join(TONES)})")
            self.meanings[name] = (tone, label)
        self.box_font: FontName | None = box_font if box_font is not None else ("mono" if theme == "paper" else None)
        # The handwriting font of the paper theme runs wider than a sans font.
        self.scale = 1.12 if (theme == "paper" and not self.clean) else 1.0
        self.used: list[str] = []  # meaning names in order of first use, for Legend()
        self._sizes: dict[int, Size] = {}

    def tone(self, name: ToneRef | None) -> ResolvedTone | None:
        """A meaning ("bad"), a tone ("orange"), "accent", "soft" or None -> tone or None."""
        if name is None or is_resolved_tone(name):
            return name
        if name in self.meanings:
            return self.meanings[name][0]
        known = sorted({*self.meanings, *TONES, "accent", "soft"})
        raise ValueError(f"unknown tone or meaning {name!r}; known: {', '.join(known)}")

    def width(self, s: str, size: float, bold: bool = False, font: FontName | None = None) -> float:
        mono = font == "mono"
        return max(text_width(line, size, bold, mono, 1.0 if mono else self.scale) for line in s.split("\n"))

    def size(self, node: Node) -> Size:
        k = id(node)
        if k not in self._sizes:
            self._sizes[k] = node.measure(self)
        return self._sizes[k]


class ToneClasses(TypedDict):
    stroke: str
    text: str
    fill: str
    solid: str


def classes(t: ResolvedTone | None) -> ToneClasses:
    """CSS classes for a resolved tone: stroke, text, fill and solid fill."""
    if t is None:
        return {"stroke": "stroke", "text": "", "fill": "fill-surface", "solid": "fill-accent"}
    if t in ("accent", "soft"):
        return {"stroke": f"stroke-{t}", "text": f"t-{t}", "fill": "fill-surface", "solid": "fill-accent"}
    return {"stroke": f"stroke-{t}", "text": f"t-{t}", "fill": f"fill-{t}", "solid": f"solid-{t}"}


class Port:
    """A point on a node, as fractions of its frame: (0, 0) top-left, (1, 1) bottom-right."""

    def __init__(self, node: Node, fx: float, fy: float) -> None:
        self.node, self.fx, self.fy = node, fx, fy

    def point(self) -> Point:
        x, y, w, h = self.node.rect
        return (x + self.fx * w, y + self.fy * h)


class Node:
    frame: Rect | None = None
    _tone: ToneRef | None = None
    _dashed: bool = False
    _fixed: tuple[float | None, float | None] = (None, None)
    _self_align: Align | None = None
    _edges: tuple[Edge, ...] = ()

    def tone(self, t: ToneRef | None) -> Self:
        """A meaning ("bad") or tone ("orange", "accent", "soft")."""
        self._tone = t
        return self

    def dashed(self, on: bool = True) -> Self:
        self._dashed = on
        return self

    def fixed(self, w: float | None = None, h: float | None = None) -> Self:
        """Use this width and/or height instead of the measured one."""
        self._fixed = (w, h)
        return self

    def align(self, a: Align) -> Self:
        """Alignment inside the parent's cross axis: "start", "center", "end" or "stretch"."""
        self._self_align = a
        return self

    def link(self, *edges: Edge) -> Self:
        """Attach edges to this node, so a reusable part carries its own arrows."""
        self._edges = (*self._edges, *edges)
        return self

    @property
    def linked(self) -> tuple[Edge, ...]:
        """Edges attached with .link()."""
        return self._edges

    def pad(self, *sides: float, top: float | None = None, right: float | None = None,
            bottom: float | None = None, left: float | None = None) -> Pad:
        return Pad(self, *sides, top=top, right=right, bottom=bottom, left=left)

    # -- geometry
    @property
    def rect(self) -> Rect:
        """The frame after layout; raises if the node was never placed."""
        if self.frame is None:
            raise ValueError(f"{self!r} is not part of the diagram (was it added to the tree?)")
        return self.frame

    @property
    def top(self) -> Port:
        return Port(self, 0.5, 0)

    @property
    def bottom(self) -> Port:
        return Port(self, 0.5, 1)

    @property
    def left(self) -> Port:
        return Port(self, 0, 0.5)

    @property
    def right(self) -> Port:
        return Port(self, 1, 0.5)

    @property
    def center(self) -> Port:
        return Port(self, 0.5, 0.5)

    def at(self, fx: float, fy: float) -> Port:
        return Port(self, fx, fy)

    # -- protocol
    def children(self) -> Sequence[Node]:
        return ()

    def tones(self) -> Iterable[ToneRef]:
        """Tones this node uses itself (children report their own)."""
        return (self._tone,) if self._tone else ()

    def measure(self, ctx: Ctx) -> Size:
        w, h = self._measure(ctx)
        fw, fh = self._fixed
        return (w if fw is None else fw, h if fh is None else fh)

    def _measure(self, ctx: Ctx) -> Size:
        return (0, 0)

    def layout(self, x: float, y: float, w: float, h: float, ctx: Ctx) -> None:
        self.frame = (x, y, w, h)
        self._layout(ctx)

    def _layout(self, ctx: Ctx) -> None:
        pass

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        pass

    def __repr__(self) -> str:
        label = getattr(self, "title", None) or getattr(self, "text", None)
        return f"{type(self).__name__}({label!r})" if label else f"{type(self).__name__}()"


def node(x: Child) -> Node:
    """Strings become labels; nodes pass through."""
    if isinstance(x, Node):
        return x
    if isinstance(x, str):
        return Label(x)
    raise TypeError(f"expected a Node or str, got {type(x).__name__}")


class Label(Node):
    """Text. Multi-line with "\\n"."""

    def __init__(self, text: str, size: float = 14, tone: ToneRef | None = None, bold: bool = False,
                 align: TextAlign = "center", font: FontName | None = None, rot: float | None = None,
                 halo: bool | None = None) -> None:
        self.text, self.size, self.bold = text, size, bold
        self.text_align: TextAlign = align
        self.font: FontName | None = font
        self.rot, self.halo = rot, halo
        self._tone = tone

    def _lh(self) -> float:
        return self.size * 1.3

    def _measure(self, ctx: Ctx) -> Size:
        n = len(self.text.split("\n"))
        return (ctx.width(self.text, self.size, self.bold, self.font), n * self._lh())

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        lines = self.text.split("\n")
        top = y + (h - len(lines) * self._lh()) / 2
        ax = {"start": x, "center": x + w / 2, "end": x + w}[self.text_align]
        anchor: Anchor = "middle" if self.text_align == "center" else self.text_align
        cls = classes(ctx.tone(self._tone))["text"]
        for i, line in enumerate(lines):
            cv.text(ax, top + i * self._lh() + self.size * 0.98, line, self.size, cls, anchor,
                    weight=700 if self.bold else 400, rot=self.rot, font=self.font, halo=self.halo)


def Headline(text: str, size: float = 16, tone: ToneRef = "accent") -> Label:
    """The one-line takeaway under a drawing."""
    return Label(text, size=size, tone=tone, bold=True)


def Note(text: str, size: float = 13) -> Label:
    """A quieter line of explanation."""
    return Label(text, size=size, tone="soft")


def Step(n: int, text: str, size: float = 14, tone: ToneRef | None = None) -> Label:
    """A numbered step: ① text."""
    if not 1 <= n <= len(CIRCLED):
        raise ValueError(f"Step number must be 1..{len(CIRCLED)}")
    return Label(f"{CIRCLED[n - 1]} {text}", size=size, tone=tone, bold=True, align="start")


class Box(Node):
    """A labeled box with an optional second line."""

    def __init__(self, title: str, sub: str | None = None, size: float = 16, sub_size: float = 12,
                 min_w: float = 80) -> None:
        self.title, self.sub, self.size, self.sub_size, self.min_w = title, sub, size, sub_size, min_w

    def _measure(self, ctx: Ctx) -> Size:
        tw = ctx.width(self.title, self.size, True, ctx.box_font)
        sw = ctx.width(self.sub, self.sub_size, False, ctx.box_font) if self.sub else 0
        h = self.size + self.sub_size + 28 if self.sub else max(40, self.size * 2.5)
        return (max(self.min_w, max(tw, sw) + 28), h)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        t = ctx.tone(self._tone)
        cv.box(x, y, w, h, self.title, self.sub, accent=t == "accent", size=self.size, sub_size=self.sub_size,
               dashed=self._dashed, tone=t if is_tone(t) else None)


class Cell(Node):
    """A flat table cell: a rectangle with one centered line."""

    def __init__(self, text: str, size: float = 14, bold: bool = False, pad: float = 10) -> None:
        self.text, self.size, self.bold, self.p = text, size, bold, pad

    def _measure(self, ctx: Ctx) -> Size:
        return (ctx.width(self.text, self.size, self.bold) + 2 * self.p, self.size + 2 * self.p + 4)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        c = classes(ctx.tone(self._tone))
        if self._dashed:
            cv.fill_rect(x, y, w, h, c["fill"])
            cv.dashed_rect(x, y, w, h, c["stroke"])
        else:
            cv.rect(x, y, w, h, c["stroke"], fill_cls=c["fill"])
        cv.text(x + w / 2, y + h / 2 + self.size * 0.35, self.text, self.size, c["text"],
                weight=700 if self.bold else 400, halo=False)


class Circle(Node):
    def __init__(self, label: str | None = None, r: float | None = None, size: float = 16) -> None:
        self.text, self.r, self.size = label, r, size

    def _radius(self, ctx: Ctx) -> float:
        return self.r or max(22, ctx.width(self.text or "", self.size, True) / 2 + 12)

    def _measure(self, ctx: Ctx) -> Size:
        r = self._radius(ctx)
        return (2 * r, 2 * r)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        c = classes(ctx.tone(self._tone))
        cx, cy, r = x + w / 2, y + h / 2, min(w, h) / 2
        cv.circle(cx, cy, r, c["stroke"], c["fill"])
        if self.text:
            cv.text(cx, cy + self.size * 0.35, self.text, self.size, c["text"], weight=700, halo=False)


class Dot(Node):
    def __init__(self, r: float = 6) -> None:
        self.r = r

    def _measure(self, ctx: Ctx) -> Size:
        return (2 * self.r + 2, 2 * self.r + 2)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        cv.dot(x + w / 2, y + h / 2, self.r, classes(ctx.tone(self._tone))["solid"])


class Mark(Node):
    """A check or a cross."""

    def __init__(self, kind: MarkKind = "check", s: float = 8) -> None:
        if kind not in ("check", "cross"):
            raise ValueError("Mark kind is 'check' or 'cross'")
        self.kind: MarkKind = kind
        self.s = s

    def _measure(self, ctx: Ctx) -> Size:
        return (2 * self.s + 6, 2 * self.s + 6)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        cls = classes(ctx.tone(self._tone) or "accent")["stroke"]
        if self.kind == "check":
            cv.check(x + w / 2, y + h / 2, cls)
        else:
            cv.cross(x + w / 2, y + h / 2, self.s, cls)


class Spacer(Node):
    def __init__(self, w: float = 0, h: float = 0) -> None:
        self.w, self.h = w, h

    def _measure(self, ctx: Ctx) -> Size:
        return (self.w, self.h)


class Free(Node):
    """Escape hatch: a fixed-size area drawn by hand. `fn(canvas, x, y)` gets the
    top-left corner and draws with the Canvas methods (line, text, arrow...)."""

    def __init__(self, w: float, h: float, fn: Callable[[Canvas, float, float], None]) -> None:
        self.w, self.h, self.fn = w, h, fn

    def _measure(self, ctx: Ctx) -> Size:
        return (self.w, self.h)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, _, _ = self.rect
        self.fn(cv, x, y)


class _Linear(Node):
    horizontal: ClassVar[bool] = True

    def __init__(self, *items: Child, gap: float = 24, align: Align = "center", justify: Justify = "center",
                 stretch: bool = False) -> None:
        self.items: list[Node] = [node(i) for i in items]
        self.gap, self.stretch = gap, stretch
        self.cross: Align = align
        self.justify: Justify = justify

    def children(self) -> Sequence[Node]:
        return self.items

    def _measure(self, ctx: Ctx) -> Size:
        sizes = [ctx.size(c) for c in self.items]
        if not sizes:
            return (0, 0)
        main = sum(s[0 if self.horizontal else 1] for s in sizes) + self.gap * (len(sizes) - 1)
        cross = max(s[1 if self.horizontal else 0] for s in sizes)
        return (main, cross) if self.horizontal else (cross, main)

    def _layout(self, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        H = self.horizontal
        main0, main_len, cross0, cross_len = (x, w, y, h) if H else (y, h, x, w)
        sizes = [ctx.size(c) for c in self.items]
        total = sum(s[0 if H else 1] for s in sizes) + self.gap * (len(sizes) - 1)
        free, gap = main_len - total, self.gap
        cur = {"start": main0, "center": main0 + free / 2, "end": main0 + free, "between": main0}[self.justify]
        if self.justify == "between" and len(sizes) > 1:
            gap += free / (len(sizes) - 1)
        for c, (cw, ch) in zip(self.items, sizes):
            m, cr = (cw, ch) if H else (ch, cw)
            a = c._self_align or self.cross
            if self.stretch or a == "stretch":
                cr, off = cross_len, 0.0
            else:
                off = {"start": 0.0, "center": (cross_len - cr) / 2, "end": cross_len - cr}[a]
            if H:
                c.layout(cur, cross0 + off, m, cr, ctx)
            else:
                c.layout(cross0 + off, cur, cr, m, ctx)
            cur += m + gap


class Row(_Linear):
    """Children left to right. `align` is vertical, `justify` horizontal
    ("start", "center", "end", "between"); `stretch` makes all children full height."""

    horizontal = True


class Col(_Linear):
    """Children top to bottom. `align` is horizontal; `stretch` makes all children full width."""

    horizontal = False

    def __init__(self, *items: Child, gap: float = 20, align: Align = "center", justify: Justify = "center",
                 stretch: bool = False) -> None:
        super().__init__(*items, gap=gap, align=align, justify=justify, stretch=stretch)


class Split(Row):
    """Side-by-side panels with a divider line between them."""

    def __init__(self, *items: Child, gap: float = 40, divider: bool = True, align: Align = "start",
                 justify: Justify = "center", stretch: bool = False) -> None:
        super().__init__(*items, gap=gap, align=align, justify=justify, stretch=stretch)
        self.divider = divider

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        if not self.divider:
            return
        _, y, _, h = self.rect
        for a, b in zip(self.items, self.items[1:]):
            ax, _, aw, _ = a.rect
            xm = (ax + aw + b.rect[0]) / 2
            cv.line(xm, y, xm, y + h, "stroke-soft", passes=1)


class Grid(Node):
    """Rows of cells; each column is as wide as its widest cell. None leaves a cell empty.
    Cells fill their slot when `stretch` (the default), so boxes in a column line up."""

    def __init__(self, rows: Sequence[Sequence[Child | None]], gap: float = 16, col_gap: float | None = None,
                 row_gap: float | None = None, widths: Sequence[float | None] | None = None,
                 stretch: bool = True) -> None:
        if not rows:
            raise ValueError("Grid needs at least one row")
        self.rows: list[list[Node | None]] = [[None if c is None else node(c) for c in r] for r in rows]
        self.col_gap = gap if col_gap is None else col_gap
        self.row_gap = gap if row_gap is None else row_gap
        self.widths, self.stretch = widths, stretch

    def children(self) -> Sequence[Node]:
        return [c for r in self.rows for c in r if c is not None]

    def _dims(self, ctx: Ctx) -> tuple[list[float], list[float]]:
        n = max(len(r) for r in self.rows)
        cols = [0.0] * n
        heights: list[float] = []
        for r in self.rows:
            rh = 0.0
            for i, c in enumerate(r):
                if c is not None:
                    cw, ch = ctx.size(c)
                    cols[i], rh = max(cols[i], cw), max(rh, ch)
            heights.append(rh)
        if self.widths:
            cols = [w if w is not None else cols[i] for i, w in enumerate(self.widths)]
        return cols, heights

    def _measure(self, ctx: Ctx) -> Size:
        cols, heights = self._dims(ctx)
        return (sum(cols) + self.col_gap * (len(cols) - 1), sum(heights) + self.row_gap * (len(heights) - 1))

    def _layout(self, ctx: Ctx) -> None:
        x, y, w, _ = self.rect
        cols, heights = self._dims(ctx)
        x0 = x + (w - (sum(cols) + self.col_gap * (len(cols) - 1))) / 2
        cy = y
        for r, rh in zip(self.rows, heights):
            cx = x0
            for i, c in enumerate(r):
                if c is not None:
                    if self.stretch:
                        c.layout(cx, cy, cols[i], rh, ctx)
                    else:
                        cw, ch = ctx.size(c)
                        c.layout(cx + (cols[i] - cw) / 2, cy + (rh - ch) / 2, cw, ch, ctx)
                cx += cols[i] + self.col_gap
            cy += rh + self.row_gap


class Overlay(Node):
    """Children stacked on the same spot, centered."""

    def __init__(self, *items: Child) -> None:
        if not items:
            raise ValueError("Overlay needs at least one child")
        self.items: list[Node] = [node(i) for i in items]

    def children(self) -> Sequence[Node]:
        return self.items

    def _measure(self, ctx: Ctx) -> Size:
        sizes = [ctx.size(c) for c in self.items]
        return (max(s[0] for s in sizes), max(s[1] for s in sizes))

    def _layout(self, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        for c in self.items:
            cw, ch = ctx.size(c)
            c.layout(x + (w - cw) / 2, y + (h - ch) / 2, cw, ch, ctx)


class Pad(Node):
    """Space around a child, CSS order: Pad(c, 10), Pad(c, 10, 20), Pad(c, 1, 2, 3, 4),
    or by name: Pad(c, top=...)."""

    def __init__(self, child: Child, *sides: float, top: float | None = None, right: float | None = None,
                 bottom: float | None = None, left: float | None = None) -> None:
        if len(sides) == 0:
            t = r = b = l = 0.0
        elif len(sides) == 1:
            t = r = b = l = sides[0]
        elif len(sides) == 2:
            t, r = sides
            b, l = t, r
        elif len(sides) == 4:
            t, r, b, l = sides
        else:
            raise ValueError("Pad takes 1, 2 or 4 positional sides")
        self.child = node(child)
        self.t = t if top is None else top
        self.r = r if right is None else right
        self.b = b if bottom is None else bottom
        self.l = l if left is None else left

    def children(self) -> Sequence[Node]:
        return (self.child,)

    def _measure(self, ctx: Ctx) -> Size:
        w, h = ctx.size(self.child)
        return (w + self.l + self.r, h + self.t + self.b)

    def _layout(self, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        self.child.layout(x + self.l, y + self.t, w - self.l - self.r, h - self.t - self.b, ctx)


class Region(Node):
    """A dashed outline with a title around a child: "kernel", "node 1", "trusted zone"."""

    def __init__(self, title: str | None, child: Child, pad: float = 16, fill: ToneRef | None = None) -> None:
        self.title, self.child, self.p, self.fill = title, node(child), pad, fill

    def children(self) -> Sequence[Node]:
        return (self.child,)

    def tones(self) -> Iterable[ToneRef]:
        return tuple(t for t in (self._tone, self.fill) if t)

    def _th(self) -> float:
        return 24 if self.title else 0

    def _measure(self, ctx: Ctx) -> Size:
        cw, ch = ctx.size(self.child)
        tw = ctx.width(self.title or "", 13, True) + 28
        return (max(cw + 2 * self.p, tw), ch + 2 * self.p + self._th())

    def _layout(self, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        p, th = self.p, self._th()
        self.child.layout(x + p, y + p + th, w - 2 * p, h - 2 * p - th, ctx)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, w, h = self.rect
        c = classes(ctx.tone(self._tone) or "soft")
        if self.fill:
            cv.fill_rect(x, y, w, h, classes(ctx.tone(self.fill))["fill"])
        cv.dashed_rect(x, y, w, h, c["stroke"])
        if self.title:
            cv.text(x + 12, y + 20, self.title, 13, c["text"], "start", weight=700, halo=False)


class Legend(Node):
    """Color key. Legend() lists the meanings the diagram uses; Legend([("bad", "traitor")])
    lists exactly these (tone or meaning, label) pairs."""

    def __init__(self, items: Sequence[tuple[ToneRef, str]] | None = None, size: float = 13) -> None:
        self.items, self.size = items, size
        self._self_align = "start"

    def entries(self, ctx: Ctx) -> list[tuple[ToneName, str]]:
        if self.items is not None:
            pairs = [(ctx.tone(t), label) for t, label in self.items]
        else:
            pairs = [ctx.meanings[m] for m in ctx.used]
        return [(t, label) for t, label in pairs if is_tone(t)]

    def _measure(self, ctx: Ctx) -> Size:
        e = self.entries(ctx)
        if not e:
            return (0, 0)
        return (sum(22 + len(label) * self.size * 0.55 + 20 for _, label in e) - 20, 16)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, y, _, _ = self.rect
        for t, label in self.entries(ctx):
            x = cv.key(x, y + 13, t, label, self.size)


class At:
    """An event on a Track: its value on the axis and what to show there."""

    def __init__(self, value: float, item: Child, side: TrackSide = "above", level: int = 0,
                 tone: ToneRef | None = None, mark: TickMark | None = None) -> None:
        self.value, self.level, self.tone = value, level, tone
        self.side: TrackSide = side
        self.mark: TickMark = mark if mark is not None else ("dot" if tone else "circle")
        self.item: Node = Label(item, size=13, tone=tone, bold=bool(tone)) if isinstance(item, str) else node(item)


class Track(Node):
    """A horizontal axis with things placed by value: the base of timelines and scales."""

    def __init__(self, *events: At, start: float | None = None, end: float | None = None,
                 length: float = 480, axis: bool = True) -> None:
        self.events = list(events)
        vals = [e.value for e in self.events] or [0.0, 1.0]
        self.start = min(vals) if start is None else start
        self.end = max(vals) if end is None else end
        self.length, self.axis = length, axis

    def children(self) -> Sequence[Node]:
        return [e.item for e in self.events]

    def tones(self) -> Iterable[ToneRef]:
        return tuple(e.tone for e in self.events if e.tone)

    def _bands(self, ctx: Ctx) -> dict[TrackSide, list[float]]:
        bands: dict[TrackSide, dict[int, float]] = {"above": {}, "below": {}}
        for e in self.events:
            h = ctx.size(e.item)[1]
            bands[e.side][e.level] = max(bands[e.side].get(e.level, 0.0), h)
        return {s: [b.get(i, 0.0) for i in range(max(b) + 1)] if b else [] for s, b in bands.items()}

    @staticmethod
    def _band_h(hs: Sequence[float]) -> float:
        return sum(hs) + 6 * max(0, len(hs) - 1) + (10 if hs else 0)

    def _measure(self, ctx: Ctx) -> Size:
        b = self._bands(ctx)
        widest = max([ctx.size(e.item)[0] for e in self.events] or [0.0])
        return (max(self.length, widest), self._band_h(b["above"]) + 24 + self._band_h(b["below"]))

    def x(self, value: float) -> float:
        """Where `value` sits on the axis (after layout)."""
        x, _, w, _ = self.rect
        span = (self.end - self.start) or 1
        return x + 12 + (w - 36) * (value - self.start) / span

    def axis_y(self, ctx: Ctx) -> float:
        return self.rect[1] + self._band_h(self._bands(ctx)["above"]) + 12

    def _layout(self, ctx: Ctx) -> None:
        x, _, w, _ = self.rect
        b, ay = self._bands(ctx), self.axis_y(ctx)
        for e in self.events:
            cw, ch = ctx.size(e.item)
            cx = min(max(self.x(e.value) - cw / 2, x), x + w - cw)
            off = sum(b[e.side][: e.level]) + 6 * e.level
            cy = ay - 22 - off - ch if e.side == "above" else ay + 22 + off
            e.item.layout(cx, cy, cw, ch, ctx)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, _, w, _ = self.rect
        ay = self.axis_y(ctx)
        if self.axis:
            cv.arrow(x, ay, x + w, ay, "stroke-soft", head=10)
        for e in self.events:
            c, ex = classes(ctx.tone(e.tone)), self.x(e.value)
            cv.line(ex, ay - 10, ex, ay + 10, c["stroke"], passes=1)
            if e.mark == "dot":
                cv.dot(ex, ay, 5, c["solid"])
            elif e.mark == "circle":
                cv.circle(ex, ay, 5, c["stroke"], "fill-surface")


class LaneRow(ABC):
    """One row of a sequence diagram."""

    tone: ToneRef | None = None

    @abstractmethod
    def height(self) -> float: ...

    def lanes(self) -> tuple[str, ...]:
        """The lanes this row refers to, checked against the diagram's lanes."""
        return ()


class Msg(LaneRow):
    """A message between two lanes. `mark` ("cross"/"check") lands at the receiver;
    `note` is a short line under the arrow at the receiving end."""

    def __init__(self, src: str, dst: str, label: str = "", tone: ToneRef | None = None,
                 mark: MarkKind | None = None, note: str | None = None) -> None:
        if src == dst:
            raise ValueError("a Msg needs two different lanes; use Act for a lane's own step")
        self.src, self.dst, self.label, self.tone, self.note = src, dst, label, tone, note
        self.mark: MarkKind | None = mark

    def height(self) -> float:
        return 40 + (20 if self.note else 0)

    def lanes(self) -> tuple[str, ...]:
        return (self.src, self.dst)


class Act(LaneRow):
    """Something a lane does or thinks, written beside its lifeline. `bar=n` draws a
    solid line on the lifeline over this row and the next n-1 rows (a pause, a hold)."""

    def __init__(self, lane: str, text: str, tone: ToneRef | None = None, bar: int = 0) -> None:
        self.lane, self.text, self.tone, self.bar = lane, text, tone, bar

    def height(self) -> float:
        return 18 * len(self.text.split("\n")) + 12

    def lanes(self) -> tuple[str, ...]:
        return (self.lane,)


class Gap(LaneRow):
    def __init__(self, h: float = 20) -> None:
        self.h = h

    def height(self) -> float:
        return self.h


LaneSpec: TypeAlias = "str | tuple[str, ToneRef | None]"
"""A lane name, or (name, tone) to tint its head."""


class Lanes(Node):
    """A sequence diagram: lane heads, dashed lifelines and rows of Msg / Act / Gap.
    lanes["storage"] is that lane's head box, for edges from outside."""

    def __init__(self, lanes: Sequence[LaneSpec], rows: Iterable[LaneRow], col: float | None = None,
                 head_size: float = 15) -> None:
        if not lanes:
            raise ValueError("Lanes needs at least one lane")
        self.names: list[str] = []
        self.heads: dict[str, Box] = {}
        for ln in lanes:
            name, tone = ln if isinstance(ln, tuple) else (ln, None)
            self.names.append(name)
            self.heads[name] = Box(name, size=head_size).tone(tone)
        self.rows, self.col = list(rows), col
        self._ys: list[float] = []
        for r in self.rows:
            for lane in r.lanes():
                if lane not in self.heads:
                    raise ValueError(f"unknown lane {lane!r}; lanes are {self.names}")

    def __getitem__(self, name: str) -> Box:
        return self.heads[name]

    def children(self) -> Sequence[Node]:
        return [self.heads[n] for n in self.names]

    def tones(self) -> Iterable[ToneRef]:
        return tuple(r.tone for r in self.rows if r.tone)

    def _col(self, ctx: Ctx) -> float:
        return self.col or max(130, max(ctx.size(b)[0] for b in self.heads.values()) + 24)

    def _measure(self, ctx: Ctx) -> Size:
        return (self._col(ctx) * len(self.names), 40 + 30 + sum(r.height() for r in self.rows) + 10)

    def lane_x(self, name: str) -> float:
        x, _, w, _ = self.rect
        return x + w / len(self.names) * (self.names.index(name) + 0.5)

    def _layout(self, ctx: Ctx) -> None:
        _, y, w, _ = self.rect
        col = w / len(self.names)
        for n in self.names:
            hw = min(col - 16, max(110, ctx.size(self.heads[n])[0]))
            self.heads[n].layout(self.lane_x(n) - hw / 2, y, hw, 40, ctx)
        cur, self._ys = y + 70, []
        for r in self.rows:
            self._ys.append(cur)
            cur += r.height()

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        _, y, _, h = self.rect
        for n in self.names:
            lx, yy = self.lane_x(n), y + 48
            while yy < y + h:
                cv.line(lx, yy, lx, min(yy + 9, y + h), "stroke-soft", rough=0.5, passes=1)
                yy += 16
        ends = self._ys[1:] + [y + h - 10]
        for i, (r, top) in enumerate(zip(self.rows, self._ys)):
            c = classes(ctx.tone(r.tone))
            if isinstance(r, Msg):
                x1, x2, ay = self.lane_x(r.src), self.lane_x(r.dst), top + 26
                d = 1 if x2 > x1 else -1
                cv.arrow(x1 + 4 * d, ay, x2 - 4 * d, ay, c["stroke"], head=9)
                if r.label:
                    cv.text((x1 + x2) / 2, ay - 8, r.label, 13, c["text"], halo=True)
                mark_cls = c["stroke"] if r.tone else "stroke-accent"
                if r.mark == "cross":
                    cv.cross(x2 - 30 * d, ay, 6, mark_cls)
                elif r.mark == "check":
                    cv.check(x2 - 30 * d, ay, mark_cls)
                if r.note:
                    cv.text(x2 - 8 * d, ay + 26, r.note, 13, c["text"], "end" if d > 0 else "start",
                            weight=700, halo=True)
            elif isinstance(r, Act):
                lx = self.lane_x(r.lane)
                right = self.names.index(r.lane) < len(self.names) - 1 or len(self.names) == 1
                for j, line in enumerate(r.text.split("\n")):
                    cv.text(lx + (8 if right else -8), top + 16 + 18 * j, line, 13, c["text"],
                            "start" if right else "end", halo=True)
                if r.bar:
                    bottom = ends[min(i + r.bar - 1, len(ends) - 1)]
                    cv.line(lx, top, lx, bottom, c["stroke"])


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
    if L <= 2 * d:
        return p
    return (p[0] + (q[0] - p[0]) * d / L, p[1] + (q[1] - p[1]) * d / L)


class Edge(ABC):
    """Something drawn between or around nodes after layout."""

    tone: ToneRef | None = None

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


def _walk(n: Node, path: str = "0") -> Iterator[tuple[str, Node]]:
    yield path, n
    for i, c in enumerate(n.children()):
        yield from _walk(c, f"{path}.{i}")


class Placed(NamedTuple):
    """A laid-out diagram: (path, node) pairs in draw order, all edges, the context and canvas size."""

    nodes: list[tuple[str, Node]]
    edges: list[Edge]
    ctx: Ctx
    width: float
    height: float


LegendSpec: TypeAlias = "bool | Legend | Sequence[tuple[ToneRef, str]]"
"""True for an automatic legend, a Legend, or explicit (tone or meaning, label) pairs."""


class Diagram:
    """The root: a body, edges, and an optional footer (headline, note, legend).

    `title` is the alt text read by screen readers; write the whole idea there.
    `width` is the canvas width (it grows if the content needs more); None fits
    the content."""

    def __init__(self, body: Child, *, edges: Iterable[Edge] = (), headline: str | Node | None = None,
                 note: str | Node | None = None, legend: LegendSpec = False, title: str | None = None,
                 width: float | None = 560, margin: float = 20, gap: float = 26, seed: int = 1) -> None:
        self.body, self.edges = node(body), list(edges)
        self.headline, self.note, self.legend = headline, note, legend
        self.title, self.width, self.margin, self.gap, self.seed = title, width, margin, gap, seed

    def _root(self) -> Node:
        foot: list[Node] = []
        if self.headline:
            foot.append(Headline(self.headline) if isinstance(self.headline, str) else self.headline)
        if self.note:
            foot.append(Note(self.note) if isinstance(self.note, str) else self.note)
        if isinstance(self.legend, Legend):
            foot.append(self.legend)
        elif self.legend is True:
            foot.append(Legend())
        elif self.legend:
            foot.append(Legend(self.legend))
        if not foot:
            return self.body
        tail = Col(*foot, gap=8).align("stretch")
        return Col(self.body, tail, gap=self.gap)

    def layout(self, style: Style = "hand", theme: Theme = "paper",
               meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> Placed:
        """Measure and place everything without drawing. Every node's `.rect` is
        set afterwards; `Diagram.check` and `render` both start here."""
        ctx = Ctx(style, theme, meanings, box_font)
        root = self._root()
        nodes = list(_walk(root))
        seen: set[int] = set()
        for _, n in nodes:
            if id(n) in seen:
                raise ValueError(f"{n!r} appears twice in the diagram; build each copy separately")
            seen.add(id(n))
        edges = [*self.edges] + [e for _, n in nodes for e in n.linked]

        refs = [t for _, n in nodes for t in n.tones()] + [e.tone for e in edges if e.tone]
        for t in refs:
            if ctx.tone(t) and t in ctx.meanings and t not in ctx.used:
                ctx.used.append(t)

        m = self.margin
        nw, nh = ctx.size(root)
        width = max(self.width or 0, nw + 2 * m)

        def place(ox: float, oy: float) -> BBox:
            root.layout(ox, oy, width - 2 * m, nh, ctx)
            boxes = [(x, y, x + w, y + h) for x, y, w, h in (n.rect for _, n in nodes) if w or h]
            boxes += [e.bbox(ctx) for e in edges]
            return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes))

        x0, y0, x1, y1 = place(m, m)
        dx, dy = max(0, m - x0), max(0, m - y0)
        if dx or dy:
            x0, y0, x1, y1 = place(m + dx, m + dy)
        return Placed(nodes, edges, ctx, max(width, x1 + m), y1 + m)

    def render(self, style: Style = "hand", theme: Theme = "paper",
               meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> Canvas:
        """Lay out and draw; returns the core Canvas (call .svg() on it, or use Diagram.svg)."""
        p = self.layout(style, theme, meanings, box_font)
        title = self.title or (self.headline if isinstance(self.headline, str) else None) or "diagram"
        cv = Canvas(math.ceil(p.width), math.ceil(p.height), title, seed=self.seed, clean=p.ctx.clean)
        cv.box_font = p.ctx.box_font
        for path, n in p.nodes:
            cv.rnd = random.Random(zlib.crc32(f"{self.seed}/{path}".encode()))
            n.draw(cv, p.ctx)
        for i, e in enumerate(p.edges):
            cv.rnd = random.Random(zlib.crc32(f"{self.seed}/e{i}".encode()))
            e.draw(cv, p.ctx)
        return cv

    def check(self, style: Style = "hand", theme: Theme = "paper",
              meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> list[Issue]:
        """Lay out and look for problems a reader would see: overlapping shapes,
        arrows through boxes, labels on shapes, text wider than its box. Empty is good."""
        from .lint import lint

        return lint(self, self.layout(style, theme, meanings, box_font))

    def svg(self, style: Style = "hand", theme: Theme = "paper",
            meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> str:
        cv = self.render(style, theme, meanings, box_font)
        return cv.svg() if theme == "blog" else cv.svg(inline=True, palette=theme)
