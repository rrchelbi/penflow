"""Common explanation shapes, built only from nodes.

Each function returns an ordinary node, so the results nest inside each other
and inside Row / Col / Region / Split like any other part:

    Split(flow("source", "build", "ship"), stack("app", "runtime", "kernel"))
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import TypeAlias

from .nodes import (
    CIRCLED,
    Act,
    Arrow,
    At,
    Box,
    Bracket,
    BracketSide,
    Cell,
    Child,
    Circle,
    Col,
    Gap,
    Grid,
    Label,
    Lanes,
    LaneSpec,
    Msg,
    Node,
    Pad,
    Row,
    Spacer,
    Split,
    Step,
    ToneRef,
    Track,
    text_width,
)

BoxSpec: TypeAlias = "Node | str | tuple[str, str]"
"""A step or layer: "title", ("title", "second line"), or any node."""
EventSpec: TypeAlias = "At | tuple[float, str] | tuple[float, str, ToneRef | None]"
"""A timeline event: (value, text), (value, text, tone), or an At for full control."""
PanelSpec: TypeAlias = "tuple[str, Node] | tuple[str, Node, ToneRef | None]"
"""A compare() panel: (title, body) or (title, body, title tone)."""
CellSpec: TypeAlias = "Node | str | tuple[str, ToneRef | None] | None"
"""A table cell: text, (text, tone), any node, or None for an empty slot."""
ItemSpec: TypeAlias = "str | tuple[str, ToneRef | None]"
"""An overlap() item: a name, or (name, tone)."""
SetSpec: TypeAlias = "tuple[int, int, str, ToneRef | None] | tuple[int, int, str, ToneRef | None, BracketSide]"
"""An overlap() set: (first, last, label, tone) or (..., side); indexes are 0-based and inclusive."""
RowSpec: TypeAlias = "Msg | Act | Gap"


def _box(s: BoxSpec) -> Node:
    if isinstance(s, Node):
        return s
    if isinstance(s, tuple):
        return Box(s[0], s[1])
    return Box(s)


def flow(*steps: BoxSpec, labels: Sequence[str | None] = (), gap: float | None = None, vertical: bool = False,
         tone: ToneRef | None = None) -> Row | Col:
    """Boxes joined by arrows: a pipeline, a chain of cause and effect.
    `labels[i]` goes on the arrow after step i."""
    nodes = [_box(s) for s in steps]
    if gap is None:
        widest = max([text_width(lab or "", 13, scale=1.12) for lab in labels] or [0.0])
        gap = 44 if vertical else max(48, widest + 24)
    cont: Row | Col = Col(*nodes, gap=gap) if vertical else Row(*nodes, gap=gap)
    for i, (a, b) in enumerate(itertools.pairwise(nodes)):
        cont.link(Arrow(a, b, labels[i] if i < len(labels) else None, tone=tone,
                        label_side="right" if vertical else "auto"))
    return cont


def stack(*layers: BoxSpec, gap: float = 8, width: float | None = None) -> Col:
    """Layers top to bottom, all the same width: what sits on what."""
    col = Col(*[_box(layer) for layer in layers], gap=gap, stretch=True)
    return col.fixed(w=width) if width else col


def timeline(*events: EventSpec, start: float | None = None, end: float | None = None, length: float = 480,
             alternate: bool = True) -> Track:
    """Events on an axis. Labels alternate above and below so neighbors don't collide."""
    ats: list[At] = []
    for i, e in enumerate(events):
        if isinstance(e, At):
            ats.append(e)
            continue
        tone = e[2] if len(e) == 3 else None
        ats.append(At(e[0], e[1], side="below" if alternate and i % 2 else "above", tone=tone))
    return Track(*ats, start=start, end=end, length=length)


def sequence(lanes: Sequence[LaneSpec], *rows: RowSpec, col: float | None = None) -> Lanes:
    """Who sends what to whom, in order. Lanes are names or (name, tone)."""
    return Lanes(lanes, rows, col=col)


def compare(*panels: PanelSpec, gap: float = 40, divider: bool = True) -> Split:
    """Panels side by side, each with a title: before/after, case 1/case 2."""
    cols: list[Child] = []
    for p in panels:
        tone = (p[2] if len(p) == 3 else None) or "accent"
        cols.append(Col(Label(p[0], size=16, bold=True, tone=tone), p[1], gap=14))
    return Split(*cols, gap=gap, divider=divider)


def table(rows: Sequence[Sequence[CellSpec]], header: Sequence[str] | None = None, gap: float = 6,
          size: float = 14) -> Grid:
    """A grid of cells."""
    def cell(c: CellSpec) -> Node:
        if c is None:
            return Spacer()
        if isinstance(c, Node):
            return c
        if isinstance(c, tuple):
            return Cell(c[0], size=size).tone(c[1])
        return Cell(c, size=size)

    grid: list[list[Child | None]] = [[cell(c) for c in r] for r in rows]
    if header:
        grid.insert(0, [Label(h, size=13, tone="soft", bold=True) for h in header])
    return Grid(grid, gap=gap)


def overlap(items: Sequence[ItemSpec], *sets: SetSpec, gap: float = 44) -> Pad:
    """Things in a row, with brackets marking which belong to which set: quorums,
    shards, replicas."""
    circles = [Circle(i[0]).tone(i[1]) if isinstance(i, tuple) else Circle(i) for i in items]
    row = Row(*circles, gap=gap)
    sides: set[BracketSide] = set()
    for st in sets:
        side: BracketSide = st[4] if len(st) == 5 else "top"
        sides.add(side)
        row.link(Bracket(circles[st[0]:st[1] + 1], st[2], side=side, tone=st[3]))
    return Pad(row, top=44 if "top" in sides else 0, bottom=44 if "bottom" in sides else 0)


def steps(*texts: str, start: int = 1, gap: float = 8) -> Col:
    """A numbered list: ① first ② then ③ finally."""
    if start < 1 or start + len(texts) - 1 > len(CIRCLED):
        raise ValueError(f"steps are numbered 1..{len(CIRCLED)}")
    return Col(*[Step(start + i, t).align("start") for i, t in enumerate(texts)], gap=gap, align="start")


def hub(center: BoxSpec, spokes: Sequence[BoxSpec], radius: float | None = None,
        tone: ToneRef | None = None) -> Col:
    """One thing in the middle and what it talks to around it (a fan-out).
    Arrows go from the center out."""
    c = _box(center)
    outer = [_box(s) for s in spokes]
    half = (len(outer) + 1) // 2
    top, bottom = outer[:half], outer[half:]
    body = Col(Row(*top, gap=28), c, Row(*bottom, gap=28) if bottom else Spacer(), gap=radius or 60)
    for o in outer:
        body.link(Arrow(c, o, tone=tone))
    return body
