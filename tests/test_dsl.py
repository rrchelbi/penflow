"""Penflow: parsing, the nodes it builds, its errors, and Markdown files."""

import pathlib

import pytest

from penflow import (
    Act,
    Arrow,
    Box,
    Cell,
    Circle,
    Col,
    Diagram,
    Gap,
    Grid,
    Label,
    Lanes,
    Line,
    Msg,
    Pad,
    Port,
    Region,
    Row,
    Spacer,
    Split,
    Track,
    parse_sketch,
)
from penflow.cli import main
from penflow.dsl import SketchDoc, SketchError, fences, layers, snake


def body(src: str) -> Diagram:
    return parse_sketch(src).diagram


def err(src: str) -> str:
    with pytest.raises(SketchError) as e:
        parse_sketch(src)
    return str(e.value)


# ---------------------------------------------------------------- nodes and blocks
def test_bare_id_is_a_box_titled_with_spaces() -> None:
    d = body("ring_buffer\n")
    assert isinstance(d.body, Box) and d.body.title == "ring buffer" and d.body.sub is None


def test_shapes_and_second_line() -> None:
    d = body('col\n  a[exec.bpf.o | bytecode + BTF]\n  n1((N1))\n  t(open)\n  q["a | b"]\n')
    assert isinstance(d.body, Col)
    a, n1, t, q = d.body.items
    assert isinstance(a, Box) and (a.title, a.sub) == ("exec.bpf.o", "bytecode + BTF")
    assert isinstance(n1, Circle) and n1.text == "N1"
    assert isinstance(t, Cell) and t.text == "open"
    assert isinstance(q, Box) and q.title == "a | b" and q.sub is None


def test_tone_attrs_and_modifiers() -> None:
    d = body("col\n  h[L1 hears]:::attack {size: 13, dashed, w: 200, align: start}\n")
    assert isinstance(d.body, Col)
    h = d.body.items[0]
    assert isinstance(h, Box) and h.size == 13 and list(h.tones()) == ["attack"]
    assert h.origin == "h (line 2)"
    plain = body("col\n  h[L1 hears]:::attack {size: 13, w: 200, align: start}\n")
    assert d.svg(meanings={"attack": "slate"}) != plain.svg(meanings={"attack": "slate"})  # dashed
    d.layout(meanings={"attack": "slate"})
    assert h.rect[2] == 200
    assert h.rect[0] == d.body.rect[0]  # align: start


def test_layout_blocks_map_to_nodes() -> None:
    d = body("split {gap: 30, divider: false}\n"
             "  row {gap: 50, align: end}\n    a\n    b\n"
             "  pad {bottom: 46}\n    c\n"
             "  region one node {pad: 10}\n    d\n    e\n")
    sp = d.body
    assert isinstance(sp, Split) and sp.gap == 30 and not sp.divider
    row, pad, region = sp.items
    assert isinstance(row, Row) and row.gap == 50 and row.cross == "end"
    assert isinstance(pad, Pad) and pad.b == 46 and pad.t == 0
    assert isinstance(region, Region) and region.title == "one node" and region.p == 10
    assert isinstance(region.child, Col) and len(region.child.items) == 2


def test_grid_rows_and_empty_cells() -> None:
    d = body("grid {gap: 6}\n  | a | b[x | y] |\n  | | c:::bad |\n")
    g = d.body
    assert isinstance(g, Grid) and g.col_gap == 6
    assert g.rows[1][0] is None
    b = g.rows[0][1]
    assert isinstance(b, Box) and b.sub == "y"


def test_label_and_spacer() -> None:
    d = body('col\n  label round 2: “C said retreat” :::retreat {size: 13, bold}\n  spacer {h: 10}\n'
             '  label "x {y}" \n  label two\\nlines\n')
    assert isinstance(d.body, Col)
    lab, sp, quoted, two = d.body.items
    assert isinstance(lab, Label) and lab.text == "round 2: “C said retreat”" and lab.bold and lab.size == 13
    assert list(lab.tones()) == ["retreat"]
    assert isinstance(sp, Spacer)
    assert isinstance(quoted, Label) and quoted.text == "x {y}"
    assert isinstance(two, Label) and two.text == "two\nlines"


def test_several_top_level_nodes_become_a_col() -> None:
    d = body("a\nb\n")
    assert isinstance(d.body, Col) and len(d.body.items) == 2


def test_comments_and_blank_lines_are_ignored() -> None:
    d = body('%% a comment\nrow  %% trailing\n\n  a\n  b["50 %% off"]  %% the quoted %% is text\n')
    assert isinstance(d.body, Row) and len(d.body.items) == 2
    b = d.body.items[1]
    assert isinstance(b, Box) and b.title == "50 %% off"


# ---------------------------------------------------------------- edges
def test_edges_labels_styles_and_chains() -> None:
    d = body("row\n  a\n  b\n  c\na -->|load| b -.-> c :::bad {label_side: left}\nc --- a\nb -.- c\n")
    e1, e2, e3, e4 = d.edges
    assert isinstance(e1, Arrow) and e1.label == "load" and not e1.dashed and e1.tone == "bad"
    assert e1.label_side == "left"
    assert isinstance(e2, Arrow) and e2.dashed and e2.label is None and e2.tone == "bad"
    assert type(e3) is Line and not e3.dashed
    assert type(e4) is Line and e4.dashed


def test_edges_in_blocks_are_linked_to_the_block() -> None:
    d = body("row\n  a --> b\n")
    assert isinstance(d.body, Row) and len(d.body.items) == 2 and len(d.body.linked) == 1
    assert not d.edges


def test_edge_declares_new_nodes_in_place_and_forward_refs_work() -> None:
    d = body("col\n  row\n    x --> y\n  y2[later box]\nx --> y2\n")
    assert isinstance(d.body, Col)
    row, later = d.body.items
    assert isinstance(row, Row) and [n.title for n in row.items if isinstance(n, Box)] == ["x", "y"]
    assert isinstance(later, Box) and later.title == "later box"
    assert len(d.edges) == 1


def test_bare_mention_does_not_declare_when_the_id_is_declared_elsewhere() -> None:
    d = body("col\n  a --> b\n  b[the real b]\n")
    assert isinstance(d.body, Col)
    titles = [n.title for n in d.body.items if isinstance(n, Box)]
    assert titles == ["a", "the real b"]


def test_ports() -> None:
    d = body("row\n  a\n  b\na.bottom --> b.at(0.15, 1)\n")
    e = d.edges[0]
    assert isinstance(e, Arrow)
    assert isinstance(e.a, Port) and isinstance(e.b, Port)
    assert (e.a.fx, e.a.fy) == (0.5, 1)
    assert (e.b.fx, e.b.fy) == (0.15, 1)


# ---------------------------------------------------------------- front matter
def test_front_matter_sets_the_diagram_and_settings() -> None:
    s = parse_sketch('---\nid: fencing\ncaption: "a: b"\nheadline: h\nnote: n\nlegend: true\ntitle: t\n'
                     "width: none\nseed: 3\ntheme: auto\nmeanings: {loyal: cyan, traitor: orange}\n---\na\n")
    assert s.id == "fencing" and s.caption == "a: b"
    d = s.diagram
    assert (d.headline, d.note, d.legend, d.title, d.width, d.seed) == ("h", "n", True, "t", None, 3)
    assert s.settings.theme == "auto" and s.settings.meanings == {"loyal": "cyan", "traitor": "orange"}


def test_meanings_render_and_unknown_meaning_fails_at_render() -> None:
    s = parse_sketch("---\nmeanings: {loyal: cyan}\n---\na:::loyal\n")
    s.diagram.svg(meanings=s.settings.meanings)
    with pytest.raises(ValueError):
        parse_sketch("b:::nobody\n").diagram.svg()


# ---------------------------------------------------------------- errors say what to do
@pytest.mark.parametrize(("src", "expect"), [
    ("clientA --> b\n", "'clientA' isn't snake_case; write 'client_a'"),
    ("sequenceDiagram\n", "write 'sequence_diagram'"),
    ("subgraph x\n", "'subgraph' is Mermaid syntax; write 'region <title>'"),
    ("row\n  a\nend\n", "remove 'end'"),
    ("row {gpa: 2}\n  a\n", "unknown attribute 'gpa' for row; its attributes are: align"),
    ("row {gap: wide}\n  a\n", "gap is a number, not 'wide'"),
    ("row {align: middle}\n  a\n", "align is one of start, center, end, stretch"),
    ("stack\n", "stack needs at least one layer"),
    ("row\n  a\n  a\n", "'a' is declared twice (first on line 2)"),
    ("a[x --> b\n", "[ after 'a' needs a closing ]"),
    ("row\n    a\n", "indented more than one level"),
    ("row\n a\n", "indent by 2 spaces"),
    ("row\n\ta\n", "spaces, not tabs"),
    ("a\n  b\n", "only blocks"),
    ("pad\n  a\n  b\n", "pad holds exactly one"),
    ("a.middle --> b\n", "unknown port .middle"),
    ("a ->> b\n", "sequence_diagram arrows"),
    ("a --> b {route: up}\n", "route is one of hv, vh"),
    ("---\nheadline: h\n", "no closing ---"),
    ("---\ncolour: x\n---\na\n", "unknown key 'colour'"),
    ("---\nmeanings: {x: purple}\n---\na\n", "meaning 'x' needs a tone"),
    ("---\nid: Fencing\n---\na\n", "write 'fencing'"),
    ("grid\n  | a |\n  |---|\n", "|---| header rows belong to table"),
    ("hub\n  a\n", "hub needs its center"),
    ("flow rl\n  a --> b\n", "flow goes lr (left to right) or td"),
    ("flow\n  a --> b\n  row\n    c\n", "flow holds nodes and edge lines"),
    ("flow\n  a --> a\n", "an edge needs two different ends"),
    ("flow\n  a --> auth{auth ok?}\n", "Mermaid's {decision} shape isn't drawn by Penflow; write auth[auth ok?]"),
    ("compare\n  a\n", "compare holds panel blocks only"),
    ("panel x\n  a\n", "panel goes directly under compare"),
    ("compare\n  panel\n    a\n", "a panel needs a title"),
    ("steps\n", "steps needs one line of text per step"),
    ("table\n  | a |\n  | b |\n  |---|\n", "a |---| line only goes right under the header row"),
    ("table\n  | a {x: 1} |\n", "table cells take a :::tone but no {attributes}"),
    ("overlap\n  a b c\n  set c..a: x\n", "write the range in order: set a..c"),
    ("overlap\n  a b c\n  set a..z: x\n", "'z' isn't one of the items: a, b, c"),
    ("overlap\n  a b\n  a..b: x\n", "overlap holds set lines"),
    ("timeline\n  soon: x\n", "a timeline event is value: text"),
    ("sequence_diagram\n  a -->> b: x\n", "-->> (dashed) isn't supported"),
    ("sequence_diagram\n  a --> b: x\n", "a message is a ->> b: text"),
    ("sequence_diagram\n  note right of a: x\n", "the note always sits beside its lane"),
    ("sequence_diagram\n  Note a: x\n", "write note <lane>: text (lowercase"),
    ("sequence_diagram\n  a -x b: x {mark: check}\n", "-x already ends in a cross"),
    ("sequence_diagram\n  participant a[same]\n  participant b[same]\n", "have the same label 'same'"),
    ("row\n  participant a\n", "participant lines go directly under sequence_diagram"),
    ("row\n  template t()\n", "template goes at the top level"),
])
def test_errors_name_the_line_and_the_fix(src: str, expect: str) -> None:
    assert expect in err(src)


def test_error_lines_count_from_first_line() -> None:
    with pytest.raises(SketchError) as e:
        parse_sketch("row\n  a\n  a\n", first_line=40)
    assert e.value.line == 42


def test_snake() -> None:
    assert snake("sequenceDiagram") == "sequence_diagram"
    assert snake("Fencing") == "fencing"
    assert snake("tool-map") == "tool_map"


# ---------------------------------------------------------------- checks name ids and lines
def test_check_messages_use_ids_and_lines() -> None:
    d = parse_sketch("row\n  a\n  b\n  c\na --> c\n", first_line=10).diagram
    crossing = [i for i in d.check() if i.code == "edge-crosses"]
    assert crossing and crossing[0].message == "edge a → c (line 14) passes through b (line 12)"


def test_python_check_messages_are_unchanged() -> None:
    a, b, c = Box("a"), Box("b"), Box("c")
    d = Diagram(Row(a, b, c), edges=[Arrow(a, c)])
    assert any(i.message == "Arrow passes through Box('b')" for i in d.check())


# ---------------------------------------------------------------- Markdown files
POST = """---
title: my post
penflow:
  theme: paper
  meanings: {loyal: cyan}
---
# post

````markdown
```penflow
an example in the docs, not a diagram
```
````

```penflow
---
id: hello
caption: one request
headline: one request, one answer
title: a client asks a server
---
row {gap: 90}
  client:::loyal
  server
client -->|request| server
```

text after.

```penflow
row
  a
  b
```
"""


def test_fences_skip_nested_examples() -> None:
    fs = fences(POST)
    assert len(fs) == 2 and fs[0].body.startswith("---\nid: hello")


def test_posts_from_before_the_rename_still_work(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "old.md"
    md.write_text("---\nsketchkit:\n  meanings: {loyal: cyan}\n---\n\n```sketch\nrow\n  a:::loyal\n  b\n```\n\n"
                  "```penflow\nc\n```\n", encoding="utf-8")
    doc = SketchDoc(md)
    assert [f.kind for f in fences(md.read_text(encoding="utf-8"))] == ["sketch", "penflow"]
    assert [s.id for s in doc.sketches] == ["sketch_1", "sketch_2"]
    assert doc.sketches[0].settings.meanings == {"loyal": "cyan"}
    doc.build()
    assert md.read_text(encoding="utf-8").count('data-sketch="') == 2


def test_sketch_doc_renders_after_each_fence_and_reruns_in_place(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_bytes(POST.replace("\n", "\r\n").encode("utf-8"))
    doc = SketchDoc(md)
    assert [s.id for s in doc.sketches] == ["hello", "sketch_2"]
    assert doc.sketches[0].settings.meanings == {"loyal": "cyan"}
    doc.build()
    once = md.read_bytes()
    SketchDoc(md).build()
    twice = md.read_bytes()
    assert once == twice and b"\r\n" in twice
    text = twice.decode("utf-8").replace("\r\n", "\n")
    assert text.count('data-sketch="hello"') == 1 and text.count('data-sketch="sketch_2"') == 1
    assert text.index("```\n\n<figure") < text.index("text after.")
    assert "<figcaption>one request</figcaption>" in text


def test_sketch_doc_errors_point_into_the_file(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text("# x\n\n```penflow\nrow\n  a\n  a\n```\n", encoding="utf-8")
    with pytest.raises(SketchError) as e:
        SketchDoc(md)
    assert str(e.value).endswith(":6: 'a' is declared twice (first on line 5); after the first time, "
                                 "refer to it by its id alone")


def test_duplicate_fence_ids(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text("```penflow\n---\nid: a\n---\nx\n```\n```penflow\n---\nid: a\n---\ny\n```\n", encoding="utf-8")
    with pytest.raises(SketchError, match="two sketches have the id 'a'"):
        SketchDoc(md)


def test_cli_render_and_check_markdown(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "post.md"
    md.write_text(POST, encoding="utf-8")
    assert main(["check", str(md)]) == 0
    assert "0 error(s)" in capsys.readouterr().out
    assert main(["render", str(md), "--no-write", "--gallery", str(tmp_path / "g.html")]) == 0
    assert (tmp_path / "g.html").exists() and "data-sketch" not in md.read_text(encoding="utf-8")
    assert main(["render", str(md)]) == 0
    assert 'data-sketch="hello"' in md.read_text(encoding="utf-8")


def test_cli_reports_parse_errors(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    md = tmp_path / "post.md"
    md.write_text("```penflow\nrow\n  a\n  a\n```\n", encoding="utf-8")
    assert main(["check", str(md)]) == 2
    assert "post.md:4: 'a' is declared twice" in capsys.readouterr().out
    assert main(["render", str(md)]) == 2


# ---------------------------------------------------------------- idea blocks
def test_flow_is_a_chain_with_gap_fitted_to_labels() -> None:
    d = body("flow lr\n  a -->|a long label here| b --> c\n")
    assert isinstance(d.body, Row) and len(d.body.items) == 3 and len(d.body.linked) == 2
    assert d.body.gap > 48
    v = body("flow td\n  a -->|x| b\n")
    assert isinstance(v.body, Col) and v.body.gap == 44
    e = v.body.linked[0]
    assert isinstance(e, Arrow) and e.label_side == "right"


def test_flow_matches_the_python_flow() -> None:
    from penflow import flow

    dsl = body("flow lr\n  a[a | one] -->|clang| b -->|bpf2go| c\n")
    py = Diagram(flow(("a", "one"), "b", "c", labels=["clang", "bpf2go"]))
    assert dsl.svg() == py.svg()


def test_stack_steps_hub() -> None:
    from penflow import hub, stack, steps

    assert body("stack\n  etcd_api[etcd API]\n  raft\n").svg() == Diagram(stack("etcd API", "raft")).svg()
    assert body("steps\n  propose\n  commit\n").svg() == Diagram(steps("propose", "commit")).svg()
    assert body("hub leader\n  f1\n  f2\n  f3\n").svg() == Diagram(hub("leader", ["f1", "f2", "f3"])).svg()


def test_hub_center_and_spokes_can_be_referenced() -> None:
    d = body("col\n  hub leader[the leader]:::accent\n    f1\n    f2\n  judge\nf1 --> judge\n")
    assert len(d.edges) == 1
    d.svg()


def test_table_header_and_tones() -> None:
    from penflow import table

    d = body("table\n  | threat | status |\n  |---|---|\n  | T1 | open :::bad |\n  | T2 | |\n")
    py = Diagram(table([["T1", ("open", "bad")], ["T2", None]], header=["threat", "status"]))
    assert d.svg() == py.svg()


def test_overlap_sets() -> None:
    from penflow import overlap

    d = body("overlap\n  n1[N1] n2[N2] n3[N3]:::good\n  set n1..n2: A :::bad\n  set n2..n3: B {side: bottom}\n")
    py = Diagram(overlap(["N1", "N2", ("N3", "good")], (0, 1, "A", "bad"), (1, 2, "B", None, "bottom")))
    assert d.svg() == py.svg()


def test_timeline_alternates_unless_told() -> None:
    from penflow import timeline

    d = body("timeline\n  0: start\n  27: alert :::bad\n  40: end {side: above}\n")
    assert isinstance(d.body, Track)
    assert [e.side for e in d.body.events] == ["above", "below", "above"]
    py = Diagram(timeline((0, "start"), (27, "alert", "bad"), (40, "end")))
    assert d.svg() == py.svg()


def test_sequence_lanes_messages_and_notes() -> None:
    d = body("sequence_diagram\n  participant client_a[client A]:::paused\n"
             "  client_a ->> etcd: lock\n  note client_a: pause :::paused {bar: 2}\n  gap 30\n"
             "  client_a -x storage: write :::stale {note: rejected}\n")
    lanes = d.body
    assert isinstance(lanes, Lanes) and lanes.names == ["client A", "etcd", "storage"]
    msg, act, gap, bad = lanes.rows
    assert isinstance(msg, Msg) and (msg.src, msg.dst, msg.label) == ("client A", "etcd", "lock")
    assert isinstance(act, Act) and act.bar == 2 and act.tone == "paused"
    assert isinstance(gap, Gap) and gap.h == 30
    assert isinstance(bad, Msg) and bad.mark == "cross" and bad.note == "rejected" and bad.tone == "stale"
    d.svg(meanings={"paused": "rust", "stale": "orange"})


def test_lane_heads_take_edges_from_outside() -> None:
    d = body("col\n  sequence_diagram\n    a ->> b: hi\n  log\nb --> log\n")
    e = d.edges[0]
    assert isinstance(e, Arrow) and isinstance(d.body, Col)
    lanes = d.body.items[0]
    assert isinstance(lanes, Lanes) and e.a is lanes.heads["b"]


def test_compare_panels() -> None:
    d = body("compare {gap: 30}\n  panel before :::bad\n    a --> b\n  panel after\n    c\n")
    assert isinstance(d.body, Split) and d.body.gap == 30 and len(d.body.items) == 2
    first = d.body.items[0]
    assert isinstance(first, Col)
    title = first.items[0]
    assert isinstance(title, Label) and title.text == "before" and list(title.tones()) == ["bad"]
    assert len(first.items[1].linked) == 1


# ---------------------------------------------------------------- templates
PAIR = "template pair(left, tone)\n  row\n    a[$left]:::$tone\n    b\n  a --> b\n"


def test_template_copies_get_prefixed_ids_and_their_own_edges() -> None:
    d = body(PAIR + "col\n  use pair as p1 {left: one, tone: bad}\n  use pair as p2 {left: two, tone: good}\n"
             "p1_b --> p2_a\np1 --> p2\n")
    assert isinstance(d.body, Col)
    r1, r2 = d.body.items
    assert isinstance(r1, Row) and isinstance(r2, Row)
    a1, a2 = r1.items[0], r2.items[0]
    assert isinstance(a1, Box) and a1.title == "one" and list(a1.tones()) == ["bad"]
    assert isinstance(a2, Box) and a2.title == "two" and a2.origin == "p2_a (line 3)"
    assert len(r1.linked) == 1 and len(d.edges) == 2
    e = d.edges[1]
    assert isinstance(e, Arrow) and e.a is r1 and e.b is r2


def test_templates_carry_over_to_later_fences(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_text(f"```penflow\n{PAIR}use pair as p {{left: x, tone: bad}}\n```\n\n"
                  "```penflow\nuse pair as q {left: y, tone: good}\n```\n", encoding="utf-8")
    doc = SketchDoc(md)
    assert len(doc.sketches) == 2 and set(doc.templates) == {"pair"}


def test_template_dollar_dollar_is_a_literal() -> None:
    d = body("template price(n)\n  label costs $$$n\nuse price as p {n: 5}\n")
    assert isinstance(d.body, Label) and d.body.text == "costs $5"


@pytest.mark.parametrize(("src", "expect"), [
    ("template t(x)\n  $x\nuse t as a {x: y}\n", "a $param can't stand in for an id or a keyword"),
    ("template t(x)\n  row\n    a --> $x\nuse t as a {x: y}\n", "can't stand in for an id"),
    ("template t(x)\n  a {$x: 1}\nuse t as a {x: y}\n", "can't stand in for an attribute key"),
    ("template t(x)\n  a[$y]\nuse t as a {x: y}\n", "$y isn't a parameter of template t; its parameters are x"),
    ("template t(x)\n  a[$x]\nuse t as u {}\n", "use t: missing x; its parameters are x"),
    ("template t(x)\n  a[$x]\nuse t as u {x: 1, y: 2}\n", "use t: no parameter 'y'"),
    ('template t(x)\n  a[$x]\nuse t as u {x: "a[b]"}\n', "the value of x is plain text"),
    ("use nope as u {}\n", "unknown template 'nope'"),
    ("template t()\n  a\n  b\nuse t as u\n", "template t makes 2 parts"),
    ("template t()\n  use t as again\nuse t as u\n", "template t uses itself (t → t)"),
    ("template t(x)\n  a[$x] {size: $x}\nuse t as u {x: big}\n",
     "size is a number, not 'big' (in template t, used as u on line 3)"),
    ("template t()\n  a\nuse t as u\nuse t as u\n", "'u' is declared twice"),
    ("template t()\n  a\ntemplate t()\n  b\nuse t as u\n", "template t is already defined (line 1)"),
    ("a\ntemplate t()\n  b\n", "templates go before the body"),
    ("template t()\n  a\n", "templates alone don't make a diagram"),
    ("template t(X)\n  a\n", "parameter 'X' isn't snake_case"),
])
def test_template_errors(src: str, expect: str) -> None:
    assert expect in err(src)


# ---------------------------------------------------------------- the demo, both ways
def test_demo_penflow_draws_exactly_what_demo_py_draws() -> None:
    import runpy

    from penflow import Doc

    root = pathlib.Path(__file__).parent.parent / "examples"
    ns = runpy.run_path(str(root / "demo.py"), run_name="__test__")
    py = next(v for v in ns.values() if isinstance(v, Doc))
    expected = {r.id.replace("-", "_"): r.svg for r in py.render()}
    got = {r.id: r.svg for r in SketchDoc(root / "demo_penflow.md").render()}
    assert set(got) == set(expected)
    for sid, svg in got.items():
        assert svg == expected[sid], sid


# ---------------------------------------------------------------- layered flows
def test_layers_rank_by_longest_path() -> None:
    r = layers(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert r.ranks == [["a"], ["b", "c"], ["d"]] and not r.back


def test_layers_leave_a_slot_for_long_edges() -> None:
    r = layers(["a", "b", "c"], [("a", "b"), ("b", "c"), ("a", "c")])
    assert r.ranks[1] in (["b", ("a", "c")], [("a", "c"), "b"])


def test_layers_drop_back_edges_from_the_ranking() -> None:
    r = layers(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    assert r.ranks == [["a"], ["b"], ["c"]] and r.back == {("c", "a")}


def test_layers_reorder_to_remove_crossings() -> None:
    # declared so that x2 -> y1 and x1 -> y2 would cross; one rank gets flipped
    r = layers(["x1", "x2", "y1", "y2"], [("x1", "y2"), ("x2", "y1")])
    pos = {n: i for rank in r.ranks for i, n in enumerate(rank) if isinstance(n, str)}
    assert (pos["x1"] < pos["x2"]) == (pos["y2"] < pos["y1"])


def test_branching_flow_builds_ranks_and_checks_clean() -> None:
    d = body("---\nheadline: h\ntitle: t\n---\nflow lr\n  a --> b --> d\n  a --> c --> d\n")
    assert isinstance(d.body, Row) and len(d.body.items) == 3
    middle = d.body.items[1]
    assert isinstance(middle, Col) and [n.title for n in middle.items if isinstance(n, Box)] == ["b", "c"]
    assert [i for i in d.check() if i.level != "info"] == []


def test_long_edge_bends_through_its_slot() -> None:
    d = body("---\nheadline: h\ntitle: t\n---\nflow lr\n  a --> b --> c\n  a -.->|skip| c\n")
    assert [i for i in d.check() if i.level != "info"] == []
    assert isinstance(d.body, Row)
    skip = [e for e in d.body.linked if isinstance(e, Arrow) and e.label == "skip"][0]
    assert len(skip.points()) == 3  # start, the slot in b's rank, end


@pytest.mark.parametrize("direction", ["lr", "td"])
def test_back_edges_go_around_the_flow(direction: str) -> None:
    d = body(f"---\nheadline: h\ntitle: t\n---\nflow {direction}\n  build --> test --> ship\n"
             "  test -.->|fix| build\n")
    assert [i for i in d.check() if i.level != "info"] == []
    assert isinstance(d.body, Pad)
    flow_node = d.body.child
    back = [e for e in flow_node.linked if isinstance(e, Arrow) and e.label == "fix"][0]
    pts = back.points()
    x, y, w, h = flow_node.rect
    if direction == "lr":
        assert max(p[1] for p in pts) > y + h  # under the flow
    else:
        assert max(p[0] for p in pts) > x + w  # right of the flow


def test_a_route_on_the_edge_turns_off_the_automatic_bend() -> None:
    d = body("flow lr\n  a --> b\n  b -->|back| a {route: hv}\n")
    assert isinstance(d.body, Pad)
    back = [e for e in d.body.child.linked if isinstance(e, Arrow) and e.label == "back"][0]
    assert type(back) is Arrow and back.route == "hv"


def test_lines_in_flows_have_no_head() -> None:
    d = body("flow lr\n  a --- b\n  a --- c\n")
    assert isinstance(d.body, Row)
    assert all(e.head == 0 for e in d.body.linked if isinstance(e, Arrow))
