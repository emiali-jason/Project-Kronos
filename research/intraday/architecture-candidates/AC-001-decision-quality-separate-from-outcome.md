# AC-001 — Decision Quality Must Be Separate From Outcome

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-001
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-001](../extracted-principles/EP-001-decision-quality-and-outcome-are-distinct.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Supporting Extracted Principles

- [EP-001 — Decision Quality and Outcome Are Distinct](../extracted-principles/EP-001-decision-quality-and-outcome-are-distinct.md)

## Underlying Problem

A profitable outcome can follow an invalid decision, while a losing outcome can follow a valid decision made under uncertainty. Outcome alone cannot establish decision quality.

## Proposed Principle

KRONOS should evaluate whether a decision was valid using information and authority available at decision time, independently of whether the outcome was profitable or losing.

Future review should consider whether the audit vocabulary must distinguish:

- valid decision, profitable outcome
- valid decision, losing outcome
- invalid decision, profitable outcome
- invalid decision, losing outcome
- execution failure
- position-management failure

These are provisional classification needs, not a final data model.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Separates uncertain decisions from hindsight and the desire to be right. | Personal experience; conceptual explanation | No independent validation. |
| YT-007 | Separates possessing rules from executing them and win rate from economic outcome. | Personal experience; anecdote | Examples are not a controlled study. |

## Validation Required

- Review decision-science and audit literature.
- Test whether reviewers can classify decision validity without outcome leakage.
- Examine ambiguity between decision, execution, and position-management failure.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
