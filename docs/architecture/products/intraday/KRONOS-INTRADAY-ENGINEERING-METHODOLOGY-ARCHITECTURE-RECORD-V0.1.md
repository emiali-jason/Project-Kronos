# KRONOS Intraday Engineering, Methodology & Architecture Record

**Status:** LIVING DOCUMENT — V0.1; published and amended through WO-03A review candidate

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

## 7. Future product trading clocks — not implemented

These are **FUTURE POLICY — NOT IMPLEMENTED**. They are separate from DOMAIN-008 market/session truth.

### 7.1 NSE

- New entry: not permitted after 15:00 IST.
- Existing-position exit: permitted through 15:15 IST.
- Exact semantics at precisely `15:00:00`: **DEFERRED / UNRESOLVED**.

### 7.2 MCX

- New entry: not permitted after 23:00 IST.
- An existing position may remain active after 23:00.
- Exit may occur after 23:00.
- Forced MCX exit time: **NONE APPROVED**.

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
| Future Trade Construction | Geometry only | Risk permission or entry timing |
| Future DOMAIN-007 policy | Risk permission only | Entry timing or broker execution |
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

## 14. Current programme state

| Programme item | State |
| --- | --- |
| Slices 0–3 factual foundation | PUBLISHED |
| Real RELIANCE factual commissioning | PASS |
| Current repository baseline | `542c84fbacbd9f1bfb2997255b90f00495ba4544` |
| Intraday factual publication checkpoint | `8cb3b3e3632107dae585a60fceb4f88be90194d0` |
| Native universe | 98 Sponsor-approved subjects; WO-03A review candidate |
| Next stage | WO-03 NATIVE DISCOVERY, after canonical prerequisites required by its scope |
| Slice 3V authority | VALIDATION ONLY |
| Slice 4 | NOT STARTED |
| Intraday analytical state family | NOT FROZEN |
| Trade Construction | NOT STARTED |
| Risk | NOT STARTED |
| Entry Timing | NOT STARTED |
| PAPER / LIVE | NOT STARTED |
| Autonomous broker execution | NOT AUTHORIZED |

## 15. Governed work sequence

The CA-ratified sequence is maintained in the [Intraday V1 Programme
Roadmap](KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md): Track A begins WO-03A →
WO-03 → conditional WO-04 → WO-05 → WO-06; Track B is WO-07 → conditional
WO-08 → WO-09; Track C is MCX prerequisites → WO-10; WO-11 through WO-24
then proceed in order. RELIANCE remains the commissioning/regression anchor.

## 16. Open policy and architecture items

The following remain unresolved or unimplemented and must not be inferred from factual foundations:

- exact NSE new-entry semantics at `15:00:00`;
- the Intraday analytical state family and classification predicates;
- Trade Construction contracts and geometry;
- Intraday DOMAIN-007 Risk policy;
- entry-timing semantics;
- Intraday watch, notification, trade, position, and journal contracts;
- PAPER / LIVE admission and acceptance policy;
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

No standalone Swing-to-Intraday handover source exists in repository-accessible
material. Its wording is therefore not reconstructed. The incorporated rules
remain: share capability, not product state; reuse KRONOS architecture and
infrastructure patterns; do not inherit Swing numerical/trading policy; and
keep trades, watches, notifications, journals, and policy versions separate.

## 20. References

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
