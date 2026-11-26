"""Typed access to `{key: value}` attributes, and the option values each key accepts."""

from __future__ import annotations

from typing import Final, NoReturn, TypeVar

from ..core import FontName
from ..nodes import (
    Align,
    BracketSide,
    Justify,
    LabelSide,
    MarkKind,
    Node,
    Route,
    Style,
    TextAlign,
    Theme,
    TickMark,
    TrackSide,
)
from .errors import SketchError
from .lexer import NUM, AttrMap, number

T = TypeVar("T", bound=str)
ALIGNS: Final[tuple[Align, ...]] = ("start", "center", "end", "stretch")
JUSTIFIES: Final[tuple[Justify, ...]] = ("start", "center", "end", "between")
TEXT_ALIGNS: Final[tuple[TextAlign, ...]] = ("start", "center", "end")
LABEL_SIDES: Final[tuple[LabelSide, ...]] = ("auto", "above", "below", "left", "right")
ROUTES: Final[tuple[Route, ...]] = ("hv", "vh")
STYLES: Final[tuple[Style, ...]] = ("hand", "clean")
THEMES: Final[tuple[Theme, ...]] = ("paper", "auto", "blog")
FONT_NAMES: Final[tuple[FontName, ...]] = ("hand", "mono")
TICK_MARKS: Final[tuple[TickMark, ...]] = ("dot", "circle", "none")
TRACK_SIDES: Final[tuple[TrackSide, ...]] = ("above", "below")
BRACKET_SIDES: Final[tuple[BracketSide, ...]] = ("top", "bottom")
MARK_KINDS: Final[tuple[MarkKind, ...]] = ("check", "cross")


class Attrs:
    """Typed access to an attribute map; done() rejects keys nobody asked for."""

    def __init__(self, items: AttrMap, line: int, what: str) -> None:
        self.items, self.line, self.what = items, line, what
        self.asked: list[str] = []

    def fail(self, msg: str) -> NoReturn:
        raise SketchError(self.line, msg)

    def _get(self, key: str) -> str | bool | None:
        self.asked.append(key)
        return self.items.get(key)

    def text(self, key: str) -> str | None:
        v = self._get(key)
        if isinstance(v, bool):
            self.fail(f"{key} needs a value: {{{key}: ...}}")
        return v

    def num(self, key: str) -> float | None:
        v = self.text(key)
        if v is None:
            return None
        if not NUM.match(v):
            self.fail(f"{key} is a number, not {v!r}")
        return number(v)

    def flag(self, key: str) -> bool | None:
        v = self._get(key)
        if v is None or isinstance(v, bool):
            return v
        if v in ("true", "false"):
            return v == "true"
        self.fail(f"{key} is true or false, not {v!r}")

    def choice(self, key: str, options: tuple[T, ...]) -> T | None:
        v = self.text(key)
        if v is None:
            return None
        for o in options:
            if o == v:
                return o
        self.fail(f"{key} is one of {', '.join(options)}, not {v!r}")

    def done(self) -> None:
        unknown = [k for k in self.items if k not in self.asked]
        if unknown:
            keys = ", ".join(dict.fromkeys(self.asked))
            self.fail(f"unknown attribute {unknown[0]!r} for {self.what}; its attributes are: {keys}")


def apply_fixed(n: Node, a: Attrs) -> None:
    w, h = a.num("w"), a.num("h")
    if w is not None or h is not None:
        n.fixed(w, h)


def apply_common(n: Node, a: Attrs, tone: str | None, self_align: bool = True) -> None:
    t = a.text("tone")
    if t and tone:
        a.fail("the tone is given twice (:::name and tone:)")
    n.tone(tone or t)
    if a.flag("dashed"):
        n.dashed()
    apply_fixed(n, a)
    if self_align:
        al: Align | None = a.choice("align", ALIGNS)
        if al:
            n.align(al)
