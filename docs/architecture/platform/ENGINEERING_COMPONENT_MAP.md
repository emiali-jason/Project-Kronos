# KRONOS Engineering Component Map
Status: Draft
Owner: Chief Architect
Version: 1.0 Draft

## Purpose

Translate each approved KRONOS Platform Domain into one primary engineering component without changing architecture, semantic ownership, contracts, or existing KR engine responsibilities.

This map is an engineering planning record only. The approved Platform Architecture remains authoritative.

## Component Mapping

| Approved Platform Domain | Primary Engineering Component | Component Document | Status |
| --- | --- | --- | --- |
| DOMAIN-001 — Instrument | Instrument component | [Instrument Engineering](domains/instrument/ENGINEERING.md) | Draft |
| DOMAIN-002 — Observation | Observation component | [Observation Engineering](domains/observation/ENGINEERING.md) | Draft |
| DOMAIN-003 — Validation | Validation component | [Validation Engineering](domains/validation/ENGINEERING.md) | Draft |
| DOMAIN-004 — Execution | Execution component | [Execution Engineering](domains/execution/ENGINEERING.md) | Draft |
| DOMAIN-005 — Portfolio | Portfolio component | [Portfolio Engineering](domains/portfolio/ENGINEERING.md) | Draft |
| DOMAIN-006 — Provider | Provider component | [Provider Engineering](domains/provider/ENGINEERING.md) | Draft |
| DOMAIN-007 — Risk | Risk component | [Risk Engineering](domains/risk/ENGINEERING.md) | Draft |
| DOMAIN-008 — Market | Market component | [Market Engineering](domains/market/ENGINEERING.md) | Draft |
| DOMAIN-009 — Event | Event component | [Event Engineering](domains/event/ENGINEERING.md) | Draft |
| DOMAIN-010 — Configuration | Configuration component | [Configuration Engineering](domains/configuration/ENGINEERING.md) | Draft |
| DOMAIN-011 — Audit | Audit component | [Audit Engineering](domains/audit/ENGINEERING.md) | Draft |

## Mapping Rules

- Each primary engineering component traces to exactly one approved Platform Domain.
- A component implements only responsibilities owned by its traced domain.
- Components consume and publish only contracts already approved by the Platform Architecture.
- Allowed business-domain dependencies are exactly those in the approved Domain Dependency Matrix.
- Existing KR engine ownership remains unchanged; component alignment does not merge, rename, replace, or reassign engines.
- The Provider component owns external provider integration. The ADR-006 Execution Context Provider remains an Execution-domain role and is not part of the Provider component merely because both names contain “provider.”
- This Draft makes no implementation technology, code organization, or deployment decision.

## Authoritative References

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [KRONOS Platform Architecture Overview](PLATFORM_OVERVIEW.md)
- [KRONOS Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
- [KRONOS Domain Dependency Matrix](DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Domain Ownership Matrix](DOMAIN_OWNERSHIP_MATRIX.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
- [ADR-006 — Execution Context Provider Architecture](../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [PP-007 — Execution Semantics Across Markets](../principles/PP-007-Execution-Semantics-Across-Markets.md)

## Open Engineering Questions

- What approved implementation plan will sequence component realization without changing frozen domain boundaries?
- Which existing public engine outputs already satisfy each approved Platform contract, and where is additional contract-conformance work required?
- What validation evidence will be required before any component can move beyond Draft?
