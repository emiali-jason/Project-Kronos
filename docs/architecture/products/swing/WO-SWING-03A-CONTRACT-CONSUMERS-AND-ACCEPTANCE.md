# WO-SWING-03A — Consumer Map and Acceptance Contract

- **Status / architecture:** APPROVED — Proposal 3
- **Approver:** Chief Architect / DOMAIN-008
- **Approval date:** 2026-09-14
- **Approved revision:** Proposal 3
- **Commissioning status:** UNCOMMISSIONED
- **Engineering status:** DEFERRED FUTURE CAPABILITY
- **Current-production requirement:** NONE ESTABLISHED
- **Current NSE/MCX disposition:** SAME-DATE CONFIRMED
- **Cross-midnight successor capability:** DEFERRED
- **Partial implementation:** Safely archived and removed from the active worktree
- **Reactivation:** Requires an authoritative D+1 schedule or new explicit Sponsor instruction
- **Approval verdict:** WO-SWING-03A-ARCH-APPROVAL-02 = APPROVED
- **Revision:** Proposal 3 — WO-SWING-03A-CONTRACT-REV02
- **Owner:** Swing EA; shared DOMAIN-008 authority remains Chief Architect-owned
- **Baseline inspected:** `9068edb3cff204f6f1584cf723b4c3607ba1963f`

**Dependencies:** [ADR-0056](../../adr/ADR-0056-DOMAIN-008-CROSS-MIDNIGHT-SESSION-FOUNDATION.md)
and [approved, uncommissioned V2 interface](../../interfaces/KRONOS-MARKET-CROSS-MIDNIGHT-SESSION-V2.md).

This approved implementation plan is retained as a deferred future capability.
The partial WO-SWING-03A-ENG implementation was safely archived and removed from
the active worktree; it was not published. V2 is not commissioned or runtime-loaded.
Historical proposal-stage statements below remain for provenance.

WO-SWING-03B inspected 1,327 current production windows and found zero D+1
windows. NSE and all five Swing MCX families are same-date; current manifest
V3/V1 remains production authority; unchanged-HEAD verification passed 231
tests. No current production record requires V2. Synthetic D 23:00 to D+1 01:00
remains a deferred successor capability. Intraday source was restored byte-
identically to HEAD. The archive is `/Users/imranali/Documents/Project-KRONOS/output/swing-deferred/WO-SWING-03A-2026-09-14`.

## 1. Current baseline and trace

At inspection, develop and fetched origin/develop were equal, ahead/behind 0/0,
with no starting dirty paths. The Intraday task was idle, consistent with its
retained engineering closure; clean Git alone was not treated as owner release.
Recheck ownership, source and ADR-number availability before approval/publication.
The document-only candidate uses the next free four-digit ADR, ADR-0056.

The clean starting-state statement above describes Proposal 1 preparation.
REV01 starts with exactly this existing seven-file proposed package dirty:
the ADR, interface and this plan are new; KNOWLEDGE_BASE.md, adr/README.md,
interfaces/README.md and platform/ARCHITECTURE_INDEX.md are modified indexes.
They are attributed to WO-SWING-03A-CONTRACT, not concurrent product work.
REV01 does not fetch, publish, stage or touch another owner's source.

No existing approved cross-midnight/explicit-day-offset/central-owner-resolution
amendment was found. ADR-0028 remains a narrower directional specialization
authority. Approved constitution/domain documents and historical ADRs are not
rewritten by this candidate.

## 2. Consumer inventory and likely source manifest

Paths in this table are repository-relative. `Change` means likely bounded
engineering after approval; `Qualify` means preserve unless a demonstrated
version/ownership seam requires an explicitly reviewed adaptation.

| File / boundary | Inspected assumption / affected function | Disposition after approval |
| --- | --- | --- |
| `src/kronos/market/calendar.py` | `PublishedTradingWindow`, `PublishedTradingSession`, `_published_session`, `_parse_publication`, `_load_manifest` use time-only/strict V1 shapes | Change: explicit V2 dispatch, offsets, source integrity, complete coverage; retain V1 parser/bytes |
| same file — proposed V4 manifest seam | Existing V3 two-publication cardinality cannot express retained V2 adjacent coverage | Change only after approval: closed V4 predecessor/successor bindings and lineage/digest/conflict checks; preserve V3 syntax/cardinality, no production manifest amendment |
| same file | `MarketCalendarEntry`, `SealedMarketCalendarPublication`, `SealedMarketCalendarPublisher`, `MarketCalendarRegistrySource`, `_parse_entry`, `_parse_window` feed shared day schedules | Change/qualify: V1 sealed syntax preserved, no V2 accepted as V1; successor projection reaches both runtime representations |
| same file | `MarketCalendarPublisher.schedule`, `trading_week`, `_require_covered`, `coverage_health` | Change: UTC-resolved endpoints and shared ownership API; DAY label/week remains trading-date keyed; distinguish coverage/non-trading |
| `src/kronos/market/schedule.py` | `MarketWindow`, `MarketDaySchedule`, `MarketSessionWindow`, `MarketSchedule`, `_valid_windows`, `_ScheduleAdapter.normalize`, `MarketSessionService.facts` | Change: explicit successor construction/serialization; centralized bound/unbound ownership, UTC chronology/envelopes; retain V1 behavior |
| `src/kronos/market/derived_timeframes.py` | `derive_weekly_bar`, `derive_session_four_hour_bars`, `_expected_hour_boundaries`, `_usable_schedule` | Qualify/adapt version and UTC arithmetic only; anchors, OHLCV aggregation, completeness and shortened-remainder labels unchanged |
| `src/kronos/application/swing_mtf_facts.py` | `_completed_hourly` chooses source timestamp civil date; `_completed_four_hour` groups that date | Change: DOMAIN-008 owner/window binding; no midnight reset, gap bridging or product-local D-1 heuristic |
| same file | `_completed_daily`, `_completed_weekly`, `build_same_run_mtf_fact_snapshot` | Qualify: retain DAY label convention, final-owner-close completion, week membership, same-98/run binding, all existing factual/analytical separation |
| `src/kronos/application/swing_progression_watch.py` | `_load_latest_completed_bar` repeats date lookup/hour grouping; `_attach` passes clock date for instrument resolution | Change demonstrated schedule seam; qualify exact contract-date input without changing selection policy or watch activation semantics |
| `src/kronos/application/swing_refresh_reminder.py` | `next_completed_one_hour_boundary` starts enumerating at source civil date | Change: include owning prior window/tail via DOMAIN-008; keep recurrence, identity, deletion, restart and missed-boundary behavior |
| `src/kronos/market/calendar.py` | `mcx_contract_session_profile` requires observation civil date == trading date; profile requires cutoff date == expiry; `_mcx_expiry_schedule`, `instrument_session_profile`, regime adapters | Change V2 seams only; retain five-family rules, COPPER fixed cutoff, source-effective periods and NSE CAS applicability |
| `src/kronos/market/schedule_compatibility.py` | `publish_mcx_schedule_compatibility`, `_as_day_schedule`, `_schedule_sha256`, exact V1 contract constants | Change: additive V2 proof/serialization path, exact base/derived/previous provenance; V1 artifact, rule and hashes unchanged |
| `src/kronos/application/swing_v1_production.py` | `_source_payload`, restoration decoder constructs current MarketSchedule using constants | Change: explicit versioned successor source evidence, legacy unversioned historical payload dispatch unchanged; no rewrite |
| `src/kronos/swing/v1/mtf_facts.py` | completed bar/fact schema, immutable snapshot serialization/recovery | Qualify owner/source/UTC boundary integrity, successor provenance and retained legacy IDs; no new candidate authority |
| `src/kronos/swing/v1/relative_context.py` | `_boundary_identity`, `_compare_common_horizon` | Qualify only: exact common tuple incl. calendar version/session/source interval; unchanged return formula/classification/non-veto |
| `src/kronos/intraday/persistence.py` | `_schedule_dict`, `_schedule_from_dict` serialize shared MarketDaySchedule/MarketWindow without successor version | Change only explicitly authorized shared serialization seam; preserve exact V1 bytes and research identities |
| `src/kronos/intraday/probables_v2_persistence.py` | `retain_schedule_compatibility`, `load_schedule_compatibility` | Qualify/add version dispatch if successor artifact consumed; cannot reinterpret existing compatibility V1 |
| `src/kronos/intraday/completed_evidence.py`, `market_context.py`, `candles.py`, `context.py` | exact schedule type/version, phase/source pairing and session-boundary consumption | Qualify unchanged legacy cases; unsupported V2 must fail closed. Do not change 15M/5M selection, admission or cutoffs |
| `src/kronos/application/intraday_live_shadow.py`, `src/kronos/intraday/live_shadow_persistence.py` | accepted capabilities and retained epoch restoration | Qualify existing exact/approved-compatible restoration. No waiver/migration; material source implications return for operational authority |
| `src/kronos/instrument/active_derivative.py`, `active_derivative_persistence.py` | DOMAIN-008 family profile and exact cutoff consumption | Qualify current-source binding, inclusive expiry boundary, immutable roll. No selection-rule change |
| `src/kronos/browser/server.py`, `runtime_state.py` | current restoration/monitoring orchestration calls existing consumers | Qualify: no route, UI, activation or startup policy change anticipated |

The intended central resolver can live in `market/schedule.py`; a separate
DOMAIN-008 module is unnecessary unless later implementation review justifies
it. This avoids inventing a new platform service or clipboard-style side path.

Additional imports discovered during implementation must be classified as
unchanged, version-dispatch-only or requiring renewed authority before editing.
This manifest is not blanket permission to modify Intraday product logic.

## 3. Implementation sequence (not executed)

1. **Contract approval:** Chief Architect ratifies ADR, identifiers/wire schema,
   failure reasons, gap ownership and coverage conservatism. No production source.
2. **Foundation:** versioned parsers, source integrity, both runtime representations,
   UTC resolution/validation and one DOMAIN-008 ownership operation. Synthetic
   publications only; existing official publications and manifest unchanged.
   Implement exact string discriminator dispatch, closed mode-specific resolver
   payloads, immutable S/W hashes, request-specific Q/R hashes, compatibility K
   hashes, and synthetic V4 adjacency according to interface §§1/5/6/8/9/11/12.
   Do not infer an identity or choose a failure order during implementation.
3. **Swing consumers:** 1H/4H, DAY/week, progression and reminder schedule seams;
   exact MCX family/expiry profiles and bounded compatibility projections.
4. **Recovery/qualification:** explicit V1/V2 codecs, isolated restart/replay,
   Intraday shared persistence/capability checks, legacy golden byte identities.
5. **Separate closure:** rerun NEXT-03 on final authorized source. Approval,
   engineering PASS, publication, runtime loaded and genuine Sponsor E2E remain
   separate. No automatic NEXT-03 pass from approving this document.

## 4. Exact acceptance criteria

All cases use fake sources and isolated stores. End-to-end here means the
actual application construction path with fake Provider inputs, not live E2E.

| ID | Required assertion |
| --- | --- |
| A01 | Explicit V2 D 23:00 to D+1 01:00 passes publication, both runtime projections and Swing fact construction |
| A02 | V1 overnight-looking compact/multi-window input remains rejected; no inferred offset |
| A03 | Missing/unknown/duplicate fields, float/string/bool/null offsets, negative or >1 offsets and first-open=1 fail with exact reasons |
| A04 | Zero/reversed UTC intervals, malformed clocks, naive absolute inputs and unresolved local time fail; no guessed chronology |
| A05 | Later window open offset 1 accepted; ordered by resolved UTC, not local clock |
| A06 | Negative/beyond-next-date endpoints rejected; no arbitrary duration threshold appears |
| A07 | Same-day V1 golden serialized bytes, IDs and digests are identical to HEAD fixtures |
| A08 | V2 wrong schema/version, tampered offsets, endpoints, source digest or window identity rejected; V1 cannot parse V2 |
| O01 | Before/at/after midnight, month/year rollover retain correct trading date under offset 0/1 |
| O02 | Exact open active; exact close inactive; bound completed lookup retains original owner; adjacent next open has distinct owner |
| O03 | Midnight gap retains owner but has no active window; source candle beginning in gap is not admitted |
| O04 | Cross-entry window overlap and envelope-only overlap fail; no load-order/first-match tie-break |
| O05 | A declared holiday/weekend C does not remove valid C-1 overnight tail |
| O06 | Missing C or required C-1 coverage is UNAVAILABLE, not holiday/NO_OWNER; legacy same-day no-spillover remains lawful |
| O07 | Explicit wrong owner tuple cannot rebind; bound completed lookup after a later session opens still uses original immutable owner |
| O08 | Fully covered instant outside all envelopes is NO_OWNER; distinguish this from invalid and missing source |
| F01 | Full 1H crossing midnight and after-midnight 1H complete only at actual end; incomplete candle excluded |
| F02 | Completed short terminal 1H/4H remainders retain existing labels, OHLCV and provenance |
| F03 | Continuous-window 4H spans midnight without anchor reset; split session cannot aggregate over gap |
| F04 | Missing constituents fail closed only through current completeness rules; no manufactured bar |
| F05 | Before today's first hour, prior completed 1H remains; after exact new boundary the next analysis selects it; missing history unavailable |
| F06 | Unchanged governed fixture first-hour boundaries: NSE 09:15→10:15 and MCX 09:00→10:00; no hard-coded exception |
| F07 | DAY midnight label binds trading date, not timestamp ownership; waits until final next-day close; unknown label semantics unavailable |
| F08 | Friday DAY/weekly constituent remains Friday-owned when close is Saturday; incomplete governed week excluded |
| F09 | Same 98 instruments/run identity and publication provenance; quotes remain factual-only; Native/Shadow authority separation unchanged |
| M01 | GOLDM/SILVERM/COPPER/CRUDEOIL/NATURALGAS each qualified with same-day and synthetic successor schedules; no inherited Intraday hold |
| M02 | Before/exactly-at/after each family cutoff; existing inclusive eligibility and half-open activity both preserved |
| M03 | COPPER legacy 17:00 remains exact; generic late session is not fallback; no expiry extension/roll permission |
| M04 | Base, derived and previous schedule versions/digests retained; valid exact directional proof only; wrong family/date/source/pair fails |
| R01 | Latest exact common completed RS tuple selected; missing intersection gives UNAVAILABLE/BOUNDARY_MISMATCH; formula and non-veto unchanged |
| S01 | Progression 1H/4H after midnight uses exact owner; no additional activation or Provider call merely from status reads |
| S02 | Reminder after-midnight next boundary includes prior owner; gaps skipped by windows, not civil-date reset |
| S03 | Reminder recurrence, delete/recycle, missed-boundary recovery, no duplicate/spam and restart behavior unchanged |
| P01 | V1 and V2 isolated serialize/restore/replay; V1 source bytes/hashes and all production evidence untouched |
| P02 | Unknown/missing/mismatched successor publication and source endpoints fail closed; no historical rewrite or latest-pointer substitution |
| P03 | Shared Intraday V1 persistence, accepted epoch/capability checks and exact restoration unchanged; unsupported V2 rejected |
| P04 | Approved same-epoch compatibility and material-successor commissioning remain distinct; no generic bypass added |
| I01 | No Discovery/readiness/K-score/Step-31/Risk/entry/lifecycle/Pine/broker method changes; Intraday 15M/5M unaffected |
| I02 | No production calendar/manifest changes or new exchange hours; no live service calls, runtime operations or historical backfill |

### 4.1 Proposal 2 additive acceptance — no original case removed

These are future engineering acceptance requirements, not tests executed by this
documentation revision. All original A/O/F/M/R/S/P/I assertions above remain.

| ID | Required assertion |
| --- | --- |
| V01 | Every §1 successor/version discriminator accepts only its exact string literal; reject integer 2, float 2.0, boolean, null, missing, and wrong string values through the specified shape/version boundary |
| V02 | Repeat V01 for publication, normalized schedule, shared schedule, resolver request/result, family profile, compatibility schema/policy/pairs and publication_binding; opaque source versions remain exact nonempty strings |
| V03 | Reject mixed identity/version tuples and unsupported V1↔V2 adjacency; unchanged V1 fixtures preserve their existing literal/type/error behavior |
| Q01 | BOUND_OWNER requires owner and forbids completed_interval; missing/extra/duplicate/null fields and malformed nested scope/bindings reject before hashing |
| Q02 | UNBOUND_TIMESTAMP forbids owner and completed_interval even when null; require every common key, with no default as_of or latest source |
| Q03 | RETAINED_COMPLETED_EVIDENCE requires exact owner and completed_interval, 60minute source interval, and OBSERVATION_AS_OF purpose; reject all other shapes |
| Q04 | All eight result states have exact required keys/null/boolean rules and codes; success phase RESOLVED and reason null; NO_OWNER has its specified reason and null trusted facts |
| Q05 | Ordinary query > as_of and future query <= as_of fail with their distinct reasons; no hidden wall clock in replay |
| Q06 | Future reminder may resolve a published boundary after as_of, but temporal_use remains FUTURE_SCHEDULE and interval_completion_validated=false; future schedule is never a candle/admission proof |
| Q07 | Retained end == as_of succeeds; end > as_of fails even when the corresponding future schedule lookup succeeds; query must equal start and actual end must equal the window-bounded constituent end. Isolated REV02 negative: verified synthetic owner window D 23:00 to D+1 01:00 IST; completed_interval.source_start=D 23:00, source_end=D+1 00:00; query_instant=D 23:30; as_of=D+1 00:00. With all earlier validation phases passing, the interval remains anchored, contained, chronological and complete, but query_instant != completed_interval.source_start alone requires INVALID / MARKET_SESSION_INTERVAL_INVALID / COMPLETION, interval_completion_validated=false and owner=null, schedule=null, window=null. Correcting only query_instant to D 23:00 removes this isolated failure |
| Q08 | Reject wrong window identity, off-anchor start, gap bridging and incomplete terminal hour; bind shortened terminal end and historical owner exactly |
| Q09 | At close, reminder boundary uses bound owner while unbound activity is exclusive; enumeration includes prior-date tail, skips gaps and stops on missing coverage |
| Q10 | Exact schedule_selection distinguishes BASE_CALENDAR from MCX_FAMILY; reject missing/extra keys, wrong profile version/type, family/expiry/source binding mismatch and implicit family context; owner selection must equal Q selection and restoration must retain it |
| H01 | Recompute all seven complete §12 canonical hash vectors, matching exact prefixes and lowercase expected outputs, including both integrity maps |
| H02 | Both complete §12 normalized projections produce the same stable S identity despite different as_of/availability; their complete serialized-schedule digests differ |
| H03 | Changing freshness/integrity projection status cannot change S identity; changed authoritative binding, endpoint, offset, session/source or ordered provenance must change S |
| H04 | Verify exact canonical timestamps, JSON strings vs integers, booleans, nulls and array order; reject noncanonical wire timestamps and prevent cross-use of day/normalized/raw-file digest meanings |
| H05 | Restoration recomputes schedule/window/resolver/compatibility/integrity hashes; any altered field in its defined hash map fails; V1 hash casing/formulas remain unchanged |
| C01 | Valid explicit V4 adjacent edge resolves exact retained predecessor/successor bytes at year/month boundary and restores without a current-manifest lookup |
| C02 | Missing edge/member returns MARKET_SESSION_ADJACENCY_MISSING; missing file returns MARKET_SESSION_SOURCE_UNAVAILABLE; missing partition date returns MARKET_SESSION_COVERAGE_INCOMPLETE; explicit non-trading date is valid proof |
| C03 | Scope, exchange, segment, timezone, calendar identity or schedule-lineage mismatch returns MARKET_SESSION_LINEAGE_MISMATCH; no same-name or newest-version selection |
| C04 | Wrong raw digest returns MARKET_SESSION_INTEGRITY_MISMATCH before use; self/cyclic/forked/duplicate edge or invalid coverage/source-boundary ordering rejects deterministically |
| C05 | Overlapping coverage, competing publication versions, window overlap and envelope-only overlap fail in their exact precedence phase, independent of manifest iteration order |
| C06 | Validate declared relationships at load, needed adjacent coverage/as_of at query and retained exact bytes at restoration; unavailable future source cannot satisfy historical replay |
| C07 | Bound owner requires D-1 conflict proof and D+1 only for a tail past next midnight; absent proof fails closed; endpoint exactly at next midnight uses half-open non-overlap exemption |
| D01 | Exercise every full §9 reason and outer boundary; malformed request has no request/result identity; admitted failure returns sanitized closed result with no trusted partial schedule |
| D02 | Multiple faults select first phase, row, canonical field path/date/window ordinal; unreadable source cannot yield invented digest/shape diagnosis; NO_OWNER cannot mask missing coverage |
| D03 | Diagnostics are in-memory-only with exact safe fields; no evidence/log/store mutation, sensitive values, new persistence schema, or public raw exception |
| D04 | Compatibility preserves legacy base_session_sha256=previous shared day schedule meaning; added base/derived/previous normalized digests remain separately checked; no version-equivalence waiver |

## 5. Likely executable test manifest

New bounded tests proposed (names subject to ordinary engineering organization,
not a change to acceptance semantics):

- `tests/unit/market/test_cross_midnight_session_contract.py`
- `tests/unit/market/test_session_ownership_resolution.py`
- `tests/unit/application/test_swing_cross_midnight_facts.py`
- `tests/unit/intraday/test_schedule_version_persistence.py`

Existing suites requiring focused qualification, with changes only where the
new approved paths need assertions:

- `tests/unit/market/test_market_schedule.py`
- `tests/unit/market/test_market_calendar.py`
- `tests/unit/market/test_market_calendar_publisher.py`
- `tests/unit/market/test_multi_window_schedule.py`
- `tests/unit/market/test_derived_timeframes.py`
- `tests/unit/market/test_mcx_contract_family_sessions.py`
- `tests/unit/market/test_schedule_compatibility.py`
- `tests/unit/market/test_nse_closing_auction_schedule.py`
- `tests/unit/application/test_swing_mtf_facts.py`
- `tests/unit/application/test_swing_progression_watch.py`
- `tests/unit/application/test_swing_refresh_reminder.py`
- `tests/unit/application/test_swing_v1_production_source.py`
- `tests/unit/swing/v1/test_relative_context_common_boundary.py`
- `tests/unit/instrument/test_active_derivative_selection.py`
- `tests/unit/intraday/test_market_context.py`
- `tests/unit/intraday/test_live_shadow_acceptance_restoration.py`
- `tests/unit/intraday/test_live_shadow_compatibility_restoration.py`
- `tests/unit/browser/test_monitoring_restoration.py`

After future engineering, run focused suites, affected Swing/Market/Instrument/
Browser/shared-Intraday regressions, full active regression and compilation
through `tools/kronos_test.py` and the repository isolation rules. Record exact
commands, counts, duration and source SHA; compare any failure with unchanged
HEAD rather than silently omitting it. None of these implementation test passes
is claimed by this architecture-only work order.

## 6. Approval conflicts, exclusions and stop gates

- Existing V1 same-date requirements conflict with the desired successor only
  if silently broadened. Proposed explicit V2 resolves that conflict prospectively;
  Chief Architect must approve it. No historical ADR is superseded now.
- ADR-0028 cannot be used as arbitrary version equivalence; its proposed exact
  V2 wire projection needs approval alongside this contract.
- No current official production cross-midnight schedule is established here.
  Synthetic engineering qualification is independent of later publication facts.
- The cited Living Architecture says BANKNIFTY in its verification summary;
  repository Swing universe spelling remains `BANK NIFTY`. No normalization or
  universe change is made in 03A.
- A Provider with unresolved DAY labels, new expiry rule, unsupported timezone,
  offset outside 0/1, or shared capability mismatch requires a separate decision.
- Before any shared source edits, reconfirm Intraday ownership. Do not use this
  proposal to activate held Intraday products or re-enroll research epochs.
- Approved domain architecture/engineering descriptions may receive conforming
  links after approval. Their historical approved text is preserved in this draft.

**Current readiness:** Proposal 3 remains approved architecture. Commissioning
is UNCOMMISSIONED and WO-SWING-03A-ENG is DEFERRED FUTURE CAPABILITY. The partial
implementation is safely archived outside the repository and was not published.
Reactivation requires an authoritative D+1 schedule or new explicit Sponsor
instruction.

Chief Architect / DOMAIN-008 approved these exact Proposal 3 decisions:
exact version/wire literals; closed resolver/future/retained semantics; stable
source-provenance identity maps and canonical timestamp encoding; manifest V4
adjacency and conservative edge coverage; full failure taxonomy/precedence;
in-memory-only diagnostics; additive MCX/shared-persistence compatibility scope.
No engineering choice may substitute for those approved decisions. The historical
execution authorization was WO-SWING-03A-ENG; the Sponsor has deferred that work.
New semantic decisions and any reactivation remain separately gated.
