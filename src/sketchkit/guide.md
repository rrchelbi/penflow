# sketchkit guide (for agents and people)

sketchkit draws hand-drawn SVG diagrams from Python. You describe *what* is in the picture: boxes, rows, arrows between named things. The library works out *where* everything goes. There are no coordinates.

```bash
python -m sketchkit guide        # this text
python -m sketchkit api          # every public name and signature, generated from the code
python -m sketchkit check FILE   # lay out every diagram in a script and list layout problems
```

## The loop

You usually can't see the picture, so work like this:

1. **Write the idea in one sentence** before writing any code. That sentence becomes the `headline`. If you can't write it, the diagram isn't ready.
2. **Pick the shape** that matches the idea (see the table below), and start from its recipe.
3. **Write the code.** Name every node you will point an arrow at.
4. **Check it**, with `d.check()` or `python -m sketchkit check script.py`. Fix every `error`. Fix `warn` items unless you have a reason not to. Each issue says which parts are involved and how to fix it.
5. **Look at it if you can.** Use `--gallery out.html` and open the page, or view the SVG. `check` finds geometry problems; it can't tell whether the drawing explains anything.

## Pick the shape

| The idea is... | Use | Example |
|---|---|---|
| a pipeline, cause → effect, a sequence of stages | `flow(...)` | source → compile → binary |
| who sends what to whom, in what order | `sequence(lanes, Msg(...), Act(...))` | client, server, database |
| when things happened, durations, gaps | `timeline((t, "text"), ...)` | an incident timeline |
| layers that sit on top of each other | `stack(...)` | app / runtime / kernel |
| before vs after, case A vs case B | `compare((title, body), ...)` | two failure cases |
| items × properties, status of many things | `table(rows, header=...)` | threats and their status |
| which items belong to which group, intersections | `overlap(items, sets...)` | two quorums sharing a node |
| one thing talking to many | `hub(center, spokes)` | a leader and its followers |
| an ordered list of actions | `steps(...)` | ① propose ② replicate ③ commit |
| something else | build it from `Row`, `Col`, `Grid`, `Region` and `Arrow` | |

Every shape returns an ordinary node, so they nest. You can put a `flow` inside a `Region`, two `stack`s inside a `compare`, and so on.

## Minimal example

```python
from sketchkit import *

client, server = Box("client"), Box("server", "checks the token")
d = Diagram(
    Row(client, server, gap=120),
    edges=[Arrow(client.at(1, 0.3), server.at(0, 0.3), "request + token"),
           Arrow(server.at(0, 0.7), client.at(1, 0.7), "403", tone="bad", label_side="below")],
    headline="the server checks every request, not just the first",
    title="A client sends a request with a token; the server checks it and answers 403 when it is invalid.",
)
svg = d.svg()                 # paper card, hand-drawn
assert not [i for i in d.check() if i.level == "error"]
```

Two arrows between the same pair of boxes would be drawn on the same line, so give each its own **ports**: `node.at(fx, fy)` is a point on the node's frame, from (0, 0) at the top-left to (1, 1) at the bottom-right.

`Diagram(...)` takes the body, then `edges=`, `headline=` (the takeaway), `note=` (a quieter second line), `legend=True`, and `title=` (alt text). Write the title as one or two full sentences, since it's what a screen reader says.

## Recipes

### A pipeline with a highlighted step

```python
from sketchkit import *

d = Diagram(
    flow(("compile", "clang -O2"), Box("verifier", "can say no").tone("bad"), "kernel",
         labels=["bytecode", "if safe"]),
    headline="the verifier is the step that says no",
    title="Code is compiled to bytecode, checked by the verifier, and only reaches the kernel if it is safe.",
)
```

`flow` sizes its gaps so arrow labels fit. Use `vertical=True` when there are more than four steps or the labels are long. A row wider than 560px gets scaled down and the text shrinks.

### Who talks to whom

```python
from sketchkit import *

d = Diagram(
    sequence(
        ["client", ("leader", "good"), "follower"],
        Msg("client", "leader", "① put x=1"),
        Msg("leader", "follower", "② append"),
        Msg("follower", "leader", "③ ack", tone="good"),
        Act("leader", "④ commit: a majority has it", tone="good"),
        Msg("leader", "client", "⑤ ok"),
    ),
    headline="a write is committed once a majority has it",
    legend=[("good", "committed path")],
    title="The client sends put to the leader, the leader appends to the follower, the follower acks, "
          "the leader commits and answers ok.",
)
```

`Msg(src, dst, label, tone=, mark="cross"|"check", note=)` draws one arrow per row. `Act(lane, text, bar=n)` writes beside a lifeline, and `bar` draws a thick line over n rows (a pause, a lock held). `Gap(h)` adds space.

### A timeline

```python
from sketchkit import *

d = Diagram(
    timeline((0, "deploy"), (40, "errors start", "bad"), (95, "rollback"), (130, "recovered", "good")),
    headline="90 seconds of errors before anyone rolled back",
    title="Deploy at 0 s, errors from 40 s, rollback at 95 s, recovered at 130 s.",
)
```

Labels alternate above and below the axis. For full control, pass `At(value, item, side=, level=, tone=)`.

### Two cases side by side, built from a function

```python
from sketchkit import *

def case(leader_alive: bool) -> Col:
    leader = Box("leader", "alive" if leader_alive else "crashed").tone("good" if leader_alive else "bad")
    f1, f2 = Box("f1"), Box("f2")
    return Col(leader, Row(f1, f2, gap=40), gap=50).link(
        Arrow(leader, f1, tone="good" if leader_alive else "bad", dashed=not leader_alive),
        Arrow(leader, f2, tone="good" if leader_alive else "bad", dashed=not leader_alive),
    )

d = Diagram(
    compare(("normal", case(True)), ("leader crash", case(False), "bad")),
    headline="no heartbeats → the followers start an election",
    legend=True,
    title="Left: a live leader sends heartbeats to two followers. Right: the leader crashed and sends nothing.",
)
```

A function that returns a node is how you reuse a part. `.link(...)` attaches its arrows to it, so the part carries its own edges wherever you put it. Don't put the same node object in a tree twice: call the function again instead.

### Groups, tables, sets

```python
from sketchkit import *

nodes = Row(*[Region(f"node {i}", stack("agent", "kernel")) for i in (1, 2, 3)], gap=16)
threats = table([["replay", ("open", "bad")], ["flood", ("fixed", "good")]], header=["threat", "status"])
quorum = overlap(["N1", "N2", ("N3", "good"), "N4", "N5"],
                 (0, 2, "majority A", "normal", "top"), (2, 4, "majority B", "wait", "bottom"))
d = Diagram(Col(nodes, threats, quorum, gap=28), headline="three shapes in one column",
            title="Three nodes each running an agent on a kernel, a two-row threat table, and two overlapping majorities.")
```

## Color means something

Nodes and edges take a **meaning**, not a color: `.tone("bad")`, `Arrow(..., tone="good")`. The built-in meanings are `good` (cyan), `bad` (orange), `wait` (rust) and `normal` (slate). Add your own when rendering, as `meanings={"traitor": "orange", "loyal": "cyan"}`, or set them once on a `Doc`. `legend=True` lists the meanings the drawing actually uses.

You can also use `"accent"` (blue on paper) for the one thing to look at, and `"soft"` (gray) for context. Raw tone names (`"cyan"`) work but don't show in the legend.

Rules that make diagrams read well:

- **Color only what the idea is about.** Leave most boxes plain. Use at most four meanings, and `check` warns past that.
- **One meaning, one color, across every diagram in a post.** Define the meanings once on the `Doc`.
- **Put words on arrows**, as verbs or the thing that moves ("ack", "token 11"). An unlabeled arrow makes the reader guess.
- **Number the steps** in the order to read them: `Step(1, ...)`, `steps(...)`, or ①②③ inside labels.
- **The headline is the takeaway**, not a title: "a lease can't stop a paused client", not "Leases".
- **Use 3 to 9 shapes.** Past 15, `check` suggests splitting. Two simple drawings beat one dense one.
- **Use `Note` or `note=` for the "why"**, shown in gray under the headline.

## Layout reference

- `Row(*items, gap=24, align="center", justify="center", stretch=False)` and `Col(...)` take nodes or strings (a string becomes a `Label`).
- `Grid(rows, gap=16)` gives aligned columns. `Split(*panels)` puts panels side by side with a divider. `Region(title, child)` draws a dashed outline. `Pad(child, top=...)` adds space. `Overlay(*items)` stacks things on one spot.
- `Box(title, sub=None)` sizes itself from its text. Override with `.fixed(w=, h=)`.
- `Label(text, size=14, tone=, bold=, align=)` supports multi-line text with `\n`. `Headline`, `Note` and `Step(n, text)` are preset labels.
- **Edges** take nodes, ports or points:
  - `Arrow(a, b, label, tone=, dashed=, route="hv"|"vh", via=[(x, y)], label_side=, label_at=)`.
  - **Ports:** `node.top`, `.bottom`, `.left`, `.right`, `.center`, `.at(fx, fy)`. Use them to start an arrow from a specific side.
  - `Line(...)` is an arrow without a head. `Bracket(nodes, label, side="top"|"bottom")` spans a group.
- **Modifiers** change the node in place and return it, so they chain: `.tone()`, `.dashed()`, `.fixed()`, `.align("start"|"center"|"end"|"stretch")`, `.link(*edges)`.

## Mistakes `check` catches, and how to fix them

| issue | usual fix |
|---|---|
| `label-overlap`: an arrow label on a box | Use `flow()`, which sizes the gaps, or a bigger `gap=`, a shorter label, `label_side="below"`, or `label_at=0.3`. |
| `edge-crosses`: an arrow through a box | Reorder the row so connected things sit next to each other, start from a port (`a.bottom`), or `route="vh"`. |
| `edge-overlap`: two arrows on one line | Give each its own ports: `a.at(1, 0.3)` to `b.at(0, 0.3)`, and back from `b.at(0, 0.7)` to `a.at(1, 0.7)`. |
| `overlap`: shapes on shapes | Increase `gap`, or move one into another row. |
| `text-overflow` | Remove `.fixed(w=...)`, or shorten the text, or use `\n`. |
| `too-wide` | Use `Col` or `flow(..., vertical=True)`, or fewer items per row. |

Some mistakes `check` can't see:

- **An arrow that points at a `Pad(...)`** stops at the padding, not at the box. Point arrows at the inner node and keep it in a variable.
- **A node built in one place and used in another**, or used twice, raises an error at render time ("appears twice", "not part of the diagram").
- **Unknown meaning names** raise an error at render time, listing the known ones.
- **Text widths are estimated** from a character table, so leave some slack.

## Into a Markdown post

```python
import pathlib, tempfile
from sketchkit import *

post = pathlib.Path(tempfile.mkdtemp()) / "post.md"
post.write_text("# Raft\n\n<!-- sketch: commit -->\n", encoding="utf-8")

doc = Doc(post, meanings={"committed": "cyan", "lost": "orange"})

@doc.diagram("commit", "A write counts once a majority has it.")
def commit() -> Diagram:
    return Diagram(flow("client", Box("leader").tone("committed"), "majority"),
                   headline="committed = on a majority", title="Client to leader to a majority of nodes.")

run(doc, argv=["--check"])   # in a real script: `if __name__ == "__main__": run(doc)`
assert 'data-sketch="commit"' in post.read_text(encoding="utf-8")
```

A diagram goes after the line `<!-- sketch: <id> -->`. Re-running the script replaces it, so edit the code and run again. The script options are `--check`, `--no-write`, `--preview DIR`, `--gallery FILE`, `--clean` (straight lines) and `--theme paper|auto|blog`.

To check a whole script from outside, without writing anything, use `python -m sketchkit check script.py --gallery out/check.html`.
