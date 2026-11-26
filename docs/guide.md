# Penflow guide (for agents and people)

Penflow draws hand-drawn SVG diagrams. You describe *what* is in the picture: boxes, rows, arrows between named things. The library works out *where* everything goes. There are no coordinates.

There are two ways to write a diagram, and they draw the same thing:

- **A ` ```penflow ` fence in the Markdown post**, in a short text format that borrows Mermaid's syntax. It's the quickest to write and costs the fewest tokens. See [Penflow fences](#penflow-fences) at the end.
- **Python**, for diagrams built by code: a part whose structure changes from case to case, or a drawing computed from data. Most of this guide shows Python, and every Python shape has a Penflow block.

```bash
python -m penflow guide           # this text
python -m penflow api             # every public name and signature, generated from the code
python -m penflow check FILE      # lay out every diagram in a script or .md file and list layout problems
python -m penflow render POST.md  # draw a post's penflow fences into it
python -m penflow convert FILE    # Mermaid in, penflow fences out
```

## The loop

You usually can't see the picture, so work like this:

1. **Write the idea in one sentence** before writing any code. That sentence becomes the `headline`. If you can't write it, the diagram isn't ready.
2. **Pick the shape** that matches the idea (see the table below), and start from its recipe.
3. **Write the code.** Name every node you will point an arrow at.
4. **Check it**, with `d.check()` or `python -m penflow check script.py`. Fix every `error`. Fix `warn` items unless you have a reason not to. Each issue says which parts are involved and how to fix it.
5. **Look at it if you can.** Use `--gallery out.html` and open the page, or view the SVG. `check` finds geometry problems; it can't tell whether the drawing explains anything.

## Pick the shape

| The idea is... | Python | Penflow block | Example |
|---|---|---|---|
| a pipeline, cause → effect, a sequence of stages | `flow(...)` | `flow lr` / `flow td` | source → compile → binary |
| who sends what to whom, in what order | `sequence(lanes, Msg(...), Act(...))` | `sequence_diagram` | client, server, database |
| when things happened, durations, gaps | `timeline((t, "text"), ...)` | `timeline` | an incident timeline |
| layers that sit on top of each other | `stack(...)` | `stack` | app / runtime / kernel |
| before vs after, case A vs case B | `compare((title, body), ...)` | `compare` + `panel` | two failure cases |
| items × properties, status of many things | `table(rows, header=...)` | `table` | threats and their status |
| which items belong to which group, intersections | `overlap(items, sets...)` | `overlap` + `set` | two quorums sharing a node |
| one thing talking to many | `hub(center, spokes)` | `hub` | a leader and its followers |
| an ordered list of actions | `steps(...)` | `steps` | ① propose ② replicate ③ commit |
| something else | `Row`, `Col`, `Grid`, `Region`, `Arrow` | `row`, `col`, `grid`, `region`, edge lines | |

Every shape returns an ordinary node, so they nest. You can put a `flow` inside a `Region`, two `stack`s inside a `compare`, and so on.

## Minimal example

```python
from penflow import *

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
from penflow import *

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
from penflow import *

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
from penflow import *

d = Diagram(
    timeline((0, "deploy"), (40, "errors start", "bad"), (95, "rollback"), (130, "recovered", "good")),
    headline="90 seconds of errors before anyone rolled back",
    title="Deploy at 0 s, errors from 40 s, rollback at 95 s, recovered at 130 s.",
)
```

Labels alternate above and below the axis. For full control, pass `At(value, item, side=, level=, tone=)`.

### Two cases side by side, built from a function

```python
from penflow import *

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
from penflow import *

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
from penflow import *

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

To check a whole script from outside, without writing anything, use `python -m penflow check script.py --gallery out/check.html`.

## Penflow fences

A ` ```penflow ` fence holds one diagram, written where it appears in the post. `python -m penflow render post.md` draws every fence and puts the figure right after it. Re-running replaces the figures, so edit the fence and render again. The full syntax is in `docs/language.md` in the Penflow repository. Everything below is enough for most diagrams.

The minimal example from the top of this guide, as a fence:

```penflow
---
headline: the server checks every request, not just the first
title: A client sends a request with a token; the server checks it and answers 403 when it is invalid.
---
row {gap: 120}
  client
  server[server | checks the token]
client.at(1, 0.3) -->|request + token| server.at(0, 0.3)
server.at(0, 0.7) -->|403| client.at(1, 0.7) :::bad {label_side: below}
```

### The syntax in one table

Every word the DSL defines is snake_case, and so are ids.

| you write | you get |
|---|---|
| `---` front matter `---` | `headline:`, `note:`, `title:`, `legend: true`, `meanings: {loyal: cyan}`, `id:`, `caption:` |
| `client` | a box titled "client" (`ring_buffer` reads "ring buffer") |
| `a[title \| second line]`, `n((N1))`, `t(open)` | a box with two lines, a circle, a table cell |
| `label some text`, `spacer {h: 20}` | a label, a gap |
| `:::bad` at the end of a node or edge | its meaning (tone) |
| `{size: 13, dashed, w: 200}` at the end | attributes: the Python keyword arguments |
| `a --> b`, `a -->\|label\| b`, `a -.-> b`, `a --- b`, `a --> b --> c` | arrows, a label, dashed, no head, a chain |
| `a.bottom --> b.at(0, 0.3)` | ports |
| `row {gap: 50}`, `col`, `split`, `region title`, `pad {bottom: 46}`, `grid`, `overlay` | layout blocks: indent the children by 2 spaces |
| `%% text` | a comment |

A node is placed where it's first written. After that, refer to it by id alone. An edge at the top level, after the body, is a diagram edge. An edge inside a block belongs to that block.

### A pipeline with a highlighted step

```penflow
---
headline: the verifier is the step that says no
title: Code is compiled to bytecode, checked by the verifier, and only reaches the kernel if it is safe.
---
flow lr
  compile[compile | clang -O2] -->|bytecode| verifier[verifier | can say no]:::bad -->|if safe| kernel
```

`flow` sizes its gaps for the labels. It also lays out flows that branch, merge and loop: a retry edge back to an earlier step is drawn around the flow. Use `flow td` for more than four steps.

### Who talks to whom

```penflow
---
headline: a write is committed once a majority has it
title: The client sends put to the leader, the leader appends to the follower, the follower acks, the leader commits and answers ok.
---
sequence_diagram
  participant client
  participant leader:::good
  participant follower
  client ->> leader: ① put x=1
  leader ->> follower: ② append
  follower ->> leader: ③ ack :::good
  note leader: ④ commit: a majority has it :::good
  leader ->> client: ⑤ ok
```

`a -x b: text` ends the message in a cross, and `{mark: check}` puts a check there. `note lane: text {bar: 3}` draws a thick line on the lifeline over 3 rows. `gap` adds a row of space.

### A timeline

```penflow
---
headline: 90 seconds of errors before anyone rolled back
title: Deploy at 0 s, errors from 40 s, rollback at 95 s, recovered at 130 s.
---
timeline
  0: deploy
  40: errors start :::bad
  95: rollback
  130: recovered :::good
```

### Two cases side by side, with a template

```penflow
---
headline: no heartbeats → the followers start an election
legend: true
title: Left, a live leader sends heartbeats to two followers. Right, the leader crashed and sends nothing.
---
template case(state, tone)
  col {gap: 50}
    leader[leader | $state]:::$tone
    row {gap: 40}
      f1
      f2
  leader --> f1 :::$tone
  leader --> f2 :::$tone
compare
  panel normal
    use case as live {state: alive, tone: good}
  panel leader crash :::bad
    use case as dead {state: crashed, tone: bad}
```

A template is a part you write once and place several times. `$param` fills in text, tones and attribute values, never ids or keywords. Each `use ... as name` gets its own ids (`live_leader`, `dead_f1`) and its own edges. A part whose *structure* changes between cases belongs in Python.

### Groups, tables, sets

```penflow
---
headline: three shapes in one column
title: Two nodes each running an agent on a kernel, a two-row threat table, and two overlapping majorities.
---
col {gap: 28}
  row {gap: 16}
    region node 1
      stack
        agent_1[agent]
        kernel_1[kernel]
    region node 2
      stack
        agent_2[agent]
        kernel_2[kernel]
  table
    | threat | status |
    |---|---|
    | replay | open :::bad |
    | flood | fixed :::good |
  overlap
    n1[N1] n2[N2] n3[N3]:::good n4[N4] n5[N5]
    set n1..n3: majority A :::normal
    set n3..n5: majority B :::wait {side: bottom}
```

### Check, render, repeat

```bash
python -m penflow check post.md --gallery out/post.html   # problems by id and line, and a page to look at
python -m penflow render post.md                          # draw the fences into the post
```

`check` names the id and the line of each part involved, and says the fix in DSL terms ("add `{route: hv}` to the edge line"). Mistakes in the text itself, such as an unknown attribute, a camelCase id or a node declared twice, stop with the line and the fix.

**Coming from Mermaid:** `python -m penflow convert post.md --write` turns the post's ` ```mermaid ` fences into penflow fences, and lists in comments anything it approximated. `render post.md --mermaid` draws Mermaid fences without changing them. See `docs/mermaid.md` in the Penflow repository.
