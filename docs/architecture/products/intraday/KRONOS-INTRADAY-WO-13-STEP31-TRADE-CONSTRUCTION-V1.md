# KRONOS Intraday WO-13 — Step 31 Trade Construction V1

**Status:** APPROVED ARCHITECTURE — GOVERNANCE PUBLISHED; BOUNDED CORE ENGINEERING AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1`

**Version:** `1.0.0`

**Policy:** `KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1 / 1.0.0`

**Owner:** `KRONOS-INTRADAY / STEP-31`

**Authority:** `TRADE_CONSTRUCTION_ONLY`

**Governing ADR:** [ADR-0022](../../adr/ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)

## Purpose

Construct immutable 15M Intraday Trade Plan geometry from one exact current
integrity-valid WO-12 V2 NOW result and retained governed evidence. This stage
does not perform analytical promotion, Risk, final Entry timing, Sponsor
decision, execution or broker activity.

## Admission and handoff

Admission is exactly `BUY_NOW` or `SELL_NOW`. Direction, canonical subject,
market family, setup family, boundary, phase, instrument/contract identity and
the complete WO-12/WO-11/WO-10/Probables lineage are inherited and exact-bound
through `KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1`.

`BUY_READY`, `SELL_READY`, both potential states and `NO_SETUP` are rejected.
Any stale, foreign, corrupt, mismatched or ambiguous binding fails closed. No
latest, mtime, symbol-only, current-market or V1 fallback is permitted.

## Timeframe and setup ownership

15M owns geometry. 1H is context only. 5M belongs to WO-15 and cannot rewrite
WO-13.

The only setup families are:

- `INTRADAY_PULLBACK_CONTINUATION`;
- `INTRADAY_RANGE_BREAKOUT`.

The upstream setup identity is immutable; WO-13 never reclassifies it.

## Geometry fields

The Trade Plan preserves independently:

- Entry Reference and geometric Entry Condition;
- Stop and Stop structural basis;
- Thesis Invalidation Reference and Event;
- setup-native Target and its basis;
- constraining objective, when any;
- canonical Target and its basis;
- risk and reward distance;
- Model R:R;
- each field availability and aggregate geometry availability;
- mathematical warnings;
- policy identity/version/checksum;
- complete source identities/integrities;
- calculation provenance, integrity and supersession lineage.

Entry Condition is not an Entry trigger, Entry Outcome or execution command.

## Pullback continuation

| Direction | Entry Reference | Stop | Thesis invalidation | Setup-native Target |
| --- | --- | --- | --- | --- |
| LONG | High of exact completed governed 15M qualification/resumption candle | Exact governing completed 15M pullback structural Low | Completed governed 15M structural failure through that Low | Prior directional 15M impulse/swing High interrupted by pullback |
| SHORT | Low of exact completed governed 15M qualification/resumption candle | Exact governing completed 15M pullback structural High | Completed governed 15M structural failure through that High | Prior directional 15M impulse/swing Low interrupted by pullback |

There is no Entry/Stop buffer, arbitrary lookback, LTP replacement or pullback
measured-move Target.

## Range breakout

The original governed range remains immutable.

| Direction | Entry Reference | Stop | Thesis invalidation | Setup-native Target |
| --- | --- | --- | --- | --- |
| LONG | Original 15M Range High | Low of exact completed breakout qualification candle | Completed governed 15M close back at/inside original range | `Range High + (Range High - Range Low)` |
| SHORT | Original 15M Range Low | High of exact completed breakout qualification candle | Completed governed 15M close back at/inside original range | `Range Low - (Range High - Range Low)` |

Acceptance belongs upstream. Retest is not required and later evidence cannot
move Entry or Stop.

## Target constraint

The setup-native Target is derived first. The nearest legitimate forward
authoritative objective strictly between Entry and setup-native Target may
constrain it. Directional price order is authoritative; labels have no fixed
hierarchy. A farther level never extends Target.

Eligible already-governed constraints are a relevant 15M swing extreme,
current-session structural high/low, PDH/PDL, Classic Pivot R1-R4/S1-S4,
governed 15M structural barrier and Range-Breakout measured objective.

SMA20/50/200, CPR, COMEX/NYMEX, USDINR, LTP and desired-R:R prices are not
standalone Targets. Target count is exactly one.

## Market families

- Equity: stock-local geometry; NIFTY has no stock geometry authority.
- Index: underlying-local geometry; option premium/strike has no authority.
- MCX: exact active-contract-local, roll-safe geometry; international references
  and USDINR have no geometry authority; cross-roll synthetic bridging is
  prohibited; NATGAS remains operationally held.

## Mathematics

| Direction | Risk distance | Reward distance |
| --- | --- | --- |
| LONG | `Entry - Stop` | `Target - Entry` |
| SHORT | `Stop - Entry` | `Entry - Target` |

Model R:R is `reward_distance / risk_distance` only when both distances are
positive and all inputs are finite. It is calculated from model geometry, not
LTP. No minimum R:R gate is authorized and `RR_UNFAVOURABLE` is unresolved.

## Availability and warnings

Field outcomes include `ENTRY_UNAVAILABLE`, `STOP_UNAVAILABLE`,
`TARGET_UNAVAILABLE` and `THESIS_INVALIDATION_UNAVAILABLE`. Aggregate states
are `GEOMETRY_COMPLETE`, `GEOMETRY_PARTIAL` and `GEOMETRY_UNAVAILABLE`.

Warnings are `NON_POSITIVE_RISK`, `NON_POSITIVE_REWARD`,
`INVALID_DIRECTIONAL_GEOMETRY`, `NON_FINITE_VALUE` and conditionally
`TICK_NORMALIZATION_FAILURE`. Poor geometry is retained; warnings do not
manufacture replacement geometry or a Risk/Sponsor decision.

## Trust failures

Foreign/stale source, policy/evidence-cycle mismatch, direction/setup/family/
instrument mismatch, integrity failure, wrong MCX active contract or roll
lineage produces no trusted construction record.

## Persistence

Dedicated `wo13-step31-v1` persistence separates handoffs, requests, geometry
evidence, Trade Plans, operations and current pointers. All retained artifacts
are content-addressed, independently integrity-bound, append-only, idempotent
for identical content and conflict-rejecting. Explicit identity reload is
mandatory. Current pointer is written atomically only after every required
artifact persists and reloads successfully.

## Contracts

- `KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1`;
- `KRONOS-INTRADAY-WO13-TRADE-CONSTRUCTION-REQUEST-V1`;
- `KRONOS-INTRADAY-WO13-GEOMETRY-EVIDENCE-V1`;
- `KRONOS-INTRADAY-WO13-TRADE-PLAN-V1`;
- `KRONOS-INTRADAY-WO13-OPERATION-PROVENANCE-V1`;
- `KRONOS-INTRADAY-CURRENT-WO13-POINTER-V1`.

The canonical policy payload is
[KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1.json](KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1.json).
Its SHA-256 and engineering contract checksum is
`c5ea70a5af50af251088785a58a39da4e824b5cc6058c11c98e880fce0fb0e6b`.

## Application boundary

A future `IntradayWo13Application` validates exact eligibility and retained
evidence, dispatches the setup-specific constructor, derives constraints and
arithmetic, persists immutable artifacts, publishes the pointer last, and
explicitly reloads/verifies. It makes no Provider or Chart Analyst call.

Runtime, Browser and real WO-13 operation are not authorized by this document.

## Downstream boundary

WO-14 alone owns advisory DOMAIN-007 Risk observation under ADR-0023. It cannot
approve, reject or block the trade and cannot rewrite geometry. WO-15 alone
owns final 5M Entry timing. Sponsor participation and broker execution remain
separate and unauthorized here.

## Historical and Swing isolation

Swing Step-31 contracts, policy, code, persistence and records are unchanged.
Intraday reuses common KR-370 semantics and engineering patterns through
product-owned contracts/adapters; it does not copy Swing Daily methodology or
reinterpret Swing artifacts.
