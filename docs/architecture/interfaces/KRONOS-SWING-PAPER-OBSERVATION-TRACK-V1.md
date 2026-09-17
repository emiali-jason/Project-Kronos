# KRONOS Swing Paper Observation Track V1

**Status:** Approved architecture contract; runtime not started
**Version:** 1
**Contract identity:** `KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1`
**Owner:** Swing Paper Observation Track
**Authority:** Non-position research evidence only
**Governing decision:** ADR-0016

## Purpose

This prospective contract observes the factual market path of one exact
Sponsor `PAPER` decision whose governed Sponsor Position activation is blocked.
It creates no position, objective model, Risk permission, fill, P&L, actual R,
order, execution, or broker authority.

## Mandatory lineage

Creation binds immutable identities and SHA-256 digests for:

- Sponsor Observation Decision and decision-time snapshot;
- run, canonical instrument, assessment, direction, and decision timestamp;
- Step-31 Observation Evidence and policy version;
- exact Entry, Stop, Target, invalidation, availability, warnings, severity,
  reward, risk, and R:R state;
- decision-time DOMAIN-007 identity/state/availability;
- blocked activation disposition; and
- track creation timestamp, provenance, policy, contract, and integrity.

The choice must be `PAPER`; activation must be blocked; Sponsor Position must
be absent. Exact duplicate start is idempotent. Foreign, stale-at-creation,
superseded-at-creation, malformed, corrupt, mismatched, or unsupported evidence
fails closed.

## Explicit Sponsor start

The track begins only after `START PAPER OBSERVATION`. A PAPER decision alone
does not start it. Starting the track is `TRACK STARTED` / `OBSERVATION ACTIVE`,
never `POSITION ACTIVATION`.

## States

Track states are `AVAILABLE`, `ACTIVE`, `MONITORING_INTERRUPTED`, `COMPLETE`,
`OUTCOME_NOT_ESTABLISHED`, and `NOT_APPLICABLE_POSITION_ACTIVATED`.

Outcome states are `ENTRY_NOT_OBSERVED`, `ENTRY_OBSERVED`,
`STOP_LEVEL_TOUCHED`, `TARGET_LEVEL_TOUCHED`,
`BOTH_ORDERING_UNRESOLVED`, `EXPIRED`, and `OUTCOME_NOT_ESTABLISHED`.
`EXPIRED` is reserved and cannot be produced until a later expiry policy is
approved.

## Geometry and events

Step-31 Entry is `OBSERVATION_ENTRY_REFERENCE`. It is not a fill or
Risk-approved execution price. Stop, Target, and invalidation remain exact.
GREEN, AMBER, and RED are eligible if trustworthy; geometry is never repaired.

Entry is observed only from the exact directional condition bound by Step-31.
Stop/Target states are factual level touches after Entry is governably observed
and are not win/loss labels. Ordered observations preserve sequence. Completed
candles may prove bounded containment; unfinished candles cannot establish a
final outcome. Multiple relevant levels inside one interval without independent
ordering produce `BOTH_ORDERING_UNRESOLVED`.

## Monitoring and recovery

The contract may consume governed observations through a dedicated Paper Track
consumer of `SharedSwingMonitoringHub`. It must not reuse KR-380 or Sponsor
Position lifecycle authority. Disconnect becomes `MONITORING_INTERRUPTED`;
bounded historical reconciliation may restore facts but never guess ordering.
Restart restores persisted state idempotently and never creates an event.

Monitoring applicability is a separate prospective contract with exactly
`OPEN`, `SUSPENDED`, and `CLOSED` states:

| State | Operational meaning | Automatic attachment |
| --- | --- | --- |
| `OPEN` | Exact current opportunity/material/assessment/direction/geometry, Review/decision authority, instrument/contract, monitoring boundary, and capability requirements are compatible | Eligible |
| `SUSPENDED` | Provider unavailable, currentness unprovable, compact state missing/stale/corrupt, or explicit recovery required | Prohibited |
| `CLOSED` | Governed operational monitoring ended | Prohibited |

Applicability is independent of factual outcome and cannot create or change
`EXPIRED`, `OUTCOME_NOT_ESTABLISHED`, Stop/Target touches, win/loss,
analytical direction, opportunity history, or Sponsor-position closure. Run
identity alone is not a closure condition. Material incompatibility prevents
automatic restoration.

Legacy tracks receive no backfill. Missing or unprovable applicability projects
ephemerally as `SUSPENDED / RECOVERY_REQUIRED` with
`automatic_restoration = false`; no applicability or recovery record is
created. Startup, Kite Connect, GET, status, and ordinary callbacks do not run
full-history reconstruction, recovery, migration, ledger rebuilding, cleanup,
deletion, or fallback scanning.

The exact current-state restoration projection validates the track, governed
events, monitoring records, and any applicability record it uses. It does not
read, decode, sort, or hash historical market-fact files. A missing or corrupt
compact state fails closed; there is no automatic fallback to those facts.

### Prospective authority publication

The explicit Sponsor start prepares the track and its first `OPEN`
applicability generation together. The generation binds the Track and Sponsor
decision, continuity opportunity and material revision, Native assessment and
direction, Step-31 geometry identity and digest, Review and decision
authorities, canonical instrument and exact Provider derivative contract,
monitoring boundary/window, capability classification, policy identity and
version, and predecessor applicability identity when one exists.

The immutable Track and applicability generation are retained before a single
validated current-applicability pointer is atomically published. Restoration
uses only that pointer. Prepared records without the pointer are inert, so a
failure between writes cannot expose a monitoring owner. Exact replay retains
the same Track, generation, and pointer; a conflicting replay fails closed.

Restoration compares all material authority fields but deliberately excludes
run identity from the compatibility decision. It registers only a nonterminal,
current, `OPEN`, exact-compatible owner under the current active capability.
The selected Provider instrument must reproduce the retained contract identity.
Status reports bounded selection counts and reason codes from this fact-free
projection; it creates no applicability, recovery, or monitoring evidence.

Later analysis-run supersession does not rewrite or terminate the original
hypothesis. `EXPIRY POLICY UNRESOLVED`; open tracks remain explicit.

## Prospective retention

Securities that do not become opportunities are not retained operationally
after Refresh. Only genuine current opportunities are carried forward, with
one compact current state per active opportunity. Ordinary ticks are not
authorized to create individual immutable files.

Persisted material transitions are limited to:

- monitoring opened;
- Entry activated;
- Stop touched;
- Target touched;
- ordering ambiguity;
- Provider/monitoring gap;
- authority superseded;
- Sponsor stopped monitoring; and
- monitoring closed.

Final compact results are retained in the Swing ledger/monthly Excel. Full
historical validation is explicit evidence inspection, audit, research,
governed recovery, or reference-safe cleanup preparation only. Detailed
evidence becomes purge-eligible after finalization, reconciliation, integrity
verification, and reference proof. No historical deletion is authorized by
this contract freeze. Any later cleanup follows: compact verified ledger,
exact external-reference scan, dry-run deletion manifest, Sponsor
authorization, rollback staging, deletion, and final verification.

## Prospective compact tick state (Slice 3)

New explicit admissions use storage generation `KRONOS-PAPER-OBSERVATION-COMPACT-V1`,
schema version `1`, and policy `LATEST-OBSERVATION-BOUNDED-REPLAY-V1`. The immutable
Track wrapper selects the storage generation. An absent generation means legacy
V1; an unknown generation fails closed. No legacy record is migrated or backfilled.

One `current-state.json` binds Track/decision digests, OPEN applicability and full
authority, exact instrument contract and geometry, monitoring generation, complete
latest accepted observation and digest, entry/touch timestamps, ordering outcome,
high/low, coverage boundaries, gap count/head, material-transition head/count,
predecessor checkpoint digest, and checkpoint digest. It excludes tick history.
Track V1 defines no numeric MFE/MAE arithmetic: excursion state is explicitly
`UNAVAILABLE_NOT_DEFINED_BY_TRACK_V1`. No full-path excursion claim is inferred
from sparse observations or coverage gaps.

The complete latest observation includes capability/monitoring generation, Provider
session, sequence, source, observed/received timestamps, exact instrument/contract,
price and every continuity/ordering flag. Within the same generation/session:

| Incoming sequence | Result | Persistence and analytical behavior |
| --- | --- | --- |
| Greater | Existing factual tick rules | Replace checkpoint if accepted; retain only material transitions |
| Equal, all observation fields equal | `EXACT_LATEST_REPLAY` | No replacement, event, registration change or interruption |
| Equal, any observation field differs | `PROVIDER_SEQUENCE_CONFLICT` | Existing interruption behavior; conflicting values never become current |
| Lower, regardless of historical-shaped values | `PROVIDER_HISTORICAL_REPLAY_UNVERIFIABLE` | Reject without file/event, analytical/applicability change or interruption solely due to age |

Prospective compact monitoring guarantees exact replay/conflict recognition for
the latest retained observation. Older observations are safely rejected as
unverifiable because their complete values are intentionally not retained. This
is a deliberate bounded-retention policy, not evidence corruption or a Provider
conflict. Memory-only rejection/duplicate counters saturate at `2**63-1`.
Unsequenced observations use their existing observation boundary conservatively;
older timestamps cannot become current. Generation/session reset requires governed
gap/currentness checks. A connection notification cannot clear factual interruption.

Tick processing uses cached active state. Computation, validation and serialization
precede publication coordination. Under workflow then store coordination, publication
rechecks cached state, captured generation/capability, checkpoint file identity and
applicability pointer identity. Material bytes are durable first; atomic checkpoint
replacement is the visibility boundary; memory advances only afterward. Orphan
transitions from failed replacement are inert. Missing, corrupt, stale or unprovably
interrupted checkpoints yield `SUSPENDED / RECOVERY_REQUIRED` without reconstruction
or repair. Restoration reads only checkpoint, exact Track/current applicability and
exact material head; it never enumerates material-event history or fact history.

Material kinds are `MONITORING_OPENED`, `ENTRY_OBSERVED`, `STOP_LEVEL_TOUCHED`,
`TARGET_LEVEL_TOUCHED`, `BOTH_ORDERING_UNRESOLVED`, `GAP_BEGAN`, `GAP_ENDED`,
`SUSPENDED`, and `CLOSED`. New prices, times, highs/lows are not material events.
Registry names grant no new closure policy or Sponsor action. Terminal checkpoints
cannot advance under later ticks. Monthly ledger/Excel and legacy cleanup remain
deferred.

Explicit full historical projection continues validating every retained legacy fact
and preserves arbitrary historical replay/conflict behavior. Compact operational
paths never fall back to it. Status exposes bounded active-checkpoint, accepted-tick,
material-transition, duplicate/rejection, recovery and inactive-legacy counts without
tick-history reads. GET/startup/restoration never creates checkpoints or converts facts.

## Double-counting and isolation

### Slice 4 operational owner cleanup

Each prospective owner binds Track, current OPEN applicability, retained material/
assessment/Review/decision/geometry authority, exact instrument/contract, capability
object and monitoring generation, registration identity and subscription scope.
The owner is fenced before its runtime references are removed. Shared release then
runs outside workflow publication coordination. Old callbacks are inert and cannot
republish a checkpoint, applicability or owner. Status contains saturating counters,
not a per-detachment history; GET/status/startup do not initiate cleanup.

The shared hub owns desired per-instrument membership and external subscription
state separately. One transport drainer reconciles ownership generations, including
changes during in-flight Provider calls. It never holds the hub state lock during
Provider operations or callbacks. Contending callers publish desired membership;
the drainer completes the resulting subscription difference. A new owner arriving
during unsubscribe is subscribed again exactly once before reconciliation settles.
No product owns last-owner inference. Final instrument-owner removal evicts only
that instrument's cached tick; other instruments and owners survive. Retired session
callbacks are fenced. Registration scope, consumer and capability references are
released, without revoking a capability still used elsewhere.

SUSPENDED retains factual checkpoint bytes and detaches operational ownership.
Resumption is explicit, requires compatible authority and a new OPEN applicability
successor; unproved observation gaps remain RECOVERY_REQUIRED. CLOSED never resumes
automatically or through this resumption method. Terminal factual completion retains
the factual transition and final checkpoint first, publishes CLOSED applicability
second, then detaches. These are existing record formats, not new evidence schemas.
Currentness incompatibility uses existing authority comparisons; no invented expiry,
contract replacement, outcome or Sponsor-position closure rule is introduced.

Invalid integrity causes runtime detachment without repair or authority backfill.
Legacy tracks without applicability remain unregistered/RECOVERY_REQUIRED, with no
closure/applicability records or fact reads. This work neither consolidates nor
deletes historical VBL evidence and adds no monthly Excel or retention maintenance.

## Slice 5 explicit legacy research consolidation

`prepare_historical_consolidation(track_identity, created_at=...)` is an explicit,
read-only maintenance operation in the Paper Observation Track owner. There is no
production caller or publication endpoint. Startup, Connect, restoration, callbacks,
GET/status, analysis refresh, Journal and Reports never invoke it. Its returned
immutable bytes are not a current checkpoint and cannot satisfy live applicability,
Position, Readiness, KR-370, Step-31, Risk or downstream authority.

The caller fixes an aware creation timestamp for one maintenance operation and
reuses it on replay. Execution start/end times belong in the separate qualification
report. Identical source evidence and operation boundary produce identical canonical
bytes and identity. A different boundary denotes a different preparation operation;
it must not be used to manufacture a duplicate publication. Production publication
is separately authorized and is not implemented in this slice.

Schema `KRONOS-PAPER-OBSERVATION-HISTORICAL-CONSOLIDATION-V1`, implementation version
`1`, policy `VALIDATED-LEGACY-RESEARCH-CONSOLIDATION-V1`, retains the complete validated
Track, material events, monitoring identities/counts/reason and recovery summary,
first/last factual boundaries and sequence/source identities, counts of unsequenced,
unordered and recovered facts, observed extrema, and final research state. Review,
requirement, market, derivative contract, opportunity and material bindings absent
from Track V1 remain explicitly unavailable; a symbol or later analysis does not
establish them. No external authority is inferred from provenance digests.

Every source record is decoded with the existing schema/integrity validators and
bound to the exact Track and filename. Evidence paths are sorted canonically using
128-row scratch runs and two-way external merging. Fact duplicates/conflicts are
checked in source-identity order, scoped by the retained Provider connection identity.
No full fact tuple, validated-object cache or unbounded in-memory fact index is used.
Memory depends on the bounded merge batch and retained control records, not tick
count. Temporary scratch is private and removed after preparation; source evidence
is never modified. Source inventory digest is SHA-256 over newline-separated
canonical JSON `[relative_path, byte_size, byte_sha256]` rows in path order. It
covers Track, every fact, every event and every monitoring record. A second complete
inventory verifies path population, bytes, inode, size, mtime and ctime stability.
Unexpected files, prospective state, symlinks and unstable sources fail closed.

Missing required sequence fields fail validation. An explicit null sequence remains
valid unsequenced evidence under the existing policy: no sequence or ordering is
invented. Numeric sequence gaps alone do not establish missing market data. Without
a previously retained expected inventory, facts removed before preparation cannot
be discovered by inference; the digest proves precisely the validated population.
Changed populations produce a different digest/identity. Conflicting same-source
facts fail closed. Final price is unavailable where differing equal-time observations
do not establish a unique final value. Extrema are factual price extrema only, not
MFE/MAE or performance analytics. Only retained material events establish touches.

Nonterminal history remains `OUTCOME_NOT_ESTABLISHED` and `RECOVERY_REQUIRED`,
independent of its retained monitoring/entry state. Terminal history preserves the
exact existing factual event. Historical records with no applicability remain
`HISTORICAL_NO_CURRENT_APPLICABILITY`, `RESEARCH_ONLY`, non-restorable, with
`deletion_ready=false` and `PENDING_REFERENCE_SCAN`. Neither factual closure nor
operational OPEN is fabricated. There is no migration, expiry, production write,
deletion, archive movement, monthly ledger, Journal/Reports or Excel change.
Full legacy projections and prospective bounded checkpoints retain their contracts.

### Slice 6A: explicit historical selection and reader disclosure

Historical reader selection is independent of monitoring applicability. An absent
selection means the existing raw representation. Neither an empty facts directory
nor a candidate consolidation selects compact history. Raw mode still validates
every retained fact with the original validators; an empty raw population is
disclosed as `HISTORICAL_DETAIL_UNAVAILABLE`, never inferred as successful compaction.
Without a retained expected population, a file removed before any coverage record
cannot be detected by inference; the reader does not claim such completeness.

The explicit maintenance operation `publish_historical_consolidation` requires an
exact prepared record, a maintenance identity and an aware publication timestamp.
The operator must separately hold an authorized reader/writer exclusion boundary.
The owner reconstructs and validates the complete source population again and
requires identical canonical bytes, identity and digest before publishing. It retains
the original consolidation bytes under `historical-consolidations/<sha256>.json`,
then publishes the immutable `historical-representation.json` selection last.
The selection uses the existing store wrapper and schema
`KRONOS-PAPER-HISTORICAL-SELECTION-V1`; it binds the exact Track/digest, consolidation
identity/digest, source count/aggregate, retained-control byte digest, maintenance
identity, publication time and selection integrity digest. It is not an OPEN
applicability, deletion receipt, Position or live checkpoint. Exact published replay
is inert; conflicting selection fails closed. An orphaned candidate remains inert
and requires explicit maintenance review, not automatic adoption or repair.

Only a validated selection may expose `COMPACT_HISTORICAL`. Every read validates
schema, policy/version, canonical bytes, integrity, exact Track/decision/geometry
binding, recorded source coverage, event and monitoring identities, current retained
controls, and selection stability. No raw fact reconstruction occurs in this mode.
Wrong-track, corrupt, stale or unsupported selection/record yields
`HISTORY_UNAVAILABLE` with reason
`PAPER_OBSERVATION_HISTORICAL_EVIDENCE_UNAVAILABLE`; no raw fallback or repair occurs.
Unknown values/counts/timestamps remain unavailable. Direct `facts()` requests on
selected history fail with `PAPER_OBSERVATION_HISTORICAL_DETAIL_UNAVAILABLE` rather
than returning an empty tuple or substituting summary evidence for an audit.

The historical projection preserves Track and event identities, geometry, first and
last actual factual observation boundaries, counts, retained Entry state and factual
terminal event where one exists. The last observation is never consolidation or
publication time. Nonterminal outcome remains `OUTCOME_NOT_ESTABLISHED`; interrupted
history remains interrupted and `RECOVERY_REQUIRED`. Historical selection prohibits
new fact/applicability admission and confers no restoration authority. Validation of
the retained summary and controls is not revalidation today of the removed raw facts.

Ledger V2 projections and JSON/CSV exports, the existing operational handoff, and
Swing Paper Journal/Reports carry representation, raw-detail availability, first/last
factual timestamps, fact/source counts, consolidation identity and bounded disclosure
reason. `COMPACT_SUMMARY_ONLY_RAW_FACTS_NOT_REVALIDATED` states the exact limitation.
These additive projection fields do not rewrite immutable ledger records, links,
source identities or their hashes. Historical selection routes independently of
factual completion, including after governed-date routing; it does not manufacture
COMPLETE, expiry or a completion timestamp. Journal keeps these records out of the
active population, but explicit detail selection remains readable; Reports retains
the historical summary with separate factual timestamps and unavailable raw detail.
Unavailable selected history remains bounded through the same consumers.

All publication in Slice 6A is isolated-fixture-only. Production selection, deletion
and runtime recovery remain unauthorized. GET/startup/Connect/status cannot invoke
preparation/publication, migrate or repair evidence. Intraday record mappings and
presentation remain unchanged, and Excel export is outside this correction.

If a governed PAPER Sponsor Position activates, no separate track is created;
the position lifecycle supplies the primary PAPER outcome relationship. A track
is a relationship on the one Sponsor-decision research row, not a second row.

The track cannot create KR-380, KR-390, Sponsor Position, lifecycle, closure,
LIVE, notification, monetary P&L, actual R, order, fill, or broker evidence.
Historical decisions receive no automatic track or backfill.
