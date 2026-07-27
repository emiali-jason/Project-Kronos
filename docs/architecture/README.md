# KRONOS Architecture Repository

**Status:** Draft  
**Owner:** Architecture Librarian  
**Approved By:** Not approved

## Purpose

This directory is the repository index for KRONOS architecture documents, governance, decisions, interfaces, product records, terminology, and diagrams.

The repository is the source of truth. Chat history, temporary notes, agent memory, and informal discussion are not official architecture unless they have been incorporated into an approved repository document.

This index organizes documents. It does not approve, replace, reinterpret, or infer architecture.

## Start Here

1. Read the root [`AGENTS.md`](../../AGENTS.md).
2. Read the central [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md).
3. Read the [Constitution](constitution/KRONOS_CONSTITUTION.md).
4. Read applicable approved decision records, including [ADR-009](platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md) for Provider-bounded Instrument Master acquisition.
5. Read [MIG-001](migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md) for the completed migration and repository-synchronization record.
6. Read applicable product documents and interface contracts, including [EAIC-002](interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) for the canonical Provider → Instrument submission boundary.
7. Read [CAR-003](../governance/reviews/CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md) for the completed RC-04 activation and constrained EDD-004 Draft Preparation authorization.
8. Read the [engineering architecture packages](../engineering/eap/) for the active EAP-001 through EAP-006 Engineering Design baseline.
9. Identify conflicts or missing authority instead of resolving them silently.

Current programme state: Architecture Programme — Accepted; Repository — Ready; Architecture Migration — Completed; Engineering Publication — Completed; Repository Synchronization — Completed; RC-04 Activation — Completed; ADR-009 — Operational Architecture; EAIC-002 — Operational Canonical Contract; Engineering Programme — Authorized with Constraints; EDD-004 Draft Preparation — Approved with Constraints; Implementation — Not Authorized; Runtime — Not Authorized.

## Repository Map

| Location | Content |
| --- | --- |
| [`constitution/`](constitution/) | Constitutional headings, approved principles, and invariants. The current file is a Draft placeholder and contains no approved principles. |
| [`governance/`](governance/) | Architecture roles, proposal, review, approval, versioning, and traceability governance. |
| [`adr/`](adr/) | Architecture Decision Record index and reusable template. |
| [`interfaces/`](interfaces/) | Cross-product interface index and reusable interface template. |
| [`migrations/`](migrations/) | Governed architecture-migration planning, sequencing, validation, publication, and closure records. |
| [`platform/`](platform/) | Canonical platform constitution, domain architecture, ownership, and dependency authorities. |
| [`products/`](products/) | Draft or approved product-specific responsibilities, interfaces, constraints, and future records. |
| [`decisions/`](decisions/) | Decision-history indexes and navigation. Formal new architecture decisions belong in `adr/`. |
| [`glossary/`](glossary/) | Approved or Draft architectural terminology. |
| [`diagrams/`](diagrams/) | Approved or Draft architecture diagrams and explanatory records. |

## Product Areas

- [`discovery/`](products/discovery/)
- [`intraday/`](products/intraday/)
- [`swing/`](products/swing/)
- [`execution/`](products/execution/)
- [`engineering/`](products/engineering/)

Product folder names do not establish product responsibilities. Draft placeholders are not authoritative.

## Placement Rules

- Constitution content belongs in `constitution/` only after the required approval.
- New formal architecture decisions belong in `adr/` and use `ADR_TEMPLATE.md`.
- Approved ADRs are historical records and must not be rewritten.
- Cross-product contracts belong in `interfaces/` and must identify status and version.
- Product-specific records belong under the applicable `products/<product>/` directory.
- Approved glossary definitions belong in `glossary/`.
- Diagrams belong in `diagrams/` and must identify the documents they represent.
- Research and validation evidence remain evidence; links do not grant architectural authority.

## Existing Architecture

Published architecture documents remain at their governed paths and retain their recorded status. The completed migration’s amendments and supersessions are recorded in [MIG-001](migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md), and historical predecessors remain available through governed links. See [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) for the current index.

Any migration, supersession, status change, or reinterpretation requires explicit architectural authority and preserved Git history.
