"""Turns parsed lines into nodes: declarations, leaves, templates and edges.

Every id is declared exactly once. Edge lines are resolved after all nodes exist, so an edge may
name a node declared further down.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence

from ..core import FontName
from ..nodes import (
    Arrow,
    Box,
    Cell,
    Circle,
    Edge,
    Label,
    LabelSide,
    Line,
    Node,
    Port,
    Ref,
    Route,
    Spacer,
    TextAlign,
)
from .attrs import FONT_NAMES, LABEL_SIDES, ROUTES, TEXT_ALIGNS, Attrs, apply_common, apply_fixed
from .blocks import BLOCK_BUILDERS, build_layout
from .errors import SketchError
from .layered import BentArrow, FlowRoute
from .lexer import split_unquoted, text
from .syntax import (
    Block,
    EdgeLine,
    GridRow,
    Item,
    ItemsLine,
    LeafLine,
    Mention,
    MessageLine,
    NodeLine,
    NoteLine,
    Participant,
    Shape,
    Use,
    parse_line,
)
from .templates import BAD_ARG, Template, copy_lines, in_template, prefix_ids, substitute


class NodeBuilder:
    def __init__(self, templates: Mapping[str, Template]) -> None:
        self.templates = templates
        self.nodes: dict[str, Node] = {}
        self.ids: dict[int, str] = {}
        self.declared_at: dict[str, int] = {}
        self.pending: list[tuple[Node, EdgeLine, LabelSide]] = []
        self.routes: dict[tuple[str, str], FlowRoute] = {}  # flow edges that bend

    def expand(self, items: Sequence[Item], stack: tuple[str, ...] = ()) -> None:
        for it in items:
            if isinstance(it, Block):
                self.expand(it.items, stack)
            elif isinstance(it, Use):
                self._expand_use(it, stack)

    def _expand_use(self, u: Use, stack: tuple[str, ...]) -> None:
        t = self.templates.get(u.name)
        if t is None:
            known = ", ".join(self.templates) or "none are defined yet"
            raise SketchError(u.line, f"unknown template {u.name!r}; templates: {known}")
        if u.name in stack:
            raise SketchError(u.line, f"template {u.name} uses itself ({' → '.join((*stack, u.name))})")
        missing = [p for p in t.params if p not in u.args]
        extra = [k for k in u.args if k not in t.params]
        if missing or extra:
            what = f"missing {', '.join(missing)}" if missing else f"no parameter {extra[0]!r}"
            raise SketchError(u.line, f"use {u.name}: {what}; its parameters are {', '.join(t.params) or '(none)'}")
        values: dict[str, str] = {}
        for k, v in u.args.items():
            if isinstance(v, bool):
                raise SketchError(u.line, f"{k} needs a value: {{{k}: ...}}")
            if BAD_ARG.search(v):
                raise SketchError(u.line, f"the value of {k} is plain text; it can't contain brackets, braces, "
                                          "|, quotes, ::: or arrows")
            values[k] = v
        try:
            parsed = [parse_line(s) for s in copy_lines(t.body, lambda x, no: substitute(x, no, values, t))]
            prefix_ids(parsed, u.inst + "_")
            u.items = parsed
            self.expand(parsed, (*stack, u.name))
        except SketchError as e:
            raise in_template(e, u) from None

    def declare_all(self, items: Sequence[Item]) -> None:
        """Ids with no declaring mention are declared by their first bare mention in an edge line."""
        explicit: set[str] = set()
        bare_first: dict[str, Mention] = {}

        def walk(its: Sequence[Item]) -> None:
            for it in its:
                if isinstance(it, Block):
                    if it.head:
                        self._explicit(it.head.id, it.head.line, explicit)
                    if it.kw == "sequence_diagram":
                        self._lanes(it, explicit)
                    walk(it.items)
                elif isinstance(it, NodeLine):
                    self._explicit(it.mention.id, it.mention.line, explicit)
                elif isinstance(it, GridRow):
                    for c in it.cells:
                        if c:
                            self._explicit(c.id, c.line, explicit)
                elif isinstance(it, ItemsLine):
                    for m in it.mentions:
                        self._explicit(m.id, m.line, explicit)
                elif isinstance(it, Use):
                    self._explicit(it.inst, it.line, explicit)
                    walk(it.items)
                elif isinstance(it, EdgeLine):
                    for e in it.ends:
                        if e.declares:
                            self._explicit(e.id, e.line, explicit)
                        else:
                            bare_first.setdefault(e.id, e)

        walk(items)
        for i, m in bare_first.items():
            if i not in explicit:
                m.declares = True

    def _lanes(self, b: Block, seen: set[str]) -> None:
        declared = {it.mention.id for it in b.items if isinstance(it, Participant)}
        for it in b.items:
            if isinstance(it, Participant):
                self._explicit(it.mention.id, it.mention.line, seen)
            lanes = (it.src, it.dst) if isinstance(it, MessageLine) else (it.lane,) if isinstance(it, NoteLine) else ()
            for lane in lanes:
                if lane not in declared:
                    declared.add(lane)
                    self._explicit(lane, it.line, seen)

    def _explicit(self, name: str, line: int, seen: set[str]) -> None:
        if name in seen:
            raise SketchError(line, f"{name!r} is declared twice (first on line {self.declared_at[name]}); "
                                    f"after the first time, refer to it by its id alone")
        seen.add(name)
        self.declared_at[name] = line

    def later(self, owner: Node, edges: Sequence[EdgeLine], side: LabelSide = "auto") -> None:
        """Edge lines are built once every node exists; then they're attached to `owner`."""
        for e in edges:
            self.pending.append((owner, e, side))

    def register(self, name: str, n: Node, line: int) -> None:
        n.origin = f"{name} (line {line})"
        self.nodes[name] = n
        self.ids[id(n)] = name

    def leaf(self, m: Mention, shape: Shape | None = None) -> Node:
        raw = m.body
        shape = shape or m.shape
        label = m.id.replace("_", " ")
        a = Attrs(m.attrs, m.line, f"{shape or 'box'} {m.id!r}")
        n: Node
        if shape == "circle":
            n = Circle(text(raw, m.line) if raw is not None else label, a.num("r"), a.num("size") or 16)
        elif shape == "cell":
            n = Cell(text(raw, m.line) if raw is not None else label, a.num("size") or 14, bool(a.flag("bold")),
                     a.num("pad") or 10)
        else:
            title, sub = label, None
            if raw is not None:
                parts = split_unquoted(raw, "|")
                title = text(parts[0], m.line)
                sub = text("|".join(parts[1:]), m.line) if len(parts) > 1 else None
            n = Box(title, sub, a.num("size") or 16, a.num("sub_size") or 12, a.num("min_w") or 80)
        apply_common(n, a, m.tone)
        a.done()
        self.register(m.id, n, m.line)
        return n

    def leaf_kw(self, it: LeafLine) -> Node:
        a = Attrs(it.attrs, it.line, it.kw)
        n: Node
        if it.kw == "label":
            if not it.text:
                a.fail("label needs text: label some words")
            t = a.text("tone")
            if t and it.tone:
                a.fail("the tone is given twice (:::name and tone:)")
            ta: TextAlign | None = a.choice("align", TEXT_ALIGNS)
            font: FontName | None = a.choice("font", FONT_NAMES)
            n = Label(it.text, a.num("size") or 14, it.tone or t, bool(a.flag("bold")), ta or "center", font)
            apply_fixed(n, a)
        else:
            if it.text or it.tone:
                a.fail("spacer takes only {w: ..., h: ...}")
            n = Spacer(a.num("w") or 0, a.num("h") or 0)
        a.done()
        n.origin = f"{it.kw} (line {it.line})"
        return n

    def items(self, its: Sequence[Item]) -> tuple[list[Node], list[EdgeLine]]:
        """Nodes declared directly in these lines, in order, and the edge lines among them."""
        out: list[Node] = []
        edges: list[EdgeLine] = []
        for it in its:
            if isinstance(it, Block):
                out.append(self.block(it))
            elif isinstance(it, NodeLine):
                out.append(self.leaf(it.mention))
            elif isinstance(it, LeafLine):
                out.append(self.leaf_kw(it))
            elif isinstance(it, Use):
                out.append(self.use(it))
            elif isinstance(it, EdgeLine):
                out += [self.leaf(e) for e in it.ends if e.declares]
                edges.append(it)
            elif isinstance(it, GridRow):
                raise SketchError(it.line, "| rows only go directly under grid or table")
            else:
                raise SketchError(it.line, "this line only goes inside its own block")
        return out, edges

    def use(self, u: Use) -> Node:
        try:
            kids, edges = self.items(u.items)
        except SketchError as e:
            raise in_template(e, u) from None
        if len(kids) != 1:
            raise SketchError(u.line, f"template {u.name} makes {len(kids)} parts; a template has one root, "
                                      "so wrap its lines in a col or row")
        root = kids[0]
        if u.inst not in self.nodes:
            self.nodes[u.inst] = root
        self.later(root, edges, "auto")
        return root

    def block(self, b: Block) -> Node:
        a = Attrs(b.attrs, b.line, b.kw)
        if b.kw == "panel":
            a.fail("panel goes directly under compare")
        n = BLOCK_BUILDERS.get(b.kw, build_layout)(self, b, a)
        apply_fixed(n, a)
        a.done()
        n.origin = f"{b.kw} (line {b.line})"
        return n

    def ref(self, m: Mention) -> Ref:
        n = self.nodes.get(m.id)
        if n is None:
            raise SketchError(m.line, f"unknown id {m.id!r}")
        return n if m.port is None else Port(n, *m.port)

    def edges(self, e: EdgeLine, default_side: LabelSide = "auto") -> list[Edge]:
        a = Attrs(e.attrs, e.line, "an edge")
        t = a.text("tone")
        if t and e.tone:
            a.fail("the tone is given twice (:::name and tone:)")
        dashed = a.flag("dashed")
        route: Route | None = a.choice("route", ROUTES)
        picked: LabelSide | None = a.choice("label_side", LABEL_SIDES)
        side: LabelSide = picked or default_side
        at, size, head, gap = a.num("label_at"), a.num("size"), a.num("head"), a.num("gap")
        a.done()
        out: list[Edge] = []
        for (head_on, dash, label), (x, y) in zip(e.hops, itertools.pairwise(e.ends), strict=True):
            if x.id == y.id and x.port is None and y.port is None:
                raise SketchError(e.line, f"{x.id} --> {x.id}: an edge needs two different ends (or two ports, "
                                          f"such as {x.id}.right --> {x.id}.top)")
            tone, dash_on = e.tone or t, dash or bool(dashed)
            lat, sz, gp = 0.5 if at is None else at, size or 13, 6 if gap is None else gap
            plan = self.routes.get((x.id, y.id))
            edge: Arrow
            if plan and route is None and x.port is None and y.port is None:
                ends, bends = plan.path(self.nodes[x.id], self.nodes[y.id])
                edge = BentArrow(*ends, bends=bends, label=label, tone=tone, dashed=dash_on, label_at=lat,
                             label_side=picked or plan.side(default_side), size=sz, gap=gp)
                if not head_on:
                    edge.head = 0
            else:
                cls = Arrow if head_on else Line
                edge = cls(self.ref(x), self.ref(y), label, tone=tone, dashed=dash_on, route=route, label_at=lat,
                           label_side=side, size=sz, gap=gp)
            if head_on and head is not None:
                edge.head = head
            edge.origin = f"edge {x.id} → {y.id} (line {e.line})"
            out.append(edge)
        return out
