"""Layered layout for `flow` blocks: ranks, slots for long edges, fewer crossings.

Edges that skip ranks bend through their slots, and edges that close a cycle go around the flow.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, NamedTuple, TypeAlias

from ..core import Point
from ..nodes import Arrow, LabelSide, Node, Port, Ref

Slot: TypeAlias = "str | tuple[str, str]"
"""A place in a rank: a node id, or the (from, to) edge whose placeholder sits there."""


class Ranked(NamedTuple):
    ranks: list[list[Slot]]
    back: set[tuple[str, str]]
    """Edges left out of the ranking because they close a cycle; they're drawn around the flow."""


def layers(nodes: Sequence[str], edges: Sequence[tuple[str, str]], sweeps: int = 4) -> Ranked:
    """Place a directed graph in ranks, for flows that branch and merge.

    1. Edges that close a cycle (found by a depth-first search in declaration order) are left out.
    2. Each node's rank is its longest path from a node with no incoming edge.
    3. An edge that skips ranks gets a placeholder in every rank it crosses, so it keeps a slot.
    4. Each rank is reordered by the average position of its neighbours, sweeping down and up, and the
       order with the fewest crossings is kept. Ties keep declaration order.
    """
    index = {n: i for i, n in enumerate(nodes)}
    succ: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in index and b in index and a != b and b not in succ[a]:
            succ[a].append(b)

    # 1. drop back edges
    state: dict[str, int] = {}  # 1 on the stack, 2 done
    forward: list[tuple[str, str]] = []

    def visit(n: str) -> None:
        state[n] = 1
        for m in succ[n]:
            if state.get(m) == 1:
                continue  # closes a cycle
            forward.append((n, m))
            if m not in state:
                visit(m)
        state[n] = 2

    for n in nodes:
        if n not in state:
            visit(n)

    # 2. longest-path ranks, in topological order (declaration order breaks ties)
    preds: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in forward:
        preds[b].append(a)
    rank: dict[str, int] = {}
    waiting = {n: len(preds[n]) for n in nodes}
    ready = [n for n in nodes if not waiting[n]]
    while ready:
        n = ready.pop(0)
        rank[n] = max((rank[p] + 1 for p in preds[n]), default=0)
        for a, b in forward:
            if a == n:
                waiting[b] -= 1
                if not waiting[b]:
                    ready.append(b)
                    ready.sort(key=index.__getitem__)

    # 3. placeholders for long edges; `links` joins neighbouring ranks
    out: list[list[int]] = [[] for _ in range(max(rank.values(), default=0) + 1)]
    for n in nodes:
        out[rank[n]].append(index[n])
    ids: list[Slot] = list(nodes)
    links: list[tuple[int, int]] = []
    for a, b in forward:
        prev = index[a]
        for r in range(rank[a] + 1, rank[b]):
            ids.append((a, b))
            out[r].append(len(ids) - 1)
            links.append((prev, len(ids) - 1))
            prev = len(ids) - 1
        links.append((prev, index[b]))

    # 4. barycentre sweeps
    def crossings(order: list[list[int]]) -> int:
        pos = {v: i for layer in order for i, v in enumerate(layer)}
        level = {v: r for r, layer in enumerate(order) for v in layer}
        total = 0
        for r in range(len(order) - 1):
            seg = [(pos[u], pos[v]) for u, v in links if level[u] == r and level[v] == r + 1]
            total += sum(1 for i, (a1, b1) in enumerate(seg) for a2, b2 in seg[i + 1:]
                         if (a1 - a2) * (b1 - b2) < 0)
        return total

    def sweep(order: list[list[int]], down: bool) -> list[list[int]]:
        order = [list(layer) for layer in order]
        rng = range(1, len(order)) if down else range(len(order) - 2, -1, -1)
        for r in rng:
            near = {v: i for i, v in enumerate(order[r - 1 if down else r + 1])}
            pairs = links if down else [(v, u) for u, v in links]
            here = {v: i for i, v in enumerate(order[r])}
            centre: dict[int, float] = {}
            for v in order[r]:
                ns = [near[u] for u, w in pairs if w == v and u in near]
                centre[v] = sum(ns) / len(ns) if ns else float(here[v])
            order[r].sort(key=centre.__getitem__)
        return order

    best, best_n = out, crossings(out)
    cur = out
    for i in range(sweeps * 2):
        cur = sweep(cur, down=i % 2 == 0)
        count = crossings(cur)
        if count < best_n:
            best, best_n = cur, count
    back = {(a, b) for a in nodes for b in succ[a]} - set(forward)
    return Ranked([[ids[v] for v in layer] for layer in best], back)


class BentArrow(Arrow):
    """An arrow whose bend points are worked out once the layout is known."""

    def __init__(self, a: Ref, b: Ref, *, bends: Callable[[], list[Point]], label: str | None, tone: str | None,
                 dashed: bool, label_at: float, label_side: LabelSide, size: float, gap: float) -> None:
        super().__init__(a, b, label, tone=tone, dashed=dashed, label_at=label_at, label_side=label_side,
                         size=size, gap=gap)
        self.bends = bends

    def points(self) -> list[Point]:
        self.via = self.bends()
        return super().points()


def _mid(n: Node) -> Point:
    x, y, w, h = n.rect
    return (x + w / 2, y + h / 2)


@dataclass
class FlowRoute:
    """How a flow edge bends: `through` the placeholders a long edge left in the ranks it skips, or
    `around` the flow (below it for lr, right of it for td) for an edge that goes back."""

    kind: Literal["through", "around"]
    flow: Node
    vertical: bool
    holes: list[Node]
    lane: int = 0  # back edges are spaced apart so they don't run on top of each other

    def side(self, default: LabelSide) -> LabelSide:
        if self.kind == "around":
            return "below" if not self.vertical else "right"
        return default

    @staticmethod
    def offset(lane: int) -> float:
        return 22 + 16 * lane

    def path(self, a: Node, b: Node) -> tuple[tuple[Ref, Ref], Callable[[], list[Point]]]:
        if self.kind == "through":
            return (a, b), lambda: [_mid(h) for h in self.holes]
        off = self.offset(self.lane)
        if self.vertical:
            def right() -> list[Point]:
                fx, _, fw, _ = self.flow.rect
                xr = fx + fw + off
                return [(xr, _mid(a)[1]), (xr, _mid(b)[1])]
            return (Port(a, 1, 0.5), Port(b, 1, 0.5)), right

        def below() -> list[Point]:
            _, fy, _, fh = self.flow.rect
            yl = fy + fh + off
            return [(_mid(a)[0], yl), (_mid(b)[0], yl)]
        return (Port(a, 0.5, 1), Port(b, 0.5, 1)), below
