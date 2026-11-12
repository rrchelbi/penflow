---
name: sketch-diagrams
description: Draw explanatory hand-drawn diagrams with the sketchkit Python library and insert them into Markdown documents (posts, write-ups, docs). Use when asked to illustrate, diagram, sketch or visualize an idea in a document, to add or fix a figure, or to explain something "with a drawing".
---

# Drawing diagrams with sketchkit

sketchkit is a Python library: you describe the parts of a drawing and the arrows between them, and it does the layout. Commands below use `uv run`.

- **sketchkit is a dependency of the project** (`uv add sketchkit`): use the commands as written.
- **It's a local checkout in another folder:** add `--project <path-to-sketchkit>` after `uv run`, for example `uv run --project sketchkit python -m sketchkit guide`. The working directory stays where you are, so the document paths still work.
- **Without uv:** use `python -m sketchkit ...` in an environment where sketchkit is installed.

## 1. Load the guide first

```bash
uv run python -m sketchkit guide
```

It covers how to pick a shape for an idea, recipes, color rules and how to fix each layout problem. For exact signatures, run `uv run python -m sketchkit api`. Don't guess the API from memory.

## 2. Decide what to draw

- **Read the section of the document** the drawing goes with. Write the one-sentence takeaway first; it becomes `headline=`.
- **One drawing explains one idea.** If a section has two ideas, make two drawings.
- **Reuse the document's meanings.** If the document already has a diagrams script, its `Doc(meanings=...)` defines what each color means; keep using it. Leave diagrams made another way (hand-drawn coordinates, other tools) as they are unless asked.

## 3. Write the script

Use one script per document, next to the project's other scripts, for example `scripts/diagrams_<doc-stem>.py`.

```python
from sketchkit import *

doc = Doc("docs/raft.md", meanings={"loyal": "cyan", "traitor": "orange"})

@doc.diagram("quorum-overlap", "Any two majorities share a node.")
def quorum_overlap() -> Diagram:
    return Diagram(..., headline="...", title="...")  # title = alt text, full sentences

if __name__ == "__main__":
    run(doc)
```

The `Doc` path is relative to the folder you run the script from. Each diagram is inserted after its anchor line `<!-- sketch: <id> -->`, so add that line to the document where the figure belongs. Re-running the script replaces the figures it inserted before.

## 4. Check, look, fix, repeat

```bash
uv run python -m sketchkit check scripts/diagrams_<doc>.py --gallery out/<doc>.html
```

- Fix every `error`, and every `warn` unless there's a reason not to. Each issue names the parts involved and a fix.
- If you have a browser or image tool, open `out/<doc>.html` and look. `check` finds geometry problems, not unclear explanations.
- Write into the document only when the check passes:

```bash
uv run python scripts/diagrams_<doc>.py
```

## 5. Report back

Tell the user:

- which diagrams were added or changed, and the anchor where each sits,
- the one-line takeaway of each,
- anything `check` still reports, and why it was left.
