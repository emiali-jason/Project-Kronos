# WO12 Opportunity Journey V1

Status: Sponsor-approved reporting boundary; release requires exact-byte independent review and EA acceptance.
Authority: [ADR-0065](../adr/ADR-0065-WO12-OPPORTUNITY-JOURNEY-REPORTING.md).

The existing Research application, local publication endpoint and monthly file name are unchanged. New explicit projections use workbook `KRONOS-INTRADAY-RESEARCH-WORKBOOK-V2 / 2.3.0`, with `Opportunity_Journey / 1.0.0` appended after the existing six sheets. Direct legacy `ResearchProjection` construction defaults to 2.2.0; historical recovery requests the receipt's recorded version. The immutable research-record policy checksum is unchanged.

| View group | Exact source and interpretation |
| --- | --- |
| Opportunity ID / Opportunity Identity / Consideration Identity | Existing readable opportunity ID, existing machine opportunity ID, and exact retained consideration ID; none substitutes for another. |
| Original prediction, direction, I1–I5, count, reasons, disposition/failure | Frozen consideration.original_prediction from exact original WO08 assessment. Count is unavailable unless every criterion has a known positive/negative interpretation. |
| Assessment Price | Original typed admission observation only; no completed-close or later-price fallback. |
| First 4 of 5 / missing criterion | First retained exactly-four snapshot in original direction/method/session/contract scope; missing criterion includes its retained state. |
| Watch fields / hints | Exact readiness-bound selective-watch bindings and matching advisory hint identities; no implied completed evaluation or promotion. |
| First 5 of 5 / first-five fact | Original prospective first-five observation and exact fact identity. No historical reconstruction. |
| First Retained 5 Snapshot | Separate first retained five-satisfied readiness timestamp; never presented as prospective first-five provenance. |
| Initial / Final WO09 and direction | First / latest retained considered snapshots, including reversals. Final Original Scope WO09 is separately labeled. Other Scope Readiness References disclose excluded direction/contract strata. |
| Stage measurements | Retained experimental analytical completed-5M close; explicitly not Assessment Price or Entry. |
| Constructed levels | Exact WO10 plan and futures expression, separately labeled. Unique track uses its exact comparison; without a track the latest retained comparison is explicitly labeled. Multiple-track scalar construction is not selected. All comparison refs remain. |
| Entry / Target / Stop | Current restored WO11 published graph and matching embedded immutable events, unique track only. YES means retained model event; absent or ambiguous evidence is NOT_EVALUABLE. |
| First terminal / gaps | TARGET_FIRST or STOP_FIRST only for the unique retained model exit. Gaps count/references are disclosed; OUTCOME_AMBIGUOUS suppresses earlier exit claims. |
| Durations | Differences of the corresponding retained aware timestamps; missing endpoints or negative order are NOT_ESTABLISHED. |
| EOD / false advance | Existing exact terminal-5M directional validation, independently preserved from model execution. Separate threshold-3/4/5 false-advance classifications follow existing denominator semantics. |

`JOURNEY_COLUMNS` is the ordered worksheet contract. Identified At is the retained opportunity-origin Analysis boundary, not an acquisition, receipt or strict knowledge-as-of claim. New timestamps are readable ISO date/time with retained precision, +05:30 and IST. Headers are frozen, wrapped and filtered, using ordinary 10-point text. Long contract identity columns are widened. The existing six sheet XML definitions remain unchanged, apart from version-dependent Metadata content in new workbooks.

Missing coverage never becomes NO for a market hit. A no-track row may say `Paper Created=NO`, which describes the retained creation record population, not market-price behavior. Multiple track references remain available for audit; no cross-track scalar chronology is composed. The existing Tracks/Events sheets retain their historical interpretation.

The view has no Provider, notification, lifecycle mutation, candle acquisition or Analysis authority. All input owner validation precedes projection. No mutable-currentness cache or new clock is added. `SAME_INTERVAL` is deferred outside V1; no OHLC inference or invented cancellation vocabulary is accepted.
