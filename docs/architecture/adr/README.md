# Architecture Decision Records

**Status:** Draft  
**Owner:** Architecture Librarian  
**Approved By:** Not approved

## Purpose

This directory is the canonical location for new KRONOS Architecture Decision Records.

## Rules

- Create new ADRs from [`ADR_TEMPLATE.md`](ADR_TEMPLATE.md).
- Follow the lifecycle, numbering, ownership, index, and authority rules in [`ADR_GOVERNANCE.md`](ADR_GOVERNANCE.md).
- Assign a stable ADR number; never reuse a number.
- Do not rewrite the historical decision in an approved ADR.
- A changed decision requires a new ADR that references the prior record.
- Cross-reference related, superseded, and superseding ADRs.
- Update this index when an ADR is added or its recorded lifecycle status changes.
- Preserve Git history.

## ADR Index

| ADR | Title | Status | Date | Owner | Supersedes | Superseded by | Related documents |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ADR-0001](ADR-0001-research-first-product-mandate.md) | Research-First Product Mandate and Execution Deferral | Draft | 2026-07-22 | Chief Architect | None | None | [Impact Assessment](../products/discovery/RESEARCH_FIRST_ARCHITECTURE_IMPACT_ASSESSMENT.md); [Engineering Roadmap](../products/discovery/RESEARCH_FIRST_ENGINEERING_ROADMAP.md) |
| [ADR-006](ADR-006-Execution-Context-Provider-Architecture.md) | Execution Context Provider Architecture | Approved | Not stated | Chief Architect | None | None | [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md); [ECIC-001](../interfaces/ECIC-001-Execution-Context-Interface-Contract.md); [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md); [ECM-001](../models/ECM-001-Execution-Context-Model.md); [ADL-003](../ADL-003-Execution-Context-Adapters.md) |

The existing approved `ADL-*` records remain at their established paths under [`../`](../) and are indexed in [`../KNOWLEDGE_BASE.md`](../KNOWLEDGE_BASE.md). They have not been converted, renumbered, or moved.
