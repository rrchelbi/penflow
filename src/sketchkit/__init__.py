"""sketchkit: composable hand-drawn SVG diagrams that explain one idea each.

    from sketchkit import *

    a, b = Box("client"), Box("server")
    svg = Diagram(Row(a, b, gap=90), edges=[Arrow(a, b, "request")],
                  headline="one request, one answer").svg()

Layers: `core` (the pen and the canvas), `nodes` (composable parts and layout),
`ideas` (common explanation shapes built from nodes), `publish` (Markdown).
"""

from .core import FONTS, PALETTES, TONES, Canvas, FontName, PaletteName, Point, ToneName, escape, figure, insert
from .ideas import (BoxSpec, CellSpec, EventSpec, ItemSpec, PanelSpec, SetSpec, compare, flow, hub, overlap, sequence,
                    stack, steps, table, timeline)
from .nodes import (DEFAULT_MEANINGS, Act, Align, Arrow, At, Box, Bracket, BracketSide, Cell, Child, Circle, Col,
                    Diagram, Dot, Edge, Free, Gap, Grid, Headline, Justify, Label, LabelSide, LaneRow, Lanes, LaneSpec,
                    Legend, Line, Mark, MarkKind, MeaningSpec, Msg, Node, Note, Overlay, Pad, Port, Rect, Ref, Region,
                    ResolvedTone, Route, Row, Spacer, Split, Step, Style, TextAlign, Theme, TickMark, ToneRef, Track,
                    TrackSide)
from .publish import Builder, Doc, Drawing, Rendered, gallery, run, to_svg

__all__ = [
    # core
    "Canvas", "TONES", "PALETTES", "FONTS", "figure", "insert", "escape",
    # nodes
    "Node", "Port", "Diagram", "DEFAULT_MEANINGS",
    "Label", "Headline", "Note", "Step", "Box", "Cell", "Circle", "Dot", "Mark", "Spacer", "Free",
    "Row", "Col", "Split", "Grid", "Overlay", "Pad", "Region", "Legend",
    "Track", "At", "Lanes", "Msg", "Act", "Gap",
    "Arrow", "Line", "Bracket",
    # ideas
    "flow", "stack", "timeline", "sequence", "compare", "table", "overlap", "steps", "hub",
    # publish
    "Doc", "run", "gallery", "to_svg", "Rendered", "Builder", "Drawing",
    # types
    "ToneName", "FontName", "PaletteName", "Point", "Rect", "Style", "Theme", "ResolvedTone", "ToneRef",
    "MeaningSpec", "Align", "Justify", "TextAlign", "TrackSide", "TickMark", "LabelSide", "BracketSide", "Route",
    "MarkKind", "Child", "Ref", "LaneSpec", "LaneRow", "Edge",
    "BoxSpec", "EventSpec", "PanelSpec", "CellSpec", "ItemSpec", "SetSpec",
]
