# The Penflow language

Status: **in progress**. Implemented (all six steps of the plan below): front matter, nodes, tones and attributes, edges and ports, the layout blocks, the idea blocks, `sequence_diagram`, `timeline`, templates, the layered layout for `flow`, `render`/`check` on Markdown files, and the Mermaid importer. Dashed sequence messages (`-->>`) aren't supported yet. [examples/demo_penflow.md](../examples/demo_penflow.md) rewrites every diagram in `examples/demo.py` in this syntax, and the measurements at the end come from comparing the two files.

## Goals

1. **Diagrams live in the Markdown.** A ` ```penflow ` fence in a post is the whole diagram. No separate script, anchor comment or decorator.
2. **Cheap to write, for people and LLMs.** No imports, constructors or keyword arguments. An agent that knows Mermaid already knows most of the syntax.
3. **A quick move from Mermaid.** Where Mermaid has syntax for an idea, the DSL uses the same syntax. New syntax appears only for what Mermaid can't draw.
4. **The same diagrams as Python.** A Penflow block compiles to the same node tree that Python builds, so layout, `check()`, themes and the hand-drawn pen work unchanged. Python stays the escape hatch for anything the DSL can't express.

Non-goals: full Mermaid compatibility, variables, loops, conditionals, expressions, or arbitrary graph layout outside `flow` blocks. [Templates](#templates) substitute text and nothing more.

Fences tagged ` ```sketch `, the name before the project was called Penflow, are still read.

## Naming: everything is snake_case

Every word the DSL defines is lowercase snake_case: block keywords (`sequence_diagram`, `flow`), directions (`lr`, `td`), attribute keys (`label_side`, `sub_size`), front-matter keys (`box_font`) and option values (`end`, `bottom`, `check`).

**Ids are snake_case too.** This rule is enforced: `client_a` is valid, while `clientA` and `Client` are errors that suggest the snake_case form. When a node has no label, its text is the id with `_` turned into spaces, so `ring_buffer` draws as "ring buffer". Text inside labels is free-form.

Mermaid spellings that aren't snake_case, such as `sequenceDiagram`, `flowchart LR` and `Note right of`, are **not** accepted in a `penflow` fence. They are only read by the Mermaid importer (see [Moving from Mermaid](#moving-from-mermaid)). This keeps one spelling for everything, which is easier for an LLM to get right than a language with aliases.

## A block

````markdown
```penflow
---
id: fencing
caption: A lease can't stop a paused client.
headline: a lease can't stop a client that's paused
legend: true
---
sequence_diagram
  participant client_a[client A]:::paused
  participant etcd
  client_a ->> etcd: ① lock (rev 10)
```
````

- **Front matter** (optional) holds diagram-level settings, between `---` lines, like Mermaid's.
- **The body** is a tree. Indentation (2 spaces) means nesting. Tabs are an error.
- **Edge lines** can appear at any depth. They don't create nesting.
- `%%` starts a comment, as in Mermaid.

### Front matter keys

| key | maps to | notes |
|---|---|---|
| `id` | figure id (`data-sketch`) | used to replace the figure on re-runs. Defaults to `sketch_<n>` (the nth fence in the file) |
| `caption` | `Doc.diagram(..., caption)` | |
| `headline`, `note` | `Diagram(headline=, note=)` | |
| `legend` | `Diagram(legend=)` | `true` or `false` |
| `title` | `Diagram(title=)` | the SVG's accessible description |
| `width`, `margin`, `gap`, `seed` | same `Diagram` arguments | |
| `style`, `theme`, `box_font` | render options | override the file defaults |
| `meanings` | `meanings=` | an inline map, `{loyal: cyan, traitor: orange}`, merged over the file defaults |

**File defaults** go under a `penflow:` key in the Markdown file's own front matter, so other front-matter keys a blog uses are left alone:

```yaml
---
penflow:
  theme: paper
  meanings: {loyal: cyan, traitor: orange}
---
```

Values are a small YAML subset: scalars, `true`/`false`, numbers and inline `{k: v}` maps. Quote a value that contains `: ` or starts with `{`.

## Nodes

A node is written where it first appears. That's where it sits in the tree. Later mentions refer to it by id.

| syntax | node | Mermaid |
|---|---|---|
| `server` | `Box("server")` | same |
| `bpf_o[exec.bpf.o \| bytecode + BTF]` | `Box(title, sub)` | `[...]`, with `\|` for the second line |
| `n1((N1))` | `Circle("N1")` | same |
| `t1(open)` | `Cell("open")` | rounded box |
| `label some text` | `Label("some text")` | |
| `spacer {w: 20}` | `Spacer(w=20)` | |

**Text rules.** `\n` is a line break in any text. In `[...]`, the first unquoted `|` separates the title from the second line. To use `]`, `|`, `:::` or `{` literally, wrap the text in double quotes: `x["a | b"]`.

### Tones and attributes

Any node, edge or block line can end with a tone, an attribute block, or both, in that order:

```
c1_hears[L1 hears: attack + retreat]:::attack {size: 13, dashed}
```

- `:::name` is short for `{tone: name}`. The name is a meaning from `meanings` or a tone (`cyan`, `orange`, `rust`, `slate`, `accent`, `soft`). It's Mermaid's class syntax, but it accepts only one name.
- `{...}` holds attributes. Keys are the Python keyword arguments, so `size`, `sub_size`, `bold`, `min_w`, `w`/`h` (for `.fixed`), `align` (for `.align`) and `dashed` all work. A bare key such as `dashed` means `true`.

An unknown key is an error that lists the valid keys for that node, as the Python API does for unknown meanings.

## Edges

| syntax | edge | Mermaid |
|---|---|---|
| `a --> b` | `Arrow(a, b)` | same |
| `a -->\|load\| b` | `Arrow(a, b, "load")` | same |
| `a -.-> b` | `Arrow(..., dashed=True)` | same |
| `a --- b`, `a -.- b` | `Line`, dashed `Line` | same |
| `a --> b --> c` | two arrows | same |

Edge attributes go at the end: `c1_cmd -->|attack| c1_l1 :::attack {label_side: left}`. The keys are `Arrow`'s arguments (`route`, `label_side`, `label_at`, `size`, `head`, `gap`).

**Ports** use dots: `execwatch.bottom`, `.top`, `.left`, `.right`, `.center`, or `.at(0.15, 1)`.

**Where edges go.** An edge at the top level, after the body, becomes a `Diagram(edges=...)` entry. An edge inside a block is attached to that block with `.link()`. Inside a `flow`, edges also determine the layout (see below). Everywhere else they are only drawn.

## Layout blocks

A block keyword starts a line. The block's children are the lines indented under it. Text after the keyword is its title, if it has one.

| block | Python | children |
|---|---|---|
| `row` | `Row` | nodes and blocks |
| `col` | `Col` | nodes and blocks |
| `split` | `Split` | nodes and blocks (one panel each) |
| `overlay` | `Overlay` | nodes and blocks |
| `pad {bottom: 46}` | `Pad(child, bottom=46)` | exactly one |
| `region kernel` | `Region("kernel", child)` | one, or several (wrapped in a `col`) |
| `grid` | `Grid` | `\|`-rows, like `table` |

Block attributes are the Python arguments: `row {gap: 50, align: end, justify: between, stretch}`.

## Idea blocks

| block | Python | child lines |
|---|---|---|
| `flow lr` / `flow td` | `flow(...)` for a chain | node and edge lines; edges may branch, merge and loop (see below) |
| `stack` | `stack` | one node per line, top to bottom |
| `steps` | `steps` | one line of text per step |
| `hub leader` | `hub("leader", ...)` | one spoke node per line |
| `compare` | `compare` | `panel <title> :::tone` blocks, each with one body |
| `table` | `table` | Markdown table rows. A `\|---\|` line makes the row above it the header |
| `overlap` | `overlap` | one line of items, then `set a..b: label :::tone {side: bottom}` lines |
| `timeline` | `timeline` | `value: text :::tone` |
| `sequence_diagram` | `sequence` | see below |

`flowchart` is accepted as a second name for `flow`. It's the only alias: it is snake_case, and it lets a Mermaid user's first word work.

Table cells take `:::tone`: `| T1 | open :::bad | no fix yet |`.

### sequence_diagram

```
sequence_diagram
  participant client_a[client A]:::paused     %% lane, in order
  client_a ->> etcd: ① lock (rev 10)          %% Msg
  client_a -->> etcd: retry                   %% dashed Msg
  client_a -x storage: ⑦ write :::stale {note: "10 < 11: rejected"}   %% mark: cross
  note client_a: ② GC pause… :::paused {bar: 4}                        %% Act
  gap 20                                      %% Gap
```

- Arrows follow Mermaid: `->>` is a message, `-->>` is a dashed one, and `-x` ends in a cross. `{mark: check}` puts a check at the receiver. Dashed messages need support in `Msg` first, so for now `-->>` and `--x` are errors that suggest the solid form.
- `note lane: text` is an `Act`. Mermaid's `right of` and `over` aren't needed: the act always sits beside its lane.
- A lane that's never declared with `participant` is added the first time a message uses it, as in Mermaid.

## Templates

A template is a part you write once and place several times, such as the two cases of a comparison. It does the job of a Python function like `generals()` in the demo, but it only substitutes text.

```
template generals(cmd_role, l2_role, to_l2)
  col {gap: 14}
    pad {bottom: 46}
      cmd[commander | $cmd_role]:::$cmd_role
    row {gap: 50}
      l1[L1 | loyal]:::loyal
      l2[L2 | $l2_role]:::$l2_role
  cmd -->|attack| l1 :::attack {label_side: left}
  cmd -->|$to_l2| l2 :::$to_l2
compare
  panel case 1: the commander lies :::traitor
    use generals as c1 {cmd_role: traitor, l2_role: loyal, to_l2: retreat}
  panel case 2: L2 lies :::traitor
    use generals as c2 {cmd_role: loyal, l2_role: traitor, to_l2: attack}
```

**Defining.** `template name(param, ...)` comes before the body, at the top level of a fence. Names and parameters are snake_case. Its body follows the same rules as a fence body: one root (a node or a block), then any edge lines. The edges are attached to the root with `.link()`, so every copy carries its own arrows. This is the DSL form of a Python part that calls `.link()`.

**Using.** `use name as instance {param: value, ...}` goes anywhere a node can go. Arguments are named, in an attribute block, so a call reads the same way as every other line. Every parameter is required. A missing, extra or misspelt argument is an error that lists the template's parameters.

**Ids.** Ids inside a template are local. Each use prefixes them with its instance name, so `cmd` in the use `as c1` becomes `c1_cmd`. Edges outside the template refer to it by that name: `c1_cmd --> judge`. A prefixed id that clashes with another id is an error that names both lines. The instance name itself refers to the copy's root, so `c1 --> c2` joins the two parts.

**Substitution.** `$param` is replaced by the argument's text, and only in three places:

- text: labels, box titles and second lines, edge labels, panel titles
- tone names after `:::`
- attribute values: `{size: $size}`

It is an error anywhere else, including ids, keywords and attribute keys. That restriction is what keeps templates from turning into a programming language: a template can change what a part says and how it is coloured, but not its structure. A part whose structure changes from one copy to the next belongs in Python. Write `$$` for a literal `$`.

**Scope.** A template can be used in the fence that defines it and in every later fence in the same Markdown file, so a post can define its parts once. Templates can use other templates. A template that uses itself, directly or through another template, is an error.

**Errors and checks** report the line inside the template as well as the use line: `post.md:48 (in generals, used as c2 at post.md:57): c2_l1 overlaps c2_l2`.

## How `flow` lays out a graph

Outside `flow`, layout is the tree, exactly as in Python. Inside `flow`, nodes are placed from the edges, so a Mermaid flowchart that splits and joins still renders:

1. **Rank.** Each node's rank is its longest path from a node with no incoming edge. Edges that close a cycle are found with a depth-first search (in the order the nodes were declared) and left out of the ranking.
2. **Slots for long edges.** An edge that skips ranks gets an empty slot in every rank it crosses, and is drawn bending through those slots instead of cutting across the nodes in between.
3. **Order.** Nodes within a rank are reordered by the average position of their neighbours, sweeping down and up a few times, and the order with the fewest crossings is kept. Ties keep declaration order.
4. **Group.** Each rank becomes a `Col` for `lr` (a `Row` for `td`), spaced by `node_gap` (default 24), and the ranks go in a `Row` (or a `Col`).
5. **Gaps.** One gap is used between all ranks: 44 for `td`, and for `lr` the widest edge label plus 24 (at least 48). This is the rule `flow()` uses.
6. **Loops.** An edge that goes back (a retry, a feedback loop) is drawn around the flow: under it for `lr`, to its right for `td`, with its label on that side. Several back edges get separate lanes, and the flow is padded so the loop doesn't run into a headline or note below it.

`{route: hv}` or a port on an edge turns off the automatic bend for that edge. A straight chain builds exactly the tree `flow()` builds, so its SVG is identical. The output is an ordinary node tree, so `check()` reports crossings and overlaps as usual.

```
flow lr
  req[request] --> auth[auth ok?]
  auth -->|hit| cache --> resp[response]
  auth -->|miss| db --> resp
  auth -.->|no| reject:::bad
  resp -.->|retry| req
```

Mermaid's `{decision}` shape isn't drawn; `auth{auth ok?}` is an error that suggests `auth[auth ok?]`.

## Tooling

```bash
uv run python -m penflow render post.md          # draw every penflow fence; put each SVG after its fence
uv run python -m penflow check post.md           # lay out every fence and report problems
uv run python -m penflow convert diagram.mmd     # Mermaid in, Penflow syntax out
uv run python -m penflow convert post.md --write # replace a post's ```mermaid fences with ```penflow fences
uv run python -m penflow render post.md --mermaid  # draw ```mermaid fences as they are (check takes --mermaid too)
```

- `render` reuses `Doc`'s figure insertion, so re-running replaces earlier figures and keeps line endings. It takes the same flags as `run`: `--preview`, `--gallery`, `--no-write`, `--clean`, `--theme`.
- **Parse errors and check issues report the line in the Markdown file**, plus the fence's `id`: `post.md:41 (fencing): c1_l1 overlaps c1_l2`. An agent can then fix one line instead of regenerating the block. To make this work, every node records the line it was declared on.
- Errors say what to do, following the AGENTS.md rule: `post.md:12: 'sequenceDiagram' is Mermaid spelling; write 'sequence_diagram'`.

## Moving from Mermaid

`convert` (and `render --mermaid` / `check --mermaid`, which read ` ```mermaid ` fences as they are) translates the Mermaid people use most. The goal isn't to accept every Mermaid file, only to make the common ones work on the first try, and to say what changed.

```
flowchart LR                               flow lr
    A[Client] -->|HTTPS| B(Load balancer)    a[Client] -->|HTTPS| b[Load balancer]
    B --> C{Healthy?}                        b --> c[Healthy?]
```

| Mermaid | becomes |
|---|---|
| `flowchart` / `graph` with `LR`, `TD`, `TB` | `flow lr` / `flow td` (`RL` and `BT` are drawn as `lr` and `td`) |
| `A[text]`, `A(text)`, `A((text))` | `a[text]`, `a[text]`, `a((text))`; other shapes become boxes |
| `-->`, `---`, `-.->`, `-.-`, `==>`, `-->\|x\|`, `-- x -->`, chains, `A & B --> C` | edge lines, one per edge |
| `subgraph id [title] ... end`, `direction` | `region title`. Regions are ordered by the edges between them, and lay out across their parent unless they set a direction |
| `classDef`, `class`, `:::` | meanings, with a tone picked from the fill colour |
| `sequenceDiagram`: `participant`/`actor ... as`, `->>`, `-x`, `Note`, `activate`/`deactivate`, `+`/`-`, `autonumber`, `title` | `sequence_diagram`; activations become `bar`s, autonumber becomes ①②③ |
| `timeline` with `title` and `period : event : event` | `timeline`; periods that aren't numbers are spaced evenly |
| front matter `title:` | `headline:` |

- **Ids become snake_case**, keeping the original as the label (`userAPI` becomes `user_api[userAPI]`), and an id that's a Penflow keyword gets `_node` added.
- **Anything approximated or dropped is listed** in a `%% converted from Mermaid: ...` comment at the top of the output (and printed by `convert`): non-box shapes, thick and two-headed links, `style`/`linkStyle`/`click` lines, `loop`/`alt` blocks (their messages are kept), dashed and async messages, timeline sections.
- **Other diagram types are refused** with the closest Penflow block: `Mermaid gantt isn't drawn by penflow; the closest penflow block is timeline`.
- **Line numbers point into the Mermaid.** With `--mermaid`, parse errors and check issues name the line of the ` ```mermaid ` fence they came from.

## Grammar sketch

```
block       = [front_matter] { template } body
template    = "template" snake "(" [ snake { "," snake } ] ")" NEWLINE indented_body
body        = line { line }
line        = indent ( block_line | node_line | edge_line | use_line | row_line | comment )
use_line    = "use" snake "as" snake attrs
block_line  = keyword [ text ] [ tone ] [ attrs ]
node_line   = node { node }                         (several only in overlap's item line)
edge_line   = endpoint { arrow [ "|" text "|" ] endpoint } [ tone ] [ attrs ]
endpoint    = node | id port
node        = id [ shape ] [ tone ] [ attrs ]
shape       = "[" text "]" | "((" text "))" | "(" text ")"
port        = "." ( "top" | "bottom" | "left" | "right" | "center" | "at(" num "," num ")" )
tone        = ":::" snake
attrs       = "{" [ pair { "," pair } ] "}"
pair        = snake [ ":" value ]
id, snake   = [a-z][a-z0-9_]*
```

Lines specific to a block (`participant`, `note`, `set`, timeline events and table rows) are parsed only inside that block. Inside a template, `$snake` may stand in for `text`, the name after `:::` and attribute values.

## Measured against the Python demo

From `examples/demo.py` against `examples/demo_penflow.md`. Token counts are approximate: each word, number and punctuation character counts as one. That's close to how BPE tokenizers behave on code, but not exact.

| diagram | Python tokens | DSL tokens | ratio | structure only, Python | structure only, DSL | ratio |
|---|---:|---:|---:|---:|---:|---:|
| fencing | 371 | 257 | 1.44 | 194 | 62 | 3.1 |
| tool_map | 307 | 205 | 1.50 | 197 | 83 | 2.4 |
| three_generals | 432 | 316 | 1.37 | 293 | 159 | 1.8 |
| alert_timeline | 160 | 119 | 1.34 | 72 | 17 | 4.2 |
| quorum_overlap | 156 | 131 | 1.19 | 88 | 49 | 1.8 |
| shapes | 210 | 131 | 1.60 | 151 | 58 | 2.6 |
| setup (imports, `Doc`, meanings) | 167 | 39 | 4.3 | | | |
| **total** | **1803** | **1198** | **1.51** | **995** | **428** | **2.3** |

"Structure only" leaves out the prose (labels, captions, alt text), which is the same in both formats.

What the numbers say:

- **Structure costs well under half as much** (2.3× fewer tokens), and 3–4× less for sequence diagrams and timelines, which are what Mermaid users draw most.
- **Prose dominates whole diagrams.** Captions and the `title` alt text are often a third of a block, so the total saving is closer to 1.5×. Savings on edits should be larger than on the first write: fixing one line reported by `check` costs a few tokens, where regenerating a Python function costs hundreds.
- **Templates make reuse cheap.** Without one, `three_generals` had to write its panel out twice and came to 423 tokens, almost the same as Python's 432. With the `generals` template it is 316.

## Open questions

1. **Template defaults.** Should parameters take defaults (`template box_pair(tone = normal)`)? They'd shorten calls, but every argument would no longer be visible on the `use` line.
2. **One-line children.** `steps propose, replicate, commit` and `hub leader: f1 f2 f3 f4` would save lines and tokens. Should every list-like block accept both forms, or should each have just one?
3. **Indentation or `end`.** This draft uses indentation: it's fewer tokens and has no unclosed blocks. Mermaid users write `subgraph ... end`, but `convert` handles that. Is accepting only indentation acceptable?
4. **Ids with capitals.** Enforcing snake_case ids means writing `n1[N1]` instead of `N1`. The alternative is to allow `[A-Za-z0-9_]` ids and keep snake_case for keywords only.
5. **Where diagrams live.** Should `render` also accept a standalone `.penflow` file, for diagrams that aren't in a post?

## Implementation plan

Each step is one pull request, following CONTRIBUTING.md:

1. This spec and `examples/demo_penflow.md` (this branch).
2. The `penflow.dsl` package: parser, front matter, nodes, edges and layout blocks, plus `render`/`check` on Markdown files, with line numbers in errors. Tests in `tests/test_dsl.py` that render the demo fences and compare their layout with the Python demo.
3. Idea blocks, `sequence_diagram`, `timeline`, templates.
4. Layered layout for `flow`.
5. `convert` and `--mermaid`.
6. Docs: a DSL section in `guide.md` (its examples run in the tests), the skill switched to the DSL by default, a README section, a "coming from Mermaid" page ([mermaid.md](mermaid.md)), and `check` fixes worded in DSL terms for diagrams written as fences.
