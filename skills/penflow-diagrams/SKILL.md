---
name: penflow-diagrams
description: Draw explanatory hand-drawn diagrams with Penflow and put them in Markdown documents (posts, write-ups, docs), written as ```Penflow fences in the document or, when code is needed, as a Python script. Use when asked to illustrate, diagram, sketch or visualize an idea in a document, to add or fix a figure, to convert Mermaid diagrams, or to explain something "with a drawing".
---

# Drawing diagrams with Penflow

Penflow draws a diagram from a description of its parts and the arrows between them, and does the layout itself. Commands below use `uv run`.

- **Penflow is a dependency of the project** (`uv add penflow`): use the commands as written.
- **It's a local checkout in another folder:** add `--project <path-to-penflow>` after `uv run`, for example `uv run --project penflow python -m penflow guide`. The working directory stays where you are, so the document paths still work.
- **Without uv:** use `python -m penflow ...` in an environment where Penflow is installed.

## 1. Load the guide first

```bash
uv run python -m penflow guide
```

It covers how to pick a shape for an idea, the Penflow fence syntax with recipes, color rules and how to fix each layout problem. Don't guess the syntax from memory. For the Python API's exact signatures, run `uv run python -m penflow api`.

## 2. Decide what to draw, and how to write it

- **Read the section of the document** the drawing goes with. Write the one-sentence takeaway first; it becomes `headline:`.
- **One drawing explains one idea.** If a section has two ideas, make two drawings.
- **Write a ` ```penflow ` fence by default.** It lives in the document where the figure goes, needs no script, and is the shortest to write.
- **Write Python only when the diagram needs code:** a part whose structure changes from case to case (beyond what a `template` covers), or a drawing computed from data. If the document already has a diagrams script, keep adding to it, and keep its `Doc(meanings=...)`.
- **Reuse the document's meanings.** Put them once in the document's own front matter, so every fence shares them:

  ```yaml
  ---
  penflow:
    meanings: {loyal: cyan, traitor: orange}
  ---
  ```

- **Mermaid already in the document?** Leave it unless asked. If asked to convert it, run `uv run python -m penflow convert <doc>.md --write`, then read the `%% converted from Mermaid` comments it leaves, which list anything approximated.
- Leave diagrams made another way (images, hand-placed coordinates) as they are unless asked.

## 3. Write the fence

Put it where the figure belongs. Give it an `id` (snake_case, unique in the document), a `caption`, a `headline` and a `title` (the alt text: one or two full sentences).

````markdown
```penflow
---
id: quorum_overlap
caption: Any two majorities share a node.
headline: N3 is in both, so B always reaches someone who saw x=1
title: Five nodes; majority A is N1 to N3 and majority B is N3 to N5, so they share N3.
---
overlap
  n1[N1] n2[N2] n3[N3]:::good n4[N4] n5[N5]
  set n1..n3: majority A
  set n3..n5: majority B {side: bottom}
```
````

For a Python diagram, use one script per document (for example `scripts/diagrams_<doc-stem>.py`) with `Doc("<doc>.md")`, `@doc.diagram(id, caption)` and `run(doc)`, and put the anchor line `<!-- sketch: <id> -->` where the figure belongs. The guide's "Into a Markdown post" section has the full pattern.

## 4. Check, look, fix, repeat

```bash
uv run python -m penflow check <doc>.md --gallery out/<doc>.html
```

- Fix every `error`, and every `warn` unless there's a reason not to. Each issue names the parts involved by id and line, and a fix.
- If you have a browser or image tool, open `out/<doc>.html` and look. `check` finds geometry problems, not unclear explanations.
- Draw into the document only when the check passes:

```bash
uv run python -m penflow render <doc>.md
```

The figure goes right after its fence. Re-running replaces it, so edit the fence and render again. For a Python script, check it with `uv run python -m penflow check scripts/diagrams_<doc>.py` and run the script to write the figures.

## 5. Report back

Tell the user:

- which diagrams were added or changed, and where each sits (its fence `id`, or its anchor),
- the one-line takeaway of each,
- anything `check` still reports, and why it was left.
