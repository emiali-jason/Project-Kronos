# Theta TE-05C deterministic assessment candidate

**Status:** Qualified isolated engineering candidate; Sponsor review and any
publication/runtime acceptance remain separate.
**Date:** 12 October 2026.
**Owner:** EA-Theta Earners.
**Authority:** Sponsor TE-05C bounded engineering order; ADR-0067.

## Implemented slice

`src/kronos/theta/assessment.py` adds a Theta-local explicit application service
over the qualified TE-04B accepted-evidence seam. It admits the exact TE-05B
publication, evaluates the approved C1–C9 documentary predicates independently
for E1/E2, applies the exact categorical precedence and writes one immutable
sealed assessment record. It accepts no raw Answer or policy from callers.

The output is separate from structural acceptance and contains no forecast,
trade, option-expression, score, rank, weight, promotion or commodity/package
aggregate. Forecast inputs and original evidence remain in their TE-04B graph;
the assessment binds their identities and hashes.

## Persistence and recovery

The only assessment commit is `v3-assessments/<TAS identity>.json`. No new
selection/index/current alias exists. Publication is no-clobber and atomic using
the retained ThetaStore. Exact replay returns the retained first timestamp.
Restart restoration validates the record and exact accepted lineage without
rerunning the evaluator. Existing TE-04B currentness is projected, never written
back into the record.

An accepted but policy-ineligible Answer receives a retained `NOT_EVALUABLE`
record. Unknown arbitrary input or a corrupt/unrestorable accepted graph returns
bounded `NOT_EVALUABLE` without publishing an unbound assessment. Persistence
failure leaves no valid record. Immutable conflicts fail closed.

## Verification boundary

KRONOS verifies only typed documentary integrity and links. Astra classifications
remain assertions. No free-text semantics, chart pixels, source truth, publisher
authenticity, research completeness, economic correctness, probability,
calibration, accuracy, profitability or later outcome is evaluated.

The permitted verification claim is emitted only after successful assessment
admission. `LIMITED` and `NOT_EVALUABLE` never reject or rewrite the accepted
forecast. E1/E2 are independent and shared records count only where explicitly
tagged for the applicable horizon.

## Compatibility and protected boundaries

TE-03A target authority, TE-04A V3 contracts, TE-04B intake/persistence, TE-04C
producer, TE-05B publications, ADR-0066 and ADR-0067 are consumed unchanged.
The implementation adds no Browser/Outlook route and does not alter the retained
8948 Sponsor sandbox. No production 8947 operation, Provider/Kite call, broker
operation, market-data request, second AI, OCR, image interpretation or external
network dependency exists.

The candidate remains Theta-local. Swing and Intraday source semantics are not
modified. The newer `develop` drift was inspected rather than merged or rebased;
its changes are outside this Theta-local slice and must be reconciled during a
later authorized integration qualification.

## Qualification scope

The focused TE-05C suite proves exact policy pins, wrong identity/version/hash
failure, pre-policy handling, exact accepted-evidence admission, arbitrary-input
rejection, all DOCUMENTED, each criterion LIMITED path, admission
NOT_EVALUABLE, E1/E2 locality, shared evidence, ADR-0066 later-retrieval behavior,
event timing, Clarifications A/B, aggregation, immutable forecast/evidence,
replay, conflict, restart without recalculation, stale currentness projection,
corrupt graph and persistence failure behavior, and static Provider/AI boundary.

Final affected qualification and the five-child disposable rehearsal are retained
in `output/theta-te05c-closure`. Synthetic records are explicitly research-free
fixtures and provide no genuine forecast or methodology-performance evidence.

## Deferred boundaries

TE-06 Sponsor workflow/Outlook presentation, TE-08 realized outcome research,
TE-09 genuine Astra trial, production deployment/promotion, Provider acquisition,
option-expression suitability and all trading/broker work are not started.
