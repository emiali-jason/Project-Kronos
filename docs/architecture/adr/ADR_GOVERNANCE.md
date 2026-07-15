# KRONOS ADR Governance

**Status:** Draft
**Owner:** Architecture Librarian
**Approved By:** Not approved

## Purpose

This document defines the standard governance process for KRONOS Architecture Decision Records.

It does not approve, supersede, reinterpret, or modify any existing architecture decision. Existing approved `ADL-*` records remain preserved at their current paths.

## Current Repository Review

The repository currently contains:

- historical approved architecture decision logs named `ADL-001` through `ADL-005` in `docs/architecture/`;
- a draft ADR directory at `docs/architecture/adr/`;
- a draft ADR template at `docs/architecture/adr/ADR_TEMPLATE.md`;
- a draft architecture governance document at `docs/architecture/governance/ARCHITECTURE_GOVERNANCE.md`;
- an engineering decision register at `docs/Decisions.md`;
- product governance in `docs/product/PLATFORM_GOVERNANCE.md`;
- research and validation areas that provide evidence but do not approve architecture.

The existing `ADL-*` records should not be renamed or moved. New formal architecture decisions should use the ADR process described here.

## ADR Lifecycle

Recommended lifecycle states:

| State | Meaning | Authority |
|---|---|---|
| `DRAFT` | A working document being shaped. Not ready for review. | Not authoritative |
| `PROPOSED` | A complete proposal submitted for architectural review. | Not authoritative |
| `UNDER REVIEW` | Actively being reviewed by the relevant architecture authority. | Not authoritative |
| `APPROVED` | Accepted as authoritative within the recorded scope. | Authoritative |
| `REJECTED` | Reviewed and not accepted. Preserved for history. | Not authoritative |
| `SUPERSEDED` | Replaced by a newer approved ADR. Preserved for history. | Historical only |
| `DEPRECATED` | Still historically valid, but no longer recommended for new work. | Historical or transitional only |

The example lifecycle states `PROPOSED`, `UNDER REVIEW`, `APPROVED`, `SUPERSEDED`, and `DEPRECATED` are appropriate, but KRONOS should also retain `DRAFT` and `REJECTED` to distinguish unfinished work from reviewed-but-declined proposals.

Lifecycle flow:

```text
DRAFT
  -> PROPOSED
  -> UNDER REVIEW
  -> APPROVED
  -> SUPERSEDED

DRAFT / PROPOSED / UNDER REVIEW
  -> REJECTED

APPROVED
  -> DEPRECATED
```

Approved ADRs are historical records. Do not rewrite the decision text of an approved ADR. Material changes require a new ADR that links back to the prior record.

## ADR Numbering Policy

New ADRs should use:

```text
ADR-0001-short-title.md
ADR-0002-short-title.md
ADR-0003-short-title.md
```

Rules:

- Use four-digit sequential numbers.
- Never reuse a number.
- Do not renumber when files move or titles change.
- Use lowercase kebab-case after the number.
- Preserve legacy `ADL-*` records as historical records; do not convert them unless a separate approved migration authorizes it.
- If a proposed ADR is abandoned before review, its number remains reserved if the file has been committed or referenced.

## ADR Ownership

| Role | Responsibility |
|---|---|
| Trading Desk / Chat Proposal | May identify observations, questions, and candidate issues. Does not approve architecture. |
| Architecture Librarian | May draft ADRs, maintain indexes, cross-reference documents, and preserve history. Does not approve architecture. |
| Product Master Architect | Reviews product-scoped proposals and identifies product/interface impacts. |
| Chief Architect | Approves platform-wide ADRs and resolves architectural conflicts. |
| Engineering / Codex | May document feasibility and implement approved ADRs. Does not approve architecture. |

Who may propose:

- Trading Desk may propose questions or observations.
- Architecture Librarian may convert approved review material into ADR drafts.
- Product Master Architects may propose product-scoped ADRs.
- Engineering may propose implementation-risk ADRs, but cannot approve them.

Who reviews:

- Product Master Architects review product-scoped ADRs.
- Chief Architect reviews platform-wide, cross-product, ownership, and interface ADRs.
- Engineering reviews feasibility and compatibility only.

Who approves:

- Chief Architect approves platform-wide ADRs.
- Product Master Architects may approve only when explicitly assigned product-level authority.

Who supersedes:

- Only the authority that could approve the replacement ADR may supersede an approved ADR.
- Supersession is recorded by a new approved ADR and cross-linked in both records.

## ADR Template Review

The current template is useful and already includes metadata, context, decision, rationale, alternatives, consequences, risks, affected products, affected interfaces, implementation implications, validation requirements, supersession links, related documents, and revision history.

Recommended improvements:

- Use the canonical lifecycle states from this document.
- Add `Reviewers`.
- Add `Decision Scope`.
- Add `Authority Level`, such as Platform, Product, Interface, or Engineering.
- Add `Validation Evidence`.
- Add `Implementation Status`.
- Add explicit `Repository Approval` and `Engineering Status` fields so approval and implementation are not confused.

These template improvements do not change any existing ADR or ADL.

## ADR Index

The ADR index should live at:

```text
docs/architecture/adr/README.md
```

The index should record:

| Field | Purpose |
|---|---|
| ADR number | Stable identifier |
| Title | Human-readable decision title |
| Status | Current lifecycle state |
| Date | Original proposal or approval date |
| Owner | Decision owner |
| Supersedes | Prior ADRs replaced |
| Superseded by | Later ADRs replacing this one |
| Related documents | Key links |

Existing `ADL-*` records remain indexed separately through the architecture knowledge base and the decision linkage in `docs/Decisions.md`.

## Relationship To Repository Areas

| Area | Relationship to ADRs |
|---|---|
| Institutional Principles | High-level principles can motivate ADRs but do not replace approved decisions unless explicitly authoritative. |
| Platform Principles | Platform principles are applied through ADRs when a concrete architecture choice is made. |
| Product Architecture | Product architecture must link to governing ADRs when decisions affect product responsibilities or boundaries. |
| Interface Contracts | Interface contracts implement approved architectural decisions and must identify governing ADRs where applicable. |
| Validation | Validation provides evidence. It does not approve architecture by itself. |
| Engineering | Engineering implements approved ADRs and records feasibility concerns. Engineering does not redefine architecture independently. |

## Decision Authority Flow

KRONOS decision authority follows this path:

```text
Chat Proposal
  -> Architecture Proposal
  -> ADR
  -> Repository Approval
  -> Engineering
```

Meaning:

- **Chat Proposal:** a discussion, observation, or idea. Not authoritative.
- **Architecture Proposal:** a structured candidate, often in draft ADR form. Not authoritative.
- **ADR:** the formal decision record. Authoritative only after approval.
- **Repository Approval:** approved status and metadata recorded in Git.
- **Engineering:** implementation work that follows the approved decision.

No implementation should occur from chat discussion alone.

## Conflict And Supersession

When ADRs conflict:

1. Identify the conflicting ADRs and passages.
2. Apply repository authority hierarchy from `AGENTS.md`.
3. Escalate unresolved conflicts to the Chief Architect.
4. Record the resolution in a new ADR if the decision changes.
5. Update index and supersession links.

## Non-Goals

This governance framework does not:

- change existing ADL records;
- approve new product architecture;
- change Pine code;
- change engineering rules;
- create implementation authority;
- convert research or validation evidence into architecture automatically.
