"""Four diagrams from the write-ups, rebuilt with the composable API, plus one
of each idea shape. No coordinates anywhere.

    uv run python examples/demo.py --no-write --gallery out/gallery.html
"""

import pathlib

from sketchkit import (
    Act,
    Arrow,
    Box,
    Col,
    Diagram,
    Doc,
    Label,
    Msg,
    Pad,
    Region,
    Row,
    Split,
    compare,
    flow,
    hub,
    overlap,
    run,
    sequence,
    stack,
    steps,
    table,
    timeline,
)

HERE = pathlib.Path(__file__).parent
raft = Doc(HERE / "demo.md", meanings={
    "loyal": "cyan", "traitor": "orange", "attack": "slate", "retreat": "rust",
    "current": "cyan", "paused": "rust", "stale": "orange",
})


@raft.diagram("fencing", "A lease can't stop a paused client; a storage that checks the lock's revision can.")
def fencing() -> Diagram:
    return Diagram(
        sequence(
            [("client A", "paused"), "etcd", ("client B", "current"), "storage"],
            Msg("client A", "etcd", "① lock (rev 10)"),
            Act("client A", "② GC pause…", tone="paused", bar=4),
            Act("etcd", "③ lease expires, lock freed", tone="soft"),
            Msg("client B", "etcd", "④ lock (rev 11)", tone="current"),
            Msg("client B", "storage", "⑤ write, token 11", tone="current"),
            Act("client A", "⑥ wakes up, still thinks\nit holds the lock", tone="paused"),
            Msg("client A", "storage", "⑦ write, token 10", tone="stale", mark="cross", note="10 < 11: rejected"),
        ),
        headline="a lease can't stop a client that's paused",
        note="the storage must check the token (the lock's revision)",
        legend=True,
        title="Client A takes the lock at revision 10, then pauses for GC. Its lease expires; client B takes the "
              "lock at revision 11 and writes with token 11. A wakes and writes with token 10; the storage "
              "rejects it because 10 is older than 11.",
    )


@raft.diagram("tool-map", "The whole tool on one page. Each box is one phase of this post.")
def tool_map() -> Diagram:
    ver, tp, ring = Box("verifier", "phase 4"), Box("tracepoint", "phase 2"), Box("ring buffer", "phase 5")
    build = flow(("exec.bpf.c", "kernel half, C"), ("exec.bpf.o", "bytecode + BTF"),
                 Box("execwatch", "Go, user half").tone("accent"), labels=["clang", "bpf2go"])
    binary = build.items[-1]
    kernel = Region("kernel", flow(ver, tp, ring, labels=["attach", "events"]))
    return Diagram(
        Col(build, kernel, gap=70, align="end"),
        edges=[Arrow(binary.at(0.15, 1), ver, "load"),
               Arrow(ring, binary, "read", dashed=True)],
        title="exec.bpf.c is compiled by clang into exec.bpf.o, which bpf2go embeds into execwatch. execwatch "
              "loads the program, the verifier checks it, it attaches to a tracepoint and events come back "
              "through a ring buffer.",
    )


def generals(commander_lies: bool) -> Col:
    """One case of the three-generals argument; used twice by compare()."""
    cmd = Box("commander", "traitor" if commander_lies else "loyal").tone("traitor" if commander_lies else "loyal")
    l1 = Box("L1", "loyal").tone("loyal")
    l2 = Box("L2", "loyal" if commander_lies else "traitor").tone("loyal" if commander_lies else "traitor")
    hears = Box("L1 hears: attack + retreat", size=13).tone("attack").dashed()
    to_l2 = "retreat" if commander_lies else "attack"
    said = Label("round 2: “C said retreat”", size=13, tone="retreat")
    return Col(Pad(cmd, bottom=46), Row(l1, l2, gap=50), said, hears, gap=14).link(
        Arrow(cmd, l1, "attack", tone="attack", label_side="left"),
        Arrow(cmd, l2, to_l2, tone=to_l2),
        Arrow(l2, l1, tone="retreat"),
    )


@raft.diagram("three-generals", "L1 gets the same two messages whoever the traitor is.")
def three_generals() -> Diagram:
    return Diagram(
        compare(("case 1: the commander lies", generals(True), "traitor"),
                ("case 2: L2 lies", generals(False), "traitor")),
        headline="same messages both times: L1 can't tell who lied",
        note="3 generals can't survive 1 traitor: you need n ≥ 3m + 1",
        legend=True,
        title="Case 1: the commander is the traitor; case 2: L2 is. In both, L1 hears attack and retreat.",
    )


@raft.diagram("alert-timeline", "The incident, re-created on purpose. Both issues opened, then closed themselves.")
def alert_timeline() -> Diagram:
    return Diagram(
        timeline((0, "KEDA → 0\njob queued"), (27, "27 s: keda-not-ready", "bad"),
                 (326, "326 s: queue-stuck", "bad"), (453, "453 s: both closed\nrun succeeds")),
        headline="that morning, the same failure: 20+ minutes, no alert",
        title="At 0 s a job is queued with KEDA at zero; issues open at 27 s and 326 s; both close at 453 s.",
    )


@raft.diagram("quorum-overlap", "Any two majorities share a node.")
def quorum() -> Diagram:
    return Diagram(
        overlap(["N1", "N2", ("N3", "good"), "N4", "N5"],
                (0, 2, "quorum A wrote x=1", "attack", "top"),
                (2, 4, "quorum B is asked later", "retreat", "bottom")),
        headline="N3 is in both, so B always reaches someone who saw x=1",
        note="3 + 3 > 5: two majorities of 5 can't avoid each other",
    )


@raft.diagram("shapes", "Ideas compose: each is a node, so they nest.")
def shapes() -> Diagram:
    return Diagram(
        Col(
            Split(
                Col(steps("propose", "replicate", "commit"), stack("etcd API", "raft", "WAL + snapshot"), gap=24),
                Region("one node", hub("leader", ["f1", "f2", "f3", "f4"])),
            ),
            table([["T1", ("open", "bad"), "no fix yet"], ["T2", ("closed", "good"), "seq guard"]],
                  header=["threat", "status", "why"]),
            gap=30,
        ),
        headline="steps · stack · hub in a region · table",
        legend=True,
    )


if __name__ == "__main__":
    run(raft)
