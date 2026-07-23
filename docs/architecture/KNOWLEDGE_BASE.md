# KRONOS Architecture Knowledge Base

**Status:** Draft  
**Owner:** Architecture Librarian  
**Approved By:** Not approved

## Purpose

This is the central navigation index for KRONOS architecture knowledge. It records document purpose, repository status, stated owner, and location without changing the authority of any indexed document.

Status values in this index reproduce the source document where one is stated. `Not stated` identifies missing metadata; it does not infer approval.

## Repository Governance and Draft Scaffolds

| Document or section | Purpose | Status | Owner | Location |
| --- | --- | --- | --- | --- |
| Project KRONOS Agent Governance | Rules for Codex and other repository agents | Draft | Not stated | [`AGENTS.md`](../../AGENTS.md) |
| Architecture Repository README | Navigation and document placement | Draft | Architecture Librarian | [`README.md`](README.md) |
| Architecture Knowledge Base | Central architecture index | Draft | Architecture Librarian | [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) |
| KRONOS Constitution | Constitutional placeholder | Draft | TBD | [`constitution/KRONOS_CONSTITUTION.md`](constitution/KRONOS_CONSTITUTION.md) |
| Architecture Governance | Roles and architecture document process | Draft | TBD | [`governance/ARCHITECTURE_GOVERNANCE.md`](governance/ARCHITECTURE_GOVERNANCE.md) |
| ADR Index | Navigation and ADR record rules | Draft | Architecture Librarian | [`adr/README.md`](adr/README.md) |
| ADR Template | Reusable Architecture Decision Record template | Draft | Architecture Librarian | [`adr/ADR_TEMPLATE.md`](adr/ADR_TEMPLATE.md) |
| Interface Index | Navigation and interface record rules | Draft | Architecture Librarian | [`interfaces/README.md`](interfaces/README.md) |
| Interface Template | Reusable cross-product interface template | Draft | Architecture Librarian | [`interfaces/INTERFACE_TEMPLATE.md`](interfaces/INTERFACE_TEMPLATE.md) |
| Discovery product section | Draft product architecture placeholders | Draft | TBD | [`products/discovery/`](products/discovery/) |
| Intraday product section | Draft product architecture placeholders | Draft | TBD | [`products/intraday/`](products/intraday/) |
| Swing product section | Draft product architecture placeholders | Draft | TBD | [`products/swing/`](products/swing/) |
| Execution product section | Draft product architecture placeholders | Draft | TBD | [`products/execution/`](products/execution/) |
| Engineering product section | Draft product architecture placeholders | Draft | TBD | [`products/engineering/`](products/engineering/) |
| Architecture Glossary | Draft terminology register | Draft | TBD | [`glossary/KRONOS_GLOSSARY.md`](glossary/KRONOS_GLOSSARY.md) |
| Architecture Diagrams | Diagram navigation and placement | Draft | Architecture Librarian | [`diagrams/README.md`](diagrams/README.md) |
| Decision Indexes | Decision-history navigation | Draft | Architecture Librarian | [`decisions/README.md`](decisions/README.md) |

## Existing Canonical and Approved Architecture Documents

| Document | Purpose | Recorded status | Owner stated in document | Location |
| --- | --- | --- | --- | --- |
| Project KRONOS Architecture Overview | Existing architecture overview | Canonical | Not stated | [`OVERVIEW.md`](OVERVIEW.md) |
| Project KRONOS Data Flow | Existing information-flow architecture | Canonical | Not stated | [`DATA_FLOW.md`](DATA_FLOW.md) |
| KRONOS Engine Ownership | Existing engine responsibility matrix | Canonical | Not stated | [`ENGINE_OWNERSHIP.md`](ENGINE_OWNERSHIP.md) |
| ADP-001A — Swing Phase 1 Market Data Inventory | Canonical Phase 1 market-data inventory for KRONOS Swing | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md`](products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md) |
| ADP-001B — KRONOS Swing Instrument Identity Architecture | Canonical Version 1.0 Instrument Identity architecture for KRONOS Swing Phase 1 | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md`](products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md) |
| ADP-001C — Provider → Instrument Contract | Canonical Version 1.0 governed semantic boundary for Provider information eligibility before Instrument interpretation | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md`](products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md) |
| ADR-006 — Execution Context Provider Architecture | Execution Context Provider architecture decision record | Approved | Chief Architect | [`adr/ADR-006-Execution-Context-Provider-Architecture.md`](adr/ADR-006-Execution-Context-Provider-Architecture.md) |
| ECIC-001 — Execution Context Interface Contract | Execution Context public interface contract | Approved | Chief Architect | [`interfaces/ECIC-001-Execution-Context-Interface-Contract.md`](interfaces/ECIC-001-Execution-Context-Interface-Contract.md) |
| ECM-001 — Execution Context Model | Execution Context behavioral model | Approved | Not stated | [`models/ECM-001-Execution-Context-Model.md`](models/ECM-001-Execution-Context-Model.md) |
| ECPC-001 — Execution Context Payload Contract | Conceptual Execution Context payload-governance contract | Approved | Not stated | [`interfaces/ECPC-001-Execution-Context-Payload-Contract.md`](interfaces/ECPC-001-Execution-Context-Payload-Contract.md) |
| EAIC-001 — Exchange Availability Interface Contract | Presentation-facing Exchange Availability interface contract | Approved | Chief Architect | [`interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md`](interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md) |
| PP-007 — Execution Semantics Across Markets | Market-neutral execution-semantics principle | Approved | Chief Architect | [`principles/PP-007-Execution-Semantics-Across-Markets.md`](principles/PP-007-Execution-Semantics-Across-Markets.md) |
| ADL-001 — Futures Model Architecture | Existing futures-model decision record | Approved for Version 1.x; not required for initial MVP | Not stated | [`ADL-001-Futures-Model.md`](ADL-001-Futures-Model.md) |
| ADL-002 — MCX Self-Contained Execution | Existing execution decision record | Approved | Not stated | [`ADL-002-MCX-Self-Contained-Execution.md`](ADL-002-MCX-Self-Contained-Execution.md) |
| ADL-003 — Execution Context Adapters | Existing adapter decision record | Approved | Not stated | [`ADL-003-Execution-Context-Adapters.md`](ADL-003-Execution-Context-Adapters.md) |
| ADL-004 — Model Trade Ownership | Existing model-trade decision record | Approved | Not stated | [`ADL-004-Model-Trade-Ownership.md`](ADL-004-Model-Trade-Ownership.md) |
| ADL-005 — Alert Architecture | Existing alert decision record | Approved | Not stated | [`ADL-005-Alert-Architecture.md`](ADL-005-Alert-Architecture.md) |
| KR-710 Deterministic Explainability Framework | Existing explainability contract | Approved Architecture Contract; Not Implemented | Not stated | [`KR710_DETERMINISTIC_EXPLAINABILITY_SPEC.md`](KR710_DETERMINISTIC_EXPLAINABILITY_SPEC.md) |
| KR-711 Action-Oriented Trader Messaging | Existing messaging contract | Approved Architecture Contract; Not Implemented | Not stated | [`KR711_ACTION_ORIENTED_MESSAGING_SPEC.md`](KR711_ACTION_ORIENTED_MESSAGING_SPEC.md) |

## Existing Product and Repository Governance Documents

| Document | Purpose | Recorded status | Owner stated in document | Location |
| --- | --- | --- | --- | --- |
| KRONOS Platform Governance | Existing platform governance principles and flow | Approved | Not stated | [`../product/PLATFORM_GOVERNANCE.md`](../product/PLATFORM_GOVERNANCE.md) |
| KRONOS Platform Architecture | Existing product architecture | Product Architecture | Not stated | [`../product/KRONOS_PLATFORM_ARCHITECTURE.md`](../product/KRONOS_PLATFORM_ARCHITECTURE.md) |
| KRONOS Versioning Policy | Existing product and contract versioning policy | Approved | Not stated | [`../product/VERSIONING_POLICY.md`](../product/VERSIONING_POLICY.md) |
| KRONOS Release Policy | Existing release-governance policy | Approved | Not stated | [`../product/RELEASE_POLICY.md`](../product/RELEASE_POLICY.md) |
| Project KRONOS Architecture | Existing legacy architecture document | Not stated | Not stated | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Project KRONOS Engineering Decisions | Existing decision log and ADL links | Not stated | Not stated | [`../Decisions.md`](../Decisions.md) |

## Status Boundary

- `Draft` and `Proposed` documents are not authoritative architecture.
- An indexed approved or canonical document retains the authority recorded in that document.
- Indexing does not approve, supersede, relocate, or reconcile content.
- Any conflict between existing documents must be reported under the authority hierarchy in `AGENTS.md`.

## Known Structural Overlaps Requiring Review

- A separate top-level [`architecture/`](../../architecture/) scaffold already exists. This task does not move, merge, deprecate, or reinterpret it.
- Existing approved decision records use `ADL-*` filenames at the root of `docs/architecture/`, while the new Draft framework uses `ADR-*` for future records. Existing records were not renumbered or relocated.
- [`docs/Decisions.md`](../Decisions.md) remains an existing engineering decision log and ADL linkage record. The new `adr/` and `decisions/` directories do not replace it.
- Approved [`PLATFORM_GOVERNANCE.md`](../product/PLATFORM_GOVERNANCE.md) remains the current recorded platform governance document. The new `ARCHITECTURE_GOVERNANCE.md` is a Draft repository-process document and does not override it.
- Existing product architecture under [`docs/product/`](../product/) is preserved. Draft product folders under `docs/architecture/products/` are not populated from it without explicit architectural direction.
