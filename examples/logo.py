"""The Penflow logo, drawn with Penflow.

    uv run python examples/logo.py
"""

import itertools
import math
import pathlib

from penflow import Canvas, Col, Diagram, Free, Label, Point, Row

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
TAGLINE = "hand-drawn diagrams from code"


def qbez(p0: Point, p1: Point, p2: Point, n: int = 16) -> list[Point]:
    """Points along a quadratic curve, so the pen can draw it in short strokes."""
    out: list[Point] = []
    for i in range(n + 1):
        t = i / n
        out.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]))
    return out


def head(cv: Canvas, a: Point, b: Point, size: float = 14) -> None:
    """An arrowhead at b, pointing the way the curve is going."""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for side in (-1, 1):
        turn = ang + math.pi - side * math.radians(26)
        cv.line(*b, b[0] + math.cos(turn) * size, b[1] + math.sin(turn) * size, "stroke-accent",
                rough=0.4, passes=1)


def mark(cv: Canvas, x: float, y: float) -> None:
    """The symbol: a yellow box and a teal circle, joined by a blue swoosh."""
    cv.rect(x + 10, y + 80, 34, 32, "stroke", o=2, fill_cls="fill-rust")
    cv.circle(x + 104, y + 30, 18, "stroke", fill_cls="fill-cyan")
    pts = qbez((x + 42, y + 88), (x + 74, y + 84), (x + 88, y + 46))
    for a, b in itertools.pairwise(pts):
        cv.line(*a, *b, "stroke-accent", rough=0.55, passes=2)
    head(cv, pts[-2], pts[-1], size=15)


def lockup() -> Diagram:
    return Diagram(
        Row(
            Free(128, 128, mark),
            Col(Label("penflow", size=76, bold=True), Label(TAGLINE, size=18, tone="cyan"), gap=4,
                align="start"),
            gap=24,
            align="center",
        ),
        width=None,
        margin=26,
        seed=11,
        title=f"penflow: {TAGLINE}",
    )


def square() -> Diagram:
    return Diagram(
        Free(128, 128, mark),
        width=None,
        margin=18,
        seed=11,
        title="penflow",
    )


def restyle(svg: str, **palette: str) -> str:
    """Set the inline paper palette, e.g. `cyan_bg="#8edbe5"`; underscores become dashes."""
    decls = "".join(f"--sk-{name.replace('_', '-')}:{value};" for name, value in palette.items())
    head_, sep, rest = svg.partition(">")
    return f"{head_}{sep}<style>:root{{{decls}}}</style>{rest}"


def main() -> None:
    full = lockup()
    icon = square()
    for d in (full, icon):
        # A logo has no takeaway line, so the only expected warning is "no-headline".
        errors = [i for i in d.check() if i.level == "error"]
        assert not errors, errors

    full_svg = full.svg(theme="paper")
    icon_svg = icon.svg(theme="paper")
    light = restyle(full_svg, cyan_bg="#8edbe5")
    icon_light = restyle(icon_svg, cyan_bg="#8edbe5")
    dark = restyle(full_svg, ink="#f2efe6", soft="#9aa4b2", accent="#7c9bff",
                   surface="#1b1e24", cyan_bg="#1f7f8c", cyan_text="#48c9d9")
    icon_dark = restyle(icon_svg, ink="#f2efe6", soft="#9aa4b2", accent="#7c9bff",
                        surface="#1b1e24", cyan_bg="#1f7f8c", cyan_text="#48c9d9")

    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "logo.svg").write_text(light, encoding="utf-8")
    (ASSETS / "logo-mark.svg").write_text(icon_light, encoding="utf-8")
    (ASSETS / "logo-dark.svg").write_text(dark, encoding="utf-8")
    (ASSETS / "logo-mark-dark.svg").write_text(icon_dark, encoding="utf-8")


if __name__ == "__main__":
    main()
