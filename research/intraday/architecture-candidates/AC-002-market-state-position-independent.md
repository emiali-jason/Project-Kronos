# AC-002 — Market State Must Remain Position Independent

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-002
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-002](../extracted-principles/EP-002-position-can-bias-market-interpretation.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Underlying Problem

An existing position can create pressure to reinterpret ambiguous evidence in the direction that protects the position or its unrealised result.

## Proposed Principle

The Market State responsibility should classify available market evidence independently of position direction and unrealised profit or loss. It must not reinterpret evidence to defend an existing long or short position.

## Scope

- Potential relevance: Market State, Information Hierarchy, Explainability, Decision Audit.
- Excluded: market-state definitions, data inputs, thresholds, and implementation logic.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Claims forecasts and interpretations are biased by existing positions. | Personal experience; anecdotal example | Causal strength is unverified. |
| YT-007 | Describes confirmation-seeking in chart interpretation. | Conceptual explanation; chart examples | No independent comparison. |

## Validation Required

- Define how position independence could be assessed without prescribing implementation.
- Review conflicting evidence about legitimate position-aware risk and management responsibilities.
- Confirm that separation does not prevent Risk Authority or Position Management from using position information within their own scope.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
