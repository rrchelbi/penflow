"""Mermaid `flowchart` / `graph` to a `flow` block, with subgraphs as regions."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from ..dsl.errors import SketchError, snake
from ..dsl.layered import layers
from .common import IdMap, Output, clean, quote, quote_tail, tone_for

SHAPES: Final[tuple[tuple[str, str, str], ...]] = (
    ("(((", ")))", "circle"), ("((", "))", "circle"), ("([", "])", "stadium"), ("[[", "]]", "subroutine"),
    ("[(", ")]", "cylinder"), ("{{", "}}", "hexagon"), ("[/", "/]", "parallelogram"),
    ("[\\", "\\]", "parallelogram"), ("[/", "\\]", "trapezoid"), ("[\\", "/]", "trapezoid"),
    ("[", "]", "rect"), ("(", ")", "rounded"), ("{", "}", "decision"), (">", "]", "flag"))
_ID = re.compile(r"[^\s\[\](){}<>&|:;\"'=.\-]+(?:-(?![-.>xo=])[^\s\[\](){}<>&|:;\"'=.\-]+)*")
_LINK_TEXT = re.compile(r"(?P<l>[<xo]?)(?P<open>--|==|-\.)(?![->=.])\s*(?P<lab>[^|]+?)\s*"
                        r"(?P<close>-{2,}|={2,}|\.-+)(?P<r>[>xo]?)")
_LINK = re.compile(r'(?P<l>[<xo]?)(?P<body>-{2,}|={2,}|-\.+-|~~~)(?P<r>[>xo]?)(?:\s*\|(?P<lab>"[^"]*"|[^|]*)\|)?')
DIRS: Final[dict[str, str]] = {"lr": "lr", "td": "td", "tb": "td", "rl": "lr", "bt": "td"}


@dataclass
class _Group:
    title: str | None
    raw: str | None
    direction: str | None
    line: int
    parent: _Group | None = None
    nodes: list[str] = field(default_factory=list[str])
    children: list[_Group] = field(default_factory=list["_Group"])


@dataclass
class _FNode:
    raw: str
    group: _Group
    line: int
    text: str | None = None
    shape: str = "rect"
    cls: str | None = None


@dataclass
class _FEdge:
    a: str
    b: str
    arrow: str
    label: str | None
    line: int


def _closer(s: str, i: int, close: str) -> tuple[str, int] | None:
    """Text up to `close` (quotes may hide it), and the index after it."""
    j, in_quotes = i, False
    while j < len(s):
        if s[j] == '"':
            in_quotes = not in_quotes
        elif not in_quotes and s.startswith(close, j):
            return s[i:j], j + len(close)
        j += 1
    return None


def _node(s: str, i: int, line: int) -> tuple[str, str | None, str, list[str], int]:
    m = _ID.match(s, i)
    if not m:
        raise SketchError(line, f"expected a node id at {s[i:i + 20]!r}")
    raw, i = m.group(), m.end()
    label: str | None = None
    shape = "rect"
    if s.startswith("@{", i):
        got = _closer(s, i + 2, "}")
        if got is None:
            raise SketchError(line, "@{ ... } needs a closing }")
        inner, i = got
        lm = re.search(r'label:\s*("([^"]*)"|[^,]+)', inner)
        if lm:
            label = clean(lm.group(1))
        sm = re.search(r"shape:\s*([\w-]+)", inner)
        if sm:
            shape = sm.group(1)
    else:
        for open_, close, name in SHAPES:
            if s.startswith(open_, i):
                got = _closer(s, i + len(open_), close)
                if got is not None:
                    label, i = clean(got[0]), got[1]
                    shape = name
                    break
    classes: list[str] = []
    while s.startswith(":::", i):
        cm = re.match(r":::([\w-]+)", s[i:])
        if not cm:
            break
        classes.append(cm.group(1))
        i += cm.end()
    return raw, label, shape, classes, i


def _group_of_nodes(s: str, i: int, line: int) -> tuple[list[tuple[str, str | None, str, list[str]]], int]:
    nodes: list[tuple[str, str | None, str, list[str]]] = []
    while True:
        while i < len(s) and s[i] == " ":
            i += 1
        raw, label, shape, classes, i = _node(s, i, line)
        nodes.append((raw, label, shape, classes))
        j = i
        while j < len(s) and s[j] == " ":
            j += 1
        if s.startswith("&", j):
            i = j + 1
            continue
        return nodes, i


def _link(s: str, i: int, out: Output) -> tuple[str, str | None, int] | None:
    while i < len(s) and s[i] == " ":
        i += 1
    m = _LINK_TEXT.match(s, i) or _LINK.match(s, i)
    if not m:
        return None
    gd = m.groupdict()
    body = (gd.get("body") or "") + (gd.get("open") or "") + (gd.get("close") or "")
    label = clean(gd["lab"]) if gd.get("lab") else None
    if body == "~~~":
        out.note("invisible links (~~~) dropped")
        return "", None, m.end()
    head = gd["r"] in (">", "x", "o")
    if gd["r"] in ("x", "o"):
        out.note("--x and --o link ends drawn as arrows")
    if gd["l"]:
        out.note("two-headed links drawn with one head")
    if "=" in body:
        out.note("thick links (==>) drawn as normal links")
    dotted = "." in body
    arrow = ("-.->" if head else "-.-") if dotted else ("-->" if head else "---")
    return arrow, label, m.end()


def convert_flowchart(head: str, stmts: Sequence[tuple[str, int]], out: Output, line: int) -> None:
    parts = head.split()
    direction = DIRS.get(parts[1].lower(), "td") if len(parts) > 1 else "td"
    if len(parts) > 1 and parts[1].lower() in ("rl", "bt"):
        out.note(f"direction {parts[1]} drawn as {direction}")
    root = _Group(None, None, direction, line)
    group = root
    nodes: dict[str, _FNode] = {}
    order: list[str] = []
    edges: list[_FEdge] = []
    class_colors: dict[str, dict[str, str]] = {}
    groups_by_raw: dict[str, _Group] = {}

    def touch(raw: str, label: str | None, shape: str, classes: list[str], no: int) -> None:
        n = nodes.get(raw)
        if n is None:
            if raw in groups_by_raw:
                return
            n = nodes[raw] = _FNode(raw, group, no)
            group.nodes.append(raw)
            order.append(raw)
        if label is not None:
            n.text, n.shape = label, shape
        if classes:
            n.cls = classes[0]
            if len(classes) > 1:
                out.note("a node with several classes keeps the first")

    for s, no in stmts:
        word = s.split()[0]
        low = word.lower()
        if low == "subgraph":
            rest = s[len(word):].strip()
            m = re.match(r'([^\s\[]+)\s*\[(.*)\]\s*$', rest)
            raw, title = (m.group(1), clean(m.group(2))) if m else (rest if " " not in rest else None, clean(rest))
            g = _Group(title, raw, None, no, group)
            group.children.append(g)
            if raw:
                groups_by_raw[raw] = g
            group = g
        elif low == "end" and s == word:
            if group.parent is None:
                raise SketchError(no, "'end' without a subgraph")
            group = group.parent
        elif low == "direction":
            d = s.split()[1].lower() if len(s.split()) > 1 else ""
            group.direction = DIRS.get(d, group.direction)
        elif low == "classdef":
            m = re.match(r"classDef\s+([\w,-]+)\s+(.*)$", s, flags=re.I)
            if m:
                colors = dict(kv.split(":", 1) for kv in m.group(2).rstrip(";").split(",") if ":" in kv)
                for name in m.group(1).split(","):
                    class_colors[name] = {k.strip(): v.strip() for k, v in colors.items()}
        elif low == "class":
            m = re.match(r"class\s+([\w,\s-]+?)\s+([\w-]+)\s*$", s)
            if m:
                for raw in (x.strip() for x in m.group(1).split(",")):
                    touch(raw, None, "rect", [m.group(2)], no)
        elif low == "style":
            out.note("style lines (direct colors) dropped; use classDef and class for tones")
        elif low == "linkstyle":
            out.note("linkStyle lines dropped; put a tone on the edge line instead")
        elif low in ("click", "callback"):
            out.note("click handlers dropped")
        else:
            i = 0
            left, i = _group_of_nodes(s, i, no)
            for raw, label, shape, classes in left:
                touch(raw, label, shape, classes, no)
            while True:
                link = _link(s, i, out)
                if link is None:
                    break
                arrow, label, i = link
                right, i = _group_of_nodes(s, i, no)
                for raw, lab, shape, classes in right:
                    touch(raw, lab, shape, classes, no)
                if arrow:
                    for a in left:
                        for b in right:
                            if a[0] in groups_by_raw or b[0] in groups_by_raw:
                                out.note("links to or from a subgraph dropped")
                                continue
                            edges.append(_FEdge(a[0], b[0], arrow, label, no))
                left = right
            rest = s[i:].strip()
            if rest:
                raise SketchError(no, f"couldn't read {rest!r} in this flowchart line")
    if group is not root:
        raise SketchError(group.line, f"subgraph {group.title or ''} has no 'end'")

    ids = IdMap()
    for raw in order:
        ids.get(raw)
    used_classes = [n.cls for n in nodes.values() if n.cls]
    for c in dict.fromkeys(used_classes):
        out.meanings[meaning_name(c)] = tone_for(class_colors.get(c, {}))
        if c not in class_colors:
            out.note(f"class {c} has no classDef; its meaning is drawn in the accent tone")
    for n in nodes.values():
        if n.shape not in ("rect", "rounded", "circle"):
            out.note(f"{n.shape} shapes drawn as boxes")

    def home(raw: str) -> _Group:
        return nodes[raw].group

    internal: dict[int, list[_FEdge]] = {}
    cross: list[_FEdge] = []
    for e in edges:
        if home(e.a) is home(e.b):
            internal.setdefault(id(home(e.a)), []).append(e)
        else:
            cross.append(e)

    def decl(raw: str) -> str:
        n = nodes[raw]
        name = ids.get(raw)
        label = n.text if n.text is not None else raw
        out_s = name
        if n.shape == "circle":
            out_s += f"(({quote(label, ')')}))"
        elif label != name.replace("_", " "):
            parts = label.split("\n")
            title = quote(parts[0], "|]")
            sub = quote("\n".join(parts[1:]), "|]") if len(parts) > 1 else None
            out_s += f"[{title}{' | ' + sub if sub else ''}]"
        if n.cls:
            out_s += f":::{meaning_name(n.cls)}"
        return out_s

    declared: set[str] = set()

    def mention(raw: str) -> str:
        """The node's full declaration the first time it's written, its id after that."""
        if raw in declared:
            return ids.get(raw)
        declared.add(raw)
        return decl(raw)

    def edge_line(e: _FEdge) -> str:
        lab = f"|{quote(e.label, '|')}|" if e.label else ""
        return f"{mention(e.a)} {e.arrow}{lab} {mention(e.b)}"

    def top(raw: str, g: _Group) -> _Group | None:
        """The child of `g` that holds this node (None when it's g's own)."""
        h: _Group | None = nodes[raw].group
        while h is not None and h.parent is not g:
            if h is g:
                return None
            h = h.parent
        return h

    def emit_flow(g: _Group, pad: str, d: str) -> None:
        own = internal.get(id(g), [])
        in_edges = {x for e in own for x in (e.a, e.b)}
        out.add(f"{pad}flow {d}", g.line)
        for r in g.nodes:
            if r not in in_edges:
                out.add(f"{pad}  {mention(r)}", nodes[r].line)
        for e in own:
            out.add(f"{pad}  {edge_line(e)}", e.line)

    def emit_group(g: _Group, indent: int, d: str) -> None:
        """A group's own nodes as a flow, and each subgraph as a region, ordered by the edges between them
        (one rank per step, side by side across the flow's direction)."""
        pad = "  " * indent
        d = g.direction or d
        across = "td" if d == "lr" else "lr"  # a region lays out across its parent, so edges leave it cleanly
        names = (["~own"] if g.nodes else []) + [f"~{i}" for i in range(len(g.children))]
        if len(names) == 1 and g.nodes:
            emit_flow(g, pad, d)
            return
        part = {id(c): f"~{i}" for i, c in enumerate(g.children)}

        def item(raw: str) -> str | None:
            h = top(raw, g)
            return "~own" if h is None else part.get(id(h))

        links: list[tuple[str, str]] = []
        for e in cross:
            a, b = item(e.a), item(e.b)
            if a and b and a != b and a in names and b in names:
                links.append((a, b))
        ranks = [[x for x in r if isinstance(x, str)] for r in layers(names, links).ranks]
        ranks = [r for r in ranks if r]
        outer = indent
        if len(ranks) > 1:
            out.add(f"{pad}{'row' if d == 'lr' else 'col'} {{gap: 40}}", g.line)
            outer += 1
        for r in ranks:
            inner = outer
            if len(r) > 1:
                out.add(f"{'  ' * outer}{'col' if d == 'lr' else 'row'} {{gap: 30}}", g.line)
                inner += 1
            ipad = "  " * inner
            for name in r:
                if name == "~own":
                    emit_flow(g, ipad, d)
                    continue
                c = g.children[int(name[1:])]
                if not c.nodes and not c.children:
                    raise SketchError(c.line, f"subgraph {c.title or c.raw} is empty")
                out.add(f"{ipad}region {quote_tail(c.title or c.raw or '')}".rstrip(), c.line)
                emit_group(c, inner + 1, c.direction or across)

    if not nodes:
        raise SketchError(line, "the flowchart has no nodes")
    emit_group(root, 0, direction)
    for e in cross:
        out.add(edge_line(e), e.line)


def meaning_name(name: str) -> str:
    """A Mermaid class name as a Penflow meaning name."""
    s = snake(name)
    return "c_" + s if s[0].isdigit() else s
