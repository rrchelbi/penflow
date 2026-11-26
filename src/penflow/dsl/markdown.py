"""Markdown files with ```penflow (and ```mermaid) fences."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ..core import FontName, figure
from ..lint import Issue
from ..nodes import Diagram, MeaningSpec, Style, Theme
from ..publish import Builder, Doc, Entry, Rendered, to_svg
from .errors import SketchError
from .frontmatter import Settings, file_settings
from .parse import Sketch, parse_sketch
from .templates import Template


@dataclass
class Fence:
    """A ```penflow (or ```mermaid) fence in a Markdown text: its body and where it sits (0-based line indexes)."""

    open: int
    close: int
    body: str
    kind: str = "penflow"


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)")


FENCE_TAGS: Final = ("penflow", "sketch")
"""Info strings of a Penflow fence; `sketch` is the tag from before the project was renamed."""


def fences(md: str, kinds: Sequence[str] = FENCE_TAGS) -> list[Fence]:
    """Every top-level fence whose info string is one of `kinds`. Fences nested in longer ones
    (````markdown) are skipped."""
    lines = md.split("\n")
    out: list[Fence] = []
    i = 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        mark, info = m.group(1), m.group(2)
        j = i + 1
        while j < len(lines) and not re.match(r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}\s*$",
                                               lines[j]):
            j += 1
        if info in kinds and mark.startswith("`"):
            if j >= len(lines):
                raise SketchError(i + 1, f"this {info} fence is never closed with ```")
            out.append(Fence(i, j, "\n".join(lines[i + 1:j]), info))
        i = j + 1
    return out


def _constant(d: Diagram) -> Builder:
    return lambda: d


_FIGURE = r'<figure class="sketch not-prose" data-sketch="{id}">.*?</figure>'


class SketchDoc(Doc):
    """A Markdown file whose diagrams are written in ```penflow fences. Works with run(),
    `python -m penflow render` and `python -m penflow check`. With `mermaid=True`, ```mermaid
    fences are converted (see convert_mermaid) and drawn too."""

    def __init__(self, path: str | pathlib.Path, *, style: Style = "hand", theme: Theme = "paper",
                 meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None,
                 mermaid: bool = False) -> None:
        from ..mermaid import convert_mermaid  # mermaid imports dsl modules, so this import stays local

        super().__init__(path, style=style, theme=theme, meanings=meanings, box_font=box_font)
        self.kinds: tuple[str, ...] = (*FENCE_TAGS, "mermaid") if mermaid else FENCE_TAGS
        self.notes: list[tuple[str, str]] = []  # (sketch id, what the Mermaid conversion approximated)
        md = self.path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        where = str(self.path)
        try:
            base = file_settings(md)
            base = Settings(base.style or style, base.theme or theme, base.box_font or box_font,
                            {**(meanings or {}), **base.meanings})
            self.sketches: list[Sketch] = []
            self.templates: dict[str, Template] = {}
            for k, f in enumerate(fences(md, self.kinds), 1):
                if f.kind == "mermaid":
                    try:
                        conv = convert_mermaid(f.body)
                    except SketchError as e:
                        raise SketchError(e.line + f.open + 1, e.message) from None
                    s = parse_sketch(conv.text, f.open + 2, base, self.templates,
                                     [n + f.open + 1 for n in conv.lines])
                    self.notes += [(f"sketch_{k}", n) for n in conv.notes]
                else:
                    s = parse_sketch(f.body, f.open + 2, base, self.templates)
                s.id = s.id or f"sketch_{k}"
                if any(o.id == s.id for o in self.sketches):
                    raise SketchError(s.line, f"two sketches have the id {s.id!r}; give one a different id:")
                self.sketches.append(s)
        except SketchError as e:
            raise e.at(where) from None
        for s in self.sketches:
            assert s.id is not None
            self.diagrams.append(Entry(s.id, s.caption, "", _constant(s.diagram)))

    def _opts(self, s: Sketch, style: Style | None, theme: Theme | None) -> tuple[Style, Theme]:
        return style or s.settings.style or self.style, theme or s.settings.theme or self.theme

    def render(self, style: Style | None = None, theme: Theme | None = None) -> list[Rendered]:
        out: list[Rendered] = []
        for s in self.sketches:
            st, th = self._opts(s, style, theme)
            assert s.id is not None
            out.append(Rendered(s.id, s.caption, "", to_svg(s.diagram, st, th, s.settings.meanings,
                                                            s.settings.box_font)))
        return out

    def check(self, style: Style | None = None, theme: Theme | None = None) -> list[tuple[str, Issue]]:
        out: list[tuple[str, Issue]] = []
        for s in self.sketches:
            st, th = self._opts(s, style, theme)
            assert s.id is not None
            out += [(s.id, i) for i in s.diagram.check(st, th, s.settings.meanings, s.settings.box_font)]
        return out

    def build(self, rendered: Sequence[Rendered] | None = None, write: bool = True) -> str:
        """Put each figure right after its fence, or replace the one put there before."""
        items = list(self.render() if rendered is None else rendered)
        raw = self.path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        md = raw.replace("\r\n", "\n")
        for k in reversed(range(len(items))):
            r = items[k]
            block = figure(r.id, r.svg, r.caption)
            found = re.search(_FIGURE.format(id=re.escape(r.id)), md, re.DOTALL)
            if found:
                md = md[:found.start()] + block + md[found.end():]
                continue
            fs = fences(md, self.kinds)
            if k >= len(fs):
                raise ValueError(f"{self.path}: the file has fewer penflow fences than when it was read")
            lines = md.split("\n")
            lines[fs[k].close + 1:fs[k].close + 1] = ["", block, ""]
            md = "\n".join(lines)
        if write:
            self.path.write_bytes((md.replace("\n", "\r\n") if crlf else md).encode("utf-8"))
        return md
