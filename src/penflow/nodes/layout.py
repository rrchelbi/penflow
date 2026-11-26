"""Containers that arrange their children: rows, columns, grids, padding, regions, legends."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from typing import ClassVar

from ..core import Canvas, ToneName, is_tone
from .base import Align, Child, Ctx, Justify, Node, Size, ToneRef, classes
from .leaves import node


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
        for c, (cw, ch) in zip(self.items, sizes, strict=True):
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
        for a, b in itertools.pairwise(self.items):
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
        for r, rh in zip(self.rows, heights, strict=True):
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
