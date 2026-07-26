# KRONOS Domain Ownership Matrix

Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Assign each platform-level semantic responsibility to exactly one KRONOS domain or explicitly governed product authority.

## Single Ownership Matrix

| Responsibility | Owner |
| --- | --- |
| Provider Integration | Provider |
| Provider Context | Provider |
| Provider Capability | Provider |
| Provider Entitlement | Provider |
| Provider Dataset Acquisition | Provider |
| Provider Catalogue | Provider |
| Provider-and-Dataset Catalogue Partitions | Provider |
| Provider Catalogue Partition Identity | Provider |
| Provider Snapshot | Provider |
| Provider Snapshot Identity | Provider |
| Provider Snapshot Currentness | Provider |
| Provider Snapshot Supersession | Provider |
| Provider Record | Provider |
| Provider Record Identity | Provider |
| Provider Record Dispositions | Provider |
| Submission Eligibility | Provider |
| Provider Provenance | Provider |
| Provider Acquisition Provenance | Provider |
| Approved, Requested, and Received Acquisition Scope | Provider |
| Technical Acquisition Result | Provider |
| Acquisition Outcome | Provider |
| Instrument Interpretation | Instrument |
| Interpretation Processing Status | Instrument |
| Interpretation Outcome | Instrument |
| Canonical Identity Decision | Instrument |
| Instrument Identity, including Canonical Instrument Identity | Instrument |
| Canonical Instrument Classification | Instrument |
| Provider Mapping | Instrument |
| Provider Mapping Status | Instrument |
| Cross-Provider Reconciliation | Instrument |
| Instrument Relationships | Instrument |
| Instrument Lifecycle Semantics | Instrument |
| Canonical Instrument Catalogue Publication | Instrument |
| Product Universe | Applicable Product |
| Product Eligibility | Applicable Product |
| Product Consumption | Applicable Product |
| Product Evidence Requirements | Applicable Product |
| Product Validation Requirements | Applicable Product |
| Product Decision Semantics | Applicable Product |
| Product Risk Interpretation | Applicable Product |
| Market Facts | Observation |
| Observations | Observation |
| Observation History | Observation |
| Observation Evidence | Observation |
| Business Judgment | Validation |
| Validation Programmes | Validation |
| Validation Outcomes | Validation |
| Risk Approval | Risk |
| Risk Semantics | Risk |
| Orders | Execution |
| Positions | Portfolio |
| Market Schedule | Market |
| Runtime Configuration | Configuration |
| Platform Events | Event |
| Audit Trail | Audit |

## Ownership Rules

1. Each listed responsibility has exactly one owner.
2. Ownership includes the authoritative semantic meaning of the responsibility.
3. Consumers may use an owned contract but must not recreate its meaning.
4. Platform support does not acquire ownership of the business information it carries.
5. Audit ownership is limited to the Audit Trail and does not include the responsibilities being observed.
6. New responsibilities require an explicit owner before approval or implementation.
7. Reassignment of a listed responsibility requires an approved Architecture Decision Record.
8. Single semantic ownership shall be preserved across architecture, engineering, implementation, and runtime representation.
9. No responsibility may have duplicated, implied, or unrecorded ownership.
10. Dependency on an owner does not transfer, share, or weaken that owner's responsibility.
11. Implementing, storing, transporting, validating, observing, or auditing owned meaning does not confer ownership.
12. An interface preserves the ownership on each side of its boundary and shall not create ownership leakage.

## Provider Ownership Boundary

Provider exclusively owns the Provider responsibilities listed in the Single Ownership Matrix.

Provider does not own:

- canonical Instrument identity;
- Instrument interpretation;
- canonical Instrument classification;
- Provider mapping;
- cross-Provider reconciliation;
- Canonical Instrument Catalogue publication;
- product universes;
- product eligibility;
- Observations;
- Validation;
- Risk; or
- Execution.

Provider-native identifiers, records, snapshots, dispositions, scope, outcomes, and provenance remain Provider-owned evidence. They shall not become canonical Instrument or product meaning.

## Instrument Ownership Boundary

Instrument exclusively owns the Instrument responsibilities listed in the Single Ownership Matrix.

Instrument does not own:

- Provider acquisition;
- Provider Catalogue;
- Provider-and-Dataset Catalogue Partitions;
- Provider Snapshots;
- Provider Records;
- Provider Record Identity;
- Provider-native provenance; or
- Submission Eligibility.

Instrument shall preserve Provider attribution without acquiring Provider-native meaning.

## Product Ownership Boundary

Swing, Intraday, and each future product exclusively own their respective:

- product universe;
- product eligibility;
- product consumption;
- evidence requirements;
- validation requirements;
- decision semantics; and
- risk interpretation.

Product ownership is bounded to the applicable product context.

Products do not own:

- canonical Instrument identity;
- Provider mappings;
- Provider Catalogue; or
- Submission Eligibility.

Product evidence and validation requirements do not transfer ownership of Observation evidence, Validation outcomes, Business Judgment, Risk Approval, or Risk semantics.

## Observation Ownership Boundary

Observation owns Observations, Observation History, and Observation Evidence.

Observation does not own:

- canonical Instrument identity;
- Provider acquisition; or
- product eligibility.

## Validation Ownership Boundary

Validation owns Validation Programmes, Validation Outcomes, and Business Judgment.

Validation does not own:

- canonical Instrument identity;
- Provider acquisition;
- Provider-to-Instrument submission; or
- Instrument interpretation.

## Risk Ownership Preservation

Risk retains exclusive ownership of Risk Approval and Risk semantics.

ADR-009, Provider acquisition, Instrument interpretation, product risk interpretation, and EAIC-002 do not transfer, duplicate, or reduce Risk authority.

## EAIC-002 Ownership Boundary

The governed ownership sequence is:

```text
Provider
    ↓
EAIC-002 — Provider → Instrument Submission Contract
    ↓
Instrument
```

Provider retains ownership of acquisition, Provider Catalogue content, Provider Records, Provider dispositions, Submission Eligibility, scope, outcomes, and Provider provenance at the interface.

Instrument retains ownership of interpretation, canonical identity, canonical classification, Provider mapping, cross-Provider reconciliation, relationships, lifecycle semantics, and Canonical Instrument Catalogue publication after the interface admits an eligible Submission Unit.

EAIC-002 transports governed meaning without transferring ownership across the interface.

Provider shall not populate Instrument directly, and Instrument shall not access or mutate Provider Catalogue internals.

## Existing KRONOS Alignment

- KR-200 retains its approved engine responsibilities. Its instrument-identity responsibility aligns to Instrument; its approved Exchange Availability production aligns to Market.
- Existing evidence engines retain their individual ENGINE_OWNERSHIP boundaries while their published market facts align to Observation.
- Business Judgment is a domain-level responsibility and does not merge the distinct KR-360 confidence and KR-370 decision engine responsibilities.
- KR-370 remains the engine owner of direction and BUY READY / SELL READY within Business Judgment.
- KR-380 remains the engine owner of final execution timing and BUY NOW / SELL NOW within Execution.
- The Orders assignment reserves order semantics to Execution; the current KRONOS execution contract does not place broker orders.
- KR-390 remains the owner of the objective KRONOS model trade within Portfolio. No personal broker-position ownership is introduced.
- KR-400 retains confirmed alert-event ownership within Event.
- Provider Integration does not redefine the separate Execution Context Provider role approved by ADR-006.
- Provider Capability remains Provider-scoped under ADR-007.
- Provider Entitlement remains account-scoped and Provider-owned under ADR-008.
- ADR-009 and EAIC-002 preserve the separation among Provider acquisition, Instrument canonical meaning, explicit product consumption, Observation facts, Validation outcomes, and Risk authority.

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [ADR-007 — Provider Capability Assessment Architecture](domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Provider Domain Architecture](domains/provider/ARCHITECTURE.md)
- [Instrument Domain Architecture](domains/instrument/ARCHITECTURE.md)
- [Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
