# KRONOS Engine Ownership

**Status:** Canonical
**Date:** 2026-07-10

This matrix defines which question each engine owns. Ownership is exclusive: downstream engines may interpret public outputs, but they must not silently recreate or reverse an upstream engine's responsibility.

See also [Architecture Overview](OVERVIEW.md), [Data Flow](DATA_FLOW.md), and the [Engine Status Registry](../ENGINE_STATUS.md).

## Evidence Synthesis Boundary

KES (KRONOS Evidence Synthesis) collects, validates, standardizes, and packages evidence before KR-360 Confidence.

KES does not own:

- evidence generation;
- confidence calculation;
- decisions;
- execution;
- trade management;
- alerts;
- presentation.

KES is an unnumbered architectural boundary over existing public evidence contracts. It does not replace an engine, change engine numbering, or alter any runtime contract.

## Ownership Matrix

| Engine | Question answered | Owns | Must not own | Primary inputs | Primary outputs | Downstream consumers |
|---|---|---|---|---|---|---|
| KR-100 | What product settings and common constants apply? | Configuration constants and user inputs | Market analysis or decisions | User configuration | Product constants, periods, display inputs | KR-150; KR-260 |
| KR-150 | Which base chart indicators should be displayed? | Legacy chart SMA display | Higher-timeframe intelligence or decisions | Chart close; KR-100 periods | SMA display series and plots | Trader chart only |
| KR-200 | What market, exchange, and symbol is this chart? | Market and instrument identity | Asset dependency selection | TradingView `syminfo` | Market flags and normalized identity | KR-250 |
| KR-250 | What asset is this and which reference symbol/profile applies? | Asset-to-reference mapping and dependency profile | Market-data retrieval or trading decisions | KR-200 identity | Asset interface, primary/reference symbols, profiles | KR-260; market-aware adapters |
| KR-251 | Which Swing market model and execution semantics apply? | Market-model classification, analysis symbol, execution instrument text/type, venue, profile, and support flag | Market relationships, data retrieval, intelligence, or decisions | KR-250 asset identity; exact NSE equity/index symbol sets | Model/configuration interface and supported-instrument status | KR-252; future KR-260A integration |
| KR-252 | What cash market, sector index, parent index, or global reference influences this instrument? | Market relationship configuration only, including MCX global references, NSE Index relationships, and the generated 91-stock NSE Equity relationship map from the CSV source of truth | Support/model classification, market-data retrieval, relative strength, decisions, or alerts | KR-251 support/model outputs; KR-250 current asset identity; `data/nse/KRONOS_NSE_RELATIONSHIPS.csv` | Relationship readiness/status/reason, cash/global/sector/parent symbols, generated NSE map, and context flags | Future relationship-aware engines; not wired into KR-260 yet |
| KR-260A | What symbols should KRONOS use? | Standardized symbol routing, route readiness, route status, capability flags, analysis/execution selection, and reference-symbol selection | `request.security`, OHLCV retrieval, normalization, indicators, relative strength, decisions, alerts, or trade management | KR-251 public configuration outputs; KR-252 public relationship outputs | Market data route interface for analysis, reference, sector, parent, and execution text | Future KR-260B retrieval |
| KR-260B | Retrieve market data from those symbols. | Guarded current-chart-timeframe OHLCV retrieval and per-context data readiness | Symbol routing, normalization, calculations, indicators, intelligence, decisions, rendering, alerts, or trade management | KR-260A public routing outputs only | Raw Analysis, Primary, Secondary, Sector, and Parent OHLCV with readiness flags | Future KR-260 normalization |
| KR-260 | Normalize retrieved market data for the Intelligence Layer. | Normalized market-data datasets, validation, safety, and downstream availability | Symbol routing, TradingView `request.security()` calls, indicator interpretation, or decisions | Future KR-260B retrieval outputs; current legacy data path pending migration | Normalized strategic, trend, structure, and execution datasets | KR-270; KR-275; KR-280; KR-300; adapters |
| KR-270 | Which standard indicators derive from available data? | SMA, RSI, ATR, ADX, volume, and related indicator series | Direction, opportunity, or execution timing | KR-260 datasets | Standardized indicator interfaces | Intelligence engines; KR-380A |
| KR-271 | Which reusable mathematical calculations are required? | Shared deterministic math functions | Market interpretation | OHLC/series arguments | TR, ATR, DM, DI, and trend-strength calculations | KR-275; KR-310; KR-330 |
| KR-275 | What confirmed market structure exists? | Swings, structure, BOS, and CHoCH | Trend decision or entry timing | KR-260 data; KR-271 math | Structure state and event outputs | Structure-aware downstream engines |
| KR-280 | What CPR and pivot reference context applies? | Reference timeframe, CPR, pivots, width, relationship, and price position | Acceptance decisions, entries, or alerts | Previous completed reference OHLC | CPR and pivot public interface | KR-315; KR-320; later intelligence |
| KR-300 | What is the Daily trend foundation? | Trend direction and stage | Trend quality, acceptance, entries, or alerts | Trend close and SMA stack | Trend readiness, direction, stage, alignment, position | KR-310 through KR-370; KR-705 |
| KR-310 | How healthy is the established trend? | Trend quality and extension | Direction reversal, opportunity, or entry timing | KR-300 direction; trend indicators | Quality state, score, text, flags | KR-315; KR-330 through KR-380; KR-705 |
| KR-315 | Is energy compressing or beginning to release? | Direction-neutral compression and expansion memory | Breakout direction, trade decisions, or entries | Existing price/volume/ATR/SMA/RSI and CPR width interfaces | Compression score/state/reason and expansion flag | KR-360; KR-370; KR-380; KR-705 |
| KR-320 | Is price accepted or rejected around value? | CPR acceptance state | Trend direction, momentum, or entries | KR-280 CPR; KR-300 trend; candle context | Acceptance and barrier public outputs | KR-330 through KR-380; KR-705 |
| KR-330 | Does the trend have usable momentum? | Momentum energy and persistence | Direction, opportunity, or entries | Public trend/quality/acceptance plus indicator evidence | Momentum state, score, text, flags | KR-335 through KR-380; KR-705 |
| KR-335 | What objective price action evidence exists? | Objective candle quality, closing pressure, expansion/contraction, and public evidence outputs | Trend, structure, momentum, relative strength, confidence, decisions, execution, trade management, alerts, or presentation | KR-260 normalized OHLC plus public outputs from KR-300, KR-310, KR-320, and KR-330 | Price action readiness/status/reason/score/state/summary plus detailed body, wick, close-location, normalized-range, closing-pressure, and expansion metrics | Future evidence synthesis consumers only; no KR-360/KR-370/KR-380 influence in this release |
| KR-340 | Is the evidence ready for review? | Review readiness, wait, and blocked gates | Direction or execution timing | Prior intelligence readiness outputs | Review state/text and readiness flags | KR-350; KR-360; KR-370 |
| KR-345 | How is the instrument performing relative to its benchmark? | Market relative, sector relative, relative evidence scoring, and relative state classification | Trend, trend quality, compression, market acceptance, momentum, price action, opportunity, confidence, decisions, execution, trade management, alerts, or presentation | Public outputs from KR-252, KR-260A, and KR-260B only | Relative readiness/status/reason/score/state/summary plus market/sector relative values, states, trends, benchmark symbol, and lookback | Future evidence synthesis consumers only; no KR-360/KR-370/KR-380 influence in this release |
| KR-350 | Is there a directional opportunity context? | Bullish, bearish, or absent opportunity context | Entry trigger or trade management | Context and review outputs | Opportunity state/text/direction flags | KR-360; KR-370; KR-380; KR-705 |
| KR-360 | How confident is the combined evidence? | Explainable 0-100 confidence and gates | Direction, entry timing, or decisions | Public outputs from KR-300, KR-310, KR-315, KR-320, KR-330, KR-340, and KR-350; KR-335 and KR-345 are not consumed in this release | Confidence score/state/reason/readiness | KR-370; KR-380; KR-705 |
| KR-370 | What should the trader do now? | Direction and readiness: AVOID, WAIT, WATCH, BUY READY, SELL READY | Entry triggers, raw timeframe calculations, alerts, stops, or trade management | Public outputs from prior engines | Decision state/text/reason, blockers, checklist, state flags | KR-380; KR-705 |
| KR-380A | Which minimum reference and MCX execution facts does timing require? | Narrow execution-context translation | Full Daily/4H/1H intelligence stacks or a directional decision | Narrow KR-260/270 datasets and prior public context | Reference permissions/readiness/blockers and MCX 1H context | KR-380; KR-390A gating |
| KR-380 | Has the entry trigger occurred? | Execution timing only | Bullish/bearish direction, WATCH/READY decisions, stops, targets, or management | KR-370 READY direction; public intelligence outputs; KR-380A | NO TRIGGER, FORMING, BUY NOW, SELL NOW, EXTENDED, FAILED and blocker queue | KR-390; KR-400; KR-705 |
| KR-390A | Which confirmed MCX 1H structure reference can protect a model trade? | Narrow completed-bar swing stop references | A full structure engine, trade direction, or management policy | Execution H/L/C and MCX 1H context | Execution close, confirmed swing low/high, readiness | KR-390 |
| KR-390 | What is the state of the objective KRONOS model trade? | Persistent model-trade entry, stop, targets, HOLD, PROTECT, TRAIL, EXIT, INVALIDATED | Personal-position tracking, broker orders, alerts, or new direction | Confirmed KR-380 BUY/SELL event; KR-390A | Trade state, direction, model prices, reasons, lifecycle flags | KR-705; future management interfaces |
| KR-400 | Did a new confirmed BUY NOW or SELL NOW event occur? | Exactly two TradingView alert event types | Trading intelligence, entry timing, trade management, or broker automation | KR-380 public BUY/SELL and confirmation outputs | Buy/sell alert event, readiness, status text | TradingView alerts |
| KR-705 | What intelligence should the trader see? | Trader-facing display, concise translation, and status presentation | Trading calculations, decisions, timing, management, or alerts | Public outputs from upstream engines and adapters | Visual table only | Trader |

## Non-Negotiable Boundaries

### KR-370 and KR-380

- KR-370 owns direction and readiness but never triggers an entry.
- KR-380 acts only when KR-370 is BUY READY or SELL READY.
- Only BUY READY may become BUY NOW.
- Only SELL READY may become SELL NOW.
- KR-380 must not upgrade WATCH states or infer a new direction.

### KR-390

- KR-390 manages the objective KRONOS model trade.
- It does not ask whether the user personally entered the trade.
- It does not place, modify, or close broker orders.

### KR-400

- KR-400 owns only the event edge for confirmed BUY NOW and SELL NOW alerts.
- It does not create trading intelligence or repeat KR-380 timing logic.
- TradingView delivers notifications; KRONOS does not automate a broker.

### KR-705

- KR-705 owns display and trader-readable translation.
- It consumes public outputs and does not calculate decisions.

## Adapter Exception

KR-380A and KR-390A are documented exceptions to the strict public-output-only dependency rule. They may access narrowly scoped lower-level datasets when a safe public fact does not yet exist. This exception does not permit them to duplicate complete trend, acceptance, confidence, structure, decision, timing, or management engines.

The full adapter decision is recorded in [ADL-003](ADL-003-Execution-Context-Adapters.md).
