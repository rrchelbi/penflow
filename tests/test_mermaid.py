"""Mermaid in, Penflow out: what converts, what's approximated (and said so), and what's refused."""

import pathlib
import re

import pytest

from penflow import Box, Circle, Col, Diagram, Lanes, Msg, Row, Track, convert_mermaid, parse_sketch
from penflow.cli import main
from penflow.dsl import SketchDoc, SketchError


def body(mermaid: str) -> list[str]:
    """The converted lines, without the %% notes."""
    return [ln for ln in convert_mermaid(mermaid).text.splitlines() if not ln.startswith("%%")]


def draw(mermaid: str) -> Diagram:
    conv = convert_mermaid(mermaid)
    return parse_sketch(conv.text, line_numbers=conv.lines).diagram


# ---------------------------------------------------------------- flowchart
def test_flowchart_reads_like_the_mermaid_it_came_from() -> None:
    assert body("flowchart LR\n  A[Client] -->|HTTPS| B[Server]\n  B --> C\n") == [
        "flow lr",
        "  a[Client] -->|HTTPS| b[Server]",
        "  b --> c[C]",
    ]


def test_shapes_become_boxes_and_circles_and_say_so() -> None:
    conv = convert_mermaid("graph TD\n  a{Healthy?} --> b[(DB)]\n  b --> c((hub))\n")
    assert "  a[Healthy?] --> b[DB]" in conv.text and "  b --> c((hub))" in conv.text
    assert "decision shapes drawn as boxes" in conv.notes and "cylinder shapes drawn as boxes" in conv.notes
    d = draw("graph TD\n  a{Healthy?} --> b[(DB)]\n  b --> c((hub))\n")
    assert isinstance(d.body, Col) and isinstance(d.body.items[2], Circle)


@pytest.mark.parametrize(("link", "arrow", "label"), [
    ("-->", "-->", None), ("---", "---", None), ("-.->", "-.->", None), ("-.-", "-.-", None),
    ("==>", "-->", None), ("-->|yes|", "-->", "yes"), ("-- yes -->", "-->", "yes"),
    ("-. maybe .->", "-.->", "maybe"), ("== go ==>", "-->", "go"), ("--->", "-->", None),
])
def test_links(link: str, arrow: str, label: str | None) -> None:
    lab = f"|{label}|" if label else ""
    assert body(f"flowchart LR\n  a {link} b\n") == ["flow lr", f"  a {arrow}{lab} b"]


def test_ampersands_and_chains_expand_to_edges() -> None:
    assert body("graph LR\n  a & b --> c --> d\n") == ["flow lr", "  a --> c", "  b --> c", "  c --> d"]


def test_classes_become_meanings_with_a_tone_from_their_colour() -> None:
    conv = convert_mermaid("graph LR\n  a:::hot --> b\n  class b cold\n  classDef hot fill:#f96\n"
                           "  classDef cold fill:#9cf\n")
    assert "meanings: {hot: orange, cold: cyan}" in conv.text
    assert "  a:::hot --> b:::cold" in conv.text
    s = parse_sketch(conv.text)
    s.diagram.svg(meanings=s.settings.meanings)


def test_ids_become_snake_case_keep_their_text_and_avoid_keywords() -> None:
    lines = body("graph LR\n  userAPI --> row\n  row --> 2fa\n")
    assert lines == ["flow lr", "  user_api[userAPI] --> row_node[row]", "  row_node --> n_2fa[2fa]"]


def test_text_that_means_something_in_the_dsl_is_quoted() -> None:
    d = draw('graph LR\n  a["x | y"] -->|"a|b"| b["50%% off"]\n')
    assert isinstance(d.body, Row)
    a, b = d.body.items
    assert isinstance(a, Box) and a.title == "x | y" and a.sub is None
    assert isinstance(b, Box) and b.title == "50%% off"


def test_br_starts_the_second_line_of_a_box() -> None:
    d = draw("graph LR\n  a[exec.bpf.o<br/>bytecode] --> b\n")
    assert isinstance(d.body, Row)
    a = d.body.items[0]
    assert isinstance(a, Box) and (a.title, a.sub) == ("exec.bpf.o", "bytecode")


def test_subgraphs_become_regions_ordered_by_their_edges() -> None:
    lines = body("flowchart LR\n  w\n  subgraph back [Server]\n    api --> db\n  end\n"
                 "  subgraph front [Browser]\n    ui --> st\n  end\n  ui --> api\n  db --> w\n")
    assert lines == [
        "row {gap: 40}",
        "  region Browser",
        "    flow td",
        "      ui --> st",
        "  region Server",
        "    flow td",
        "      api --> db",
        "  flow lr",
        "    w",
        "ui --> api",
        "db --> w",
    ]
    d = draw("flowchart LR\n  w\n  subgraph back [Server]\n    api --> db\n  end\n"
             "  subgraph front [Browser]\n    ui --> st\n  end\n  ui --> api\n  db --> w\n")
    assert [i for i in d.check() if i.level == "error"] == []


def test_a_subgraph_direction_is_kept() -> None:
    assert body("flowchart TD\n  subgraph s\n    direction LR\n    a --> b\n  end\n") == [
        "region s", "  flow lr", "    a --> b"]


def test_dropped_things_are_listed_as_comments_too() -> None:
    conv = convert_mermaid("graph LR\n  a --> b\n  style a fill:#f00\n  linkStyle 0 stroke:red\n  click a cb\n")
    assert len(conv.notes) == 3
    assert all(f"%% converted from Mermaid: {n}" in conv.text for n in conv.notes)


def test_mermaid_front_matter_title_becomes_the_headline() -> None:
    conv = convert_mermaid("---\ntitle: CI: the pipeline\nconfig:\n  theme: dark\n---\ngraph LR\n  a --> b\n")
    assert 'headline: "CI: the pipeline"' in conv.text and "front matter 'config' dropped" in conv.notes
    assert draw("---\ntitle: CI: the pipeline\n---\ngraph LR\n  a --> b\n").headline == "CI: the pipeline"


def test_semicolons_separate_statements() -> None:
    assert body("graph LR; a --> b; b --> c") == ["flow lr", "  a --> b", "  b --> c"]


# ---------------------------------------------------------------- sequenceDiagram
SEQ = """sequenceDiagram
    autonumber
    participant C as Client
    participant S as Auth server
    C->>+S: login
    Note over S,C: checks
    loop every hour
        C->>S: refresh
    end
    S-->>-C: token
    C-xS: rejected
"""


def test_sequence_conversion() -> None:
    conv = convert_mermaid(SEQ)
    assert [ln for ln in conv.text.splitlines() if not ln.startswith("%%")] == [
        "sequence_diagram",
        "  participant c[Client]",
        "  participant s[Auth server]",
        '  note s: "" {bar: 5}',
        "  c ->> s: ① login",
        "  note s: checks",
        "  c ->> s: ② refresh",
        "  s ->> c: ③ token",
        "  c -x s: ④ rejected",
    ]
    assert "notes over several lanes sit beside the first one" in conv.notes
    assert "dashed messages drawn solid" in conv.notes


def test_sequence_draws() -> None:
    d = draw(SEQ)
    assert isinstance(d.body, Lanes) and d.body.names == ["Client", "Auth server"]
    last = d.body.rows[-1]
    assert isinstance(last, Msg) and last.mark == "cross"
    assert [i for i in d.check() if i.level == "error"] == []


def test_unbalanced_deactivate_is_an_error() -> None:
    with pytest.raises(SketchError, match="deactivate A without an activate"):
        convert_mermaid("sequenceDiagram\n  A->>B: hi\n  deactivate A\n")


# ---------------------------------------------------------------- timeline
def test_timeline_keeps_years_as_values() -> None:
    lines = body("timeline\n  title Releases\n  2021 : v1\n  2022 : v2 : plugins\n")
    assert lines[-3:] == ["timeline", "  2021: 2021\\nv1", "  2022: 2022\\nv2\\nplugins"]
    d = draw("timeline\n  2021 : v1\n  2022 : v2\n")
    assert isinstance(d.body, Track) and [e.value for e in d.body.events] == [2021, 2022]


def test_timeline_with_named_periods_spaces_them_evenly() -> None:
    conv = convert_mermaid("timeline\n  section Now\n  Q1 : discovery\n  Q2 : build\n       : test\n")
    assert "  0: Q1\\ndiscovery" in conv.text and "  1: Q2\\nbuild\\ntest" in conv.text
    assert "timeline sections dropped" in conv.notes


# ---------------------------------------------------------------- refused, with the closest block
@pytest.mark.parametrize(("src", "expect"), [
    ("gantt\n  title x\n", "Mermaid gantt isn't drawn by Penflow; the closest penflow block is timeline"),
    ("pie\n  \"a\" : 1\n", "closest penflow block is table"),
    ("stateDiagram-v2\n  [*] --> A\n", "flow (states as nodes, transitions as edges)"),
    ("bogus\n", "'bogus' isn't a Mermaid diagram type Penflow knows"),
    ("graph LR\n  subgraph s\n    a\n", "subgraph s has no 'end'"),
    ("graph LR\n  a --> b\n  end\n", "'end' without a subgraph"),
    ("", "the Mermaid text is empty"),
])
def test_refused(src: str, expect: str) -> None:
    with pytest.raises(SketchError, match=None) as e:
        convert_mermaid(src)
    assert expect in str(e.value)


# ---------------------------------------------------------------- Markdown files and the CLI
POST = """# post

```mermaid
graph LR
  a --> b
  b --> c
```

text
"""


def test_render_mermaid_fences_and_point_issues_at_the_mermaid(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text(POST.replace("  b --> c", "  a --> c\n  b --> c\n  c --> a"), encoding="utf-8")
    doc = SketchDoc(md, mermaid=True)
    assert [s.id for s in doc.sketches] == ["sketch_1"]
    doc.build()
    text = md.read_text(encoding="utf-8")
    assert text.index("```mermaid") < text.index('data-sketch="sketch_1"') < text.index("text")
    assert len(SketchDoc(md).sketches) == 0  # without the flag, mermaid fences are left alone


def test_conversion_errors_point_into_the_file(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text("# x\n\n```mermaid\ngantt\n  title x\n```\n", encoding="utf-8")
    with pytest.raises(SketchError) as e:
        SketchDoc(md, mermaid=True)
    assert str(e.value).endswith(":4: Mermaid gantt isn't drawn by Penflow; the closest penflow block is timeline")


def test_check_issues_name_mermaid_lines(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text("```mermaid\nflowchart LR\n  subgraph s\n    a --> b\n    a --> c\n  end\n  x --> b\n"
                  "  x --> c\n  c --> x\n```\n", encoding="utf-8")
    doc = SketchDoc(md, mermaid=True)
    for _, issue in doc.check():
        for n in re.findall(r"line (\d+)", issue.message):
            assert 2 <= int(n) <= 9  # inside the mermaid fence


def test_cli_convert_mmd(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "d.mmd"
    f.write_text("graph LR\n  A --> B\n", encoding="utf-8")
    assert main(["convert", str(f)]) == 0
    assert capsys.readouterr().out == "flow lr\n  a[A] --> b[B]\n"
    assert main(["convert", str(f), "--write"]) == 2


def test_cli_convert_write_replaces_fences(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "post.md"
    md.write_bytes(POST.replace("\n", "\r\n").encode("utf-8"))
    assert main(["convert", str(md)]) == 0
    assert "```penflow\nflow lr\n  a --> b" in capsys.readouterr().out
    assert "```mermaid" in md.read_text(encoding="utf-8")  # printing doesn't touch the file
    assert main(["convert", str(md), "--write"]) == 0
    raw = md.read_bytes().decode("utf-8")
    assert "```mermaid" not in raw and "```penflow\r\nflow lr\r\n" in raw
    assert len(SketchDoc(md).sketches) == 1


def test_cli_render_and_check_with_mermaid(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "post.md"
    md.write_text(POST, encoding="utf-8")
    assert main(["check", str(md), "--mermaid"]) == 0
    assert "1 diagram(s): 0 error(s)" in capsys.readouterr().out
    assert main(["render", str(md), "--mermaid", "--no-write"]) == 0
    assert main(["render", str(md), "--mermaid"]) == 0
    assert 'data-sketch="sketch_1"' in md.read_text(encoding="utf-8")


# ---------------------------------------------------------------- docs/mermaid.md stays true
DOC = (pathlib.Path(__file__).parent.parent / "docs" / "mermaid.md").read_text(encoding="utf-8")
PAIRS = re.findall(r"```mermaid\n(.*?)```\n\n```penflow\n(.*?)```", DOC, re.S)


def test_the_mermaid_page_has_examples() -> None:
    assert len(PAIRS) >= 5


@pytest.mark.parametrize("i", range(len(PAIRS)))
def test_each_sketch_on_the_mermaid_page_is_what_convert_prints(i: int) -> None:
    mermaid, sketch = PAIRS[i]
    assert convert_mermaid(mermaid).text == sketch
    s = parse_sketch(sketch)
    assert [x for x in s.diagram.check(meanings=s.settings.meanings) if x.level == "error"] == []


def test_self_messages_become_notes() -> None:
    conv = convert_mermaid("sequenceDiagram\n  A->>A: think\n  A->>B: hi\n")
    assert "  note a: think" in conv.text and "messages to self drawn as notes beside the lane" in conv.notes
    with pytest.raises(SketchError, match="for a's own step write note a: think"):
        parse_sketch("sequence_diagram\n  a ->> a: think\n")
