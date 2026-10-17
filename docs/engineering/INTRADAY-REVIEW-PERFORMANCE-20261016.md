# Intraday Review request-local source reuse

Status: Isolated engineering candidate; qualification and exact-byte independent
EA-Intraday, PCP and EA-Swing/shared review are required. No release/runtime authority.
Owner: EA-Intraday, with shared Browser/read-model ownership preserved.
Authority: KRONOS-INTRADAY-REVIEW-PERFORMANCE-20261016-01.
Base: ec105574933928224d7f678d628c0270f9fbfb62.

## Evidence and scope

The controlling isolated diagnostic ZIP SHA-256 is
0550fbbc2c6b5efc2bc73baf04b975ab58dc86672cc824c3117d0a8e69a1c74d.
Its registered 98-member fixture demonstrated repeated source validation, not the
historical 30-second timeout. Historical causation remains NOT_ESTABLISHED;
deployed verification remains FAILED / INCOMPLETE; Sponsor acceptance is PENDING.

Only project_intraday_dashboard changes production source. It captures validated
Probables/WO08 source identities in local variables inside the existing owner
source span, retains complete population/lineage validation and every per-subject
result, Native, exact-contract, calendar/session and WO09 pointer check, then
freshly compares source pointers and the WO09 population before returning.
Nothing survives the request; no new cache, storage index, producer or API exists.
The requirements reader, renderer, HTTP timeout and analytical policies are unchanged.

## Guards and limits

IntradayPublicationBoundary._sources for machine evidence acquires existing
Probables -> active derivative bindings -> WO08 read guards. The resolved-root
Probables/derivative RLocks serialize canonical retain/save_current methods in
this process. WO08 _scope also shares publication.lock with publish's exclusive
file lock. No guard order or duration is expanded by this correction.

Native records/bindings remain immutable producer evidence and are independently
joined per subject. WO09 reads are not a transaction: their individual pointers
and complete before/after population comparisons remain mandatory. Calendar and
clock interpretation stays per subject. No lock is added to shared Swing/Theta.

These guards do not forbid same-thread reentrant callbacks, arbitrary external
file edits or cross-process Probables writers. Fresh final comparisons deny
observed replacement/corruption after capture, including callback-induced source
supersession. This is not a cross-process transaction or protection against an
uncoordinated write/restore ABA attack; neither guarantee is claimed by the existing
read contract. No metadata-only validation or authority reuse across requests.

## Verification and review

Complete implementation and owning tests before consolidated qualification through
tools/kronos_test.py. Protect exact output, corruption/disappearance, source and
pointer changes, actual canonical writer blocking/release, Native/MCX/session
joins, request termination, shared Dashboard, Swing and Theta composition.
Compare predecessor/candidate with the same synthetic diagnostic stores and
transparent instrumentation; report first/repeated timings and read/validation
counts without claiming production latency or timeout resolution.

The external exact-byte package retains commands, JUnits, intermediate failures,
patch, manifests, guard/writer analysis, before/after measurements, preservation
and independent owner dispositions. Review approval and release remain separate.

## Documentation synchronization

CHANGELOG.md records this unpublished Python/Browser candidate. Reviewed
docs/ENGINE_STATUS.md and docs/architecture/ENGINE_OWNERSHIP.md: no Pine engine,
version, status, lineage or ownership changes are appropriate. Both registries
remain synchronized without artificial edits. Pine compilation/symbol validation
is not applicable. Source qualification is not release or live acceptance.
