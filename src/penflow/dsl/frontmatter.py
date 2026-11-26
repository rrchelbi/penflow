"""Front matter: per-fence settings, and the `penflow:` map in a file's own front matter.

The map's old name, `sketchkit:`, is still read."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, TypeAlias

from ..core import FontName
from ..nodes import MeaningSpec, Style, Theme, is_resolved_tone
from .attrs import FONT_NAMES, STYLES, THEMES, Attrs
from .errors import SketchError, snake
from .lexer import SNAKE, Scanner, text

FENCE_KEYS: Final = ("id", "caption", "headline", "note", "legend", "title", "width", "margin", "gap", "seed",
                     "style", "theme", "box_font", "meanings")
FILE_KEYS: Final = ("style", "theme", "box_font", "meanings")
Value: TypeAlias = "str | bool | dict[str, str | bool]"


def parse_value(raw: str, line: int) -> Value:
    v = raw.strip()
    if v.startswith("{"):
        sc = Scanner(v, line)
        m = sc.attrs()
        if sc.rest().strip():
            sc.fail(f"unexpected {sc.rest().strip()!r} after the map")
        return m
    if v.startswith('"'):
        return text(v, line)
    if v in ("true", "false"):
        return v == "true"
    return v


def parse_front_matter(lines: Sequence[tuple[int, str]]) -> dict[str, tuple[int, Value]]:
    """`key: value` lines, plus one level of `key:` followed by indented `k: v` lines."""
    out: dict[str, tuple[int, Value]] = {}
    parent: tuple[str, int, dict[str, str | bool]] | None = None
    for no, raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw.startswith(" ")
        m = re.match(r"\s*([A-Za-z0-9_]+):(?:\s+(.*))?\s*\Z", raw)
        if not m:
            raise SketchError(no, f"front matter lines are key: value, not {raw.strip()!r}")
        key, val = m.group(1), (m.group(2) or "").strip()
        if not SNAKE.match(key):
            raise SketchError(no, f"key {key!r} isn't snake_case; write {snake(key)!r}")
        if indented:
            if parent is None:
                raise SketchError(no, "this line is indented but has no parent key above it")
            v = parse_value(val, no)
            if isinstance(v, dict):
                raise SketchError(no, "maps nest one level only")
            parent[2][key] = v
            continue
        if key in out:
            raise SketchError(no, f"{key!r} is given twice")
        if val == "":
            nested: dict[str, str | bool] = {}
            out[key] = (no, nested)
            parent = (key, no, nested)
        else:
            out[key] = (no, parse_value(val, no))
            parent = None
    return out


@dataclass
class Settings:
    """Rendering defaults from front matter: the file's `penflow:` map or one fence's."""

    style: Style | None = None
    theme: Theme | None = None
    box_font: FontName | None = None
    meanings: dict[str, MeaningSpec] = field(default_factory=dict[str, MeaningSpec])


def read_settings(fm: Mapping[str, tuple[int, Value]], keys: Sequence[str], base: Settings | None = None) -> Settings:
    s = Settings(base.style, base.theme, base.box_font, dict(base.meanings)) if base else Settings()
    for key, (no, v) in fm.items():
        if key not in keys:
            raise SketchError(no, f"unknown key {key!r}; the keys are: {', '.join(keys)}")
        if key == "meanings":
            if not isinstance(v, dict):
                raise SketchError(no, "meanings is a map: meanings: {loyal: cyan, traitor: orange}")
            for name, tone in v.items():
                if not isinstance(tone, str) or not is_resolved_tone(tone):
                    raise SketchError(no, f"meaning {name!r} needs a tone: cyan, orange, rust, slate, accent "
                                          "or soft")
                s.meanings[name] = tone
            continue
        if key in ("style", "theme", "box_font"):
            a = Attrs({key: v} if isinstance(v, str) else {}, no, "front matter")
            if not isinstance(v, str):
                raise SketchError(no, f"{key} needs a word")
            if key == "style":
                s.style = a.choice(key, STYLES)
            elif key == "theme":
                s.theme = a.choice(key, THEMES)
            else:
                s.box_font = a.choice(key, FONT_NAMES)
    return s


def file_settings(md: str) -> Settings:
    """The `penflow:` map in a Markdown file's own front matter; other keys are left alone."""
    lines = md.split("\n")
    if not lines or lines[0].strip() != "---":
        return Settings()
    end = next((j for j in range(1, len(lines)) if lines[j].strip() == "---"), None)
    if end is None:
        return Settings()
    start = next((j for j in range(1, end) if re.match(r"(?:penflow|sketchkit):\s*$", lines[j])), None)
    if start is None:
        return Settings()
    stop = next((j for j in range(start + 1, end) if lines[j].strip() and not lines[j].startswith(" ")), end)
    fm = parse_front_matter([(j + 1, lines[j][2:] if lines[j].startswith("  ") else lines[j])
                 for j in range(start + 1, stop)])
    return read_settings(fm, FILE_KEYS)
