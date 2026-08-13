# Swing V1 Step 32 — Monitoring Architecture

**Status:** Approved
**Version:** 1.0
**Approval date:** 2026-08-13
**Owner / approved by:** Chief Architect
**Runtime implementation:** Not authorized
**Operational authority:** SHADOW / VALIDATION ONLY

## Governed path

```text
authorized TradingView/Pine publisher
  → untrusted factual Monitoring Submission
  → authenticated loopback-independent HTTPS ingress
  → transport/schema/security/binding checks
  → DOMAIN-002 admission
  → governed Observation
  → KR-380/KR-390 evaluation
  → DOMAIN-009 lifecycle Event
```

The architecture is distinct from the paused Step-30 pre-trade webhook and does not activate or adopt that implementation.

## MCX monitoring context

The canonical Swing identity remains the approved MCX analytical subject; lifecycle crossings use only its governed current MCX execution instrument. Provider Foundation/Instrument resolution owns the expiring contract mapping. COMEX/NYMEX or other reference instruments may provide separately governed context but cannot trigger Entry, Stop, Target, invalidation, or closure. Mapping changes fail closed into reconciliation and never silently remap an active binding. No MCX 1H assumption enters the common lifecycle semantics.

## NSE monitoring context

Lifecycle crossings use the explicitly governed NSE execution instrument. An analytical identity is not automatically the execution instrument. Sector indices, NIFTY, BANKNIFTY, or another reference instrument cannot trigger an individual-equity lifecycle event. Instrument identity, exchange, tick/precision, product, session, and provider mapping must match the active binding.

## Ingress and security

Ingress is HTTPS with TLS 1.2 or stronger, publisher authentication using high-entropy protected credentials, rotation with governed overlap, strict JSON/schema validation, bounded payload size, rate limiting, and loopback-independent deployment controls. Logs and diagnostics exclude credentials, broker/OpenAI secrets, tokens, and raw sensitive payloads. Authentication failures, accepted submissions, and rejected submissions remain auditable. Public reachability grants no semantic or Production authority.

## Replay, idempotency, and ordering

The deterministic submission identity and payload digest govern replay. Identical duplicates are idempotent. Conflicting duplicates are retained, rejected from authority, and flagged. Order uses authoritative timestamps and then source sequence when available; otherwise it is unknown. Out-of-order or stale evidence may be stored for audit but cannot regress current lifecycle state. Wrong contract, candidate, binding, model, instrument, product, publisher, Pine build/hash, or alert configuration fails closed.

## Missed-delivery reconciliation

Webhook absence is not proof of market state. A missing/unavailable interval that could affect Entry or outcome creates reconciliation. Entry is not activated across such an interval. Approved finer-grained evidence may reconstruct the crossing before candidate staleness. Stop/Target ambiguity remains reconciliation; irrecoverable ambiguity closes as `OUTCOME_UNRESOLVED`. Neither AI inference, receipt ordering, nor a later price manufactures the missing sequence.

## Alert binding and lifecycle

The Sponsor manually creates TradingView alerts from KRONOS-produced instructions, identifiers, templates, and checklists. No automated alert creation is authorized. A pre-entry binding requires current candidate, Risk permission, valid integrity, governed execution instrument, and authorized publisher/configuration. The binding ends on Entry, stale, invalidated, Risk rejected, integrity failure, or supersession. Post-entry association adds `model_trade_id` and ends at model closure or unrecoverable outcome. Inactive alerts are rejected and audited.

## Persistence, restart, and recovery

Durable owners retain candidate, Business Judgment, Risk result, Sponsor revisions, candidate lifecycle/binding, Execution Outcome, objective model, Sponsor position, raw/validated/rejected ingress records, governed Observations, Events, and Audit evidence. Restart loads contracts, validates identity/integrity/version, replays accepted Observations deterministically, and compares the reconstructed projection with stored state. Equality permits normal authority; mismatch or missing intervals require reconciliation. Irrecoverable ambiguity becomes unresolved. Restart never silently resumes or manufactures state.

## Crossing and gap semantics

Model Entry uses canonical Step-31 Entry only under the consecutive accepted-observation rule in P32-002. A first eligible session observation beyond Entry, session-opening gap, missing interval, or nondeterministic order does not activate a model. Gap through Stop closes the model as STOP without manufacturing an execution price; gap through Target never assumes favorable improvement. If both are crossed and authoritative order is unknown, reconciliation is required; bar high/low alone is insufficient. Analytical invalidation is derived by KRONOS from accepted completed-Daily Observation and immutable Step-31 invalidation condition.

## Exit authority

Pine is factual submission only; DOMAIN-002 is governed fact only; KR-380 owns Entry timing/outcome; KR-390 owns objective model exit; DOMAIN-009 publishes/notifies. PAPER default position closure may project from model closure, while manual PAPER exit affects Sponsor history only. LIVE model closure produces a Sponsor action notification only. LIVE actual/manual exit belongs to Sponsor evidence. Broker execution authority is `NONE`.
