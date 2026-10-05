# WO-SWING-NEXT-12 prospective research — isolated candidate contract

Status: **source candidate for review only**. Base revision `7f783d10530557e7d19a36297a79f43861ca7f49`. No production capture hook, Browser action, runtime load, release publication or live acceptance is implied.

## Existing owners and source boundaries

- `src/kronos/swing/v1/opportunity_continuity.py` owns admitted Swing continuity instances. Its opportunity ID is the candidate's instance identity; a setup-family ID is not an instance. An owner-declared replacement or direction change needs a new origin. Unchanged continuity is one origin.
- `src/kronos/swing/v1/analytical_promotion_v2.py` owns V2 evaluated readiness and satisfied criterion count. The adapter accepts the exact validated V2 record at 4/5 or 5/5; it does not alter V1/V2 history or infer readiness from price movement.
- Swing Sponsor and lifecycle owners in `src/kronos/application/swing_trade_window.py` and the existing Swing V1/V2 tracks remain authoritative for decisions, PAPER, Observation and LIVE. WO-12 links their retained facts without accounting or trade admission.
- `src/kronos/provider/contracts/market_data.py` and `src/kronos/market/calendar.py` are the later governed candle/session integration boundaries. This candidate injects them through explicit testable interfaces and makes no Provider call.
- `src/kronos/application/intraday_research.py` and `src/kronos/browser/intraday_research.py` supply technical publication patterns only. The candidate reuses XLSX packaging primitives without importing Intraday row or metric policy. No Intraday source is edited.

## Frozen record contract, version 1

Immutable, content-hashed JSON records under a separate research store retain `ORIGIN`, first `MILESTONE` at each 4/5 and 5/5 score, actual `DECISION`, separate `LIFECYCLE_TRACK`, exact-contract `CANDLE`, `CHECKPOINT`, `RECEIPT` and explicit `UPDATE`. Atomic current pointers identify the latest checkpoint and receipt while older records remain. Each origin includes the continuity instance, NSE or exact MCX family, exact instrument and expiry where applicable, direction, admission time, source/version/hash, run, assessment and native setup. It remains even without progression, with IGNORE, or with no entry. Actual Swing decisions are LIVE, PAPER and IGNORE only.

A milestone binds to an origin and retains actual V2 readiness state, source identity/version/hash, occurrence time, original observed reference price and its observation/source/receipt timing where available. Missing price stays null. Duplicate refresh returns the first retained milestone; an earlier claim requires owner-reviewed revision. A retained 4/5 cannot follow 5/5, nor can 5/5 predate 4/5. A future owner hook must capture milestone events when they occur; no historical backfill is fabricated.

Lifecycle links retain the owner event, source version, truth class (`OBJECTIVE_MODEL`, `PAPER_OBSERVATION`, `PAPER_POSITION`, `LIVE_SPONSOR`) and factual state. No-entry and armed states have no fill or P&L. Objective and counterfactual rows have no money. LIVE entry or P&L requires Sponsor attestation. Lifecycle P&L never derives from direction checkpoints.

## Session and direction rules

For each milestone, count distinct completed governed trading sessions whose **IST trading date is after the milestone IST date**, in calendar order. Evaluate the close of sessions 1, 3, 5 and 10 against the *original* milestone reference price. Raw percent is `(close/reference - 1) × 100`; direction-adjusted percent is raw for LONG and its negative for SHORT. Positive, negative and exactly zero map to WITH_PREDICTION, AGAINST_PREDICTION and UNCHANGED. Incomplete future sessions remain PENDING. Missing original price or covered due candles is UNAVAILABLE. No later CMP or candle close replaces a missing reference.

Only intervals wholly after the milestone and adequately covered supply candle research favourable/adverse percentages. They are labelled separately from authoritative lifecycle MFE/MAE. An exact MCX future never rolls to its successor; horizons after expiry are EXPIRY_LIMITED. NSE corporate actions in the interval produce UNAVAILABLE until an owner supplies a governed common price basis. Candle revisions require explicit new source identity, prior-source link and reason, retaining the original.

Analysis partitions NSE, GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS, 4/5 versus 5/5, LONG versus SHORT and each horizon. It reports origin and milestone counts, eligible/pending/unavailable/expiry-limited counts, wins/losses/zeros, directional success and movement distribution. Its always-up comparator uses the **same eligible exact milestone/horizon rows**; no 50% benchmark is assumed. Linked milestones and repeated instruments are correlated observations, not independent trials. No R, expectancy, monetary P&L, costs or predictive-performance assertion is computed. These need separately governed entry/exit, costs, zero-outcome, uncertainty and eligibility rules.

## Storage and publication rules

The intended canonical root is `/Users/imranali/Documents/Project-KRONOS/Statistics/Swing`; no candidate run writes there. The compact JSON store is authoritative. One rebuildable `KRONOS_Swing_Research_YYYY_MM.xlsx` per origin month has six sheets: Opportunities, Tracks, Events, Analysis, Data_Quality and Metadata. Later checkpoints revise the original month. Publication stages and validates the workbook, checksums it, atomically replaces it, reads it back and records a receipt. A prior receipted workbook can be restored after interruption. Replayed operation identities and unchanged projections avoid duplicate publications. Status reads are observational. Explicit updates have a 60-request ceiling and deduplicate exact-contract/session candle acquisitions; disconnected or missing acquisition leaves the last verified workbook intact.

## Integration and acceptance holds

After accepted WO-13/14 integration baseline, the owning Swing event boundaries must call origin/milestone/decision/lifecycle capture without blocking admission or trading. The Browser must expose one explicit Sponsor UPDATE SWING RESEARCH action using the governed Provider and session calendar; GET/startup must remain observational. Shared paths require owner coordination. Integrated final bytes need focused and protected qualification, exact-byte release review and separate publication/load authorization. Live acceptance requires real governed price receipts, completed follow-up sessions and a genuine Sponsor update. MCX PAPER acceptance remains waiting for a qualifying MCX opportunity.

## R2 bounded review correction: resumable catch-up and calendar authority

The explicit update accepts a `GovernedCalendar` for each market with milestones. Its source identity/version, observation time, complete date range and ordered sessions attest that the sequence is exhaustive through the requested update date. Missing or stale coverage yields `CALENDAR_UNAVAILABLE`, identifies each affected market, and leaves the current checkpoint pointers and last verified workbook unchanged. Remaining candle work is **unknown** until calendar evidence returns. A new calendar that removes or changes a previously retained historical session yields a history conflict rather than renumbering a horizon. Source identity reuse with different calendar bytes is also a conflict. The calendar owner must still establish the initial sequence's completeness; the research store cannot independently prove an unseen holiday or session.

When more than 60 exact-contract/session candle requests are due, one explicit update acquires at most 60, retains every successfully verified candle, and returns `CATCHUP_INCOMPLETE` with the exact remaining request count. It does not recalculate checkpoints or publish a partial workbook. A later explicit update, including after restart, derives remaining work from retained candles and requests only missing pairs. A disconnected or interrupted acquisition returns `ACQUISITION_UNAVAILABLE` with durable progress and remaining count. The completed operation identity becomes idempotent; duplicate clicks do not reacquire candles or republish unchanged bytes. No background job, Provider connection or production Browser wiring is added by R2.

## Governed authority and factual-time correction — review candidate

Status: engineering implemented in isolation; renewed exact-byte review and the
final protected qualification remain release gates. Direct base is now
`7fad659876a62a26b345137b475ca999b0f33297`. The preserved bounded archive and its
369-pass qualification continue to identify the predecessor bytes only.

Canonical startup installs the research control, release verifier, compact
store, independent capture inbox and corporate-action store. Installation is
observational: commissioning, capture population and historical acquisition
remain absent until explicit authorized operations. The ordinary Browser
update stays a single counted `SWING_RESEARCH` worker with a 60-request bound.

`POST /control/swing-research/corporate-actions/import` requires same-origin
loopback, exact process-owned control credentials and an admitted Browser POST
owner. Its bounded JSON contains original CSV bytes (base64) and a Sponsor or
data-owner completeness attestation: original SHA-256, exact symbol/EQ series,
coverage dates, unfiltered all-results row count, source URL, capture identity
and timestamp, attestor identity and attestation timestamp. Governed NSE calendar
publication and actual session windows certify the completed coverage boundary;
there is no hard-coded 16:00 close. Missing session authority, incomplete capture,
wrong scope, purpose filtering, truncated rows and conflicting capture replay
reject before retention. This is attributable completeness attestation, not a
claim that an exchange cryptographically certified the negative result.
The first retained import receipt time wins on identical capture replay. Legacy
boolean-only reports remain historical but cannot supply comparable-price
authority. Reported actions still withhold a common basis; no adjustment factor
is invented. Real source bytes and genuine attestation remain live commissioning
inputs. No current report is downloaded or imported by this engineering slice.

`POST /control/swing-research/commission` uses the same authentication and counted
admission boundary. It accepts the reviewed manifest bytes and expected hash;
independently checks the process's startup-loaded revision, clean Git HEAD,
the immutable `WO12-Source-Manifest-SHA256` release-commit trailer,
base-to-release exact path scope, every committed candidate blob and on-disk
byte, then rechecks identity. Git optional locks are disabled so the verification
does not rewrite the index. The operation rejects nonempty prospective records,
unknown store files and any inbox record, pending file or symlink. It retains one
immutable receipt and one active pointer; exact replay is idempotent even after
restart. A crash between receipt and pointer resumes that same receipt and time.
No GET/startup operation performs commissioning or changes historical evidence.

The analytical cutoff remains fixed before acquisition, including calendar,
completed-session eligibility and checkpoint evaluation. Provider candle
`retrieved_at` is sampled after actual acquisition returns. New workbook creation
uses the actual generation clock; its receipt's `published_at` is sampled after
atomic installation and byte/structure readback. UPDATE completion is sampled
after publication. Receipt/UPDATE records separately bind `analytical_cutoff`.
Identical update replay and unchanged-projection rebuild preserve original candle,
creation and publication receipt times. These facts remain research-only and do
not supply entry, Risk, position, Provider or Intraday authority.

NSE and GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS retain separate exact-contract
research rows and governed sessions. Corporate-action absence authority applies
only to NSE equities; indices and MCX retain their existing semantics. All existing
commissioned MCX V1 boundaries, one-lot PAPER, manual LIVE facts, historical exits
and the outstanding genuine MCX opportunity acceptance remain unchanged.

The release sequence is renewed coordinating/shared review, then exactly one full
protected run on frozen executable bytes, then separate publication/build/load
and commissioning authorization. Production import, research commissioning and
UPDATE SWING RESEARCH have not occurred. WO-16 scope stays frozen.

Canonical research defaults follow the existing process-user home: Documents/Project-KRONOS/Statistics/Swing. This preserves Imran’s production location and makes the governed test bootstrap’s isolated home effective before canonical owner installation. No fixture is allowed to read or write the real Statistics population.

Corporate-action imports and explicit UPDATE evaluation share one process-owned authority boundary. An import during evaluation rejects promptly with SWING_RESEARCH_AUTHORITY_BUSY without writing; an already admitted bounded import completes before a queued counted UPDATE begins evaluation. The worker ticket remains counted while waiting and through publication/final bookkeeping. Success or failure releases the boundary. This prevents one workbook from observing different imported report generations under one fixed cutoff.
