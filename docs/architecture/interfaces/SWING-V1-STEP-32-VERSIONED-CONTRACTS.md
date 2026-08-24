# Swing V1 Step 32 — Versioned Interface Contracts

**Status:** Approved
**Version:** 1.3
**Approval date:** 2026-08-13
**Owner / approved by:** Chief Architect
**Implementation:** ADR-0013 commissions the exact Native DOMAIN-007 V1, ECPC V2, KR-380 V2, persistence/restoration, and KR-390 handoff; all other expansion remains unauthorized

All identities are immutable and all timestamps are timezone-aware. Contract identity/version, provenance, integrity, binding, and lifecycle applicability are mandatory. Unsupported versions, malformed identity/digest, binding mismatch, ambiguity, or unavailable mandatory evidence fail closed. Availability is expressed only as `AVAILABLE`, `UNAVAILABLE`, or `NOT_APPLICABLE`; absence is never converted into a fact.

## ADR-0015 observation-phase boundary

[ADR-0015](../adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
authorizes versioned contracts for Step-31 observation evidence and future
Sponsor observation decisions. The Step-31 evidence contract below preserves individual
Entry/Stop/Target/invalidation/risk/reward/R:R availability, exact mathematics,
warning identities, hard-blocker identities, DOMAIN-007 facts/state, and an
immutable decision-time snapshot.

Recording Sponsor `LIVE`, `PAPER`, or `IGNORE` observation choice is distinct
from activating a Sponsor Position or objective model. Risk `REJECTED` or
`UNAVAILABLE`, invalid lineage/integrity, invalid execution context, or another
existing hard blocker continues to prevent every downstream effect that
requires that authority. A geometry warning alone does not become an `IGNORE`
decision. Existing contract records and meanings below remain unchanged.
SPONSOR-OBS-01 is not implemented by the Step-31 evidence contract.

## KRONOS-SWING-STEP31-OBSERVATION-EVIDENCE-V1

- **Policy:** `SWING-STEP31-OBSERVATION-PHASE-V1`.
- **Semantic owner / producer:** Step-31 Trade Construction.
- **Consumers:** Trade Window presentation, Audit, and the bounded future
  SPONSOR-OBS-01 handoff only.
- **Eligibility:** exact current KR-370 `BUY_NOW` or `SELL_NOW` plus the
  existing exact UX-05 handoff. Other KR-370 states remain ineligible.
- **Mandatory lineage:** run, canonical instrument, Native assessment,
  opportunity, direction, KR-370 handoff identity/integrity, V3/V3.1
  Readiness identity/integrity, evidence-package identity/integrity,
  canonical execution-context identity, policy/version, observation boundary,
  provenance, created time, and record integrity.
- **Factual mathematics:** Entry, Stop, Target, invalidation, risk, reward, and
  R:R each retain their exact safely established value and availability.
  Negative or zero risk/reward is retained as factual mathematics; R:R is
  calculated only when both risk and reward are positive.
- **Warnings:** `TARGET_BELOW_ENTRY`, `TARGET_ABOVE_ENTRY`,
  `NON_POSITIVE_REWARD`, `NON_POSITIVE_RISK`, `RR_UNFAVOURABLE`,
  `TARGET_UNAVAILABLE`, `STOP_UNAVAILABLE`, `ENTRY_UNAVAILABLE`, and
  `STRUCTURAL_GEOMETRY_WARNING`. A producer emits only warnings justified by
  existing approved mathematics; this contract creates no threshold.
- **Presentation:** severity `GREEN|AMBER|RED` and geometry status
  `COMPLETE_FAVOURABLE|COMPLETE_WARNING|INCOMPLETE_WARNING` are explanatory
  only. `HARD_UNAVAILABLE` is reserved for fail-closed processing and is not
  persisted as a successful observation.
- **Conventional-plan linkage:** a valid existing
  `KRONOS-SWING-V1-TRADE-PLAN-RECORD-V0` remains unchanged and is linked when
  its strict geometry succeeds. Warning or incomplete evidence is never
  promoted into that Trade Plan contract.
- **Hard failures:** stale/foreign run, instrument, assessment, handoff, or
  evidence; identity/integrity mismatch; malformed inputs; and untrusted or
  incomplete canonical execution context fail closed without an observation
  record.
- **Persistence:** immutable, append-only, exact-binding restoration. Older
  Trade Plans and unavailable records are not reinterpreted.
- **Authority:** advisory geometry evidence only. No Risk, Sponsor-decision,
  Sponsor-position, Entry Outcome, model, order, fill, broker, or autonomous
  trading authority.

## KRONOS-KR-370-ANALYTICAL-PROMOTION-V1

- **Semantic owner / producer:** KR-370 / DOMAIN-003 Validation.
- **Consumers:** Step-31 eligibility and approved presentation only.
- **States:** `BUY_NOW|SELL_NOW|BUY_READY|SELL_READY|POTENTIAL_BUY_SETUP|POTENTIAL_SELL_SETUP|NO_SETUP`.
- **Mandatory:** owner identity, state-family identity `KR370_ANALYTICAL_PROMOTION`, contract identity/version, exact current Native run/candidate/assessment and V3 Review bindings, direction, boundaries, evidence identities, freshness, provenance, integrity, and created time.
- **Lifecycle:** immutable analytical promotion for one exact current reviewed Native Probable. Only exact current `BUY_NOW` / `SELL_NOW` may establish eligibility for Step 31.
- **Authority:** no execution, Risk, Sponsor-decision, position, fill, model, alert, quantity, order, or broker authority.

## KRONOS-KR-380-ENTRY-OUTCOME-V2

- **Semantic owner / producer:** KR-380 / DOMAIN-004 Execution.
- **Consumers:** KR-390, KR-400, Browser, Audit, and approved lifecycle orchestration.
- **States:** `NO_TRIGGER|FORMING|LONG_ENTRY_TRIGGERED|SHORT_ENTRY_TRIGGERED|EXTENDED|FAILED`.
- **Mandatory:** owner identity, state-family identity `KR380_ENTRY_OUTCOME`, contract identity/version, candidate and KR-370 promotion bindings, immutable Step-31 geometry, Risk permission, monitoring/Observation and Execution Context bindings, timing result, provenance, integrity, and created time.
- **Lifecycle:** current entry-timing outcome. Triggered states are analytical Entry Outcomes, not fills or broker orders.
- **Isolation:** owner/family/version mismatch fails closed. KR-370 analytical promotion cannot satisfy this contract.

## KRONOS-KR-380-ENTRY-OUTCOME-V1 — historical compatibility

- **Semantic owner:** KR-380 / DOMAIN-004 Execution.
- **States:** `NO_TRIGGER|FORMING|BUY_NOW|SELL_NOW|EXTENDED|FAILED`.
- **Status:** historical, immutable, read-only/restorable; not emitted by current producers.
- **Lifecycle:** original Entry Outcome meaning is preserved. Restoration cannot create a new current model trade, alert, Sponsor position, or broker action.

The complete state-family contract and machine-readable registry are
[published separately](KR-370-KR-380-STATE-FAMILY-CONTRACTS.md).

## KRONOS-SWING-V1-BUSINESS-JUDGMENT-V1

- **Semantic owner:** DOMAIN-003 Validation.
- **Producer:** approved Swing Validation component/adapter.
- **Consumers:** DOMAIN-007 Risk and approved Swing orchestration.
- **Mandatory:** `business_judgment_id`, `contract_identity`, `contract_version`, `trade_candidate_id`, candidate contract identity/version/digest, `validation_identity`, `readiness_identity`, `run_id`, `market_data_boundary`, freshness, integrity, `created_at`, provenance.
- **Conditional:** canonical instrument, product, setup and direction echoes; when present they must exactly equal the candidate.
- **Lifecycle:** immutable judgment for one current candidate/run. It carries no geometry and grants no Risk or execution authority.

## KRONOS-SWING-V1-RISK-APPROVAL-V1

- **Semantic owner / producer:** DOMAIN-007 Risk.
- **Consumers:** Swing candidate lifecycle, KR-380, Sponsor Decision/Position projection.
- **Mandatory:** `risk_result_id`, contract identity/version, candidate and judgment identities/digests, `run_id`, result (`APPROVED|CONSTRAINED|REJECTED|UNAVAILABLE`), evaluated time, validity/currentness, provenance, integrity.
- **Conditional:** maximum quantity, notional, capital risk, margin, exposure, concentration, reason codes; each carries availability.
- **Lifecycle:** valid only for the bound current candidate/run. It cannot alter geometry.
- **ADR-0013 conformance:** the Native V1 producer also binds the exact UX-05 handoff, Step-31 plan, Portfolio State cycle, policy version, evaluation boundary, and integrity SHA. Quantity and numerical portfolio optimization remain unavailable.

## KRONOS-SWING-PORTFOLIO-STATE-V1

- **Semantic owner / producer:** DOMAIN-005 Portfolio factual-state publisher.
- **Consumer:** DOMAIN-007 V1 only.
- **Mandatory:** contract identity/version, cycle identity, as-of boundary, complete-source status and identities, objective-model and Sponsor-position exposure facts, provenance, integrity.
- **Lifecycle:** immutable current-state cycle. Supersession invalidates Risk results bound to the older cycle. Missing sources cannot be represented as empty.
- **Authority:** no Risk decision, optimization, quantity, order, fill, or broker authority.

## KRONOS-SWING-V1-SPONSOR-DECISION-V1

- **Semantic owner / producer:** Swing Sponsor Decision responsibility / Sponsor action.
- **Consumers:** Swing orchestration and DOMAIN-005 Sponsor Position.
- **Mandatory:** `sponsor_decision_id`, contract identity/version, candidate/run/Risk binding, revision, decision time, mode (`LIVE|PAPER|IGNORE`), current/frozen status, provenance, integrity.
- **Conditional:** Sponsor explanation and bounded intended quantity. `NO_DECISION_RECORDED` is represented by no contract, never as a mode.
- **Lifecycle:** revisable only before Entry while all bindings remain current; frozen at Entry; no retrospective relabel.
- **ADR-0015 compatibility:** existing V1 records retain this exact mandatory
  Risk/geometry binding. SPONSOR-OBS-01 must use an explicitly versioned
  observation-phase record rather than weakening or reinterpreting V1.

## KRONOS-SWING-V1-SPONSOR-POSITION-V1

- **Semantic owner:** DOMAIN-005 Sponsor Position representation.
- **Producer:** approved Sponsor-position recorder; LIVE facts require explicit actual evidence.
- **Consumers:** Browser, Event notification, Step 33.
- **Mandatory:** `sponsor_position_id`, contract identity/version, candidate/model binding as applicable, mode (`LIVE|PAPER`), position state, evidence identity, timestamps, provenance, integrity.
- **Conditional:** quantity, actual entry/exit, costs, actual P&L, actual R, manual-exit evidence, each with availability.
- **Lifecycle:** separate from objective model. IGNORE/no decision creates no Sponsor position. Sponsor changes never mutate model history.

## KRONOS-SWING-V1-MONITORING-SUBMISSION-V1 — transport amended

- **Semantic owner:** Swing Product Architecture.
- **Producer:** KRONOS Kite Provider market-data adapter from one normalized WebSocket tick.
- **Consumer:** DOMAIN-002 admission boundary.
- **Semantic status:** factual Provider submission only.
- **Mandatory:** contract identity/version, `submission_id`, `candidate_id`, `monitoring_binding_id`, canonical and provider instrument, product, direction, submission type, observed-price availability, reference, `observed_at`, boundary/timeframe/session, Provider source/connection/provenance, continuity flags, payload digest.
- **Conditional:** `model_trade_id` after activation, observed price, source sequence.
- **Types:** `ENTRY_LEVEL_CROSSED`, `STOP_LEVEL_CROSSED`, `TARGET_LEVEL_CROSSED`, `DAILY_BOUNDARY_CLOSED`, `DATA_UNAVAILABLE`.
- **Lifecycle:** only an active binding may be admitted. No Observation, lifecycle, execution, broker, or decision authority.
- **Supersession:** Pine identity/build/hash, alert configuration, webhook publisher, and public-ingress fields are retired from the active Swing V1 monitoring transport. Public webhook is not required.

## KRONOS-SWING-V1-MONITORING-OBSERVATION-V1

- **Semantic owner / producer:** DOMAIN-002 Observation after admission.
- **Consumers:** KR-380 and KR-390.
- **Mandatory:** contract identity/version, `observation_id`, source submission identity/digest, candidate/binding, canonical/provider instrument, product, observation type, price availability, observed/received/admitted times, market/session/boundary, Kite Provider provenance, freshness, integrity.
- **Conditional:** `model_trade_id` after activation, observed/reference price, ordered source sequence.
- **Lifecycle:** governed fact only; cannot declare Entry, closure, invalidation, staleness, or Event meaning.

## Optional Kite order-update evidence

Kite order-update evidence is Provider factual evidence for `KRONOS-SWING-V1-SPONSOR-POSITION-V1`; it is not a ninth lifecycle-authority contract. It carries order identity, status, filled quantity, average/fill information when authoritative, timestamps, governed instrument, side, Provider provenance, candidate binding, and Sponsor Decision binding. Missing/ambiguous current order state remains explicit. It cannot enter KR-380/KR-390 or mutate objective model history.

## KRONOS-SWING-V1-LIFECYCLE-EVENT-V1

- **Semantic owner / producer:** DOMAIN-009 Event, from authoritative source-domain outcomes.
- **Consumers:** Browser, notification, Audit, Step 33.
- **Mandatory:** contract identity/version, `event_id`, event type, candidate identity, source domain/outcome identity, occurred/published times, canonical instrument/product, provenance, integrity.
- **Conditional:** `model_trade_id` after activation and Sponsor-position/action references where applicable.
- **Types:** `SWING_ENTRY_TRIGGERED`, `SWING_MODEL_TRADE_CLOSED`, `SWING_RECONCILIATION_REQUIRED`, `SWING_LIVE_ACTION_REQUIRED`, `SWING_DATA_UNAVAILABLE`. A current `SWING_ENTRY_TRIGGERED` binds only to KR-380 Version 2 `LONG_ENTRY_TRIGGERED` / `SHORT_ENTRY_TRIGGERED`, never to KR-370 promotion.
- **Lifecycle:** publication only; DOMAIN-009 performs no calculation and creates no broker authority.

## KRONOS-SWING-V1-TRADE-OUTCOME-V1

- **Semantic owner / producer:** KRONOS Analytics — Trade Journal capability (Step 33).
- **Consumers:** approved journal/learning views; Audit consumes trace identifiers only.
- **Mandatory:** `trade_outcome_id`, contract identity/version, candidate and model identities, canonical instrument/product/direction/setup, model outcome state and close reason, model-entry availability/value, model-exit availability/value, model-R availability/value, Sponsor decision history reference, Sponsor-position availability/reference, actual outcome/entry/exit/quantity/P&L/R availability, model-vs-actual deviation availability, completeness status, unresolved reasons, source contract identities, provenance, integrity, learning annotations.
- **Lifecycle:** eligible only when objective state is `MODEL_TRADE_CLOSED` for `STOP`, `TARGET`, `ANALYTICAL_INVALIDATION`, or `OUTCOME_UNRESOLVED`. Missing Sponsor evidence does not block model integration and remains explicit.
- **Prohibitions:** cannot rewrite history, retune policy, change geometry/readiness, fabricate actuals, or automatically grant Production authority.
