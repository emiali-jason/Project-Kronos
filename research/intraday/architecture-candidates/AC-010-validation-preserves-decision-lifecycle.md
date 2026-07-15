# AC-010 — Validation Must Preserve the Entire Decision Lifecycle

> Unapproved research candidate. Not an architecture decision, audit schema, or implementation specification.

## Candidate Metadata

- Candidate ID: AC-010
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-010](../extracted-principles/EP-010-lifecycle-provenance-is-needed-to-attribute-failure.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Supporting Extracted Principles

- [EP-010 — Lifecycle Provenance Is Needed to Attribute Failure](../extracted-principles/EP-010-lifecycle-provenance-is-needed-to-attribute-failure.md)

## Underlying Problem

Outcome-only records cannot reveal whether failure arose from information, classification, decision, authority, execution, or position management.

## Proposed Principle

Future validation review should consider whether the audit model must preserve:

- information available at the time
- market-state classification
- decision issued
- authorised risk
- actual execution
- deviations
- position-management decisions
- exit reason
- outcome
- post-trade decision-quality assessment

This list expresses research-level traceability needs, not a final schema.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Highlights hindsight, competing narratives, and behavioural deviation. | Personal experience; conceptual explanation | Does not provide an audit model. |
| YT-007 | Highlights live executability, rule compliance, and outcome distribution. | Personal experience; anecdote | Does not demonstrate the proposed lifecycle record. |

## Validation Required

- Review audit completeness, provenance, and decision-quality literature.
- Determine whether each proposed element is necessary and sufficient.
- Examine privacy, complexity, ambiguity, and false-attribution risks without selecting implementation details.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
