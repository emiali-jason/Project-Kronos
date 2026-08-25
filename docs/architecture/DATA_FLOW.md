# Project KRONOS Data Flow

**Status:** Canonical
**Date:** 2026-07-10

This document describes how information moves through KRONOS. It complements the [Architecture Overview](OVERVIEW.md) and [Engine Ownership Matrix](ENGINE_OWNERSHIP.md).

## Canonical Flow Classes

KRONOS distinguishes:

- platform-support flow;
- the canonical business pipeline;
- explicit product-consumption flow; and
- attributable evidence and feedback flow.

A support, evidence, or feedback flow does not become a business-pipeline stage, transfer semantic ownership, or create runtime authority.

## Canonical Business Pipeline

The approved business pipeline remains unchanged:

```text
Instrument
    ↓
Observation
    ↓
Validation
    ↓
Risk
    ↓
Execution
    ↓
Portfolio
```

Provider supports Instrument through an approved contract boundary but does not join this pipeline.

Market supplies Market-owned schedule and availability meaning as platform support. It does not become an additional business-pipeline stage.

## Platform Support Flow — Instrument Master

The canonical Instrument Master support flow is:

```text
Authorized Provider Dataset
        ↓
Provider Acquisition                                      [Provider-owned]
        ↓
Provider-and-Dataset Catalogue Partition                  [Provider-owned]
        ↓
Provider Snapshot and Provider Records                    [Provider-owned]
        ↓
Provider Dispositions                                     [Provider-owned]
        ↓
Submission Eligibility                                    [Provider-owned]
        ↓
EAIC-002 — Provider → Instrument Submission Contract      [sole governed boundary]
        ↓
Instrument Contract Receipt and Validation                [Instrument-side handling]
        ↓
Instrument Interpretation Admission                       [Instrument-side handling]
        ↓
Instrument Interpretation Processing                      [Instrument-owned]
        ↓
Interpretation Outcome                                    [Instrument-owned]
        ↓
Canonical Identity Decision                               [Instrument-owned]
        ↓
Provider Mapping Decision / Provider Mapping Status       [Instrument-owned]
        ↓
Cross-Provider Reconciliation, where applicable           [Instrument-owned]
        ↓
Canonical Instrument Catalogue Publication                [Instrument-owned]
```

This support flow applies only to the Instrument Master dataset governed by [ADR-009](platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md) and [EAIC-002](interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md).

[EAIC-002](interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) is the sole governed Provider-to-Instrument boundary for this dataset.

Provider shall not write directly to Instrument state.

Instrument shall not access or mutate Provider Catalogue internals.

An arrow across EAIC-002 represents contract-governed presentation and receipt. It does not represent ownership transfer or direct state mutation.

## Ownership Through the Support Flow

| Flow stage or meaning | Semantic owner |
|---|---|
| Provider acquisition | Provider |
| Provider-and-Dataset Catalogue Partition | Provider |
| Provider Snapshot and Provider Records | Provider |
| Provider Record Identity | Provider |
| Provider Dispositions | Provider |
| Submission Eligibility | Provider |
| Provider provenance | Provider |
| Provider acquisition provenance | Provider |
| EAIC-002 contract boundary | Ownership preserved on each side |
| Contract receipt and validation handling | Instrument |
| Interpretation admission | Instrument |
| Interpretation processing status | Instrument |
| Interpretation outcome | Instrument |
| Canonical identity decision | Instrument |
| Provider mapping status | Instrument |
| Cross-Provider reconciliation | Instrument |
| Canonical Instrument Catalogue publication | Instrument |

Technical receipt does not imply contract validity.

Contract validation does not imply interpretation admission or interpretation success.

Interpretation admission does not imply canonical identity.

Canonical identity does not automatically imply Provider mapping.

Canonical Instrument Catalogue publication does not imply product membership or product eligibility.

## Provider Catalogue Currentness and Supersession

Provider Catalogue currentness is scoped independently within each Provider-and-Dataset Catalogue Partition.

Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition.

Provider Record Identity is unique only within one Provider Snapshot.

Currentness and supersession shall preserve:

- partition-scoped currentness;
- non-destructive supersession;
- no cross-partition supersession;
- explicit stale or superseded state;
- protection against a stale snapshot masquerading as current; and
- historical Provider evidence after supersession.

Provider tokens, exchange tokens, symbols, and row positions shall not establish globally permanent Provider Record Identity or canonical Instrument identity.

Submission Unit identity shall not create canonical Instrument identity, cross-partition permanence, cross-snapshot permanence, or cross-Provider identity equivalence.

Cross-Provider reconciliation remains Instrument-owned.

Kite, IBKR, and any future Provider shall remain isolated through separate Provider-and-Dataset Catalogue Partitions and may participate through the same governed EAIC contract family only where separately approved.

No direct Provider-to-Provider flow is created.

## Provenance and Evidence Flow

The flow preserves distinct evidence and provenance meanings:

| Evidence or provenance | Owner | Meaning |
|---|---|---|
| Provider acquisition provenance | Provider | Which Provider acquisition, operation, scope, result, snapshot, and records produced the Provider evidence. |
| EAIC-002 submission provenance | Provider at submission; preserved across the contract | Which eligible Submission Unit, contract version, authority, and Provider evidence were presented. |
| Instrument interpretation evidence | Instrument | Which admitted evidence supported the interpretation processing status and outcome. |
| Canonical identity evidence | Instrument | Which approved semantic evidence supported the canonical identity decision. |
| Provider mapping evidence | Instrument | Which evidence supported the Provider mapping status and any cross-Provider reconciliation. |

Acquisition request time, response receipt time, snapshot closure time, submission time, contract receipt time, contract validation time, interpretation admission time, interpretation processing time, canonical identity decision time, and Provider mapping decision time remain distinct.

Evidence may flow to Audit through approved read-only contracts without transferring ownership of the recorded meaning.

## Failure, Rejection, and Deferral Paths

The Instrument Master support flow is not a single success-or-failure path.

| Condition | Architectural path | Non-implication |
|---|---|---|
| Acquisition failure | Provider records the technical result and Acquisition Outcome; no success is invented. | Does not establish Submission Eligibility or Instrument failure. |
| Partial acquisition | Provider preserves Requested and Received Acquisition Scope and a Partial Acquisition Outcome. | Does not silently become complete acquisition; independently eligible records may remain separately assessable. |
| Structural invalidity | Provider records the applicable Provider Record Disposition. | Does not become Instrument invalidity. |
| Quarantine | Provider retains the Provider Record and quarantine meaning inside its Catalogue Partition. | Does not cross EAIC-002 while ineligible. |
| Submission Ineligibility | Provider records the exact ineligibility disposition and does not submit the affected unit. | Does not become contract rejection or Instrument interpretation outcome. |
| Contract rejection | Instrument-side contract handling records the bounded EAIC-002 result. | Does not begin Instrument interpretation or alter Provider meaning. |
| Interpretation rejection | Instrument records the applicable processing status and outcome after admission. | Does not retroactively invalidate receipt or Provider evidence. |
| Ambiguity | Instrument preserves ambiguity in the applicable interpretation, identity, or mapping dimension. | Does not invent canonical identity or equivalence. |
| Unsupported Provider vocabulary | Provider preserves the vocabulary and applicable disposition; Instrument may record a bounded unsupported outcome after admission. | Does not authorize inference from symbols, tokens, or product demand. |
| Canonical identity deferral | Instrument records the applicable non-establishment or not-evaluated meaning. | Does not imply Instrument non-existence or product ineligibility. |
| Provider mapping deferral | Instrument records Provider Mapping Status as `NOT_EVALUATED` or `MAPPING_PENDING`, as governed. | Does not invalidate canonical identity or create another Provider's mapping. |

## Explicit Product-Consumption Flow

Products consume only approved canonical Instrument outputs after Canonical Instrument Catalogue publication.

Swing consumption remains separate:

```text
Canonical Instrument Catalogue
        ↓
Swing Product-Consumption Contract
        ↓
Swing Universe and Swing Product Eligibility
        ↓
Swing Evidence, Validation Requirements, Decision Semantics, and Risk Interpretation
```

Intraday consumption remains separate:

```text
Canonical Instrument Catalogue
        ↓
Intraday Product-Consumption Contract
        ↓
Intraday Universe and Intraday Product Eligibility
        ↓
Intraday Evidence, Validation Requirements, Decision Semantics, and Risk Interpretation
```

Each future product requires its own explicit product-consumption boundary:

```text
Canonical Instrument Catalogue
        ↓
Future Product-Consumption Contract
        ↓
That Product's Universe and Product Eligibility
        ↓
That Product's Evidence, Validation Requirements, Decision Semantics, and Risk Interpretation
```

No product may consume Provider Catalogue records, Provider Snapshots, Provider Records, or EAIC-002 envelopes directly.

No product owns or writes canonical Instrument identity, canonical classification, Provider mapping, cross-Provider reconciliation, or Canonical Instrument Catalogue state.

Provider acquisition does not depend on Swing, Intraday, or future-product membership or demand.

## Instrument-to-Observation and Downstream Flow

Observation consumes canonical Instrument identity through the separately governed Instrument-to-Observation attribution boundary.

For an eligible instrument-specific candidate, the governed attribution boundary produces one Composite Observation Participation Boundary containing exactly:

- Observation Participation Eligibility; and
- its inseparably associated Eligible Candidate Factual Context.

Observation Participation Eligibility remains the sole attribution-admission meaning. Eligible Candidate Factual Context remains distinct factual meaning and does not acquire Observation ownership through eligibility or boundary crossing. The two constituents form one conceptual semantic boundary, not two independent domain flows.

The composite boundary creates no direct Provider → Observation dependency, carries no Provider Record, Provider Catalogue content, Provider Snapshot, Provider-native identifier, Submission Unit or EAIC-002 artefact, and authorizes no runtime path. Observation ownership of an accepted factual record begins only following separately governed Observation Acceptance.

Observation does not consume Provider-native records, Provider Catalogue content, Provider Snapshots, or EAIC-002 envelopes.

Provider acquisition and EAIC-002 submission do not create Observation authority.

Downstream ownership remains:

- Observation owns Observations, Observation History, Observation Evidence, and factual Market Facts;
- Market owns Market Schedule and approved exchange-availability meaning;
- Validation owns Validation Programmes, Validation Outcomes, and Business Judgment;
- Risk owns Risk Approval and Risk semantics;
- products own their bounded decision semantics and risk interpretation without acquiring Validation or Risk ownership; and
- Execution and Portfolio retain their existing approved responsibilities.

ADR-009 and EAIC-002 do not establish automatic Validation approval, Risk approval, execution authority, or a trading recommendation.

## Dataset Separation

EAIC-002 and the Provider-to-Instrument support flow in this document govern Instrument Master only.

They do not govern:

- Futures OI;
- Options OI;
- quotes;
- historical data;
- streaming;
- market depth;
- option-chain data; or
- any separately governed dataset.

Other market-data and product flows in this document remain separately governed and shall not be interpreted as extensions of the Instrument Master contract.

## Prohibited Direct-Write Paths

The following paths are prohibited:

- Provider → Instrument database;
- Provider → canonical Instrument record;
- Product → canonical Instrument identity;
- Observation → Provider Catalogue;
- Provider → product universe; and
- Provider → trading decision.

All cross-domain movement shall use an approved governed contract.

## Activation and Authority

This migrated DATA_FLOW document describes canonical architecture.

It does not:

- authorize runtime Provider-to-Instrument submission;
- authorize Provider endpoint invocation;
- authorize persistence;
- authorize implementation;
- authorize product activation; or
- execute coordinated migration.

The Instrument Master support path completed migration under [MIG-001](migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md) and activation under [CAR-003](../governance/reviews/CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md). EDD-004 Draft Preparation is authorized with constraints; runtime, endpoint, persistence, implementation, and product activation authorities remain absent.

## Existing Swing Product-Consumption and Decision Flow

This is a downstream Swing product-consumption and decision flow. It does not define Provider acquisition scope or a prerequisite for Instrument interpretation or canonical identity.

```text
MCX execution symbol + reference-market identity
  -> standardized primary/reference datasets
  -> market intelligence
  -> decision and readiness
  -> execution-context translation
  -> execution timing
  -> objective model-trade management
  -> confirmed execution alerts
  -> trader-facing display
```

Reference markets provide evidence. The MCX 1H chart owns the executable context.

### 1. Market Intelligence

```text
KR-200 Market Identification
  -> EAIC-001 Exchange Availability when explicitly publishable
  -> KR-250 Asset and Reference Mapping
  -> KR-260 Primary/Reference OHLCV
  -> KR-270 Indicators + KR-271 Math
  -> KR-275 Structure + KR-280 CPR
  -> KR-300 Trend
  -> KR-310 Quality
  -> KR-315 Compression
  -> KR-320 Acceptance
  -> KR-330 Momentum
  -> KR-340 Review Readiness
  -> KR-341 Consolidated Directional Bias
  -> KR-350 Opportunity
  -> KES (KRONOS Evidence Synthesis)
  -> KR-360 Confidence
```

Each intelligence engine answers one question and exposes public outputs. No individual indicator creates a trade.

KES collects, validates, standardizes, and packages that evidence before KR-360 Confidence. KES does not own evidence generation, confidence calculation, decisions, execution, trade management, alerts, or presentation.

### 2. Decision

KR-370 consumes governed current Native and same-run post-Review public evidence before producing one versioned analytical-promotion state:

- NO SETUP;
- POTENTIAL BUY SETUP;
- POTENTIAL SELL SETUP;
- BUY READY;
- SELL READY;
- BUY NOW;
- SELL NOW.

KR-370 owns analytical promotion. Its BUY NOW / SELL NOW means only that all governed KR-370 promotion criteria are satisfied; it is not an Entry Outcome and grants no execution, Risk, Sponsor-decision, position, fill, or broker authority. KR-370 consumes governed public facts and does not recreate raw timeframe engines. Exact current BUY NOW / SELL NOW alone may establish eligibility for Step 31. READY, POTENTIAL, and NO SETUP remain analytical only.

```text
Native PROBABLE + same-run V3 Review
  -> KR-370 analytical promotion
  -> versioned state, reason, criteria, and authority declaration
  -> exact BUY NOW / SELL NOW only: Step-31 eligibility
```

### 3. Execution Context

KR-380A is a narrow adapter. It translates the minimum reference and execution facts needed by KR-380:

- Reference Daily directional permission;
- Reference 4H acceptance/compression readiness;
- Reference 1H momentum support;
- MCX 1H chart/context readiness;
- precise internal blockers for later trader-readable translation.

```text
KR-260/270 narrow reference datasets
  + prior public direction/readiness context
  -> KR-380A public adapter contract
  -> KR-380
```

KR-380A does not create separate Daily, 4H, and 1H copies of the intelligence core. The exception is governed by [ADL-003](ADL-003-Execution-Context-Adapters.md).

### 4. Execution Timing

KR-380 acts only after exact KR-370 analytical promotion complete, immutable Step-31 geometry, DOMAIN-007 Risk permission, and the existing governed timing inputs are valid.

```text
KR-370 BUY NOW  + long geometry + Risk -> FORMING / EXTENDED / FAILED / LONG_ENTRY_TRIGGERED
KR-370 SELL NOW + short geometry + Risk -> FORMING / EXTENDED / FAILED / SHORT_ENTRY_TRIGGERED
Other KR-370 states                         -> no Step-31 progression
Invalid/missing downstream authority        -> NO_TRIGGER / fail closed
```

Final LONG_ENTRY_TRIGGERED, SHORT_ENTRY_TRIGGERED, EXTENDED, and FAILED outcomes retain the existing confirmed timing/context requirements. KR-380 cannot infer direction, reverse KR-370, upgrade incomplete analytical promotion, change Step-31 geometry, or bypass Risk.

KR-380 also publishes an ordered blocker queue. KR-705 translates that queue into trader-readable Need, Next, and Then rows.

### 4A. Observation-Phase Sponsor Branch

[ADR-0015](adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
adds a prospective evidence branch without changing the objective flow:

```text
exact KR-370 BUY NOW / SELL NOW
  -> Step-31 factual mathematics + availability + warnings
  -> DOMAIN-007 facts/state where evaluable
  -> explicit Sponsor LIVE / PAPER / IGNORE observation choice
  -> immutable decision-time snapshot
  -> linked observation/research evidence

valid geometry + APPROVED/CONSTRAINED Risk + qualified context
  -> independent KR-380 / KR-390 objective progression

hard Risk / integrity / context blocker
  -> no prohibited downstream activation
  -> no rewrite of KR-370 or Sponsor choice
```

The Sponsor branch and objective branch remain separate. A Step-31 warning is
evidence, not Sponsor choice. A recorded choice is not a Sponsor Position,
Entry Outcome, model trade, order, or fill. IGNORE creates no Sponsor Position;
objective evidence remains observable wherever the independent objective path
has every required valid input.

### 4B. Blocked-PAPER Observation Track

[ADR-0016](adr/ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md)
adds a prospective, explicitly started research-evidence path without changing
DOMAIN-007, the objective branch, or Sponsor Position activation:

```text
immutable PAPER decision + exact Step-31 observation evidence
  -> DOMAIN-007 separately determines Sponsor Position activation

activation permitted
  -> existing PAPER Sponsor Position lifecycle
  -> one Sponsor-decision Research Ledger row

activation blocked + explicit START PAPER OBSERVATION
  -> non-position Paper Observation Track
  -> governed factual market observations
  -> bounded Track outcome or explicit unavailability
  -> relationship on the same Sponsor-decision Research Ledger row
```

The Track retains exact Entry as an observation reference and exact Stop,
Target, invalidation, warnings, and severity. It never repairs geometry,
creates a position, activates KR-380/KR-390, infers a fill, calculates P&L or
actual R, changes LIVE authority, or calls a broker. An activated PAPER
position and a Paper Track cannot both count as independent observations for
the same decision.

### 5. Model Trade Management

KR-390A supplies the narrow confirmed structure reference required for the initial and managed model stop. It uses completed MCX 1H execution bars and does not duplicate KR-275.

KR-390 starts a new current model trade only from an exact Version 2 KR-380 `LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED` Entry Outcome with valid geometry and Risk binding. Historical Version 1 trigger records remain restorable but cannot create a new current model trade.

```text
NO TRADE
  -> confirmed LONG_ENTRY_TRIGGERED / SHORT_ENTRY_TRIGGERED
  -> HOLD
  -> PROTECT at qualifying progress
  -> TRAIL from confirmed structure
  -> EXIT on confirmed managed-stop breach

Invalid entry/stop data
  -> INVALIDATED
```

The model trade persists after KR-380 returns to NO TRIGGER. New triggers are ignored while a model trade is active. Managed risk must never loosen.

KR-390 tracks the objective KRONOS model trade whether or not the user personally entered. See [ADL-004](ADL-004-Model-Trade-Ownership.md).

### 6. Alerts

KR-400 consumes versioned KR-380 Entry Outcomes only and defines two current alert types:

- KRONOS ENTRY TRIGGERED — LONG;
- KRONOS ENTRY TRIGGERED — SHORT.

The alert event fires only on the transition into the confirmed trigger state. A persistent trigger state must not produce duplicate alerts on later calculations.

```text
new KR380_LONG_ENTRY_TRIGGERED edge  -> KRONOS ENTRY TRIGGERED — LONG alert
new KR380_SHORT_ENTRY_TRIGGERED edge -> KRONOS ENTRY TRIGGERED — SHORT alert
KR-370 analytical transition         -> no KR-400 entry alert
all other states                     -> no alert
```

TradingView handles alert creation, mobile push, and delivery. KRONOS places no broker order. See [ADL-005](ADL-005-Alert-Architecture.md).

### 7. Trader Display

KR-705 consumes public outputs and presents:

- explicit Exchange Availability from EAIC-001 when available;
- trend, quality, acceptance, momentum, compression, opportunity, and confidence;
- KR-390 model-trade status in the Risk row;
- KR-380 versioned Entry Outcome in the Entry row;
- KR-370 analytical-promotion state in the Decision row;
- the most relevant decision or execution blockers in Need, Next, and Then;
- core data status.

KR-705 translates and displays. It does not calculate trading intelligence.

EAIC-001 Exchange Availability flows from KR-200 to KR-705 for presentation only. KR-705 must not infer exchange availability from market-data availability, stale bars, readiness failures, Execution Context availability, or missing confirmed candles. Exchange Availability does not alter KR-370 decisions, KR-380 execution timing, KR-380A Execution Context production, ECPC payloads, alerts, trade management, or market-data readiness.

### Reference Charts Versus Execution Chart

| Context | Role | May issue a current KR-380 MCX Entry Outcome? |
|---|---|---:|
| COMEX/NYMEX Daily | Strategic/reference support | No |
| COMEX/NYMEX 4H | Structure, acceptance, compression support | No |
| COMEX/NYMEX 1H | Momentum/timing support | No |
| MCX 1H | Self-contained execution venue | Yes, after KR-370 analytical promotion, Step-31 geometry, Risk, and confirmed KR-380 timing |

Reference charts may expose their own analytical states for diagnostics, but they cannot issue an MCX executable trigger.

### Self-Contained MCX Execution Rule

On MCX 1H, every remaining blocker must be available in the same panel in trader language. The trader should not need to open COMEX merely to discover why execution is pending.

The source of a blocker may be reference Daily, reference 4H, reference 1H, or MCX 1H. Its presentation must describe the required market behavior, not leak internal engine naming. This decision is recorded in [ADL-002](ADL-002-MCX-Self-Contained-Execution.md).

## Swing V1 Step-32 Approved Data Flow — 2026-08-13

Trade Candidate → Business Judgment → Risk Result → Entry Outcome → Objective Model Trade → Lifecycle Event. Kite Connect WebSocket market data → KRONOS Provider adapter → validated Monitoring Submission → DOMAIN-002 governed Observation → KR-380/KR-390. Optional Kite order updates follow a separate Provider evidence path into Sponsor Position only. Sponsor Decision and Sponsor Position remain parallel to objective history. Rejected transport evidence never enters the business flow; missing/ambiguous evidence fails closed. TradingView/Pine active monitoring and public webhook ingress are retired/not required. See [monitoring architecture](products/swing/SWING-V1-STEP-32-MONITORING-ARCHITECTURE.md).
