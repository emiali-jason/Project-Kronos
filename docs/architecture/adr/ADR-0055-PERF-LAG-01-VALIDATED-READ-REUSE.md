# ADR-0055 — PERF/LAG-01 validated read reuse

**Status:** Sponsor/EA authorized engineering; release separately gated.
**Authority:** PERF/LAG-01 overnight engineering order, 2026-09-13.
**Scope:** Read mechanics only; publication and runtime deployment remain separate.

## Decision

Preserve evidence, validation strength, authority and governed outputs while
removing diagnosed repeated reconstruction. No analytical or trading policy
changes. ADR-0016 Swing observation authority and ADR-0050 startup/runtime
boundaries remain authoritative and are not superseded.

Swing Journal and Reports construct one validated operational handoff population.
A pure completion-date projection applies the existing governed calendar to that
same population. It changes only the operational routing field. It does not
perform another synchronization, retain evidence, or reconstruct track history.
A V2 ledger snapshot also loads its V1 source population once and still applies
the exact existing source-binding checks separately to every V2 record.

Intraday Review snapshot validates currentness once inside its existing Review
workspace and Probables generation locks. It still reloads and checks the current
Review pointer against the verified producer identity before loading the snapshot.
The Review page supplies its successful immutable snapshot to status rendering
instead of reconstructing it again. The status control still independently checks
currentness; failed/empty snapshots use its existing error path. Opportunities
uses the snapshot’s own currentness gate. No global Browser lock is introduced.
Other independent reads retain their checks.

## Exact-byte validation reuse

Probables typed artifact loads and Swing retained paper market-fact loads retain a
bounded, process-local LRU of successful immutable validation results. Every load
still opens/reads the requested file using the existing persistence read boundary.
Path metadata, modification time, inode and size never substitute for bytes.
Directory discovery, mutable pointers, lineage traversal and projection remain
live reads. Existing no-follow readers are unchanged.

Reuse requires the exact lexical path, SHA-256 of newly read bytes, equality of
those bytes, and the validator domain token. Probables tokens bind decoder,
integrity functions, expected type, enum registry and typed constructor registry.
Swing tokens bind store schema, contract and policy versions, fact constructor and
its validator, decoder, canonical digest and normalization functions. Versions and
identity fields inside artifacts are additionally bound by complete byte equality.
All transitive validator code is startup-pinned process source; live patching of
production code is not supported. A source revision load requires a new process
and therefore an empty cache. Dynamically acquired policy evidence is not cached
by this utility; its owning readers still establish current authority.

Identity checks and cross-artifact lineage checks run after reuse. Only recursively
immutable values are retained: frozen dataclasses, immutable scalar fields and
tuples. Mutable mappings/lists or mutable dataclass members bypass retention.
Failures are never retained. Disappeared files cannot be served from reuse. A
corrupt or replaced file is decoded/validated anew and fails by its existing rule.
A removed directory member is absent on the next enumeration, as before.

Capacity is bounded by both input bytes (64 MiB) and entry count (4,096 Probables;
32,768 Swing facts per store). LRU eviction causes ordinary revalidation. Thirty-two
striped locks coalesce identical concurrent validation; a short accounting lock
never covers I/O or validation. Cache values are not written to disk, and no raw
WebSocket history is newly persisted. This is reuse of already-retained records,
not a new market-data collector or authority.

## Bounded current-state access and residual costs

The current Review pointer remains the access path. No replacement current index
or historical rewrite is introduced. Latest evaluable Probables still checks the
existing run population because the current producer pointer alone does not prove
which retained run is the latest evaluable run. Swing still enumerates and reads
its exact retained fact population. Skipping those bytes using file metadata would
weaken unexpected-change detection and is not commissioned to meet a time target.

## Qualification and release

Require exact projection equivalence, deterministic construction/validation counts,
changed-byte/schema/identity/policy/pointer and disappearance/corruption tests,
concurrent reuse, restart/eviction and existing no-follow regressions. Measure warm
and cold-ish behavior on the same retained source population in isolation. Retain
route, filesystem, multitab and residual-cost evidence under the external
`output/PERF-LAG-01/engineering/` qualification directory. No qualification process
may invoke production operations or load candidate code into the canonical app.
