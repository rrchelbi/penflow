"""The drawing layer: a coordinate canvas with a hand-drawn pen.

Lines are drawn as two slightly different wobbly curves, like a pen going over
a line twice. Colors are CSS classes (stroke-<tone>, t-<tone>, fill-<tone>...)
that either a site stylesheet themes (`svg()`) or that get styled in place
(`svg(inline=True, palette=...)`) for Markdown readers such as Obsidian.

The composable API in `penflow.nodes` draws on this canvas. Use it directly
for hand-placed drawings; its output is kept byte-for-byte stable.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from typing import Final, Literal, TypeAlias, TypedDict, TypeGuard

ToneName: TypeAlias = Literal["orange", "cyan", "rust", "slate"]
FontName: TypeAlias = Literal["hand", "mono"]
PaletteName: TypeAlias = Literal["auto", "paper"]
Anchor: TypeAlias = Literal["start", "middle", "end"]
Point: TypeAlias = tuple[float, float]


def escape(s: str) -> str:
    """Escape text for SVG/HTML content."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Tones from the site logo. Each: (light ink, light tint), (dark ink, dark tint).
# Used as stroke-<tone>, t-<tone>, fill-<tone> (tint) and solid-<tone> (dots).
TONES: Final[dict[ToneName, tuple[tuple[str, str], tuple[str, str]]]] = {
    "orange": (("#d0531f", "rgba(226,98,47,.13)"), ("#e2622f", "rgba(226,98,47,.16)")),
    "cyan": (("#0e8a9c", "rgba(72,201,217,.16)"), ("#48c9d9", "rgba(72,201,217,.14)")),
    "rust": (("#a3441f", "rgba(183,77,36,.12)"), ("#cf6d3f", "rgba(183,77,36,.22)")),
    "slate": (("#3b4350", "rgba(42,48,56,.08)"), ("#a3adbb", "rgba(163,173,187,.12)")),
}


def is_tone(name: object) -> TypeGuard[ToneName]:
    """True for the four tone names; narrows the type for checkers."""
    return name in TONES


def _tone_style(names: list[ToneName]) -> str:
    """Per-SVG theme for the tones it uses. The --sk-* variables sit in :where()
    so a site stylesheet can redefine them; the class rules use `svg <element>.<class>`
    (0,1,2) so they beat a generic `.sketch text` / `.sketch path` rule."""
    def vars_(i: int) -> str:
        return "".join(f"--sk-{n}:{TONES[n][i][0]};--sk-{n}-bg:{TONES[n][i][1]};" for n in names)

    css = [f":where(svg){{{vars_(0)}}}",
           "@media (prefers-color-scheme:dark){"
           f":where(:root:not(.light):not([data-theme=light])) :where(svg){{{vars_(1)}}}}}",
           f":where(.dark,[data-theme=dark]) :where(svg){{{vars_(1)}}}"]
    css += [f"svg path.stroke-{n}{{fill:none;stroke:var(--sk-{n});stroke-width:1.8;"
            f"stroke-linecap:round;stroke-linejoin:round}}"
            f"svg text.t-{n}{{fill:var(--sk-{n})}}svg path.fill-{n}{{fill:var(--sk-{n}-bg)}}"
            f"svg circle.solid-{n}{{fill:var(--sk-{n})}}" for n in names]
    return "<style>" + "".join(css) + "</style>"


# For Markdown readers that strip <style> and have no .sketch CSS (Obsidian,
# GitHub, VS Code): every element gets a style attribute instead.
#
# Palettes:
#   "auto"  follows the reader's theme: ink is currentColor, the rest uses
#           Obsidian's variables, tones are translucent tints.
#   "paper" an Excalidraw-like card: white paper, dark ink, saturated yellow,
#           teal, orange and gray fills, blue for key lines, a handwriting font
#           for notes and monospace for box labels. Looks the same in light and
#           dark mode because it brings its own background.
# Each value can still be overridden with the --sk-* variable (e.g. a CSS snippet).
FONTS: Final[dict[FontName, str]] = {
    "hand": "Virgil, Excalifont, 'Segoe Print', 'Bradley Hand', 'Comic Sans MS', cursive",
    "mono": "'Cascadia Code', 'Cascadia Mono', Consolas, 'Courier New', monospace",
}


class Palette(TypedDict):
    ink: str
    soft: str
    accent: str
    surface: str
    width: float
    tones: dict[ToneName, tuple[str, str, str]]  # tone: (stroke, fill, text)


PALETTES: Final[dict[PaletteName, Palette]] = {
    "auto": {
        "ink": "currentColor", "soft": "var(--text-muted,currentColor)", "accent": "#e2622f",
        "surface": "var(--background-primary,transparent)", "width": 1.8,
        "tones": {"orange": ("#e2622f", "rgba(226,98,47,.16)", "#e2622f"),
                  "cyan": ("#1fa9bc", "rgba(72,201,217,.17)", "#1fa9bc"),
                  "rust": ("#c4592b", "rgba(183,77,36,.17)", "#c4592b"),
                  "slate": ("#6b7a8c", "rgba(107,122,140,.15)", "#6b7a8c")},
    },
    "paper": {
        "ink": "#1e1e1e", "soft": "#5f6b76", "accent": "#2c4fd6", "surface": "#ffffff", "width": 2.2,
        "tones": {"cyan": ("#1c8c9c", "#c3ecf2", "#157887"),     # teal
                  "orange": ("#e8702a", "#fde1d0", "#d2601b"),
                  "rust": ("#b98510", "#fcc847", "#8a5a00"),     # yellow
                  "slate": ("#343a40", "#e9ecef", "#343a40")},   # gray
    },
}


def _inline_styles(pal: Palette) -> tuple[dict[str, str], str, str]:
    def v(name: str, val: str) -> str:
        return f"var(--sk-{name},{val})"

    line = (f"fill:none;stroke-width:{pal['width']};stroke-linecap:round;stroke-linejoin:round;stroke:")
    ink, soft = v("ink", pal["ink"]), v("soft", pal["soft"])
    acc, surf = v("accent", pal["accent"]), v("surface", pal["surface"])
    st = {"stroke": line + ink, "stroke-soft": line + soft, "stroke-accent": line + acc,
          "t-soft": "fill:" + soft, "t-accent": "fill:" + acc,
          "fill-surface": "fill:" + surf, "fill-accent": "fill:" + acc, "t-ink": "fill:" + ink}
    for n, (stroke, fill, text) in pal["tones"].items():
        c = v(n, stroke)
        st.update({f"stroke-{n}": line + c, f"t-{n}": "fill:" + v(n + "-text", text),
                   f"fill-{n}": "fill:" + v(n + "-bg", fill), f"solid-{n}": "fill:" + c,
                   f"hatch-{n}": "fill:none;stroke-width:1.1;stroke-linecap:round;opacity:.55;stroke:" + c})
    return st, surf, ink


def _inline(body: str, palette: PaletteName = "auto") -> tuple[str, str]:
    st, surf, ink = _inline_styles(PALETTES[palette])
    # Labels get a thin outline in the page color, so lines crossing them pass behind.
    halo = f";paint-order:stroke;stroke:{surf};stroke-width:4px;stroke-linejoin:round"

    def sub(m: re.Match[str]) -> str:
        tag, attrs, cls = m.groups()
        extra = halo if tag == "text" and 'data-halo="1"' in attrs else ""
        return f'<{tag}{attrs} class="{cls}" style="{st.get(cls, "")}{extra}"'

    body = re.sub(r'<(\w+)([^>]*?) class="([^"]+)"', sub, body)
    body = re.sub(r'<text ((?:(?!class=)[^>])*?) data-halo="1"((?:(?!class=)[^>])*)>',
                  lambda m: f'<text {m.group(1)}{m.group(2)} style="fill:{ink}{halo}">', body)
    return re.sub(r"<text (?![^>]*(?:class|style)=)", f'<text style="fill:{ink}" ', body), surf


class Canvas:
    def __init__(self, width: float, height: float, title: str, seed: int = 1, clean: bool = False) -> None:
        """clean=True draws the same diagram precisely: straight single lines,
        rounded boxes, level text and a sans font, instead of the pen look."""
        self.w, self.h, self.title, self.clean = width, height, title, clean
        self.box_font: FontName | None = None  # e.g. "mono" for monospace box labels
        self.halo = False  # turn on for diagrams where lines cross labels
        self.rnd = random.Random(seed)
        self.out: list[str] = []

    def j(self, a: float) -> float:
        return 0.0 if self.clean else self.rnd.uniform(-a, a)

    def line(self, x1: float, y1: float, x2: float, y2: float, cls: str = "stroke", rough: float = 1.4,
             passes: int = 2) -> None:
        L = math.hypot(x2 - x1, y2 - y1)
        if L == 0:
            return
        nx, ny = -(y2 - y1) / L, (x2 - x1) / L
        if self.clean:
            self.out.append(f'<path class="{cls}" d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}"/>')
            return
        r = min(rough, 0.6 + L * 0.012)
        for p in range(passes):
            a = (x1 + self.j(r), y1 + self.j(r))
            b = (x2 + self.j(r), y2 + self.j(r))

            def mid(t: float) -> Point:
                d = self.j(r * 1.6)
                return (x1 + (x2 - x1) * t + nx * d, y1 + (y2 - y1) * t + ny * d)

            c1 = mid(self.rnd.uniform(0.3, 0.45))
            c2 = mid(self.rnd.uniform(0.6, 0.8))
            op = "" if p == 0 else ' opacity="0.55"'
            self.out.append(
                f'<path class="{cls}"{op} d="M{a[0]:.1f} {a[1]:.1f} C{c1[0]:.1f} {c1[1]:.1f} '
                f'{c2[0]:.1f} {c2[1]:.1f} {b[0]:.1f} {b[1]:.1f}"/>'
            )

    def text(self, x: float, y: float, s: str, size: float = 16, cls: str = "", anchor: Anchor = "middle",
             weight: int = 400, rot: float | None = None, font: FontName | None = None,
             halo: bool | None = None) -> None:
        """`font` picks a FONTS family ("hand", "mono") for this label only.
        `halo` (default: the sketch's .halo) outlines the label in the paper color
        in inline mode, so lines crossing it pass behind; off for text on fills."""
        rot = self.j(1.0) if rot is None else rot
        c = f' class="{cls}"' if cls else ""
        f = f' font-family="{FONTS[font]}"' if font else ""
        if self.halo if halo is None else halo:
            f += ' data-halo="1"'
        self.out.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}"{f} '
            f'text-anchor="{anchor}" transform="rotate({rot:.2f} {x:.1f} {y:.1f})"{c}>{escape(s)}</text>'
        )

    def fill_rect(self, x: float, y: float, w: float, h: float, cls: str = "fill-surface") -> None:
        if self.clean:
            self.out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6"/>')
            return
        j = self.j
        pts = [(x + j(2), y + j(2)), (x + w + j(2), y + j(2)), (x + w + j(2), y + h + j(2)), (x + j(2), y + h + j(2))]
        d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts) + " Z"
        self.out.append(f'<path class="{cls}" d="{d}"/>')

    def rect(self, x: float, y: float, w: float, h: float, cls: str = "stroke", fill: bool = True, o: float = 3,
             fill_cls: str = "fill-surface") -> None:
        if fill:
            self.fill_rect(x, y, w, h, fill_cls)
        if self.clean:
            rx = 3 if w < 20 else 6
            self.out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}"/>')
            return
        self.line(x - o, y, x + w + o, y, cls)
        self.line(x + w, y - o, x + w, y + h + o, cls)
        self.line(x + w + o, y + h, x - o, y + h, cls)
        self.line(x, y + h + o, x, y - o, cls)

    def dashed_rect(self, x: float, y: float, w: float, h: float, cls: str = "stroke-soft") -> None:
        """Region outline drawn as short wobbly dashes."""
        if self.clean:
            self.out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                            f'rx="6" stroke-dasharray="6 5"/>')
            return

        def dashes(x1: float, y1: float, x2: float, y2: float) -> None:
            L = math.hypot(x2 - x1, y2 - y1)
            n = max(1, int(L // 18))
            for i in range(n):
                t0, t1 = i / n, (i + 0.6) / n
                self.line(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0,
                          x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1, cls, rough=0.8, passes=1)
        dashes(x, y, x + w, y)
        dashes(x + w, y, x + w, y + h)
        dashes(x + w, y + h, x, y + h)
        dashes(x, y + h, x, y)

    def arrow(self, x1: float, y1: float, x2: float, y2: float, cls: str = "stroke", head: float = 12) -> None:
        self.line(x1, y1, x2, y2, cls, rough=1.8)
        ang = math.atan2(y2 - y1, x2 - x1)
        for s in (-1, 1):
            a = ang + math.pi - s * math.radians(26 + self.j(4))
            l = head + self.j(2)
            self.line(x2, y2, x2 + math.cos(a) * l, y2 + math.sin(a) * l, cls, rough=0.8, passes=1)

    def dot(self, x: float, y: float, r: float = 5, cls: str = "fill-accent") -> None:
        self.out.append(f'<circle class="{cls}" cx="{x + self.j(0.8):.1f}" cy="{y + self.j(0.8):.1f}" r="{r}"/>')

    def circle(self, x: float, y: float, r: float, cls: str = "stroke", fill_cls: str = "fill-surface") -> None:
        if self.clean:
            self.out.append(f'<circle class="{fill_cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>')
            self.out.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>')
            return
        pts: list[Point] = []
        for i in range(25):
            t = i / 24 * 2 * math.pi
            rr = r + self.j(0.9)
            pts.append((x + math.cos(t) * rr, y + math.sin(t) * rr))
        d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        self.out.append(f'<path class="{fill_cls}" d="{d} Z"/>')
        self.out.append(f'<path class="{cls}" d="{d}"/>')

    def hatch(self, x: float, y: float, w: float, h: float, tone: ToneName, gap: float = 10) -> None:
        """Wobbly 45-degree hatching inside a rectangle, like a shaded region."""
        k = -h
        while k < w:
            # segment of the line x' - x = (y' - y) + k, clipped to the rectangle
            t0, t1 = max(0, -k), min(h, w - k)
            if t1 > t0:
                self.line(x + k + t0, y + t0, x + k + t1, y + t1, f"hatch-{tone}", rough=0.7, passes=1)
            k += gap

    def check(self, x: float, y: float, cls: str = "stroke-accent") -> None:
        self.line(x - 7, y, x - 2, y + 6, cls, rough=0.6, passes=1)
        self.line(x - 2, y + 6, x + 8, y - 7, cls, rough=0.6, passes=1)

    def cross(self, x: float, y: float, s: float = 8, cls: str = "stroke-accent") -> None:
        self.line(x - s, y - s, x + s, y + s, cls, rough=0.8, passes=1)
        self.line(x + s, y - s, x - s, y + s, cls, rough=0.8, passes=1)

    def box(self, x: float, y: float, w: float, h: float, title: str, sub: str | None = None, accent: bool = False,
            size: float = 18, sub_size: float = 14, dashed: bool = False, tone: ToneName | None = None) -> None:
        """`tone` (a TONES name: orange, cyan, rust, slate) tints the fill and colors
        the outline and title. The SVG carries the tone theme itself."""
        if tone:
            cls, tcls, fcls = f"stroke-{tone}", f"t-{tone}", f"fill-{tone}"
        else:
            cls = "stroke-accent" if accent else "stroke"
            tcls = "t-accent" if accent else ""
            fcls = "fill-surface"
        if dashed:
            self.fill_rect(x, y, w, h, fcls)
            self.dashed_rect(x, y, w, h, cls)
        else:
            self.rect(x, y, w, h, cls, fill_cls=fcls)
        cx = x + w / 2
        if sub:
            self.text(cx, y + h / 2 - 3, title, size, tcls, weight=700, font=self.box_font, halo=False)
            self.text(cx, y + h / 2 + sub_size + 2, sub, sub_size, "t-soft", font=self.box_font, halo=False)
        else:
            self.text(cx, y + h / 2 + size * 0.35, title, size, tcls, weight=700, font=self.box_font, halo=False)

    def key(self, x: float, y: float, tone: ToneName, label: str, size: float = 13) -> float:
        """One color-key entry (swatch + label). Returns the x where the next one starts."""
        self.rect(x, y - 11, 14, 14, f"stroke-{tone}", o=1, fill_cls=f"fill-{tone}")
        self.text(x + 22, y, label, size, "t-soft", "start", rot=0, halo=False)
        return x + 22 + len(label) * size * 0.55 + 20

    def svg(self, inline: bool = False, palette: PaletteName = "auto") -> str:
        """inline=True styles every element itself (no <style>, no site CSS needed);
        use it for Markdown read outside the blog, such as in Obsidian. `palette`
        picks a PALETTES entry for inline mode; "paper" also draws its own card."""
        tid = "sk-" + hashlib.sha1(self.title.encode()).hexdigest()[:8]
        body = "".join(self.out)
        font = ""
        if inline:
            body, surf = _inline(body, palette)
            head = ""
            if palette == "paper":
                head = f'<rect width="{self.w}" height="{self.h}" rx="12" style="fill:{surf}"/>'
                font = f'font-family="{FONTS["hand"]}" '
        else:
            used: list[ToneName] = [n for n in TONES if f"-{n}\"" in body]
            head = _tone_style(used) if used else ""
        if self.clean:
            font = "font-family=\"Inter, 'Segoe UI', system-ui, -apple-system, sans-serif\" "
        return (
            f'<svg viewBox="0 0 {self.w} {self.h}" xmlns="http://www.w3.org/2000/svg" role="img" {font}'
            f'aria-labelledby="{tid}"><title id="{tid}">{escape(self.title)}</title>'
            + head
            + body
            + "</svg>"
        )


def figure(sketch_id: str, svg: str, caption: str) -> str:
    """The Markdown-embeddable block. `data-sketch` lets the inserter replace it later."""
    return (
        f'<figure class="sketch not-prose" data-sketch="{sketch_id}">\n{svg}\n'
        f"<figcaption>{escape(caption)}</figcaption>\n</figure>"
    )


def insert(md: str, sketch_id: str, block: str, after: str) -> str:
    """Insert `block` after the first line containing `after`, or replace an
    existing figure with the same id. Idempotent, so it can be re-run."""
    pat = re.compile(
        r'<figure class="sketch not-prose" data-sketch="' + re.escape(sketch_id) + r'">.*?</figure>', re.DOTALL
    )
    if pat.search(md):
        return pat.sub(lambda m: block, md, count=1)
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if after in line:
            lines[i + 1 : i + 1] = ["", block, ""]
            return "\n".join(lines)
    raise ValueError(f"{sketch_id}: anchor not found: {after!r}")
