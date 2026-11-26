"""The agent-facing surface: the guide's examples, the generated API, the checker and the CLI."""

import pathlib
import re
from typing import Any

import pytest

import penflow
from penflow import (
    Arrow,
    Box,
    Col,
    Diagram,
    Doc,
    Issue,
    Label,
    Overlay,
    Region,
    Row,
    flow,
)
from penflow.cli import main
from penflow.reference import SECTIONS, api
from penflow.resources import guide

BLOCKS = re.findall(r"```python\n(.*?)```", guide(), re.S)


def codes(d: Diagram) -> list[str]:
    return [i.code for i in d.check()]


# ---------------------------------------------------------------- guide
def test_guide_has_examples() -> None:
    assert len(BLOCKS) >= 6


@pytest.mark.parametrize("i", range(len(BLOCKS)))
def test_every_guide_example_runs_and_checks_clean(i: int) -> None:
    ns: dict[str, Any] = {}
    exec(BLOCKS[i], ns)  # noqa: S102  (our own docs)
    d = ns.get("d")
    if isinstance(d, Diagram):
        problems = [i for i in d.check() if i.level != "info"]
        assert not problems, "\n".join(map(str, problems))
        d.svg()


SKETCHES = re.findall(r"```penflow\n(.*?)```", guide(), re.S)


def test_guide_has_sketch_examples() -> None:
    assert len(SKETCHES) >= 5


@pytest.mark.parametrize("i", range(len(SKETCHES)))
def test_every_guide_sketch_parses_and_checks_clean(i: int) -> None:
    s = penflow.parse_sketch(SKETCHES[i])
    problems = [x for x in s.diagram.check(meanings=s.settings.meanings) if x.level != "info"]
    assert not problems, "\n".join(map(str, problems))
    s.diagram.svg(meanings=s.settings.meanings)


def test_skill_fence_example_parses_and_checks_clean() -> None:
    from penflow.resources import skill

    (block,) = re.findall(r"```penflow\n(.*?)```", skill(), re.S)
    s = penflow.parse_sketch(block)
    assert [x for x in s.diagram.check() if x.level != "info"] == []


def test_guide_mentions_every_check_code() -> None:
    text = guide()
    from typing import get_args

    from penflow.lint import Code

    for code in get_args(Code):
        if code not in ("no-title", "no-headline", "too-many-tones", "crowded"):
            assert f"`{code}`" in text, code


# ---------------------------------------------------------------- api
def test_api_lists_every_public_callable() -> None:
    """Every class and function penflow defines and exports appears in `python -m penflow api`."""
    import inspect

    listed = {n for names in SECTIONS.values() for n in names}
    base_classes = {"Node", "Edge", "LaneRow", "Rendered"}
    public = {n for n in penflow.__all__
              if (inspect.isclass(obj := getattr(penflow, n)) or inspect.isfunction(obj))
              and getattr(obj, "__module__", "").startswith("penflow")}
    assert public - base_classes <= listed, public - base_classes - listed


def test_api_text_is_readable() -> None:
    text = api()
    assert "Box(title: str, sub: str | None = None" in text
    assert "Align = 'start' | 'center' | 'end' | 'stretch'" in text
    assert "'Child'" not in text and "(self" not in text


# ---------------------------------------------------------------- checks
def test_clean_diagram_has_no_problems() -> None:
    a, b = Box("a"), Box("b")
    d = Diagram(Row(a, b, gap=90), edges=[Arrow(a, b, "go")], headline="h", title="t")
    assert d.check() == []


def test_overlap() -> None:
    assert "overlap" in codes(Diagram(Row(Box("a"), Box("b"), gap=-30), title="t", headline="h"))


def test_overlay_children_may_overlap() -> None:
    assert "overlap" not in codes(Diagram(Overlay(Box("a"), Label("b")), title="t", headline="h"))


def test_edge_crosses() -> None:
    a, mid, b = Box("a"), Box("middle"), Box("b")
    assert "edge-crosses" in codes(Diagram(Row(a, mid, b), edges=[Arrow(a, b)], title="t", headline="h"))


def test_edge_into_a_container_is_not_a_crossing() -> None:
    inner, src = Box("inner"), Box("src")
    zone = Region("zone", inner)
    d = Diagram(Row(src, zone, gap=60), edges=[Arrow(src, zone)], title="t", headline="h")
    assert "edge-crosses" not in codes(d)


def test_edge_overlap_and_the_port_fix() -> None:
    a, b = Box("a"), Box("b")
    bad = Diagram(Row(a, b, gap=100), edges=[Arrow(a, b), Arrow(b, a)], title="t", headline="h")
    assert "edge-overlap" in codes(bad)
    a, b = Box("a"), Box("b")
    good = Diagram(Row(a, b, gap=100), edges=[Arrow(a.at(1, 0.3), b.at(0, 0.3)), Arrow(b.at(0, 0.7), a.at(1, 0.7))],
                   title="t", headline="h")
    assert "edge-overlap" not in codes(good)


def test_label_overlap_and_flow_fix() -> None:
    a, b = Box("a"), Box("b")
    bad = Diagram(Row(a, b, gap=30), edges=[Arrow(a, b, "a long label here")], title="t", headline="h")
    assert "label-overlap" in codes(bad)
    good = Diagram(flow("a", "b", labels=["a long label here"]), title="t", headline="h")
    assert "label-overlap" not in codes(good)


def test_text_overflow() -> None:
    assert "text-overflow" in codes(Diagram(Box("a very long title").fixed(w=60), title="t", headline="h"))


def test_too_wide() -> None:
    assert "too-wide" in codes(Diagram(Row(*[Box(f"box {i}") for i in range(8)]), title="t", headline="h"))


def test_too_many_tones_and_crowded() -> None:
    tones = ["good", "bad", "wait", "normal", "accent"]
    d = Diagram(Col(*[Row(*[Box(f"{r}{c}").tone(tones[c]) for c in range(5)], gap=8) for r in range(4)], gap=8),
                width=None, title="t", headline="h")
    found = codes(d)
    assert "crowded" in found
    d2 = Diagram(Row(*[Box(m).tone(m) for m in ["good", "bad", "wait", "normal", "x"]]),
                 width=None, title="t", headline="h")
    assert "too-many-tones" in d2.check(meanings={"x": "cyan"}).__repr__()


def test_missing_title_and_headline_are_info() -> None:
    issues = Diagram(Box("a")).check()
    assert {(i.level, i.code) for i in issues} == {("info", "no-title"), ("info", "no-headline")}


def test_issue_reads_well() -> None:
    i = Issue("error", "overlap", "A overlaps B", "add gap")
    assert str(i) == "error overlap: A overlaps B\n      fix: add gap"


# ---------------------------------------------------------------- cli
def _script(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    (tmp_path / "post.md").write_text("<!-- sketch: x -->\n", encoding="utf-8")
    script = tmp_path / "diagrams.py"
    script.write_text(
        "import pathlib\nfrom penflow import *\n"
        "doc = Doc(pathlib.Path(__file__).parent / 'post.md')\n"
        "@doc.diagram('x', 'cap')\n"
        f"def x() -> Diagram:\n    {body}\n"
        "if __name__ == '__main__':\n    raise SystemExit('the check must not run the main block')\n",
        encoding="utf-8")
    return script


def test_cli_check_passes_clean_script(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    script = _script(tmp_path, "return Diagram(flow('a', 'b'), headline='h', title='t')")
    assert main(["check", str(script), "--gallery", str(tmp_path / "g.html")]) == 0
    out = capsys.readouterr().out
    assert "0 error(s)" in out and (tmp_path / "g.html").exists()
    assert "data-sketch" not in (tmp_path / "post.md").read_text(encoding="utf-8")  # nothing written


def test_cli_check_fails_on_errors(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    script = _script(tmp_path, "a, b, c = Box('a'), Box('b'), Box('c')\n"
                               "    return Diagram(Row(a, b, c), edges=[Arrow(a, c)], headline='h', title='t')")
    assert main(["check", str(script)]) == 1
    assert "edge-crosses" in capsys.readouterr().out


def test_cli_strict_fails_on_warnings(tmp_path: pathlib.Path) -> None:
    script = _script(tmp_path, "return Diagram(Box('long title').fixed(w=40), headline='h', title='t')")
    assert main(["check", str(script)]) == 0
    assert main(["check", str(script), "--strict"]) == 1


def test_cli_guide_and_api(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["guide"]) == 0
    assert "## The loop" in capsys.readouterr().out
    assert main(["api"]) == 0
    assert "## Ideas" in capsys.readouterr().out


def test_doc_check_and_run_flag(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "p.md"
    md.write_text("<!-- sketch: a -->\n", encoding="utf-8")
    doc = Doc(md)
    doc.diagram("a", "cap")(lambda: Diagram(Box("x").fixed(w=10), headline="h", title="t"))
    assert [i.code for _, i in doc.check()] == ["text-overflow"]
    penflow.run(doc, argv=["--check", "--no-write"])
    assert "text-overflow" in capsys.readouterr().out


# ---------------------------------------------------------------- skill
def test_skill_has_frontmatter_and_uses_real_commands() -> None:
    from penflow.resources import skill

    text = skill()
    assert text.startswith("---\nname: penflow-diagrams\ndescription: ")
    for cmd in re.findall(r"python -m penflow (\w+)", text):
        assert cmd in {"guide", "api", "check", "render", "convert", "skill"}, cmd


def test_skill_install_refuses_to_clobber_edits(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "penflow-diagrams" / "SKILL.md"
    assert main(["skill", "--install", str(tmp_path)]) == 0
    assert main(["skill", "--install", str(tmp_path)]) == 0  # same content: fine
    target.write_text("my edits", encoding="utf-8")
    assert main(["skill", "--install", str(tmp_path)]) == 1
    assert target.read_text(encoding="utf-8") == "my edits"
    assert main(["skill", "--install", str(tmp_path), "--force"]) == 0
    assert target.read_text(encoding="utf-8").startswith("---")
    capsys.readouterr()
