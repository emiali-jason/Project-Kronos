# WO-07E — Final temporal authority composition

**Status:** Sponsor-authorized engineering candidate; publication/runtime separately gated.
**Authority:** [ADR-0035](../../adr/ADR-0035-INTRADAY-TEMPORAL-AUTHORITY-COMPOSITION.md).
**Baseline:** eebeb7c4282ff08e9d25afe8ec8ae773e15374b2.

## Required composition

| Dimension | Required native result |
| --- | --- |
| Retained machine candle/calendar/session/binding | Independently VALIDATED and COMPLETE |
| Independent visual subject/timeframe/role/core | VALIDATED |
| Qualified region, temporal axis and right edge | Readable, full and sufficient for contradiction checks |
| context_sufficient | true; completion uncertainty alone is not a reason for false |
| visible_labels / basis | Distinct readable exact labels and truthful nonempty explanation |
| later_evidence / other_contradiction | ABSENT, supported by the visible context |
| forming_evidence UNKNOWN | Allowed without invented completion; all exclusion fields null |
| forming_evidence PRESENT | Existing strict exclusion/contradiction rules; never erased |

All required dimensions compose to CONFIRMED_COMPATIBLE. False/null sufficiency,
cropping, unreadability, ambiguous qualified scope, missing labels/basis or unknown
later/other findings remain INSUFFICIENT_VISUAL_EVIDENCE. Affirmative temporal
contradiction remains VISIBLY_CONTRADICTED. Machine-only failure is not visual
contradiction and does not produce CONFIRMED_COMPATIBLE.

The Protocol asks whether visible context can reveal contradiction, not whether
static pixels independently prove candle completion. It never requests a true
value to obtain acceptance. A full visible axis does not automatically establish
sufficiency for the Review window. Neither machine data nor free-text analysis
may overwrite the submitted structured assessment.

## Qualification and historical evidence

Dedicated tests cover native UNKNOWN with no visual endpoints, immutable replay,
explicit false with completion-only prose, missing/invalid source and session,
visible forming/future/stale evidence, cropped/unreadable content, wrong identity,
timeframe and chart/cycle binding, prior completed higher timeframes, and all five
MCX families. Reference UNKNOWN remains fail-closed without independent completion.
Full regression preserves commissioning HELD, 98/98 identities, schema 1.1.0 and
strict distinct labels, Q6/Q9, analytical and execution boundaries.

Exact revised LUPIN Answer SHA-256:
29dc481f0636873cd25c9ad976f5979eefb7b5e76347a4ccdc26015f112ca594.
Its four explicit false values are not reinterpreted. The isolated unchanged
replay remains unverifiable; a distinct constructed protocol-positive scenario
may qualify the correction without repairing or importing the production Answer.
That constructed scenario is engineering evidence, not empirical Analyst proof.

All exact source copies, replay reports, test counts, PDF QA and candidate hashes
are retained in isolated qualification output. No production operation is needed.
No source/Answer backfill, runtime restart, staging/commit/push, FB01 or WO-07F is
part of this engineering gate. Batch compilation remains a separate work order.
