# Contributing to sketchkit

Thanks for helping. sketchkit is small on purpose: pure Python, no runtime dependencies, one idea per drawing. Contributions that keep it that way are the easiest to merge.

## Before you start

- **Bugs:** open an issue with the smallest script that shows the problem, the SVG it produced (or a screenshot), and what you expected. If `python -m sketchkit check` reports something wrong, or misses something, include its output.
- **New features:** open an issue first for anything bigger than a fix, such as a new node, idea or check. A short sketch of the API you have in mind is enough. It saves you writing code that doesn't fit.
- **Small fixes** (typos, docs, clear bugs) can go straight to a pull request.

## Setup

sketchkit uses [uv](https://docs.astral.sh/uv/), not pip.

```bash
git clone git@github.com:rrchelbi/sketchkit.git
cd sketchkit
uv sync            # creates .venv with pytest, mypy and pyright
```

Requires Python 3.11 or newer.

## The four checks

Run all of these before opening a pull request. A change isn't done until they all pass.

```bash
uv run pytest                                                         # tests, including every code block in guide.md
uv run mypy                                                           # strict
uv run pyright                                                        # strict
uv run python -m sketchkit check examples/demo.py --gallery out/check.html
```

Then open `out/check.html` and look at the diagrams. Text widths are estimated rather than measured, so the checker can't catch everything. If your change affects drawing, say in the pull request which diagrams you looked at.

## How the code is organised

[AGENTS.md](AGENTS.md) is the reference for working on the library. It covers the file layout, the render pipeline, and step-by-step lists for adding a node, an idea or a check. Read it before changing anything in `src/`. The short version:

- **No runtime dependencies.** Dev tools go in the `dev` group: `uv add --dev <tool>`.
- **Types stay strict** in both mypy and pyright. Options are `Literal` aliases and modifiers return `Self`. Use `# pyright: ignore[rule]` and `# type: ignore[code]`, never a bare ignore.
- **Keep drawing stable.** Randomness is seeded per node, so editing one box doesn't redraw the others. Don't add `rnd` calls to existing draw methods unless you mean to change every existing diagram's wobble, and say so in the pull request if you do.
- **Errors say what to do.** User mistakes raise `ValueError` with a message that names the fix.
- **Docs move with the code.** If you change a public signature or behaviour, update `src/sketchkit/guide.md`, the skill (`src/sketchkit/skills/sketch-diagrams/SKILL.md`) and the README. The guide's code blocks run as tests, so stale examples fail.

## Tests

- Node and layout tests live in `tests/test_nodes.py`. The CLI, guide and skill are tested in `tests/test_agents.py`.
- A new check needs a test that builds the bad diagram and expects the check's code.
- Prefer asserting on layout (`node.rect`) and `check()` issues over comparing whole SVG strings, which change whenever the drawing does.

## Pull requests

- Keep each pull request to one change. A refactor and a feature are two pull requests.
- Write commit messages as a short summary line in the imperative ("Add bracket labels on the left side"), with a body if the why isn't obvious.
- Describe what changed, why, and how you checked it. Include a before/after image for any visual change.
- Don't commit generated files: `out/`, `dist/`, `.venv/` and caches are already in `.gitignore`.

## Using an AI agent

You're welcome to. `CLAUDE.md` imports `AGENTS.md`, so Claude Code picks up the rules above automatically. You're still responsible for the change: run the four checks and look at the output yourself.
