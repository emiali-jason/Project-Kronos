# WO-06H — Final integration and bounded prospective live shadow

Engineering candidate under Sponsor/EA review. This document does not publish, activate, start a research month, close WO-06, or authorize a real operation.

Authority: the three Sponsor WO-06H instructions supplied on 8 September 2026. Baseline: `develop`, `2aeb5f32855355f055e93dbaac7e0a31b80041ca`. The direct current instructions govern this work; historical roadmap labels in the Current Authority Manifest and Living Master do not create new authority.

## Frozen production and research inputs

Production methodology remains **2.2.0**. Narrow CPR remains a production admission gate. WO-06A combined Opening support, WO-06B exact subject/benchmark/previous-session binding, WO-06C same-observation Assessment Price/Time, WO-06D population authority, and WO-05A/B trusted time and truthful accounting remain unchanged.

Every new actual admission is in Cohort A, independently of Review, rejection, promotion, trading or Sponsor selection. All 33 retained historical admissions remain historical; no price/time is backfilled. No historical candle, later LTP, Review/Chart/Answer, entry, broker or EOD value substitutes for Assessment Price.

The exact accepted research inputs are:

| Input | Published commit | Accepted research identity |
| --- | --- | --- |
| WO-06E | `997e3902c05eee57f74fe24874f4baf01597e2d6` | `WO06E-RESEARCH-1d118f57ed95cc58a4d304e97a635ed1dc72cad5f6262a90d6bd7eddb314b015` |
| WO-06F | `8ffb28edb496f0fd48d5e5da589f51875b1a7ba0` | `WO06F-RESEARCH-415176852e5b3e9e493af5db6259419babbea6b6fc7dac7c610d9cf04926ada3` |
| WO-06G | `2aeb5f32855355f055e93dbaac7e0a31b80041ca` | `WO06G-RESEARCH-ab3c4f33ce7f2c5665b5a5a1de12dcf1605863734db5dceadb87ea9abd1e2515` |

Retain 572 eligible observations, 33 baseline admissions, 107 no-CPR admissions, 74 sole blockers, 329 CPR-plus-other blockers, zero removed admissions and 310 unavailable observations. Decision impact is established; predictive value, missed winners/trades/profit and strategy effectiveness remain **NOT_ESTABLISHED**. WO-06H does not rerun or alter the accepted research datasets.

## Minimum same-schema feature set

Contract: `KRONOS-INTRADAY-LIVE-SHADOW/1.0.0`.

Both cohorts retain the same features, field-level availability, frozen definitions and exact source-set identities:

- Completed current-session **5M SMA20 side and SMA50 side**. Existing WO-06F arithmetic and lookback requirements are reused. Side is ABOVE/BELOW/AT/NOT_ESTABLISHED. Missing lookback does not filter an observation.
- Research-only **5M typical-price VWAP side**: sum(((H+L+C)/3) × V) / sum(V), completed candles from the governed session open, reset each session. No forming candles, prior-session carry, tick-VWAP claim or index-volume proxy. NIFTY and BANKNIFTY have missing VWAP where meaningful traded volume is not established.
- Separately for **5M and 15M**: body/range, upper-wick/range, lower-wick/range, close location, range ratio to the preceding completed candle, and one canonical pair-range state: INSIDE/OUTSIDE/EQUAL/OTHER/NOT_ESTABLISHED. WO-06G geometry is reused; zero denominators remain missing, with no tolerance or threshold.
- Existing phase and direction, exact NIFTY relationship, and already-governed local 15M structure where present. Opening does not fabricate a later-phase structure fact.

No second indicator or pattern formula is introduced. Mapping-selected candles must match the exact retained fact set, and existing Window validation rejects incomplete, unordered, duplicate, foreign or future candles. MCX feature calculations require exact same-operation native contract history. Reference context cannot become native authority.

Excluded from this experiment: SMA slopes, SMA200, strict stacks, VWAP slope/distance, volume normalization, named candlestick production labels, Hero/Bahubali, multi-candle reversals, break/retest authority, indicator votes, confluence scores and optimized thresholds. Their earlier research dispositions remain unchanged.

At 09:30 IST, the completed first 15M and Opening 5M candles remain lawful; forming current-day 1H is excluded and prior completed governed 1H is allowed. Missing shadow lookback does not delay or reject Opening. Trusted 09:29 requesting 09:30 still rejects before Provider acquisition.

## Cohorts and post-publication capture

**A — PRODUCTION_ADMISSION**: every new production admission, with its unchanged existing WO-06C Assessment companion. No extra A quote. Original companion identity, source and pair remain authoritative; restoration compares the projection against that companion.

**B — CPR_SOLE_BLOCKED_SHADOW**: factually evaluable, exact source binding, all other production conditions passing, and only Narrow CPR blocking admission. The existing reviewed WO-06E CPR-only decision function is reused and compared with the actual production evaluator and retained baseline result. Unavailable observations and CPR-plus-other blockers do not enter B. Failed classification is explicit incomplete research coverage, not an invented zero.

The callback runs after successful Probables publication/currentization. It cannot modify the producer result, membership, direction, current pointer or production failure state. Unexpected callback failure is separately visible as `SHADOW_CAPTURE_INCOMPLETE`. B never becomes a Probable, Review candidate, Readiness, Promotion, Trade Construction, Risk, PAPER/LIVE or broker object.

The current operation's exact resolved native InstrumentRecord and active derivative binding supply B quote identity. No free-text symbol, reference-series proxy, generic ticker transformation or silently assumed contract is accepted. The governed legacy canonical label RELIANCE remains supported through its resolved NSE record. NIFTY/BANKNIFTY retain analytical index identity. MCX uses the same generic native-binding code for supported commodities.

Each B member gets at most one bounded Provider-boundary quote attempt, after its sole-blocker decision. Price and time come from that same QuoteSnapshot. Requested and received times remain separate from market observation time. Known request time survives a failed response; unavailable price/time remains PRICE_NOT_RETAINED and never removes the row. No retry, candle fallback or later quote is performed. Retained B source contains only the normalized native instrument and quote pair; its digest and pair are checked again during restoration. No credentials, tokens, arbitrary Provider bodies or exceptions are retained.

## Truthful accounting and partial completion

New operation accounting is version **1.2.0**. Its ordered categories are the existing four factual/binding categories, existing `ASSESSMENT_OBSERVATION_REQUEST` for A, and separate `COHORT_B_SHADOW_OBSERVATION_REQUEST` for B. Each actual DOMAIN-006 invocation, including raised calls, is counted before execution. Nominal coverage is never substituted. This does not claim unobserved SDK retries or physical HTTP counts. Benchmark requests remain an overlapping subset, not an extra additive category.

Versions 1.0.0 and 1.1.0 restore with their original four/five categories and byte identities. Unknown historical counts remain unknown; known zero remains zero. Missing telemetry time does not discard a known request count or fabricate an earlier timestamp.

An immutable operation journal precedes factual acquisition once the accepted shadow window is active. A receipt distinguishes a recorded population, historical replay with no prospective capture, and publication outside the capture window. A crash before population projection remains an incomplete operation after restoration.

Before any B quote, the batch records exact expected A/B observation keys, and a per-member intent is atomically claimed. If a process stops after the intent but before an observation persists, an explicit isolated/current-operation reconciliation can retain the member with `PRIOR_REQUEST_UNFINISHED_NO_REQUOTE`; startup itself does not recreate or requote it. Successfully persisted members replay byte-identically. Missing rows and classification failures remain visible.

The batch membership is fixed when the collector enters within the accepted window. If the window ends during a batch, the remaining expected rows are still retained. Further B quotes stop and those pairs are marked `WINDOW_CLOSED_NO_QUOTE`. A keeps its existing admitted pair. Publication after the window is recorded as outside capture, without beginning a new population or requesting data.

## Persistence, identities and restoration

Intraday-only namespace: `live-shadow-v1` below the established evidence root. The constructor and ordinary status reads perform no writes. No production CURRENT pointer is created or changed by this namespace.

Immutable artifact kinds: window, acceptance, operation, receipt, expected-member batch, request intent, observation and outcome. Canonical JSON, explicit schema, logical keys and content integrity identify each artifact. Observation keys bind window/run/result/cohort; feature and quote identities are separately retained; outcome keys bind the original observation. Fields use an exact schema and reject unexpected fields. The namespace uses ancestor-by-ancestor directory descriptors with O_NOFOLLOW, bounded reads, exclusive temporary files, fsync and atomic non-overwriting hard links. Traversal and ancestor/leaf symlink escapes are rejected. Temporary files belong only to the writer and are cleaned without deleting retained evidence.

An observation holds canonical/native identity, session and schedule, source run/result/mapping/integrity, boundary, phase/direction, methodology, baseline/Narrow state, CPR source, same-schema Assessment and features, runtime, request intent and subject/session grouping. Raw observations are not independent research episodes. Later Review or trading selection never changes this denominator.

Outcomes are separate immutable records. Completing or replaying an EOD outcome never rewrites Assessment/context bytes. Conflicting source or outcome bytes fail closed. Restoration validates schema/integrity, expected membership, cohort separation, features, A's original companion, B's quote pair and outcome relationships. Restoration does not authenticate, quote, Refresh, publish Probables, create Review, synthesize EOD or reset the experiment clock.

## Runtime acceptance and one-month window

Default: **INACTIVE**. Source publication and ordinary startup are insufficient to activate capture.

All shadow modules are imported inside the existing WO-05C launcher capture boundary through the Intraday composition module. No shared launcher/server/view change is needed. The composed service receives the actual frozen runtime manifest. Its declared capability hashes the composed collector and the actual loaded CPR evaluator, feature, geometry, VWAP and quote functions; file existence alone does not establish composition.

A later separately authorized acceptance must independently verify published revision, listener/PID and source state, then supply the exact frozen manifest identity, schema, revision and bounded request identity. The service also verifies process ownership, CLEAN_COMMIT and required actual composed capabilities. The initial accepted clock instant starts one calendar month in Asia/Kolkata, with the same local wall time next month and end-of-month clamping. The interval is half-open. The window retains UTC and IST start, end, schema, definitions, accepted input identities, initial runtime/process/revision/configuration proof and capability digests.

A replacement process must be accepted explicitly. It reuses the original window and must preserve the frozen shadow implementation capability, including the reviewed calculation functions. Acceptance cannot extend or restart the month. Acceptance after the interval may permit retained EOD completion; it does not re-enable capture. No event or Provider call occurs merely because acceptance succeeds.

Read-only status is embedded in the existing `/control/intraday-discovery/v2/status` document: enabled state, accepted runtime, window, schema, counts, last capture and bounded failures. Status does not calculate indicators or request data.

The Intraday-owned explicit POST seam is `/control/intraday-live-shadow/v1` (JSON, no query, maximum 4096 bytes). There is no automatic Browser caller and no activation button added. Exact actions:

- ACCEPT_RUNTIME: action, runtime, schema, revision, request_identity.
- COMPLETE_RETAINED_EOD: action, runtime, schema, observation, envelope.

Unknown/malformed requests fail closed. These source-level controls do not replace separate Sponsor authorization to use them. No production invocation is part of engineering qualification.

## EOD authority and directional outcome

EOD research price is the **close of the exact terminal completed governed 5M candle** for the observation's analytical subject and session. DOMAIN-008 supplies the terminal interval, including a shortened final interval where governed. Price time is that candle's actual completion boundary. It is neither Assessment Price nor an execution/exit price.

Equities and analytical indices use their own exact native completed facts; meaningful volume is not a condition for an index EOD price. MCX requires an exact retained expiry-specific native contract proof for the same contract as the observation. A later valid same-contract binding is retained separately as EOD provenance; continuous/reference prices cannot substitute.

The explicit completion action loads the caller-selected exact existing replay envelope, validates it, and selects that subject's terminal completed fact. It does not load the newest file, scan unrelated subjects for acquisition, request a new quote or reconstruct missing data. Wrong session, subject, contract, nonterminal candle, future boundary, tampering or conflict is rejected. Missing source leaves the observation and missing outcome represented; a later valid outcome is appended separately.

Research directional move:

- LONG: 100 × (EOD − Assessment) / Assessment.
- SHORT: 100 × (Assessment − EOD) / Assessment.

Decimal precision is the existing fixed research policy. Exact zero is FLAT_DIRECTIONAL_MOVE; positive and negative values have corresponding directional-move states. Missing input is NOT_ESTABLISHED. There is no invented P&L, realised R, trade count, win rate, entry/exit, MFE/MAE, fill, friction or profitability authority.

**EOD_SCHEDULING_AUTHORITY_REQUIRED = YES for autonomous completion.** No existing automatic runtime trigger is commissioned here. The implemented method is explicit completion from retained evidence. A future autonomous scheduler or missing-EOD acquisition requires its own bounded authority; neither is implemented or executed. A one-month plan must explicitly arrange permitted completion operations or obtain that separate scheduling decision.

## Monthly working ledger and personal retention

The temporary monthly working projection is derived in memory. It is not the final Sponsor Statistics/Excel product and does not write a workbook. One batch uses the IST calendar month of its initial research capture receipt; all its expected members share that reconciliation month, including delayed missing-member completion. EOD's later completion date cannot move the original observation into another month.

Visible fields are security, cohort, phase, direction, Assessment Price/Time/availability, EOD Price/Time, signed directional research move/state, compact features and feature availability. Internal observation/group keys are trace fields, not ordinary Sponsor columns. Sorting is deterministic. Monthly expected/actual A/B counts, missing rows, Assessment and EOD availability, and classification failures are separate from whole-window operation completeness. A missing row, missing price, unavailable feature or EOD cannot silently shrink the denominator. Report raw observations and subject/session groups separately; no independent sample or predictive significance is asserted.

Permanent: final monthly Excel, GitHub source/tests/governance and Living Master/programme governance. Temporary: generated operational, analytical and research working evidence, including this namespace and qualification outputs.

The retention predicate allows future eligibility only from day 6 of the next calendar month, with the previous month closed, reconciled, final Excel present, its integrity and readability verified, and no conflicts. All gates must be true. Current-month data, the five-day grace period, an absent/unverified workbook, open reconciliation or a conflict prevents eligibility. **No purge engine, deletion or final Excel generator is implemented.** The existing published engineering export is not silently accepted as that final monthly product.

## Authority reconciliation proposal — not an applied manifest amendment

AUTHORITY_MANIFEST_AMENDMENT_REQUIRED = YES. The current V1 manifest still describes several historical WO-06 corrections as open. Do not overwrite its historical evidence or claim runtime/empirical acceptance from this engineering candidate.

Proposed next approved edition:

| Existing/new capability | Proposed truthful status |
| --- | --- |
| 06-opening | WO-06A methodology 2.2.0 correction implemented and published at af13782476d93928155f5471417f9a592e9ce7e7; current runtime dimension must use separate accepted evidence |
| 06-relative-binding / 06-cpr-binding | WO-06B implemented and published at ae5b7aa27bcd5c42239668a603e09429635e80e4; preserve original history |
| 06-assessment-observation | WO-06C two-commit prospective capture published at 2b7bf26beb83ac5a1a0dc9f0a420b0bf6950ac25; historical 33 prices remain unretained; use the accepted WO-06D activation disposition for loaded status, not a new claim here |
| New population measurement | WO-06D published at 979c9661926fad8eec96f9e71906713e835c0c21; every admission remains in the denominator |
| 06-cpr-usefulness | Decision-impact research published; predictive usefulness NOT_ESTABLISHED; Narrow CPR unchanged |
| New technical/candle context research | WO-06F/G published at the input commits above; research-only, predictive value NOT_ESTABLISHED |
| New WO-06H live shadow | Implementation/qualification candidate; publication, runtime acceptance, live month start and operational proof PENDING; no trading authority |
| 06-phase-contribution / 06-candidate-outcomes | Prospective measurement framework does not establish effectiveness; empirical qualification NOT_ESTABLISHED |

The manifest's publication, runtime, operational and empirical dimensions must remain separate. No manifest row is edited by WO-06H engineering. The Living Master was read; its WO-06 closure entry remains deferred until the actual publication, activation, operational and closure gates pass. WO-06H engineering PASS must not be used as WO_06_CLOSED.

## Qualification and next gates

All qualification uses deterministic fixtures, fake Provider responses, isolated temporary evidence and existing unchanged Swing tests. It covers cohort truth tables, source binding, both directions, all supported MCX native bindings, no index proxy, same quote pair, request accounting, missing telemetry, both geometry timeframes, Opening, atomic intent/replay/conflict/restoration, month rollover/cutoff, runtime freeze, explicit route safety, EOD terminal/source checks, retention gates and non-authority.

The complete engineering evidence pack records exact source/test hashes, focused/affected/full repository outcomes, syntax, diff checks, changed-scope secret scan, baseline production preservation and any concurrent unclassified Swing additions. No generated production evidence is rewritten or removed. Concurrent additions are preserved and are not attributed to WO-06H without evidence.

Sequence: Sponsor/EA engineering review → separately authorized exact commit → separately authorized publication → separately authorized governed restart/activation acceptance → separately authorized real operation if required → actual WO-06 closure. WO-07 onward, final Statistics/Excel, purge and shared/Swing hardening do not start automatically.

## Accepted-authority restoration correction — 9 September 2026

Status: Sponsor-authorized engineering correction; publication and runtime
acceptance remain separately gated. This section supersedes the earlier
replacement-process reacceptance requirement for an already-valid, unambiguous
active acceptance/window pair. It does not grant initial acceptance.

Root cause: `IntradayLiveShadowService.__init__` read `ShadowStore.all('window')`
and reconciled counts but initialized `_accepted=None`. The composed
`IntradayProbablesV2OperationalControl` passed its frozen manifest into
`bind_runtime`, which only assigned the manifest. Although `ShadowStore` could
read immutable acceptance artifacts, no startup caller read/bound them.

The same binding seam now performs read-only restoration. It uses the existing
`ShadowStore.all`, `Artifact` canonical/schema/integrity and body validation,
`key`, `instant`, `RuntimeManifest`/`StartupEvidence` validation and
`LoadedCapability` declarations. Exactly one window and one acceptance must
exist. Their logical keys, runtime-proof identities, research-only authority,
request identities, original interval, methodology 2.2.0, frozen research inputs
and feature definitions must agree. The accepted timestamp must belong to the
window and follow its process startup. The current process must own a valid
CLEAN_COMMIT manifest and must not claim a future startup boundary.

A new process legitimately has a different PID, startup, manifest and possibly
published revision. These values are never copied from the old process. All
retained/current composed capability declarations and non-secret launcher
configuration must match exactly. Missing or changed capabilities, configuration,
malformed source proofs, foreign bindings or tampered identities fail closed.
The persisted proof contains a manifest identity plus its original bounded
projection, not the full startup manifest; restoration validates the retained
projection and existing artifact integrity without inventing unavailable proof.

No acceptance-creation method is called. The restored acceptance ID is retained
in process-local state while the current manifest identifies the running
process. Read-only status distinguishes `NEW_ACCEPTANCE_GRANTED`,
`EXISTING_ACCEPTANCE_RESTORED` and `NOT_ACCEPTED`, and reports the original
`acceptance_identity`. The persisted schema remains 1.0.0. Initial explicit
acceptance remains a separate action. Repeated binding/status reads do not
write, duplicate, rewrite, migrate or currentize any evidence.

Missing, malformed, tampered, conflicting, duplicate or schema-incompatible
authority is explicit and inactive. No-authority fresh installation remains
inactive. Before the start and at/after the end, restoration cannot activate
collection or extend the month. A failure during existing count reconciliation
also prevents restored authority. Expiry of an already-running accepted process
still disables collection through the existing half-open interval check.

Historical `WO_06H_ACCEPTANCE_EPOCH/1.1.0` preserves its original marshaled
code-object identity in retained proofs. [ADR-0047](../../adr/ADR-0047-WO06H-DETERMINISTIC-ACCEPTANCE-EPOCH-DIGEST.md)
introduces the prospective 1.2.0 semantic AST digest because code-object bytes
also encoded non-semantic compiler and loader context. The successor binds an
explicit acceptance-owned callable allowlist, policy/schema/invariant
declarations and the separate live-shadow calculation identity while excluding
paths, positions and stdlib wrapper bytecode.

An immutable `DIGEST_SCOPE_COLLATERAL` compatibility record can bind one exact
historical 1.1.0 proof to its deterministic 1.2.0 equivalent for the same epoch.
It requires exact epoch/acceptance/window, complete old/new proof identities,
protected source-byte identities, equivalence evidence and Sponsor authority.
It creates no new acceptance or window and grants no compatibility to later
semantic changes. Ordinary exact equality remains the primary restoration rule.

[ADR-0048](../../adr/ADR-0048-WO06H-SAME-EPOCH-COMPATIBILITY-RESTORATION.md)
adds the missing maintenance-only operational surface for that already-retained
record. The surface validates the current epoch, acceptance, window, complete
current runtime/capability proof, exact compatibility and Sponsor/EA reference,
then uses the existing restoration operation. It does not pass through successor
commissioning authorization and cannot create a successor epoch. Exact-match
startup restoration and successor commissioning retain their existing rules.
Repeated compatible restoration is read-only and idempotent.

The known backend gap, 9 September 2026 07:56:03.186–09:30:40.076267 IST,
remains missing observations; disabled collection after that start remains
unobserved too. No Cohort A/B, Assessment or EOD backfill, later-price substitution
or synthetic operation is created. Existing counts and unfinished-operation
facts restore truthfully. Future observation still requires its separate lawful
operation authority; acceptance restoration supplies no Provider authentication,
WebSocket restoration, historical acquisition, Refresh, Discovery, Review,
OpenAI or broker authority.

Engineering uses the published kernel-isolated test runner and temporary stores.
The two retained Swing `PROVIDER_CAPABILITY_NOT_ACTIVE` monitoring records are
preserved. This correction changes no Swing implementation, monitoring policy,
WO-07B/07B1 workflow, production Narrow CPR, methodology, or trading authority.

## Successor acceptance epochs — 11 September 2026

**Status:** Approved bounded engineering by direct Sponsor / EA order; no production activation.

[ADR-0043](../../adr/ADR-0043-WO06H-SUCCESSOR-ACCEPTANCE-EPOCHS.md) and the [successor contract](../../interfaces/KRONOS-WO06H-SUCCESSOR-EPOCH-V1.md) extend the earlier singleton restriction. The existing acceptance/window maps deterministically to initial epoch 1 without byte migration. Explicit material-change successor commissioning creates a distinct acceptance and calendar-month window at the actual new acceptance instant, atomically advances CURRENT after immutable records validate, and starts current A/B/EOD at zero. The prior planned end remains historical metadata; supersession is represented separately.

Prospective observations add epoch and acceptance identities to their existing window binding. Default accounting/ledger/status is current-only; explicit historical status and all-epoch count reporting are available. Restore only the exact current epoch when compatible, never an older compatible fallback. The existing frozen calculation identity is unchanged; separate loaded epoch infrastructure declares its own capability. Ordinary acceptance remains maintenance-blocked; the new bounded commissioning route neither exits maintenance nor restores Provider. See the interface for trusted authorization enrollment and failure handling.

## Successor capability-boundary correction — ADR-0044

**Status:** Approved bounded engineering; operational enrollment/commissioning remains separately gated.

[ADR-0044](../../adr/ADR-0044-WO06H-SUCCESSOR-CAPABILITY-BOUNDARY.md) distinguishes strict same-epoch restoration from explicit material-change successor commissioning. An immutable bridge binds predecessor and current capability identities, exact changed/unchanged declarations, reviewed semantics, diagnosis and Sponsor authorization. It cannot restore an older incompatible epoch or grant a general compatibility exception.
