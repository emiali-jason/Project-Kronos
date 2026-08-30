# KRONOS Architecture Knowledge Base

**Status:** Draft
**Owner:** Architecture Librarian
**Approved By:** Not approved

## Purpose

This is the central navigation index for KRONOS architecture knowledge. It records document purpose, repository status, stated owner, and location without changing the authority of any indexed document.

Status values in this index reproduce the source document where one is stated. `Not stated` identifies missing metadata; it does not infer approval.

Repository synchronization and RC-04 activation are complete. ADR-009 is Operational Architecture, EAIC-002 is the Operational Canonical Provider → Instrument Contract, the Engineering Programme is Authorized with Constraints, and EDD-004 Draft Preparation is Approved with Constraints. Implementation and runtime activity remain unauthorized.

## Provider Authentication Canonical Architecture

The following documents are approved canonical architecture. They grant no engineering-design, implementation or runtime authority.

| Document | Purpose | Status | Owner | Location |
| --- | --- | --- | --- | --- |
| ADR-010 — Provider Authentication Shared Platform Capability | Provider-neutral Shared Platform capability for Provider Authentication and Authenticated Context Establishment | Approved Canonical Architecture | Chief Architect | [`platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md`](platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md) |
| DOMAIN-006 Version 1.1 | Provider Authentication and Authenticated Context Establishment within the Provider Domain architecture | Approved Canonical Architecture | Chief Architect | [`platform/domains/provider/ARCHITECTURE.md`](platform/domains/provider/ARCHITECTURE.md) |

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
| Intraday product section | Living Intraday architecture, contracts, universe and control records | Living / source-specific | KRONOS Intraday | [`products/intraday/`](products/intraday/) |
| Intraday Native Universe V1 | Exact 98-member Intraday-owned Native analytical universe and canonical coverage | WO-03A review candidate | KRONOS Intraday | [`products/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md`](products/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md) |
| Intraday Programme Roadmap | CA-ratified WO sequence and conditional gates | Controlled | KRONOS Intraday | [`products/intraday/KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md`](products/intraday/KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md) |
| Swing product section | Draft product architecture placeholders | Draft | TBD | [`products/swing/`](products/swing/) |
| Execution product section | Draft product architecture placeholders | Draft | TBD | [`products/execution/`](products/execution/) |
| Engineering product section | Draft product architecture placeholders | Draft | TBD | [`products/engineering/`](products/engineering/) |
| Architecture Glossary | Draft terminology register | Draft | TBD | [`glossary/KRONOS_GLOSSARY.md`](glossary/KRONOS_GLOSSARY.md) |
| Architecture Diagrams | Diagram navigation and placement | Draft | Architecture Librarian | [`diagrams/README.md`](diagrams/README.md) |
| Decision Indexes | Decision-history navigation | Draft | Architecture Librarian | [`decisions/README.md`](decisions/README.md) |
| CAR-003 — RC-04 Architecture Activation and Engineering Authorization Decision | Canonical publication of completed RC-04 activation and constrained EDD-004 Draft Preparation authorization | Approved | Chief Architect | [`../governance/reviews/CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md`](../governance/reviews/CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md) |

## Existing Canonical and Approved Architecture Documents

| Document | Purpose | Recorded status | Owner stated in document | Location |
| --- | --- | --- | --- | --- |
| Project KRONOS Architecture Overview | Existing architecture overview | Canonical | Not stated | [`OVERVIEW.md`](OVERVIEW.md) |
| Project KRONOS Data Flow | Existing information-flow architecture | Canonical | Not stated | [`DATA_FLOW.md`](DATA_FLOW.md) |
| KRONOS Engine Ownership | Existing engine responsibility matrix | Canonical | Not stated | [`ENGINE_OWNERSHIP.md`](ENGINE_OWNERSHIP.md) |
| ADP-001A — Swing Phase 1 Market Data Inventory | Canonical Phase 1 market-data inventory for KRONOS Swing | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md`](products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md) |
| ADP-001B — KRONOS Swing Instrument Identity Architecture | Canonical Version 1.0 Instrument Identity architecture for KRONOS Swing Phase 1 | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md`](products/swing/SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md) |
| ADP-001C — Provider → Instrument Contract | Superseded Version 1.0 historical predecessor; EAIC-002 Version 0.1 is the sole canonical Provider → Instrument submission contract | Superseded | Chief Architect | [`products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md`](products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md) |
| ADP-001D — Instrument → Observation Contract | Canonical Version 1.0 governed attribution boundary for factual market information and approved canonical Instrument identity | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md`](products/swing/SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md) |
| ADP-001E — Observation Domain Architecture | Canonical KRONOS Swing architecture for governed factual Observation ownership and semantics | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md`](products/swing/SWING-PHASE-1-OBSERVATION-DOMAIN-ARCHITECTURE.md) |
| ADP-001F — Configuration → Provider Runtime Configuration Boundary | Canonical Version 1.0 Configuration-owned Provider runtime-configuration boundary for KRONOS Swing | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md`](products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md) |
| ADP-001G — Configuration → Provider Authentication Boundary | Canonical Version 1.0 boundary for Configuration-owned authentication material and Provider-owned authenticated context | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md`](products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md) |
| ADP-001H — Provider Instrument Master Acquisition Capability and Contract | Superseded Version 1.0 historical predecessor; successor authority: [ADR-009 Version 1.0](platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md), [DOMAIN-006 Provider Domain Architecture](platform/domains/provider/ARCHITECTURE.md), and [EAIC-002 Version 0.1](interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) | Superseded | Chief Architect | [`products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md`](products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md) |
| ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture | Approved canonical architecture defining the KRONOS Swing Phase 1 semantic Instrument universe, MCX Analysis and Intended Execution roles, COMEX Reference roles, and provider-neutral reference semantics | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md`](products/swing/SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md) |
| MCX-CONTEXT-01 — Twice-Daily Supporting Context V1 | Immutable MORNING/EVENING METALS and ENERGY visual context retained only as supporting evidence | Approved | Chief Architect | [`products/swing/KRONOS-SWING-MCX-CONTEXT-01-TWICE-DAILY-SUPPORTING-CONTEXT-V1.md`](products/swing/KRONOS-SWING-MCX-CONTEXT-01-TWICE-DAILY-SUPPORTING-CONTEXT-V1.md) |
| ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture | Approved canonical architecture for Instrument-owned interpretation and canonical identity establishment | Approved | Chief Architect | [`products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md`](products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md) |
| EAP-001 — Configuration-to-Provider Authenticated Context Engineering Architecture | Approved Canonical Engineering Architecture Version 1.0 for Configuration-to-Provider authenticated-context engineering contracts | Approved | Chief Architect | [`../engineering/eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md`](../engineering/eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md) |
| EAP-002 — Provider Instrument Master Acquisition Engineering Architecture | Approved Canonical Engineering Architecture Version 2.0 for Provider-bounded acquisition and Provider Catalogue engineering | Approved | Engineering Architect | [`../engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md`](../engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md) |
| EAP-003 — Provider-to-Instrument Submission Validation and Interpretation Admission Engineering Architecture | Approved Canonical Engineering Architecture Version 2.0 for submission validation and Instrument interpretation admission | Approved | Engineering Architect | [`../engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md`](../engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md) |
| EAP-004 — Instrument Interpretation and Canonical Identity Establishment Engineering Architecture | Approved Canonical Engineering Architecture Version 2.0 for Instrument-owned interpretation and canonical identity establishment | Approved | Engineering Architect | [`../engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md`](../engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md) |
| EAP-005 — Instrument-to-Observation Attribution Eligibility Engineering Architecture | Approved Canonical Engineering Architecture Version 1.1 for product-neutral attribution eligibility | Approved | Engineering Architect | [`../engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md`](../engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md) |
| EAP-006 — Observation Acceptance and Governed Observation Establishment Engineering Architecture | Approved Canonical Engineering Architecture Version 1.1 for Observation-owned acceptance and governed Observation establishment | Approved | Engineering Architect | [`../engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md`](../engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md) |
| ADR-006 — Execution Context Provider Architecture | Execution Context Provider architecture decision record; affected state-name and ownership clauses are superseded by ADR-0011 while provider/consumer topology remains approved | Approved — superseded in part | Chief Architect | [`adr/ADR-006-Execution-Context-Provider-Architecture.md`](adr/ADR-006-Execution-Context-Provider-Architecture.md) |
| ADR-0011 — KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics | Approved current separation of KR-370 analytical promotion from KR-380 entry timing, with historical KR-380 state preservation | Approved | Chief Architect | [`adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md`](adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md) |
| ADR-0012 / SWING-UX-GOV-01 — Remaining Swing UX/OPS Scope and Disposition | Approved definitions and dispositions for UX-04, UX-05, UX-06, UX-07, UX-09, and OPS-01, including verified closures and the frozen remaining sequence | Approved | Chief Architect | [`adr/ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md`](adr/ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md) |
| ADR-0013 — Native Swing DOMAIN-007 Risk Permission and KR-380 V2 Production Commissioning | Approved bounded DOMAIN-007 V1 permission, Portfolio State V1, Native ECPC V2, KR-380 V2 persistence, and KR-390 handoff with no broker authority | Approved | Chief Architect / Sponsor | [`adr/ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md`](adr/ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md) |
| ADR-0014 — DOMAIN-001 Canonical Instrument V2 Semantic Layering, Provider Classification, and Active Derivative Binding Architecture | Approved Platform architecture for Catalogue V2 semantic layers, explicit Provider classification mapping, persistent NSE/MCX analytical subjects, and governed active derivative bindings | Approved | Chief Architect | [`adr/ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md`](adr/ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md) |
| ADR-0015 — Swing Sponsor Observation-Phase Authority and Step-31 Evidence Governance | Approved prospective separation of Step-31 mathematical warnings from explicit Sponsor participation choice, with DOMAIN-007 and objective-model hard blockers preserved | Approved | Chief Architect | [`adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md`](adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md) |
| ADR-0016 — Swing Paper Observation Track Authority | Approved prospective non-position market-path tracking for explicitly started blocked PAPER decisions, with no Risk bypass, position, objective-model, P&L, actual-R, or broker authority | Approved | Chief Architect | [`adr/ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md`](adr/ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md) |
| ADR-0017 — KRONOS Platform Governed Active Derivative Contract Selection V1 | Approved DOMAIN-001 selection authority for the exact five governed MCX families using unique minimum eligible expiry and DOMAIN-008 expiry-session eligibility, with immutable roll and no execution authority | Approved | Chief Architect | [`adr/ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md`](adr/ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md) |
| ADR-0018 — DOMAIN-001 Governed Visual Identity Relationship V1 | Exact, source-qualified, effective-dated DOMAIN-001 authority for external visible labels to resolve to canonical analytical subjects without rewriting raw evidence | Approved | Chief Architect | [`adr/ADR-0018-DOMAIN-001-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-V1.md`](adr/ADR-0018-DOMAIN-001-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-V1.md) |
| ADR-0019 — Intraday WO-10/WO-11 Pre-KR-370 Semantic Boundary | Approved product clarification establishing the seven-state WO-10 family and zero-discretion WO-11 publication as pre-KR-370 product states with no Entry, Risk or broker authority | Approved | KRONOS Intraday | [`adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md`](adr/ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md) |
| ADR-0020 — Intraday WO-11 to WO-12 KR-370 Analytical Promotion Boundary | Approved additive successor establishing the exact versioned WO-11 → WO-12 crossing, common KR-370 reuse, Intraday 15M K1–K5 and bounded implementation authority | Approved | Chief Architect / KR-370 / DOMAIN-003 Validation | [`adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md`](adr/ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md) |
| Intraday WO-12 KR-370 Analytical Promotion V1 | Canonical product architecture for exact WO-11 admission, 15M K1–K5, common maturity states, hard gates, K5 unresolved threshold and WO-13 eligibility | Approved Architecture — Bounded Engineering Authorized | KR-370 / DOMAIN-003 Validation | [`products/intraday/KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md`](products/intraday/KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md) |
| ADR-007 — Provider Capability Assessment Architecture | Canonical platform Provider-domain architecture for governed Provider capability assessment | Approved | Chief Architect | [`platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md`](platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md) |
| ADR-008 — Provider Entitlement Assessment Architecture | Canonical platform Provider-domain architecture for governed account-specific Provider entitlement assessment | Approved | Chief Architect | [`platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md`](platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md) |
| ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture | Operational Architecture for Provider-bounded acquisition and Provider Catalogue meaning under RC-04 | Approved | Chief Architect | [`platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md`](platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md) |
| MIG-001 — ADR-009 Coordinated Architecture Migration Package | Canonical Version 0.2 closure record for completed architecture migration, engineering publication, and repository synchronization | Approved | Chief Architect | [`migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md`](migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md) |
| EAIC-002 — Provider → Instrument Submission Contract | Operational Canonical Provider → Instrument Contract under RC-04; runtime submission authority remains separate and absent | Approved | Chief Architect | [`interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md`](interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md) |
| ECIC-001 — Execution Context Interface Contract | Execution Context public interface contract | Approved | Chief Architect | [`interfaces/ECIC-001-Execution-Context-Interface-Contract.md`](interfaces/ECIC-001-Execution-Context-Interface-Contract.md) |
| ECM-001 — Execution Context Model | Execution Context behavioral model | Approved | Not stated | [`models/ECM-001-Execution-Context-Model.md`](models/ECM-001-Execution-Context-Model.md) |
| ECPC-001 — Execution Context Payload Contract | Conceptual Execution Context payload-governance contract | Approved | Not stated | [`interfaces/ECPC-001-Execution-Context-Payload-Contract.md`](interfaces/ECPC-001-Execution-Context-Payload-Contract.md) |
| EAIC-001 — Exchange Availability Interface Contract | Presentation-facing Exchange Availability interface contract | Approved | Chief Architect | [`interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md`](interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md) |
| PP-007 — Execution Semantics Across Markets | Market-neutral execution-semantics principle | Approved | Chief Architect | [`principles/PP-007-Execution-Semantics-Across-Markets.md`](principles/PP-007-Execution-Semantics-Across-Markets.md) |
| KR-370 / KR-380 State-Family Contracts | Versioned owner/state-family separation for current analytical promotion, current Entry Outcome, and historical Entry Outcome restoration | Approved | Chief Architect | [`interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md`](interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md) |
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

## Swing V1 Step-32 Approved Architecture — 2026-08-13

- [P32-001–P32-008](adr/ADR-SWING-STEP-32-PLATFORM-AMENDMENTS.md)
- [S32-001–S32-009](products/swing/SWING-V1-STEP-32-PRODUCT-ADRS.md)
- [Eight contracts](interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md)
- [Monitoring/recovery architecture](products/swing/SWING-V1-STEP-32-MONITORING-ARCHITECTURE.md)
- [202-case validation](products/swing/SWING-V1-STEP-32-VALIDATION-PROGRAMME.md)
- [Production gates](products/swing/SWING-V1-STEP-32-PRODUCTION-GATES.md)
- [Step-33 outcome/journal architecture](products/swing/SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md)

Step-32 implementation is authorized only within its current engineering scope. Active monitoring uses Kite Connect WebSocket factual Provider input; 32H and TradingView/Pine active-trade webhook transport are retired and public webhook ingress is not required. Pine changes and broker execution remain unauthorized. Authority remains SHADOW / VALIDATION ONLY.
