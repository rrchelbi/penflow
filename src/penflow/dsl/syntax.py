"""What each line of a fence says: keywords, and the syntax tree a line parses into.

Lines are parsed one at a time and independently; ids are resolved later, by the builder.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, TypeAlias

from .errors import SketchError
from .lexer import NUM, SENTINEL, AttrMap, Scanner, SourceLine, number, split_unquoted, text

GENERIC: Final = ("row", "col", "split", "overlay", "pad", "region", "grid", "stack", "hub", "flow", "flowchart",
                  "compare", "panel")
"""Blocks whose children are ordinary node, edge and block lines."""
SPECIAL: Final = ("steps", "table", "overlap", "timeline", "sequence_diagram")
"""Blocks whose children have a syntax of their own."""
BLOCKS: Final = GENERIC + SPECIAL
LEAVES: Final = ("label", "spacer")
INNER: Final[dict[str, str]] = {
    "participant": "sequence_diagram", "note": "sequence_diagram", "set": "overlap"}
DIRECTIONS: Final = ("lr", "td", "tb")
MERMAID: Final[dict[str, str]] = {
    "subgraph": "write 'region <title>' and indent its contents under it",
    "end": "blocks end where the indentation does; remove 'end'",
    "graph": "write 'row' or 'col' and indent the nodes under it",
    "classDef": "define colors in front matter: meanings: {name: cyan}",
    "class": "put the tone on the node: id:::name",
    "linkStyle": "put the tone on the edge line: a --> b :::name",
    "style": "put the tone on the node: id:::name",
}
ARROWS: Final[tuple[tuple[str, bool, bool], ...]] = (  # token, has head, dashed (longest first)
    ("-.->", True, True), ("-->", True, False), ("-.-", False, True), ("---", False, False))
PORTS: Final[dict[str, tuple[float, float]]] = {
    "top": (0.5, 0), "bottom": (0.5, 1), "left": (0, 0.5), "right": (1, 0.5), "center": (0.5, 0.5)}
Shape: TypeAlias = Literal["box", "circle", "cell"]


@dataclass
class Mention:
    id: str
    line: int
    shape: Shape | None = None
    body: str | None = None  # raw text inside the shape
    tone: str | None = None
    attrs: AttrMap = field(default_factory=dict[str, "str | bool"])
    port: tuple[float, float] | None = None
    declares: bool = False


@dataclass
class NodeLine:
    mention: Mention

    @property
    def line(self) -> int:
        return self.mention.line


@dataclass
class EdgeLine:
    line: int
    ends: list[Mention]
    hops: list[tuple[bool, bool, str | None]]  # (head, dashed, label) between ends[i] and ends[i+1]
    tone: str | None
    attrs: AttrMap


@dataclass
class LeafLine:
    kw: str
    line: int
    text: str
    tone: str | None
    attrs: AttrMap


@dataclass
class GridRow:
    line: int
    cells: list[Mention | None]


@dataclass
class Block:
    kw: str
    line: int
    title: str | None
    tone: str | None
    attrs: AttrMap
    items: list[Item]
    head: Mention | None = None  # hub's center


@dataclass
class Use:
    line: int
    name: str
    inst: str
    args: AttrMap
    items: list[Item] = field(default_factory=list["Item"])  # the template's lines, filled in and prefixed


@dataclass
class ItemsLine:
    """overlap's first line: the items, separated by spaces."""

    line: int
    mentions: list[Mention]


@dataclass
class SetLine:
    """`set first..last: label` under overlap."""

    line: int
    first: str
    last: str
    label: str
    tone: str | None
    attrs: AttrMap


@dataclass
class EventLine:
    """`value: text` under timeline."""

    line: int
    value: float
    text: str
    tone: str | None
    attrs: AttrMap


@dataclass
class TableRow:
    line: int
    cells: list[tuple[str, str | None] | None]
    sep: bool  # a |---| line


@dataclass
class Participant:
    mention: Mention

    @property
    def line(self) -> int:
        return self.mention.line


@dataclass
class MessageLine:
    line: int
    src: str
    dst: str
    cross: bool
    text: str
    tone: str | None
    attrs: AttrMap


@dataclass
class NoteLine:
    """`note lane: text` under sequence_diagram."""

    line: int
    lane: str
    text: str
    tone: str | None
    attrs: AttrMap


@dataclass
class GapLine:
    line: int
    h: float | None


Item: TypeAlias = (
    Block
    | NodeLine
    | EdgeLine
    | LeafLine
    | GridRow
    | Use
    | ItemsLine
    | SetLine
    | EventLine
    | TableRow
    | Participant
    | MessageLine
    | NoteLine
    | GapLine
)


def parse_mention(sc: Scanner) -> Mention:
    m = Mention(sc.ident(), sc.line)
    if sc.eat("(("):
        m.shape, m.body = "circle", sc.until(("))",))
        if not sc.eat("))"):
            sc.fail(f"(( after {m.id!r} needs a closing ))")
    elif sc.eat("["):
        m.shape, m.body = "box", sc.until(("]",))
        if not sc.eat("]"):
            sc.fail(f"[ after {m.id!r} needs a closing ]")
    elif sc.eat("("):
        m.shape, m.body = "cell", sc.until((")",))
        if not sc.eat(")"):
            sc.fail(f"( after {m.id!r} needs a closing )")
    if sc.eat("."):
        pname = sc.word() or ""
        if pname == "at":
            if not sc.eat("("):
                sc.fail("write the port as .at(fx, fy)")
            nums = [p.strip() for p in sc.until((")",)).split(",")]
            if not sc.eat(")") or len(nums) != 2 or not all(NUM.match(n) for n in nums):
                sc.fail("write the port as .at(fx, fy), two numbers from 0 to 1")
            m.port = (float(nums[0]), float(nums[1]))
        elif pname in PORTS:
            m.port = PORTS[pname]
        else:
            sc.fail(f"unknown port .{pname}; ports are {', '.join('.' + p for p in PORTS)} and .at(fx, fy)")
    if sc.eat(":::"):
        m.tone = sc.ident("tone")
    if sc.peek("{"):
        start = sc.i
        try:
            m.attrs = sc.attrs()
        except SketchError:
            if m.shape is None and m.tone is None and not sc.s[start:].startswith("{{"):
                inner = sc.s[start + 1:].split("}", 1)[0].strip()
                sc.fail(f"Mermaid's {{decision}} shape isn't drawn by Penflow; write {m.id}[{inner}] "
                        f"(a box), or {m.id}(({inner})) for a circle")
            raise
    return m


def _arrow(sc: Scanner) -> tuple[bool, bool, str | None] | None:
    for tok, head, dashed in ARROWS:
        if sc.eat(tok):
            label = None
            if sc.eat("|"):
                label = text(sc.until(("|",)), sc.line)
                if not sc.eat("|"):
                    sc.fail("an edge label is written -->|label| with a closing |")
            return head, dashed, label
    if sc.peek("->>") or sc.peek("-x") or sc.peek("--x"):
        sc.fail("->> and -x are sequence_diagram arrows; in a layout use --> (or -.-> dashed)")
    return None


def _keyword(sc: Scanner, src: SourceLine) -> tuple[str, bool]:
    """The line's first word, and whether it's in keyword position (followed by a space, {, : or nothing)."""
    if sc.peek(SENTINEL):
        sc.fail("a $param can't stand in for an id or a keyword; templates change text, tones and attribute "
                "values only")
    first = sc.word()
    if first is None:
        sc.fail(f"a line starts with a keyword or an id, not {src.text[:1]!r}")
    after = sc.rest()
    is_kw = (after == "" or after[0] in " {:") and not after.startswith(":::")
    if is_kw and first in MERMAID:
        sc.fail(f"{first!r} is Mermaid syntax; {MERMAID[first]}")
    return first, is_kw


def _no_children(src: SourceLine, what: str) -> None:
    if src.children:
        raise SketchError(src.children[0].no, f"{what} can't have lines indented under it")


def parse_line(src: SourceLine) -> Item:
    sc = Scanner(src.text, src.no)
    if sc.peek("|"):
        _no_children(src, "a | row")
        return _grid_row(src)
    start = sc.i
    first, is_kw = _keyword(sc, src)
    if is_kw and first == "template":
        sc.fail("template goes at the top level of a fence, not inside a block")
    if is_kw and first == "use":
        _no_children(src, "use")
        return _use(sc)
    if is_kw and first in INNER:
        sc.fail(f"{first} lines go directly under {INNER[first]}")
    if is_kw and first in BLOCKS:
        head = None
        if first == "hub":
            sc.ws()
            if sc.done():
                sc.fail("hub needs its center: hub leader")
            head = parse_mention(sc)
            title = ""
            tone, attrs = sc.tail()
        else:
            title, tone, attrs = sc.text_tail()
        items = _special(first, src.children) if first in SPECIAL else [parse_line(c) for c in src.children]
        return Block(first, src.no, title or None, tone, attrs, items, head)
    if is_kw and first in LEAVES:
        _no_children(src, first)
        body, tone, attrs = sc.text_tail()
        return LeafLine(first, src.no, body, tone, attrs)
    if src.children:
        raise SketchError(src.children[0].no, "only blocks can have lines indented under them, such as "
                                              f"{', '.join(GENERIC[:6])} or {', '.join(SPECIAL)}")
    sc.i = start
    m = parse_mention(sc)
    sc.ws()
    hop = _arrow(sc)
    if hop is None:
        tone, attrs = sc.tail()
        if tone and m.tone:
            sc.fail(f"{m.id!r} has two tones")
        m.tone = m.tone or tone
        clash = set(m.attrs) & set(attrs)
        if clash:
            sc.fail(f"{', '.join(sorted(clash))} given twice")
        m.attrs = {**m.attrs, **attrs}
        m.declares = True
        return NodeLine(m)
    ends, hops = [m], [hop]
    while True:
        sc.ws()
        ends.append(parse_mention(sc))
        sc.ws()
        nxt = _arrow(sc)
        if nxt is None:
            break
        hops.append(nxt)
    tone, attrs = sc.tail()
    for e in ends:
        e.declares = e.shape is not None or e.tone is not None or bool(e.attrs)
    return EdgeLine(src.no, ends, hops, tone, attrs)


def _use(sc: Scanner) -> Use:
    """use name as instance {param: value, ...}; the cursor is just past `use`."""
    sc.ws()
    name = sc.ident("template name")
    sc.ws()
    if sc.word() != "as":
        sc.fail(f"write use {name} as <instance name> {{param: value, ...}}")
    sc.ws()
    inst = sc.ident("instance name")
    sc.ws()
    args = sc.attrs() if sc.peek("{") else {}
    sc.ws()
    if not sc.done():
        sc.fail(f"unexpected {sc.rest()!r}; arguments go in one {{...}} block")
    return Use(sc.line, name, inst, args)


def _special(kw: str, children: Sequence[SourceLine]) -> list[Item]:
    """Child lines of the blocks that have a syntax of their own."""
    out: list[Item] = []
    for i, src in enumerate(children):
        _no_children(src, f"a line inside {kw}")
        sc = Scanner(src.text, src.no)
        if kw == "steps":
            body, tone, attrs = sc.text_tail()
            if not body:
                sc.fail("each line under steps is the text of one step")
            out.append(LeafLine("step", src.no, body, tone, attrs))
        elif kw == "table":
            out.append(_table_row(src))
        elif kw == "overlap":
            out.append(_items_line(sc) if i == 0 else _set_line(sc))
        elif kw == "timeline":
            out.append(_event(sc))
        else:
            out.append(_seq_line(sc))
    return out


def _table_row(src: SourceLine) -> TableRow:
    raw = src.text.strip()
    if not (raw.startswith("|") and raw.endswith("|")) or len(raw) < 2:
        raise SketchError(src.no, "a table row starts and ends with |: | a | b |")
    parts = split_unquoted(raw[1:-1], "|")
    if all(re.fullmatch(r"\s*:?-+:?\s*", p) for p in parts):
        return TableRow(src.no, [], True)
    cells: list[tuple[str, str | None] | None] = []
    for p in parts:
        if not p.strip():
            cells.append(None)
            continue
        body, tone, attrs = Scanner(p, src.no).text_tail()
        if attrs:
            raise SketchError(src.no, "table cells take a :::tone but no {attributes}")
        cells.append((body, tone))
    return TableRow(src.no, cells, False)


def _items_line(sc: Scanner) -> ItemsLine:
    if sc.peek("set ") or sc.s == "set":
        sc.fail("overlap starts with the line of items (n1 n2 n3), then the set lines")
    out: list[Mention] = []
    while True:
        sc.ws()
        if sc.done():
            return ItemsLine(sc.line, out)
        out.append(parse_mention(sc))
        if not sc.done() and not sc.peek(" "):
            sc.fail(f"items are separated by spaces; unexpected {sc.rest()!r}")


def _set_line(sc: Scanner) -> SetLine:
    if sc.word() != "set":
        sc.fail("after the line of items, overlap holds set lines: set n1..n3: label")
    sc.ws()
    first = sc.ident()
    if not sc.eat(".."):
        sc.fail("write the range as first..last: set n1..n3: label")
    last = sc.ident()
    sc.ws()
    if not sc.eat(":"):
        sc.fail("a set needs a label after a colon: set n1..n3: quorum A")
    body, tone, attrs = sc.text_tail()
    return SetLine(sc.line, first, last, body, tone, attrs)


def _event(sc: Scanner) -> EventLine:
    value = sc.until((":",)).strip()
    if not sc.eat(":") or not NUM.match(value):
        sc.fail("a timeline event is value: text, such as 27: alert fires")
    body, tone, attrs = sc.text_tail()
    return EventLine(sc.line, number(value), body, tone, attrs)


SEQ_ARROWS: Final[tuple[tuple[str, bool, bool], ...]] = (  # token, cross, dashed
    ("-->>", False, True), ("--x", True, True), ("->>", False, False), ("-x", True, False))


def _seq_line(sc: Scanner) -> Item:
    start = sc.i
    first = sc.word()
    if first is None:
        sc.fail(f"expected participant, note, gap or a message (a ->> b: text), not {sc.s[:1]!r}")
    after = sc.rest()
    is_kw = after == "" or after[0] == " "
    if is_kw and first == "participant":
        sc.ws()
        m = parse_mention(sc)
        tone, attrs = sc.tail()
        m.tone = m.tone or tone
        m.attrs = {**m.attrs, **attrs}
        return Participant(m)
    if is_kw and first == "gap":
        sc.ws()
        h = sc.rest().strip()
        if h and not NUM.match(h):
            sc.fail("write gap, or gap 30 for a taller one")
        return GapLine(sc.line, number(h) if h else None)
    if first == "Note":
        sc.fail("write note <lane>: text (lowercase; the note always sits beside its lane)")
    if is_kw and first == "note":
        sc.ws()
        lane = sc.ident("lane")
        if lane in ("right", "left", "over"):
            sc.fail("write note <lane>: text; the note always sits beside its lane")
        sc.ws()
        if not sc.eat(":"):
            sc.fail("write note <lane>: text")
        body, tone, attrs = sc.text_tail()
        return NoteLine(sc.line, lane, body, tone, attrs)
    sc.i = start
    src = sc.ident("lane")
    sc.ws()
    for tok, cross, dashed in SEQ_ARROWS:
        if sc.eat(tok):
            if dashed:
                sc.fail(f"{tok} (dashed) isn't supported in sequence diagrams yet; use "
                        f"{'-x' if cross else '->>'}")
            sc.ws()
            dst = sc.ident("lane")
            sc.ws()
            if sc.eat(":"):
                body, tone, attrs = sc.text_tail()
            else:
                body = ""
                tone, attrs = sc.tail()
            return MessageLine(sc.line, src, dst, cross, body, tone, attrs)
    sc.fail("a message is a ->> b: text (or a -x b: text for one that fails)")


def _grid_row(src: SourceLine) -> GridRow:
    raw = src.text.strip()
    if not raw.endswith("|") or len(raw) < 2:
        raise SketchError(src.no, "a grid row starts and ends with |: | a | b |")
    cells: list[Mention | None] = []
    for part in split_unquoted(raw[1:-1], "|"):
        body = part.strip()
        if not body:
            cells.append(None)
            continue
        if set(body) <= set("-: "):
            raise SketchError(src.no, "|---| header rows belong to table; grid has no header")
        sc = Scanner(body, src.no)
        m = parse_mention(sc)
        tone, attrs = sc.tail()
        m.tone = m.tone or tone
        m.attrs = {**m.attrs, **attrs}
        m.declares = True
        cells.append(m)
    return GridRow(src.no, cells)
