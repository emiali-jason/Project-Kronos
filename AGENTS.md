# Project KRONOS Agent Governance

**Status:** Draft

## Source of Truth

The repository is the authoritative source of truth for Project KRONOS.

Chat discussions, temporary notes, assumptions, and agent memory are not authoritative unless they have been incorporated into an approved repository document.

## Authority Hierarchy

When instructions conflict, use this hierarchy:

1. Project KRONOS Constitution
2. Approved Architecture Decision Records
3. Approved product architecture documents
4. Approved interface contracts
5. Engineering documentation
6. Current task instructions
7. Chat history and informal discussion

A lower-level source must never silently override a higher-level source.

## Architectural Authority

The Chief Architect approves platform-wide architectural decisions.

Product Master Architects may propose and document architecture within their assigned product boundaries.

Engineering implements approved architecture and must not independently redefine product ownership or architectural boundaries.

Codex acts as an engineering and documentation agent. Codex does not possess architectural approval authority.

## Mandatory Repository Review

Before performing architecture-related or implementation-related work, inspect:

- `docs/architecture/README.md`
- `docs/architecture/KNOWLEDGE_BASE.md`
- `docs/architecture/constitution/`
- applicable approved ADRs
- applicable product documents
- applicable interface contracts

Do not rely solely on previous conversation context.

## No Invented Architecture

Do not invent:

- architectural principles
- product responsibilities
- engine ownership
- interface fields
- decision rules
- thresholds
- dependencies
- approval status

When authoritative information is missing, identify the gap clearly.

## Decision Management

Approved architectural changes must be represented by a new ADR.

Do not rewrite the historical decision recorded in an approved ADR.

When a decision changes:

1. Create a new ADR.
2. Reference the previous ADR.
3. Mark the previous ADR as superseded where appropriate.
4. Update relevant indexes and active architecture documents.
5. Preserve Git history.

## Product Boundaries

Products must communicate through documented interfaces.

A product must not absorb another product's responsibilities merely for convenience.

Shared concepts do not automatically imply shared ownership.

## Implementation Discipline

Architecture and implementation are separate activities.

Do not modify implementation merely because an architectural idea was discussed.

Implementation changes require an approved architecture or an explicit engineering instruction consistent with approved architecture.

Prefer additive, reviewable changes over broad rewrites.

Preserve existing public contracts unless an approved decision authorizes a change.

## Conflict Handling

When repository documents conflict:

1. Do not choose silently.
2. Identify the conflicting documents and passages.
3. Apply the authority hierarchy where possible.
4. Escalate unresolved architectural conflicts to the Chief Architect.
5. Do not implement disputed architecture until resolved.

## Documentation Status

Every governance, architecture, ADR, interface, or product document must clearly show a status such as:

- Draft
- Proposed
- Approved
- Superseded
- Deprecated

A draft or proposed document is not authoritative.

## Traceability

Architecture-related implementation should reference the governing ADR, product document, interface contract, or approved requirement whenever practical.

## Change Scope

Do not make unrelated changes.

Do not reformat or rename unrelated files.

Do not modify approved documents unless the task explicitly requires it.
