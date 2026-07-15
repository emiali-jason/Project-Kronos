# Research Lifecycle

## Governing Pipeline

```text
Source
  -> Research Note
  -> Extracted Principle
  -> Architecture Candidate
  -> Architecture Review
  -> Validation
  -> Accepted Principle
```

No stage may be skipped. Advancement means that the next artefact may be created; it does not approve the prior source wholesale.

## Stage Responsibilities

### Source

Preserve provenance, availability, publication context, and source artefact status. A source creates hypotheses, not truth.

### Research Note

Separate verified facts, observed behaviour, speaker interpretation, personal opinion, claims, evidence classifications, non-architectural content, and open questions. A note may link to many topics and extracted principles.

### Extracted Principle

State one concise, source-faithful proposition that may describe market behaviour, a decision problem, or a governance concern. Extraction is not endorsement. Each principle must retain source traceability, evidence strength, limitations, and disconfirming questions.

### Architecture Candidate

Translate an extracted principle into a technology-neutral, parameter-free proposition for architecture review. It may not specify indicators, thresholds, entries, exits, formulas, or implementation logic.

### Architecture Review

Evaluate responsibility boundaries, assumptions, evidence independence, conflicts, failure modes, and validation feasibility. Review does not grant acceptance.

### Validation

Test a candidate using evidence and methods appropriate to the claim. Every candidate must enter the validation queue before acceptance, including candidates believed to be obvious.

### Accepted Principle

Record only a principle that has completed independent review, validation, and explicit approval. Acceptance applies to the exact principle and scope, never to an entire source or research note. Accepted does not mean implemented.

## Research Note Status

```text
COLLECTED -> STRUCTURED
```

- `COLLECTED`: provenance and available source material recorded.
- `STRUCTURED`: required evidence separation and assessment completed.

## Principle and Candidate Status

- Extracted principles: `EXTRACTED`, `REVIEWED`, or `REJECTED`.
- Architecture candidates: `ARCHITECTURE REVIEW`, `VALIDATION REQUIRED`, `ACCEPTED`, or `REJECTED`.
- Validation queue items: `QUEUED`, `IN REVIEW`, `VALIDATED`, or `FAILED VALIDATION`.

## Prohibited Transitions

- Source directly to architecture candidate.
- Research note directly to accepted principle.
- Candidate directly to accepted principle without a validation-queue record.
- Accepted principle directly to production without the separate architecture and production change process.
