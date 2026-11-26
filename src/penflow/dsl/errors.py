"""The error every DSL mistake raises, and the snake_case rule."""

from __future__ import annotations

import re


class SketchError(ValueError):
    """A mistake in a penflow fence. `line` counts from the top of the file (or text) given."""

    def __init__(self, line: int, message: str, where: str = "") -> None:
        self.line, self.message, self.where = line, message, where
        super().__init__(f"{where}:{line}: {message}" if where else f"line {line}: {message}")

    def at(self, where: str) -> SketchError:
        return SketchError(self.line, self.message, where)


def snake(word: str) -> str:
    """The snake_case spelling of a word: sequenceDiagram -> sequence_diagram."""
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", word)
    return re.sub(r"[^a-z0-9_]", "_", s.lower()).strip("_") or "x"
