"""Mermaid `timeline` to a `timeline` block."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..dsl.errors import SketchError
from .common import Output, clean, quote_tail


def convert_timeline(stmts: Sequence[tuple[str, int]], out: Output, line: int) -> None:
    periods: list[tuple[str, list[str], int]] = []
    for s, no in stmts:
        low = s.split()[0].lower()
        if low == "title":
            out.headline = clean(s[5:])
        elif low == "section":
            out.note("timeline sections dropped")
        elif s.startswith(":"):
            if not periods:
                raise SketchError(no, "an event line starts with : but there's no period above it")
            periods[-1][1].extend(clean(x) for x in s[1:].split(":") if x.strip())
        else:
            label, *events = s.split(":")
            periods.append((clean(label), [clean(x) for x in events if x.strip()], no))
    if not periods:
        raise SketchError(line, "the timeline has no periods")
    numeric = all(re.fullmatch(r"-?\d+(\.\d+)?", p[0]) for p in periods)
    if not numeric:
        out.note("period names aren't numbers, so periods are spaced evenly")
    out.add("timeline", line)
    for k, (label, events, no) in enumerate(periods):
        value = label if numeric else str(k)
        shown = "\n".join([label, *events])  # the axis has no tick labels, so the period goes in the text
        out.add(f"  {value}: {quote_tail(shown)}", no)
