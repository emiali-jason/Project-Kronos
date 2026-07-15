# AC-006 — Behavioural Compliance Is Part of System Performance

> Unapproved research candidate. Not an architecture decision or implementation specification.

## Candidate Metadata

- Candidate ID: AC-006
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-006](../extracted-principles/EP-006-rule-compliance-affects-realised-system-performance.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Supporting Extracted Principles

- [EP-006 — Rule Compliance Affects Realised System Performance](../extracted-principles/EP-006-rule-compliance-affects-realised-system-performance.md)

## Underlying Problem

A defined decision process cannot be evaluated solely from stated rules if actual actions deviate from their authorisation.

## Proposed Principle

KRONOS should make authorised and unauthorised actions explicit across the trade lifecycle, including:

- entry authorisation
- additional exposure
- risk reduction
- stop changes
- exit requirements
- re-entry restrictions
- deviations from the authorised decision

The candidate identifies governance responsibilities only; it does not define any trading action or rule.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Describes recurring failure to act consistently with intended loss and profit behaviour. | Personal experience | Human anecdotes do not automatically map to an automated engine. |
| YT-007 | Separates knowing rules from executing them under uncertainty. | Personal experience; attributed practitioner statement | No formal compliance model is supplied. |

## Validation Required

- Determine which lifecycle deviations are decision, execution, risk, or position-management concerns.
- Review whether explicit authorisation improves auditability without conflating system and operator behaviour.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
