# WO12 / WO08 terminal validation interface V1

Status: Sponsor-approved bounded engineering and terminal-match policy;
qualification/review/runtime technical acceptance are release gates.
Date: 2026-10-11
Owner: EA-Intraday
Authority: ADR-0063 and WO12_V1_TERMINAL_DIRECTIONAL_MATCH.

The existing IntradayResearchApplication owns the composition. Explicit UPDATE
RESEARCH is the sole completion/publication trigger. project() is read-only by
default; optional year_month selects an existing origin month, without changing
the evaluation clock. Existing Browser transport, six-sheet workbook, publication
root, research transaction and per-workbook atomic receipts remain in use.

## Immutable records

WO12_WO08_CONSIDERATION_V1 binds opportunity_id and distinct opportunity_identity,
subject, market, original session/origin/direction, exact original WO08 prediction
(criteria/reasons/disposition), run/result identity and integrity, methodology
identity/version/checksum, original source/Native/completed lineage, original
Assessment Price companion and observation, original DOMAIN-008 schedule, exact
MCX contract/roll where applicable, actual first retained WO09 entry, policy
identity/version/checksum and RESEARCH_ONLY_NO_TRADING_AUTHORITY.

WO12_WO08_JOURNEY_V1 retains the consideration identity, exact readiness history
and exact applicable current-pointer snapshot. Coverage is
RETAINED_SNAPSHOTS_ONLY_NO_UNOBSERVED_TRANSITIONS_INFERRED. Each assessment's own
methodology tuple governs attribution. Missing original prediction does not
remove an actual entrant or borrow another version's entry.

WO12_WO08_EOD_VALIDATION_V1 binds consideration identity/integrity, opportunity
identities, original method/subject/session/direction/contract, original Assessment
Price, terminal price/time/candle identity/integrity/full governed payload, exact
source envelope/facts identities/integrities, retained native evidence, signed
directional movement and state, prediction_match, structured reason, policy
identity/version/checksum, endpoint-only interpretation and evaluation boundary.

Source readback resolves exact original WO08/Probables/Assessment Price/schedule
and terminal replay-envelope/facts/native authority before composed projection
and publication. Rehashed original fields, endpoint revisions, schema/integrity
and storage faults are not analytical NOT_MATCHED results. Missing or invalid
analytical authority is explicitly NOT_EVALUABLE. Conflicting endpoint publication
raises WO12_EOD_PUBLICATION_CONFLICT and cannot advance a report receipt falsely.

## Classification and reporting

Policy WO12_V1_TERMINAL_DIRECTIONAL_MATCH / 1.0.0 uses existing WO06H signed
movement arithmetic. Positive is MATCHED; negative/flat is NOT_MATCHED with
distinct flat reason. No threshold or PARTIALLY_MATCHED is commissioned. Prices
are never replaced by Entry, later quote or a reconstructed baseline.

Workbook V2/2.2.0 adds original-price, terminal-price/time, reason, signed move,
policy/checksum, consideration and progression-currentness columns and exact
consideration/journey/outcome events. Analysis reports considered/evaluated/
not-evaluable counts, endpoint distribution, retained progression, withheld
endpoint outcomes and separate 3/4/5 false-advance and unevaluated-advance counts.
Methodology/version/checksum, market, direction, exact contract and session remain
stratified. Denominators are explicit and zero-denominator rates are unavailable.
Existing admitted-assessment audit diagnostics are not the prediction denominator.

Original monthly reports refresh during explicit updates when late retained
terminal evidence becomes available. Atomicity is per workbook. Partial operation
failure leaves already verified monthly receipts truthful; no automatic retry.
No Provider request, automatic update, notification, readiness change, lifecycle
change, historical rewrite, acquisition expansion or broker authority is added.
NATGAS remains HELD. I1 commission/I2-I5 NOT_COMMISSIONED and original first-five
fail-closed remain intact. Existing positions and Swing are independent.
