# Validation Policy

## Governing Rule

Every architecture candidate must have a validation-queue record before it can become an accepted principle. Validation is candidate-specific and scope-specific.

## Queue Entry Requirements

- Candidate ID and extracted-principle traceability
- Validation question
- Claim and responsibility boundary under test
- Required evidence categories
- Known conflicts and limitations
- Risks of false acceptance and false rejection
- Independence requirements
- Current convergence level and the evidence needed to change it
- Status and review owner when assigned

## Validation Standards

- Preserve information available at the relevant time.
- Avoid hindsight-dependent classification.
- Separate decision quality from realised outcome where applicable.
- Use evidence proportionate to the candidate's scope and consequence.
- Distinguish source repetition from independent corroboration.
- Treat convergence as evidence metadata, not as candidate acceptance or a substitute for validation.
- Record negative, ambiguous, and conflicting results.
- Do not select trading metrics, formulas, parameters, or thresholds in this governance document.

## Outcomes

- `VALIDATED`: stated candidate and scope are supported sufficiently for approval review.
- `FAILED VALIDATION`: evidence contradicts or fails to support the candidate.
- `INCONCLUSIVE`: evidence is insufficient or conflicting; the item remains unaccepted.
- `RETURN TO REVIEW`: the candidate definition or scope must change before further validation.

## Acceptance Gate

Validation alone does not create an accepted principle. Explicit architecture approval must reference the validation record, exact candidate version, scope, limitations, and any continuing conditions.

## Preservation

Validation observations belong in [`../validation-observations/`](../validation-observations/). Queue status belongs in [`../validation-queue/`](../validation-queue/). Failed and rejected records must remain traceable.
