# WO-07B-MCX — asymmetric chart correspondence

**Status:** Sponsor-approved bounded engineering requirement; unpublished candidate.
**Owner:** Intraday. **Authority:** direct Sponsor decision, 9 September 2026.
**Baseline:** `4ad67f62ce0f782c80921802784e3906169fe574`.

## Purpose and authority

The original gate obtains native selected evidence but has no reference candles
and no 4H selected candle. This correction supplies native 4H using retained exact
contract history and explicitly represents international context as visual only.
No external market producer, calendar, alias, listed/continuous membership or
reference price evidence is created. Shared Market, Provider and Instrument code
is reused unchanged. Production methodology 2.2.0 and admission remain unchanged.

| Native registry family | Governed supporting reference context | Independent reference correspondence |
| --- | --- | --- |
| GOLDM | COMEX:GC1! | NOT_INDEPENDENTLY_ESTABLISHED |
| SILVERM | COMEX:SI1! | NOT_INDEPENDENTLY_ESTABLISHED |
| COPPER | COMEX:HG1! | NOT_INDEPENDENTLY_ESTABLISHED |
| CRUDE | NYMEX:CL1! | NOT_INDEPENDENTLY_ESTABLISHED |
| NATGAS | NYMEX:NG1! | NOT_INDEPENDENTLY_ESTABLISHED |

Each reference 1D/4H/15M/5M panel is SUPPORTING_VISUAL_CONTEXT_ONLY. Its overall and
independent temporal comparison remain UNVERIFIABLE; visible identity and core
content may validate without upgrading independent correspondence. Exact existing
DOMAIN-001 visible commodity/venue/currency matching remains required. Listed
series remains a separate raw visual observation that must agree with the Answer.
No ticker parsing, proxy, cross-commodity substitution or source equivalence exists.
Known contradictions still reject. Missing machine reference times are not zeros
or fabricated sessions. R/X observations cannot independently create downstream
authority; the V2 reconciliation barrier remains unchanged.

## Native source binding

The gate first restores the exact Review cycle, chart bytes, handoff, Probables
run/result/mapping and completed selection, with existing integrity checks. Existing
native 1D, 15M and 5M sources and comparisons are unchanged. Native visual identity
still resolves to the metadata-bound derivative contract, separately from temporal
comparison. Wrong contract/expiry, reference-as-native and native absence cannot
be excused by supporting-reference policy.

For native 4H the adapter restores the exact active binding named by the paired
bundle and requires its retained integrity. It reads only that subject/contract's
existing `mcx-contract-history-v1` records. Each hourly record validates its own
integrity, exact subject/contract and Provider instrument record. No current-contract
roll, continuous native series, another Review selection or later acquisition is
substituted. The adapter performs no filesystem writes or Provider calls.

Context dates come only from the exact selection's Daily/hourly context. DOMAIN-008
provides the subject-specific MCX session windows, timezone, calendar version and
lawful hourly endpoints for those dates. Records must match that session/calendar,
start timestamp and source; duplicate starts or mixed sources fail closed. Records
observed after the analysis boundary are excluded, leaving missing membership
unverifiable. Missing contract history is unavailable; corrupt history rejects.

## Existing lawful 4H aggregation

Reuse `derive_session_four_hour_bars` unchanged: session-window anchored, ordered
60-minute constituents; first open, maximum high, minimum low, last close and summed
volume. No cross-session assembly or arbitrary four-row grouping. The source store
canonicalizes chronological order. Every expected member must exist and be complete.
The latest full four-hour bucket within the selected context is the expected source.
If its membership is incomplete, do not substitute an older complete bucket.
Forming buckets are excluded by the analysis boundary. Completed shorter session
remainders are not claimed as 4H. Opening may retain governed prior completed 4H
context while current-day 4H is forming; no new admission filter is introduced.

The derived proof retains shared aggregation policy, exact constituent boundaries,
Provider source and observation boundary, native contract/binding/Provider-record
identities, raw candle/integrity/historical-binding/operation identities. Its source
identity hashes the complete derived proof. The existing panel comparator rechecks
schedule, timeframe, endpoints, completion, visible latest endpoint and cutoff.
No tolerance or numeric TradingView-equivalence claim is introduced.

## Persistence and compatibility

After all native panels pass and all supporting visual requirements pass, the
current paired V2 adapter supplies an ordered eight-row `chart_correspondence`
tuple to the existing import engine. Each row is role, timeframe, authority,
independent correspondence and source identity. Reference rows have no source
identity and cannot deserialize as independently validated. Native rows require a
nonempty source identity and VALIDATED status. The tuple participates in existing
artifact integrity and immutable persistence, currentness and replay machinery.

The field is optional solely for truthful historical restoration. When absent it
is omitted from canonical serialization and historical hashes remain unchanged;
missing historical proof is NOT_RETAINED, never backfilled. Fresh current imports
always construct it after the real gate. V2 Analyst JSON, questions, enums, PDF,
filename, inbox containment and chart/review lineage are unchanged. There is no
validator bypass or new Answer import engine. No WO-07F reconciliation is implemented.

## Qualification and operational boundary

Fresh isolated five-family tests construct new chart revisions, independent
synthetic panel receipts, exact native retained constituents, V2 packs/Answers,
current imports, restoration and identical replay through the real application
gate. They do not use the historical-import fixture bypass. Synthetic native
visual relationships and NATGAS commissioning remain test-only, not new production
authority. These tests prove software behavior, not real pixels or empirical
Analyst reliability. Missing lawful production chart receipts/relationships remain
honest blockers for any later operational import.

Negative tests cover native missing/duplicate/tampered/foreign/future/session-invalid
constituents, each panel's wrong identity/venue/future/forming/cropped evidence,
malformed persistence and attempted reference authority upgrades. Existing NSE,
paired V1/V2, USDINR, currentness, inbox, Browser, DOMAIN-001/008, WO-06H and complete
active repository tests qualify preservation. Exact results and candidate hashes
are frozen in the external WO-07B-MCX-ASYMMETRIC engineering evidence pack.

No runtime restart, Provider/Refresh/Discovery, production chart/Review/Question/
Answer operation, OpenAI/Analyst call, broker operation or evidence rewrite is
permitted by this candidate. No staging/commit/push. WO-07E empirical work, WO-07F
and WO-09 remain held for separate Sponsor authorization.
