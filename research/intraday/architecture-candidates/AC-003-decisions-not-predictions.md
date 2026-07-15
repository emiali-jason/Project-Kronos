# AC-003 — KRONOS Makes Decisions, Not Predictions

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-003
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-003](../extracted-principles/EP-003-decisions-operate-under-uncertainty.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Supporting Extracted Principles

- [EP-003 — Decisions Operate Under Uncertainty](../extracted-principles/EP-003-decisions-operate-under-uncertainty.md)

## Underlying Problem

Claims of directional certainty can obscure uncertainty, authorisation boundaries, and invalidation responsibilities.

## Proposed Principle

KRONOS should deterministically describe the market state, evidence, authorisation, invalidation, and required action. It should not claim certainty about future price movement.

This candidate concerns responsibility and explanation only. It does not define states, actions, or trading logic.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Emphasises uncertainty and the bias embedded in forecasts. | Personal experience; conceptual explanation | Does not establish a complete decision architecture. |
| YT-007 | Frames trading as repeated uncertain opportunities rather than a perfect predictive system. | Personal experience; unsupported opinion | No empirical comparison of prediction and decision formulations. |

## Validation Required

- Review whether decision-oriented descriptions improve clarity and auditability.
- Identify possible conflicts where probabilistic forecasts are legitimate evidence inputs.
- Ensure the candidate does not prohibit uncertainty estimates while rejecting claims of certainty.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
