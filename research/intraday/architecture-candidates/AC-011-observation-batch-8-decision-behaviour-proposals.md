# AC-011 — Observation Batch 8 Decision Behaviour Proposals

> Draft repository proposal. Not an Architecture Decision Record, approved architecture, implementation specification, trading rule, or authorisation to change KRONOS.

## Candidate Metadata

- Candidate ID: AC-011
- Title: Observation Batch 8 Decision Behaviour Proposals
- Originating Research IDs: Observation Batch 8
- Extracted Principle: None
- Created Date: 2026-07-16
- Owner: Architecture Librarian
- Lifecycle Status: DRAFT
- Independent Reviewer: Chief Architect review required
- Validation Queue ID: TBD

## Repository Proposal Status

These proposals are derived solely from repeated observed KRONOS engine behaviour. They must remain Draft until reviewed by the Chief Architect.

They do not modify approved architecture, product responsibilities, engine ownership, Pine logic, thresholds, confidence calculations, decision behaviour, execution behaviour, or presentation contracts.

## Proposal 1 — Suggested ADR: Confidence Engine Independence

### Suggested ADR Title

`ADR-XXXX-confidence-engine-independence.md`

### Rationale

Repeated observations indicate that Confidence behaves as an independent architectural decision component.

Multiple candidates reportedly exhibited:

- Bullish Trend.
- Healthy or Excellent Quality.
- Acceptance Confirmed.

while simultaneously reporting:

- Low Confidence.
- AVOID or WATCH decisions.

Examples observed:

- BPCL.
- Cummins India.
- Container Corporation.
- CDSL.
- Dixon Technologies, prior to BUY READY.
- Bharat Heavy Electricals.

### Draft Repository Recommendation

Document, subject to Chief Architect review, that Confidence is not assumed to be derived from Trend, Quality, and Acceptance unless an approved architectural document explicitly states otherwise.

### Initial Cross-Reference Review

- [ENGINE_STATUS.md](../../../docs/ENGINE_STATUS.md) records KR-360 Confidence as synthesizing public outputs from KR-341, KR-310, KR-315, KR-320, KR-330, KR-340, and KR-350.
- [ENGINE_OWNERSHIP.md](../../../docs/architecture/ENGINE_OWNERSHIP.md) records KR-360 as owning explainable confidence and not owning direction, entry timing, or decisions.
- [PLATFORM_GOVERNANCE.md](../../../docs/product/PLATFORM_GOVERNANCE.md) states Evidence -> Confidence -> Decision -> Execution.

Initial conflict assessment: no direct conflict found. This proposal should not be treated as an approved ADR until reviewed.

## Proposal 2 — Draft Decision State Machine

### Working Hypothesis

```text
WAIT
  -> Trend Alignment
  -> Acceptance
  -> Confidence Building
  -> Price Acceptance
  -> Compression
  -> BUY READY
  -> BUY
  -> Position Management
  -> EXIT
```

This is an observation-based hypothesis only. It should remain Draft until validated through additional market observations.

### Initial Cross-Reference Review

- [KR-370 Decision Engine](../../../docs/ENGINE_STATUS.md) is documented as deciding AVOID, WAIT, WATCH, BUY READY, or SELL READY.
- [KR-380 Execution Trigger Engine](../../../docs/ENGINE_STATUS.md) converts KR-370 READY states into confirmed timing states.
- [ADL-004 Model Trade Ownership](../../../docs/architecture/ADL-004-Model-Trade-Ownership.md) separates KR-370 direction/readiness, KR-380 trigger timing, and KR-390 model trade management.
- [KR-340 Decision Pipeline Metrics](../validation/KR-340-decision-pipeline-metrics.md) records decision inventory and transition flow as validation evidence.

Initial conflict assessment: potential terminology mismatch. Current approved documentation uses BUY READY / SELL READY and BUY NOW / SELL NOW in execution contexts, while this hypothesis uses BUY and EXIT. Any future ADR must align state names with KR-370, KR-380, and KR-390 contracts.

## Proposal 3 — Decision State Definitions

### Draft Scope

Create a repository document that formally defines every decision state used by KRONOS:

- WAIT.
- WATCH LONG.
- WATCH SHORT.
- BUY READY.
- BUY.
- SELL READY.
- SELL.
- AVOID.

These states are currently being inferred from observed engine behaviour. Formal definitions would improve consistency across Discovery, Swing, Intraday, Execution, and future products.

### Initial Cross-Reference Review

- [KR-370 Decision Engine](../../../docs/ENGINE_STATUS.md) currently documents AVOID, WAIT, WATCH, BUY READY, and SELL READY.
- [KR-380 Execution Trigger Engine](../../../docs/ENGINE_STATUS.md) documents BUY NOW, SELL NOW, NO TRIGGER, FORMING, FAILED, and EXTENDED execution states.
- [KR-390 Trade Management Engine](../../../docs/ENGINE_STATUS.md) owns model entry, stops, targets, and lifecycle flags after a confirmed trigger.

Initial conflict assessment: possible conflict if BUY and SELL are treated as KR-370 decision states. Current documentation appears to reserve executable timing for KR-380 as BUY NOW / SELL NOW rather than BUY / SELL. Future definitions should preserve engine ownership boundaries.

## Proposal 4 — Decision Gate Matrix

### Observation-Based Hypothesis

| Component | Promotion Authority |
|---|---|
| Trend | Yes |
| Acceptance | Yes |
| Confidence | Yes |
| Price Acceptance | Yes |
| Compression | Yes |
| Quality | Context Only |
| Momentum | Context Only |

This matrix is Draft and requires validation.

### Initial Cross-Reference Review

- [KR-710 Deterministic Explainability Spec](../../../docs/architecture/KR710_DETERMINISTIC_EXPLAINABILITY_SPEC.md) describes active blocker ownership, severity, category, and a conservative blocker precedence model.
- [ENGINE_OWNERSHIP.md](../../../docs/architecture/ENGINE_OWNERSHIP.md) identifies individual engine ownership boundaries.
- [KR-370 Decision Engine](../../../docs/ENGINE_STATUS.md) owns direction and readiness, not individual source engines independently promoting trades.

Initial conflict assessment: potential conflict if "Promotion Authority" is interpreted as direct decision ownership by source engines. Safer future wording may be "can block or support promotion through KR-370" rather than "has promotion authority."

## Proposal 5 — WATCH LONG Lifecycle Definition

### Observation-Based Hypothesis

```text
WATCH LONG
=
Trend Confirmed
+
Structure Confirmed
+
Risk Acceptable
+
Execution Not Yet Authorised
```

Observed behaviour suggests WATCH LONG represents a distinct lifecycle stage rather than a simple watchlist label.

### Initial Cross-Reference Review

- [KR-370 Decision Engine](../../../docs/ENGINE_STATUS.md) owns WATCH states as direction and readiness outputs.
- [KR-380 Execution Trigger Engine](../../../docs/ENGINE_STATUS.md) owns execution timing after READY, not WATCH.
- [KR-390 Trade Management Engine](../../../docs/ENGINE_STATUS.md) owns model trade management after confirmed triggers.

Initial conflict assessment: no direct conflict if kept as observed lifecycle language. The phrase "Risk Acceptable" may require review because risk governance and model trade management are separate responsibilities in existing architecture.

## Proposal 6 — BUY READY Promotion Criteria

### Observation-Based Hypothesis

Across reviewed observation batches, BUY READY has been exceptionally rare.

Current evidence suggests BUY READY is intentionally conservative and represents the final state before execution authorisation.

### Draft Repository Recommendation

Document BUY READY as a high-confidence pre-execution state only after formal criteria are approved by the Chief Architect.

### Initial Cross-Reference Review

- [KRONOS Platform Architecture](../../../docs/product/KRONOS_PLATFORM_ARCHITECTURE.md) states BUY READY and SELL READY are reserved for the final consolidated multi-timeframe KRONOS decision.
- [KR-370 Decision Engine](../../../docs/ENGINE_STATUS.md) owns BUY READY and SELL READY as decision readiness states.
- [KR-380 Execution Trigger Engine](../../../docs/ENGINE_STATUS.md) converts KR-370 BUY READY / SELL READY into confirmed execution timing states.
- [KR-340 Decision Pipeline Metrics](../validation/KR-340-decision-pipeline-metrics.md) exists to measure READY and NOW conversion behaviour over time.

Initial conflict assessment: no direct conflict. This proposal aligns with current READY-state conservatism, but it must not define criteria without approved architecture.

## Overall Conflict Summary

No approved architecture conflicts were found that prevent these items from being recorded as Draft repository proposals.

Items requiring careful future review:

- BUY / SELL terminology may conflict with current BUY NOW / SELL NOW execution-state language.
- "Promotion Authority" could conflict with KR-370 decision ownership if interpreted literally.
- WATCH LONG references to risk may need separation from trade-management and risk-governance responsibilities.
- Confidence independence should be formalized only through a reviewed ADR if future evidence supports it.

## Future ADR Path

If future observation batches continue to reinforce these patterns, recommended next steps are:

1. Create a Draft ADR for Confidence Engine Independence.
2. Create a Draft decision-state definition document or ADR that reconciles KR-370, KR-380, and KR-390 terminology.
3. Convert the Decision Gate Matrix into an explainability or blocker-contract proposal only if it preserves KR-370 as the Decision owner.

No direct architectural change should be made from this batch alone.
