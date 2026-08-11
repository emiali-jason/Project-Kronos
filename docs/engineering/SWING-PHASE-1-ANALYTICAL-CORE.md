# Swing Phase 1 Analytical Core

## Status

**ANALYTICAL CORE VALIDATED THROUGH STAGE 9**

Validation baseline: **2026-08-11**

## Purpose

The Swing Phase 1 analytical core turns the approved canonical universe into a
bounded set of trader-attention opportunities:

```text
98 canonical instruments
→ completed Daily datasets
→ Swing Zero assessments
→ QUALIFIED candidates
→ setup-native Trade Plans
→ deterministic ACTIONABLE ranking
→ Top 0–2 attention selection
```

The core is analytical only. It does not provide Sponsor decisions, trade
execution, position sizing, or active-trade management.

## Canonical Universe

The approved Phase 1 universe contains exactly 98 stable Swing analytical
identities:

- 91 NSE cash equities enumerated by
  `data/nse/KRONOS_NSE_RELATIONSHIPS.csv`;
- NIFTY and BANK NIFTY; and
- GOLDM, SILVERM, COPPER, CRUDEOIL, and NATURALGAS.

Swing owns canonical analytical-universe membership and the stable analytical
identity of each member. Provider Foundation owns Provider mapping, Provider
symbols, Instrument Master retrieval, current futures-contract resolution, and
market-data retrieval. Expiring futures contracts are operational Provider
identities; they do not become permanent Swing analytical identities.

The universe mechanism is deterministic and source-validated so that a future
approved expansion can change membership without rewriting the analytical
engine. This document does not authorize any expansion beyond the approved 98.

## Daily Data Pipeline

The Stage 3 pipeline requests Provider Foundation V2 historical data for every
canonical member and retains the latest 30 completed Daily candles. The
current, incomplete trading-day candle is excluded. At least 25 completed
Daily candles are required by Swing Zero; insufficient or malformed history is
reported as an explicit per-instrument unavailable result rather than silently
omitted.

Provider Foundation V2 resolves the Provider-private instrument and retrieves
normalized candles. Provider tokens and Kite objects do not cross into the
Swing analytical contract. The frozen real-data readiness proof produced 98
READY datasets from 98 requested members.

## Assessment

Stage 4 reuses `SWING-ZERO-V0-CLASSIFICATION-POLICY` unchanged. Each READY
instrument is evaluated independently for Pullback Continuation and
Consolidation Breakout, producing exactly two immutable `SwingAssessment`
objects. The common completed observation boundary is deterministic, and an
isolated instrument failure remains explicit without stopping the market run.

Detailed V0 calculations, setup predicates, minimum-history requirements, and
fail-closed rules remain authoritative in `docs/engineering/SWING-ZERO.md`.

The frozen full-universe run produced 196 assessments for 98 instruments with
zero assessment failures.

## Candidate Validation

Stage 5 extracts only assessments whose state is `QUALIFIED`. It preserves the
original assessment, canonical instrument identity, setup identity, direction,
policy version, and observation boundary. Pullback Continuation and
Consolidation Breakout remain independent; one instrument may therefore have
multiple qualified setup candidates.

The frozen run produced 12 qualified setup assessments across 11 unique
instruments. All 12 independent predicate audits passed, with zero `FORMING`
or `NO_SETUP` leakage. HDFCBANK retained two distinct qualified SHORT setup
identities.

## Candidate Comparison Foundation

Qualified assessments are comparable as analytical candidates, but setup
classification evidence alone does not establish authoritative opportunity
ranking. Comparison becomes authoritative only after each candidate has a
setup-native Trade Plan. Multiple same-direction setups for one instrument
preserve their independent evidence and do not automatically receive duplicate
ranking weight.

All approved candidates share one attention pool. No direction, asset-class,
or setup-family quota is applied.

## Trade Plan

Policy: `SWING-PHASE1-V0-TRADE-PLAN-POLICY`

For each qualified candidate, Stage 7 deterministically derives:

- Entry and its subsequent-session condition;
- Stop;
- Thesis Invalidation;
- Target 1;
- risk per unit;
- reward per unit; and
- Risk:Reward.

The calculations are setup-native. Pullback plans use the qualification candle,
the preceding pullback structure, and a prior structural target window.
Breakout plans use the qualification candle and the original consolidation
range. No Entry Zone, Target 2, position sizing, or ranking field is invented.

A `QUALIFIED` setup does not necessarily produce an `ACTIONABLE` Trade Plan.
Invalid stop geometry fails closed as `INVALID`; absent positive structural
reward is `NOT_ACTIONABLE`. The Stage 7 policy has no minimum Risk:Reward gate.
The frozen run produced 12 Trade Plans: 6 `ACTIONABLE` and 6
`NOT_ACTIONABLE`.

## Ranking

Policy: `SWING-PHASE1-V0-CANDIDATE-RANKING-POLICY`

Stage 8 ranks only `ACTIONABLE` Trade Plans by descending Risk:Reward.
Canonical identity, setup identity, direction, and candidate identity are used
only as deterministic tie-breakers. There is no weighted or composite score,
confidence ranking, setup-family preference, direction preference, or
asset-class preference. `NOT_ACTIONABLE` and `INVALID` plans remain preserved
and reconciled outside the ranked list. The Stage 7 minimum Risk:Reward gate
remains `NONE`.

## Top 0–2

Policy: `SWING-PHASE1-V0-TOP-OPPORTUNITY-POLICY`

A ranked plan is attention-eligible only when it is `ACTIONABLE` and has
Risk:Reward greater than or equal to 1.00. Stage 9 selects at most two canonical
instruments and validly supports zero, one, or two results. It never fills an
empty slot with an ineligible plan.

When one instrument has multiple attention-eligible plans, it occupies one
attention entry. Its highest Stage 8-ranked eligible plan is representative,
and its additional eligible plans remain preserved as children.

## Real Validation Baseline

The frozen Stage 2–9 real-data evidence is:

- universe resolution: 98/98;
- completed-Daily readiness: 98/98;
- Stage 4: 196/196 assessments and 0 failures;
- Stage 5: 12 qualified setup assessments, 11 unique instruments, and 12/12
  predicate audits passed;
- Stage 7: 12 Trade Plans, comprising 6 `ACTIONABLE` and 6
  `NOT_ACTIONABLE`; and
- Stage 9: one attention-eligible canonical instrument.

The Stage 8 real ranking was:

| Rank | Instrument | Setup | Direction | Risk:Reward |
| ---: | --- | --- | --- | ---: |
| 1 | HDFCBANK | Consolidation Breakout | SHORT | 2.8333 |
| 2 | AXISBANK | Pullback Continuation | SHORT | 0.8059 |
| 3 | ADANIENT | Pullback Continuation | SHORT | 0.3655 |
| 4 | TCS | Pullback Continuation | LONG | 0.2834 |
| 5 | SRF | Pullback Continuation | SHORT | 0.2698 |
| 6 | LUPIN | Pullback Continuation | SHORT | 0.0638 |

The Stage 9 result was:

```text
#1 HDFCBANK
Consolidation Breakout / SHORT
Entry: 728.2
Stop: 736
Target 1: 706.1
Risk:Reward: 2.83333333333

#2 NONE
```

This validation proves deterministic implementation behavior against the
frozen real-data boundary. It does not prove profitability or parameter
optimality.

## Product Boundary

The following are not implemented by the Stage 1–9 analytical core:

- Browser V1;
- TradingView/Pine evidence integration;
- KRONOS Pre-Decision;
- Sponsor `LIVE`, `PAPER`, or `IGNORE` decisions;
- Paper Trader;
- Entry Thesis monitoring;
- WebSocket active-trade monitoring;
- Exit, Journal, or learning workflows;
- execution; and
- position sizing.

## Safe Maintenance

The four frozen policy identities are:

- `SWING-ZERO-V0-CLASSIFICATION-POLICY`;
- `SWING-PHASE1-V0-TRADE-PLAN-POLICY`;
- `SWING-PHASE1-V0-CANDIDATE-RANKING-POLICY`; and
- `SWING-PHASE1-V0-TOP-OPPORTUNITY-POLICY`.

Do not tune their rules or parameters in response to one market observation.
Any future policy change requires explicit approval, a new policy version,
deterministic offline tests, and bounded real-data validation. Provider
integration must continue to preserve stable Swing identities, private
Provider instrument identity, completed-candle boundaries, and sanitized
fail-closed outcomes.

## Next Roadmap

- Stage 10: TradingView/Pine Evidence Integration;
- Stage 11: KRONOS Pre-Decision;
- Stage 12: Imran Decision and Paper Trader;
- Stage 13: Active Trade and Entry Thesis Monitoring; and
- Stage 14: Exit, Journal, and Learning.

Browser V1 begins immediately after this analytical-core checkpoint.
