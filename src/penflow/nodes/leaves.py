"""Nodes without children: text, boxes, cells, circles, marks and spacers."""

from __future__ import annotations

from collections.abc import Callable

from ..core import Anchor, Canvas, FontName, is_tone
from .base import CIRCLED, Child, Ctx, MarkKind, Node, Size, TextAlign, ToneRef, classes


def node(x: Child) -> Node:
    """Strings become labels; nodes pass through."""
    return x if isinstance(x, Node) else Label(x)


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
