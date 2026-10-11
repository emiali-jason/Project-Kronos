# KRONOS Intraday experimental PAPER interfaces V1

Status: Sponsor-approved bounded engineering; qualification/review and loaded
technical acceptance are separate. Method rules are frozen by ADR-0064.

## Version dispatch

`intraday/wo08_experimental.py` owns `ExperimentalWo08Assessment` and
`assess_experimental`. Its schema is
`KRONOS-INTRADAY-WO08-EXPERIMENTAL-ASSESSMENT-V1`; method is
`KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER / 0.1.0`.
The controlling method checksum is
`eddf2365be3c22825ccd5b9d1bdb1cb41a91d3a06912ff72e5d72dec6f004b68`.
The legacy assessment remains a distinct readable contract. Validation must
recompute rule results from exact retained source graphs, not accept rehashed
caller flags. Method checksum and `EXPERIMENTAL_PAPER_ONLY` accompany authority.

`intraday/wo09_experimental.py` owns `ExperimentalReadinessRecord`,
`ExperimentalNextWoHandoff` and `FirstFiveObservation`, with policy
`KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-READINESS / 0.1.0`.
`evaluate_experimental_readiness` interprets the validated criterion vector.
`create_experimental_handoff` builds the separate machine handoff; no visual
workspace, Answer or reconciliation identity is fabricated. Legacy visual and
uncommissioned machine contracts retain their original validators.

The application supplies current eligibility and trusted observation time.
Assessment publication time, observation time and first-five time are distinct.
Source-derived strict inequalities and unavailable states cannot be converted
to positive counts by a consumer. Currentness and existing first-five/handoff
freshness still constrain downstream admission.

## Durable first-five

The existing WO09 root retains claim-keyed immutable facts under
`experimental-first-five/`. The application interprets opportunity/session/
method authority; persistence serializes and verifies the complete fixed
expectation. `_Wo09Mutation.retain_experimental` participates in the existing
single outer root/subject mutation. It retains or validates an existing
first-five fact, then readiness and pointer. It does not create a new generic
transaction service or cross-process serialization guarantee.

Claims use stable owner-established opportunity, subject, direction, session,
exact contract and method identities. Per-operation run, Native cycle and
binding identities stay in provenance but cannot reset the claim when only
the analysis observation changes. Actual contract/session/method changes are
distinct claims. Original provenance is never reconstructed from a later run.

A retained fact without successful current readiness/pointer publication is
not handoff authority. Failed publication retains truthful partial evidence,
emits no success and does not recapture/retry the expectation. Handoff verifies
the exact current typed graph. This is fail-closed publication composition,
not a multi-file atomic transaction claim.

## Selective watch adapter

`application/intraday_experimental_watch.py` owns
`IntradayExperimentalWatchCoordinator` and `ExperimentalWatchStore` under the
existing WO09 root's `experimental-watch/` evidence. It adapts the existing
reassessment-watch APIs; it does not own readiness policy or Provider transport.
Canonical composition uses `GovernedExperimentalWatchCoordinator` to supply
source/session authority, maintenance admission and the existing monitoring hub.
Binding evidence ties each watch to exact current assessment/readiness,
opportunity, subject/session/contract, method, sole I2/I3 criterion, source,
generation, activation and existing session expiry.

`ProviderMarketTick.last_price`, `observed_at`, `received_at`, `connection_id`
and optional `source_sequence` are observation facts. DOMAIN-008 provides the
session binding separately. There is no fabricated `source_session`, bid/ask,
completed-candle flag or exchange ordering from callback receipt order.

The observer can consume only already lawful applied subscriptions. It does
not create a transport owner, connect, disconnect, reconcile subscriptions or
acquire REST data. No available subscription means no promised tick delivery.
Existing owner lifecycle and callback behavior must remain protected.

Loss of the last ordinary subscription owner permanently invalidates the
affected passive registration. Instrument-local interruption carries the exact
persisted watch-binding identity into cleanup; it cannot retire another subject
or a later successor binding on the same instrument. Whole-transport and
maintenance interruption may fence all affected observers. Callback fencing is
in-memory; durable retirement runs as bounded maintenance-counted worker work,
without taking source/store locks or awaiting persistence on that callback.

An eligible tick can retain only `ADVISORY_WAKE_HINT`, with the message
"Possible change — awaiting completed Analysis". The next lawful ordinary
Analysis owns criterion reevaluation. Supersession, stale generation, session
expiry, roll, maintenance and monitoring gaps fence hints/new-work authority.
No hint mints a first-five event, changes readiness or grants PAPER/LIVE Entry.

## Consumers and protected boundaries

WO10 and WO11 consume the separate typed experimental machine authority and
retain PAPER-only scope. Existing selection, exact Native structure, pricing,
one-lot PAPER truth, currentness and operational holds remain independent gates.
No analytical gate is introduced after established Entry.

`intraday/wo10_reconciled_underlying.py` supplies `ReconciledNseUnderlying` for
the experimental handoff's governed NSE V2 universe. It binds the commissioned
reconciliation publication, exact retained Discovery run and instrument master;
it does not invent a legacy catalogue identity. The canonical Futures source
receives explicit `discovery_store` and `reconciliation` dependencies. Restart
resolves the handoff's retained Discovery/master lineage rather than relying on
the last in-memory acquisition. Legacy `RuntimeInstrument` consumption remains
unchanged; the V2 bridge is admitted only with the experimental typed handoff.

WO12 consumes the exact method/criteria, original price/prediction, actual
progression, first-five and advisory history for research association. Its
terminal-directional classification remains ADR-0063. It does not repair
missing provenance or generate operational events.

WO13 receives only already commissioned state-transition families after source
commit and guard release. Shared deduplication and opt-in delivery remain the
notification authority; watch hints do not become Telegram readiness claims.

Canonical composition must wire the actual stores, trusted clock, eligibility,
session/instrument bindings and shared monitoring observer. Constructor tests
alone do not establish loaded composition. Runtime acceptance must identify
the exact published revision and distinguish technical availability from
NOT_YET_EXERCISED natural business events.

The existing `/runtime/status` response adds `intraday_experimental_paper` when
the canonical coordinator is composed. It reports the exact method tuple,
configured dependencies, passive observer count, bounded worker state and
sanitized failures from memory. It does not replay retained evidence, assess
current eligibility, publish a pointer or call the Provider. Configured watch
capability is distinct from active delivery on an existing subscription.

Immutable validation reuse follows ADR-0055: read the manifest and every member
file afresh, then reuse only a bounded successful validation keyed by the exact
complete bytes. Removal, replacement, reordered membership or changed bytes
must be detected. No current pointer, session eligibility, clock, generation or
first-five freshness decision is cached as authority.
