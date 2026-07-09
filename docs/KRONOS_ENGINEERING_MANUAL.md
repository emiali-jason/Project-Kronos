# Project KRONOS Engineering Manual

**Version:** 0.1.0  
**Product:** Project KRONOS  
**Document Type:** Permanent Engineering Reference

---

## Table of Contents

1. [Vision](#1-vision)
2. [Mission](#2-mission)
3. [Version 1.0 Scope](#3-version-10-scope)
4. [What KRONOS Is](#4-what-kronos-is)
5. [What KRONOS Is Not](#5-what-kronos-is-not)
6. [Engineering Principles](#6-engineering-principles)
7. [KRONOS Interface Standard (KIS)](#7-kronos-interface-standard-kis)
8. [Development Workflow](#8-development-workflow)
9. [KRONOS Architecture](#9-kronos-architecture)
10. [Engine Specification Template](#10-engine-specification-template)
11. [Current Engine Status](#11-current-engine-status)
12. [Design Decisions](#12-design-decisions)
13. [Long Term Philosophy](#13-long-term-philosophy)

---

## 1. Vision

Project KRONOS is intended to become a professional-grade directional intelligence framework for active traders.

The long-term vision is to help the trader understand market direction, trend quality, market acceptance, opportunity context, and decision confidence through a transparent modular system. KRONOS should remain explainable at every stage. A trader should be able to inspect any engine and understand why the system is producing a particular state.

KRONOS is designed to grow over several years without losing architectural discipline. New engines should strengthen the decision process, not add noise.

---

## 2. Mission

The mission of KRONOS is to identify high-probability institutional trends, stay aligned with the trend while evidence remains strong, and exit or stand aside when evidence weakens.

KRONOS does not attempt to predict exact tops or bottoms. It exists to support disciplined directional understanding.

Every engine must serve one or more of these mission areas:

- Trend understanding
- Market context
- Evidence quality
- Opportunity recognition
- Position management
- Decision quality
- Trader clarity

KRONOS decision flow summary:

**Direction. Quality. Acceptance. Energy. Opportunity. Confidence.**

---

## 3. Version 1.0 Scope

Version 1.0 is focused on futures and directional market intelligence. The first production milestone should be narrow, stable, and useful before the system expands into more complex workflows.

### MCX Futures

Version 1.0 includes directional intelligence support for:

- Gold
- Silver
- Copper
- Crude Oil
- Natural Gas

### NSE

Version 1.0 includes directional intelligence support for:

- Cash Market Stocks
- Stock Futures

### Version 1.0 Exclusions

The following areas are excluded from Version 1.0:

- Options Strategies
- Strategy Builder
- Portfolio Analytics

These exclusions protect the architecture from expanding too early. They may be revisited after the core directional intelligence system is stable.

---

## 4. What KRONOS Is

KRONOS is a **Directional Intelligence Engine**.

It is a modular decision-support framework that organizes market data into structured evidence. It helps the trader answer questions such as:

- Is there a dominant trend?
- Is the trend healthy or extended?
- Is the market accepting price in the trend direction?
- Is the opportunity context improving or weakening?
- Is the evidence strong enough to continue monitoring?

KRONOS is engineered as a sequence of independent engines. Each engine answers one major question and exposes public outputs for downstream engines.

---

## 5. What KRONOS Is Not

KRONOS is not an automated trading system.

KRONOS is not:

- A buy/sell signal generator
- A prediction engine
- A top-or-bottom finder
- A black-box strategy
- A replacement for trader judgment
- A portfolio management platform
- An options strategy builder
- A collection of unrelated indicators

Indicators inside KRONOS do not generate trades by themselves. Indicators contribute evidence. Evidence contributes context. Context contributes decision quality.

---

## 6. Engineering Principles

The following engineering principles govern Project KRONOS.

### Architecture Principles

- Preserve the existing architecture.
- Extend the framework instead of rewriting it.
- One engine must have one major responsibility.
- Never merge unrelated engine responsibilities.
- Higher engines consume only public outputs from lower engines.
- Mature engines must expose clean public interfaces.
- Loose coupling is mandatory.
- Frozen engines must not be changed unless specifically requested.
- Bug fixes are allowed in frozen engines only when the fix is scoped and necessary.

### Code Quality Principles

- Use Pine Script Version 6.
- Follow the existing naming conventions.
- Keep functions small and reusable.
- Keep calculations readable.
- Prefer clarity over fewer lines.
- Avoid duplicated calculations.
- Reuse helper functions where practical.
- Avoid unnecessary `request.security()` calls.
- Comment all major sections.
- Preserve existing comments unless there is approval to remove them.
- Keep one logical statement per line where possible.
- Avoid long compressed one-line calculations.
- Avoid nested ternary expressions unless Pine compatibility requires them.

### Trading Logic Principles

- KRONOS follows trend evidence, not prediction.
- No single indicator is sufficient.
- Confluence is required.
- Trend is more important than prediction.
- Institutional participation matters.
- Never introduce trading rules without approval.
- Never invent trading logic to fill a gap.
- When uncertain, ask before implementing.

### Documentation Principles

- Documentation must evolve with the code.
- Major architectural decisions must be recorded.
- Engine purpose must be documented before complex expansion.
- Every public output should have a clear reason to exist.
- The engineering manual explains why the system exists and how it should evolve.

---

## 7. KRONOS Interface Standard (KIS)

The KRONOS Interface Standard defines the public output shape expected from mature engines.

The purpose of KIS is to keep engines predictable, easy to consume, and safe to extend.

### Required Outputs

Every mature engine should expose these output types where applicable:

| Output | Purpose |
|--------|---------|
| State | Numeric machine-readable state. |
| Text | Human-readable explanation of the state. |
| Ready | Boolean indicating whether the engine has sufficient valid input. |

### Optional Outputs

Engines may expose these outputs when they add value:

| Output | Purpose |
|--------|---------|
| Score | Numeric measure of quality, strength, or completeness. |
| Confidence | Numeric or text confidence classification. |
| Reason1-Reason5 | Human-readable explanation stack for dashboards or developer panels. |

### Interface Rules

- Public outputs must be stable once downstream engines consume them.
- Public names should be explicit and readable.
- Internal variables should not be consumed by higher engines.
- Compatibility aliases are allowed when an engine evolves and downstream engines still depend on older outputs.
- Public outputs should not expose unnecessary internal calculations.

---

## 8. Development Workflow

KRONOS development follows a disciplined sequence.

```text
Discuss
  ↓
Design
  ↓
Implement
  ↓
Compile
  ↓
Validate
  ↓
Commit
  ↓
Push
  ↓
Update Documentation
```

### Discuss

Clarify the trading question, affected engines, scope boundaries, and expected outputs.

### Design

Identify dependencies, public interfaces, required states, and downstream consumers before code is written.

### Implement

Implement only the requested feature. Preserve existing interfaces and avoid unrelated refactoring.

### Compile

Compile in TradingView after implementation. Pine compatibility is mandatory.

### Validate

Validate engine states, public outputs, and behavior across representative symbols and timeframes.

### Commit

Commit only coherent changes. The commit should describe the engine and purpose clearly.

### Push

Push after validation so the repository remains the source of truth.

### Update Documentation

Update documentation when architecture, engine responsibility, public interfaces, or development rules change.

---

## 9. KRONOS Architecture

The KRONOS architecture is engine-based. Each engine answers one major question and passes public outputs forward.

### Current and Planned Engine Flow

```text
KR-100 Configuration
  ↓
KR-150 Display / Base Indicators
  ↓
KR-200 Market Identification
  ↓
KR-250 Asset Intelligence
  ↓
KR-260 Market Data
  ↓
KR-270 Market Indicators
  ↓
KR-271 Mathematical Library
  ↓
KR-275 Market Structure Intelligence
  ↓
KR-280 CPR Intelligence
  ↓
KR-300 Trend Foundation
  ↓
KR-310 Trend Quality
  ↓
KR-320 Market Acceptance
  ↓
KR-330 Context Foundation
  ↓
KR-340 Review Readiness
  ↓
KR-350 Opportunity Foundation
  ↓
KR-400 Position Management
  ↓
KR-500 Decision Engine
  ↓
KR-600 Risk Management
  ↓
KR-700 Dashboard and Developer Tools
  ↓
KR-800 Alerts
  ↓
KR-900 Rendering Engine
```

### Architectural Notes

- KR-280 is frozen and should remain stable unless a specific approved change is required.
- KR-300 through KR-350 form the current intelligence layer.
- KR-705 is a developer tool, not an end-user dashboard.
- KR-900 is reserved for future rendering separation if display complexity grows.

---

## 10. Engine Specification Template

Every new engine specification should use the following template.

### Engine Name

Use the KR number and engine title.

### Purpose

Explain why the engine exists.

### Trading Question

State the single trading question the engine answers.

### Philosophy

Explain the trading belief or market behavior behind the engine.

### Inputs

List all consumed public outputs and any direct market data dependencies.

### Outputs

List all public outputs, including state, text, ready, score, confidence, and reasons where applicable.

### States

Define every numeric state and its meaning.

### What it Does

Describe the engine responsibility in plain language.

### What it Does NOT Do

Define strict boundaries. State what the engine must not decide, display, or trigger.

### Known Limitations

Document assumptions, temporary simplifications, and validation gaps.

### Future Improvements

List likely extensions without implementing them early.

### Version History

Track version, build, status, and meaningful changes.

---

## 11. Current Engine Status

This section documents key active and frozen engines in the current KRONOS implementation.

### KR-280 CPR Intelligence

| Field | Status |
|-------|--------|
| Engine Status | Frozen |
| Current Role | Calculates CPR, support/resistance, CPR relationship, price position, and CPR public outputs. |
| Why it Exists | CPR is a major institutional reference zone. KRONOS uses it to understand value, acceptance, rejection, and barrier behavior. |
| Current Boundary | KR-280 performs no trading decisions. |
| Future Direction | Future changes should be renderer enhancements or additive outputs that do not break compatibility. |

### KR-300 Trend Foundation

| Field | Status |
|-------|--------|
| Engine Status | Foundation |
| Current Role | Classifies local trend foundation using SMA alignment and price position. |
| Why it Exists | KRONOS must know whether the market has a directional foundation before evaluating quality or opportunity. |
| Current Boundary | KR-300 defines trend direction; it does not score quality or generate signals. |
| Future Direction | It should remain a stable directional foundation consumed by higher engines. |

### KR-310 Trend Quality

| Field | Status |
|-------|--------|
| Engine Status | Foundation |
| Current Role | Evaluates the quality of the KR-300 trend using SMA slope, railway track quality, extension, RSI extension, and pullback respect. |
| Why it Exists | A trend can exist but be weak, extended, or healthy. KR-310 separates direction from quality. |
| Current Boundary | KR-310 never flips KR-300 direction and never produces trade signals. |
| Future Direction | Add confidence and reason outputs when the quality model matures. |

### KR-320 Market Acceptance

| Field | Status |
|-------|--------|
| Engine Status | Foundation |
| Current Role | Evaluates whether the market is accepting price in the direction of the KR-300 trend. |
| Why it Exists | Trend direction is not enough. KRONOS must know whether price is being accepted beyond meaningful market levels. |
| Current Boundary | KR-320 evaluates acceptance only. It does not validate trades or produce alerts. |
| Future Direction | Expand acceptance reasons and refine breakout/pullback validation. |

### KR-330 Momentum Confirmation Engine

| Field | Status |
|-------|--------|
| Engine Status | Foundation |
| Current Role | Measures whether the current trend still has enough energy to justify a new swing trade. |
| Why it Exists | KRONOS must separate direction from usable trend energy. A trend can be directionally correct but too weak, exhausted, or fading for a fresh entry. |
| Current Boundary | KR-330 measures energy only. It does not determine direction, override KR-300, generate signals, calculate stops or targets, or decide opportunity. |
| Future Direction | Expand reason outputs and refine momentum persistence validation after live symbol testing. |

#### Purpose

Measure whether the current trend still has enough energy to justify a new swing trade.

#### Trading Question

Does this trend still have enough energy to reward a fresh entry?

#### Core Concept

KR-330 measures **Energy**, not Direction.

Direction comes from KR-300. Quality comes from KR-310. Acceptance comes from KR-320.

#### Evidence Pillars

1. **Momentum Persistence**

   Expanding impulse legs indicate building energy. Shrinking impulse legs indicate weakening energy.

2. **RSI Behaviour**

   Rising RSI supports energy. Falling RSI warns of weakening. Flat RSI suggests normal or fading momentum.

3. **ADX Behaviour**

   Rising ADX supports strengthening trend energy. Falling ADX warns of fading trend strength.

4. **Volume Participation**

   Expanding volume supports participation. Declining volume reduces confidence.

5. **Candle Strength**

   Strong bodies and strong closes support energy. Small bodies, overlap, and rejection wicks weaken energy.

#### States

| State | Meaning |
|-------|---------|
| 4 | Building |
| 3 | Strong |
| 2 | Normal |
| 1 | Weakening |
| 0 | Exhausted |

#### Outputs

- `outMomentumState`
- `outMomentumText`
- `outMomentumReady`
- `outMomentumScore`
- `outMomentumBuilding`
- `outMomentumStrong`
- `outMomentumNormal`
- `outMomentumWeakening`
- `outMomentumExhausted`

#### What KR-330 Does

- Measures trend energy.
- Helps determine whether a fresh entry still has momentum support.
- Supports KR-340 and KR-350.

#### What KR-330 Does NOT Do

- Does not determine trend direction.
- Does not override KR-300.
- Does not generate buy/sell signals.
- Does not calculate stop-loss or targets.
- Does not decide opportunity.

### KR-705 Developer Debug Panel

| Field | Status |
|-------|--------|
| Engine Status | Developer Tool |
| Current Role | Displays current engine states for validation. |
| Why it Exists | Developers need a compact way to confirm engine state flow during TradingView testing. |
| Current Boundary | KR-705 is not an end-user dashboard and does not make decisions. |
| Future Direction | Replace placeholder unavailable values with dynamic confidence and reason outputs as engines mature. |

---

## 12. Design Decisions

This section records permanent architectural decisions that guide future implementation.

### DD-004: KR-705 Must Become Timeframe-Aware

KR-300 remains the Daily Trend Foundation.

KR-705 must not show the same dashboard on every chart. A fixed dashboard across all chart timeframes would make the multi-chart workflow misleading because each chart is expected to answer a different class of question.

- Daily charts show trend intelligence.
- 4H charts should eventually show structure intelligence.
- 1H charts should eventually show execution intelligence.
- Until 4H and 1H engines exist, KR-705 may display unavailable or coming states.

This decision preserves the intended multi-chart workflow and prevents KR-705 from implying that Daily trend intelligence is equally valid on every chart.

---

## 13. Long Term Philosophy

KRONOS should grow slowly, deliberately, and with strong interface discipline. The system should become more useful by improving the quality of its reasoning, not by accumulating indicators.

Every future engine should earn its place by improving the trader's understanding of direction, quality, acceptance, opportunity, position management, or decision confidence.

The quality of KRONOS will not be measured by the number of indicators it contains, but by the quality of the trading decisions it helps the trader make.
