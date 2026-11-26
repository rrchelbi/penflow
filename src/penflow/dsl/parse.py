"""Parsing one fence: front matter, templates and body, into a Diagram."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..nodes import Col, Diagram
from .builder import NodeBuilder
from .errors import SketchError, snake
from .frontmatter import FENCE_KEYS, FILE_KEYS, Settings, Value, parse_front_matter, read_settings
from .lexer import NUM, SNAKE, SourceLine, number, source_tree
from .syntax import parse_line
from .templates import Template, parse_template


@dataclass
class Sketch:
    """One parsed fence: its diagram, its figure id and caption, and its settings."""

    id: str | None
    caption: str
    diagram: Diagram
    settings: Settings
    line: int


def parse_sketch(source: str, first_line: int = 1, defaults: Settings | None = None,
                 templates: dict[str, Template] | None = None, line_numbers: Sequence[int] | None = None) -> Sketch:
    """Parse the inside of one ```penflow fence (front matter and body). `first_line` is the
    file line of the text's first line, so errors and checks point into the file. `templates` is
    shared by the fences of one file: a fence can use the templates of the fences before it.
    `line_numbers` gives each line its own number instead, for text converted from Mermaid."""
    raw = source.replace("\r\n", "\n").split("\n")
    lines = [(line_numbers[i] if line_numbers and i < len(line_numbers) else first_line + i, s)
             for i, s in enumerate(raw)]
    fm: dict[str, tuple[int, Value]] = {}
    body = lines
    start = next((i for i, (_, s) in enumerate(lines) if s.strip()), None)
    if start is not None and lines[start][1].strip() == "---":
        end = next((j for j in range(start + 1, len(lines)) if lines[j][1].strip() == "---"), None)
        if end is None:
            raise SketchError(lines[start][0], "front matter starts with --- but has no closing ---")
        fm = parse_front_matter(lines[start + 1:end])
        body = lines[end + 1:]
    settings = read_settings({k: v for k, v in fm.items() if k in FILE_KEYS or k not in FENCE_KEYS}, FENCE_KEYS,
                         defaults)
    tree = source_tree(body)
    known = {} if templates is None else templates
    rest: list[SourceLine] = []
    for s in tree:
        if s.text.split(" ", 1)[0].split("(", 1)[0] == "template":
            if rest:
                raise SketchError(s.no, "templates go before the body of the fence")
            t = parse_template(s)
            if t.name in known:
                raise SketchError(s.no, f"template {t.name} is already defined (line {known[t.name].line})")
            known[t.name] = t
        else:
            rest.append(s)
    if not rest:
        raise SketchError(tree[-1].no if tree else first_line, "the sketch has no body (templates alone don't "
                          "make a diagram; define them in the first fence that uses them)")
    items = [parse_line(s) for s in rest]
    b = NodeBuilder(known)
    b.expand(items)
    b.declare_all(items)
    roots, top_edges = b.items(items)
    if not roots:
        raise SketchError(rest[0].no, "the body declares no nodes")
    root = roots[0] if len(roots) == 1 else Col(*roots)
    edges = [edge for e in top_edges for edge in b.edges(e)]
    for owner, e, side in b.pending:
        owner.link(*b.edges(e, side))

    def get(key: str) -> tuple[int, Value] | None:
        return fm.get(key)

    def txt(key: str) -> str | None:
        v = get(key)
        if v is None:
            return None
        if not isinstance(v[1], str):
            raise SketchError(v[0], f"{key} is text")
        return v[1]

    def num(key: str, default: float) -> float:
        v = txt(key)
        if v is None:
            return default
        if not NUM.match(v):
            raise SketchError(fm[key][0], f"{key} is a number, not {v!r}")
        return number(v)

    legend = get("legend")
    if legend is not None and not isinstance(legend[1], bool):
        raise SketchError(legend[0], "legend is true or false")
    sid = txt("id")
    if sid is not None and not SNAKE.match(sid):
        raise SketchError(fm["id"][0], f"id {sid!r} isn't snake_case; write {snake(sid)!r}")
    width_raw = txt("width")
    width = None if width_raw == "none" else num("width", 560)
    d = Diagram(root, edges=edges, headline=txt("headline"), note=txt("note"),
                legend=bool(legend and legend[1]), title=txt("title"), width=width,
                margin=num("margin", 20), gap=num("gap", 26), seed=int(num("seed", 1)))
    d.dialect = "penflow"
    return Sketch(sid, txt("caption") or "", d, settings, first_line)
