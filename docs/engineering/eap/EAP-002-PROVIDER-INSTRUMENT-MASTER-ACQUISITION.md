# EAP-002 — Provider Instrument Master Acquisition Engineering Architecture

**Document ID:** EAP-002
**Title:** Provider Instrument Master Acquisition Engineering Architecture
**Version:** 2.0
**Status:** Approved
**Canonical Status:** Approved Canonical Engineering Architecture
**Classification:** Engineering Architecture Package
**Owner:** Engineering Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Approved By:** Chief Architect
**Repository Location:** `docs/engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md`
**Workflow Stage:** Repository Publication
**Governing Architecture:** ADR-009 Version 1.0
**Governing Migration:** MIG-001 Version 0.1
**Upstream EAP:** EAP-001 Version 1.0
**Downstream Contract:** EAIC-002 Version 0.1
**Activation State:** Inactive — Pending RC-03 Repository Synchronization and RC-04 Activation Governance
**EDD-004 Drafting Authorization:** None
**Implementation Authorization:** None
**Runtime Authority:** None
**Provider Endpoint Invocation Authority:** None
**Persistence Authority:** None
**Provider-to-Instrument Submission Authority:** None

---

# 1. Purpose

EAP-002 translates the approved Provider-bounded Instrument Master acquisition architecture into provider-neutral and implementation-neutral engineering contracts.

It defines engineering meaning for dataset-bounded acquisition, complete returned-dataset preservation, immutable Provider Snapshots, Provider-and-Dataset Catalogue Partitions, Provider Record dispositions, catalogue continuity, retention obligations, and deterministic Submission Eligibility for EAIC-002.

EAP-002 terminates at the Provider-owned EAIC-002 submission boundary. It does not perform contract delivery, Instrument interpretation, canonical identity establishment, Provider mapping, product selection, Observation formation, persistence implementation, or runtime activity.

# 2. Migration Effect

Version 2.0 replaces the product-bounded acquisition contracts in EAP-002 Version 1.0.

The replacement implements the approved direction:

> Acquire Broadly. Interpret Canonically. Consume Explicitly.

The following rules now govern EAP-002:

- acquisition is bounded by one Provider, dataset, operation, capability, permission, context, authority, environment, security boundary, retention boundary, and licensing boundary;
- acquisition is not bounded by Swing, Intraday, Options, a current strategy, a current market, or another product universe;
- every safely preservable returned record is preserved regardless of current product use;
- Provider information remains external, Provider-owned, product-neutral, and non-canonical;
- Provider Catalogue partitions remain strictly isolated by Provider and dataset;
- product membership is not a Submission Eligibility condition; and
- products shall not consume Provider Catalogue records directly.

This publication changes engineering architecture only. It does not activate ADR-009, EAIC-002, acquisition, preservation, persistence, submission, interpretation, or any product.

# 3. Governing Authority

EAP-002 is subordinate to:

- PLATFORM-000 — KRONOS Platform Constitution;
- ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture;
- MIG-001 — ADR-009 Coordinated Architecture Migration Package;
- EAIC-002 — Provider → Instrument Submission Contract;
- DOMAIN-006 — Provider Domain Architecture;
- DOMAIN-001 — Instrument Domain Architecture;
- the Domain Ownership Matrix;
- the Domain Dependency Matrix;
- DATA_FLOW;
- EAP-001 — Configuration-to-Provider Authenticated Context Engineering Architecture;
- EAS-001 through EAS-007; and
- applicable approved Configuration, capability, entitlement, security, retention, and governance authorities.

ADP-001H and ADP-001C are superseded historical predecessors. They grant no active authority and shall not constrain or define this Version 2.0 boundary.

ADP-001A, ADP-001B, ADP-001D, ADP-001E, ADP-001I, and ADP-001J remain applicable only within their migrated canonical meanings. Product requirements shall not narrow Provider acquisition or Provider preservation.

# 4. Scope

EAP-002 defines engineering architecture for:

- Acquisition Eligibility;
- separately established Dataset Permission and Acquisition Authority evidence;
- Approved, Requested, and Received Acquisition Scope;
- technical acquisition activity and result;
- Complete, Partial, Empty, Missing, Unsupported, and Failed Acquisition Outcomes;
- safe normalization of Provider information;
- immutable Provider Snapshots;
- Provider Catalogue and Provider-and-Dataset Catalogue Partitions;
- Provider Record and Provider Record Identity;
- complete safely preservable returned-record preservation;
- structural, evidence-quality, quarantine, interpretation-support, and submission dispositions;
- Provider Snapshot currentness and non-destructive supersession;
- record-added, record-absent, record-changed, token-reuse, and symbol-change evidence;
- deterministic Submission Eligibility;
- Provider and acquisition provenance;
- security, licensing, retention, and deletion-authority separation;
- non-sensitive observability; and
- engineering verification.

# 5. Explicit Exclusions

EAP-002 does not define or authorize:

- a Provider endpoint, SDK, route, request, response, parser, adapter, transport, retry, schedule, or polling mechanism;
- an executable workflow or state machine;
- database, schema, file, cache, repository, index, service, API, queue, transaction, deployment, or persistence technology;
- credentials, Authentication Material, secret custody beyond EAP-001, or sensitive logging;
- Dataset Permission, Acquisition Authority, Live Acquisition Authority, Persistence Authority, Retention Authority, Deletion Authority, or Submission Authority;
- Instrument interpretation, canonical identity, classification, relationship, lifecycle, Provider mapping, or cross-Provider reconciliation;
- product universe, product eligibility, product consumption, strategy, or trading meaning;
- Observation, Market, Validation, Risk, Execution, Portfolio, Event, or Audit meaning;
- historical data, quotes, streaming, market depth, OI, option-chain, account, or other non-Instrument-Master datasets;
- implementation, production code, deployment, or runtime behavior; or
- EDD-004 drafting.

# 6. Engineering Ownership and Dependency Direction

| Engineering meaning | Semantic owner |
| --- | --- |
| Configuration eligibility and Operational Configuration Validity | Configuration |
| Provider Capability | Provider |
| Provider Entitlement | Provider |
| Provider Operational Availability and Provider Usability | Provider |
| Provider Context | Provider |
| Provider Instrument Master acquisition | Provider |
| Provider Snapshot and Provider Record | Provider |
| Provider Catalogue and its partitions | Provider |
| Provider Record dispositions and Submission Eligibility | Provider |
| Instrument Interpretation Admission and later Instrument meaning | Instrument, outside EAP-002 |
| Canonical Instrument Catalogue | Instrument, outside EAP-002 |
| Product universe and Product Eligibility | Each product, outside EAP-002 |

The engineering dependency direction is:

```text
Configuration and Provider precondition contracts
                    ↓
Provider Instrument Master acquisition
                    ↓
Provider Snapshot
                    ↓
Provider-and-Dataset Catalogue Partition
                    ↓
Provider Record disposition
                    ↓
Submission Eligibility
                    ↓
EAIC-002 Provider → Instrument Submission Contract
```

No reverse dependency or ownership transfer is authorized.

# 7. Acquisition Entry Contract

The acquisition boundary may be represented as eligible only when the separately governed entry conditions required by ADR-009 are independently established for one exact Provider, Instrument Master dataset, operation, environment, and operational context.

The contract shall preserve non-sensitive references to:

- Provider identity;
- dataset identity;
- operation identity;
- current Provider Capability evidence;
- Dataset Permission;
- entitlement evidence where applicable;
- eligible Runtime Configuration;
- Operational Configuration Validity;
- valid Provider Context;
- Context Reuse Eligibility where applicable;
- Provider Operational Availability;
- Provider Usability;
- exact Acquisition Authority;
- environment and security classification;
- retention and licensing treatment; and
- absence of an unresolved blocking dependency.

No entry condition implies another. EAP-002 consumes these authorities and meanings; it does not create, extend, replace, or infer them.

# 8. Acquisition and Scope Contracts

## 8.1 Acquisition Eligibility Contract

Represents the Provider-owned determination that every required entry condition is established for one bounded acquisition. It is not Acquisition Authority, activity, technical success, or permission to invoke an endpoint.

## 8.2 Approved Acquisition Scope Contract

Represents the maximum approved Provider, Instrument Master dataset, operation, context, environment, security, authority, retention, and licensing boundary. It is not bounded by a product universe.

## 8.3 Requested Acquisition Scope Contract

Represents the complete approved Instrument Master dataset requested for one acquisition. It shall remain within Approved Acquisition Scope and shall not be reduced by current product use.

## 8.4 Received Acquisition Scope Contract

Represents what was actually received and safely established, including actual coverage, record count, missingness, excess, partiality, duplicates, malformed information, ambiguity, inconsistency, quarantine, limitations, and comparison with Requested Acquisition Scope.

Approved, Requested, and Received Acquisition Scope shall remain independent. Technical success shall not establish completeness.

## 8.5 Technical Acquisition Result Contract

Represents exactly one bounded technical result:

- `TECHNICAL_ACQUISITION_SUCCESS`; or
- `TECHNICAL_ACQUISITION_FAILURE`.

The technical result does not establish the Acquisition Outcome, Provider availability, dataset completeness, preservation authority, or submission eligibility.

## 8.6 Acquisition Outcome Contract

Represents exactly one Provider-owned outcome:

| Outcome | Engineering meaning |
| --- | --- |
| `COMPLETE` | Received scope covers Requested scope within known Provider and technical limits. |
| `PARTIAL` | Some but not all Requested scope was received or safely preserved. |
| `EMPTY` | The operation produced no Provider Records. |
| `MISSING` | Required response or scope evidence was absent. |
| `UNSUPPORTED` | The Provider operation or bounded scope was explicitly unsupported. |
| `FAILED` | The bounded acquisition produced no valid technical result for the approved operation. |

Technical success may coexist with `PARTIAL`, `EMPTY`, `MISSING`, or bounded limitations. Empty and Missing do not mean zero Instruments or Instrument non-existence.

# 9. Provider Snapshot Contract

Where safe Provider Records exist, one completed or partially completed acquisition shall establish one immutable Provider Snapshot within exactly one Provider-and-Dataset Catalogue Partition.

The snapshot shall preserve:

- partition, Provider, dataset, operation, acquisition, and snapshot identities;
- request-initiation, response-receipt, snapshot-closure, and acquisition-effective times as distinct meanings;
- Provider-supplied generation or effective time as a separate Provider assertion where present;
- Approved, Requested, and Received Acquisition Scope;
- technical result and Acquisition Outcome;
- capability, authority, context, Configuration, environment, security, retention, and licensing references;
- Provider and acquisition provenance;
- record count, missingness, partiality, duplicates, malformed evidence, ambiguity, inconsistency, quarantine, and limitations; and
- currentness and supersession relationships where applicable.

A closed Provider Snapshot is immutable. A later acquisition creates another snapshot and shall not mutate the earlier snapshot.

# 10. Provider Catalogue Contract

Provider Catalogue is one first-class Provider-owned platform capability composed of strictly isolated Provider-and-Dataset Catalogue Partitions.

Each partition shall be uniquely bounded by at least:

- Provider identity;
- dataset identity; and
- operational environment or Provider Context class where materially required.

Each partition contains its own Provider Snapshots, Provider Records, identities, dispositions, scope, currentness, supersession, retention, and provenance.

No Provider Record, snapshot identity, currentness state, or supersession relationship may cross a partition. Provider shall not reconcile identities across Providers. Products, Observation, Validation, Risk, Execution, and Portfolio shall not consume partitions directly.

The engineering contract defines the catalogue’s meaning and boundaries only. It does not define a persistence implementation.

# 11. Provider Record Contract

A Provider Record is a safely normalized, Provider-owned, product-neutral, non-canonical, snapshot-bounded representation of one returned Instrument Master record.

Where supplied and permitted, it shall preserve Provider identity, Provider Record Identity, Provider tokens, exchange tokens, Provider vocabulary, symbol, name or underlying assertion, exchange, segment, Instrument type, expiry, strike, lot size, tick size, auxiliary metadata, snapshot membership, provenance, limitations, missingness, ambiguity, duplicate and inconsistency evidence, preservation fact, and every applicable disposition.

Provider Record Identity is unique only within one Provider Snapshot and is scoped by Provider, dataset, snapshot, and a Provider-record identity component. A Provider token, exchange token, symbol, or row position shall not alone become a permanent Provider Record Identity or canonical Instrument identity.

Every safely preservable returned record shall be preserved. Current product inactivity or exclusion is not a preservation restriction.

# 12. Provider Record Disposition Contract

Provider Record disposition is multidimensional and shall not become an Instrument lifecycle state machine.

## 12.1 Preservation Fact

Every preserved record has exactly one preservation fact:

- `ACQUIRED`.

## 12.2 Structural Disposition

Every preserved record has exactly one:

- `STRUCTURALLY_VALID`; or
- `STRUCTURALLY_INVALID`.

Structural validity establishes safe catalogue structure only, not semantic correctness.

## 12.3 Evidence-Quality Flags

Every preserved record has zero or more:

- `AMBIGUOUS`;
- `DUPLICATE`;
- `INTERNALLY_INCONSISTENT`;
- `MISSING_REQUIRED_PROVIDER_ASSERTION`;
- `UNRECOGNIZED_PROVIDER_VOCABULARY`; or
- `PROVIDER_LIMITATION_PRESENT`.

Absence of a flag does not establish correctness, completeness, support, identity, or product meaning.

## 12.4 Quarantine Disposition

Every preserved record has exactly one:

- `NOT_QUARANTINED`; or
- `QUARANTINED`.

Quarantine preserves evidence and prohibits unsafe submission. It does not delete the record or establish Instrument invalidity.

## 12.5 Interpretation-Support Disposition

Every preserved record has exactly one:

- `INTERPRETATION_SUPPORT_ESTABLISHED`;
- `INTERPRETATION_SUPPORT_LIMITED`; or
- `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`.

This is Provider-owned support evidence only. It does not perform Instrument interpretation.

## 12.6 Submission Disposition

Every evaluated Provider Record or explicitly bounded Submission Unit has exactly one:

- `SUBMISSION_ELIGIBLE`; or
- `SUBMISSION_INELIGIBLE`.

Product membership shall not participate in this determination.

## 12.7 Mandatory Precedence

- `STRUCTURALLY_INVALID` requires `QUARANTINED`, `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`, and `SUBMISSION_INELIGIBLE`.
- `QUARANTINED` requires `SUBMISSION_INELIGIBLE`.
- materially unresolved `INTERNALLY_INCONSISTENT` evidence requires quarantine and submission ineligibility unless an approved deterministic Provider rule establishes non-materiality while preserving the inconsistency.
- `DUPLICATE` requires every occurrence and duplicate relationship to remain preserved; no record may be selected silently.
- Provider ambiguity may be submitted only where it is bounded, preserved, safe, and explicitly permitted for Instrument evaluation without Provider choosing canonical meaning.
- `UNRECOGNIZED_PROVIDER_VOCABULARY` requires at least `INTERPRETATION_SUPPORT_LIMITED`.

# 13. Submission Eligibility and EAIC-002 Output

A Provider Record or explicitly bounded multi-record Submission Unit may be `SUBMISSION_ELIGIBLE` only when every applicable EAIC-002 Provider-side condition is established, including:

- Provider, dataset, partition, snapshot, record, and Submission Unit identity;
- closed immutable snapshot membership;
- `STRUCTURALLY_VALID`;
- `NOT_QUARANTINED`;
- required non-sensitive Provider and acquisition provenance;
- attributable source, operation, context, and snapshot;
- required Provider assertions;
- safe exclusion of sensitive, raw, SDK, and transport-private content;
- deterministic duplicate and inconsistency treatment;
- bounded ambiguity treatment;
- preserved limitations and missingness;
- no need for Provider to infer canonical Instrument meaning; and
- no architectural or authority prohibition.

Failure of any mandatory condition requires `SUBMISSION_INELIGIBLE` with preserved reason classification, non-sensitive evidence, provenance, identities, and applicable flags.

The EAP-002 output is Provider-owned submission meaning conforming to EAIC-002. It does not deliver the unit, establish Submission Authority, validate the EAIC-002 envelope, admit interpretation, or create Instrument meaning.

# 14. Catalogue Continuity and Retention

Snapshot currentness and supersession remain Provider-owned, non-destructive meanings.

- a later comparable complete snapshot may supersede an earlier snapshot as current Provider reference evidence;
- a Partial, Empty, Missing, Unsupported, or Failed outcome shall not automatically displace the last applicable complete snapshot;
- Record Added does not establish a new canonical Instrument;
- Record Absent does not establish expiry, delisting, retirement, deletion, non-support, product exclusion, or Instrument non-existence;
- Record Changed does not mutate canonical identity, lifecycle, historical observations, or product eligibility;
- Provider token reuse does not establish identity or mapping continuity; and
- symbol change remains Provider evidence for later Instrument evaluation.

Acquisition, preservation, persistence, retention, deletion, and Audit authorities remain separate. EAP-002 grants none of them.

Normalized evidence shall remain conservatively retainable under approved restrictions, including the current and immediately preceding comparable completed snapshots and all evidence referenced by submission, mapping, canonical identity, historical attribution, verification, or Audit. EAP-002 grants no destructive deletion authority.

# 15. Security and Provenance

Raw Provider payloads, SDK objects, SDK exceptions, credentials, Authentication Material, authorization headers, secret-bearing URLs, and private transport state shall remain adapter-private and shall not enter Provider Records, catalogue contracts, EAIC-002 content, observability, diagnostics, or Audit evidence.

Provider and acquisition provenance shall preserve the non-sensitive authorities, identities, timing meanings, scope, result, outcome, adapter and SDK basis where applicable, limitations, snapshot lineage, disposition evidence, and retention treatment required by ADR-009 and EAIC-002.

Provider provenance, acquisition provenance, interpretation provenance, and product-consumption provenance remain distinct.

# 16. Engineering Observability

Observability may expose only non-sensitive:

- boundary and conformance status;
- Provider, dataset, partition, snapshot, acquisition, and record reference;
- scope comparison;
- technical result and Acquisition Outcome;
- record counts and evidence-quality categories;
- quarantine, interpretation-support, and submission dispositions;
- currentness and supersession status;
- provenance completeness;
- authority-reference presence without authority material; and
- boundary violations.

Observability shall not reinterpret Provider meaning, expose protected material, imply canonical identity, or represent product exclusion as acquisition or preservation failure.

# 17. Mandatory Engineering Invariants

1. Provider acquisition is dataset-bounded and not product-bounded.
2. Every safely preservable returned record is preserved regardless of current product use.
3. Provider Records remain Provider-owned, product-neutral, non-canonical, and snapshot-bounded.
4. Provider Catalogue partitions remain strictly isolated by Provider and dataset.
5. Requested and Received Acquisition Scope remain distinct.
6. Technical success does not establish completeness.
7. Provider record preservation does not imply Submission Eligibility.
8. Submission Eligibility does not imply EAIC-002 Submission Authority or Interpretation Admission.
9. Product membership does not affect acquisition, preservation, or Submission Eligibility.
10. Provider dispositions do not become Instrument lifecycle.
11. Snapshot currentness and supersession do not become Instrument lifecycle.
12. Provider shall not reconcile canonical identity or mappings across Providers.
13. Raw Provider payloads and SDK objects remain adapter-private.
14. No sensitive information enters governed records, provenance, observability, or downstream contracts.
15. Acquisition, preservation, persistence, retention, deletion, submission, interpretation, runtime, and product-consumption authorities remain independent.
16. EAP-002 creates no Instrument, Observation, Market, Validation, Risk, Execution, Portfolio, Event, or Audit meaning.
17. EAP-002 remains implementation-neutral.
18. EDD-004 remains unauthorized.

# 18. Engineering Verification

Engineering Verification shall confirm:

- traceability to ADR-009, MIG-001, DOMAIN-006, EAIC-002, and EAP-001;
- removal of product-universe filtering from acquisition, preservation, and submission eligibility;
- complete returned-record preservation within the authorized dataset boundary;
- correct Provider Catalogue partition isolation;
- immutable snapshot and non-destructive supersession meaning;
- independent disposition cardinality and mandatory precedence;
- deterministic Submission Eligibility aligned with EAIC-002;
- absence of Instrument interpretation, canonical identity, product eligibility, or Observation meaning;
- authority separation and explicit inactive state;
- security and provenance conformance;
- metadata, register, links, and repository path consistency; and
- absence of implementation, runtime, persistence technology, endpoint invocation, or EDD-004 authority.

# 19. Publication Record

Version 2.0 is the approved canonical engineering replacement for EAP-002 Version 1.0 under RC-02 — Engineering Architecture Publication.

Publication establishes repository authority for this engineering architecture only. RC-03 Repository Synchronization and RC-04 Activation Governance remain separate and subsequent. EDD-004 drafting remains prohibited until explicitly authorized after those stages.

# 20. Related Approved Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../architecture/migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../architecture/interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [Instrument Domain Architecture](../../architecture/platform/domains/instrument/ARCHITECTURE.md)
- [EAP-001 — Configuration-to-Provider Authenticated Context Engineering Architecture](EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
