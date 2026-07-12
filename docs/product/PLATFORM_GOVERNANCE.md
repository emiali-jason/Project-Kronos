# KRONOS Platform Governance

**Status:** Approved
**Date:** 2026-07-12

## Governance Principles

1. One engine owns one responsibility.
2. Evidence engines do not make trading decisions.
3. KR-370 remains the sole Decision owner.
4. Analysis and execution are separate.
5. New ideas enter as evidence before receiving authority.
6. Observation and validation precede Confidence or Decision integration.
7. Architecture changes require a recorded decision.
8. Frozen contracts are not changed casually.
9. Market-specific routing belongs in configuration or adapters, not intelligence engines.
10. The market is the final reviewer.

## Canonical Flow

```text
Configuration
-> Market Data Routing
-> Market Data Retrieval
-> Normalization
-> Evidence
-> KES
-> Confidence
-> Decision
-> Execution
-> Trade Management
-> Alerts
-> Presentation
```

## KES Boundary

KES (KRONOS Evidence Synthesis)

**Responsibility:** Collect, validate, standardize, and package evidence before KR-360 Confidence.

KES does not own:

- evidence generation;
- confidence calculation;
- decisions;
- execution;
- management;
- alerts;
- presentation.

KES is an architectural synthesis boundary over existing evidence contracts. It does not change engine numbering or runtime ownership.

## Evolution Rule

```text
Research
-> Architecture
-> Evidence
-> Observation
-> Validation
-> Confidence Integration
-> Decision Integration
-> Production
```

Authority increases only after the preceding stage is documented and supported by appropriate evidence. Production integration must preserve existing ownership and release-governance rules.
