# AC-007 — Risk Governance and Profit Management Are Separate Responsibilities

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-007
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-007](../extracted-principles/EP-007-loss-authority-and-profit-management-address-different-problems.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Underlying Problem

Loss authority and continuation management address different decision problems and may be obscured if treated as a single responsibility.

## Proposed Principle

Initial loss acceptance, maximum exposure, and invalidation response belong to Risk Governance. Continuation, reduction, and profit realisation belong to Position Management.

The source claim that fixed profit targets are universally wrong is explicitly rejected as a universal principle. This candidate does not choose a profit-management method.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Discusses different emotional and decision problems around adverse and favourable positions. | Personal experience | Does not establish responsibility boundaries. |
| YT-007 | Separates known loss exposure from uncertain favourable continuation and questions fixed targets. | Personal method; unsupported generalisation | Personal practice is not universal evidence. |

## Validation Required

- Review whether the proposed separation improves authority clarity and auditability.
- Identify legitimate interactions without defining stop, reduction, or realisation logic.
- Test against alternative responsibility boundaries.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
