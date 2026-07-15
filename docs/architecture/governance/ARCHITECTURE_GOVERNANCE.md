# KRONOS Architecture Governance

**Status:** Draft  
**Owner:** TBD  
**Approved By:** Not approved

## Purpose

This Draft describes the repository process for proposing, reviewing, approving, recording, and preserving KRONOS architecture. It does not approve architecture or assign authority beyond the root [`AGENTS.md`](../../../AGENTS.md).

## Chief Architect

The Chief Architect approves platform-wide architectural decisions.

[Additional responsibilities: TBD]

## Product Master Architects

Product Master Architects may propose and document architecture within their assigned product boundaries.

[Assigned product boundaries and review responsibilities: TBD]

## Engineering

Engineering implements approved architecture and must not independently redefine product ownership or architectural boundaries.

[Additional engineering governance responsibilities: TBD]

## Architecture Librarian

The Architecture Librarian organizes, documents, cross-references, and maintains architecture approved by the Chief Architect.

The Architecture Librarian does not make, infer, reinterpret, or approve architectural decisions.

## Proposal Process

1. Record the context and the proposed decision in a Draft ADR.
2. Identify affected products, interfaces, existing decisions, dependencies, risks, and validation needs without inventing missing content.
3. Cross-reference related repository records.
4. Submit the proposal for the applicable review.

## Review Process

1. Product Master Architects review proposals within their assigned product boundaries.
2. Cross-product proposals identify all affected products and interface contracts.
3. Engineering may document feasibility, compatibility, and validation concerns without approving architecture.
4. Conflicts and missing authority are escalated rather than resolved silently.

## Approval Process

1. The Chief Architect approves platform-wide architectural decisions.
2. Approval must be recorded in the ADR metadata and status.
3. Approval applies only to the recorded decision, scope, and version.
4. A Draft or Proposed document is not authoritative.

[Any additional product-level approval authority: TBD]

## ADR Lifecycle

Detailed ADR lifecycle, numbering, ownership, template, index, repository relationship, and authority-flow rules are defined in [`../adr/ADR_GOVERNANCE.md`](../adr/ADR_GOVERNANCE.md).

```text
DRAFT -> PROPOSED -> UNDER REVIEW -> APPROVED -> SUPERSEDED
DRAFT / PROPOSED / UNDER REVIEW -> REJECTED
APPROVED -> DEPRECATED
```

- Approved ADRs are preserved as historical records.
- A changed approved decision is recorded in a new ADR.
- Related, superseded, and superseding ADRs are cross-referenced.
- The ADR index and Knowledge Base are updated without rewriting history.

## Conflict Resolution

When repository documents conflict:

1. identify the documents and conflicting passages;
2. apply the authority hierarchy in `AGENTS.md` where possible;
3. escalate unresolved architectural conflicts to the Chief Architect;
4. do not implement disputed architecture until the conflict is resolved and recorded.

## Document Status

Architecture documents must state a status such as:

- DRAFT
- PROPOSED
- UNDER REVIEW
- APPROVED
- REJECTED
- SUPERSEDED
- DEPRECATED

DRAFT, PROPOSED, UNDER REVIEW, and REJECTED documents are not authoritative.

## Versioning

- ADR numbers are stable and never reused.
- Approved ADR history is not rewritten.
- Material decision changes require a new ADR.
- Interface documents state a version and compatibility policy.
- Superseding records preserve links to prior decisions.
- Existing approved document names and paths are preserved unless an approved decision authorizes migration.

## Traceability

- ADRs link to affected products, interfaces, related decisions, validation requirements, and related documents.
- Product documents link to governing ADRs and authoritative interface contracts.
- Architecture-related implementation references its governing approved record whenever practical.
- Git history is part of the architecture record and must be preserved.

## Related Records

- [`../adr/`](../adr/)
- [`../products/`](../products/)
- [`../interfaces/`](../interfaces/)
- [`../KNOWLEDGE_BASE.md`](../KNOWLEDGE_BASE.md)
