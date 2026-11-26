# AGENTS.md: working on Penflow

This file covers changing the library itself. To **draw diagrams with it**, read the guide:

```bash
uv run python -m penflow guide   # how to pick a shape, recipes, design rules, fixing check issues
uv run python -m penflow api     # the public API with signatures, generated from the code
```

## Commands (uv, not pip)

```bash
uv sync                                    # .venv with the dev tools
uv run pytest                              # tests, including every example in docs/guide.md
uv run mypy                                # strict
uv run pyright                             # strict
uv run ruff check                          # lint; rules in pyproject.toml
uv run python -m penflow check examples/demo.py --gallery out/check.html
uv run python -m penflow check examples/demo_penflow.md
```

Run all of these before calling a change done; CI (`.github/workflows/ci.yml`) runs the same on every pull request, on Python 3.11 to 3.14. If you're running from the folder above this project, add `--directory <this folder>` after `uv run` so the tools find this project's settings.

## Layout of the code

Everything under `src/penflow/`:

| module | what it holds |
|---|---|
| `core.py` | `Canvas`: the hand-drawn pen, tones and palettes, and the SVG output, positioned by coordinates |
| `nodes/` | the node tree: `base` (the `Node` protocol, option types, `Ctx`, `Port`), `leaves`, `layout` (containers), `scales` (`Track`, `Lanes`), `edges`, `diagram` (`Diagram`: layout, then draw) |
| `ideas.py` | `flow`, `sequence`, `timeline`...: plain functions that compose nodes |
| `lint.py` | `Diagram.check()`: geometric checks over a laid-out diagram |
| `publish.py` | `Doc`, `run`, `gallery`: putting SVGs into Markdown posts |
| `dsl/` | Penflow (spec: `docs/language.md`): `lexer` → `syntax` (one line to a syntax tree) → `builder` + `blocks` (syntax tree to nodes), with `attrs`, `frontmatter`, `templates`, `layered` (the `flow` layout), `parse` (`parse_sketch`) and `markdown` (`SketchDoc`) |
| `mermaid/` | `convert_mermaid`: `flowchart`, `sequence` and `timeline` converters sharing `common` |
| `cli.py` | `python -m penflow guide \| api \| check \| render \| convert \| skill`; `reference.py` generates `api` |
| `resources.py` | reads the guide and the skill, from the wheel or from a checkout |

Outside the package:

| path | what it holds |
|---|---|
| `docs/` | `guide.md` (shipped in the wheel, printed by `guide`), `language.md` (the Penflow language spec), `mermaid.md`, `assets/` |
| `skills/penflow-diagrams/SKILL.md` | the Claude Code skill (shipped in the wheel; installed with `skill --install`) |
| `examples/` | `demo.py` and `demo_penflow.md`, which draw the same six diagrams |

`pyproject.toml` copies `docs/guide.md` and `skills/` into the wheel under `penflow/_data/`.

**Render pipeline:** `Diagram.layout()` measures with `ctx.size(node)`, then places with `node.layout(x, y, w, h)`, which sets every `node.rect`. `render()` then draws nodes in tree order, each with its own seed, and draws edges last. `check()` runs on the same layout.

## Rules

- **No runtime dependencies.** The library is pure Python 3.11+. Dev tools go in `[dependency-groups] dev` with `uv add --dev`.
- **Types stay strict in both checkers.**
  - Options are `Literal` aliases, and modifiers return `Self`.
  - When an attribute holds a Literal value, assign it on its own line with its type (`self.side: TrackSide = side`). Tuple assignments widen the type to `str` in pyright.
  - Don't use `# type: ignore` without an error code. pyright ignores those comments here (`enableTypeIgnoreComments = false`), so use `# pyright: ignore[rule]` for it.
- **Keep drawing stable.** Seeds are per node path (`seed/0.1.2`), so editing one node doesn't redraw the others. Don't add `rnd` calls to existing draw methods without a reason: that changes every existing diagram's wobble.
- **Report user mistakes with messages that say what to do.** Unknown lanes, unknown meanings, nodes used twice, or nodes missing from the tree should raise `ValueError`, and the message should name the fix.
- **Keep the agent-facing text in sync.** If you change a public signature or behavior, update `docs/guide.md`, the skill and the README; for the DSL, also `docs/language.md` and, if Mermaid conversion changes, `docs/mermaid.md`. `api` updates itself, but the guide doesn't. The guide's ```python and ```Penflow blocks, the skill's fence and every Mermaid/sketch pair in `docs/mermaid.md` run in the tests, so a stale example fails.
- **Word `check` fixes both ways.** A new check in `lint.py` gives its fix with `fix(python_text, dsl_text)`, so diagrams written as fences get DSL advice.

## Adding things

- **A node:** subclass `Node`. Implement `_measure(ctx) -> (w, h)`, `_layout(ctx)` (place your children inside `self.rect`), `draw(cv, ctx)` (draw only yourself, not your children), and `children()` and `tones()` if it has any. Export it in `__init__.py`, add it to a section in `reference.SECTIONS`, and test it in `tests/test_nodes.py`.
- **A DSL block:** add its keyword to `dsl/syntax.py`, a builder in `dsl/blocks.py` (registered in `BLOCK_BUILDERS`), a row in `docs/language.md` and a test in `tests/test_dsl.py`.
- **An idea:** add a function in `ideas.py` that only composes existing nodes and returns a node. Add an input alias such as `BoxSpec` if the argument shape is new, a row in the guide's "Pick the shape" table, and a recipe.
- **A check:** add it in `lint.py`, plus its `Code` literal, a line in the module docstring, a row in the guide's "Mistakes" table, and a test that builds the bad case and expects the code.
