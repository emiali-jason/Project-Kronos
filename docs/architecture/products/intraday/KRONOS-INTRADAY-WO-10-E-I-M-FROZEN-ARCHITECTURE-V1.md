# KRONOS Intraday V1 — WO-10 E/I/M Frozen Architecture V1

**Status:** APPROVED — FROZEN ARCHITECTURE

**Owner:** KRONOS Intraday

**Document identity:** `KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1`

**Version:** 1.0.0

**Decision date:** 2026-08-30

**Governing ADR:** [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)

**Implementation status:** NOT STARTED

**Trading / Risk / Entry / Broker authority:** NONE

## 1. Purpose

WO-10 is Intraday analytical reconciliation. It asks whether an exact Native
Probable has developed sufficient coherent governed evidence to progress to
the next governed analytical stage.

WO-10 does not mean Enter Now, Trade Approved, Risk Approved, acceptable R:R,
PAPER, LIVE or broker execution. Direction is inherited from the exact Native
Probable and cannot change inside WO-10 or WO-11.

The family contains three independent policies:

- WO-10E — NSE Equity;
- WO-10I — NSE Index;
- WO-10M — MCX.

They share a consequence contract but retain separate policy identities,
publications, checksums and family-specific evidence.

## 2. Product-local consequence family

The common product-local state family is:

1. `CONTEXT_INCOMPLETE`
2. `INVALIDATED`
3. `WEAKENING`
4. `HELD_BY_CONTRADICTION`
5. `WAIT_SETUP_DEVELOPMENT`
6. `WAIT_IMMEDIATE_CONFIRMATION`
7. `PROMOTION_READY`

Precedence is exact:

| Order | Condition | State |
| ---: | --- | --- |
| 1 | Required governed evidence unavailable or invalid | `CONTEXT_INCOMPLETE` |
| 2 | Governing structural thesis failed | `INVALIDATED` |
| 3 | Thesis intact but materially deteriorating | `WEAKENING` |
| 4 | Authoritative evidence materially conflicts | `HELD_BY_CONTRADICTION` |
| 5 | 15M setup structurally incomplete | `WAIT_SETUP_DEVELOPMENT` |
| 6 | Analytical setup sufficiently formed but immediate progression absent | `WAIT_IMMEDIATE_CONFIRMATION` |
| 7 | Required governed evidence materially coherent | `PROMOTION_READY` |

There is no score, vote, weight, rank, quota or “N out of M” rule.

## 3. KR-370 semantic boundary

This seven-state family is not the KR-370 or KR-380 state family. In
particular:

- `PROMOTION_READY` is not `BUY_NOW`, `SELL_NOW`, `BUY_READY` or `SELL_READY`;
- `WAIT_IMMEDIATE_CONFIRMATION` is not `BUY_READY` or `SELL_READY`;
- neither state establishes Step-31 eligibility or an Entry Outcome.

`PROMOTION_READY` means only that WO-10 reconciliation is sufficiently
complete for a later governed analytical stage. It grants no Entry, Stop,
Target, R:R, Trade Construction, Risk, PAPER/LIVE or broker authority.

`WAIT_IMMEDIATE_CONFIRMATION` means the setup remains analytically viable and
sufficiently developed, but immediate progression is absent for completion of
WO-10. WO-15 remains the precision Entry/Exit timing authority.

The exact boundary and the unchanged relationship to ADR-0011 are governed by
ADR-0019.

## 4. WO-11 relationship

WO-10E, WO-10I and WO-10M decide independently. WO-11 validates, collates and
publishes their exact results with zero analytical discretion. WO-11 retains:

- market family;
- canonical subject;
- inherited direction;
- WO-10 policy identity/version/publication/checksum;
- WO-10 result identity and state;
- bounded reason codes;
- analysis boundary and persisted phase;
- exact evidence lineage and integrity.

WO-11 cannot reinterpret, reverse or remap a result into KR-370 semantics.
Only `PROMOTION_READY` can be eligible for a later separately governed
handoff; eligibility itself grants no later-layer authority.

## 5. Common timeframe responsibility

Machine structural hierarchy is:

| Timeframe | Responsibility |
| --- | --- |
| 1D | Broader context |
| 1H | Intraday regime; primary Railway Track timeframe |
| 15M | Primary directional/setup structure |
| 5M | Immediate analytical progression; later precision timing belongs to WO-15 |

Timeframes do not vote equally. Structural consequence uses completed governed
candles. A developing/current price relationship may be retained factually
where an existing contract permits it, but cannot rewrite completed structure.

## 6. Shared RSI policy

Machine RSI thresholds are frozen:

| Timeframe | Overbought | Oversold |
| --- | ---: | ---: |
| 1H | `>= 70` | `<= 30` |
| 15M | `>= 70` | `<= 30` |
| 5M | `>= 80` | `<= 20` |

RSI is condition/momentum evidence. Overbought does not automatically mean
SHORT and oversold does not automatically mean LONG. Machine-calculated RSI
is canonical numerical authority where governed candles exist.

## 7. Railway Track grammar

Railway Track factual evidence uses SMA20, SMA50 and SMA200 and preserves:

- value;
- slope;
- price relationship;
- stack/order;
- crisscross;
- separation/convergence;
- interaction.

Stack alone is insufficient. The ideal bullish and bearish arrangements are
structural descriptions, not automatic signals. The primary timeframe is 1H;
15M expresses setup alignment/deterioration, 5M immediate interaction, and 1D
broad location/SMA200 context.

No new distance or separation threshold is authorized. If material separation
or crisscross cannot be reproduced from an existing exact grammar, the policy
is unresolved; Engineering must not invent a threshold.

## 8. Structural-location model

The factual reference set may include:

- CPR pivot, upper, lower and width;
- PDH and PDL;
- Classic Pivots P, R1–R4 and S1–S4;
- SMA20/SMA50/SMA200;
- relevant completed 1H structure;
- relevant completed 15M range/swing structure.

Classic Pivot formulas remain:

```text
P  = (H + L + C) / 3
R1 = 2P - L            S1 = 2P - H
R2 = P + (H - L)       S2 = P - (H - L)
R3 = P + 2(H - L)      S3 = P - 2(H - L)
R4 = P + 3(H - L)      S4 = P - 3(H - L)
```

Reference proximity is not a signal. Above/below CPR, PDH/PDL breaks, or
touches of R/S levels do not automatically create direction. Existing exact
price relationships and interaction vocabulary must be reused where available;
duplicate synonyms are prohibited.

## 9. Volume telemetry architecture

The factual design may retain:

- current volume;
- rolling median and rolling mean;
- ratio to median and mean;
- volume percentile;
- same-time session median, ratio and percentile for 15M/5M where history
  permits;
- research-only impulse, pullback, resumption and breakout relative volume.

Median is the preferred baseline. Every volume observation must bind to its
price event. Expansion on breakout, rejection and an opposing move are
different facts. Volume cannot rescue failed price structure.

No ratio, percentile or Promotion threshold is authorized. The exact
supportive/neutral/contradictory consequence remains unresolved until separately
qualified.

## 10. WO-10E — NSE Equity

WO-10E covers 91 NSE equities and reconciles:

- stock 1D context;
- 1H regime and Railway Track;
- 15M primary structure;
- 5M immediate progression;
- RSI;
- structural location/interactions;
- factual participation;
- validated visual evidence;
- NIFTY relationship.

NIFTY opposition is not an automatic veto. A stock retaining its proposed
direction against NIFTY may express meaningful relative strength/weakness.
NIFTY cannot rescue failed stock 1H/15M structure.

The primary comparison is 15M stock ↔ 15M NIFTY; 1H is broader context. 5M
benchmark timing belongs mainly to WO-15E. Exact relative materiality remains
unresolved, so V1 may retain the relationship factually but cannot invent a
materiality threshold or consequence.

## 11. WO-10I — NSE Index

WO-10I covers NIFTY and BANKNIFTY. Its hierarchy is:

```text
WEEKLY → DAILY → 1H → 15M → 5M
```

Weekly CPR, Previous Week High/Low and weekly pivots are higher-order map facts
where governed. Daily CPR, PDH/PDL, Classic Pivots, SMA structure and relevant
1H/15M structure provide current-session context.

Weekly CPR and daily location do not create or reverse direction. Exact
location, target, stop and R:R consequences belong to WO-14I.

For Index option trading, the underlying NIFTY/BANKNIFTY remains analytical
authority for direction, structure, invalidation, target structure and price
confirmation. An option is a later execution vehicle and option premium does
not create WO-10I direction.

Confluence distance, middle-of-range, flat/tangled SMA, new narrow/wide CPR
prediction, break/retest Entry, target hierarchy and option selection remain
unresolved or downstream.

## 12. WO-10M — MCX

WO-10M covers GOLDM, SILVERM, COPPER, NATGAS and CRUDE with one common V1
methodology. Metals and Energy do not receive separate methodologies without
future empirical evidence and a successor version.

MCX is the Native analytical subject. NIFTY is `NOT_APPLICABLE`. Persistent
reference relationships are:

- GOLDM ↔ COMEX Gold;
- SILVERM ↔ COMEX Silver;
- COPPER ↔ COMEX Copper;
- CRUDE ↔ NYMEX Crude Oil;
- NATGAS ↔ NYMEX Natural Gas.

These are governed relationship identities, not Provider ticker assumptions.
The exact visible reference identity is retained with visual evidence.

International reference evidence may contextualize, corroborate or expose
divergence. It cannot manufacture or reverse an MCX thesis, rescue failed MCX
structure, independently invalidate MCX, or grant downstream authority.
Chart Analyst reports independent observations; KRONOS alone derives any
cross-market synthesis.

Native machine timeframes are 1D/1H/15M/5M. Paired visual timeframes are
1D/4H/15M/5M. Visual 4H is not native machine 1H. Machine MCX RSI is canonical;
international RSI remains visual/context only.

Same-time session telemetry is especially relevant to the long MCX session,
but its materiality is unresolved. Session phase, international overlap,
contract roll, expiry/special session, shortened session and missing Provider
volume are factual context only.

CPR, PDH/PDL, previous close, pivots and prior-session 1H are actual-contract
local. A contract roll is not a market gap. Contract-local levels and exact
session gaps do not cross a roll without separate authority. A non-back-
adjusted continuous view may provide already-governed higher-order context but
cannot erase contract lineage.

WO-10M methodology may support NATGAS, but operational evaluation remains
unavailable while upstream NATGAS commissioning is `HELD`.

The existing single-subject Q1–Q10 contract is insufficient for paired
MCX/reference evidence. A separately governed successor is required; this
document does not create it.

## 13. Chart Analyst boundary

Chart Analyst observes. KRONOS reconciles and decides. Chart Analyst must not
emit any WO-10 state, Entry, Stop, Target, R:R, Trade Approved, Risk, PAPER or
LIVE consequence. Raw visible identity remains independent evidence and is
resolved separately through DOMAIN-001.

## 14. Unresolved empirical policy

The following remain unresolved unless separately governed:

- Railway Track material separation;
- material crisscross where no existing exact grammar applies;
- Equity relative-strength/weakness materiality;
- volume consequence and ratio/percentile thresholds;
- confluence distance and middle-of-range;
- flat/tangled SMA;
- new CPR predictive consequence;
- Index weekly/daily location consequence;
- MCX reference-divergence materiality and duration;
- MCX same-time-volume materiality;
- extension/chase numerical threshold.

These items do not block the Slice 1 contract foundation because Slice 1 does
not implement a classifier. In later policy/classifier slices:

- an explicitly informational V1 field may remain absent or informational;
- missing evidence follows the governed evidence-availability rule;
- a required consequence that depends on unresolved policy fails closed as
  `POLICY_UNRESOLVED` and produces no fabricated result;
- no default, epsilon, score, weight, vote or fallback is permitted.

For V1, Equity relative materiality, raw volume consequence, weekly/daily
location consequence, MCX divergence materiality, MCX same-time-volume
materiality and extension/chase may remain informational. Railway Track may be
used only to the extent exact factual grammar is reproducible without a new
threshold.

The family-specific treatment is:

| Applicability | Unresolved item | V1 treatment | Blocking effect |
| --- | --- | --- | --- |
| Common | Railway Track material separation/crisscross | Retain exact reproducible factual grammar only | Does not block Slice 1; blocks only a later predicate that declares the unresolved materiality required |
| Common | Volume supportive/neutral/contradictory consequence and ratio/percentile thresholds | Retain event-bound raw telemetry as informational | Does not block Slice 1 or a policy that keeps volume informational |
| Common | Extension/chase numerical threshold | Informational or absent; geometry/timing consequence remains downstream | Does not block Slice 1 |
| WO-10E | Equity relative-strength/weakness materiality | Retain the exact stock/NIFTY relationship as informational | Does not block Slice 1 or WO-10E V1 while informational |
| WO-10I | Confluence distance, middle-of-range, flat/tangled SMA and new CPR prediction | Retain exact location/SMA/CPR facts without the unresolved consequence | Does not block Slice 1; any required classifier consequence needs successor authority |
| WO-10I | Weekly/daily location consequence | Retain the higher-order map as informational | Does not block Slice 1 or WO-10I V1 while informational |
| WO-10M | Reference-divergence materiality and duration | Retain paired observations without automatic veto, reversal or invalidation | Does not block Slice 1 or WO-10M V1 while informational |
| WO-10M | Same-time-session volume materiality | Retain session-qualified raw telemetry as informational | Does not block Slice 1 or WO-10M V1 while informational |

Accordingly, no unresolved empirical predicate is a hard blocker to Slice 1
contract foundation. A later family policy must either declare the item
informational/absent or close its consequence before making it required. It
must never silently treat an unresolved item as satisfied or failed.

## 15. WO-14 exclusions

WO-10 does not own:

- Entry, Stop, Target, invalidation or R:R geometry;
- target hierarchy or stop placement;
- path clearance when used to approve/reject trade geometry;
- location-to-target or location-to-stop consequence;
- option selection or execution geometry.

WO-10 may preserve the underlying factual location/obstacle evidence only.

## 16. WO-15 exclusions

WO-15 remains the precision Entry/Exit timing authority. WO-10 does not own:

- executable 5M trigger;
- break/retest Entry trigger;
- 5M NIFTY timing confirmation;
- final acceptance/rejection trigger;
- entry expiry;
- transformation of `WAIT_IMMEDIATE_CONFIRMATION` into an order or Entry
  Outcome.

## 17. Authority declaration

This architecture introduces no classifier implementation, evidence snapshot,
RSI producer, Railway Track producer, successor volume telemetry, MCX paired
Review contract, runtime composition, Browser control, Provider operation,
Trade Construction, Entry, Stop, Target, R:R, Risk, PAPER/LIVE, lifecycle or
broker authority.

Historical WO-10 V1 artifacts and contracts remain immutable and readable.
They are not the frozen E/I/M successor state family.

## 18. Required successor sequence

```text
WO-10E / WO-10I / WO-10M
        ↓ independent exact results
WO-11 zero-discretion validation, collation and publication
        ↓ only PROMOTION_READY eligible for later governed handoff
Later separately governed analytical / construction / timing stages
        ↓
KR-370 only through a future explicit versioned boundary
```

No arrow grants unstated authority.

## 19. Related documents

- [ADR-0019](../../adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
- [ADR-0011](../../adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [Historical WO-10 V1](KRONOS-INTRADAY-WO-10-NATIVE-VISUAL-RECONCILIATION-V1.md)
- [V2 Review Successor Seam](KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM-V1.md)
- [Contract and State Ownership Registry](KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Deferred Decision Register](KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md)
