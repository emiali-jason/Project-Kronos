# Research-First Engineering Roadmap

**Status:** Draft
**Owner:** Chief Architect
**Approved By:** Not approved
**Date:** 2026-07-22

## Purpose

Propose a gated engineering sequence for a research-first KRONOS Discover capability while preserving approved Platform Domain ownership and excluding automated order placement.

This roadmap is not implementation authority. EP scope may proceed only when its listed architecture gate is satisfied.

## Proposed Operating Flow

```text
Kite through Provider
  -> Instrument and Market context
  -> historical, volume, and OI observations
  -> reproducible research evidence
  -> opportunity discovery
  -> Validation-owned candidate ranking and explanation
  -> TradingView-assisted human review
  -> Human Trading Decision
```

Risk, automated Execution, and Portfolio automation are outside the active roadmap. Their approved ownership remains unchanged.

## Roadmap Rules

- Small initial operating scope must not reduce scalable architectural capability.
- Provider-specific objects stay inside Provider.
- Instrument Identity, Market Schedule, Market Facts, and Business Judgment retain their approved owners.
- Research artefacts do not become architecture, production facts, or business judgment automatically.
- No EP may invent a cross-domain payload while its interface contract is unresolved.
- No EP may introduce BUY/SELL rules, thresholds, parameter optimization, or automated orders.
- Infrastructure must remain proportionate to measured need; distributed systems are not an initial requirement.

## EP-004 — Minimum Read-Only Kite Connectivity

### Outcome

Establish a narrow Provider-internal capability to verify read-only Kite connectivity and provider availability.

### Domain trace

- Provider owns external integration.
- Configuration supplies approved runtime configuration.

### Architecture gate

May proceed under existing approved Provider and Configuration boundaries if it remains internal to Provider.

### Required boundaries

- No Market Facts publication.
- No SDK-specific object outside Provider.
- No market-data persistence.
- No candidate discovery or ranking.
- No orders, order endpoints, or broker execution.
- Authentication/session mechanics, if required for connectivity, must remain limited to the approved technical scope and must not create business semantics.

## EP-005 — Scalable Instrument-Master Foundation

### Outcome

Establish a scalable Instrument-owned foundation for relevant Futures contracts, Cash instruments, Options instruments and chains, provider mappings, expiries, rollover relationships, and future provider independence.

### Domain trace

- Instrument owns identity and relationships.
- Provider may supply external reference material without owning Instrument Identity.
- Market retains schedule semantics.

### Architecture gate

Requires an approved Instrument-consumer contract or approved contract profile before the master is exposed across domains or products.

### Scalability requirements

- Support a small initial universe without encoding a one-instrument design.
- Preserve stable identity across provider symbols and contract rollover.
- Distinguish Futures, Cash, and Options research coverage from execution eligibility.
- Permit additional market-data providers without changing business identity.

## EP-006 — Historical Candle and OI Acquisition

### Outcome

Acquire read-only historical price, volume, and open-interest data for approved instruments and timeframes through Provider, then make attributable Market Facts available through Observation.

### Domain trace

- Provider owns acquisition integration.
- Instrument supplies identity.
- Market supplies authoritative schedule context where approved.
- Observation owns published Market Facts.

### Architecture gate

Blocked until a provider-neutral Provider-to-Observation acquisition interface and applicable Instrument/Market consumption boundaries are approved.

### Scalability requirements

- Multiple timeframes and long historical ranges.
- Contract expiry and rollover awareness.
- Rate-limit and retry behavior that does not alter fact semantics.
- Incremental acquisition without losing provenance.
- Provider-neutral facts suitable for reproducible research.

## EP-007 — Research Data Persistence and Incremental Updates

### Outcome

Preserve reproducible datasets and update them incrementally without changing the semantic ownership of their contents.

### Domain trace

- Observation retains ownership of Market Facts.
- Persistence, dataset lifecycle, and replay orchestration ownership are unresolved.

### Architecture gate

Blocked pending Chief Architect approval of platform responsibility, dataset identity, provenance, retention, correction, replay, and contract boundaries.

### Scalability requirements

- Reproducible dataset versions and source provenance.
- Explicit completeness, availability, and correction history.
- Incremental updates and deterministic re-runs.
- Futures expiry and rollover continuity.
- Cash and Options dataset distinctions.
- Multiple timeframes and long ranges.
- Additional providers without rewriting business consumers.
- Parallel acquisition only after measurement justifies it.

## EP-008 — Futures, Cash, and Options Universe Scanning

### Outcome

Coordinate approved Instrument, Market, and Observation outputs to identify evidence-bearing opportunities across supported research universes.

### Domain trace

- Proposed KRONOS Discover product capability owns orchestration only.
- Instrument owns universe identity.
- Market owns schedule meaning.
- Observation owns Market Facts.
- Validation owns business interpretation.

### Architecture gate

Blocked until ADR-0001 and KRONOS Discover product responsibilities and interfaces are approved.

### Scalability requirements

- Avoid one-instrument control flow.
- Support Futures contracts, Cash instruments, and Options chains as distinct research universes.
- Preserve multi-timeframe evidence and dataset provenance.
- Respect rate limits and partial availability without inventing facts.
- Permit bounded parallelism only when safe and justified.

## EP-009 — Opportunity Evidence and Candidate Ranking

### Outcome

Create explainable candidate evidence and publish Validation-owned comparative Business Judgment for candidate presentation.

### Domain trace

- Observation supplies factual evidence.
- Validation owns interpretation and ranking meaning.
- Discovery coordinates presentation but owns no independent ranking logic.

### Architecture gate

Blocked until candidate evidence, Validation ranking, explainability, and presentation-consumer contracts are approved.

### Required boundaries

- No new BUY/SELL rules.
- No thresholds or optimization in this roadmap.
- No ranking based on provider-private objects.
- Every candidate retains Instrument Identity, fact provenance, observation scope, Validation ownership, and known limitations.
- Ranking must not duplicate or silently redefine KR-370 direction/readiness.

## EP-010 — TradingView-Assisted Validation Workflow

### Outcome

Present approved candidate evidence for visual chart review and an explicit discretionary human decision.

### Domain trace

- TradingView is a presentation and visual-review interface.
- Source domains retain their meanings.
- Human action is external to the Platform Domain model.
- Workflow-record ownership remains unresolved.

### Architecture gate

Blocked until TradingView presentation, human-consumption, validation-record, and audit boundaries are approved.

### Required boundaries

- No TradingView automation.
- No hidden human step that completes a domain responsibility.
- No mutation of Market Facts or Business Judgment.
- No automated Risk, Execution, Portfolio, or order path.
- Human review outcome must not be represented as an approved domain contract without a separate decision.

## Explicitly Deferred Work

- Automated broker order placement before 2028.
- Execution activation from Discovery candidates.
- Personal position and broker-fill tracking.
- Options execution strategies.
- Trading thresholds and parameter optimization.
- Automated TradingView control.
- Distributed acquisition or storage infrastructure without measured need.
- A new Research Platform Domain without a separately demonstrated semantic boundary.

## Sequencing and Approval Gates

| EP | May begin? | Required approval before broader implementation |
| --- | --- | --- |
| EP-004 | Conditionally yes | Stay Provider-internal and read-only. |
| EP-005 | Foundation work only | Instrument consumer contract before cross-domain use. |
| EP-006 | No | Provider-neutral acquisition and Instrument/Market/Observation contracts. |
| EP-007 | No | Persistence, provenance, incremental-update, and replay ownership. |
| EP-008 | No | ADR-0001 and Discovery product architecture. |
| EP-009 | No | Validation ranking and presentation contracts. |
| EP-010 | No | TradingView, human-consumption, record, and audit boundaries. |

## Roadmap Validation

Before each EP starts:

1. Confirm the owning approved domain or product responsibility.
2. Confirm every dependency is authorized through an approved contract.
3. Confirm unresolved ownership has not been decided by implementation.
4. Confirm the EP does not alter KR-370, KR-380, KR-390, or KR-400 ownership.
5. Confirm no automated order placement is introduced.
6. Confirm small-scope acceptance criteria do not create a throwaway architecture.
7. Record reproducibility and provenance requirements before data work begins.

## Related Draft Materials

- [Architecture Impact Assessment](RESEARCH_FIRST_ARCHITECTURE_IMPACT_ASSESSMENT.md)
- [ADR-0001 — Research-First Product Mandate and Execution Deferral](../../adr/ADR-0001-research-first-product-mandate.md)
