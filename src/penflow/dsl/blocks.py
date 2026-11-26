"""One builder per block keyword, from a parsed block to a node."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from ..ideas import CellSpec, PanelSpec, compare, hub, stack, table
from ..nodes import (
    CIRCLED,
    Act,
    Align,
    At,
    Bracket,
    BracketSide,
    Col,
    Gap,
    Grid,
    Justify,
    LaneRow,
    Lanes,
    LaneSpec,
    MarkKind,
    Msg,
    Node,
    Overlay,
    Pad,
    Region,
    Row,
    Spacer,
    Split,
    Step,
    TickMark,
    Track,
    TrackSide,
    text_width,
)
from .attrs import ALIGNS, BRACKET_SIDES, JUSTIFIES, MARK_KINDS, TICK_MARKS, TRACK_SIDES, Attrs
from .errors import SketchError
from .layered import FlowRoute, layers
from .lexer import text
from .syntax import (
    DIRECTIONS,
    Block,
    EventLine,
    GapLine,
    GridRow,
    ItemsLine,
    LeafLine,
    MessageLine,
    NoteLine,
    Participant,
    SetLine,
    TableRow,
)

if TYPE_CHECKING:
    from .builder import NodeBuilder

def plain(b: Block, a: Attrs, title: bool = False, tone: bool = False) -> None:
    if b.title and not title:
        a.fail(f"{b.kw} has no title; put a label line inside it, or use region <title>")
    if b.tone and not tone:
        a.fail(f"{b.kw} doesn't take a tone; put it on the lines inside")


def build_layout(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    kids, edges = builder.items(b.items)
    n: Node
    if b.kw in ("row", "col", "split"):
        plain(b, a)
        al: Align | None = a.choice("align", ALIGNS)
        js: Justify | None = a.choice("justify", JUSTIFIES)
        st = bool(a.flag("stretch"))
        if b.kw == "row":
            n = Row(*kids, gap=a.num("gap") or 24, align=al or "center", justify=js or "center", stretch=st)
        elif b.kw == "col":
            n = Col(*kids, gap=a.num("gap") or 20, align=al or "center", justify=js or "center", stretch=st)
        else:
            div = a.flag("divider")
            n = Split(*kids, gap=a.num("gap") or 40, divider=True if div is None else div,
                      align=al or "start", justify=js or "center", stretch=st)
    elif b.kw == "overlay":
        plain(b, a)
        if not kids:
            a.fail("overlay needs at least one line indented under it")
        n = Overlay(*kids)
    elif b.kw == "pad":
        if b.title:
            a.fail("pad has no title; write pad {top: 10} or pad {all: 10}")
        plain(b, a)
        if len(kids) != 1:
            a.fail(f"pad holds exactly one node or block, not {len(kids)}; wrap them in a col")
        p = a.num("all") or 0
        n = Pad(kids[0], p, top=a.num("top"), right=a.num("right"), bottom=a.num("bottom"),
                left=a.num("left"))
    elif b.kw == "stack":
        plain(b, a)
        if not kids:
            a.fail("stack needs at least one layer indented under it")
        n = stack(*kids, gap=a.num("gap") or 8, width=a.num("width"))
    else:  # region
        plain(b, a, title=True)
        if not kids:
            a.fail("region needs at least one line indented under it")
        child = kids[0] if len(kids) == 1 else Col(*kids)
        n = Region(b.title, child, pad=a.num("pad") or 16, fill=a.text("fill"))
    builder.later(n, edges, "auto")
    return n


def build_grid(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    rows: list[list[Node | None]] = []
    for it in b.items:
        if not isinstance(it, GridRow):
            raise SketchError(getattr(it, "line", b.line), "grid holds | rows only: | a | b[x] | |")
        rows.append([builder.leaf(c) if c else None for c in it.cells])
    if not rows:
        a.fail("grid needs at least one | row indented under it")
    st = a.flag("stretch")
    return Grid(rows, gap=a.num("gap") or 16, col_gap=a.num("col_gap"), row_gap=a.num("row_gap"),
                stretch=True if st is None else st)


def build_hub(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    assert b.head is not None
    center = builder.leaf(b.head)
    kids, edges = builder.items(b.items)
    if not kids:
        a.fail("hub needs its spokes indented under it, one per line")
    t = a.text("tone")
    if t and b.tone:
        a.fail("the tone is given twice (:::name and tone:)")
    n = hub(center, kids, radius=a.num("radius"), tone=b.tone or t)
    builder.later(n, edges, "auto")
    return n


def build_flow(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    if b.tone:
        a.fail("flow doesn't take a tone; put it on the edge lines")
    direction = b.title or "lr"
    if direction not in DIRECTIONS:
        a.fail(f"flow goes lr (left to right) or td (top down), not {direction!r}")
    vertical = direction != "lr"
    kids, edges = builder.items(b.items)
    names: list[str] = []
    for k in kids:
        name = builder.ids.get(id(k))
        if name is None:
            a.fail("flow holds nodes and edge lines; put blocks around the flow, or use row or col")
        names.append(name)
    hops = [(x.id, y.id, lab) for e in edges
            for (_, _, lab), (x, y) in zip(e.hops, itertools.pairwise(e.ends), strict=True)]
    gap = a.num("gap")
    if gap is None:
        widest = max([text_width(lab or "", 13, scale=1.12) for _, _, lab in hops] or [0.0])
        gap = 44 if vertical else max(48, widest + 24)
    across = a.num("node_gap") or 24
    ranked = layers(names, [(x, y) for x, y, _ in hops])
    by_name = dict(zip(names, kids, strict=True))
    n: Node
    holes: dict[tuple[str, str], list[Node]] = {}
    if all(len(r) == 1 for r in ranked.ranks):  # a chain: the same tree flow() builds
        line = [by_name[r[0]] for r in ranked.ranks if isinstance(r[0], str)]
        n = Col(*line, gap=gap) if vertical else Row(*line, gap=gap)
    else:
        groups: list[Node] = []
        for r in ranked.ranks:
            slots: list[Node] = []
            for x in r:
                if isinstance(x, str):
                    slots.append(by_name[x])
                else:
                    hole = Spacer(*((12, 0) if vertical else (0, 12)))
                    holes.setdefault(x, []).append(hole)
                    slots.append(hole)
            groups.append(slots[0] if len(slots) == 1 else
                          Row(*slots, gap=across) if vertical else Col(*slots, gap=across))
        n = Col(*groups, gap=gap) if vertical else Row(*groups, gap=gap)
    for key, hs in holes.items():
        builder.routes[key] = FlowRoute("through", n, vertical, hs)
    back = sorted(ranked.back, key=lambda e: (names.index(e[0]), names.index(e[1])))
    for lane, key in enumerate(back):
        builder.routes[key] = FlowRoute("around", n, vertical, [], lane)
    builder.later(n, edges, "right" if vertical else "auto")
    if back:  # room for the edges that go around, and their labels
        labelled = any(lab for x, y, lab in hops if (x, y) in ranked.back)
        room = FlowRoute.offset(len(back) - 1) + (24 if labelled else 8)
        if vertical:
            widest = max([text_width(lab or "", 13, scale=1.12) for x, y, lab in hops if (x, y) in ranked.back]
                         or [0.0])
            return Pad(n, right=room + (widest if labelled else 0))
        return Pad(n, bottom=room)
    return n


def build_compare(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    panels: list[PanelSpec] = []
    for it in b.items:
        if not isinstance(it, Block) or it.kw != "panel":
            raise SketchError(getattr(it, "line", b.line), "compare holds panel blocks only: "
                                                           "panel <title> :::tone, with the body under it")
        pa = Attrs(it.attrs, it.line, "panel")
        pa.done()
        if not it.title:
            pa.fail("a panel needs a title: panel case 1: the commander lies")
        kids, edges = builder.items(it.items)
        if not kids:
            pa.fail("a panel needs its body indented under it")
        body = kids[0] if len(kids) == 1 else Col(*kids)
        builder.later(body, edges, "auto")
        panels.append((it.title, body, it.tone))
    if not panels:
        a.fail("compare needs panel blocks indented under it")
    div = a.flag("divider")
    return compare(*panels, gap=a.num("gap") or 40, divider=True if div is None else div)


def build_steps(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    start = a.num("start") or 1
    if start != int(start) or start < 1:
        a.fail("start is a whole number from 1")
    lines = [it for it in b.items if isinstance(it, LeafLine)]
    if not lines:
        a.fail("steps needs one line of text per step indented under it")
    if int(start) + len(lines) - 1 > len(CIRCLED):
        a.fail(f"steps are numbered 1..{len(CIRCLED)}")
    out: list[Node] = []
    for i, it in enumerate(lines):
        sa = Attrs(it.attrs, it.line, "a step")
        st = Step(int(start) + i, it.text, sa.num("size") or 14, it.tone).align("start")
        sa.done()
        st.origin = f"step {i + 1} (line {it.line})"
        out.append(st)
    return Col(*out, gap=a.num("gap") or 8, align="start")


def build_table(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    rows = [it for it in b.items if isinstance(it, TableRow)]
    header: list[str] | None = None
    if len(rows) > 1 and rows[1].sep:
        if any(c and c[1] for c in rows[0].cells):
            raise SketchError(rows[0].line, "header cells don't take a tone")
        header = [c[0] if c else "" for c in rows[0].cells]
        rows = rows[2:]
    for r in rows:
        if r.sep:
            raise SketchError(r.line, "a |---| line only goes right under the header row")
    if not rows:
        a.fail("table needs at least one row: | a | b |")
    cells: list[list[CellSpec]] = [[None if c is None else (c[0], c[1]) for c in r.cells] for r in rows]
    return table(cells, header=header, gap=a.num("gap") or 6, size=a.num("size") or 14)


def build_overlap(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    if not b.items or not isinstance(b.items[0], ItemsLine) or not b.items[0].mentions:
        a.fail("overlap starts with a line of items: n1 n2 n3")
    first = b.items[0]
    assert isinstance(first, ItemsLine)
    circles = [builder.leaf(m, "circle") for m in first.mentions]
    order = [m.id for m in first.mentions]
    row = Row(*circles, gap=a.num("gap") or 44)
    sides: set[BracketSide] = set()
    for it in b.items[1:]:
        assert isinstance(it, SetLine)
        sa = Attrs(it.attrs, it.line, "a set")
        chosen: BracketSide | None = sa.choice("side", BRACKET_SIDES)
        side: BracketSide = chosen or "top"
        sa.done()
        for name in (it.first, it.last):
            if name not in order:
                sa.fail(f"{name!r} isn't one of the items: {', '.join(order)}")
        i, j = order.index(it.first), order.index(it.last)
        if i > j:
            sa.fail(f"write the range in order: set {it.last}..{it.first}")
        sides.add(side)
        br = Bracket(circles[i:j + 1], it.label or None, side=side, tone=it.tone)
        br.origin = f"set {it.first}..{it.last} (line {it.line})"
        row.link(br)
    return Pad(row, top=44 if "top" in sides else 0, bottom=44 if "bottom" in sides else 0)


def build_timeline(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    events = [it for it in b.items if isinstance(it, EventLine)]
    if not events:
        a.fail("timeline needs events indented under it: 27: alert fires")
    alt = a.flag("alternate")
    ats: list[At] = []
    for i, e in enumerate(events):
        ea = Attrs(e.attrs, e.line, "an event")
        side: TrackSide | None = ea.choice("side", TRACK_SIDES)
        mark: TickMark | None = ea.choice("mark", TICK_MARKS)
        level = ea.num("level") or 0
        ea.done()
        auto: TrackSide = "below" if (alt is not False) and i % 2 else "above"
        ats.append(At(e.value, e.text, side=side or auto, level=int(level), tone=e.tone, mark=mark))
    return Track(*ats, start=a.num("start"), end=a.num("end"), length=a.num("length") or 480)


def build_sequence(builder: NodeBuilder, b: Block, a: Attrs) -> Node:
    plain(b, a)
    labels: dict[str, str] = {}
    tones: dict[str, str | None] = {}
    lines: dict[str, int] = {}

    def lane(name: str, line: int) -> str:
        if name not in labels:
            labels[name], tones[name], lines[name] = name.replace("_", " "), None, line
        return labels[name]

    for it in b.items:
        if isinstance(it, Participant):
            m = it.mention
            pa = Attrs(m.attrs, m.line, f"participant {m.id!r}")
            pa.done()
            if m.shape not in (None, "box"):
                pa.fail("a participant is drawn as a box: participant id[label]")
            labels[m.id] = text(m.body, m.line) if m.body is not None else m.id.replace("_", " ")
            tones[m.id], lines[m.id] = m.tone, m.line
    rows: list[LaneRow] = []
    for it in b.items:
        if isinstance(it, MessageLine):
            if it.src == it.dst:
                raise SketchError(it.line, f"a message needs two different lanes; for {it.src}'s own step "
                                           f"write note {it.src}: {it.text or 'text'}")
            ma = Attrs(it.attrs, it.line, "a message")
            mark: MarkKind | None = ma.choice("mark", MARK_KINDS)
            if mark and it.cross:
                ma.fail("-x already ends in a cross; drop mark:")
            note = ma.text("note")
            ma.done()
            rows.append(Msg(lane(it.src, it.line), lane(it.dst, it.line), it.text, it.tone,
                            "cross" if it.cross else mark, note))
        elif isinstance(it, NoteLine):
            aa = Attrs(it.attrs, it.line, "a note")
            bar = aa.num("bar") or 0
            if bar != int(bar) or bar < 0:
                aa.fail("bar is a whole number of rows")
            aa.done()
            rows.append(Act(lane(it.lane, it.line), it.text, it.tone, int(bar)))
        elif isinstance(it, GapLine):
            rows.append(Gap(it.h or 20))
    if not labels:
        a.fail("sequence_diagram needs participants or messages indented under it")
    seen: dict[str, str] = {}
    for name, label in labels.items():
        if label in seen:
            raise SketchError(lines[name], f"lanes {seen[label]!r} and {name!r} have the same label "
                                           f"{label!r}; give one a different label")
        seen[label] = name
    specs: list[LaneSpec] = [(labels[n], tones[n]) for n in labels]
    n = Lanes(specs, rows, col=a.num("col"), head_size=a.num("head_size") or 15)
    for name, label in labels.items():
        builder.register(name, n.heads[label], lines[name])
    return n


BLOCK_BUILDERS: Final[dict[str, Callable[[NodeBuilder, Block, Attrs], Node]]] = {
    "grid": build_grid, "steps": build_steps, "table": build_table, "overlap": build_overlap,
    "timeline": build_timeline, "sequence_diagram": build_sequence, "compare": build_compare,
    "hub": build_hub, "flow": build_flow, "flowchart": build_flow,
}
"""Blocks with a builder of their own; the plain layout blocks use build_layout."""
