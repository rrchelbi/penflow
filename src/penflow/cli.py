"""python -m penflow <command>

  guide              how to draw good diagrams with Penflow (written for agents and people)
  api                every public name with its signature, generated from the code
  check FILE         lay out every diagram in a script, or every ```penflow fence in a .md file,
                     and report layout problems (--strict: fail on warnings too; --gallery FILE)
  render FILE.md     draw every ```penflow fence and put each figure right after its fence
                     (takes a diagrams script's flags: --no-write, --gallery, --preview, ...)
  convert FILE       Mermaid in, Penflow out: a .mmd file, or every ```mermaid fence in a .md file
                     (--write: replace the .md file's mermaid fences with penflow fences)
  skill              print the Claude Code skill (--install [DIR]: write it to DIR/penflow-diagrams/SKILL.md)

check and render take --mermaid to draw ```mermaid fences as they are, converted on the fly.
"""

from __future__ import annotations

import argparse
import pathlib
import runpy
import sys
from collections.abc import Sequence

from .dsl import SketchDoc, SketchError, fences
from .mermaid import convert_mermaid
from .publish import Doc, Rendered, gallery, report, run
from .reference import api
from .resources import guide, install_skill, skill

MARKDOWN = (".md", ".markdown")


def check(path: pathlib.Path, strict: bool = False, gallery_path: pathlib.Path | None = None,
          mermaid: bool = False) -> int:
    """Check every Doc a diagrams script defines, or every fence in a Markdown file."""
    try:
        docs = _load(path, mermaid)
    except SketchError as e:
        print(e)
        return 2
    if not docs:
        print(f"{path}: no Doc found (define one at module level: doc = Doc('post.md'))")
        return 2
    errors = warnings = 0
    rendered: list[Rendered] = []
    for doc in docs:
        issues = doc.check()
        errors += report(issues, doc.path.name)
        warnings += sum(i.level == "warn" for _, i in issues)
        if gallery_path:
            rendered += doc.render()
    if gallery_path:
        print("gallery:", gallery(rendered, gallery_path, title=f"check: {path.name}"))
    print(f"{sum(len(d.diagrams) for d in docs)} diagram(s): {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (strict and warnings) else 0


def render(path: pathlib.Path, flags: Sequence[str]) -> int:
    """Draw a Markdown file's fences into it; `flags` are run()'s, plus --mermaid."""
    rest = [f for f in flags if f != "--mermaid"]
    try:
        doc = SketchDoc(path, mermaid=len(rest) != len(flags))
    except SketchError as e:
        print(e)
        return 2
    run(doc, argv=rest)
    return 0


def convert(path: pathlib.Path, write: bool = False) -> int:
    """Print the Penflow version of a Mermaid file, or of each ```mermaid fence in a Markdown file.
    With `write`, replace the Markdown file's fences instead."""
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    md = raw.replace("\r\n", "\n")
    if path.suffix.lower() not in MARKDOWN:
        if write:
            print("--write replaces ```mermaid fences in a .md file; for a Mermaid file, redirect the output")
            return 2
        try:
            print(convert_mermaid(md).text, end="")
        except SketchError as e:
            print(e.at(str(path)))
            return 2
        return 0

    found = fences(md, ("mermaid",))
    if not found:
        print(f"{path}: no ```mermaid fences")
        return 2
    lines = md.split("\n")
    blocks: list[str] = []
    notes: list[str] = []
    for f in reversed(found):  # bottom up, so earlier fences keep their line numbers
        try:
            conv = convert_mermaid(f.body)
        except SketchError as e:
            print(SketchError(e.line + f.open + 1, e.message, str(path)))
            return 2
        fence = ["```penflow", *conv.text.rstrip("\n").split("\n"), "```"]
        lines[f.open:f.close + 1] = fence
        blocks.insert(0, "\n".join(fence))
        notes[:0] = [f"{path}:{f.open + 1}: note: {n}" for n in conv.notes]
    for n in notes:
        print(n)
    if write:
        out = "\n".join(lines)
        path.write_bytes((out.replace("\n", "\r\n") if crlf else out).encode("utf-8"))
        print(f"{path}: {len(found)} mermaid fence(s) replaced with penflow fences")
    else:
        print("\n\n".join(blocks))
    return 0


def print_skill(install: pathlib.Path | None, force: bool) -> int:
    if install is None:
        print(skill(), end="")
        return 0
    try:
        print("installed:", install_skill(install, force))
    except FileExistsError as e:
        print(e)
        return 1
    return 0


def _load(path: pathlib.Path, mermaid: bool = False) -> list[Doc]:
    """A Markdown file's fences, or the Docs a diagrams script defines (run without its __main__ block)."""
    if path.suffix.lower() in MARKDOWN:
        return [SketchDoc(path, mermaid=mermaid)]
    sys.path.insert(0, str(path.resolve().parent))
    ns = runpy.run_path(str(path), run_name="__penflow_check__")
    return [v for v in ns.values() if isinstance(v, Doc)]


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m penflow", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("guide", help="print the guide")
    sub.add_parser("api", help="print the generated API reference")
    c = sub.add_parser("check", help="check every diagram in a script or a .md file")
    c.add_argument("file", type=pathlib.Path)
    c.add_argument("--strict", action="store_true", help="fail on warnings too")
    c.add_argument("--gallery", type=pathlib.Path, help="also write an HTML page with the diagrams")
    c.add_argument("--mermaid", action="store_true", help="also draw ```mermaid fences in a .md file")
    r = sub.add_parser("render", help="draw the fences of a Markdown file into it")
    r.add_argument("file", type=pathlib.Path)
    r.add_argument("flags", nargs=argparse.REMAINDER,
                   help="--no-write, --gallery FILE, --preview DIR, --clean, --theme T, --check, --mermaid")
    v = sub.add_parser("convert", help="convert Mermaid to Penflow")
    v.add_argument("file", type=pathlib.Path)
    v.add_argument("--write", action="store_true", help="replace the mermaid fences of a .md file")
    k = sub.add_parser("skill", help="print or install the Claude Code skill")
    k.add_argument("--install", nargs="?", const=pathlib.Path(".claude/skills"), type=pathlib.Path, metavar="DIR",
                   help="write it under DIR (default: .claude/skills in the current folder)")
    k.add_argument("--force", action="store_true", help="replace an installed copy that differs")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")  # labels use ①, → and curly quotes, which cp1252 consoles can't print
    a = _parser().parse_args(argv)
    if a.cmd == "guide":
        print(guide(), end="")
        return 0
    if a.cmd == "api":
        print(api(), end="")
        return 0
    if a.cmd == "skill":
        return print_skill(a.install, a.force)
    if a.cmd == "convert":
        return convert(a.file, a.write)
    if a.cmd == "render":
        return render(a.file, a.flags)
    return check(a.file, a.strict, a.gallery, a.mermaid)
