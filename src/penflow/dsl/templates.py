"""`template name(params)` and `use name as copy {...}`.

A template is checked when it's defined: each $param is replaced by a marker the lexer rejects in
ids and keywords. A use fills the text in, parses it, and prefixes every id with the copy's name.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .errors import SketchError, snake
from .lexer import SENTINEL, SNAKE, Scanner, SourceLine
from .syntax import (
    Block,
    EdgeLine,
    GridRow,
    Item,
    ItemsLine,
    MessageLine,
    NodeLine,
    NoteLine,
    Participant,
    SetLine,
    Use,
    parse_line,
)


@dataclass
class Template:
    """A `template name(params)` block: lines to stamp out with `use name as instance {...}`."""

    name: str
    params: tuple[str, ...]
    line: int
    body: list[SourceLine]


_PARAM = re.compile(r"\$(\$|[a-z][a-z0-9_]*)")
BAD_ARG = re.compile(r'[\[\](){}|"\n]|:::|-->|-\.->')


def substitute(s: str, line: int, values: Mapping[str, str], t: Template) -> str:
    def rep(m: re.Match[str]) -> str:
        k = m.group(1)
        if k == "$":
            return "$"
        if k not in values:
            raise SketchError(line, f"${k} isn't a parameter of template {t.name}; its parameters are "
                                    f"{', '.join(t.params) or '(none)'} (write $$ for a literal $)")
        return values[k]

    return _PARAM.sub(rep, s)


def copy_lines(srcs: Sequence[SourceLine], fn: Callable[[str, int], str]) -> list[SourceLine]:
    return [SourceLine(s.no, s.indent, fn(s.text, s.no), copy_lines(s.children, fn)) for s in srcs]


def parse_template(src: SourceLine) -> Template:
    sc = Scanner(src.text, src.no)
    sc.word()
    sc.ws()
    name = sc.ident("template name")
    if not sc.eat("("):
        sc.fail(f"write template {name}(param, ...) with its parameters in parentheses")
    raw = sc.until((")",))
    if not sc.eat(")") or sc.rest().strip():
        sc.fail(f"write template {name}(param, ...) and indent its lines under it")
    params = tuple(p.strip() for p in raw.split(",") if p.strip())
    for p in params:
        if not SNAKE.match(p):
            sc.fail(f"parameter {p!r} isn't snake_case; write {snake(p)!r}")
    if len(set(params)) != len(params):
        sc.fail("a parameter is listed twice")
    if not src.children:
        sc.fail(f"template {name} has no lines indented under it")
    t = Template(name, params, src.no, src.children)
    marked = {p: f"{SENTINEL}{p}{SENTINEL}" for p in params}
    for s in copy_lines(t.body, lambda x, no: substitute(x, no, marked, t)):  # $params in the wrong place fail here
        parse_line(s)
    return t


def prefix_ids(items: Sequence[Item], p: str) -> None:
    """Make a template copy's ids its own: cmd -> c1_cmd."""
    for it in items:
        if isinstance(it, (NodeLine, Participant)):
            it.mention.id = p + it.mention.id
        elif isinstance(it, EdgeLine):
            for e in it.ends:
                e.id = p + e.id
        elif isinstance(it, GridRow):
            for c in it.cells:
                if c:
                    c.id = p + c.id
        elif isinstance(it, ItemsLine):
            for m in it.mentions:
                m.id = p + m.id
        elif isinstance(it, Block):
            if it.head:
                it.head.id = p + it.head.id
            prefix_ids(it.items, p)
        elif isinstance(it, Use):
            it.inst = p + it.inst
        elif isinstance(it, SetLine):
            it.first, it.last = p + it.first, p + it.last
        elif isinstance(it, MessageLine):
            it.src, it.dst = p + it.src, p + it.dst
        elif isinstance(it, NoteLine):
            it.lane = p + it.lane


def in_template(e: SketchError, u: Use) -> SketchError:
    if "(in template " in e.message:
        return e
    return SketchError(e.line, f"{e.message} (in template {u.name}, used as {u.inst} on line {u.line})")
