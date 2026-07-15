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
4. Read applicable approved decision records.
5. Read applicable product documents and interface contracts.
6. Identify conflicts or missing authority instead of resolving them silently.

## Repository Map

| Location | Content |
| --- | --- |
| [`constitution/`](constitution/) | Constitutional headings, approved principles, and invariants. The current file is a Draft placeholder and contains no approved principles. |
| [`governance/`](governance/) | Architecture roles, proposal, review, approval, versioning, and traceability governance. |
| [`adr/`](adr/) | Architecture Decision Record index and reusable template. |
| [`interfaces/`](interfaces/) | Cross-product interface index and reusable interface template. |
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

Existing architecture documents remain at their current paths and retain their recorded status. They have not been moved, renamed, duplicated, or rewritten by this repository setup. See [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) for the complete index.

Any migration, supersession, status change, or reinterpretation requires explicit architectural authority and preserved Git history.
