# Swing V1 Step 32 — Platform Architecture Amendments

**Status:** Approved
**Version:** 1.0
**Approval date:** 2026-08-13
**Decision owner / approved by:** Chief Architect
**Scope:** Platform extension for Swing V1 Step 32
**Engineering status:** Architecture activated; implementation not authorized
**Operational authority:** SHADOW / VALIDATION ONLY

These amendments extend, and do not silently rewrite, the existing Platform architecture. Repository activation does not grant runtime, Pine, webhook, or broker-execution authority.

## P32-001 — DOMAIN-003 Swing Business Judgment

DOMAIN-003 Validation is the sole semantic owner of Swing Business Judgment. An approved Swing Validation component or adapter may produce `KRONOS-SWING-V1-BUSINESS-JUDGMENT-V1`; production does not transfer ownership. The judgment binds immutably to a Trade Candidate by identity, version, digest, validation identity, readiness identity, run, market-data boundary, freshness, integrity, creation time, and provenance. Optional instrument, product, setup, or direction echoes must exactly equal the candidate; mismatch fails integrity. Geometry is never duplicated.

## P32-002 — DOMAIN-004 / KR-380 Swing Entry Timing

Step 31 owns trade geometry; KR-380 owns when canonical Entry occurs. KR-380 consumes immutable candidate identity/digest, Entry, direction, Risk permission, monitoring binding, and governed Observation/Execution Context qualification. It cannot change geometry, direction, or setup, and cannot infer a fill. An accepted Entry produces an Execution Outcome transition. Execution Context Provider supplies qualification/translation only and owns no instrument, tick, precision, price, session, or geometry fact.

`MODEL_REFERENCE_ENTRY_PRICE` equals canonical Step-31 Entry only when consecutive accepted, authoritatively ordered observations in a continuously monitored eligible session prove the candidate was armed, the prior price was on the pre-entry side, the next price was at/beyond Entry in the required direction, no missing interval or session-opening gap spans Entry, and order is deterministic. Otherwise the result is `RECONCILIATION_REQUIRED_PRE_ENTRY` and no model trade activates unless separately approved evidence reconstructs the crossing before staleness. This is analytical accounting, never a fill or Sponsor-position claim.

## P32-003 — DOMAIN-005 Swing Objective Model Trade

KR-390 / DOMAIN-005 begins only after an accepted, Risk-permitted KR-380 Entry Outcome. It consumes immutable geometry and never recomputes it. Persistent states are `MODEL_TRADE_ACTIVE`, `RECONCILIATION_REQUIRED`, and `MODEL_TRADE_CLOSED`; close reasons are `STOP`, `TARGET`, `ANALYTICAL_INVALIDATION`, and `OUTCOME_UNRESOLVED`. Entry and exit are events. Legacy `HOLD`, `PROTECT`, and `TRAIL` semantics are not inherited.

## P32-004 — DOMAIN-005 Sponsor LIVE/PAPER Position

Sponsor LIVE/PAPER Position is a separate contract and history from the objective model. Modes are `LIVE` and `PAPER`; neither may mutate the model. LIVE facts require explicit Sponsor or separately approved broker evidence. PAPER follows the approved PAPER semantics. Every actual-position field uses `AVAILABLE`, `UNAVAILABLE`, or `NOT_APPLICABLE` and missing evidence is never fabricated.

## P32-005 — DOMAIN-002 External Monitoring Submission Admission

The governed path is Pine publisher → authenticated ingress → transport/schema/binding validation → DOMAIN-002 admission → governed Observation. A transport-valid payload is only an untrusted factual submission. Rejection is audit evidence only and cannot become an Observation, lifecycle conclusion, or event.

## P32-006 — DOMAIN-005 / KR-390 Post-Entry Observation Consumption

KR-390 consumes accepted Observations and alone derives the objective lifecycle. Observations may establish Stop/Target crossings, completed Daily boundaries, and data unavailability, but sources cannot declare lifecycle conclusions. Ordering ambiguity, missing intervals, or reconstruction mismatch fail closed into reconciliation or unresolved outcome; no price, order, or conclusion is manufactured.

## P32-007 — DOMAIN-009 Swing Lifecycle Events

DOMAIN-009 publishes, but does not calculate, authoritative outcomes as `SWING_ENTRY_TRIGGERED`, `SWING_MODEL_TRADE_CLOSED`, `SWING_RECONCILIATION_REQUIRED`, `SWING_LIVE_ACTION_REQUIRED`, and `SWING_DATA_UNAVAILABLE`. Events derive only from source-domain outcomes and never acquire calculation, broker, or Sponsor-position authority.

## P32-008 — Ownership and dependency extension

The authoritative extension is:

```text
Swing Trade Candidate
  → DOMAIN-003 Business Judgment
  → DOMAIN-007 Risk Result
  → KR-380 Entry Outcome
  → KR-390 Objective Model Trade
  → DOMAIN-009 Lifecycle Event

TradingView/Pine
  → untrusted Monitoring Submission
  → authenticated ingress
  → DOMAIN-002 governed Observation
  → KR-380/KR-390
```

Instrument retains mapping, tick, precision, lot, multiplier, and execution-instrument identity. Observation retains prices and crossings. Market retains session, calendar, and availability. Portfolio retains capital, position, and exposure. Risk retains permission and constraints. Audit remains read-only. Dependencies authorize contract consumption only and never transfer ownership.

## Extension relationship

These P32 records extend the approved Domain Ownership Matrix, Domain Dependency Matrix, KR-380, KR-390, Execution Context Provider, and Domain event architecture. Where earlier generic wording conflicts with the explicit Step-32 crossing, pre-entry, or model/Sponsor separation rules, this approved extension controls for Swing V1 Step 32 while preserving the historical record.
