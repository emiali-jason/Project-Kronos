# AC-005 — Historical Appearance Is Not Live Executability

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-005
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-005](../extracted-principles/EP-005-retrospective-visibility-does-not-prove-live-executability.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Underlying Problem

A concept may appear clear after the event while depending on hindsight, selective examples, or information that was not usable at decision time.

## Proposed Principle

Before architectural relevance is considered, a concept should face separate review for:

- precise definition
- observability at decision time
- hindsight independence
- repeatability
- live executability
- outcome-independent classification

These are review dimensions, not pass thresholds or implementation tests.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Describes competing narratives and retrospective pattern perception. | Personal experience; conceptual explanation | Limited operational detail. |
| YT-007 | Directly contrasts attractive historical chart signals with live monitoring and execution difficulty. | Personal experience; chart examples | No documented systematic test. |

## Validation Required

- Review hindsight and selection-bias controls.
- Establish whether contemporaneous evidence can be preserved and independently assessed.
- Examine repeatability across reviewers and market conditions without defining parameters here.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
