---
penflow:
  meanings: {loyal: cyan, traitor: orange, attack: slate, retreat: rust, current: cyan, paused: rust, stale: orange}
---

# demo, in Penflow

The six diagrams from `examples/demo.py`, written as `penflow` fences (see
[docs/language.md](../docs/language.md)). They draw exactly the same SVGs as the Python
versions, and a test keeps it that way.

    uv run python -m penflow render examples/demo_penflow.md --no-write --gallery out/penflow.html

```penflow
---
id: fencing
caption: A lease can't stop a paused client; a storage that checks the lock's revision can.
headline: a lease can't stop a client that's paused
note: the storage must check the token (the lock's revision)
legend: true
title: Client A takes the lock at revision 10, then pauses for GC. Its lease expires; client B takes the lock at revision 11 and writes with token 11. A wakes and writes with token 10; the storage rejects it because 10 is older than 11.
---
sequence_diagram
  participant client_a[client A]:::paused
  participant etcd
  participant client_b[client B]:::current
  participant storage
  client_a ->> etcd: ① lock (rev 10)
  note client_a: ② GC pause… :::paused {bar: 4}
  note etcd: ③ lease expires, lock freed :::soft
  client_b ->> etcd: ④ lock (rev 11) :::current
  client_b ->> storage: ⑤ write, token 11 :::current
  note client_a: ⑥ wakes up, still thinks\nit holds the lock :::paused
  client_a -x storage: ⑦ write, token 10 :::stale {note: "10 < 11: rejected"}
```

```penflow
---
id: tool_map
caption: The whole tool on one page. Each box is one phase of this post.
title: exec.bpf.c is compiled by clang into exec.bpf.o, which bpf2go embeds into execwatch. execwatch loads the program, the verifier checks it, it attaches to a tracepoint and events come back through a ring buffer.
---
col {gap: 70, align: end}
  flow lr
    bpf_c[exec.bpf.c | kernel half, C] -->|clang| bpf_o[exec.bpf.o | bytecode + BTF] -->|bpf2go| execwatch[execwatch | Go, user half]:::accent
  region kernel
    flow lr
      verifier[verifier | phase 4] -->|attach| tracepoint[tracepoint | phase 2] -->|events| ring[ring buffer | phase 5]
execwatch.at(0.15, 1) -->|load| verifier
ring -.->|read| execwatch
```

```penflow
---
id: three_generals
caption: L1 gets the same two messages whoever the traitor is.
headline: "same messages both times: L1 can't tell who lied"
note: "3 generals can't survive 1 traitor: you need n ≥ 3m + 1"
legend: true
title: "Case 1: the commander is the traitor; case 2: L2 is. In both, L1 hears attack and retreat."
---
template generals(cmd_role, l2_role, to_l2)
  col {gap: 14}
    pad {bottom: 46}
      cmd[commander | $cmd_role]:::$cmd_role
    row {gap: 50}
      l1[L1 | loyal]:::loyal
      l2[L2 | $l2_role]:::$l2_role
    label round 2: “C said retreat” :::retreat {size: 13}
    hears[L1 hears: attack + retreat]:::attack {size: 13, dashed}
  cmd -->|attack| l1 :::attack {label_side: left}
  cmd -->|$to_l2| l2 :::$to_l2
  l2 --> l1 :::retreat
compare
  panel case 1: the commander lies :::traitor
    use generals as c1 {cmd_role: traitor, l2_role: loyal, to_l2: retreat}
  panel case 2: L2 lies :::traitor
    use generals as c2 {cmd_role: loyal, l2_role: traitor, to_l2: attack}
```

```penflow
---
id: alert_timeline
caption: The incident, re-created on purpose. Both issues opened, then closed themselves.
headline: "that morning, the same failure: 20+ minutes, no alert"
title: At 0 s a job is queued with KEDA at zero; issues open at 27 s and 326 s; both close at 453 s.
---
timeline
  0: KEDA → 0\njob queued
  27: 27 s: keda-not-ready :::bad
  326: 326 s: queue-stuck :::bad
  453: 453 s: both closed\nrun succeeds
```

```penflow
---
id: quorum_overlap
caption: Any two majorities share a node.
headline: N3 is in both, so B always reaches someone who saw x=1
note: "3 + 3 > 5: two majorities of 5 can't avoid each other"
---
overlap
  n1[N1] n2[N2] n3[N3]:::good n4[N4] n5[N5]
  set n1..n3: quorum A wrote x=1 :::attack
  set n3..n5: quorum B is asked later :::retreat {side: bottom}
```

```penflow
---
id: shapes
caption: "Ideas compose: each is a node, so they nest."
headline: steps · stack · hub in a region · table
legend: true
---
col {gap: 30}
  split
    col {gap: 24}
      steps
        propose
        replicate
        commit
      stack
        etcd_api[etcd API]
        raft
        wal[WAL + snapshot]
    region one node
      hub leader
        f1
        f2
        f3
        f4
  table
    | threat | status | why |
    |---|---|---|
    | T1 | open :::bad | no fix yet |
    | T2 | closed :::good | seq guard |
```
