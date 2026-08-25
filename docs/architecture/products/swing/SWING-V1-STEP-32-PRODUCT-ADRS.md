# Swing V1 Step 32 — Product Architecture Decisions

**Status:** Approved
**Version:** 1.1
**Approval date:** 2026-08-13
**Owner / approved by:** Chief Architect
**Engineering status:** Native V2 production path commissioned by ADR-0013; historical/intermediate implementation remains validation-only
**Operational authority:** PRODUCTION — exact ADR-0013 Native DOMAIN-007 V1 / ECPC V2 / KR-380 V2 / KR-390 path only

## S32-001 — Step-32 Product Orchestration

Swing orchestrates approved contracts; it is not a new engine. Candidate → DOMAIN-003 judgment → DOMAIN-007 Risk → objective monitoring. Sponsor Decision is a parallel branch. Accepted, Risk-permitted Entry activates the objective model whether the Sponsor chose LIVE, PAPER, IGNORE, or recorded no decision. A Sponsor position exists only for pre-entry LIVE/PAPER. Rejected or unavailable Risk prevents activation.

## S32-002 — Candidate / Pre-Entry Lifecycle

The explicit semantic owner is the **Swing V1 Trade Candidate Lifecycle responsibility**. States are `WAITING_FOR_RISK`, `WAITING_FOR_ENTRY`, `RISK_REJECTED`, `STALE`, `PRE_ENTRY_INVALIDATED`, and `RECONCILIATION_REQUIRED_PRE_ENTRY`. Risk owns Risk results; the candidate lifecycle owns staleness, invalidation evaluation, binding validity, and terminal pre-entry state; KR-380 owns Entry. KR-390 has no pre-entry authority. The candidate lifecycle ends when an accepted, Risk-permitted KR-380 outcome creates the model.

## S32-003 — Sponsor Decision

Modes are `LIVE`, `PAPER`, and `IGNORE`; `NO_DECISION_RECORDED` is absence, not a mode. Revision is allowed only before Entry while candidate, Risk, geometry, and run remain current, and freezes at Entry. No retrospective relabel is permitted. IGNORE and no decision affect only the Sponsor branch and never terminate objective monitoring.

## S32-004 — Risk Result Semantics

DOMAIN-007 produces `APPROVED`, `CONSTRAINED`, `REJECTED`, or `UNAVAILABLE`. Constraints may bound quantity, notional, capital risk, margin, exposure, and concentration. Risk never changes Entry, Stop, Target, thesis invalidation, direction, setup, or any Step-31 geometry.

## S32-005 — Position-Sizing Ownership

Portfolio owns capital, positions, and exposure; Configuration owns preferences; Instrument owns lot and multiplier; Provider/account sources own margin facts; DOMAIN-007 owns permission and maxima; Sponsor chooses actual quantity within constraints; DOMAIN-005 records the Sponsor position. No owner may absorb another's facts.

## S32-006 — Model vs Sponsor Position

The objective model and Sponsor LIVE/PAPER position have distinct identities, states, evidence, and histories. Sponsor action, omission, quantity, manual exit, or deviation never rewrites objective model Entry, Exit, closure reason, P&L availability, or R availability.

## S32-007 — PAPER Semantics

PAPER requires approved/constrained Risk and canonical geometry and must be chosen before Entry. It uses `MODEL_REFERENCE_ENTRY`, not a broker fill. Without a separately approved paper-accounting policy, monetary P&L, actual R, costs, and execution price remain `UNAVAILABLE`. Objective outcome remains measurable. A Sponsor manual PAPER exit changes only Sponsor PAPER history.

## S32-008 — LIVE Semantics

LIVE is Sponsor intent to act manually. It is not an order, fill, quantity, position, or broker acknowledgement. A LIVE Sponsor position activates only from explicit Sponsor evidence or future separately approved evidence. Broker execution authority remains `NONE`.

## S32-009 — Pre-Entry Monitoring Binding

Pre-entry monitoring binds `candidate_id` and `monitoring_binding_id`; `model_trade_id` exists only after activation. Monitoring begins when Risk permits, the candidate is current, integrity is valid, governed execution-instrument context is valid, and the Kite Provider subscription is active. Sponsor Decision is not required. Subscribe only for current monitoring responsibility; pre-entry subscriptions end on Entry, staleness, invalidation, Risk rejection, integrity failure, or supersession, and post-entry subscriptions end on model closure or unrecoverable outcome unless another active KRONOS responsibility still needs the instrument.

## ADR-0015 Observation-Phase Conformance

[ADR-0015](../../adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
prospectively distinguishes recording an explicit Sponsor observation-phase
choice from activating a Sponsor Position or objective model.

- A factual Step-31 geometry warning alone must not manufacture `IGNORE` or
  suppress recording the Sponsor's explicit `LIVE`, `PAPER`, or `IGNORE`
  observation choice.
- The decision-time evidence snapshot must retain individual geometry
  availability, warnings, Risk facts/state, and every current binding.
- `REJECTED` or `UNAVAILABLE` Risk, invalid integrity/lineage, invalid execution
  context, or another existing hard blocker still prevents every downstream
  effect that requires that authority.
- A recorded PAPER or LIVE observation choice creates no Sponsor Position,
  monitoring activation, objective Entry Outcome, model trade, order, or fill
  when its separately governed activation requirements are not satisfied.
- IGNORE creates no Sponsor Position and never terminates objective monitoring
  where the independent objective path is otherwise valid.

The existing Version 1 Sponsor Decision, Risk, Sponsor Position, and monitoring
records retain their historical meaning. STEP31-OBS-01 and SPONSOR-OBS-01 must
publish compatible prospective policy/contract versions before runtime use.

## ADR-0016 Paper Observation Track Conformance

[ADR-0016](../../adr/ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md)
prospectively supersedes only the prohibition on monitoring an exact blocked
`PAPER` decision when a separately identified non-position Paper Observation
Track is explicitly started. DOMAIN-007 remains hard for Sponsor Position and
objective activation. Activated PAPER uses the existing Sponsor Position
lifecycle as its primary outcome relationship; no duplicate Track is created.

The Track does not create KR-380 or KR-390 state, Sponsor Position, LIVE
authority, P&L, actual R, fill, order, or broker evidence. Historical Version 1
records retain their original meaning and are not backfilled.

## Prohibitions

No score, threshold, setup policy, geometry, broker authority, Pine decision authority, or automated execution authority is introduced. ADR-0013 authorizes only its exact Native production chain; all other Step-32 expansion remains unauthorized.
