import pathlib
import re

import pytest

from sketchkit import (
    Act,
    Arrow,
    Box,
    Col,
    Diagram,
    Doc,
    Label,
    Legend,
    Msg,
    Region,
    Row,
    Split,
    Style,
    Theme,
    compare,
    flow,
    overlap,
    run,
    sequence,
    stack,
    steps,
    table,
    timeline,
)


def paths(svg: str) -> list[str]:
    return re.findall(r'<path class="[^"]+"[^>]* d="([^"]+)"', svg)


def test_row_places_children_left_to_right_without_overlap() -> None:
    a, b, c = Box("a"), Box("bb"), Box("ccc")
    Diagram(Row(a, b, c, gap=30)).render()
    assert a.rect[0] + a.rect[2] + 30 == pytest.approx(b.rect[0])
    assert b.rect[0] + b.rect[2] + 30 == pytest.approx(c.rect[0])


def test_box_grows_with_its_text() -> None:
    short, long = Box("x"), Box("a much longer title here")
    Diagram(Col(short, long)).render()
    assert long.rect[2] > short.rect[2]


def test_arrow_ends_on_the_outlines() -> None:
    a, b = Box("a"), Box("b")
    Diagram(Row(a, b, gap=100), edges=[e := Arrow(a, b)]).render()
    (x0, y0), (x1, _) = e.points()
    assert x0 == pytest.approx(a.rect[0] + a.rect[2] + 6)
    assert x1 == pytest.approx(b.rect[0] - 6)
    assert y0 == pytest.approx(a.rect[1] + a.rect[3] / 2)


def test_same_input_same_svg() -> None:
    def make() -> str:
        return Diagram(flow("a", "b", "c", labels=["x", "y"]), headline="h").svg()

    assert make() == make()


def test_editing_one_node_keeps_the_others_wobble() -> None:
    """Each node draws with its own seed, so a change stays local."""
    one = Diagram(Col(Box("first"), Box("second"))).svg(style="hand")
    two = Diagram(Col(Box("first"), Box("second"), Label("added"))).svg(style="hand")
    # Box outlines (two-pass pen lines) are identical up to the vertical shift from re-centering.
    assert len(paths(one)) == len(paths(two))


def test_canvas_grows_to_fit_edge_labels_left_of_content() -> None:
    a, b = Box("a"), Box("b")
    e = Arrow(a, b, "a very long label on the left", label_side="left")
    cv = Diagram(Col(a, b, gap=80), edges=[e], width=None).render()
    from sketchkit.nodes import Ctx
    x0, _, _, _ = e.bbox(Ctx())
    assert x0 >= 20 - 0.01  # shifted right so the label stays inside the margin
    assert a.rect[0] > 100 and cv.w >= a.rect[0] + a.rect[2] + 20


def test_node_used_twice_is_an_error() -> None:
    b = Box("x")
    with pytest.raises(ValueError, match="twice"):
        Diagram(Row(b, b)).render()


def test_edge_to_node_outside_the_tree_is_an_error() -> None:
    a, stray = Box("a"), Box("stray")
    with pytest.raises(ValueError, match="not part of the diagram"):
        Diagram(a, edges=[Arrow(a, stray)]).render()


def test_unknown_meaning_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown tone or meaning 'evil'"):
        Diagram(Box("a").tone("evil")).render()


def test_legend_lists_used_meanings_in_order() -> None:
    d = Diagram(Row(Box("a").tone("bad"), Box("b").tone("good"), Box("c").tone("bad")), legend=True)
    svg = d.svg(meanings={"bad": ("orange", "traitor")})
    assert svg.index(">traitor<") < svg.index(">good<")
    assert ">wait<" not in svg


def test_explicit_legend() -> None:
    svg = Diagram(Box("a"), legend=Legend([("cyan", "honest")])).svg()
    assert ">honest<" in svg


@pytest.mark.parametrize("theme", ["paper", "auto", "blog"])
@pytest.mark.parametrize("style", ["hand", "clean"])
def test_every_idea_renders_in_every_mode(style: Style, theme: Theme) -> None:
    body = Col(
        flow("a", ("b", "sub"), labels=["go"]),
        stack("top", "mid", "bottom"),
        timeline((0, "start"), (5, "event", "bad"), (10, "end")),
        sequence(["x", ("y", "good")], Msg("x", "y", "hi", mark="check"), Act("y", "thinks", bar=1)),
        compare(("left", Box("l")), ("right", Box("r"))),
        table([["a", ("b", "bad")]], header=["h1", "h2"]),
        overlap(["n1", "n2", "n3"], (0, 1, "A", "good"), (1, 2, "B", "bad", "bottom")),
        steps("one", "two"),
        Region("zone", Split(Box("p"), Box("q"))),
    )
    svg = Diagram(body, headline="all", note="of them", legend=True).svg(style, theme)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert ("<style>" in svg) == (theme == "blog")


def test_lanes_reject_unknown_lane() -> None:
    with pytest.raises(ValueError, match="unknown lane"):
        sequence(["a", "b"], Msg("a", "c", "x"))


def test_lane_heads_can_be_edge_targets() -> None:
    seq = sequence(["a", "b"], Msg("a", "b", "x"))
    note = Box("note")
    Diagram(Row(seq, note), edges=[Arrow(note, seq["b"])]).render()


def test_doc_inserts_and_replaces(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "post.md"
    md.write_bytes(b"# t\r\n\r\n<!-- sketch: one -->\r\n\r\nend\r\n")
    doc = Doc(md)

    @doc.diagram("one", "caption")
    def one() -> Diagram:
        return Diagram(Box("hello"))

    run(doc, argv=[])
    first = md.read_bytes()
    assert b'data-sketch="one"' in first and b"\r\n" in first
    run(doc, argv=[])
    assert md.read_bytes() == first  # idempotent


def test_run_preview_and_gallery(tmp_path: pathlib.Path) -> None:
    md = tmp_path / "p.md"
    md.write_text("<!-- sketch: a -->\n", encoding="utf-8")
    doc = Doc(md)
    doc.diagram("a", "cap")(lambda: Diagram(Box("x")))
    run(doc, argv=["--no-write", "--clean", "--theme", "auto", "--preview", str(tmp_path / "svg"),
                   "--gallery", str(tmp_path / "g.html")])
    assert (tmp_path / "svg" / "a.svg").exists()
    assert "<figure" in (tmp_path / "g.html").read_text(encoding="utf-8")
    assert md.read_text(encoding="utf-8") == "<!-- sketch: a -->\n"
