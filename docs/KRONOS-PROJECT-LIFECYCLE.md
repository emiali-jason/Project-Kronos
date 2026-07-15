# KRONOS Project Lifecycle

## Purpose

KRONOS separates evidence gathering, design authority, validation, and engineering. This lifecycle is the project-wide path from an external input to production behaviour:

**Research → Observation → Architecture Candidate → Architecture Review → Validation → Approved Principle → Implementation Specification → Engineering → Testing → Production**

The Intraday Research Library has its own detailed [research lifecycle](../research/intraday/governance/research-lifecycle.md). That process feeds this project lifecycle but does not bypass architecture or validation governance.

## Lifecycle Stages

### 1. Research

Collect source material, summaries, hypotheses, and provenance in [`research/`](../research/). Research establishes what was said or discovered; it is not approval to change architecture or code.

### 2. Observation

Record a specific, reviewable behaviour or finding, including its context, evidence, limitations, and stable reference. Observations may originate in research or validation, but they do not prescribe a solution.

### 3. Architecture Candidate

Translate a supported principle into a proposed system responsibility, boundary, or information-flow rule. A candidate remains provisional, must retain its evidence links, and must not be represented as approved architecture.

### 4. Architecture Review

Evaluate the candidate against KRONOS constitutions, existing boundaries, ownership, failure modes, evidence quality, and compatibility with current behaviour. The review must explicitly accept, reject, revise, or defer the candidate.

### 5. Validation

Test the reviewed proposition through preserved observations, experiments, and evidence in [`validation/`](../validation/). Validation records expected-versus-actual behaviour and limitations; it does not directly alter production.

### 6. Approved Principle

Record a principle only after successful review and sufficient validation. Approval establishes design authority and traceability; it still does not constitute executable code.

### 7. Implementation Specification

Convert approved architecture into an engineering-ready specification with stable `SPEC-###` identity, scope, interfaces, invariants, acceptance criteria, and links to the approving decision and validation record.

### 8. Engineering

Implement the approved specification without inventing new architecture in code. Engineering artefacts belong to the implementation boundary and must preserve all frozen contracts and existing production behaviour outside the approved scope.

### 9. Testing

Verify syntax, contracts, expected-versus-actual behaviour, regressions, and specification acceptance criteria. Preserve the evidence required to reproduce or review the result.

### 10. Production

Release only reviewed and tested behaviour. A production change must remain traceable through its specification, approved architecture, validation evidence, and originating research or observation where applicable.

## Governing Rules

1. Research does not directly modify architecture.
2. An observation does not directly trigger an engineering change.
3. Architecture decisions require explicit review.
4. Validation evidence must be preserved.
5. Implementation follows architecture.
6. Production changes must remain traceable to approved design and validation.
7. Pine Script must not become the source of architectural truth.
8. Existing KRONOS Swing production behaviour must not be altered by this repository reorganisation.

## Authority Boundary

Folders describe responsibility; they do not confer approval. A document becomes authoritative only through the required review stage and an explicit status record. Research findings, candidates, drafts, archived material, and implementation details cannot silently become architecture.

