# KRONOS Domain Dependency Matrix

Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Define the allowed semantic dependencies between KRONOS Platform domains.

A listed dependency authorizes consumption of an approved contract only.

It does not authorize access to producer internals, transfer semantic ownership, create implied authority, or establish runtime, endpoint, acquisition, submission, or persistence authority.

## Dependency Types

KRONOS distinguishes:

| Dependency type | Meaning |
| --- | --- |
| Business-pipeline dependency | A downstream domain consumes the owned semantic output of an upstream business domain. |
| Platform-support dependency | A platform capability supplies bounded support without joining or changing the business pipeline. |
| Contract dependency | A consumer may receive only the meaning exposed by one approved contract. |
| Runtime dependency | A separately authorized runtime relationship; architecture dependency alone does not establish it. |
| Ownership | Exclusive authority over semantic meaning; ownership is not a dependency and never follows from one. |

A support dependency shall not automatically become a business-pipeline stage.

A contract dependency shall not permit direct state access or mutation.

## Allowed Business-Pipeline Dependencies

The approved business-pipeline dependencies remain:

| Consumer Domain | Depends On |
| --- | --- |
| Instrument | None (Business Pipeline) |
| Observation | Instrument |
| Validation | Observation |
| Risk | Validation, Portfolio |
| Execution | Validation, Risk |
| Portfolio | Execution |
| Provider | None (Business) |
| Market | None (Business) |
| Event | None (Business) |
| Configuration | None (Business) |
| Audit | All domains (Read Only) |

Provider is not a business-pipeline stage.

## Allowed Platform-Support and Contract Dependencies

| Consumer | Supporting Producer | Governing Boundary | Scope | Dependency Effect |
| --- | --- | --- | --- | --- |
| Instrument | Provider | EAIC-002 — Provider → Instrument Submission Contract | Instrument Master only | Instrument may consume an EAIC-002-conforming Submission Unit for possible interpretation without accessing Provider Catalogue internals or acquiring Provider ownership. |
| Observation | Instrument | Applicable approved Instrument-to-Observation contract | Canonical Instrument identity attribution where governed | Observation may attribute its facts to canonical Instrument identity without acquiring Instrument ownership. |
| Applicable Product | Instrument | Separately approved explicit product-consumption contract | Canonical Instrument outputs approved for that product | Swing, Intraday, or a future product may consume canonical Instrument outputs without acquiring Instrument ownership or accessing Provider-owned information. |
| Audit | All domains | Approved published audit evidence contracts | Read only | Audit may record published evidence without becoming an upstream dependency or acquiring the recorded meaning. |

The Provider-to-Instrument support path is:

```text
Provider
    ↓
EAIC-002 — Provider → Instrument Submission Contract
    ↓
Instrument
```

Provider produces eligible Provider-owned Submission Units.

Instrument consumes the contract boundary.

Technical receipt does not imply contract validity, interpretation admission, semantic acceptance, interpretation success, canonical identity, Provider mapping, or product eligibility.

The support path does not permit Provider to populate Instrument directly or Instrument to mutate Provider state.

Recording this dependency does not activate ADR-009 or EAIC-002 and creates no migration-execution, runtime, endpoint, submission, acquisition, or persistence authority.

## Provider Dependency Boundary

Provider owns Instrument Master acquisition independently and has no Instrument business dependency for acquisition.

Provider may publish eligible Provider-owned information through EAIC-002 only when the separately governed contract and submission authorities exist.

Provider Context, Provider Capability, Provider Entitlement, Dataset Permission, Acquisition Authority, and runtime authority remain independent prerequisites or authorities where separately governed.

No one prerequisite or authority implies another.

Provider Instrument Master acquisition does not depend on:

- Swing scope;
- Intraday scope;
- any product universe membership;
- product eligibility;
- canonical Instrument identity before acquisition;
- product validation;
- Risk Approval; or
- Execution.

Provider acquisition shall not be filtered by current product demand or product membership.

## Instrument Dependency Boundary

Instrument depends on EAIC-002-conforming submissions only for Provider-supplied Instrument Master information presented for possible interpretation.

This platform-support and contract dependency does not make Provider part of the business pipeline.

Instrument:

- shall not depend directly on Provider Catalogue internals;
- shall not depend on Swing, Intraday, or another product for canonical identity;
- shall not acquire Provider datasets;
- shall not own or redefine Submission Eligibility; and
- shall not depend on product decisions.

The absence of a Provider submission does not transfer acquisition responsibility to Instrument.

## Explicit Product-Consumption Dependencies

Swing, Intraday, and future products may depend on canonical Instrument outputs only through separately approved explicit product-consumption contracts.

Products shall not depend directly on:

- Provider Catalogue;
- Provider Records;
- Provider Snapshots;
- EAIC-002 envelopes;
- Submission Eligibility; or
- Provider acquisition internals.

Product consumption creates no reverse Instrument dependency on a product.

## Observation, Validation, and Risk Boundaries

Observation depends on canonical Instrument identity for attribution where governed.

Observation shall not depend directly on Provider acquisition, Provider Catalogue, Provider Records, Provider Snapshots, or EAIC-002 envelopes.

Validation retains its existing dependency on Observation-owned meaning and shall not acquire ownership of Instrument interpretation.

Risk retains its existing dependencies on Validation and Portfolio. Risk shall not acquire ownership of Provider acquisition, Provider submission, Instrument interpretation, or product decisions.

Provider shall not depend on Risk Approval, and Instrument shall not depend on product decisions.

ADR-009 and EAIC-002 create no new Validation or Risk dependency.

## Dataset Boundary

The Provider-to-Instrument dependency introduced by this migration applies only to the Instrument Master dataset governed by ADR-009 and EAIC-002.

It does not govern:

- Futures OI;
- Options OI;
- quotes;
- historical data;
- streaming;
- market depth;
- option-chain data; or
- any other separately governed Provider dataset.

Each excluded dataset requires its own separately approved capability, Dataset Permission, Acquisition Authority, engineering design, runtime authority, and applicable contract dependency.

## Cross-Provider Support

Each Provider, including a future Provider such as IBKR, shall use isolated Provider-and-Dataset Catalogue Partitions.

Eligible Instrument Master submissions may use the same governed contract family only through the separately approved Provider-specific and dataset-specific boundary.

No direct Provider-to-Provider dependency is created.

Cross-Provider reconciliation remains Instrument-owned and shall not create a Provider-to-Provider dependency.

## Business Pipeline Preservation

The canonical business pipeline remains unchanged:

```text
Instrument
    ↓
Observation
    ↓
Validation
    ↓
Risk
    ↓
Execution
    ↓
Portfolio
```

Provider → EAIC-002 → Instrument is a platform-support and contract path, not a business-pipeline stage.

Market, Configuration, Event, and Audit retain their approved platform-support or read-only relationships and do not become business-pipeline stages.

## Dependency Rules

1. Dependencies are directional and contract-based.
2. A consumer may use only meanings published by the producer.
3. A consumer must not reconstruct, override, or supplement the producer's owned meaning.
4. Transitive dependency does not authorize direct access to an upstream domain.
5. Instrument begins the business pipeline and has no business-domain dependency.
6. Risk consumes the previously established Portfolio state together with current Validation judgment.
7. Execution consumes Validation judgment and Risk approval; it does not produce either.
8. Portfolio consumes completed Execution outcomes and publishes the resulting portfolio state for later decisions.
9. The Risk–Execution–Portfolio relationship is sequential across a business decision cycle and must not create circular authority.
10. Provider, Market, Event, and Configuration have no business judgment dependency. Their platform contracts may support domains without joining the business decision chain.
11. Audit may consume all published domain contracts read-only and must not become an upstream business dependency.
12. Any dependency not listed here requires an approved Architecture Decision Record.
13. A dependency shall not transfer semantic ownership or create duplicate ownership.
14. Architecture dependency shall not create implicit, runtime, endpoint, submission, acquisition, or persistence authority.
15. Feedback, evidence, provenance, rejection, and audit flows shall be classified separately from authoritative semantic dependencies.
16. A contract consumer shall not mutate producer-owned state through the contract.

## Cycle Prohibitions

The dependency model shall not create:

- Provider → Instrument → Provider;
- Instrument → Product → Instrument;
- Provider → Product → Provider; or
- Observation → Provider → Observation.

Provider submission evidence, Instrument contract outcomes, product-consumption evidence, and audit evidence are attributable evidence flows. They do not reverse an authoritative dependency.

The existing Risk–Execution–Portfolio sequence remains governed across business decision cycles and shall not become circular authority within one decision cycle.

## Existing KRONOS Alignment

- KR-370 remains upstream of KR-380 and owns direction and readiness.
- KR-380 consumes approved direction/readiness and Execution Context without reinterpreting either.
- KR-390 consumes confirmed KR-380 execution outcomes for objective model-trade state.
- Existing narrow adapter exceptions remain governed by ADL-003 and do not create new domain dependencies.
- Provider Capability remains Provider-scoped under ADR-007.
- Provider Entitlement remains account-scoped and Provider-owned under ADR-008.
- ADR-009 and EAIC-002 add one Instrument-Master-only platform-support and contract path without changing the canonical business pipeline.
- The migrated Domain Ownership Matrix remains authoritative for semantic ownership; no dependency in this document alters it.

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Ownership Matrix](DOMAIN_OWNERSHIP_MATRIX.md)
- [ADR-007 — Provider Capability Assessment Architecture](domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Provider Domain Architecture](domains/provider/ARCHITECTURE.md)
- [Instrument Domain Architecture](domains/instrument/ARCHITECTURE.md)
- [ADL-003 — Execution Context Adapters](../ADL-003-Execution-Context-Adapters.md)
- [ADR-006 — Execution Context Provider Architecture](../adr/ADR-006-Execution-Context-Provider-Architecture.md)
