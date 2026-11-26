"""The node protocol and what every node shares: option types, tones, sizing context, ports.

A node knows its natural size (`measure`) and draws itself inside the frame its parent gives it
(`layout`, then `draw`). Modifiers change the node in place and return it, so a node kept in a
variable is the one in the tree and edges can point at it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Final, Literal, Self, TypeAlias, TypedDict, TypeGuard

from ..core import TONES, Canvas, FontName, Point, ToneName, is_tone

if TYPE_CHECKING:
    from .edges import Edge
    from .layout import Pad

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
    origin: str | None = None
    """Where the node was written, for check messages: "c1_l1 (line 41)". Set by the DSL."""

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
        from .layout import Pad

        return Pad(self, *sides, top=top, right=right, bottom=bottom, left=left)

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
