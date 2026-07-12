# Project KRONOS Engine Status

**Document role:** Canonical current engine registry
**Source audited:** `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`
**Audit date:** 2026-07-10

This registry reports source metadata exactly as it appears in the Pine file. Contract maturity is a documentation classification and does not replace the source header. Validation claims are deliberately limited to evidence present in source comments, repository history, or the current verified implementation baseline.

Related documents:

- [Architecture Overview](architecture/OVERVIEW.md)
- [Engine Ownership](architecture/ENGINE_OWNERSHIP.md)
- [Data Flow](architecture/DATA_FLOW.md)
- [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md)

## Status Semantics

| Field | Meaning |
|---|---|
| Source version | Version stated in the engine's source header. `Not declared` means no engine-level version is present. |
| Source status | Status stated in the engine's source header, preserving its exact spelling and capitalization. |
| Contract maturity | Current documentation classification: Foundation, Frozen, Skeleton, Adapter, or Developer/Trader Tool. |
| Validation scope | What is actually evidenced. It is not a claim that every state has occurred live. |

## Configuration, Data, and Market Foundation

| Engine | Name | Single responsibility | Source version | Source status | Contract maturity | Inputs / dependencies | Public outputs summary | Downstream consumers | Validation scope and notes |
|---|---|---|---|---|---|---|---|---|---|
| KR-100 | Configuration Engine | Defines product constants, common periods, and user display inputs. | Not declared; product constant is `0.5.0` | Not declared | Foundation | TradingView inputs | Product/build constants, SMA periods, visibility inputs; no formal `out...` contract | KR-150; KR-260 configuration placeholders | Static source review only. Engine-level version and status are absent. |
| KR-150 | Indicator Engine | Calculates and plots the chart-symbol SMA 20/50/200 display set. | Not declared | Not declared | Foundation | KR-100 periods and visibility inputs; chart close | `maFast`, `maMid`, `maSlow` and three plots; no formal `out...` contract | Chart rendering only | Static source review only. Engine-level version and status are absent. |
| KR-200 | Market Identification Engine | Identifies exchange, symbol, root, description, and market family. | Not declared | Not declared | Foundation | `syminfo` identity fields | Exchange/ticker/root/description values, market flags, `krMarket`; no formal `out...` contract | KR-250 | Static review confirms MCX, NSE, COMEX, NYMEX, and OANDA recognition paths. |
| KR-250 | Asset Intelligence Engine | Maps the current instrument to asset identity, dependency profile, and reference symbol. | Not declared | Not declared | Foundation | KR-200 identity | Asset name/type/market/exchange, primary and reference symbols, dependency and trading profiles | KR-260; KR-380A; other market-aware consumers | Static review confirms Gold -> `COMEX:GC1!`, Silver -> `COMEX:SI1!`, Copper -> `COMEX:HG1!`, Crude Oil -> `NYMEX:CL1!`, and Natural Gas -> `NYMEX:NG1!` configuration mappings. |
| KR-251 | Market Model Configuration Engine | Classifies the chart into MCX Metals Swing, MCX Energy Swing, NSE Equity Swing, NSE Index Swing, or Unsupported and exposes execution semantics. | `0.1.0` | `FOUNDATION` | Foundation | KR-250 asset identity; exact NSE equity universe symbols; exact NIFTY/BANKNIFTY index symbols | Model name, asset name, analysis symbol, execution instrument text/type, venue, profile, cash symbol, support flag | KR-252; future KR-260A integration | Configuration Layer complete for current Swing models. Market Data integration pending; no data retrieval is performed. |
| KR-252 | Market Relationship Engine | Exposes cash, sector, parent-index, and global-reference relationships for supported instruments. | `0.1.0` | `FOUNDATION` | Foundation | KR-251 support/model outputs; KR-250 asset identity; generated `data/nse/KRONOS_NSE_RELATIONSHIPS.csv` map | Relationship readiness/status/reason, cash/reference/sector/parent symbols, context flags, and generated 91-stock NSE relationship map | Future market-relationship consumers; not wired into KR-260 yet | Configuration-only foundation. MCX Metals and Energy relationships are unchanged. NSE Equity has 90 READY rows and 1 REVIEW row (`KAYNES`); NSE Index supports NIFTY and BANKNIFTY as relationship-ready context instruments. Market Data integration pending. |
| KR-260A | Market Data Routing Engine | Selects the symbols and capabilities KRONOS should use for market data. | `0.1.0` | `FOUNDATION` | Foundation | KR-251 model/execution outputs; KR-252 relationship outputs | Route readiness/status/reason, analysis symbol, execution text, primary/secondary/sector/parent symbols, and capability flags | Future KR-260B retrieval | Routing only. Behavior is unchanged; no `request.security()` calls or OHLCV retrieval. |
| KR-260B | Market Data Retrieval Engine | Retrieves current-chart-timeframe OHLCV from valid KR-260A routes without interpreting or normalizing it. | `1.0.0` | `Implemented` | Implemented | KR-260A route readiness, routed symbols, and context capability flags | Raw Analysis, Primary, Secondary, Sector, and Parent OHLCV plus per-context readiness flags | Future KR-260 normalization | Five guarded `request.security()` call sites use `gaps_off` and `lookahead_off`; unavailable contexts are not requested. Legacy KR-260 retrieval remains unchanged pending migration. |
| KR-260 | Market Data Normalization Engine | Normalizes retrieved market data for the Intelligence Layer. | `0.5.0-alpha` | Not declared | Foundation | Future KR-260B retrieval interface; current legacy KR-100/KR-250 data path remains unchanged | Normalized primary/reference OHLCV datasets, availability flags, status and error text | KR-270; KR-275; KR-280; KR-300; KR-315; KR-380A; KR-390A | Target ownership excludes routing and `request.security()`. Existing executable retrieval/normalization logic is unchanged pending KR-260B integration. |
| KR-270 | Market Indicator Engine | Calculates derived indicators from KR-260 datasets without retrieving market data itself. | `0.5.0-alpha` | Not declared | Foundation | KR-260 OHLCV | Primary/reference SMA, RSI, ATR, directional and momentum series used by later engines | KR-275; KR-300; KR-310; KR-315; KR-330; KR-380A | Static source review only. Source status is absent. |
| KR-271 | Mathematical Library | Provides reusable true-range, ATR, directional-movement, directional-index, and trend-strength calculations. | Not declared | Not declared | Foundation | OHLC and period arguments | Reusable calculation functions and derived series; no formal engine `out...` contract | KR-275; KR-310; KR-330; other mathematical consumers | Static source review only. Engine-level version and status are absent. |
| KR-275 | Market Structure Intelligence Engine | Detects and maintains confirmed market structure, swings, BOS, and CHoCH. | `1.0.0` | `Release` | Foundation | KR-260 trend data; KR-271 calculations | Structure state/direction, swing classifications, BOS and CHoCH flags, last-break memory | Current public contract; future structure consumers | Static review confirms public structure outputs. No stored instrument-level validation artifact exists. |
| KR-280 | CPR Intelligence Engine | Calculates reference-period CPR, pivots, width, relationship, price position, and virgin-CPR context. | `1.0.0` at module start; `1.1.0` in closing metadata | `FROZEN` | Frozen | KR-250/260 primary symbol and previous completed reference OHLC; user-selected CPR reference mode | Reference period, CP/BC/TC, R1-R4, S1-S4, reference H/L/C, width, relationship, price position, virgin CPR | KR-315; KR-320; KR-360 indirectly; KR-370 indirectly; KR-705 | CPR reference behavior is recorded in source as validated against the preserved legacy Auto mode. Two source version labels coexist. **Source metadata requires reconciliation.** |

## Intelligence Core

KES (KRONOS Evidence Synthesis) is the unnumbered architectural boundary that collects, validates, standardizes, and packages evidence before KR-360 Confidence. It does not own evidence generation, confidence calculation, decisions, execution, trade management, alerts, or presentation. Engine numbers and runtime contracts remain unchanged.

| Engine | Name | Single responsibility | Source version | Source status | Contract maturity | Inputs / dependencies | Public outputs summary | Downstream consumers | Validation scope and notes |
|---|---|---|---|---|---|---|---|---|---|
| KR-300 | Trend Foundation Engine | Classifies Daily trend direction and stage from price/SMA alignment. | `1.1.0` | `Foundation` | Foundation | KR-260 trend close; KR-270 trend SMA 20/50/200 | Trend readiness, direction, stage, SMA alignment, price-position states and flags | KR-310; KR-320; KR-330; KR-340; KR-350; KR-360; KR-370; KR-705 | Included in repository-history intelligence-core freeze language while source remains Foundation. **Source metadata requires reconciliation.** |
| KR-310 | Trend Quality Engine | Evaluates trend quality without changing KR-300 direction. | `1.0.0` | `Foundation` | Foundation | KR-300 public direction; KR-260/270 trend price, SMA, RSI, ATR; KR-271 math | Quality state/text/score/flags and compatibility evidence outputs | KR-315; KR-330; KR-340; KR-350; KR-360; KR-370; KR-380; KR-705 | Included in repository-history freeze language while source remains Foundation. **Source metadata requires reconciliation.** |
| KR-315 | Compression Intelligence Engine | Detects compression and remembers expansion release without predicting direction. | `1.0.0` | `FROZEN` | Frozen | Existing KR-260/270 price, volume, ATR, SMA, RSI interfaces; KR-280 CPR width | Compression readiness, score, state, text/reason, state flags, three-bar expansion memory | KR-360; KR-370; KR-380; KR-705 | Source contract records core behavior as validated. No claim is made that every expansion event has been observed live. |
| KR-320 | Market Acceptance Engine | Classifies acceptance or rejection around CPR in KR-300 trend context. | `0.1.0` | `Foundation` | Foundation | KR-280 public CPR/position; KR-300 public trend; existing candle data | Acceptance state/text/score/flags and compatibility barrier outputs | KR-330; KR-340; KR-350; KR-360; KR-370; KR-380; KR-705 | Included in repository-history freeze language while source remains Foundation. **Source metadata requires reconciliation.** |
| KR-330 | Momentum Confirmation Engine | Measures directional trend energy without owning direction. | `0.1.0` | `Foundation` | Foundation | KR-300/310/320 public outputs; existing RSI, ADX, volume, and candle interfaces | Momentum readiness/state/text/score/flags and compatibility context outputs | KR-335; KR-340; KR-350; KR-360; KR-370; KR-380; KR-705 | Included in repository-history freeze language while source remains Foundation. **Source metadata requires reconciliation.** |
| KR-335 | Price Action Evidence Engine | Converts objective candle quality, closing pressure, and ATR-normalized expansion/contraction into standardized evidence. | `1.0.0` | `FOUNDATION` | Foundation | KR-260 normalized OHLC plus public outputs from KR-300, KR-310, KR-320, and KR-330 | Price action readiness/status/reason/score/state/summary; body, wick, close-location, normalized-range, closing-pressure, and expansion developer metrics | Future evidence synthesis consumers; no confidence, decision, execution, alert, trade-management, or presentation consumer in this release | Category: Evidence Engine. Static source review only. No `request.security()` calls, routing, configuration, confidence weighting, decision influence, or execution logic are introduced. |
| KR-340 | Review Readiness Engine | Determines whether the intelligence set is ready, waiting, or blocked for review. | `0.1.0` | `Skeleton` | Skeleton | KR-300 through KR-330 readiness/context outputs | Review input readiness, state/text, ready/blocked/wait flags | KR-350; KR-360; KR-370 | Repository history uses freeze language while source remains Skeleton. **Source metadata requires reconciliation.** |
| KR-345 | Relative Intelligence Engine | Measures NSE Equity market-relative and sector-relative strength and produces standardized evidence. | `1.0.0` | `FOUNDATION` | Foundation | Public outputs from KR-252, KR-260A, and KR-260B only | Relative readiness/status/reason/score/state/summary; market and sector relative values, states, trends, benchmark symbol, and lookback | Future evidence synthesis consumers; no confidence, decision, execution, alert, trade-management, or presentation consumer in this release | Category: Evidence Engine. Static source review only. No `request.security()` calls, routing, configuration, symbol mapping, confidence weighting, decision influence, or execution logic are introduced. NSE Index and MCX are not applicable in v1.0. |
| KR-350 | Opportunity Foundation Engine | Classifies bullish, bearish, or absent opportunity context. | `0.1.0` | `Skeleton` | Skeleton | KR-330 context; KR-340 review readiness; prior public direction/context outputs | Opportunity readiness/state/text and bullish/bearish/no-opportunity flags | KR-360; KR-370; KR-380; KR-705 | Repository history uses freeze language while source remains Skeleton. **Source metadata requires reconciliation.** |
| KR-360 | Confidence Engine | Synthesizes prior public outputs into explainable confidence. | `1.0.0` | `FROZEN` | Frozen | Public outputs from KR-300, KR-310, KR-315, KR-320, KR-330, KR-340, and KR-350; KR-335 and KR-345 are not consumed in this release | Confidence readiness, 0-100 score, state/text/reason, classification flags | KR-370; KR-380; KR-705 | Static review confirms score clamping and public-output-only architecture. Source and repository history agree on Frozen. |

## Decision, Execution, Trade Management, Alerts, and Interface

| Engine | Name | Single responsibility | Source version | Source status | Contract maturity | Inputs / dependencies | Public outputs summary | Downstream consumers | Validation scope and notes |
|---|---|---|---|---|---|---|---|---|---|
| KR-370 | Decision Engine | Decides direction and readiness: AVOID, WAIT, WATCH, BUY READY, or SELL READY. | `1.0.0` | `FROZEN` | Frozen | Public `out...` outputs from prior intelligence engines | Decision readiness/state/text/reason, blocker, next review, dynamic checklist, exclusive state flags | KR-380; KR-705 | Source header records validation on Copper, Silver, and Gold. It does not trigger entries. |
| KR-380A | Execution Context Adapter | Translates minimum Daily/4H/1H reference and MCX 1H facts into a formal timing interface. | `0.1.0` | `FOUNDATION` | Adapter | Narrow access to KR-260/270 reference datasets plus prior public readiness/direction context | Reference Daily/4H/1H permissions, readiness and blocker text; MCX 1H context readiness | KR-380; KR-390A context gating | Repository history uses freeze language while source remains FOUNDATION. **Source metadata requires reconciliation.** |
| KR-380 | Execution Trigger Engine | Converts only KR-370 BUY READY/SELL READY into confirmed timing states. | `0.1.0` | `FOUNDATION` | Foundation | KR-370 public decision; prior public quality/acceptance/confidence/compression/momentum/opportunity outputs; KR-380A public adapter outputs | Trigger readiness/bar confirmation, state/text/reason, exclusive trigger flags, execution readiness and blocker queue | KR-390; KR-400; KR-705 | Repository history describes KR-380 v1.0 as Frozen and validated on Copper, Gold, and Silver, while source says 0.1.0 FOUNDATION. **Source metadata requires reconciliation.** |
| KR-390A | Trade Management Execution Adapter | Supplies confirmed prior-five-bar MCX 1H swing references for model stops. | `0.1.0` | `FOUNDATION` | Adapter | KR-260 execution H/L/C; KR-380A MCX 1H context | Trade execution context/stop readiness, execution close, confirmed swing low/high | KR-390 | Static review confirms use of completed execution bars. No live stop lifecycle validation is claimed. |
| KR-390 | Trade Management Engine | Maintains the objective KRONOS model trade after a confirmed KR-380 trigger. | `0.1.0` | `FOUNDATION` | Foundation | KR-380 BUY/SELL trigger outputs; KR-390A stop interface; confirmed MCX 1H bars | Readiness, active/direction/state/text/reason, model entry, initial/managed stops, 1R/2R targets, lifecycle flags | KR-705; future trade-management consumers | Static review confirms persistent state, non-overlap, no silent reversal, non-loosening stops, and confirmed-close exits. Live HOLD/PROTECT/TRAIL/EXIT coverage remains open. |
| KR-400 | Execution Alert Engine | Emits TradingView alert events for new confirmed KR-380 BUY NOW/SELL NOW transitions. | `0.1.0` | `FOUNDATION` | Foundation | KR-380 public trigger readiness, confirmation, BUY and SELL outputs | Buy/sell alert-event flags, readiness, status text; exactly two `alertcondition()` definitions | TradingView alert subsystem; no intelligence consumer | Static review confirms edge detection and inherited MCX 1H restriction. Live push-delivery evidence is not stored. |
| KR-705 | Engine Status Panel | Displays and translates trader-facing engine intelligence without owning decisions. | `0.1.2` | `FROZEN` | Developer/Trader Tool | Public outputs from KR-300 through KR-390 and KR-380A execution context | Table presentation only; no downstream public contract | Trader | Source comments/input still use developer-validation terminology while the verified architecture assigns trader-facing display ownership. **Source metadata requires reconciliation.** |

## Futures Model Status

### Validated Futures Model

- **MCX Metals**
  - Gold with `COMEX:GC1!`
  - Silver with `COMEX:SI1!`
  - Copper with `COMEX:HG1!`

Validation is scoped in [MCX Metals Validation](validation/MCX-METALS-VALIDATION.md). It must not be interpreted as proof that every live trigger, management transition, or alert-delivery path has occurred.

### Planned

- **MCX Energy:** Crude Oil and Natural Gas
- **NSE Stock Futures**
- **Futures Model selector:** Auto plus manual model override

Symbol mappings present for planned models are scaffolding, not proof that the complete model is supported or validated.

## Known Source-Metadata Reconciliation Items

1. KR-280 contains both `1.0.0` and `1.1.0` version comments.
2. Repository history describes the KR-300 through KR-380 intelligence core as frozen, while several source headers remain Foundation, Skeleton, or FOUNDATION.
3. KR-380 repository history describes v1.0 Frozen, while its source header says v0.1.0 FOUNDATION.
4. KR-705 source comments still describe a developer validation panel, while current architecture assigns it trader-facing display and translation.
5. Product-level source constants remain Version `0.5.0`, Build `0004`; this Phase 1 task does not alter release metadata.
