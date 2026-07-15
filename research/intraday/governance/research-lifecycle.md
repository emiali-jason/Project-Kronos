# Research Lifecycle

## Executive Rule

KRONOS uses linked lifecycles, not one status chain from source collection to production. A source may support zero, one, or many extracted principles, and a principle may support zero, one, or many architecture candidates. Source review, research synthesis, architecture governance, and production delivery therefore have different artefacts, owners, and approval authority.

The Research Library governs source review and research synthesis. It records architecture-candidate traceability and validation state, but it does not grant production authority. Engineering, live validation, and production remain outside this library.

## Complete Lifecycle Map

```text
SOURCE RECORD (availability and standing; independent of review progress)
ACTIVE | SUPERSEDED | WITHDRAWN | UNAVAILABLE

SOURCE REVIEW
COLLECTED -> REVIEWED -> STRUCTURED
     \-> REVIEW_BLOCKED -> REVIEWED

RESEARCH SYNTHESIS
STRUCTURED source(s) -> EP EXTRACTED -> EP REVIEWED | EP REJECTED

ARCHITECTURE GOVERNANCE
REVIEWED EP(s) -> AC: ARCHITECTURE REVIEW
               -> AC: VALIDATION REQUIRED
               -> ARCHITECTURE APPROVAL
               -> ACCEPTED PRINCIPLE | REJECTED

EXTERNAL DELIVERY — NOT RESEARCH-LIBRARY STATUS
Approved architecture -> ENGINEERING -> LIVE VALIDATION -> PRODUCTION
```

Movement to a downstream track permits creation or review of a new artefact. It does not transform the upstream source into that artefact and does not approve the source wholesale.

## Why the Proposed Single Chain Is Not Adopted

The proposed chain correctly identifies important gates, but it should not be a single source lifecycle:

- A source is never an architecture candidate; candidates are separately identified propositions derived through extracted principles.
- One source can produce no principles or candidates, while one candidate can depend on many sources.
- `ENGINEERING`, `LIVE VALIDATION`, and `PRODUCTION` describe delivery state, not research maturity.
- A source may be superseded or become unavailable without changing the review or validation history of propositions already extracted from it.
- Architecture approval and production authority belong to governance processes outside source review.

## Source Status

Source Status records the standing of the registered source independently of how far its review has progressed.

| Status | Meaning |
| --- | --- |
| `ACTIVE` | The source record is current and remains eligible to support research. |
| `SUPERSEDED` | A newer edition, version, or authoritative source replaces it; historical traceability is retained. |
| `WITHDRAWN` | The source was deliberately removed from active support, with the reason recorded. |
| `UNAVAILABLE` | The source cannot currently be accessed or verified; existing provenance and review history are retained. |

Collection references such as playlists are indexed as `COLLECTION_REFERENCE`, not as research sources. Source Status is not an evidence-quality rating.

## Source Review Stages

### COLLECTED

- **Purpose:** Register the source without inferring its contents or conclusions.
- **Entry criteria:** A stable Research ID exists; title or identifying description, source type, provenance, collection date, and source or artefact location are recorded to the extent available.
- **Exit criteria:** The usable source has been substantively reviewed in full or to a clearly declared boundary; claims, limitations, unavailable material, and review scope have been inventoried.
- **Deliverables:** Index entry, source manifest or transcript status when applicable, initial note shell, and provisional evidence profile.
- **Architecture Candidates:** May not be created at this stage.

### REVIEW_BLOCKED

- **Purpose:** Make an access, language, rights, corruption, or source-completeness blocker explicit without pretending that review occurred.
- **Entry criteria:** A `COLLECTED` record exists and the blocker, attempted access path, and affected review scope are documented.
- **Exit criteria:** The blocker is resolved and substantive review is completed, or the Source Status is changed to `UNAVAILABLE` or `WITHDRAWN` with rationale.
- **Deliverables:** Blocker statement, affected artefacts, attempted resolution, and next review action.
- **Architecture Candidates:** May not be created at this stage.

### REVIEWED

- **Purpose:** Confirm that the available source has been substantively consumed and its contents understood before formal structuring.
- **Entry criteria:** `COLLECTED` requirements are complete; the usable source has been reviewed to a declared boundary; reviewer and review date are recorded.
- **Exit criteria:** Required note sections are populated; facts, observations, source interpretation, reviewer opinion, claims, conflicts, limitations, topics, and traceability are separated; the evidence profile is assessed rather than provisional.
- **Deliverables:** Review scope, review record, claim inventory, limitations, open questions, and any review notes needed for structuring.
- **Architecture Candidates:** May not be created at this stage.

### STRUCTURED

- **Purpose:** Produce a normalized, searchable research note suitable for comparison and synthesis.
- **Entry criteria:** `REVIEWED` requirements are complete and the current research-note template has been applied.
- **Exit criteria:** The note passes completeness and link checks; topic links, evidence metadata, related research, and any existing EP references resolve; unsupported sections are explicitly marked rather than inferred.
- **Deliverables:** Completed research note, assessed evidence profile, source and topic index entries, transcript or source-manifest references, and related-research links.
- **Architecture Candidates:** May not be created directly. A structured note may support extraction of a separate `EP-*` record; candidates require the downstream EP and architecture-review process.

`STRUCTURED` is the terminal maturity status for a research note. It does not mean correct, validated, architecture-relevant, or accepted.

## Downstream Stage Definitions

| Stage | Purpose | Entry criteria | Exit criteria | Deliverables | Architecture Candidate rule |
| --- | --- | --- | --- | --- | --- |
| `EP EXTRACTED` | Preserve one source-faithful proposition for cross-source analysis. | At least one `STRUCTURED` source supports the proposition and provenance is explicit. | Proposition-level evidence profile, support list, scope, limitations, convergence, conflicts, and disconfirming questions are recorded. | Stable `EP-*` record and source links. | No candidate yet. |
| `EP REVIEWED` | Check fidelity, scope, duplication, and suitability for architectural translation. | `EP EXTRACTED` record is complete. | Principle is marked `REVIEWED` or `REJECTED` with rationale. | Reviewed EP and consensus/convergence traceability where applicable. | A candidate may be created only from one or more `REVIEWED` EPs. |
| `AC: ARCHITECTURE REVIEW` | Evaluate a technology-neutral, parameter-free proposition against KRONOS responsibility boundaries. | Supporting reviewed EPs are named and the candidate is not a duplicate. | Review records assumptions, conflicts, failure modes, evidence independence, and validation feasibility. | Stable `AC-*` record and review record. | Candidate exists but is unapproved. |
| `AC: VALIDATION REQUIRED` | Define and conduct validation appropriate to the candidate claim. | Architecture review identifies a testable validation need and a validation-queue record exists. | Validation evidence is sufficient for an explicit approval or rejection decision. | `VQ-*` record, methods, observations, limitations, and result. | Candidate remains unapproved. |
| `ARCHITECTURE APPROVAL` | Make an explicit governance decision on the exact candidate and scope. | Architecture review and independent validation are complete. | Candidate is marked `ACCEPTED` or `REJECTED` and the rationale is retained. | Approval record and, if accepted, an Accepted Principle record. | No new candidate is created; the existing candidate is decided. |
| `ENGINEERING` | Implement approved architecture through the applicable engineering process. | Separate architecture authority has approved implementation scope. | Engineering acceptance criteria are satisfied. | Implementation artefacts outside this library. | Not a Research Library status. |
| `LIVE VALIDATION` | Evaluate approved implementation under controlled live-operating governance. | Engineering and deployment gates are complete. | Live-validation criteria produce an explicit promote, revise, or reject decision. | Operational validation records outside this library. | Not a Research Library status. |
| `PRODUCTION` | Operate an approved and validated implementation under production change control. | Production approval is explicit. | Governed by production lifecycle, not research maturity. | Production records outside this library. | Not a Research Library status. |

An accepted principle is not an implementation instruction. No research artefact may bypass the separate architecture and production change processes.

## Transition Rules

- `COLLECTED -> REVIEWED -> STRUCTURED` is the normal source-review path.
- `REVIEW_BLOCKED` is an exception state, not a lower evidence score and not proof that the source is poor.
- Historical milestone dates may be recorded, but Review Status shows the current source-review stage.
- Sources already marked `STRUCTURED` are understood to have satisfied the `REVIEWED` gate; they do not need to be downgraded merely because the intermediate status was introduced later.
- A source directly becoming an architecture candidate is prohibited.
- A research note directly becoming an accepted principle is prohibited.
- A candidate directly becoming accepted without a validation-queue record is prohibited.
- Engineering or production status may not be inferred from an accepted principle.

## Index Requirements

The master source index should expose four separate concepts:

- **Source Status:** standing of the registered source (`ACTIVE`, `SUPERSEDED`, `WITHDRAWN`, or `UNAVAILABLE`).
- **Review Status:** current maturity (`COLLECTED`, `REVIEW_BLOCKED`, `REVIEWED`, or `STRUCTURED`).
- **Architecture Traceability:** controlled relationship label, not an impact or approval claim: `NONE`, `TOPIC_ONLY`, `SUPPORTS_EXISTING_EP`, `ORIGINATES_AC`, `VALIDATION_EVIDENCE`, or `ACCEPTED_REFERENCE`.
- **Candidate Links:** count of distinct existing `AC-*` records traceably linked to the source. This is not a count of accepted candidates and must not be inferred from free text.

`Architecture Impact` is not the recommended column name because it can imply that research has altered architecture. `Architecture Traceability` describes only the recorded relationship.

## Metrics Requirements

Metrics should distinguish current-stage inventory from cumulative milestones:

- Current-stage source counts: `COLLECTED`, `REVIEW_BLOCKED`, `REVIEWED`, and `STRUCTURED`.
- Cumulative source milestones: registered sources, reviewed-or-beyond sources, and structured sources.
- Candidate records created, candidates in architecture review, candidates requiring validation, accepted candidates, and rejected candidates.
- EP, consensus, evidence-profile, and convergence coverage already governed elsewhere in the library.

Candidate Links in the source index must not be summed as “candidates generated,” because the same candidate may be supported by multiple sources.

## Migration Rule

Introducing `REVIEWED` does not alter existing conclusions or require retrospective invention of reviewers or dates. Existing `COLLECTED` and `STRUCTURED` records retain those Review Status values. New or updated source records should add Source Status, Review Status, Status Updated, and Reviewer metadata when known. Unknown historical metadata must remain explicitly unknown rather than inferred.

The ten existing candidates predate the explicit `EP REVIEWED` creation gate and currently link to EPs whose status remains `EXTRACTED`. They remain legacy, unapproved records at their present statuses; this governance change does not backfill EP review, recreate candidates, or imply approval. Any future candidate must satisfy the new gate.
