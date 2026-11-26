"""Mermaid `sequenceDiagram` to a `sequence_diagram` block."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from ..dsl.errors import SketchError
from ..nodes import CIRCLED
from .common import IdMap, Output, clean, quote, quote_tail

_MSG = re.compile(r"^(?P<a>.+?)\s*(?P<arrow><<-->>|<<->>|-->>|->>|--x|-x|--\)|-\)|-->|->)(?P<act>[+-]?)"
                  r"\s*(?P<b>[^:]+?)\s*(?::\s*(?P<text>.*))?$")
EMPTY: Final = '""'
"""An empty note: the row that carries an activation bar."""
BLOCK_WORDS: Final = ("loop", "alt", "else", "opt", "par", "and", "critical", "option", "break", "rect", "box")


@dataclass
class _Row:
    kind: Literal["msg", "note"]
    line: int
    a: str = ""
    b: str = ""
    cross: bool = False
    text: str = ""
    bar: int = 0


def _at(rows: Sequence[_Row], r: _Row) -> int:
    return next(i for i, x in enumerate(rows) if x is r)


def convert_sequence(stmts: Sequence[tuple[str, int]], out: Output, line: int) -> None:
    ids = IdMap()
    labels: dict[str, str] = {}
    declared: list[tuple[str, int]] = []
    rows: list[_Row] = []
    open_bars: dict[str, list[_Row]] = {}
    number = 0

    def lane(raw: str, no: int) -> str:
        raw = raw.strip()
        name = ids.get(raw)
        if name not in labels:
            labels[name] = raw
        return name

    def activate(name: str, no: int) -> None:
        r = _Row("note", no, a=name, text="")
        rows.append(r)
        open_bars.setdefault(name, []).append(r)

    def deactivate(name: str, no: int) -> None:
        stack = open_bars.get(name)
        if not stack:
            raise SketchError(no, f"deactivate {labels.get(name, name)} without an activate")
        r = stack.pop()
        r.bar = len(rows) - _at(rows, r)

    for s, no in stmts:
        word = s.split()[0]
        low = word.lower()
        if low in ("participant", "actor"):
            m = re.match(r"\w+\s+(.+?)(?:\s+as\s+(.+))?$", s)
            assert m
            name = lane(m.group(1), no)
            if m.group(2):
                labels[name] = clean(m.group(2))
            if name not in (d for d, _ in declared):
                declared.append((name, no))
            if low == "actor":
                out.note("actors drawn as boxes")
        elif low in ("create", "destroy"):
            out.note("create and destroy dropped; lanes span the whole diagram")
            if low == "create":
                m = re.match(r"create\s+(participant|actor)\s+(.+?)(?:\s+as\s+(.+))?$", s)
                if m:
                    name = lane(m.group(2), no)
                    if m.group(3):
                        labels[name] = clean(m.group(3))
                    declared.append((name, no))
        elif low == "note":
            m = re.match(r"note\s+(right of|left of|over)\s+([^:]+):\s*(.*)$", s, flags=re.I)
            if not m:
                raise SketchError(no, "couldn't read this note; Mermaid writes Note right of A: text")
            lanes = [x.strip() for x in m.group(2).split(",")]
            if len(lanes) > 1:
                out.note("notes over several lanes sit beside the first one")
            rows.append(_Row("note", no, a=lane(lanes[0], no), text=clean(m.group(3))))
        elif low == "activate":
            activate(lane(s.split(None, 1)[1], no), no)
        elif low == "deactivate":
            deactivate(lane(s.split(None, 1)[1], no), no)
        elif low == "autonumber":
            number = 1
        elif low == "title":
            out.headline = clean(s[len(word):].lstrip(": "))
        elif low in BLOCK_WORDS:
            out.note("loop, alt, opt and par blocks aren't drawn; their messages are kept in order")
        elif low == "end" and s == word:
            continue
        else:
            m = _MSG.match(s)
            if not m:
                raise SketchError(no, f"couldn't read {s!r} as a message (A->>B: text)")
            arrow = m.group("arrow")
            a, b = lane(m.group("a"), no), lane(m.group("b"), no)
            if arrow in ("-->>", "--x", "--)", "-->"):
                out.note("dashed messages drawn solid")
            if arrow in ("->", "-->", "-)", "--)", "<<->>", "<<-->>"):
                out.note("open, async and two-way message arrows drawn as ->>")
            if m.group("act") == "+":
                activate(b, no)
            text = clean(m.group("text") or "")
            if number:
                text = f"{CIRCLED[number - 1] if number <= len(CIRCLED) else str(number) + '.'} {text}".strip()
                number += 1
            if a == b:
                out.note("messages to self drawn as notes beside the lane")
                rows.append(_Row("note", no, a=a, text=text))
            else:
                rows.append(_Row("msg", no, a=a, b=b, cross=arrow.endswith("x"), text=text))
            if m.group("act") == "-":
                deactivate(a, no)
    for name, stack in open_bars.items():
        for r in stack:
            r.bar = len(rows) - _at(rows, r)
            out.note(f"activation of {labels[name]} never closed; it runs to the end")
    if not rows and not declared:
        raise SketchError(line, "the sequence diagram has no participants or messages")

    out.add("sequence_diagram", line)
    for name, no in declared:
        label = labels[name]
        out.add(f"  participant {name}" + (f"[{quote(label, '|]')}]" if label != name.replace("_", " ") else ""), no)
    named = {d for d, _ in declared}
    for r in rows:  # lanes first seen in a message, whose label isn't their id
        for name in (r.a, r.b) if r.kind == "msg" else (r.a,):
            if name not in named and labels[name] != name.replace("_", " "):
                out.add(f"  participant {name}[{quote(labels[name], '|]')}]", r.line)
            named.add(name)
    for r in rows:
        if r.kind == "msg":
            text = f": {quote_tail(r.text)}" if r.text else ""
            out.add(f"  {r.a} {'-x' if r.cross else '->>'} {r.b}{text}", r.line)
        else:
            bar = f" {{bar: {r.bar}}}" if r.bar else ""
            out.add(f"  note {r.a}: {quote_tail(r.text) if r.text else EMPTY}{bar}", r.line)
