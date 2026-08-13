# Swing V1 Step 32 — Versioned Interface Contracts

**Status:** Approved
**Version:** 1.0
**Approval date:** 2026-08-13
**Owner / approved by:** Chief Architect
**Implementation:** Not authorized

All identities are immutable and all timestamps are timezone-aware. Contract identity/version, provenance, integrity, binding, and lifecycle applicability are mandatory. Unsupported versions, malformed identity/digest, binding mismatch, ambiguity, or unavailable mandatory evidence fail closed. Availability is expressed only as `AVAILABLE`, `UNAVAILABLE`, or `NOT_APPLICABLE`; absence is never converted into a fact.

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

## KRONOS-SWING-V1-SPONSOR-DECISION-V1

- **Semantic owner / producer:** Swing Sponsor Decision responsibility / Sponsor action.
- **Consumers:** Swing orchestration and DOMAIN-005 Sponsor Position.
- **Mandatory:** `sponsor_decision_id`, contract identity/version, candidate/run/Risk binding, revision, decision time, mode (`LIVE|PAPER|IGNORE`), current/frozen status, provenance, integrity.
- **Conditional:** Sponsor explanation and bounded intended quantity. `NO_DECISION_RECORDED` is represented by no contract, never as a mode.
- **Lifecycle:** revisable only before Entry while all bindings remain current; frozen at Entry; no retrospective relabel.

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
- **Types:** `SWING_ENTRY_TRIGGERED`, `SWING_MODEL_TRADE_CLOSED`, `SWING_RECONCILIATION_REQUIRED`, `SWING_LIVE_ACTION_REQUIRED`, `SWING_DATA_UNAVAILABLE`.
- **Lifecycle:** publication only; DOMAIN-009 performs no calculation and creates no broker authority.

## KRONOS-SWING-V1-TRADE-OUTCOME-V1

- **Semantic owner / producer:** KRONOS Analytics — Trade Journal capability (Step 33).
- **Consumers:** approved journal/learning views; Audit consumes trace identifiers only.
- **Mandatory:** `trade_outcome_id`, contract identity/version, candidate and model identities, canonical instrument/product/direction/setup, model outcome state and close reason, model-entry availability/value, model-exit availability/value, model-R availability/value, Sponsor decision history reference, Sponsor-position availability/reference, actual outcome/entry/exit/quantity/P&L/R availability, model-vs-actual deviation availability, completeness status, unresolved reasons, source contract identities, provenance, integrity, learning annotations.
- **Lifecycle:** eligible only when objective state is `MODEL_TRADE_CLOSED` for `STOP`, `TARGET`, `ANALYTICAL_INVALIDATION`, or `OUTCOME_UNRESOLVED`. Missing Sponsor evidence does not block model integration and remains explicit.
- **Prohibitions:** cannot rewrite history, retune policy, change geometry/readiness, fabricate actuals, or automatically grant Production authority.
