"""Mermaid in, Penflow out (docs/mermaid.md).

    convert_mermaid("flowchart LR\\n  A[client] -->|request| B[server]").text
    # flow lr
    #   a[client] -->|request| b[server]

Covers flowchart/graph, sequenceDiagram and timeline. Other diagram types raise a
SketchError that names the closest penflow block.
"""

from .common import Converted
from .convert import convert_mermaid

__all__ = ["Converted", "convert_mermaid"]
