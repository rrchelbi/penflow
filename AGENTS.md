# AGENTS.md: working on sketchkit

This file covers changing the library itself. To **draw diagrams with it**, read the guide:

```bash
uv run python -m sketchkit guide   # how to pick a shape, recipes, design rules, fixing check issues
uv run python -m sketchkit api     # the public API with signatures, generated from the code
```

## Commands (uv, not pip)

```bash
uv sync                                    # .venv with the dev tools
uv run pytest                              # tests, including every code block in guide.md
uv run mypy                                # strict
uv run pyright                             # strict
uv run python -m sketchkit check examples/demo.py --gallery out/check.html
```

Run all four checks (pytest, mypy, pyright, and `check` on the demo) before calling a change done. If you're running from `write-ups/`, add `--directory sketchkit` after `uv run` so the tools find this project's settings.

## Layout of the code

| file | what it holds |
|---|---|
| `src/sketchkit/core.py` | `Canvas`: the hand-drawn pen and the SVG output, positioned by coordinates |
| `src/sketchkit/nodes.py` | `Node` and every node type, containers, edges and `Diagram` (layout, then draw) |
| `src/sketchkit/ideas.py` | `flow`, `sequence`, `timeline`... These are plain functions that return nodes. |
| `src/sketchkit/lint.py` | `Diagram.check()`: geometric checks over a laid-out diagram |
| `src/sketchkit/publish.py` | `Doc`, `run`, `gallery`: putting SVGs into Markdown posts |
| `src/sketchkit/__main__.py` | `python -m sketchkit guide | api | check | skill` |
| `src/sketchkit/guide.md` | the guide for people using the library (shipped in the wheel) |
| `src/sketchkit/skills/sketch-diagrams/SKILL.md` | the Claude Code skill (shipped in the wheel; installed with `skill --install`) |

**Render pipeline:** `Diagram.layout()` measures with `ctx.size(node)`, then places with `node.layout(x, y, w, h)`, which sets every `node.rect`. `render()` then draws nodes in tree order, each with its own seed, and draws edges last. `check()` runs on the same layout.

## Rules

- **No runtime dependencies.** The library is pure Python 3.11+. Dev tools go in `[dependency-groups] dev` with `uv add --dev`.
- **Types stay strict in both checkers.**
  - Options are `Literal` aliases, and modifiers return `Self`.
  - When an attribute holds a Literal value, assign it on its own line with its type (`self.side: TrackSide = side`). Tuple assignments widen the type to `str` in pyright.
  - Don't use `# type: ignore` without an error code. pyright ignores those comments here (`enableTypeIgnoreComments = false`), so use `# pyright: ignore[rule]` for it.
- **Keep drawing stable.** Seeds are per node path (`seed/0.1.2`), so editing one node doesn't redraw the others. Don't add `rnd` calls to existing draw methods without a reason: that changes every existing diagram's wobble.
- **Report user mistakes with messages that say what to do.** Unknown lanes, unknown meanings, nodes used twice, or nodes missing from the tree should raise `ValueError`, and the message should name the fix.
- **Keep the agent-facing text in sync.** If you change a public signature or behavior, update `guide.md`, the skill and the README. `api` updates itself, but the guide doesn't. The guide's code blocks run in the tests, so a stale example fails.

## Adding things

- **A node:** subclass `Node`. Implement `_measure(ctx) -> (w, h)`, `_layout(ctx)` (place your children inside `self.rect`), `draw(cv, ctx)` (draw only yourself, not your children), and `children()` and `tones()` if it has any. Export it in `__init__.py`, add it to a section in `__main__.SECTIONS`, and test it in `tests/test_nodes.py`.
- **An idea:** add a function in `ideas.py` that only composes existing nodes and returns a node. Add an input alias such as `BoxSpec` if the argument shape is new, a row in the guide's "Pick the shape" table, and a recipe.
- **A check:** add it in `lint.py`, plus its `Code` literal, a line in the module docstring, a row in the guide's "Mistakes" table, and a test that builds the bad case and expects the code.
