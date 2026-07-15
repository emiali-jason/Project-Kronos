# AC-004 — Confirmation Must Represent Meaningful Information

> Unapproved research candidate. Validation is required before architecture acceptance.

## Candidate Metadata

- Candidate ID: AC-004
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-004](../extracted-principles/EP-004-shared-data-is-not-independent-confirmation.md)
- Created Date: 2026-07-15
- Lifecycle Status: VALIDATION REQUIRED
- Validation Queue: [VQ-001](../validation-queue/VQ-001-meaningful-information-confirmation.md)

## Underlying Problem

Multiple transformations or descriptions of the same underlying price data can appear to provide independent confirmation even when they contain substantially overlapping information.

## Proposed Principle

Independent confirmation should require meaningfully distinct information. Future information architecture should classify evidence by its underlying source so that repeated transformations are not automatically counted as independent confirmation.

No evidence taxonomy, formula, weighting, or threshold is proposed here.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Questions whether widely available indicators add distinct decision value. | Conceptual explanation; personal experience | Does not measure information overlap. |
| YT-007 | Shows how multiple chart descriptions can arise from the same price history. | Chart examples; personal experience | Does not establish independence criteria. |

## Validation Required

- Determine how underlying information sources can be identified at an architecture level.
- Review statistical and information-theoretic evidence without adopting a formula at this stage.
- Test whether the distinction improves validation and avoids false confirmation.

## Review Outcome

- Status: VALIDATION REQUIRED
- Acceptance: Not granted
