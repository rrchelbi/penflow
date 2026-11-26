"""Mermaid in, Penflow out.

Each output line remembers the Mermaid line it came from, so errors and check issues point into the
Mermaid source. Anything approximated is listed in `notes` and as %% comments at the top.
"""

from __future__ import annotations

import re
from typing import Final

from ..dsl.errors import SketchError
from .common import Converted, Output, clean, statements
from .flowchart import convert_flowchart
from .sequence import convert_sequence
from .timeline import convert_timeline

CLOSEST: Final[dict[str, str]] = {
    "gantt": "timeline", "gitgraph": "timeline", "pie": "table", "journey": "steps", "mindmap": "hub",
    "statediagram": "flow (states as nodes, transitions as edges)",
    "statediagram-v2": "flow (states as nodes, transitions as edges)",
    "classdiagram": "grid of boxes", "erdiagram": "grid of boxes, with edges", "quadrantchart": "grid",
    "xychart-beta": "table", "sankey-beta": "flow", "block-beta": "grid", "requirementdiagram": "flow",
    "c4context": "regions with a flow inside", "architecture-beta": "regions with a flow inside",
    "kanban": "split with a stack per column", "packet-beta": "table",
}


def convert_mermaid(text: str) -> Converted:
    """Convert one Mermaid diagram to Penflow text. Raises SketchError (with the Mermaid line) for
    diagram types Penflow doesn't draw."""
    out = Output()
    body = text.replace("\r\n", "\n")
    lines = body.split("\n")
    skip = 0
    if lines and lines[0].strip() == "---":  # Mermaid front matter: title is kept, config isn't
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            raise SketchError(1, "the Mermaid front matter has no closing ---")
        for ln in lines[1:end]:
            m = re.match(r"title:\s*(.+)", ln.strip())
            if m:
                out.headline = clean(m.group(1))
            elif ln.strip() and not ln.startswith((" ", "\t")):
                out.note(f"front matter '{ln.strip().split(':')[0]}' dropped")
        skip = end + 1
    stmts = [(s, no) for s, no in statements("\n".join(lines[skip:])) if not s.startswith("%%{")]
    stmts = [(s, no + skip) for s, no in stmts]
    if any(s.startswith("%%{") for s in lines):
        out.note("%%{init}%% directives dropped")
    if not stmts:
        raise SketchError(1, "the Mermaid text is empty")
    head, line = stmts[0]
    kind = head.split()[0]
    low = kind.lower()
    if low in ("flowchart", "graph"):
        convert_flowchart(head, stmts[1:], out, line)
    elif low == "sequencediagram":
        convert_sequence(stmts[1:], out, line)
    elif low == "timeline":
        convert_timeline(stmts[1:], out, line)
    elif low in CLOSEST:
        raise SketchError(line, f"Mermaid {kind} isn't drawn by Penflow; the closest penflow block is "
                                f"{CLOSEST[low]}")
    else:
        raise SketchError(line, f"{kind!r} isn't a Mermaid diagram type Penflow knows; it converts flowchart, "
                                "graph, sequenceDiagram and timeline")
    return out.done()
