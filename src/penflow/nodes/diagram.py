"""The root of a drawing: body, edges and footer, laid out and drawn with per-node seeds."""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeAlias

from ..core import Canvas, FontName
from .base import BBox, Child, Ctx, MeaningSpec, Node, Style, Theme, ToneRef
from .edges import Edge
from .layout import Col, Legend
from .leaves import Headline, Note, node

if TYPE_CHECKING:
    from ..lint import Issue

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

    dialect: Literal["python", "penflow"] = "python"
    """How the diagram was written. Diagram.check words its fixes to match."""

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
        from ..lint import lint  # lint imports the node types, so this import stays local

        return lint(self, self.layout(style, theme, meanings, box_font))

    def svg(self, style: Style = "hand", theme: Theme = "paper",
            meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> str:
        cv = self.render(style, theme, meanings, box_font)
        return cv.svg() if theme == "blog" else cv.svg(inline=True, palette=theme)
