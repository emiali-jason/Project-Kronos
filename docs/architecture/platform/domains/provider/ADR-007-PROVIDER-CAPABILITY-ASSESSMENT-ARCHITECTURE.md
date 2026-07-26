# ADR-007 — Provider Capability Assessment Architecture

**Document ID:** ADR-007
**Title:** Provider Capability Assessment Architecture
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Approved Canonical Architecture
**Classification:** Architecture Decision Record
**Owner:** Chief Architect
**Prepared By:** Codex Engineering Team
**Approved By:** Chief Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/architecture/platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md`
**Decision Scope:** Platform Provider Domain
**Architecture Impact:** Bounded Provider Capability Assessment authority
**Engineering Impact:** None
**Runtime Impact:** None
**EDD-002 Drafting Authorization:** None
**Implementation Authorization:** None

---

# 1. Purpose

This document defines the platform-wide architecture for Provider Capability Assessment within Project KRONOS.

Provider Capability Assessment determines, from approved evidence, whether a defined Provider technical capability is supported by a Provider and whether KRONOS has an approved implementation for that capability.

This architecture prevents Provider capability from being confused with:

- Account Entitlement;
- Service Availability;
- Dataset Permission;
- Acquisition Authority;
- Runtime Observation;
- business meaning; or
- implementation authority.

This document authorizes assessment architecture only. It authorizes no Provider operation, acquisition, Engineering Design Document, implementation or runtime activity.

# 2. Authority and Applicability

This architecture applies to every KRONOS product and engineering capability that needs to establish Provider capability meaning.

It derives from:

- PLATFORM-000 — KRONOS Platform Constitution;
- DOMAIN-006 — Provider Domain;
- Domain Ownership Matrix;
- Domain Dependency Matrix;
- ENGINE_OWNERSHIP;
- DATA_FLOW;
- ADP-001A — Swing Phase 1 Market Data Inventory;
- ADP-001G — Configuration → Provider Authentication Boundary;
- ADP-001H — Provider Instrument Master Acquisition Capability and Contract;
- EAP-001 — Configuration-to-Provider Authenticated Context Engineering Architecture;
- EDD-001 — Provider Access and Provider Context Engineering Design;
- DOC-001 — Document Identification, Classification & Metadata Standard; and
- GOV-002 — KRONOS Governance Lifecycle.

Official Provider documentation and approved SDK evidence may supply Provider evidence. They shall not redefine KRONOS architecture.

Where Provider documentation, SDK behaviour or implementation conflicts with canonical KRONOS architecture, canonical KRONOS architecture shall prevail.

## 2.1 Architectural Stability Principle

Provider Capability shall be established, changed or withdrawn only through governed Provider Capability Assessment using approved evidence.

Runtime evidence from a later authorized operation may identify a need for reassessment, but it shall not silently create, extend, narrow, withdraw or redefine Provider Capability.

Reassessment is a governed activity. It shall produce a new traceable Capability Assessment Record and, where applicable, a non-destructive supersession of the prior determination.

# 3. Terminology

| Term | Architectural meaning |
|---|---|
| Provider Capability Assessment | One bounded, read-only Provider-owned capability that evaluates approved evidence concerning a defined Provider technical capability. |
| Capability Assessment Activity | The Provider-owned assessment activity performed for one Provider and one approved Capability Identifier. |
| Capability Assessment Record | The Provider-owned result containing separate support and implementation determinations, evidence basis, limitations, currentness and provenance. |
| Capability Identifier | A stable provider-neutral identity for one technical capability whose support may be assessed. |
| Provider-Supported Capability | A Provider-owned determination of whether approved evidence establishes that the Provider supports the identified technical capability. |
| KRONOS-Implemented Capability | A Provider engineering determination of whether an approved KRONOS adapter implements the provider-neutral capability contract. |
| Account Entitlement | Account-specific permission or enablement. It is separate from Provider capability and outside this architecture. |
| Service Availability | Provider-owned current operational meaning concerning whether an approved capability can presently be used. It is separate from support. |
| Capability Limitation | A descriptive Provider-owned constraint attached to a supported capability, such as a documented request, interval, connection or subscription limit. |
| Provider-Wide Evidence | Evidence whose applicability is independent of one authenticated account or Provider Context. |
| Context-Specific Evidence | Evidence produced through an explicitly authorized operation within one bounded Authenticated Provider Context. |
| Evidence Currentness | The stated temporal and version basis under which capability evidence remains applicable. |
| Supersession | Non-destructive replacement of an earlier assessment by a later governed assessment. |
| Runtime Observation | Evidence of behaviour from a later separately authorized operation. It is not Observation-domain factual market information. |
| Indeterminate Assessment | An assessment for which available evidence is insufficient, ambiguous, stale, conflicting or unauthorized. |

# 4. Provider Ownership

Provider is the exclusive semantic owner of:

- Provider Capability Assessment;
- Capability Assessment Activity;
- Provider-Supported Capability;
- Provider capability limitations;
- Provider capability evidence;
- Provider capability provenance;
- capability-evidence currentness;
- capability-assessment supersession;
- capability-assessment failure; and
- capability-assessment indeterminacy.

The KRONOS implementation disposition is an engineering representation maintained within the Provider boundary. It shall not acquire Provider-support meaning.

Provider ownership shall not transfer ownership of:

- Configuration Meaning;
- Account Entitlement;
- Dataset Permission;
- Acquisition Authority;
- Instrument identity;
- Observation facts;
- Market meaning;
- Validation judgment;
- Risk approval;
- Execution authority;
- Portfolio state;
- Event meaning; or
- Audit meaning.

# 5. Boundary

The Provider Capability Assessment boundary begins with:

1. one approved Provider identity;
2. one approved provider-neutral Capability Identifier;
3. one or more approved evidence sources;
4. an approved compatibility basis;
5. an assessment time; and
6. an Authenticated Provider Context only where explicitly authorized endpoint evidence requires one.

The boundary contains:

- evidence classification;
- evidence evaluation;
- Provider-support determination;
- KRONOS implementation-disposition determination;
- capability limitations;
- provenance;
- currentness;
- supersession; and
- assessment failure or indeterminacy.

The boundary terminates with one Capability Assessment Record.

The boundary shall not extend into:

- account-entitlement determination;
- Provider capability execution;
- acquisition;
- Instrument interpretation;
- Observation establishment;
- Validation;
- Risk;
- Execution;
- Portfolio; or
- the KRONOS business pipeline.

# 6. Explicit Non-Implications

Provider Capability Assessment shall never imply:

- Account Entitlement;
- authentication success;
- Context Validity;
- Context Reuse Eligibility beyond separately approved authority;
- Service Availability;
- Provider Operational Availability;
- Dataset Permission;
- Acquisition Authority;
- Acquisition Eligibility;
- Technical Acquisition Success;
- acquisition completeness;
- Instrument identity;
- Provider-to-Instrument mapping;
- Observation acceptance;
- Market availability;
- Validation judgment;
- Risk approval;
- Execution permission;
- Portfolio meaning;
- business readiness;
- implementation authorization; or
- runtime authorization.

Approval of a Capability Identifier authorizes assessment only.

Provider support shall not imply KRONOS implementation.

KRONOS implementation shall not imply Provider support.

Neither meaning shall imply account-specific permission.

# 7. Capability Identifier Set

The following provider-neutral identifiers are approved for assessment:

| Capability Identifier | Architectural scope | Assessment disposition |
|---|---|---|
| Instrument Reference Capability | Provider technical capability supplying Provider-owned instrument-reference information. | Included |
| Full Quote Snapshot Capability | Provider technical capability supplying a full current quote snapshot. | Included |
| OHLC Snapshot Capability | Provider technical capability supplying a current OHLC and last-price snapshot. | Included |
| LTP Snapshot Capability | Provider technical capability supplying a current last-traded-price snapshot. | Included |
| Historical Observation Capability | Provider technical capability supplying historical market-information records. | Included |
| Live Observation Streaming Capability | Provider technical capability supplying live market-information streaming. | Included for assessment; implementation remains Deferred under the approved Phase 1 roadmap. |

These identifiers define no:

- endpoint;
- SDK method;
- payload;
- schema;
- acquisition contract;
- Dataset Permission;
- implementation sequence; or
- runtime operation.

Execution, orders, GTT, portfolio, positions, funds, margins and mutual funds are excluded.

# 8. Provider-Support Model

Provider-Supported Capability shall use exactly one of:

- `SUPPORTED`;
- `UNSUPPORTED`; or
- `UNDETERMINED`.

The determination shall apply to:

- one Provider;
- one Capability Identifier;
- one Provider or API compatibility basis;
- one evidence basis; and
- one determination time.

Provider support shall be established independently of KRONOS implementation.

A support determination shall not be inferred solely from:

- an SDK constant;
- an SDK method name;
- adapter code;
- account profile data;
- Authentication Success;
- operational availability; or
- one incidental runtime result.

# 9. KRONOS Implementation-Disposition Model

KRONOS-Implemented Capability shall use exactly one of:

- `IMPLEMENTED`;
- `NOT_IMPLEMENTED`; or
- `DEFERRED`.

`IMPLEMENTED` means an approved KRONOS adapter implements the provider-neutral contract for the Capability Identifier under a recorded adapter and dependency basis.

`NOT_IMPLEMENTED` means no approved KRONOS implementation exists for that capability.

`DEFERRED` means implementation is intentionally outside the current authorized phase.

The implementation disposition shall not establish Provider support.

Except for Live Observation Streaming Capability, whose implementation is Deferred by approved roadmap authority, the actual implementation disposition of each identifier shall be determined during separately authorized EDD-002 assessment.

Architecture shall not presume an implementation disposition merely because an SDK exposes a related method.

# 10. Valid State Combinations

| Provider support | KRONOS implementation | Architectural meaning |
|---|---|---|
| `SUPPORTED` | `IMPLEMENTED` | Provider support and an approved KRONOS implementation are separately established. Entitlement, availability and operational authority remain unresolved. |
| `SUPPORTED` | `NOT_IMPLEMENTED` | Provider support is established, but KRONOS has no approved implementation. |
| `SUPPORTED` | `DEFERRED` | Provider support is established, while implementation is intentionally outside the current phase. |
| `UNSUPPORTED` | `NOT_IMPLEMENTED` | Provider non-support is established and no implementation exists. |
| `UNSUPPORTED` | `DEFERRED` | Provider non-support is established; implementation remains intentionally inactive. |
| `UNSUPPORTED` | `IMPLEMENTED` | Governance conflict. The implementation shall not be treated as usable and requires controlled review. |
| `UNDETERMINED` | `IMPLEMENTED` | Adapter mechanics exist, but Provider support is not established. No positive capability conclusion is permitted. |
| `UNDETERMINED` | `NOT_IMPLEMENTED` | Neither Provider support nor KRONOS implementation is established. |
| `UNDETERMINED` | `DEFERRED` | Provider support remains unresolved and implementation is outside the current phase. |

No combination grants entitlement, availability, Dataset Permission, Acquisition Authority or business authority.

# 11. Evidence Hierarchy

Capability evidence shall be classified in the following order.

## 11.1 Official Provider Documentation

Official Provider Documentation may establish:

- that the Provider documents a named capability;
- the documented purpose of that capability;
- documented compatibility or API basis; and
- documented Capability Limitations.

It shall not establish:

- Account Entitlement;
- current Service Availability;
- KRONOS implementation;
- Dataset Permission;
- Acquisition Authority; or
- runtime success.

## 11.2 Approved Adapter and Locked-SDK Compatibility

Approved Adapter and Locked-SDK Compatibility may establish:

- that the locked SDK represents the required Provider mechanics;
- that an approved adapter is compatible with those mechanics;
- the applicable SDK and adapter versions; and
- implementation limitations known at assessment time.

It shall not establish:

- Provider support by itself;
- Account Entitlement;
- current Service Availability;
- Dataset Permission;
- Acquisition Authority; or
- successful operation.

SDK constants shall be treated as implementation vocabulary, not Provider-discovered capability evidence.

## 11.3 Authorized Provider-Endpoint Evidence

Authorized Provider-Endpoint Evidence may establish:

- a Provider response for one explicitly approved, read-only evidence operation;
- context-specific evidence concerning the identified capability;
- Provider-reported limitations where the endpoint contract defines them; and
- evidence of indeterminacy or failure within that operation.

It shall not establish:

- provider-wide account entitlement;
- permanent Provider support;
- cross-account support;
- Dataset Permission;
- Acquisition Authority;
- acquisition success; or
- business authority.

Account profile fields shall not be used by Provider Capability Assessment.

## 11.4 Runtime Evidence from Later Authorized Operations

Runtime Evidence may establish:

- observed behaviour during a separately authorized operation;
- observed compatibility;
- a Capability Limitation;
- an assessment conflict; or
- a governed need for reassessment.

It shall not:

- create retrospective authorization;
- establish universal support from one success;
- establish unsupported capability from an incidental failure;
- silently create, extend, narrow, withdraw or redefine Provider Capability;
- redefine the later operation’s ownership; or
- replace the evidence hierarchy.

Runtime evidence requiring a changed capability determination shall be referred to governed reassessment.

# 12. Determination Semantics

`SUPPORTED` shall require current, affirmative and capability-specific Provider evidence.

Official Provider documentation may establish `SUPPORTED` when it:

- identifies the capability;
- applies to the recorded Provider and API basis;
- has not been superseded; and
- conflicts with no stronger current evidence.

`UNSUPPORTED` shall require explicit, authoritative and capability-specific evidence that the capability:

- is not supported;
- has been withdrawn;
- is unavailable under the applicable Provider or API basis as a matter of support rather than temporary operation; or
- is rejected through an authorized endpoint response whose canonical Provider meaning explicitly establishes non-support.

`UNDETERMINED` shall apply when:

- evidence is absent;
- evidence is stale;
- evidence is ambiguous;
- evidence conflicts;
- evidence is unauthorized;
- the compatibility basis is unresolved; or
- the evidentiary threshold for either positive support or explicit non-support is not satisfied.

No determination shall be strengthened beyond the meaning supported by its evidence.

A determination shall change only through governed reassessment and traceable supersession.

# 13. Failure and Indeterminacy Semantics

The following shall not automatically establish `UNSUPPORTED`:

- timeout;
- invalid or terminated context;
- authentication failure;
- throttling;
- account restriction;
- entitlement denial;
- generic `404` or `405`;
- malformed response;
- Provider unavailability;
- adapter absence;
- SDK absence;
- parsing failure;
- transport failure; or
- incomplete evidence.

Such conditions shall produce the applicable meaning, including:

- evidence unavailable;
- evidence stale;
- evidence conflicting;
- evidence unauthorized;
- context invalid;
- Provider operationally unavailable;
- adapter incompatible;
- evidence insufficient; or
- assessment failed.

Unless authoritative evidence proves non-support, these conditions shall result in or preserve `UNDETERMINED`.

Assessment failure shall not retroactively change a prior valid assessment. It may require a governed reassessment or supersession decision.

# 14. Capability Limitations

Documented Provider limits may be represented as descriptive Capability Limitations.

Capability Limitations may include:

- request-size limits;
- subscription limits;
- connection limits;
- supported interval vocabulary;
- documented data-retention limits;
- documented response-currentness characteristics;
- documented capability scope; and
- provider-published technical restrictions.

Capability Limitations shall preserve:

- Provider source;
- applicable Capability Identifier;
- documentation or evidence basis;
- version basis;
- determination time; and
- currentness.

Capability Limitations shall not authorize:

- retries;
- scheduling;
- caching;
- batching;
- throttling algorithms;
- persistence;
- acquisition;
- subscription;
- connection establishment; or
- implementation.

# 15. Context-Reuse Rules

Official-documentation assessment shall not require authentication.

Adapter and locked-SDK compatibility assessment shall not require authentication.

An EDD-001 Authenticated Provider Context may be reused only for an explicitly authorized, capability-specific, read-only endpoint-evidence operation.

Context reuse requires:

1. an approved Capability Identifier;
2. separately approved endpoint-evidence authority;
3. a valid, non-terminated Authenticated Provider Context;
4. explicit Context Reuse Eligibility for the exact capability;
5. unchanged Provider identity;
6. unchanged account or authorization context;
7. unchanged operating environment;
8. unchanged Configuration approval context;
9. unchanged lifecycle and operational boundaries;
10. sensitive-material containment; and
11. no expansion of the approved operation.

Context reuse shall not establish:

- Provider support by itself;
- Account Entitlement;
- Dataset Permission;
- Acquisition Authority;
- Service Availability; or
- business authority.

Account profile evidence is excluded and belongs to separately approved entitlement architecture.

# 16. Provider-Internal Composition

Where an authorized endpoint-evidence operation requires authentication, Provider may compose that operation internally with the approved EDD-001 Provider-access implementation.

Internal composition shall:

- remain entirely inside Provider;
- preserve Provider ownership;
- consume only an eligible Authenticated Provider Context;
- use adapter-private transport state only within the Provider implementation boundary;
- translate Provider and SDK results into provider-neutral assessment meanings;
- redact sensitive information; and
- preserve non-sensitive provenance.

Provider-neutral contracts and the Authenticated Provider Context shall never expose:

- API secrets;
- request tokens;
- access tokens;
- checksums;
- authorization headers;
- SDK clients;
- SDK responses;
- SDK exceptions;
- Provider credentials; or
- adapter-private transport state.

The SDK client shall not become the Authenticated Provider Context.

# 17. Provenance, Currentness and Supersession

Every Capability Assessment Record shall preserve:

- Provider identity;
- Capability Identifier;
- Provider-support determination;
- KRONOS implementation disposition;
- evidence class;
- official documentation basis;
- Provider or API compatibility basis;
- locked SDK name and version;
- approved adapter identity and version or repository revision;
- authorized endpoint context where applicable;
- determination timestamp;
- Capability Limitations;
- assessment outcome;
- prior assessment reference where applicable;
- supersession reason where applicable; and
- non-sensitive audit reference.

Provider-wide evidence and context-specific evidence shall remain distinct.

Invalidation or termination of one Authenticated Provider Context shall not erase:

- official documentation evidence;
- SDK compatibility evidence;
- adapter compatibility evidence; or
- prior assessment history.

Context termination may end eligibility to use context-specific evidence operationally. It shall not rewrite provider-wide support meaning.

Supersession shall be non-destructive. A later governed assessment may supersede an earlier assessment, but the earlier record shall remain traceable.

Conflicting current evidence shall produce `UNDETERMINED` until resolved through governed reassessment.

Runtime evidence shall not update or supersede a Provider Capability determination without governed reassessment.

# 18. Security and Sensitive-Data Boundaries

Capability assessment shall apply data minimization.

Capability evidence, provenance, audit records, errors and diagnostics shall never contain:

- API secrets;
- request tokens;
- access tokens;
- refresh tokens;
- checksums;
- authorization headers;
- SDK clients;
- raw SDK exceptions;
- reconstructable authentication material;
- adapter-private transport state; or
- unnecessary account identity.

Sensitive Provider responses shall remain inside the Provider adapter boundary and shall be discarded after the approved non-sensitive meaning has been established.

Account profile payloads shall not be retained or published by this capability.

SDK debug logging shall not be enabled through this architecture.

# 19. Dependencies

Provider Capability Assessment depends on:

- approved Provider identity;
- canonical Provider ownership;
- approved Capability Identifiers;
- approved evidence classes;
- official Provider documentation where used;
- approved adapter and locked dependency evidence where used;
- EDD-001 Context Validity and Context Reuse Eligibility where authenticated evidence is separately authorized; and
- repository governance for assessment traceability.

It does not depend on:

- Instrument;
- Observation;
- Validation;
- Risk;
- Execution;
- Portfolio;
- Account Entitlement;
- Dataset Permission;
- Acquisition Authority; or
- the business pipeline.

This architecture creates no new Domain Dependency Matrix entry.

# 20. Explicit Exclusions

This architecture excludes:

- EDD-002 engineering design;
- capability-assessment implementation;
- Account Entitlement assessment;
- profile-field publication;
- Dataset Permission;
- Acquisition Authority;
- instrument acquisition;
- Instrument interpretation;
- Provider-to-Instrument mapping;
- historical acquisition;
- current-quote acquisition;
- live streaming;
- Observation processing;
- Validation;
- Risk;
- Execution;
- Portfolio;
- orders;
- GTT;
- positions;
- holdings;
- funds;
- margins;
- mutual funds;
- retries;
- scheduling;
- caching;
- batching;
- throttling algorithms;
- persistence;
- APIs;
- payloads;
- schemas;
- SDK selection changes;
- deployment; and
- GUI design.

# 21. GUI Readiness

A future Administration Console may consume provider-neutral, read-only capability information consisting of:

- Provider identity;
- Capability Identifier;
- provider-support determination;
- KRONOS implementation disposition;
- evidence class;
- determination timestamp;
- currentness or superseded indication;
- non-sensitive Capability Limitations; and
- non-sensitive provenance reference.

The Administration Console shall not represent capability assessment as:

- Account Entitlement;
- Dataset Permission;
- Acquisition Authority;
- current Service Availability;
- business readiness;
- implementation authorization; or
- permission to initiate an operation.

This section is non-authoritative for GUI design. It defines no screen, workflow, user interaction, API or implementation.

# 22. Consequences for EDD-002

EDD-002 may be authorized for drafting only after this architecture is approved and canonical.

If separately authorized, EDD-002 shall translate this architecture into implementation-neutral engineering design for:

- Capability Assessment Activity;
- provider-neutral Capability Identifiers;
- separate support and implementation axes;
- evidence classification;
- determination semantics;
- assessment failure and indeterminacy;
- Capability Limitations;
- context-reuse eligibility;
- Provider-internal composition;
- provenance;
- currentness; and
- supersession.

EDD-002 shall determine actual KRONOS implementation dispositions from approved evidence, except where canonical architecture already establishes `DEFERRED`.

EDD-002 shall not:

- assess Account Entitlement;
- use account profile fields;
- authorize Provider operations;
- define acquisition;
- establish Dataset Permission;
- establish Acquisition Authority;
- implement capability behaviour; or
- authorize EDD-003.

Canonicalization of this architecture shall not itself authorize EDD-002 drafting.

# 23. Relationship to Existing Authority

## 23.1 ADP-001G

This architecture fulfils ADP-001G’s requirement for later Provider capability architecture without altering the authentication boundary.

Authentication Success remains limited to establishing an Authenticated Provider Context.

Context reuse remains explicit, capability-specific and bounded.

## 23.2 ADP-001H

ADP-001H remains the authoritative architecture for the bounded Instrument Master Acquisition Capability and its Acquisition Contract.

This document may assess support for the Instrument Reference Capability. It shall not replace ADP-001H, authorize acquisition or generalize ADP-001H into a reusable acquisition framework.

## 23.3 EAP-001

EAP-001 remains authoritative for engineering representation of the Authenticated Provider Context and Context Reuse Eligibility.

This architecture supplies the separate capability authority that a future engineering package or EDD must inherit. It does not amend EAP-001.

## 23.4 EDD-001

EDD-001 remains authoritative for Provider access and Provider Context engineering design.

This architecture may consume only the provider-neutral context meanings approved by EDD-001. It shall not expose or enlarge EDD-001 adapter internals.

## 23.5 Governance Statement

This Version 1.0 document is approved canonical architecture.

It authorizes no:

- EDD-002 Draft;
- EDD-003 Draft;
- implementation;
- dependency change;
- endpoint operation;
- acquisition;
- runtime activity.

Repository publication shall follow the controlled governance process.

---

# End of Document
