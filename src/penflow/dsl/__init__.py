"""Penflow: diagrams written as ```penflow fences in Markdown (docs/language.md).

    ```penflow
    ---
    headline: one request, one answer
    ---
    row {gap: 90}
      client
      server[server | handles it]
    client -->|request| server
    ```

A fence compiles to the same node tree the Python API builds, so layout, checks and
rendering are shared. Every word the DSL defines is snake_case, and so are ids.
"""

from .errors import SketchError, snake
from .frontmatter import Settings, file_settings
from .layered import Ranked, layers
from .markdown import Fence, SketchDoc, fences
from .parse import Sketch, parse_sketch
from .templates import Template

__all__ = [
    "Fence",
    "Ranked",
    "Settings",
    "Sketch",
    "SketchDoc",
    "SketchError",
    "Template",
    "fences",
    "file_settings",
    "layers",
    "parse_sketch",
    "snake",
]
