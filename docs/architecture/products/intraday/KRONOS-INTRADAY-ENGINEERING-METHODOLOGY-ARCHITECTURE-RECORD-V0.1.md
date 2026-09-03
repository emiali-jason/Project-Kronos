# KRONOS Intraday Engineering, Methodology & Architecture Record

**Status:** LIVING DOCUMENT — V0.1; amended through WO-17 Slice 0 governance authorization

**Product owner:** KRONOS Intraday

**WO-03A repository baseline:** `542c84fbacbd9f1bfb2997255b90f00495ba4544`

**Intraday factual publication checkpoint:** `8cb3b3e3632107dae585a60fceb4f88be90194d0`

**Created:** 2026-08-22

**Change authority:** Future governed work orders must amend this record when architecture or methodology is frozen.

## 1. Purpose and authority boundary

This is the living engineering, methodology, and architecture record for KRONOS Intraday. It preserves the commissioned factual foundation, product and Platform ownership boundaries, approved Sponsor/Chief Architect direction, future work sequence, unresolved policy, and lessons inherited from Swing.

Its governing handover principle is:

> **REUSE ARCHITECTURE AND INFRASTRUCTURE; DO NOT COPY SWING TRADING METHODOLOGY.**

This record documents current authority. WO-02 published the Slice 3V contract;
WO-03A establishes the review-candidate Native universe. Neither establishes a
trading strategy, authorizes Risk or broker execution, or converts a Swing
implementation into a Platform API.

Repository authority and ownership remain governed by the approved Platform records. In particular, a contract or support dependency does not transfer semantic ownership, permit access to producer internals, or create runtime authority.

## 2. Repository baseline and advancement audit

### 2.1 Gate

The document was prepared against this verified gate:

| Gate | Verified state |
| --- | --- |
| Branch | `develop` |
| HEAD | `5ca871df96ede9e5d6657ee31dab99eef389784d` |
| `origin/develop` | `5ca871df96ede9e5d6657ee31dab99eef389784d` |
| Ahead/behind | `0/0` |
| Working tree before WO-01 | Clean |

### 2.2 Advancement from the Intraday factual checkpoint

The range `8cb3b3e3632107dae585a60fceb4f88be90194d0..5ca871df96ede9e5d6657ee31dab99eef389784d` contains 30 commits and 122 changed paths. The primary classification is:

| Classification | Count | Scope |
| --- | ---: | --- |
| SWING | 22 | Swing evidence, review, analytical promotion, readiness, progression, entry timing, lifecycle, journal, and Sponsor Browser UX |
| SHARED PLATFORM | 6 | Safe runtime exit; bounded notification, monitoring, Telegram, dashboard, configuration, and Browser composition support used by Swing |
| DOCUMENTATION | 2 | Approved Swing/Platform authority and remaining Swing UX/operations governance |
| INTRADAY | 0 | No intervening Intraday product commit |
| OTHER | 0 | None identified |

Primary commit classification:

- **SWING:** `704359d`, `4817933`, `1967c72`, `ba1897c`, `79c9529`, `8dc865d`, `12d5e57`, `5765088`, `8fd4432`, `c11dfd1`, `58a0d19`, `3a4db94`, `6b82434`, `fcd3015`, `e6708ae`, `07dcdcf`, `e270363`, `fa31709`, `9f40a18`, `0eb246d`, `e8ab6a5`, `5ca871d`.
- **SHARED PLATFORM:** `cf52d7f`, `6d31e3e`, `1e86743`, `feb5a6c`, `0dbc24e`, `3ad3590`. These commits include Swing composition/consumption; their shared additions do not automatically constitute an approved Intraday API.
- **DOCUMENTATION:** `fb80efa`, `8ccaf2d`.

No direct change occurred in:

- `src/kronos/intraday/`;
- `src/kronos/application/intraday_*`;
- `src/kronos/browser/intraday_*`;
- `src/kronos/provider/`, including the DOMAIN-006 shared Provider runtime;
- `src/kronos/instrument/`, including DOMAIN-001 canonical publication; or
- `src/kronos/market/`, including DOMAIN-008 market/session semantics.

The shared `browser/server.py` and `browser/views.py` composition files did advance for Swing and shared Browser capabilities. The stable `ProductBrowserRoutes` dispatch remains in place, `/intraday` remains owned through the Intraday route/view seam, and the Intraday route/view modules themselves did not change. No intervening change materially supersedes the commissioned Intraday factual architecture recorded below.

## 3. Ownership model and product isolation

### 3.1 Non-negotiable rule

> **SHARE CAPABILITY. NEVER SHARE PRODUCT OWNERSHIP.**

Every relevant responsibility must be classified as one of:

- **PLATFORM-OWNED** — governed cross-product capability or semantic domain;
- **SWING-OWNED** — Swing product state, methodology, composition, or implementation; or
- **INTRADAY-OWNED** — Intraday product state, methodology, composition, or implementation.

Intraday must not depend on Swing application state. Swing must not depend on Intraday application state. The following dependency chains are prohibited:

```text
Intraday → Swing application → Provider
Swing product implementation → Intraday product implementation
```

Shared capability is consumed only through its governed contract or bounded Platform seam. Technical reuse does not transfer ownership.

### 3.2 Product-state separation

The product identities are explicitly distinct:

```text
SWING TRADE        ≠ INTRADAY TRADE
SWING POSITION     ≠ INTRADAY POSITION
SWING WATCH        ≠ INTRADAY WATCH
SWING JOURNAL      ≠ INTRADAY JOURNAL
SWING NOTIFICATION ≠ INTRADAY NOTIFICATION
```

Swing and Intraday also retain separate persistence identities, work orders, policy versions, and mutable product state. One product event must never mutate another product's watch, notification, position, trade, journal, or lifecycle.

## 4. Commissioned Intraday factual foundation

The Intraday factual foundation was published through checkpoint `8cb3b3e3632107dae585a60fceb4f88be90194d0` and remains present in the current descendant baseline.

Published capability includes:

1. Intraday namespace and product isolation.
2. DOMAIN-006 shared authenticated read-only Provider runtime.
3. DOMAIN-001 governed canonical Instrument publication.
4. RELIANCE canonical catalogue version `1.0.1`, with tick size `0.10` and price precision `1`.
5. DOMAIN-008 effective-dated NSE Closing Auction Session semantics.
6. Real governed RELIANCE runtime bootstrap.
7. Real factual reconciliation for 1D, 1H, 15m, and 5m.
8. Previous-session facts.
9. Classic Pivot factual arithmetic.
10. Central Pivot Range factual arithmetic.
11. Slice-2 structural facts.
12. Slice-3 factual/shadow telemetry.
13. Immutable persistence and reconstruction.
14. Intraday Browser factual projection.
15. Real RELIANCE operational proof.

These are factual capabilities. They are not a trading strategy and confer **no trading consequence**.

## 5. Real RELIANCE commissioning evidence

### 5.1 Run identity and reconciliation

| Fact | Value |
| --- | --- |
| Run | `INTRADAY-RUN-02490E741DA64343AAB2916271E98299` |
| 1D | `1 / 1 COMPLETE` |
| 1H | `6 / 6 COMPLETE` |
| 15m | `24 / 24 COMPLETE` |
| 5m | `72 / 72 COMPLETE` |
| Synthesized candles | None |

### 5.2 Previous governed session and observed price

Previous governed session: `2026-08-17`.

| Fact | Value |
| --- | ---: |
| PDH / High | `1320.8` |
| PDL / Low | `1298.1` |
| Close | `1316.0` |
| Factual current price during the run | `1321.3` |

### 5.3 Classic Pivot facts

| Level | Value |
| --- | ---: |
| P | `1311.633333333333333333333333` |
| R1 | `1325.166666666666666666666666` |
| R2 | `1334.333333333333333333333333` |
| R3 | `1357.033333333333333333333333` |
| R4 | `1379.733333333333333333333333` |
| S1 | `1302.466666666666666666666666` |
| S2 | `1288.933333333333333333333333` |
| S3 | `1266.233333333333333333333333` |
| S4 | `1243.533333333333333333333333` |

### 5.4 CPR facts

| Fact | Value |
| --- | ---: |
| Pivot | `1311.633333333333333333333333` |
| BC / lower | `1309.45` |
| TC / upper | `1313.816666666666666666666666` |
| Width | `4.366666666666666666666666` |

### 5.5 Headline factual presentation and volume telemetry

| Presentation | Fact |
| --- | --- |
| 15m | `CLOSE_ABOVE_BOUNDARY` |
| 5m | `RETEST_FROM_ABOVE` |

| 5m volume fact | Value |
| --- | ---: |
| Current volume | `473321` |
| Previous-five mean | `209647.2` |
| Current / previous-five ratio | `2.257702463948958059063035423` |
| Previous-five classification | `EXPANSION` |
| Session mean | `125166.2816901408450704225352` |
| Current / session-mean ratio | `3.781537596297252353657770857` |
| Session-mean classification | `EXPANSION` |

**NO TRADING CONSEQUENCE.**

## 6. DOMAIN-008 NSE session semantics

The approved distinction is:

```text
CONTINUOUS_TRADING ≠ CLOSING_AUCTION_SESSION
```

For RELIANCE, the applicable regime is effective from `2026-08-03`:

| Session identity | Time in IST | Meaning |
| --- | --- | --- |
| Continuous trading | 09:15 → 15:15 | Ordinary governed continuous session |
| Closing Auction Session (CAS) | 15:15 → 15:35 | Separate governed session identity |

Ordinary continuous 1H, 15m, and 5m expectations stop at 15:15. KRONOS must not fabricate an ordinary 15:15–15:30 tail. The official Daily Close may legitimately differ from the last continuous Intraday close. Pre-CAS history remains historically correct.

DOMAIN-008 owns market and session truth. These session facts do not themselves define an Intraday entry or exit policy.

## 7. Governed product trading clocks — WO-17 source not implemented

ADR-0027 freezes these product clocks prospectively. Production WO-17 source
remains unimplemented. The clocks remain separate from DOMAIN-008
market/session truth.

### 7.1 NSE

- New PAPER entry and LIVE entry attestation require a timestamp strictly
  before `15:00:00 IST`.
- Action at or after `15:00:00 IST` is rejected. For LIVE, both actual-entry
  and attestation-operation timestamps must precede the cutoff.
- Existing active-position monitoring may continue through the applicable
  DOMAIN-008 continuous-session boundary; session end does not assume an exit.

### 7.2 MCX

- New PAPER entry and LIVE entry attestation require a timestamp strictly
  before `23:00:00 IST`.
- Action at or after `23:00:00 IST` is rejected. For LIVE, both actual-entry
  and attestation-operation timestamps must precede the cutoff.
- Existing active-position monitoring may continue while DOMAIN-008 reports
  the applicable session open. Session end does not force-close the position.
- Forced MCX exit time and later-session automatic reactivation: **NONE
  APPROVED**.

### 7.3 Clock separation

There is no global Intraday cutoff. KRONOS must keep three clocks distinct:

1. DOMAIN-008 market clock;
2. Intraday new-entry clock; and
3. active-position lifecycle/exit clock.

## 8. MCX reference-market shadow domain

`MCX_REFERENCE_MARKET_RELATIONSHIP_V0` is approved for future validation with **SHADOW / VALIDATION ONLY** authority.

| MCX family | Reference market |
| --- | --- |
| GOLD / GOLDM | COMEX GOLD |
| SILVER / SILVERM | COMEX SILVER |
| COPPER | COMEX COPPER |
| CRUDEOIL | NYMEX CRUDE OIL |
| NATURALGAS | NYMEX NATURAL GAS |

Comparison is like-for-like: 1D ↔ 1D, 1H ↔ 1H, 15m ↔ 15m, and 5m ↔ 5m. The comparison axis is absolute event timestamp.

Trading authority is **NONE**. Cross-market price arithmetic is prohibited. A reference-market observation cannot directly create or reject an MCX trade. This work belongs to Slice 3V validation.

## 9. Shared Platform capabilities and consumption boundary

The following may be reused when they are genuinely governed as Platform capability:

- Provider authentication and authenticated read-only runtime;
- canonical Instrument identity and binding;
- market calendar and session infrastructure;
- Provider-neutral market-data and monitoring transport;
- WebSocket mechanics;
- credential and security boundaries;
- notification delivery infrastructure;
- Telegram delivery transport;
- persistence primitives and patterns;
- identity, version, provenance, and integrity patterns;
- Browser shell and composition infrastructure;
- Dashboard derivative aggregation; and
- the DOMAIN-007 architectural pattern, only where separately and explicitly approved for Intraday.

An existing Swing implementation is not automatically a Platform API. If Intraday needs a capability embedded in Swing, ownership must be decided first. A genuinely shared capability requires a separate bounded Platform work order; Intraday must not import Swing product code merely because the implementation is convenient.

### 9.1 Shared-file change rule

Ordinary Intraday work belongs under product-owned seams such as:

- `src/kronos/intraday/`;
- `src/kronos/application/intraday_*`;
- `src/kronos/browser/intraday_*`; and
- associated Intraday tests.

If Intraday requires a change to Provider, Instrument, Market, shared monitoring, shared notification delivery, shared Browser composition, or another shared Platform component, the work order must declare:

```text
SHARED-FILE CHANGE REQUIRED
```

Ordinary Intraday work then stops. Engineering must use a separate bounded Platform work order and prove both Swing and Intraday regression safety.

## 10. Trust and authority matrix

| Component | Authorized meaning | Explicitly not authorized |
| --- | --- | --- |
| DOMAIN-006 Provider | Factual Provider observations and authenticated read-only context | Product judgment, canonical identity, trading authority |
| DOMAIN-001 Instrument | Canonical Instrument identity and governed binding | Product eligibility or trading decision |
| DOMAIN-008 Market | Market, calendar, and session truth | Intraday entry/exit policy |
| Intraday Machine Facts | Deterministic facts | Analytical or trading consequence |
| Slice 3V | Validation and comparison only | Trading authority |
| Future Intraday analytical engine | Analytical classification only | Geometry, Risk, execution |
| Future Trade Construction | Geometry only | Risk observation or entry timing |
| Intraday DOMAIN-007 / WO-14 | Advisory Risk/loss-exposure observation only | Trade permission/veto, final quantity, Entry timing or broker execution |
| Future Entry Timing | Entry timing only | Risk reinterpretation or broker execution |
| Future lifecycle | Objective lifecycle; Sponsor position represented separately | Cross-product state mutation |
| Notifications | Delivery only | Analytical, Risk, lifecycle, or execution authority |
| Browser / Dashboard | Presentation only | Source-of-truth or decision authority |
| Broker autonomous execution | **NONE** | All autonomous order activity |

## 11. Fail-closed rules and commissioned lessons

The product must fail closed:

```text
missing evidence                         → UNAVAILABLE
stale evidence                           → UNAVAILABLE
identity mismatch                        → UNAVAILABLE
Provider/canonical geometry mismatch     → BINDING UNAVAILABLE
monitoring gap without authoritative proof → RECONCILIATION REQUIRED
```

Neutral or default values must not be inserted merely to keep a pipeline moving.

Commissioning has already demonstrated why these rules matter:

- strict DOMAIN-001 binding caught a stale RELIANCE tick size;
- factual reconciliation caught an incorrect NSE session expectation;
- operational verification caught a launcher using the wrong source checkout; and
- sanitized stage diagnostics replaced an unhelpfully generic runtime failure without leaking Provider secrets.

## 12. UI and presentation freeze

### 12.1 Product identity and density

Intraday retains its **GREEN** product identity.

Typography, information density, spacing, card scale, navigation typography, button scale, and layout rhythm must match the compact Swing Sponsor Browser pattern. Oversized Intraday typography is not the target.

```text
SWING-LIKE TYPOGRAPHY / DENSITY
+
INTRADAY GREEN PRODUCT IDENTITY
```

Visual pattern reuse is authorized. Swing analytical labels and state semantics are not.

### 12.2 Main-page triage rule

The main Intraday page is compact triage for approximately 12–15 names. Each card may show important current factual state and a very small number of useful observations, followed by:

```text
DETAILED EVIDENCE →
```

The main-page card must not repeat full 1D or 1H context, PDH/PDL, the complete Pivot ladder, CPR, OHLCV, all structural facts, or provenance. Those belong on a linked detailed-evidence route.

## 13. Swing methodology that does not transfer

The following Swing methodology must not be copied automatically into Intraday:

- the Swing 1W / 1D / 4H / 1H hierarchy;
- KR-370 K1–K5;
- the `0.5 × 1H ATR` path-clearance threshold;
- the `>2.0 ATR` extension policy;
- Swing completed-1H CPR acceptance;
- Swing setup-quality consequences;
- the Weekly Neutral rule;
- Swing BUY READY / BUY NOW / SELL READY / SELL NOW meanings;
- Swing Step-31 trade geometry;
- Swing KR-380 entry-trigger policy; and
- Swing Risk semantics.

Any Intraday methodology must arise from:

```text
Intraday evidence
    +
Intraday validation
    +
Sponsor / Chief Architect authorization
```

The Swing programme may contribute architecture, infrastructure, failure lessons, testing patterns, and presentation patterns. It does not contribute Intraday trading predicates by implication.

[ADR-0020](../../adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
now supplies the separately governed Chief-Architect authority for a distinct
Intraday WO-12 layer. It authorizes product-specific 15M K1–K5 adapters under
the common KR-370 state family; it does not retroactively transfer Swing's 1H,
weekly, 4H, path-distance, extension-threshold or visual-literal policy.

## 14. Current programme state

| Programme item | State |
| --- | --- |
| Slices 0–3 factual foundation | PUBLISHED |
| Real RELIANCE factual commissioning | PASS |
| Current WO-03 repository baseline | `76f97da9934aebff9b4de653bd028f2a26f11dfc` |
| Intraday factual publication checkpoint | `8cb3b3e3632107dae585a60fceb4f88be90194d0` |
| Native universe | 98 governed subjects; P5 reconciliation published |
| Native factual evaluability | 93 available; 5 prerequisite unavailable |
| Next stage | WO-15 source engineering only after ADR-0025 governance publication and synchronization |
| Slice 3V authority | VALIDATION ONLY |
| Slice 4 | NOT STARTED |
| Intraday WO-12 analytical state family | Common `KR370_ANALYTICAL_PROMOTION` reuse frozen by ADR-0020 |
| Trade Construction / WO-13 | ENGINEERING CLOSED |
| Risk Observation / WO-14 | ENGINEERING CLOSED; `RISK_OBSERVATION_ONLY` |
| Review Intake Correction | CLOSED; current Review bound to current Probables V2 |
| Entry Timing / WO-15 | ARCHITECTURE GOVERNED; SOURCE ENGINEERING HELD PENDING PUBLICATION |
| PAPER / LIVE position evidence and lifecycle / WO-17 | ARCHITECTURE GOVERNED; SOURCE ENGINEERING HELD PENDING PUBLICATION |
| Autonomous broker execution | NOT AUTHORIZED |

## 15. Governed work sequence

The CA-ratified sequence is maintained in the [Intraday V1 Programme
Roadmap](KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md): Track A begins WO-03A →
WO-03 → WO-05 → WO-06; WO-04 was found unnecessary by WO-03. Track B is WO-07 → conditional
WO-08 → WO-09; Track C is MCX prerequisites → WO-10; WO-11 through WO-24
then proceed in order. RELIANCE remains the commissioning/regression anchor.

## 16. Open policy and architecture items

The following remain unresolved or unimplemented and must not be inferred from factual foundations:

- WO-15 extension/chase threshold and severity bands;
- ATR veto, volume, RSI, Railway/SMA and level-proximity timing consequences;
- N-bar/time-based timing expiry and extension-alert threshold;
- option-premium execution timing and any new Entry indicator gates;
- WO-18 notification delivery and later Journal/Analytics contracts;
- any successor manual PAPER close, later-session carry/reactivation, quantity,
  monetary P&L or realised-R policy;
- any future forced MCX exit policy; and
- the governed Slice 3V contract for reference-market comparison.

## 17. Living-document control

This record is **LIVING DOCUMENT — V0.1**, not FINAL. A future governed work order must amend it when architecture or methodology is frozen, superseded, or commissioned. Amendments must preserve decision history, distinguish evidence from authority, and identify the authorizing Sponsor/EA/CA record.

The eventual production version may be published to GitHub and Google Drive only through separately authorized publication control.

## 18. Slice 3V factual / visual validation contract — WO-02

WO-02 publishes the Slice 3V V1 contract identities:

| Contract | Identity |
| --- | --- |
| Question set | `KRONOS-INTRADAY-SLICE-3V-QUESTION-SET-V1` |
| Visual Answer schema | `KRONOS-INTRADAY-SLICE-3V-VISUAL-ANSWER-V1` |
| Comparison policy | `KRONOS-INTRADAY-SLICE-3V-COMPARISON-POLICY-V1` |
| Validation record schema | `KRONOS-INTRADAY-SLICE-3V-VALIDATION-RECORD-V1` |

The contract compares independently observed chart facts with already-frozen machine evidence. The reviewer payload contains visual-only fields; KRONOS owns identity binding, comparison, discrepancy records, persistence, and integrity. Exact values compare exactly, relational observations compare only like-for-like, and approximate or hidden precision remains `NOT_VISUALLY_VERIFIABLE`. V1 defines no tolerance or acceptance threshold.

Individual results are `MATCH`, `MISMATCH`, `NOT_VISUALLY_VERIFIABLE`, `CHART_EVIDENCE_UNAVAILABLE`, `IDENTITY_MISMATCH`, `TIMEFRAME_MISMATCH`, or `OBSERVATION_BOUNDARY_MISMATCH`. These are factual validation results, not trading-quality states.

Native chart validation and future `MCX_REFERENCE_MARKET_RELATIONSHIP_V0` validation are separate evidence families. V1 reserves the relationship seam but does not implement cross-market comparison. The contract introduces no Discovery, promotion, Readiness, Trade Construction, Risk, PAPER/LIVE, OpenAI, or broker authority.

The complete published decision is recorded in [KRONOS Intraday Slice 3V Factual / Visual Validation Contract V1](KRONOS-INTRADAY-SLICE-3V-FACTUAL-VISUAL-VALIDATION-CONTRACT-V1.md).

## 19. WO-03A Native universe amendment

The Intraday-owned publication `KRONOS-INTRADAY-NATIVE-UNIVERSE-V1` `1.0.0`
preserves exactly 91 Sponsor equities, NIFTY, BANKNIFTY, and five persistent MCX
subjects (98 total). Membership is independent of Swing and Provider presence
and is not execution eligibility. DOMAIN-001 currently covers RELIANCE only;
the remaining 97 members stay governed with unavailable canonical binding until
a separate Platform publication closes the prerequisite.

That WO-03A-era prerequisite statement is historical. Platform P3/P4 and the
published P5 reconciliation now provide all 98 persistent/direct canonical
subjects; current machine-fact consumability is 93 available and five
prerequisite unavailable.

No standalone Swing-to-Intraday handover source exists in repository-accessible
material. Its wording is therefore not reconstructed. The incorporated rules
remain: share capability, not product state; reuse KRONOS architecture and
infrastructure patterns; do not inherit Swing numerical/trading policy; and
keep trades, watches, notifications, journals, and policy versions separate.

## 20. WO-03 Native Discovery V0 contract amendment

WO-03 establishes `KRONOS-INTRADAY-NATIVE-DISCOVERY-V0 / 0.1.0` as an
Intraday-owned factual-evaluability, candidate-contract and run-accounting
boundary. Every current run accounts for all 98 governed members. The
published P5 boundary yields 93 factually evaluable members and five explicit
prerequisite-unavailable members; it does not create a 93-member universe.

The structural family remains exactly 1D/1H/15m/5m and completed governed
candles remain structural authority. Current/incomplete candles are
observation only. The mandatory V0 bundle is limited to DOMAIN-008 session
truth, completed OHLCV, completeness/reconciliation, exact source identities,
versions, freshness and integrity. Existing pivots, CPR, structure, volume,
distance, R:R and session-position facts remain optional telemetry with no
admission consequence.

No numerical or directional methodology is frozen. ATR, SMA20/50/200, volume
consequence, path clearance, normalized extension and candidate thresholds
remain deferred. WO-03 found no missing mandatory machine fact for this
non-threshold contract, so WO-04 is skippable. WO-05 remains the scanner
implementation stage. Discovery does not create Analytical Promotion,
Trade Construction, Risk, Entry Timing, execution eligibility or broker
authority.

## 21. WO-05 runtime and Sponsor projection record

WO-05 implements the published non-threshold Native Discovery contract through
an Intraday-owned coordinator, immutable bundle/result/run persistence and a
read-only application snapshot. The existing product route seam is sufficient;
no shared Browser server or shared Browser renderer change is required.

The runtime is universe-driven and isolates per-member factual failure. The
current governed accounting remains 98 members with 93 pre-evaluable factual
paths and five explicit prerequisite-unavailable MCX results. Factual bundle
success preserves `NOT_EVALUATED` while admission methodology is deferred.

The main page follows `MAIN PAGE = TRIAGE`, using stable canonical presentation
ordering without ranking meaning. Detail routes explain governed evidence. The
Browser derives no machine fact or analytical state. Current failure cannot
replace the last successful run.

Controlled fixture evidence establishes 93 bundle-success paths, 372
four-timeframe fact requests, deterministic restart reconstruction and bounded
projection size. It establishes no production latency threshold. No real
Provider operation was performed. The separately governed next engineering
dependency is `DISCOVERY_OPERATIONAL_INVOCATION_SEAM_REQUIRED`; WO-06 remains
held until WO-05 review/publication and controlled real operational proof.

## 22. WO-05A operational invocation amendment

WO-05A closes the engineering invocation seam with
`KRONOS-INTRADAY-DISCOVERY-OPERATION-SERVICE-V0 / 0.1.0`. One explicit
Intraday-owned operation verifies the actual shared DOMAIN-006 lifecycle,
acquires a minimized `INSTRUMENTS + HISTORICAL_DATA` lease, builds the generic
93-member factual source, invokes the existing Discovery runtime, verifies
immutable persistence and updates the application snapshot. It creates no
second Provider context, Browser command endpoint, automatic startup operation
or retry.

The operation binds a composite of all eligible subject-scoped DOMAIN-008
sessions and one observation boundary. Five MCX prerequisite members remain
outside Provider acquisition. Concurrent operations fail closed, duplicate
completed identity is idempotent, and global failure preserves the last
successful run.

The CA successor-universe decision is recorded for a separate bounded work
order: V1/1.0.0 stays immutable at 98, while a later governed successor may use
publication-driven non-empty variable cardinality. WO-05A implements no such
contract change. Candidate methodology and all downstream authority remain
deferred.

## 23. WO-05B bounded operational control amendment

WO-05B freezes the remaining defect as
`DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE` and closes it with the
Intraday-owned
`KRONOS-INTRADAY-DISCOVERY-OPERATIONAL-CONTROL-V0 / 0.1.0`. The loopback
Browser exposes only `GET /control/intraday-discovery/status` and
`POST /control/intraday-discovery`. GET is side-effect free. POST accepts one
bounded request label and timezone-aware observation boundary, then invokes the
already-composed WO-05A service inside the existing KRONOS process.

This is an explicit shared-file exception under the Intraday Shared-File Change
Rule. `kronos.browser.server` supplies only bounded HTTP transport and
`tools.kronos_browser.py` injects the Intraday-owned control over the exact
shared DOMAIN-006 runtime already used by Swing and Platform commissioning.
No generic action framework, second Provider context, automatic authentication,
startup operation or Sponsor trading control is introduced.

The candidate is ready for a separately authorized controlled real Discovery
run after review, publication and restart. Authentication is required only if
the actual shared context is not active. No real Provider acquisition,
authentication or restart occurred in WO-05B.

## 24. WO-06 Part-1 qualification-foundation amendment

WO-06 Part 1 introduces Intraday-owned, immutable research contracts for
qualification hypotheses, multi-session corpora, observations, factual outcome
definitions, population diagnostics and reports. It commissions the
Sponsor-specified `NARROW_CPR_KGS_V0` calculation from the previous completed
Daily candle using the strict `abs(P - BC_RAW) < 0.001 × C` boundary and retains
both raw and normalized CPR levels.

The calculation is an available deterministic qualification fact only. Market
usefulness is not established, Probables methodology is not commissioned, and
directional consequence is none. Synthetic fixtures cannot establish efficacy
or approve methodology. All candidate-formation evidence must be available at
or before its observation boundary; subsequent facts belong only to versioned
factual outcome evidence and never to trade outcome.

Population zero/flooding buckets are diagnostics without admission authority.
There is no fixed quota, top-N, score, ranking, fixed universe capacity or
successor-universe implementation. The first real operation supplied no corpus,
so evidence remains `EVIDENCE_PENDING_REAL_DISCOVERY_RUN`. The complete Part-1
boundary is recorded in the [WO-06 Part-1 Qualification
Foundation](KRONOS-INTRADAY-WO-06-PART-1-QUALIFICATION-FOUNDATION.md).

## 25. WO-06 Part-2 methodology-research amendment

WO-06 Part 2 adds Intraday-owned explicit methodology variants, staged
qualification, mandatory/supporting/veto/informational roles, research-only
Long/Short/neutral/conflict states, stage attrition, population calibration,
ablation, versioned factual outcome proposals and exact real-corpus binding.
These are comparison mechanics, not production Probable admission.

The current governed fact surface is sufficient for research representation;
ATR and SMA are not required now. Volume thresholds remain deferred, and any
nearest/important barrier consequence requires a separately governed selection
methodology. No real post-activation corpus exists, so Narrow CPR usefulness,
all directional methodologies and the final Probables methodology remain
unsupported. `METHODOLOGY_FREEZE_READY = NO`; Part 3 is not started. The full
boundary is recorded in [WO-06 Part-2 Probables Methodology
Research](KRONOS-INTRADAY-WO-06-PART-2-PROBABLES-METHODOLOGY-RESEARCH.md).

## 26. WO-06H historical qualification-reconstruction amendment

WO-06H introduces a separate Intraday-owned research contract for reconstructing
completed historical qualification facts for the current governed subject set.
It does not backdate the universe or reuse production Discovery state. The
production `observation_boundary < universe.valid_from → PUBLICATION_STALE`
rule remains unchanged.

Reconstruction binds exact current subject-set, canonical reconciliation,
DOMAIN-008 target and previous-session schedules, governed observation boundary,
completed 1D/1H/15M/5M facts, source identities and integrity. Inputs must have
been available at the boundary; later outcomes remain separate. Historical,
post-activation production and synthetic evidence stay distinct. Exact corpus
eligibility requires a later explicit binding and never appends automatically.

WO-06HA closes the engineering seam with the product-owned
`KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-V0 / 0.1.0` and the
`COMPLETED_SESSION_EOD_RESEARCH_V0` boundary. Explicit sessions are resolved by
DOMAIN-008, the complete request plan is bounded before a single minimized
shared read-only lease, execution is sequential without retry, and immutable
artifacts are reloaded by exact identity. The current five unavailable MCX
subjects remain represented and cause zero Provider requests. No Browser or
startup invocation, authentication, automatic corpus binding or production
state mutation is introduced. Real acquisition remains separately authorized.
The full seam is recorded in [WO-06HA Historical Research Operational
Seam](KRONOS-INTRADAY-WO-06HA-HISTORICAL-RESEARCH-OPERATIONAL-SEAM.md).

## 27. Deferred multi-refresh analysis-run requirement

WO-06HJ records, but does not commission, the Sponsor requirement that every
future Refresh Analysis creates a new immutable governed analysis run at the
latest completed authorized candle boundary. Probables are
observation-boundary-specific and may change during the same trading day.
Earlier analysis runs remain immutable and inspectable.

A later refresh must not rewrite an already-open PAPER or LIVE trade
lifecycle. Commissioning belongs to WO-06 Part 3/runtime work and its
downstream lifecycle architecture; WO-06HJ introduces no refresh operation,
Probable admission, trade mutation, or lifecycle authority.

## 28. WO-06 Part-3 V0 Probables methodology amendment

WO-06 Part 3 freezes the WO-06S Variant-G evidence conclusion as
`KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V1 / 1.0.0`. Narrow CPR TRUE is required
admission support; completed 1H, completed 15M and explicit coherence are
mandatory; participation is supporting/non-blocking; completed 1D, completed
5M, PDH/PDL, CPR location and Classic Pivots are informational.

Long requires exact Long agreement across 1H, 15M and coherence; Short requires
exact Short agreement. Non-directional and conflicting members are not
admitted. Missing evidence remains unavailable. No score, rank, Top-N, quota,
threshold, fallback or performance claim exists.

The production evaluator reproduces the retained real sessions exactly as
14/7/6/17/18, aggregating 17 Long and 45 Short. This is population-health
evidence only; outcome evidence remains `ABSENT_PENDING`. Immutable runs bind
exact source facts and subject-aware boundaries, preserve earlier runs, keep a
later failure separate from the last success and project through a Provider-
free Browser view.

Part 3 commissions Probables for deeper review only. It does not commission
3V Review, Promotion, Trade Construction, Risk, Entry Timing, PAPER/LIVE,
lifecycle, notification, journal or broker authority. WO-06 remains open for
WO-06V, WO-06L and WO-06E2E. The complete freeze is recorded in
[WO-06 Part-3 V0 Probables Methodology](KRONOS-INTRADAY-WO-06-PART-3-V0-PROBABLES-METHODOLOGY.md).

## 29. WO-06MCX-A DOMAIN-008 expiry-session amendment

WO-06MCX-A closes `MCX_DOMAIN008_SESSION_GAP` with the platform-owned
`KRONOS-MCX-CONTRACT-FAMILY-SESSION-V1 / 1` contract and immutable 2026
publication. DOMAIN-008 now resolves a governed MCX family, contract expiry,
trading date and historical observation boundary into pre-expiry,
expiry-at-or-before-cutoff, expiry-after-cutoff or post-expiry state.

GOLDM, SILVERM, NATURALGAS and CRUDEOIL retain their independently sourced
normal MCX session on expiry. COPPER alone has the sourced 17:00 expiry close.
NATGAS → NATURALGAS and CRUDE → CRUDEOIL are explicit governed aliases rather
than inferred mappings. The cutoff instant is inclusive for expiry-day
eligibility; any later observation is ineligible.

Expiry schedules are completed-candle authority, so Copper acquisition cannot
expect candles after 17:00 on its expiry date. Unknown families, uncovered or
source-unqualified dates, missing publications and invalid integrity fail
closed as `MCX_CONTRACT_SESSION_UNAVAILABLE`; the generic 23:30 session is not
a fallback.

DOMAIN-008 supplies this factual session authority. No contract selection,
Discovery, Probables, Risk or broker authority is introduced here.

## 30. WO-06MCX-R governed active derivative selection amendment

ADR-0017 authorizes DOMAIN-001 to resolve an analytical derivative subject to
one immutable active contract binding. The subject remains GOLDM, SILVERM,
COPPER, NATGAS or CRUDE; the expiry-specific Kite symbol is contract lineage,
not product identity. Exact mappings are GOLDM → GOLDM, SILVERM → SILVERM,
COPPER → COPPER, NATGAS → NATURALGAS and CRUDE → CRUDEOIL. Fuzzy matching is
prohibited.

Each governed Refresh performs one complete DOMAIN-006 instrument-master read,
filters exact MCX FUT records, consumes DOMAIN-008 family/expiry eligibility and
selects the unique minimum eligible expiry. A tie at that expiry fails closed;
Provider ordering, symbol and token are not tie-breakers. Provider absence,
staleness or an unavailable DOMAIN-008 fact also fails closed, with no prior
binding fallback.

The binding records the observation and eligibility boundaries, exact Provider
record and mapping directive identities, DOMAIN-008 publication/session facts,
catalogue and snapshot integrity, and deterministic provenance. It never
persists a Provider token. A roll creates a new binding and optional supersedes
link; old bindings and Discovery/Probables runs remain immutable. Browser GET
loads persisted lineage only and performs no resolution or Provider read.

Active derivative binding is analytical availability only. It does not create
execution eligibility, alter the frozen Probables methodology, or grant trading,
Risk or broker authority.

## 31. WO-07 governed Native Review amendment

WO-07 establishes the Intraday-owned Review Handoff, Review Cycle, immutable
Chart Revision, exact-current Review pointer and governed Q1-Q10 Question Pack.
Only current Long/Short Probables are eligible. The frozen manual chart is one
1D | 1H | 15M | 5M composite; chart receipt establishes `CHART_READY` but does
not establish visual analysis, Readiness, Promotion or trading authority.

The exact evidence-cycle identity binds the Probables run/member, Discovery
run/member, observation boundary, canonical subject, Review Cycle/Request,
Chart Revision and Review Pack. Restart uses an explicit integrity-bound
pointer and never directory, mtime, instrument or revision-ordinal guessing.

Canonical JSON remains authority and deterministic PDF is Sponsor transport.
Expected canonical identity stays separate from future independently observed
chart identity. The Chart Analyst trust boundary is visual evidence only and
WO-09 retains exclusive future Answer-import authority. Full detail is recorded
in [WO-07 Governed Native Review](KRONOS-INTRADAY-WO-07-GOVERNED-NATIVE-REVIEW-V1.md).

WO-07A adds the Sponsor's paste-first, multi-card Review workflow. Clipboard
paste and file upload share one candidate-bound governed chart-intake path.
`CREATE ALL REVIEW PDF` creates or reuses independent current Question Packs,
reports per-candidate created/reused/skipped/failed state and may export one
combined transport-only PDF with deterministic membership. Individual packs
remain authoritative. `UPLOAD ALL ANSWERS` remains disabled until WO-09 and no
inbox scan or Answer import occurs. See
[WO-07A Sponsor Review UX and Batch Transport](KRONOS-INTRADAY-WO-07A-SPONSOR-REVIEW-UX-AND-BATCH-TRANSPORT-V1.md).

## 32. WO-09 governed Chart Analyst Answer import amendment

WO-09 commissions `KRONOS-INTRADAY-CHART-ANALYST-ANSWER-PACK-V1 / 1.0.0`
and `KRONOS-INTRADAY-IMPORTED-VISUAL-EVIDENCE-V1 / 1.0.0`. One strict JSON
Answer Pack carries exact ordered Q1-Q10 visual observations and independently
reported chart identity. It contains no machine provenance, Provider token,
trading field or analytical consequence. The optional extraction-confidence
field was not copied because Swing does not provide a bounded product-neutral
enum.

KRONOS validates exact Question Set, Review Pack, Review Cycle/Request, Chart
Revision, expected subject and proposed direction, then independently requires
the observed visible subject to equal the expected subject before creating
trusted evidence. An unreadable or mismatched identity fails closed. Individual
`UPLOAD ANSWER` and candidate-isolated `UPLOAD ALL ANSWERS` resolve only the
deterministic filename for each exact current Question Pack in the governed
Answer inbox. There is no recursive, mtime or latest-file selection, and
combined-answer transport is not accepted.

Validated Answer Packs, import records and trusted evidence are append-only.
An explicit integrity-bound pointer per Review Pack restores trusted evidence;
a later missing, invalid or conflicting input cannot blank or replace prior
valid evidence. Browser projection is compact factual Q1-Q10 evidence only.
WO-10 exclusively owns any future reconciliation, consequence, Readiness or
Promotion semantics. See [WO-09 Governed Chart Analyst Answer Import](KRONOS-INTRADAY-WO-09-GOVERNED-CHART-ANALYST-ANSWER-IMPORT-V1.md).

## 33. WO-10 deterministic Native + visual reconciliation amendment

WO-10 freezes and implements the Intraday-owned
`KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-POLICY-V1 / 1.0.0` under
`POLICY_B_CORE_STRUCTURE` and
`STATUS_POLICY_2_COMPLETE_IF_CORE_OBSERVED`. Q2 and Q4 are the only mandatory
core visual conditions. Review is exactly incomplete, required or complete;
Readiness is exactly not ready or analytically ready; Promotion is exactly not
promoted or promoted. Promotion inherits the Native Probable direction and
never flips it.

Q1, Q7 and Q8 remain informational. Q3 and the stalling branch of Q5 remain
adverse non-blocking. Q5 opposing structure, Q9 rejection against direction,
and Q10 material observation require review and are terminal for automatic
Promotion. Q6 remains supporting and non-blocking. No score, weight, rank,
vote, quota, free-text interpretation or Entry consequence exists.

Reconciliation is an explicit product-owned operation over persisted exact-
cycle evidence. It performs no Provider, Discovery, Probables, Answer-import
or Chart Analyst operation. Immutable facts, run, Review, Readiness, Promotion
and explicit current pointer restore without Provider access. New evidence or
policy inputs produce a new immutable result; historical evidence is never
rewritten. Full details are in [WO-10 Native + Visual Reconciliation](KRONOS-INTRADAY-WO-10-NATIVE-VISUAL-RECONCILIATION-V1.md).

### 33A. WO-10 E/I/M successor-governance amendment

The preceding section remains the historical WO-10 V1 Q1–Q10 implementation
record. It does not govern the frozen WO-10E/WO-10I/WO-10M successor.

The successor uses a product-local seven-state analytical-reconciliation
family: `CONTEXT_INCOMPLETE`, `INVALIDATED`, `WEAKENING`,
`HELD_BY_CONTRADICTION`, `WAIT_SETUP_DEVELOPMENT`,
`WAIT_IMMEDIATE_CONFIRMATION` and `PROMOTION_READY`, in that precedence order.
The states are pre-KR-370 product states. No state is equivalent or
automatically mapped to ADR-0011 `BUY_NOW`, `SELL_NOW`, `BUY_READY`,
`SELL_READY`, a potential state or `NO_SETUP`.

WO-10E, WO-10I and WO-10M decide independently. WO-11 only validates,
collates and publishes exact results with zero analytical discretion. Exact
frozen family policy, empirical deferrals and downstream exclusions are in
[WO-10 E/I/M Frozen Architecture V1](KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
and [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md).
No classifier or operation is authorized by this amendment itself. The later
additive [ADR-0020](../../adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
authorizes a distinct WO-12 evaluation layer without changing any WO-10 or
WO-11 state meaning.

## 34. WO-06E phase-aware Probables V2 methodology freeze

WO-06E-FREEZE establishes
`KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2 / 2.0.0` without changing immutable
V1 evidence or production source. The exact phase family is `OPENING`,
`STRUCTURE`, `FIRST_CURRENT_SESSION_1H` and
`CURRENT_SESSION_ESTABLISHED`; selection is driven by DOMAIN-008 sessions and
governed completed evidence, never fixed clock labels.

Opening uses the prior valid session's completed 1H regime as explicit context,
the first current-session completed 15M as direction, exactly three constituent
completed 5M candles, and aligned `NSE-INDEX-NIFTY` relative context where
applicable. Narrow CPR remains required admission support. Typed prior-1H,
Opening-5M and NIFTY conflicts fail closed as not admitted without creating or
flipping direction. Missing mandatory evidence remains unavailable.

The first current-session 1H becomes primary immediately; two current 1H
candles are required only for the established phase. Current-phase NIFTY
calculations after Opening remain deferred. MCX is structurally supportable but
not empirically commissioned. Score, rank, weight, quota, confidence and
relative-strength magnitude thresholds remain absent.

The deterministic publication is
`INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-7B75EE711558F706CFB97B4548952B8924A8CBD8E519EFEEE61B53828FDD9F89`,
with canonical payload SHA-256
`7b75ee711558f706cfb97b4548952b8924a8cbd8e519efeee61b53828fdd9f89`.
Implementation, runtime, Review, Promotion, Entry, Trade, Risk, PAPER/LIVE and
broker authority are not introduced. Full authority is recorded in
[WO-06E Phase-Aware Probables V2 Methodology](KRONOS-INTRADAY-WO-06E-PHASE-AWARE-PROBABLES-V2-METHODOLOGY.md).

## 35. WO-12 KR-370 analytical-promotion governance amendment

ADR-0020 establishes WO-12 as the distinct KR-370 analytical-promotion layer
after WO-11. ADR-0019 remains valid: no WO-10 state and no WO-11 eligibility
value is a KR-370 state. WO-12 must evaluate newly bound evidence rather than
rename or remap an upstream result.

WO-12 reuses `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1`, owner `KR-370`, state
family `KR370_ANALYTICAL_PROMOTION` and the seven common analytical states. The
Intraday V1 criteria are exactly:

1. `K1_15M_DIRECTIONAL_PROGRESSION`;
2. `K2_15M_CPR_ACCEPTANCE`;
3. `K3_15M_IMMEDIATE_PATH_CLEARANCE`;
4. `K4_15M_SETUP_QUALITY`; and
5. `K5_15M_NON_EXTENSION`.

The criterion frame is 15M. 1H remains upstream context and 5M remains outside
WO-12 under WO-15 / KR-380 final timing. K2 uses the strict completed-15M-close
relationship to CPR upper/TC for LONG and lower/BC for SHORT. K3 is
structure-only and has no distance, ATR, R:R or trade-geometry threshold. K4
adapts already-governed Intraday Native/visual reconciliation without a new
Chart Analyst operation or copied Swing literals.

K5 authorizes only factual ATR-normalized measurement from an exact governed
15M structural origin. `MATERIAL_EXTENSION_THRESHOLD = POLICY_UNRESOLVED`, so
K5 consequence remains `UNAVAILABLE` and full NOW commissioning remains held.
Swing's `>2 × 1H ATR` is not copied.

Exactly five available criteria use the common maturity grammar: five
satisfied → NOW, four → READY, two or three → POTENTIAL, zero or one →
`NO_SETUP`. Any unavailable mandatory criterion fails closed to `NO_SETUP`.
The only universal hard gates are invalid exact binding, mandatory criterion
unavailable, governing 15M structure failure and authoritative governed
directional conflict.

Only exact current `BUY_NOW` / `SELL_NOW` may establish eligibility for the
separately governed WO-13 boundary. WO-12 has no Entry, Stop, Target, R:R,
Risk, Sponsor-decision, 5M timing or broker authority. Bounded source
engineering is authorized; runtime/control/Browser integration remains
separately sliced and no real WO-12 operation is authorized by this amendment.
The complete historical product architecture is recorded in [WO-12 KR-370
Analytical Promotion V1](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md).

### 35.1 WO-12 V2 successor correction

[ADR-0021](../../adr/ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
supersedes only the Intraday five-criterion/K5 clauses above. It preserves this
section as V1 history and establishes the current four-criterion WO-12 V2:

1. `K1_15M_DIRECTIONAL_PROGRESSION`;
2. `K2_15M_CPR_ACCEPTANCE`;
3. `K3_15M_IMMEDIATE_PATH_CLEARANCE`; and
4. `K4_15M_SETUP_QUALITY`.

Four satisfied means NOW, three READY, two POTENTIAL, and zero or one
`NO_SETUP`; unavailable K1–K4 fails closed. The public KR-370 state family is
unchanged. K5 is no longer a WO-12 criterion or mandatory gate. Its historical
origin, completed-15M ATR, extension and forward-outcome artifacts remain
supporting research/telemetry for future WO-15 extension/chase design only.
WO-15 owns any future 5M ATR/reference methodology and no such consequence is
commissioned here. Swing retains its independent five-criterion semantics.

The current product architecture is [WO-12 KR-370 Analytical Promotion
V2](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md).

## 35.2 WO-13 Step-31 trade-construction governance amendment

[ADR-0022](../../adr/ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
supplies the separately governed Intraday WO-12 → WO-13 crossing that
ADR-0020 explicitly left unauthorized. Only an exact current integrity-valid
WO-12 V2 `BUY_NOW` or `SELL_NOW` may enter. Direction and setup family are
inherited and immutable.

WO-13 owns 15M Trade Plan geometry only. The two explicit setup families are
`INTRADAY_PULLBACK_CONTINUATION` and `INTRADAY_RANGE_BREAKOUT`. Pullback
geometry uses the exact 15M qualification/resumption candle, governing pullback
structure and prior directional impulse extreme. Range-breakout geometry uses
the immutable original range and exact breakout qualification candle. A
setup-native Target is derived before the nearest legitimate forward
structural objective may constrain it. R:R evaluates the resulting geometry
and has no minimum V1 gate.

Equity remains stock-local, Index underlying-local and MCX exact active-
contract-local/roll-safe. NIFTY, option premium, COMEX/NYMEX and USDINR cannot
replace local geometry. 1H is context only; 5M and extension/chase remain
WO-15. WO-14 remains DOMAIN-007 Risk. Runtime, Browser and real operation are
separately gated. The complete product record is [WO-13 Step-31 Trade
Construction V1](KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md).

## 35.3 WO-14 advisory Risk-observation governance amendment

[ADR-0023](../../adr/ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
supersedes only ADR-0022's permission-oriented downstream WO-14 clause. For
Intraday, DOMAIN-007 answers what observable downside exposure would exist if
an exact immutable WO-13 plan were taken. Its authority is
`RISK_OBSERVATION_ONLY`; it cannot approve, reject, constrain, block or execute
the trade and cannot alter WO-13 geometry.

The successor contract
`KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1 / 1.0.0` uses
`RISK_OBSERVED`, informational `RISK_ALERT`, and `RISK_UNAVAILABLE`. Initial
severity is `UNCLASSIFIED`; no numerical alert threshold or veto is frozen.
Sponsor owns participation and actual quantity. WO-15 remains the exclusive 5M
timing and extension/chase owner. Swing DOMAIN-007 permission semantics remain
unchanged.

Architecture and factual methodology are frozen, but source engineering must
wait for the actual published WO-13 Trade Plan/handoff contracts and a separate
instruction. Runtime, Browser, Provider calls, real observation and WO-15 are
not authorized. The complete product record is [WO-14 DOMAIN-007 Risk
Observation V1](KRONOS-INTRADAY-WO-14-DOMAIN-007-RISK-OBSERVATION-V1.md).

## 35.4 WO-15 KR-380 completed-5M Entry Timing governance amendment

[ADR-0025](../../adr/ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md)
freezes `KRONOS-INTRADAY-WO15-ENTRY-TIMING-V1 / 1.0.0` as the complete WO-15
A/B/C/D architecture. Authority is exactly
`COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY` against one exact current
immutable `KRONOS-INTRADAY-WO13-TRADE-PLAN-V1`.

WO-15A owns the WO-13 handoff/trust boundary; WO-15B owns exact completed-5M
Pullback and Range-Breakout Direct/Retest/Resumption timing grammar; WO-15C
owns advisory extension and research telemetry; WO-15D owns immutable timing
cycles, append-only transitions and the versioned
`KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1 / 1.0.0` boundary. Direction, setup,
Entry, Stop, Target, invalidation and Model R:R remain immutable WO-13 facts.

The six states are `TIMING_NOT_EVALUATED`, `TIMING_WAITING`,
`TIMING_QUALIFIED`, `TIMING_FAILED`, `TIMING_EXPIRED` and
`TIMING_UNAVAILABLE`. Trust failure precedes expiry, explicit failure,
qualification and waiting. Completed governed 5M candles alone carry timing
authority; incomplete candles, LTP and wick-only crossings do not.

LONG requires a strict completed Close above Entry plus aligned governed 5M
progression; SHORT is strict below Entry plus aligned progression. Equality
does not qualify. One completed close is sufficient; there is no Entry buffer,
two-close requirement, mandatory retest, volume, RSI or Railway gate.
Pullback failure requires explicit opposing governed progression. Range
Breakout permits both Direct Acceptance and Retest/Resumption with exact
zero-tolerance candle rules. Timing failure never rewrites the 15M thesis.

Every opportunity owns immutable `timing_cycle_id`; the first cycle begins at
the first valid post-plan completed-5M evaluation boundary, not first Entry
interaction. Multiple cycles require a terminal failed predecessor and exact
deterministic reset. Qualification is historical truth; later failure or expiry
is a new immutable transition. There is no cooldown, maximum attempt count,
N-bar/minute TTL or overnight carry.

Completed-5M directional/absolute extension and Wilder/RMA ATR-14 normalized
extension are `ADVISORY_RESEARCH_ONLY`. Invalid ATR makes normalization
unavailable. Severity remains `UNCLASSIFIED`; thresholds and veto authority are
none. Existing volume, RSI, SMA/Railway, CPR, PDH/PDL and Pivot facts remain
context/research only.

WO-14 is independent advisory context and never a timing prerequisite or veto.
The timing handoff may preserve a Risk observation reference for audit/context
only. Equity timing is stock-local, Index timing is underlying-local and MCX
timing is exact active-contract-local/roll-safe; option premium and
COMEX/NYMEX/USDINR cannot substitute. NATGAS remains operationally held.

`TIMING_QUALIFIED` is not execution. Sponsor Decision, PAPER/LIVE/IGNORE,
position, order, fill and broker authority remain downstream and absent. The
canonical policy payload is
[KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json](KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json),
SHA-256 `d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26`.
No WO-15 production source, persistence, runtime, Browser, Provider operation
or real timing evaluation is authorized by this amendment.

## 35.5 WO-17 position evidence and lifecycle-monitoring governance amendment

[ADR-0027](../../adr/ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING.md)
freezes
`KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1 / 1.0.0`
with authority exactly
`FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY`.

Only an exact WO-16 PAPER or LIVE decision plus
`PENDING_POSITION_EVIDENCE` enters WO-17; IGNORE is excluded. The complete
WO-13/14/15/16, DOMAIN-008, canonical Instrument and MCX contract/roll graph is
bound without recalculation. WO-14 remains advisory and non-veto.

PAPER begins `PAPER_ARMED`; the first factual observation is baseline only and
two ordered, consecutive, continuous observations must prove a directional
Entry Reference crossing before `PAPER_ENTRY_OBSERVED` and `PAPER_ACTIVE` can
exist. LIVE begins `LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE` and requires exact
Sponsor-attested actual entry price/time and lineage before
`LIVE_ENTRY_ATTESTED` and `LIVE_ACTIVE`. Neither is broker truth. Quantity,
monetary P&L and realised R remain `UNAVAILABLE`.

NSE entry and LIVE attestation require all applicable timestamps strictly
before `15:00:00 IST`; MCX requires strictly before `23:00:00 IST`. At or after
the cutoff is rejected. This supersedes the former deferred exact-NSE-cutoff
wording. DOMAIN-008 continues to own session truth.

There is at most one non-closed WO-17 position per canonical subject. A
preserved prior-session position blocks activation of a successor WO-16
decision without mutating that decision. MCX position lineage cannot migrate
automatically to a new contract or roll.

Active monitoring may reuse the shared DOMAIN-006 read-only Kite WebSocket, but
all position/event/history identities are Intraday-owned. Availability is
separate from position state. Interruption preserves position; recovery
requires a fresh baseline; missed crossings are never inferred. Ambiguous Stop
and Target order remains `LIFECYCLE_EVENT_ORDER_UNRESOLVED` and does not close
or create economics.

PAPER closes only from an unambiguous ordered Stop or Target crossing. LIVE
closes only from Sponsor-attested actual exit evidence. Session end preserves
position/history and grants no forced exit, carry or automatic later-session
reactivation. WO-17 may publish notification-worthy facts, while delivery
belongs exclusively to WO-18. Production contracts, source, runtime, Browser,
position creation and monitoring remain separately gated.

## 36. References

- [Intraday Shared-File Change Rule](../../../engineering/INTRADAY-SHARED-FILE-CHANGE-RULE.md)
- [Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [Platform Overview](../../platform/PLATFORM_OVERVIEW.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Intraday product architecture index](README.md)
- [Native Universe V1](KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md)
- [Programme Roadmap](KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md)
- [Machine-Fact Catalogue](KRONOS-INTRADAY-MACHINE-FACT-CATALOGUE.md)
- [Contract/State Ownership Registry](KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Deferred Decision Register](KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md)
- [Native Discovery V0 Contract](KRONOS-INTRADAY-NATIVE-DISCOVERY-V0-CONTRACT.md)
- [WO-05 Native Discovery Runtime](KRONOS-INTRADAY-WO-05-NATIVE-DISCOVERY-RUNTIME.md)
- [WO-05A Operational Invocation](KRONOS-INTRADAY-WO-05A-OPERATIONAL-INVOCATION.md)
- [WO-05B Bounded Operational Control](KRONOS-INTRADAY-WO-05B-BOUNDED-OPERATIONAL-CONTROL.md)
- [WO-06 Part-1 Qualification Foundation](KRONOS-INTRADAY-WO-06-PART-1-QUALIFICATION-FOUNDATION.md)
- [WO-06 Part-2 Probables Methodology Research](KRONOS-INTRADAY-WO-06-PART-2-PROBABLES-METHODOLOGY-RESEARCH.md)
- [WO-06H Historical Qualification Reconstruction](KRONOS-INTRADAY-WO-06H-HISTORICAL-QUALIFICATION-RECONSTRUCTION.md)
- [WO-06HA Historical Research Operational Seam](KRONOS-INTRADAY-WO-06HA-HISTORICAL-RESEARCH-OPERATIONAL-SEAM.md)
- [WO-06 Part-3 V0 Probables Methodology](KRONOS-INTRADAY-WO-06-PART-3-V0-PROBABLES-METHODOLOGY.md)
- [WO-06E Phase-Aware Probables V2 Methodology](KRONOS-INTRADAY-WO-06E-PHASE-AWARE-PROBABLES-V2-METHODOLOGY.md)
- [WO-06E Probables V2 Canonical Payload](KRONOS-INTRADAY-WO-06E-PROBABLES-V2-METHODOLOGY-PAYLOAD.json)
- [WO-07 Governed Native Review](KRONOS-INTRADAY-WO-07-GOVERNED-NATIVE-REVIEW-V1.md)
- [WO-07A Sponsor Review UX and Batch Transport](KRONOS-INTRADAY-WO-07A-SPONSOR-REVIEW-UX-AND-BATCH-TRANSPORT-V1.md)
- [WO-10 Native + Visual Reconciliation](KRONOS-INTRADAY-WO-10-NATIVE-VISUAL-RECONCILIATION-V1.md)
- [WO-10 E/I/M Frozen Architecture V1](KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
- [ADR-0019 — Intraday WO-10/WO-11 Pre-KR-370 Semantic Boundary](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
- [ADR-0020 — Intraday WO-11 to WO-12 KR-370 Analytical Promotion Boundary](../../adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
- [ADR-0021 — Intraday WO-12 Four-Criterion Promotion and WO-15 Extension Ownership](../../adr/ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
- [ADR-0022 — Intraday WO-12 to WO-13 Step-31 Trade Construction Boundary](../../adr/ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
- [ADR-0023 — Intraday DOMAIN-007 Advisory Risk Observation Boundary](../../adr/ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
- [ADR-0025 — Intraday WO-15 / KR-380 Completed-5M Entry Timing Boundary](../../adr/ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md)
- [ADR-0026 — Intraday WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission](../../adr/ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-LIFECYCLE-ADMISSION.md)
- [ADR-0027 — Intraday WO-17 Position Evidence and Active Lifecycle Monitoring](../../adr/ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING.md)
- [WO-12 KR-370 Analytical Promotion V1](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md)
- [WO-12 KR-370 Analytical Promotion V2](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md)
- [WO-13 Step-31 Trade Construction V1](KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md)
- [WO-14 DOMAIN-007 Risk Observation V1](KRONOS-INTRADAY-WO-14-DOMAIN-007-RISK-OBSERVATION-V1.md)
- [WO-15 KR-380 Entry Timing V1](KRONOS-INTRADAY-WO-15-KR380-ENTRY-TIMING-V1.md)
- [WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission V1](KRONOS-INTRADAY-WO-16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md)
- [WO-17 Position Evidence and Active Lifecycle Monitoring V1](KRONOS-INTRADAY-WO-17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1.md)
- [WO-09 Governed Chart Analyst Answer Import](KRONOS-INTRADAY-WO-09-GOVERNED-CHART-ANALYST-ANSWER-IMPORT-V1.md)
- [ADR-0017 Governed Active Derivative Contract Selection](../../adr/ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md)
