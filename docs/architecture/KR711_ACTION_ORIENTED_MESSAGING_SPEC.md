# KR-711 Action-Oriented Trader Messaging

**Status:** Approved Architecture Contract; Not Implemented
**Date:** 2026-07-14
**Task Type:** Architecture Audit + Documentation

## Purpose

KR-711 translates KR-710 deterministic blocker output into concise Trader Mode wording.

KR-711 is not a trading engine. It must not inspect raw market data, calculate conditions, invent unsupported context, or alter any state.

## Input Contract

KR-711 consumes KR-710 outputs only:

- `outExplainabilityReady`
- `outActiveBlockerOwner`
- `outActiveBlockerSeverity`
- `outActiveBlockerCategory`
- `outActiveBlockerMetric`
- `outActiveBlockerCurrentText`
- `outActiveBlockerRequiredText`
- `outActiveBlockerComparator`
- `outActiveBlockerPass`
- `outActiveBlockerClearCondition`
- `outActiveBlockerSummary`
- Optional typed fields such as source engine ID, source engine name, and priority rank

## Public Output Proposal

| Output | Type | Purpose |
|---|---|---|
| `outTraderMessageReady` | bool | KR-711 can publish an action message |
| `outTraderActiveNeedText` | string | Concise Trader Mode Need text |
| `outTraderActiveNeedCategory` | string | Stable category for validation |
| `outTraderActiveNeedSeverity` | string | Severity inherited from KR-710; informational only |
| `outTraderActiveNeedFallback` | bool | True when KR-711 used generic fallback wording |
| `outTraderActiveNeedSourceEngineId` | string | Owner engine ID inherited from KR-710 |
| `outTraderActiveNeedSourceEngineName` | string | Owner engine name inherited from KR-710 |

## Allowed Wording Categories

| Category | Example wording | Source requirement |
|---|---|---|
| `DATA` | `Market Data`, `COMEX 4H Data` | Data blocker from KR-710 |
| `TREND` | `Daily Trend Confirmation`, `4H Trend Confirmation`, `Higher TF Confirmation` | Trend/stage blocker with known timeframe |
| `ACCEPTANCE` | `Price Acceptance`, `Acceptance Above Resistance`, `Acceptance Below Support`, `COMEX 4H Price Acceptance` | Acceptance blocker; level-specific wording only if source exposes it |
| `COMPRESSION` | `Breakout from Compression`, `Wait for COMEX 4H Breakout` | Compression blocker |
| `MOMENTUM` | `Momentum Building`, `MCX 1H Momentum` | Momentum blocker |
| `PRICE_ACTION` | `Wait for Pullback` | Extension or price-action blocker |
| `CONFIDENCE` | `Confidence Building` | Confidence blocker |
| `EXECUTION` | `MCX 1H Confirmation`, `Switch to MCX 1H Chart` | KR-380/KR-380A blocker |
| `STRUCTURE` | `4H Alignment`, `COMEX Daily Trend Alignment` | Structure or directional-alignment blocker |
| `RELATIVE_INTELLIGENCE` | `Relative Strength Building` | Relative evidence blocker if later approved |
| `OPPORTUNITY` | `Opportunity Building` | Opportunity blocker |
| `RISK` | `Review Gate Clears` | Risk/review gate blocker |
| `OTHER` | `Setup Readiness` | Deterministic owner exists but context is too generic |

## Fallback Wording

KR-711 must prefer safe generic wording over invented precision.

Fallback examples:

| KR-710 category | Fallback |
|---|---|
| Unknown trend timeframe | `Higher TF Confirmation` |
| Unknown acceptance level | `Price Acceptance` |
| Unknown execution condition | `Setup Readiness` |
| Unknown opportunity detail | `Opportunity Building` |
| Unknown confidence detail | `Confidence Building` |

## Maximum Text Length

Target maximum: 28 characters.

Allowed exception: market/timeframe-specific wording such as `Wait for COMEX 4H Breakout` may exceed the target when the context is valuable and source-supported.

Trader Mode wording should complete this sentence:

```text
KRONOS will reconsider the trade when...
```

## Precedence When Multiple Blockers Exist

KR-711 must not choose priority independently. It must consume the KR-710 active blocker and render only that blocker in Trader Mode v0.1.

If future Trader Mode shows multiple needs, the order must be inherited from KR-710 priority rank.

## Relationship To KR-705

KR-705 remains presentation-only.

Trader Mode:

- Displays `outTraderActiveNeedText`.
- Shows no raw metrics.
- Adds no rows unless separately approved.

Developer Mode:

- Displays KR-710 deterministic fields.
- May additionally show KR-711 output for comparison.
- Preserves diagnostic wording and metrics.

## Prohibited Behavior

KR-711 must not:

- Read OHLCV, indicators, pivots, or raw market series.
- Calculate pass/fail conditions.
- Change decision, confidence, execution, or alert state.
- Invent support/resistance levels or timeframes.
- Fabricate numeric scores or thresholds.

## Recommendation

APPROVE
