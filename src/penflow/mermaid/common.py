"""What the Mermaid converters share: the output being built, id mapping and text quoting."""

from __future__ import annotations

import colorsys
import re
from typing import Final, NamedTuple

from ..dsl.errors import snake
from ..dsl.syntax import BLOCKS, LEAVES


class Converted(NamedTuple):
    """The Penflow text, the Mermaid line (1-based) each of its lines came from, and what was approximated."""

    text: str
    lines: list[int]
    notes: list[str]


RESERVED: Final = frozenset((*BLOCKS, *LEAVES, "template", "use", "participant", "note", "set", "gap", "as"))
NAMED: Final[dict[str, str]] = {
    "red": "orange", "orange": "orange", "pink": "orange", "salmon": "orange", "coral": "orange",
    "tomato": "orange", "crimson": "orange", "magenta": "orange", "yellow": "rust", "gold": "rust",
    "brown": "rust", "tan": "rust", "khaki": "rust", "green": "cyan", "lime": "cyan", "blue": "cyan",
    "cyan": "cyan", "teal": "cyan", "navy": "cyan", "purple": "cyan", "violet": "cyan", "lightblue": "cyan",
    "lightgreen": "cyan", "gray": "slate", "grey": "slate", "black": "slate", "white": "slate",
    "silver": "slate", "lightgray": "slate", "lightgrey": "slate",
}


class Output:
    def __init__(self) -> None:
        self.rows: list[tuple[str, int]] = []
        self.notes: list[str] = []
        self.headline: str | None = None
        self.meanings: dict[str, str] = {}

    def add(self, text: str, line: int) -> None:
        self.rows.append((text, line))

    def note(self, msg: str) -> None:
        if msg not in self.notes:
            self.notes.append(msg)

    def done(self) -> Converted:
        head: list[tuple[str, int]] = []
        front: list[str] = []
        if self.headline:
            front.append(f"headline: {_fm(self.headline)}")
        if self.meanings:
            front.append("meanings: {" + ", ".join(f"{k}: {v}" for k, v in self.meanings.items()) + "}")
        if front:
            head = [("---", 1), *((f, 1) for f in front), ("---", 1)]
        head += [(f"%% converted from Mermaid: {n}", 1) for n in self.notes]
        rows = head + self.rows
        return Converted("\n".join(r[0] for r in rows) + "\n", [r[1] for r in rows], list(self.notes))


class IdMap:
    """Mermaid ids to snake_case ids that are unique and aren't Penflow keywords."""

    def __init__(self) -> None:
        self.map: dict[str, str] = {}
        self.used: set[str] = set()

    def get(self, raw: str) -> str:
        if raw in self.map:
            return self.map[raw]
        base = snake(raw)
        if base[0].isdigit():
            base = "n_" + base
        if base in RESERVED:
            base += "_node"
        name, k = base, 2
        while name in self.used:
            name, k = f"{base}_{k}", k + 1
        self.used.add(name)
        self.map[raw] = name
        return name


def _fm(v: str) -> str:
    return '"' + v.replace('"', '\\"') + '"' if (": " in v or v.startswith(("{", '"', "'")) or "#" in v) else v


def clean(t: str) -> str:
    """Mermaid label text to plain text: quotes, `markdown`, entity codes and <br> line breaks."""
    t = t.strip()
    if len(t) >= 2 and t[0] == t[-1] == '"':
        t = t[1:-1]
    if len(t) >= 2 and t[0] == t[-1] == "`":
        t = t[1:-1].replace("**", "").replace("*", "")
    t = re.sub(r"#(\d+);", lambda m: chr(int(m.group(1))), t)
    t = t.replace("#quot;", '"').replace("#amp;", "&").replace("#lt;", "<").replace("#gt;", ">")
    return re.sub(r"<br\s*/?>", "\n", t, flags=re.I).strip()


def quote(t: str, specials: str) -> str:
    """Quote text for the DSL when it holds characters that mean something there."""
    t = t.replace("\n", "\\n")
    if any(s in t for s in (*specials, "%%", '"')) or t.startswith(" "):
        return '"' + t.replace('"', '\\"') + '"'
    return t


def quote_tail(t: str) -> str:
    """Text that ends a line (messages, notes, events): ::: and { would start a tone or attributes."""
    return quote(t, ":::{")


def tone_for(colors: dict[str, str]) -> str:
    for key in ("fill", "stroke", "color"):
        c = colors.get(key, "").strip().lower()
        if not c:
            continue
        if c in NAMED:
            return NAMED[c]
        m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", c)
        if m:
            h = m.group(1)
            if len(h) == 3:
                h = "".join(ch * 2 for ch in h)
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            hue, light, sat = colorsys.rgb_to_hls(r, g, b)
            if sat < 0.15 or light > 0.95 or light < 0.08:
                continue  # grey, white or black: try the stroke
            deg = hue * 360
            return "orange" if deg < 40 or deg >= 300 else "rust" if deg < 70 else "cyan"
    return "accent"


def statements(text: str) -> list[tuple[str, int]]:
    """Lines (1-based), split on ; outside quotes and brackets, without %% comments or directives."""
    out: list[tuple[str, int]] = []
    for no, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        s = raw.strip()
        if not s or s.startswith("%%"):
            continue
        depth, in_quotes, cur = 0, False, ""
        for c in s:
            if c == '"':
                in_quotes = not in_quotes
            elif not in_quotes and c in "[({":
                depth += 1
            elif not in_quotes and c in "])}":
                depth -= 1
            elif not in_quotes and depth == 0 and c == ";":
                if cur.strip():
                    out.append((cur.strip(), no))
                cur = ""
                continue
            cur += c
        if cur.strip():
            out.append((cur.strip(), no))
    return out
