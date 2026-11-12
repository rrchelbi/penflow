"""Put diagrams into Markdown posts.

    doc = Doc("posts/raft.md", theme="paper", meanings={...})

    @doc.diagram("fencing", "A lease can't stop a paused client.")
    def fencing() -> Diagram:
        return Diagram(...)

    if __name__ == "__main__":
        run(doc)

Each diagram goes after the line containing its anchor (default
`<!-- sketch: <id> -->`), or replaces the figure it inserted last time, so
the script can be re-run after editing. Builders may also return a core
Canvas for hand-placed drawings.
"""

from __future__ import annotations

import argparse
import html
import os
import pathlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import NamedTuple, TypeAlias, TypeVar

from .core import Canvas, FontName, escape, figure, insert
from .lint import Issue
from .nodes import Diagram, MeaningSpec, Style, Theme

Drawing: TypeAlias = Diagram | Canvas
Builder: TypeAlias = Callable[[], Drawing]
B = TypeVar("B", bound=Builder)


class Rendered(NamedTuple):
    id: str
    caption: str
    anchor: str
    svg: str


class Entry(NamedTuple):
    id: str
    caption: str
    anchor: str
    build: Builder


def to_svg(drawing: Drawing, style: Style = "hand", theme: Theme = "paper",
           meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None) -> str:
    if isinstance(drawing, Diagram):
        return drawing.svg(style, theme, meanings, box_font)
    if style == "clean" and not drawing.clean:
        raise ValueError("a hand-placed Canvas fixes its own style; pass clean=True when creating it")
    return drawing.svg() if theme == "blog" else drawing.svg(inline=True, palette=theme)


class Doc:
    """One Markdown file and the diagrams that go into it."""

    def __init__(self, path: str | os.PathLike[str], *, style: Style = "hand", theme: Theme = "paper",
                 meanings: Mapping[str, MeaningSpec] | None = None, box_font: FontName | None = None,
                 anchor: str = "<!-- sketch: {id} -->") -> None:
        self.path = pathlib.Path(path)
        self.style: Style = style
        self.theme: Theme = theme
        self.meanings = meanings
        self.box_font: FontName | None = box_font
        self.anchor = anchor
        self.diagrams: list[Entry] = []

    def diagram(self, sid: str, caption: str, anchor: str | None = None) -> Callable[[B], B]:
        """Register a builder. The decorated function is returned unchanged."""
        if any(d.id == sid for d in self.diagrams):
            raise ValueError(f"duplicate diagram id {sid!r} in {self.path}")

        def wrap(fn: B) -> B:
            self.diagrams.append(Entry(sid, caption, anchor or self.anchor.format(id=sid), fn))
            return fn

        return wrap

    def render(self, style: Style | None = None, theme: Theme | None = None) -> list[Rendered]:
        """Every diagram as SVG, with this doc's settings unless overridden."""
        st, th = style or self.style, theme or self.theme
        return [Rendered(e.id, e.caption, e.anchor, to_svg(e.build(), st, th, self.meanings, self.box_font))
                for e in self.diagrams]

    def check(self, style: Style | None = None, theme: Theme | None = None) -> list[tuple[str, Issue]]:
        """Run Diagram.check on every diagram: [(diagram id, issue)]. Hand-drawn
        Canvas builders are skipped (they have no layout to check)."""
        st, th = style or self.style, theme or self.theme
        out: list[tuple[str, Issue]] = []
        for e in self.diagrams:
            drawing = e.build()
            if isinstance(drawing, Diagram):
                out += [(e.id, i) for i in drawing.check(st, th, self.meanings, self.box_font)]
        return out

    def build(self, rendered: Sequence[Rendered] | None = None, write: bool = True) -> str:
        """Insert the figures into the file, keeping its line endings. Returns the new text."""
        items = self.render() if rendered is None else rendered
        raw = self.path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        md = raw.replace("\r\n", "\n")
        for r in items:
            md = insert(md, r.id, figure(r.id, r.svg, r.caption), r.anchor)
        if write:
            self.path.write_bytes((md.replace("\n", "\r\n") if crlf else md).encode("utf-8"))
        return md


def gallery(items: Iterable[Rendered], path: str | os.PathLike[str], title: str = "sketchkit gallery") -> pathlib.Path:
    """Write one HTML page with every diagram, for reviewing them together."""
    figs = "\n".join(
        f'<figure id="{html.escape(r.id)}"><div class="art">{r.svg}</div>'
        f"<figcaption><code>{html.escape(r.id)}</code> {escape(r.caption)}</figcaption></figure>"
        for r in items)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#f4f2ee;--ink:#1e1e1e;--muted:#5f6b76}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--ink:#e6e6e6;--muted:#9aa4b0}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:24px 16px}}
figure{{margin:0 0 40px}} .art svg{{width:100%;height:auto;display:block}}
figcaption{{color:var(--muted);margin-top:8px}} code{{color:var(--ink)}}
</style></head><body><main><h1>{html.escape(title)}</h1>
{figs}
</main></body></html>"""
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


class _Args(argparse.Namespace):
    preview: pathlib.Path | None
    gallery: pathlib.Path | None
    no_write: bool
    clean: bool
    check: bool
    theme: Theme | None


def run(*docs: Doc, argv: Sequence[str] | None = None) -> None:
    """Command line for a diagrams script:
      --preview DIR    also write each SVG to DIR
      --gallery FILE   also write an HTML page with every diagram
      --no-write       don't touch the Markdown files
      --clean          straight lines instead of the pen look
      --theme T        paper, auto or blog (default: each doc's own)
      --check          also report layout problems (see Diagram.check)
    """
    ap = argparse.ArgumentParser(description="Render diagrams into Markdown posts.")
    ap.add_argument("--preview", type=pathlib.Path)
    ap.add_argument("--gallery", type=pathlib.Path)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--theme", choices=["paper", "auto", "blog"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv, namespace=_Args())
    every: list[Rendered] = []
    for doc in docs:
        rendered = doc.render(style="clean" if a.clean else None, theme=a.theme)
        if a.preview:
            a.preview.mkdir(parents=True, exist_ok=True)
            for r in rendered:
                (a.preview / f"{r.id}.svg").write_text(r.svg, encoding="utf-8", newline="\n")
        every += rendered
        if a.check:
            report(doc.check(style="clean" if a.clean else None, theme=a.theme), doc.path.name)
        if not a.no_write:
            doc.build(rendered)
            print(f"{doc.path}: {len(rendered)} diagram(s)")
    if a.gallery:
        print("gallery:", gallery(every, a.gallery))


def report(issues: Sequence[tuple[str, Issue]], where: str = "") -> int:
    """Print issues grouped by diagram; returns how many are errors."""
    prefix = f"{where}: " if where else ""
    if not issues:
        print(f"{prefix}no layout issues")
        return 0
    current = None
    for sid, issue in issues:
        if sid != current:
            print(f"{prefix}{sid}")
            current = sid
        print("  " + str(issue).replace("\n", "\n  "))
    return sum(i.level == "error" for _, i in issues)
