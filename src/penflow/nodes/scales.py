"""Nodes laid out along a scale: timelines (Track) and sequence diagrams (Lanes)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import TypeAlias

from ..core import Canvas
from .base import Child, Ctx, MarkKind, Node, Size, TickMark, ToneRef, TrackSide, classes
from .leaves import Box, Label, node


class At:
    """An event on a Track: its value on the axis and what to show there."""

    def __init__(self, value: float, item: Child, side: TrackSide = "above", level: int = 0,
                 tone: ToneRef | None = None, mark: TickMark | None = None) -> None:
        self.value, self.level, self.tone = value, level, tone
        self.side: TrackSide = side
        self.mark: TickMark = mark if mark is not None else ("dot" if tone else "circle")
        self.item: Node = Label(item, size=13, tone=tone, bold=bool(tone)) if isinstance(item, str) else node(item)


class Track(Node):
    """A horizontal axis with things placed by value: the base of timelines and scales."""

    def __init__(self, *events: At, start: float | None = None, end: float | None = None,
                 length: float = 480, axis: bool = True) -> None:
        self.events = list(events)
        vals = [e.value for e in self.events] or [0.0, 1.0]
        self.start = min(vals) if start is None else start
        self.end = max(vals) if end is None else end
        self.length, self.axis = length, axis

    def children(self) -> Sequence[Node]:
        return [e.item for e in self.events]

    def tones(self) -> Iterable[ToneRef]:
        return tuple(e.tone for e in self.events if e.tone)

    def _bands(self, ctx: Ctx) -> dict[TrackSide, list[float]]:
        bands: dict[TrackSide, dict[int, float]] = {"above": {}, "below": {}}
        for e in self.events:
            h = ctx.size(e.item)[1]
            bands[e.side][e.level] = max(bands[e.side].get(e.level, 0.0), h)
        return {s: [b.get(i, 0.0) for i in range(max(b) + 1)] if b else [] for s, b in bands.items()}

    @staticmethod
    def _band_h(hs: Sequence[float]) -> float:
        return sum(hs) + 6 * max(0, len(hs) - 1) + (10 if hs else 0)

    def _measure(self, ctx: Ctx) -> Size:
        b = self._bands(ctx)
        widest = max([ctx.size(e.item)[0] for e in self.events] or [0.0])
        return (max(self.length, widest), self._band_h(b["above"]) + 24 + self._band_h(b["below"]))

    def x(self, value: float) -> float:
        """Where `value` sits on the axis (after layout)."""
        x, _, w, _ = self.rect
        span = (self.end - self.start) or 1
        return x + 12 + (w - 36) * (value - self.start) / span

    def axis_y(self, ctx: Ctx) -> float:
        return self.rect[1] + self._band_h(self._bands(ctx)["above"]) + 12

    def _layout(self, ctx: Ctx) -> None:
        x, _, w, _ = self.rect
        b, ay = self._bands(ctx), self.axis_y(ctx)
        for e in self.events:
            cw, ch = ctx.size(e.item)
            cx = min(max(self.x(e.value) - cw / 2, x), x + w - cw)
            off = sum(b[e.side][: e.level]) + 6 * e.level
            cy = ay - 22 - off - ch if e.side == "above" else ay + 22 + off
            e.item.layout(cx, cy, cw, ch, ctx)

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        x, _, w, _ = self.rect
        ay = self.axis_y(ctx)
        if self.axis:
            cv.arrow(x, ay, x + w, ay, "stroke-soft", head=10)
        for e in self.events:
            c, ex = classes(ctx.tone(e.tone)), self.x(e.value)
            cv.line(ex, ay - 10, ex, ay + 10, c["stroke"], passes=1)
            if e.mark == "dot":
                cv.dot(ex, ay, 5, c["solid"])
            elif e.mark == "circle":
                cv.circle(ex, ay, 5, c["stroke"], "fill-surface")


class LaneRow(ABC):
    """One row of a sequence diagram."""

    tone: ToneRef | None = None

    @abstractmethod
    def height(self) -> float: ...

    def lanes(self) -> tuple[str, ...]:
        """The lanes this row refers to, checked against the diagram's lanes."""
        return ()


class Msg(LaneRow):
    """A message between two lanes. `mark` ("cross"/"check") lands at the receiver;
    `note` is a short line under the arrow at the receiving end."""

    def __init__(self, src: str, dst: str, label: str = "", tone: ToneRef | None = None,
                 mark: MarkKind | None = None, note: str | None = None) -> None:
        if src == dst:
            raise ValueError("a Msg needs two different lanes; use Act for a lane's own step")
        self.src, self.dst, self.label, self.tone, self.note = src, dst, label, tone, note
        self.mark: MarkKind | None = mark

    def height(self) -> float:
        return 40 + (20 if self.note else 0)

    def lanes(self) -> tuple[str, ...]:
        return (self.src, self.dst)


class Act(LaneRow):
    """Something a lane does or thinks, written beside its lifeline. `bar=n` draws a
    solid line on the lifeline over this row and the next n-1 rows (a pause, a hold)."""

    def __init__(self, lane: str, text: str, tone: ToneRef | None = None, bar: int = 0) -> None:
        self.lane, self.text, self.tone, self.bar = lane, text, tone, bar

    def height(self) -> float:
        return 18 * len(self.text.split("\n")) + 12

    def lanes(self) -> tuple[str, ...]:
        return (self.lane,)


class Gap(LaneRow):
    def __init__(self, h: float = 20) -> None:
        self.h = h

    def height(self) -> float:
        return self.h


LaneSpec: TypeAlias = "str | tuple[str, ToneRef | None]"
"""A lane name, or (name, tone) to tint its head."""


class Lanes(Node):
    """A sequence diagram: lane heads, dashed lifelines and rows of Msg / Act / Gap.
    lanes["storage"] is that lane's head box, for edges from outside."""

    def __init__(self, lanes: Sequence[LaneSpec], rows: Iterable[LaneRow], col: float | None = None,
                 head_size: float = 15) -> None:
        if not lanes:
            raise ValueError("Lanes needs at least one lane")
        self.names: list[str] = []
        self.heads: dict[str, Box] = {}
        for ln in lanes:
            name, tone = ln if isinstance(ln, tuple) else (ln, None)
            self.names.append(name)
            self.heads[name] = Box(name, size=head_size).tone(tone)
        self.rows, self.col = list(rows), col
        self._ys: list[float] = []
        for r in self.rows:
            for lane in r.lanes():
                if lane not in self.heads:
                    raise ValueError(f"unknown lane {lane!r}; lanes are {self.names}")

    def __getitem__(self, name: str) -> Box:
        return self.heads[name]

    def children(self) -> Sequence[Node]:
        return [self.heads[n] for n in self.names]

    def tones(self) -> Iterable[ToneRef]:
        return tuple(r.tone for r in self.rows if r.tone)

    def _col(self, ctx: Ctx) -> float:
        return self.col or max(130, max(ctx.size(b)[0] for b in self.heads.values()) + 24)

    def _measure(self, ctx: Ctx) -> Size:
        return (self._col(ctx) * len(self.names), 40 + 30 + sum(r.height() for r in self.rows) + 10)

    def lane_x(self, name: str) -> float:
        x, _, w, _ = self.rect
        return x + w / len(self.names) * (self.names.index(name) + 0.5)

    def _layout(self, ctx: Ctx) -> None:
        _, y, w, _ = self.rect
        col = w / len(self.names)
        for n in self.names:
            hw = min(col - 16, max(110, ctx.size(self.heads[n])[0]))
            self.heads[n].layout(self.lane_x(n) - hw / 2, y, hw, 40, ctx)
        cur, self._ys = y + 70, []
        for r in self.rows:
            self._ys.append(cur)
            cur += r.height()

    def draw(self, cv: Canvas, ctx: Ctx) -> None:
        _, y, _, h = self.rect
        for n in self.names:
            lx, yy = self.lane_x(n), y + 48
            while yy < y + h:
                cv.line(lx, yy, lx, min(yy + 9, y + h), "stroke-soft", rough=0.5, passes=1)
                yy += 16
        ends = self._ys[1:] + [y + h - 10]
        for i, (r, top) in enumerate(zip(self.rows, self._ys, strict=True)):
            c = classes(ctx.tone(r.tone))
            if isinstance(r, Msg):
                x1, x2, ay = self.lane_x(r.src), self.lane_x(r.dst), top + 26
                d = 1 if x2 > x1 else -1
                cv.arrow(x1 + 4 * d, ay, x2 - 4 * d, ay, c["stroke"], head=9)
                if r.label:
                    cv.text((x1 + x2) / 2, ay - 8, r.label, 13, c["text"], halo=True)
                mark_cls = c["stroke"] if r.tone else "stroke-accent"
                if r.mark == "cross":
                    cv.cross(x2 - 30 * d, ay, 6, mark_cls)
                elif r.mark == "check":
                    cv.check(x2 - 30 * d, ay, mark_cls)
                if r.note:
                    cv.text(x2 - 8 * d, ay + 26, r.note, 13, c["text"], "end" if d > 0 else "start",
                            weight=700, halo=True)
            elif isinstance(r, Act):
                lx = self.lane_x(r.lane)
                right = self.names.index(r.lane) < len(self.names) - 1 or len(self.names) == 1
                for j, line in enumerate(r.text.split("\n")):
                    cv.text(lx + (8 if right else -8), top + 16 + 18 * j, line, 13, c["text"],
                            "start" if right else "end", halo=True)
                if r.bar:
                    bottom = ends[min(i + r.bar - 1, len(ends) - 1)]
                    cv.line(lx, top, lx, bottom, c["stroke"])
