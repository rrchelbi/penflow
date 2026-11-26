"""Reading one line of the DSL: words, quoted text, attributes, and indentation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, NoReturn, TypeAlias

from .errors import SketchError, snake

SNAKE = re.compile(r"[a-z][a-z0-9_]*\Z")
WORD = re.compile(r"[A-Za-z0-9_]+")
NUM = re.compile(r"-?\d+(\.\d+)?\Z")
SENTINEL: Final = "\x00"
"""Stands in for a $param while a template body is checked, so a $param in an id or keyword fails there."""
AttrMap: TypeAlias = dict[str, "str | bool"]


class Scanner:
    def __init__(self, text: str, line: int) -> None:
        self.s, self.i, self.line = text, 0, line

    def fail(self, msg: str) -> NoReturn:
        raise SketchError(self.line, msg)

    def ws(self) -> bool:
        j = self.i
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1
        return self.i > j

    def peek(self, tok: str) -> bool:
        return self.s.startswith(tok, self.i)

    def eat(self, tok: str) -> bool:
        if self.peek(tok):
            self.i += len(tok)
            return True
        return False

    def done(self) -> bool:
        return self.i >= len(self.s)

    def rest(self) -> str:
        return self.s[self.i:]

    def word(self) -> str | None:
        m = WORD.match(self.s, self.i)
        if not m:
            return None
        self.i = m.end()
        return m.group()

    def ident(self, what: str = "id") -> str:
        if self.peek(SENTINEL):
            if what == "tone":
                j = self.s.index(SENTINEL, self.i + 1)
                marker = self.s[self.i:j + 1]
                self.i = j + 1
                return marker
            self.fail(f"a $param can't stand in for {'an' if what[0] in 'aeiou' else 'a'} {what}; templates "
                      "change text, tones and attribute values only")
        w = self.word()
        if w is None:
            self.fail(f"expected {what} here: {self.rest()[:20]!r}")
        if not SNAKE.match(w):
            self.fail(f"{what} {w!r} isn't snake_case; write {snake(w)!r}")
        return w

    def quoted(self) -> str:
        """A "..." string at the cursor; \\" is a quote inside it."""
        assert self.eat('"')
        out: list[str] = []
        while not self.done():
            c = self.s[self.i]
            if c == "\\" and self.peek('\\"'):
                out.append('"')
                self.i += 2
                continue
            self.i += 1
            if c == '"':
                return "".join(out)
            out.append(c)
        self.fail('a quoted text is missing its closing "')

    def until(self, stops: Sequence[str]) -> str:
        """Raw text up to the first stop token that isn't inside quotes."""
        j, quote = self.i, False
        while self.i < len(self.s):
            if self.s[self.i] == '"':
                quote = not quote
            elif not quote and any(self.s.startswith(t, self.i) for t in stops):
                break
            self.i += 1
        return self.s[j:self.i]

    def attrs(self) -> AttrMap:
        """{key: value, flag} at the cursor."""
        assert self.eat("{")
        out: AttrMap = {}
        while True:
            self.ws()
            if self.eat("}"):
                return out
            key = self.ident("attribute key")
            if key in out:
                self.fail(f"{key!r} is given twice")
            self.ws()
            if self.eat(":"):
                self.ws()
                out[key] = self.quoted() if self.peek('"') else self.until((",", "}")).strip()
                if out[key] == "":
                    self.fail(f"{key!r} has no value; write {key}: <value>, or just {key} for true")
            else:
                out[key] = True
            self.ws()
            if self.eat(","):
                continue
            if not self.peek("}"):
                self.fail("attributes are separated by commas and end with }")

    def tail(self) -> tuple[str | None, AttrMap]:
        """An optional :::tone and {attrs} that end a line."""
        self.ws()
        tone = self.ident("tone") if self.eat(":::") else None
        self.ws()
        attrs = self.attrs() if self.peek("{") else {}
        self.ws()
        if not self.done():
            self.fail(f"unexpected {self.rest()!r} at the end of the line")
        return tone, attrs

    def text_tail(self) -> tuple[str, str | None, AttrMap]:
        """Free text, then an optional :::tone and {attrs}."""
        self.ws()
        raw = self.until((":::", "{"))
        return text(raw, self.line), *self.tail()


def number(v: str) -> float:
    """13 stays an int, so the SVG says 13 like the Python API does, not 13.0."""
    return float(v) if "." in v else int(v)


def text(raw: str, line: int) -> str:
    """Strip, unquote a "..." text, and turn \\n into a line break."""
    t = raw.strip()
    if t.startswith('"'):
        sc = Scanner(t, line)
        t = sc.quoted()
        if sc.rest().strip():
            sc.fail(f"text after the closing quote: {sc.rest().strip()!r}")
        return t.replace("\\n", "\n")
    return t.replace("\\n", "\n")


def split_unquoted(raw: str, sep: str) -> list[str]:
    """Split on `sep` outside quotes and outside [ ] / ( ) / { }."""
    parts: list[str] = []
    cur: list[str] = []
    depth, quote = 0, False
    for c in raw:
        if c == '"':
            quote = not quote
        elif not quote:
            if c in "[({":
                depth += 1
            elif c in "])}":
                depth -= 1
            elif c == sep and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(c)
    parts.append("".join(cur))
    return parts


@dataclass
class SourceLine:
    no: int
    indent: int
    text: str
    children: list[SourceLine] = field(default_factory=list["SourceLine"])


def strip_comment(s: str) -> str:
    quote = False
    for i, c in enumerate(s):
        if c == '"':
            quote = not quote
        elif not quote and s.startswith("%%", i):
            return s[:i]
    return s


def source_tree(lines: Sequence[tuple[int, str]]) -> list[SourceLine]:
    root = SourceLine(0, -1, "")
    stack = [root]
    for no, raw in lines:
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise SketchError(no, "indent with spaces, not tabs")
        body = strip_comment(raw).rstrip()
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip(" "))
        if indent % 2:
            raise SketchError(no, f"indent by 2 spaces per level (this line has {indent})")
        while stack[-1].indent >= indent:
            stack.pop()
        if indent > stack[-1].indent + 2 and stack[-1] is not root:
            raise SketchError(no, "this line is indented more than one level past the line above")
        if stack[-1] is root and indent:
            raise SketchError(no, "the first line of the body can't be indented")
        src = SourceLine(no, indent, body.strip())
        stack[-1].children.append(src)
        stack.append(src)
    return root.children
