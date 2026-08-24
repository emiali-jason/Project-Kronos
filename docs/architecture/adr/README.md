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
| [ADR-006](ADR-006-Execution-Context-Provider-Architecture.md) | Execution Context Provider Architecture | Approved — affected state-name/ownership clauses superseded | Not stated | Chief Architect | None | [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md) (in part) | [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md); [ECIC-001](../interfaces/ECIC-001-Execution-Context-Interface-Contract.md); [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md); [ECM-001](../models/ECM-001-Execution-Context-Model.md); [ADL-003](../ADL-003-Execution-Context-Adapters.md) |
| [ADR-007](../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md) | Provider Capability Assessment Architecture | Approved | 2026-07-26 | Chief Architect | None | None | [DOMAIN-006](../platform/domains/provider/ARCHITECTURE.md); [ADP-001G](../products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md); [ADR-009](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md); [EAIC-002](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md); [ADP-001H — superseded history](../products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md) |
| [ADR-008](../platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md) | Provider Entitlement Assessment Architecture | Approved | 2026-07-26 | Chief Architect | None | None | [DOMAIN-006](../platform/domains/provider/ARCHITECTURE.md); [ADR-007](../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md); [EDD-001](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md); [EDD-002](../../engineering/edd/EDD-002-PROVIDER-CAPABILITY-ASSESSMENT-ENGINEERING-DESIGN.md) |
| [ADR-009](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md) | Provider-Bounded Instrument Master Acquisition Architecture | Approved — inactive pending activation review | 2026-07-26 | Chief Architect | None | None | [MIG-001](../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md); [EAIC-002](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md); [DOMAIN-006](../platform/domains/provider/ARCHITECTURE.md); [DOMAIN-001](../platform/domains/instrument/ARCHITECTURE.md); [ADP-001C — superseded history](../products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md); [ADP-001H — superseded history](../products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md) |
| [ADR-010](../platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md) | Provider Authentication Shared Platform Capability | Approved Canonical Architecture | 2026-08-03 | Chief Architect | None | None | [DOMAIN-006 Version 1.1](../platform/domains/provider/ARCHITECTURE.md); [ADP-001G](../products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md) |
| [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md) | KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics | Approved | 2026-08-21 | Chief Architect | Affected ownership and terminology clauses of ADR-006 | None | [State-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md); [PLATFORM-000](../platform/PLATFORM-000-CONSTITUTION.md); [Engine Ownership](../ENGINE_OWNERSHIP.md); [Data Flow](../DATA_FLOW.md) |
| [ADR-0012](ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md) | Remaining Swing UX/OPS Scope and Disposition | Approved | 2026-08-21 | Chief Architect | None | None | [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md); [State-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md); [ADL-005](../ADL-005-Alert-Architecture.md) |
| [ADR-0013](ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md) | Native Swing DOMAIN-007 Risk Permission and KR-380 V2 Production Commissioning | Approved | 2026-08-21 | Chief Architect / Sponsor | Step-32 validation-only operational limit for the exact Native V2 path | None | [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md); [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md); [Step-32 contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md) |
| [ADR-0014](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md) | DOMAIN-001 Canonical Instrument V2 Semantic Layering, Provider Classification, and Active Derivative Binding Architecture | Approved | 2026-08-22 | Chief Architect | None | None | [DOMAIN-001](../platform/domains/instrument/ARCHITECTURE.md); [DOMAIN-006](../platform/domains/provider/ARCHITECTURE.md); [ADR-009](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md); [EAIC-002](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md); [Intraday Native Universe V1](../products/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md) |
| [ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md) | Swing Sponsor Observation-Phase Authority and Step-31 Evidence Governance | Approved | 2026-08-24 | Chief Architect | Selected Sponsor-control implications of ADR-0012 and Step-32 product contracts, prospectively and in part | None | [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md); [ADR-0013](ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md); [Step-32 contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md); [DOMAIN-007](../platform/domains/risk/ARCHITECTURE.md); [Step-33](../products/swing/SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md) |

The existing approved `ADL-*` records remain at their established paths under [`../`](../) and are indexed in [`../KNOWLEDGE_BASE.md`](../KNOWLEDGE_BASE.md). They have not been converted, renumbered, or moved.
