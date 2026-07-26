# EDD-002 — Provider Capability Assessment Engineering Design

**Document ID:** EDD-002
**Title:** Provider Capability Assessment Engineering Design
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Engineering Design Document
**Owner:** Engineering Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/engineering/edd/EDD-002-PROVIDER-CAPABILITY-ASSESSMENT-ENGINEERING-DESIGN.md`
**Draft Authorization:** Chief Architect Draft Authorization — Approved
**Governing Architecture:** ADR-007 Version 1.0
**Immediate Upstream EDD:** EDD-001 Version 1.0
**ADR Required:** No
**Implementation Authorization:** None
**Runtime Impact:** None

---

# 1. Purpose

This Engineering Design Document defines the implementation-neutral engineering design for Provider Capability Assessment.

It answers one engineering question:

> How shall KRONOS assess approved Provider capabilities from governed evidence while keeping Provider support, KRONOS implementation, Account Entitlement, Service Availability, Dataset Permission, Acquisition Authority, Runtime Observation and Business Meaning separate?

The design translates canonical ADR-007 into provider-neutral requests, activities, outcomes, records, evidence representations, determination rules, lifecycle states, contracts, security boundaries, verification requirements and GUI-readiness outputs.

This document authorizes no implementation or Provider operation.

# 2. Authority

This design is subordinate to:

1. [ADR-007 — Provider Capability Assessment Architecture](../../architecture/platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md);
2. [EDD-001 — Provider Access and Provider Context Engineering Design](EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
3. [DOMAIN-006 — Provider Domain](../../architecture/platform/domains/provider/ARCHITECTURE.md);
4. [PLATFORM-000 — KRONOS Platform Constitution](../../architecture/platform/PLATFORM-000-CONSTITUTION.md);
5. [Domain Ownership Matrix](../../architecture/platform/DOMAIN_OWNERSHIP_MATRIX.md);
6. [Domain Dependency Matrix](../../architecture/platform/DOMAIN_DEPENDENCY_MATRIX.md);
7. [ENGINE_OWNERSHIP](../../architecture/ENGINE_OWNERSHIP.md);
8. [DATA_FLOW](../../architecture/DATA_FLOW.md);
9. [EAS-001 through EAS-007](../eap/);
10. [EAP-001 — Configuration-to-Provider Authenticated Context Engineering Architecture](../eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md);
11. [DOC-001 — Document Identification, Classification & Metadata Standard](../../governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md);
12. [GOV-002 — KRONOS Governance Lifecycle](../../governance/lifecycle/GOV-002-GOVERNANCE-LIFECYCLE.md); and
13. [IDX-001 — Document Register](../../indexes/DOCUMENT-REGISTER.md).

Official Kite Connect documentation defines Provider-supported behaviour and limitations. Official pykiteconnect Version 5.2.0 supplies implementation evidence only. Neither source may redefine KRONOS architecture.

# 3. Scope

EDD-002 defines engineering design for:

- Capability Assessment Request;
- Capability Assessment Activity;
- Capability Assessment Outcome;
- Capability Assessment Record;
- the six approved Capability Identifiers;
- Provider-Support determination;
- KRONOS Implementation Disposition;
- Capability Evidence;
- evidence classes;
- Capability Limitations;
- Evidence Currentness;
- non-destructive supersession;
- assessment failure and indeterminacy;
- provider-neutral contracts;
- Provider-internal composition;
- representation of EDD-001 context-reuse checks;
- provenance and non-sensitive audit evidence;
- security and redaction;
- deterministic verification;
- Engineering Lab validation; and
- GUI Readiness output.

The design supports documentation and compatibility assessment without authentication.

It represents authenticated endpoint evidence only as a separately authorized future evidence path. It does not authorize an endpoint invocation.

# 4. Dependencies

## 4.1 Required dependencies

Provider Capability Assessment requires:

- one approved Provider identity;
- one approved Capability Identifier;
- canonical ADR-007;
- an approved evidence class;
- an explicit evidence basis;
- an assessment time;
- a Provider or API compatibility basis;
- a locked-SDK basis where SDK compatibility is assessed;
- an adapter revision basis where KRONOS implementation is assessed; and
- EDD-001 context validity and reuse evidence only where a separately authorized endpoint-evidence operation requires authentication.

## 4.2 Prohibited dependencies

Provider Capability Assessment shall not depend on:

- Instrument;
- Observation;
- Validation;
- Risk;
- Execution;
- Portfolio;
- the business pipeline;
- Account Entitlement;
- profile fields;
- Dataset Permission;
- Acquisition Authority; or
- provider-specific objects crossing the Provider boundary.

## 4.3 Current controlled evidence basis

The initial Kite assessment uses:

- Kite Connect API Version 3 documentation;
- official pykiteconnect Version 5.2.0;
- the repository lock for `kiteconnect==5.2.0`;
- the current approved Kite adapter boundary; and
- the current repository revision assessed by Engineering Verification.

No live Provider evidence is required for the initial documentation and compatibility assessment.

# 5. Engineering Boundary

Assessment Request Processing precedes the EDD-002 Capability Assessment boundary.

The EDD-002 Capability Assessment boundary begins only after Assessment Request Processing has established all approved assessment inputs and accepted one eligible Capability Assessment Request.

The boundary accepts only:

- provider-neutral assessment intent;
- approved evidence representations;
- compatibility references;
- non-sensitive authority references; and
- an opaque Provider Context reference only for a separately authorized endpoint-evidence operation.

Once the Capability Assessment Activity begins, the boundary produces exactly one Capability Assessment Outcome, one Capability Assessment Record, one Provider-Support determination and one KRONOS Implementation Disposition.

An `ASSESSMENT_NOT_PERFORMED` outcome occurs before this boundary and produces no Capability Assessment Record or determination.

The boundary terminates before:

- capability execution;
- entitlement evaluation;
- availability probing;
- acquisition;
- downstream domain communication; or
- business use.

Provider-specific mechanics and sensitive state remain internal to Provider.

# 6. Inputs and Outputs

## 6.1 Inputs

| Input | Required meaning |
|---|---|
| Assessment identity | Non-sensitive correlation identity for one assessment activity. |
| Provider identity | Approved Provider identity to which the assessment applies. |
| Capability Identifier | Exactly one identifier approved by ADR-007. |
| Evidence set | One or more immutable Capability Evidence representations. |
| Assessment authority reference | Non-sensitive reference to the authority permitting assessment. |
| Compatibility basis | Provider/API, SDK and adapter version basis applicable to the evidence. |
| Assessment time | Controlled time at which currentness is evaluated. |
| Prior record reference | Optional reference when reassessment may supersede an earlier record. |
| Provider Context reference | Optional opaque reference, permitted only for separately authorized endpoint evidence. |

## 6.2 Outputs

| Output | Required meaning |
|---|---|
| Capability Assessment Outcome | Pre-boundary request-processing result or engineering result of one activity, separate from both determination axes. |
| Capability Assessment Record | Complete non-sensitive assessment record produced only after Capability Assessment Activity begins. |
| Provider-Support determination | `SUPPORTED`, `UNSUPPORTED` or `UNDETERMINED`; established only after Capability Assessment Activity begins. |
| KRONOS Implementation Disposition | `IMPLEMENTED`, `NOT_IMPLEMENTED` or `DEFERRED`; established only after Capability Assessment Activity begins. |
| Capability Limitations | Zero or more descriptive, sourced limitations. |
| Evidence Currentness | Currentness of each evidence item and the aggregate determination basis. |
| Supersession reference | Non-destructive relationship to any prior record superseded by this assessment. |
| Provenance | Non-sensitive evidence and authority lineage. |
| Audit evidence | Non-sensitive evidence that the bounded assessment occurred. |
| GUI Readiness projection | Optional read-only provider-neutral projection containing no new authority. |

# 7. Responsibilities

## 7.1 Provider

Provider shall:

- own Capability Assessment Activity;
- validate request eligibility;
- classify evidence;
- evaluate evidence currentness;
- determine Provider support;
- determine KRONOS implementation disposition from approved repository evidence;
- preserve Capability Limitations;
- distinguish failure from non-support;
- produce one outcome for every processed request and, once Capability Assessment Activity begins, one record with both required determinations;
- preserve non-destructive supersession;
- maintain sensitive-state containment; and
- publish only provider-neutral, non-sensitive meanings.

## 7.2 Assessment initiator

A separately authorized assessment initiator may:

- request assessment of one approved Capability Identifier;
- supply approved evidence references;
- identify a prior record for reassessment; and
- consume the resulting record within its authorization.

The initiator shall not:

- define Provider capability;
- supply credentials;
- infer entitlement;
- invoke a Provider endpoint through this EDD;
- expand the identifier set; or
- convert the result into operational authority.

## 7.3 Evidence source

An evidence source shall:

- identify its evidence class;
- identify its source and compatibility basis;
- preserve currentness information;
- provide only the minimum non-sensitive evidence required; and
- avoid stronger claims than its evidence class permits.

## 7.4 GUI consumer

A future Administration Console may consume only the approved GUI Readiness projection.

It shall not alter assessment records or initiate capability execution through this design.

# 8. Approved Capability Identifiers

The Capability Identifier representation shall be closed to exactly:

1. `INSTRUMENT_REFERENCE_CAPABILITY`;
2. `FULL_QUOTE_SNAPSHOT_CAPABILITY`;
3. `OHLC_SNAPSHOT_CAPABILITY`;
4. `LTP_SNAPSHOT_CAPABILITY`;
5. `HISTORICAL_OBSERVATION_CAPABILITY`; and
6. `LIVE_OBSERVATION_STREAMING_CAPABILITY`.

The representation shall preserve the canonical display meanings:

| Engineering identifier | Canonical meaning |
|---|---|
| `INSTRUMENT_REFERENCE_CAPABILITY` | Instrument Reference Capability |
| `FULL_QUOTE_SNAPSHOT_CAPABILITY` | Full Quote Snapshot Capability |
| `OHLC_SNAPSHOT_CAPABILITY` | OHLC Snapshot Capability |
| `LTP_SNAPSHOT_CAPABILITY` | LTP Snapshot Capability |
| `HISTORICAL_OBSERVATION_CAPABILITY` | Historical Observation Capability |
| `LIVE_OBSERVATION_STREAMING_CAPABILITY` | Live Observation Streaming Capability |

Unknown identifiers shall not be accepted or coerced into a known identifier.

Adding an identifier requires prior architectural approval.

# 9. Capability Assessment Request

The Capability Assessment Request is an immutable, provider-neutral engineering representation.

It shall contain:

- assessment identity;
- Provider identity;
- exactly one Capability Identifier;
- requested evidence classes;
- evidence references;
- assessment authority reference;
- compatibility basis;
- assessment time;
- optional prior-record reference; and
- optional opaque Provider Context reference.

It shall not contain:

- API secret;
- request token;
- access token;
- checksum;
- authorization header;
- SDK client;
- SDK response;
- SDK exception;
- adapter-private state;
- profile data;
- Account Entitlement;
- Dataset Permission; or
- Acquisition Authority.

## 9.1 Assessment Request Processing

Assessment Request Processing occurs before the Capability Assessment boundary.

A request is eligible only when:

1. Provider identity is approved;
2. the Capability Identifier is approved;
3. assessment authority is present;
4. every requested evidence class is approved;
5. evidence references are non-sensitive;
6. the compatibility basis is explicit;
7. the assessment time is present; and
8. endpoint evidence is not requested without separate endpoint-evidence authority and eligible EDD-001 context reuse.

Unknown Capability Identifiers, invalid requests, missing prerequisites and other request-eligibility failures shall produce an `ASSESSMENT_NOT_PERFORMED` outcome preserving the non-sensitive reason.

`ASSESSMENT_NOT_PERFORMED` shall not create a Capability Assessment Record, Provider-Support determination or KRONOS Implementation Disposition.

# 10. Capability Assessment Activity

Capability Assessment Activity is one bounded Provider-owned activity.

For one eligible request, the activity shall:

1. confirm request eligibility;
2. verify that each evidence item belongs to an approved evidence class;
3. evaluate evidence applicability;
4. evaluate Evidence Currentness;
5. detect evidence conflicts;
6. apply Provider-support rules;
7. apply KRONOS implementation-disposition rules;
8. preserve Capability Limitations;
9. determine assessment outcome;
10. create one Capability Assessment Record;
11. establish supersession only where governed criteria are satisfied; and
12. emit non-sensitive audit evidence.

The activity shall assess one Provider and one Capability Identifier independently.

It shall not:

- execute the capability;
- call a live Provider endpoint under this authorization;
- infer Account Entitlement;
- infer Service Availability;
- create Dataset Permission;
- create Acquisition Authority; or
- update an existing record destructively.

# 11. Capability Assessment Outcome

Capability Assessment Outcome is separate from Provider support and KRONOS implementation disposition.

It shall use exactly one of:

| Outcome | Engineering meaning |
|---|---|
| `ASSESSMENT_COMPLETED` | Eligible evidence was evaluated and the record contains the resulting support and implementation determinations. The support determination may still be `UNDETERMINED`. |
| `ASSESSMENT_NOT_PERFORMED` | Pre-boundary request eligibility was not established. No Capability Assessment Activity began, no Capability Assessment Record was created and no assessment determination exists. |
| `ASSESSMENT_FAILED` | An eligible activity began but could not complete because of an engineering failure. The activity produces one record containing both required determinations, and any prior valid record remains unchanged. Where the failure prevents a support conclusion, Provider support is `UNDETERMINED`; KRONOS implementation disposition remains independently determined from approved repository evidence. |

Every processed request shall produce exactly one outcome.

Once Capability Assessment Activity begins, exactly one Capability Assessment Record, one Provider-Support determination and one KRONOS Implementation Disposition shall accompany that outcome.

No outcome shall imply entitlement, availability, acquisition or business meaning.

# 12. Capability Assessment Record

The Capability Assessment Record is an immutable, provider-neutral representation of one Capability Assessment Activity that began.

Exactly one record shall be produced for every activity that begins, whether the outcome is `ASSESSMENT_COMPLETED` or `ASSESSMENT_FAILED`.

No record shall be produced for `ASSESSMENT_NOT_PERFORMED`.

It shall contain:

- record identity;
- assessment identity;
- Provider identity;
- Capability Identifier;
- Capability Assessment Outcome;
- Provider-Support determination;
- KRONOS Implementation Disposition;
- evidence references and classes;
- evidence-currentness determinations;
- Provider/API compatibility basis;
- locked-SDK basis where applicable;
- approved adapter revision basis where applicable;
- Capability Limitations;
- assessment timestamp;
- prior-record reference where applicable;
- superseded-record reference where applicable;
- non-sensitive failure or indeterminacy reasons;
- provenance; and
- non-sensitive audit reference.

The record shall not contain:

- raw Provider payloads;
- profile payloads;
- SDK objects;
- SDK exceptions;
- credentials;
- authentication material;
- account identity not required by approved authority;
- acquisition results; or
- business-domain information.

One record applies only to its recorded Provider, Capability Identifier, evidence basis, compatibility basis and assessment time.

# 13. Capability Evidence

Capability Evidence is an immutable, non-sensitive representation.

Each evidence item shall contain:

- evidence identity;
- evidence class;
- Provider identity;
- Capability Identifier;
- source reference;
- asserted evidence meaning;
- Provider/API compatibility basis;
- SDK version basis where applicable;
- adapter revision basis where applicable;
- evidence issue, retrieval or observation time where known;
- Evidence Currentness;
- provider-wide or context-specific scope;
- authorization reference where required;
- non-sensitive integrity reference where available; and
- supersession reference where applicable.

Evidence shall preserve its source meaning without interpretation beyond its evidence class.

Raw SDK responses, Provider payloads and sensitive values shall not become Capability Evidence.

# 14. Evidence Classes

The Evidence Class representation shall use exactly:

1. `OFFICIAL_PROVIDER_DOCUMENTATION`;
2. `APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY`;
3. `AUTHORIZED_PROVIDER_ENDPOINT_EVIDENCE`; and
4. `LATER_AUTHORIZED_RUNTIME_EVIDENCE`.

## 14.1 Official Provider Documentation

This class may establish:

- documented Provider support;
- documented capability purpose;
- Provider/API compatibility basis; and
- documented Capability Limitations.

It shall not establish:

- Account Entitlement;
- present Service Availability;
- KRONOS implementation;
- Dataset Permission;
- Acquisition Authority; or
- runtime success.

## 14.2 Approved Adapter and Locked-SDK Compatibility

This class may establish:

- availability of suitable SDK mechanics;
- adapter compatibility;
- applicable SDK and adapter versions; and
- implementation limitations.

It shall not establish:

- Provider support by itself;
- Account Entitlement;
- present Service Availability;
- Dataset Permission;
- Acquisition Authority; or
- successful capability execution.

SDK constants and method names shall not be treated as Provider-discovered capability evidence.

## 14.3 Authorized Provider-Endpoint Evidence

This class may represent:

- a response from one separately authorized read-only evidence operation;
- context-specific Provider evidence;
- a Provider-reported limitation; or
- endpoint-evidence failure or indeterminacy.

EDD-002 defines its representation only. This document does not authorize invocation.

It shall not establish:

- provider-wide entitlement;
- permanent support;
- cross-account support;
- Dataset Permission;
- Acquisition Authority; or
- acquisition success.

## 14.4 Runtime Evidence from Later Authorized Operations

This class may represent:

- observed behaviour from a later authorized operation;
- observed compatibility;
- a Capability Limitation;
- an evidence conflict; or
- a governed need for reassessment.

It shall not silently change Provider Capability.

Reassessment requires a new request, activity, outcome and record.

# 15. Provider-Support Determination

Provider-Support determination shall use exactly:

- `SUPPORTED`;
- `UNSUPPORTED`; or
- `UNDETERMINED`.

## 15.1 SUPPORTED

`SUPPORTED` requires current, affirmative and capability-specific Official Provider Documentation that:

- identifies the capability;
- applies to the Provider/API compatibility basis;
- has not been superseded; and
- has no unresolved conflicting evidence.

Authorized endpoint or runtime evidence may corroborate `SUPPORTED`. It shall not be required where current official documentation is sufficient.

## 15.2 UNSUPPORTED

`UNSUPPORTED` requires explicit, authoritative and capability-specific evidence that the capability:

- is not supported;
- has been withdrawn;
- does not exist under the applicable Provider/API basis; or
- is rejected by a separately authorized endpoint operation whose documented canonical meaning specifically establishes non-support.

The assessment shall preserve the exact evidence basis.

The following shall not automatically establish `UNSUPPORTED`:

- timeout;
- invalid context;
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

## 15.3 UNDETERMINED

`UNDETERMINED` applies when:

- evidence is absent;
- evidence is stale;
- evidence is ambiguous;
- evidence conflicts;
- evidence is unauthorized;
- compatibility is unresolved; or
- the threshold for `SUPPORTED` or `UNSUPPORTED` is not satisfied.

Indeterminacy is an explicit result. It shall not be represented as support, non-support or failure.

# 16. KRONOS Implementation Disposition

KRONOS Implementation Disposition shall use exactly:

- `IMPLEMENTED`;
- `NOT_IMPLEMENTED`; or
- `DEFERRED`.

## 16.1 IMPLEMENTED

`IMPLEMENTED` requires repository evidence that:

- an approved provider-neutral capability contract exists;
- an approved Provider adapter implements that contract;
- the implementation is attributable to a repository revision;
- the locked dependency basis is known; and
- boundary verification confirms that Provider-specific types do not escape.

SDK support alone shall not establish `IMPLEMENTED`.

## 16.2 NOT_IMPLEMENTED

`NOT_IMPLEMENTED` applies when no approved KRONOS implementation exists for the capability.

An empty protocol, placeholder class, package skeleton or SDK method shall not satisfy implementation.

## 16.3 DEFERRED

`DEFERRED` applies only where approved roadmap or governance authority intentionally places implementation outside the current phase.

The reason and authority shall be preserved.

## 16.4 Initial dispositions

Current repository evidence establishes:

| Capability Identifier | Initial disposition | Basis |
|---|---|---|
| Instrument Reference Capability | `NOT_IMPLEMENTED` | The repository contains only an empty provider-neutral protocol and Kite skeleton; no approved capability operation is implemented. |
| Full Quote Snapshot Capability | `NOT_IMPLEMENTED` | No approved provider-neutral quote capability contract or adapter operation exists. |
| OHLC Snapshot Capability | `NOT_IMPLEMENTED` | No approved provider-neutral OHLC capability contract or adapter operation exists. |
| LTP Snapshot Capability | `NOT_IMPLEMENTED` | No approved provider-neutral LTP capability contract or adapter operation exists. |
| Historical Observation Capability | `NOT_IMPLEMENTED` | No approved provider-neutral historical capability contract or adapter operation exists. |
| Live Observation Streaming Capability | `DEFERRED` | ADR-007 and the approved Phase 1 roadmap defer implementation. |

# 17. Valid Determination Combinations

The implementation shall support every valid combination approved by ADR-007.

| Provider support | KRONOS disposition | Required treatment |
|---|---|---|
| `SUPPORTED` | `IMPLEMENTED` | Preserve both meanings independently. No entitlement, availability or authority follows. |
| `SUPPORTED` | `NOT_IMPLEMENTED` | Report documented support and absence of approved implementation. |
| `SUPPORTED` | `DEFERRED` | Report documented support and governed implementation deferral. |
| `UNSUPPORTED` | `NOT_IMPLEMENTED` | Report authoritative non-support and absence of implementation. |
| `UNSUPPORTED` | `DEFERRED` | Report authoritative non-support while preserving deferral history. |
| `UNSUPPORTED` | `IMPLEMENTED` | Produce a governance-conflict indication; the implementation shall not be treated as usable. |
| `UNDETERMINED` | `IMPLEMENTED` | Preserve the implementation evidence but permit no positive Provider-support conclusion. |
| `UNDETERMINED` | `NOT_IMPLEMENTED` | Preserve both unresolved support and absent implementation. |
| `UNDETERMINED` | `DEFERRED` | Preserve unresolved support and governed deferral. |

No combination authorizes capability execution.

# 18. Capability Limitation

A Capability Limitation is an immutable, descriptive representation attached to one Capability Identifier and one evidence basis.

It shall contain:

- limitation identity;
- Capability Identifier;
- Provider identity;
- limitation category;
- provider-neutral description;
- source evidence reference;
- Provider/API version basis;
- Evidence Currentness; and
- determination timestamp.

Approved limitation categories are:

- request-size;
- subscription-count;
- connection-count;
- interval-support;
- data-currentness;
- provider-scope;
- compatibility; and
- other documented technical constraint.

A Capability Limitation shall not authorize:

- retry;
- scheduling;
- caching;
- batching;
- throttling algorithms;
- persistence;
- acquisition;
- subscription;
- connection establishment; or
- capability implementation.

# 19. Evidence Currentness

Evidence Currentness shall use:

- `CURRENT`;
- `STALE`; or
- `CURRENTNESS_UNDETERMINED`.

## 19.1 Currentness evaluation

Currentness shall be determined from:

- Provider/API version applicability;
- documentation basis;
- SDK version basis;
- adapter revision basis;
- evidence issue or retrieval time;
- known superseding evidence; and
- assessment time.

Age alone shall not determine currentness unless approved evidence defines an expiration rule.

## 19.2 Currentness consequences

Current evidence may contribute to a determination.

Stale evidence shall remain traceable but shall not independently establish a current `SUPPORTED` or `UNSUPPORTED` determination.

Evidence of undetermined currentness may contribute only to `UNDETERMINED` unless another approved current evidence item independently satisfies the determination threshold.

# 20. Non-Destructive Supersession

Reassessment shall create a new Capability Assessment Record.

A new record may supersede a prior record only when:

- Provider identity and Capability Identifier match;
- the new assessment is governed and complete;
- the new evidence basis is explicit;
- the supersession reason is preserved; and
- the prior record remains traceable.

Supersession shall not:

- delete or rewrite the prior record;
- erase prior evidence;
- erase context-specific provenance;
- conceal conflicting evidence; or
- convert runtime evidence directly into a changed capability determination.

Invalidation or termination of one Authenticated Provider Context shall not supersede or erase provider-wide documentation or compatibility evidence.

# 21. State and Lifecycle Model

The logical assessment lifecycle is:

```text
NOT_ASSESSED
      |
      v
REQUEST_RECEIVED
      |
      +--------------------------+
      |                          |
      v                          v
REQUEST_ELIGIBLE          REQUEST_INELIGIBLE
      |                          |
      v                          v
CAPABILITY_ASSESSMENT     ASSESSMENT_NOT_PERFORMED
BOUNDARY_ENTERED                 |
      |                          v
      v                  OUTCOME_ONLY_NO_RECORD
ASSESSMENT_ACTIVITY
      +-------------------+
      |                   |
      v                   v
ASSESSMENT_COMPLETED   ASSESSMENT_FAILED
      |                   |
      v                   v
COMPLETED_RECORD          FAILED_RECORD
      |                   |
      |                   v
      |              PRIOR_RECORD_RETAINED
      |
      v
GOVERNED_REASSESSMENT
      |
      v
NEW_CURRENT_RECORD
      |
      v
PRIOR_RECORD_SUPERSEDED
```

These are logical engineering states, not persistence, scheduling or runtime-processing requirements.

`ASSESSMENT_NOT_PERFORMED` terminates before the Capability Assessment boundary with an outcome only.

Both `ASSESSMENT_COMPLETED` and `ASSESSMENT_FAILED` occur after Capability Assessment Activity begins and therefore produce exactly one record containing both required determinations.

Provider-support and implementation-disposition values remain independent of lifecycle state.

# 22. Provider-Neutral Contracts

## 22.1 Capability Assessment Request Processing Contract

| Contract element | Requirement |
|---|---|
| Producer | Separately authorized assessment initiator |
| Consumer | Provider-owned Assessment Request Processing |
| Inputs | One immutable Capability Assessment Request |
| Outputs | Request eligibility or one `ASSESSMENT_NOT_PERFORMED` outcome with a bounded non-sensitive ineligibility reason |
| Preconditions | One request is presented for eligibility processing |
| Postconditions | An eligible request enters one Capability Assessment Activity; an ineligible request produces one `ASSESSMENT_NOT_PERFORMED` outcome without a Capability Assessment Record or determination |
| Failure conditions | Missing authority, unknown identifier, sensitive input, invalid evidence class or unauthorized endpoint evidence |

## 22.2 Capability Evidence Contract

| Contract element | Requirement |
|---|---|
| Producer | Approved evidence source |
| Consumer | Provider Capability Assessment |
| Inputs | Non-sensitive source material and compatibility basis |
| Outputs | Immutable Capability Evidence |
| Preconditions | Approved evidence class, attributable source and explicit currentness basis |
| Postconditions | Evidence meaning and limitations remain bounded to their source class |
| Failure conditions | Sensitive material, ambiguous source, missing basis, unauthorized evidence or unclassifiable meaning |

## 22.3 Capability Assessment Contract

| Contract element | Requirement |
|---|---|
| Producer | Provider |
| Consumer | Governed engineering consumers only |
| Inputs | One eligible request and its evidence set |
| Outputs | Exactly one Capability Assessment Outcome, one Capability Assessment Record, one Provider-Support determination and one KRONOS Implementation Disposition |
| Preconditions | Request eligibility and evidence boundary conformance |
| Postconditions | Separate support and implementation determinations, limitations, currentness, provenance and audit evidence |
| Failure conditions | Evidence-processing failure, incompatibility or an activity-level invariant violation produces `ASSESSMENT_FAILED` and one safe record containing both required determinations |

## 22.4 Capability Assessment Record Contract

| Contract element | Requirement |
|---|---|
| Producer | Provider |
| Consumer | Authorized repository governance, Engineering Verification and future GUI projection |
| Inputs | Completed or failed Capability Assessment Activity meanings |
| Outputs | Immutable provider-neutral Capability Assessment Record |
| Preconditions | Capability Assessment Activity began and exactly one assessment outcome and both required determinations exist |
| Postconditions | Record is attributable, non-sensitive, currentness-aware and non-destructive |
| Failure conditions | Potential sensitive content, inconsistent state, destructive supersession or incomplete record meaning shall produce a safe `ASSESSMENT_FAILED` record rather than unsafe publication or mutation |

## 22.5 GUI Readiness Contract

| Contract element | Requirement |
|---|---|
| Producer | Provider capability record projection |
| Consumer | Future separately authorized Administration Console |
| Inputs | One Capability Assessment Record |
| Outputs | Read-only GUI Readiness projection |
| Preconditions | Record exists and projection fields are non-sensitive |
| Postconditions | No new authority or semantic meaning is introduced |
| Failure conditions | Sensitive field exposure, unsupported inference or action-enabling output |

# 23. Provider-Internal Composition

Documentation assessment shall operate without authentication.

Adapter and locked-SDK compatibility assessment shall operate without authentication.

Where future separately authorized endpoint evidence requires authentication, Provider may internally compose:

```text
Provider Capability Assessment
            |
            v
Provider-internal context eligibility check
            |
            v
EDD-001 Provider access boundary
            |
            v
Kite-specific adapter-private operation
            |
            v
Provider-neutral Capability Evidence
```

The composition shall not expose:

- credentials;
- authentication material;
- SDK client;
- SDK response;
- SDK exception;
- authorization header; or
- adapter-private state.

The Authenticated Provider Context shall not become a transport handle in a provider-neutral contract.

# 24. EDD-001 Context-Reuse Checks

Endpoint evidence shall be ineligible unless all of the following are independently established:

1. endpoint evidence is separately authorized;
2. the Capability Identifier is approved;
3. the endpoint operation is read-only;
4. the Authenticated Provider Context is valid;
5. the context is not terminated;
6. Context Reuse Eligibility exists for the exact capability;
7. Provider identity is unchanged;
8. account or authorization context is unchanged;
9. operating environment is unchanged;
10. Configuration approval context is unchanged;
11. lifecycle and operational boundaries are unchanged;
12. sensitive material remains contained; and
13. no scope expansion occurs.

Failure of a check shall not establish `UNSUPPORTED`.

EDD-002 does not authorize endpoint evidence and therefore requires no Authenticated Provider Context for its initial documentation and compatibility assessment.

# 25. Failure and Indeterminacy Semantics

| Condition | Required engineering meaning | Prohibited inference |
|---|---|---|
| Unknown Capability Identifier | Pre-boundary `ASSESSMENT_NOT_PERFORMED`; no record or determination | Provider non-support |
| Missing assessment authority | Pre-boundary `ASSESSMENT_NOT_PERFORMED`; no record or determination | Provider non-support |
| Unauthorized evidence class | Pre-boundary `ASSESSMENT_NOT_PERFORMED`; no record or determination | Provider non-support |
| Evidence absent | `UNDETERMINED` | `UNSUPPORTED` |
| Evidence stale | `UNDETERMINED`, unless separate current evidence resolves the determination | `UNSUPPORTED` |
| Evidence conflict | `UNDETERMINED` and governed reassessment requirement | Silent capability change |
| Adapter or SDK incompatibility | Assessment failure or implementation `NOT_IMPLEMENTED` according to repository evidence | Provider non-support |
| Invalid Provider Context | Endpoint-evidence request remains pre-boundary and produces `ASSESSMENT_NOT_PERFORMED`; no record or determination | Provider non-support |
| Authentication failure | Endpoint evidence unavailable | Provider non-support |
| Timeout or transport failure | Endpoint or runtime evidence unavailable | Provider non-support |
| Throttling | Operational evidence only | Provider non-support |
| Account restriction or entitlement denial | Later entitlement evidence | Provider non-support |
| Generic `404` or `405` | Indeterminate endpoint evidence | Provider non-support |
| Malformed Provider response | Assessment failure or indeterminate evidence | Provider non-support |
| Provider unavailability | Operational availability meaning | Provider non-support |
| Parsing failure | Adapter failure | Provider non-support |

Failure shall preserve any prior valid current record.

Raw exception messages shall not cross the Provider boundary.

# 26. Provenance and Non-Sensitive Audit Evidence

Assessment provenance shall identify:

- assessment identity;
- record identity;
- Provider identity;
- Capability Identifier;
- assessment authority reference;
- evidence identities and classes;
- documentation references;
- Provider/API compatibility basis;
- locked-SDK version;
- adapter revision basis;
- assessment timestamp;
- determination values;
- currentness values;
- supersession relationship; and
- non-sensitive failure or indeterminacy reason.

Audit evidence shall establish only that:

- one assessment request was processed;
- one outcome was produced;
- one record was produced if and only if Capability Assessment Activity began;
- determination rules were applied;
- sensitive-data checks passed or failed; and
- supersession was or was not established.

Audit shall not acquire ownership of Provider capability meaning.

# 27. Security and Redaction Rules

EDD-002 shall apply deny-by-default sensitive-data handling.

The following shall never enter requests, evidence, outcomes, records, limitations, provenance, audit evidence, GUI projections, logs or errors:

- API secrets;
- request tokens;
- access tokens;
- refresh tokens;
- checksums;
- authorization headers;
- SDK clients;
- raw SDK responses;
- raw SDK exceptions;
- reconstructable authentication material;
- adapter-private transport state; or
- unnecessary account identity.

Provider-specific exceptions shall be translated into provider-neutral failure meanings.

Provider and SDK messages shall be redacted before any bounded non-sensitive representation is created.

SDK debug logging shall remain disabled.

Profile fields, including exchanges, products and order types, shall not be consumed or retained.

# 28. Deterministic Test Strategy

Verification shall use deterministic, isolated evidence fixtures.

Tests shall require no:

- live credentials;
- network access;
- Provider endpoint;
- wall-clock dependency;
- SDK client construction; or
- account profile.

## 28.1 Required unit verification

Unit verification shall cover:

- all six Capability Identifiers;
- request eligibility;
- each evidence class;
- each support determination;
- each implementation disposition;
- all nine valid state combinations;
- high-threshold `UNSUPPORTED` rules;
- explicit `UNDETERMINED` rules;
- current, stale and undetermined currentness;
- Capability Limitation preservation;
- one outcome for every processed request;
- no record or determination for `ASSESSMENT_NOT_PERFORMED`;
- exactly one record and both determinations for `ASSESSMENT_COMPLETED`;
- exactly one record and both determinations for `ASSESSMENT_FAILED`;
- `UNDETERMINED` support where assessment failure prevents a support conclusion;
- record immutability;
- non-destructive supersession;
- failure preservation of prior records;
- security and redaction; and
- GUI projection restrictions.

## 28.2 Required boundary verification

Boundary tests shall confirm:

- no SDK import outside the Kite adapter package;
- no SDK type crosses provider-neutral contracts;
- no sensitive field exists in provider-neutral models;
- no business-domain import enters Provider Capability Assessment;
- no profile-field dependency exists;
- no capability execution occurs;
- no endpoint invocation occurs;
- no implementation authority is inferred; and
- no EDD-003 behaviour exists.

## 28.3 Required evidence tests

Table-driven evidence tests shall prove that:

- official documentation can establish `SUPPORTED`;
- SDK compatibility alone cannot establish Provider support;
- adapter absence cannot establish `UNSUPPORTED`;
- endpoint and runtime evidence cannot silently redefine capability;
- evidence conflict produces `UNDETERMINED`;
- stale evidence does not independently establish a current determination; and
- reassessment creates a new record and preserves its predecessor.

# 29. Engineering Lab Validation Criteria

Independent Engineering Lab validation shall:

1. read canonical ADR-007 and the approved EDD-002;
2. review the official Kite documentation references;
3. inspect official pykiteconnect Version 5.2.0 methods and tests;
4. verify the repository dependency lock;
5. inspect the actual KRONOS provider-neutral contracts and Kite adapters;
6. verify all six capability mappings;
7. verify every initial implementation disposition;
8. verify that no live endpoint was invoked;
9. verify sensitive-data containment;
10. verify that account profile fields were excluded;
11. verify that support, implementation, entitlement, availability and authority remain separate;
12. run focused unit and boundary tests;
13. run the complete repository test suite;
14. run compilation and build validation where implementation is later authorized;
15. run `git diff --check`; and
16. report defects without modifying architecture.

Engineering Lab validation shall choose one:

- EDD-002 implementation fully validated;
- implementation correction required; or
- EDD-002 amendment required.

This document does not authorize implementation or the validation execution of future implementation.

# 30. GUI Readiness

The provider-neutral GUI Readiness projection may contain only:

- Provider identity;
- Capability Identifier;
- canonical display name;
- Provider-Support determination;
- KRONOS Implementation Disposition;
- evidence classes;
- determination timestamp;
- Evidence Currentness;
- superseded indication;
- non-sensitive Capability Limitations; and
- non-sensitive provenance reference.

It shall not contain:

- account identity;
- entitlement;
- Dataset Permission;
- Acquisition Authority;
- current Service Availability;
- credentials;
- SDK or adapter objects;
- operation controls;
- retry controls;
- acquisition controls; or
- business-readiness meaning.

GUI Readiness is informational and non-authoritative.

# 31. Kite Evidence Mapping

The initial mapping is a documentation and compatibility assessment only.

Official documentation was reviewed on 2026-07-26. SDK compatibility was assessed against official pykiteconnect Version 5.2.0. KRONOS implementation disposition was assessed from the published repository state at the EDD-002 Draft baseline.

| Capability Identifier | Official documentation evidence | SDK implementation evidence | Provider support | KRONOS disposition | Capability Limitations |
|---|---|---|---|---|---|
| Instrument Reference Capability | [Market quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/) documents `/instruments` and `/instruments/:exchange`. | `KiteConnect.instruments(exchange=None)` and the SDK CSV parser represent the documented mechanics. | `SUPPORTED` | `NOT_IMPLEMENTED` | The dump is generated once daily; it is large; documented `last_price` is not real time; instrument tokens may be reused after derivative expiry. |
| Full Quote Snapshot Capability | [Market quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/) documents `/quote`. | `KiteConnect.quote()` represents the documented request and response mechanics. | `SUPPORTED` | `NOT_IMPLEMENTED` | Maximum 500 instruments per request; requested keys may be absent when data is unavailable. |
| OHLC Snapshot Capability | [Market quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/) documents `/quote/ohlc`. | `KiteConnect.ohlc()` represents the documented mechanics. | `SUPPORTED` | `NOT_IMPLEMENTED` | Maximum 1000 instruments per request; requested keys may be absent; the response is a current snapshot, not a completed historical candle. |
| LTP Snapshot Capability | [Market quotes and instruments](https://kite.trade/docs/connect/v3/market-quotes/) documents `/quote/ltp`. | `KiteConnect.ltp()` represents the documented mechanics. | `SUPPORTED` | `NOT_IMPLEMENTED` | Maximum 1000 instruments per request; requested keys may be absent. |
| Historical Observation Capability | [Historical candle data](https://kite.trade/docs/connect/v3/historical/) documents the historical endpoint and interval vocabulary. | `KiteConnect.historical_data()` represents the documented request and formats candle records. | `SUPPORTED` | `NOT_IMPLEMENTED` | Documented intervals are minute, day, 3minute, 5minute, 10minute, 15minute, 30minute and 60minute; continuous history is limited to documented NFO and MCX futures behaviour and day candles. |
| Live Observation Streaming Capability | [WebSocket streaming](https://kite.trade/docs/connect/v3/websocket/) documents live quote streaming. | `KiteTicker` represents connection, subscription, mode and binary-decoding mechanics. | `SUPPORTED` | `DEFERRED` | Up to 3000 instruments per connection and up to three WebSocket connections per API key; current roadmap authority defers implementation. |

## 31.1 Mapping restrictions

The mapping shall not:

- invoke any documented endpoint;
- use profile fields;
- infer account entitlement;
- infer current Service Availability;
- infer Dataset Permission;
- infer Acquisition Authority;
- infer acquisition success;
- import SDK response shapes into provider-neutral contracts; or
- authorize the SDK mechanics listed above.

# 32. Architecture Traceability Matrix

| EDD-002 design meaning | Governing authority |
|---|---|
| Provider Capability Assessment ownership | ADR-007 Sections 1, 4 and 5; DOMAIN-006 |
| Six Capability Identifiers | ADR-007 Section 7 |
| Provider-Support determination | ADR-007 Sections 8 and 12 |
| KRONOS Implementation Disposition | ADR-007 Section 9 |
| Valid state combinations | ADR-007 Section 10 |
| Evidence classes | ADR-007 Section 11 |
| High threshold for `UNSUPPORTED` | ADR-007 Sections 12 and 13 |
| Capability Limitations | ADR-007 Section 14 |
| Context reuse | ADR-007 Section 15; EDD-001 |
| Provider-internal composition | ADR-007 Section 16; EDD-001 |
| Currentness and supersession | ADR-007 Section 17 |
| Sensitive-data boundary | ADR-007 Section 18; EDD-001 |
| Prohibited dependencies | ADR-007 Sections 19 and 20 |
| GUI Readiness | ADR-007 Section 21 |
| EDD-002 boundary | ADR-007 Section 22 |
| Architectural stability | ADR-007 Section 2.1 |

# 33. Explicit Exclusions

EDD-002 excludes:

- Account Entitlement;
- profile exchanges;
- profile products;
- profile order types;
- account identity;
- Dataset Permission;
- Acquisition Authority;
- instrument acquisition;
- quote acquisition;
- historical acquisition;
- live streaming;
- Instrument interpretation;
- Provider-to-Instrument mapping;
- Observation processing;
- Validation;
- Risk;
- Execution;
- Portfolio;
- orders;
- positions;
- holdings;
- funds;
- margins;
- GTT;
- mutual funds;
- retries;
- scheduling;
- caching;
- batching;
- persistence;
- deployment;
- runtime infrastructure;
- endpoint invocation;
- implementation;
- EDD-003; and
- any capability not listed in Section 8.

# 34. Engineering Invariants

1. Provider shall remain the sole owner of Provider Capability Assessment.
2. Exactly one approved Capability Identifier shall be assessed per activity.
3. Every processed request shall produce exactly one Capability Assessment Outcome; `ASSESSMENT_NOT_PERFORMED` shall occur before the Capability Assessment boundary and shall produce no record or determination.
4. Every Capability Assessment Activity that begins shall produce exactly one Capability Assessment Record containing exactly one Provider-Support determination and exactly one KRONOS Implementation Disposition.
5. Provider support and KRONOS implementation disposition shall remain separate.
6. Capability shall not imply Account Entitlement.
7. Capability shall not imply Service Availability.
8. Capability shall not imply Dataset Permission.
9. Capability shall not imply Acquisition Authority.
10. Capability shall not imply Runtime Observation or Business Meaning.
11. SDK compatibility alone shall not establish Provider support.
12. Authentication Success shall not establish Provider capability.
13. Profile fields shall not be used as capability evidence.
14. Runtime evidence shall not silently redefine Provider Capability.
15. Reassessment shall be governed and shall create a new record.
16. Supersession shall be non-destructive.
17. Context invalidation shall not erase provider-wide evidence.
18. Context termination shall not erase provider-wide evidence.
19. Documentation assessment shall not require authentication.
20. Adapter and SDK compatibility assessment shall not require authentication.
21. Endpoint evidence shall require separate authorization.
22. EDD-002 shall not invoke a Provider endpoint.
23. `UNSUPPORTED` shall require explicit authoritative evidence.
24. Incidental failure shall not establish `UNSUPPORTED`.
25. Evidence conflict shall produce `UNDETERMINED`.
26. Stale evidence shall not independently establish a current determination.
27. SDK types shall not cross provider-neutral contracts.
28. Credentials shall not enter assessment representations.
29. Raw Provider or SDK responses shall not enter assessment records.
30. Capability Limitations shall not authorize operational mechanisms.
31. An SDK method shall not establish `IMPLEMENTED`.
32. Empty protocols and skeletons shall not establish `IMPLEMENTED`.
33. Live Observation Streaming Capability shall remain `DEFERRED` under current authority.
34. GUI Readiness shall remain read-only and non-authoritative.
35. EDD-002 approval shall not authorize implementation.

# 35. Open Engineering Issues

No unresolved engineering issue remains following Engineering Verification and Chief Architect approval.

The following are governed deferrals, not blockers:

- endpoint evidence remains unauthorized;
- Provider Capability Assessment implementation remains unauthorized;
- persistence remains excluded;
- EDD-003 remains unauthorized; and
- future capability identifiers require separate architecture.

# 36. Review and Approval Record

**Engineering Verification:** Complete

**Chief Architect Decision:** Approved

**Canonical Status:** Canonical

**Implementation Authorization:** None

**Commit Authorization:** None

**Push Authorization:** None

**Next Authorized Capability:** None

# 37. Review History

| Version | Activity | Result |
|---|---|---|
| 0.1 | Chief Architect-authorized initial EDD-002 Draft preparation | Draft prepared for Engineering Verification |
| 0.1 | Engineering Verification and controlled amendment EV-EDD002-001 | Engineering Verification passed; request-processing and Capability Assessment cardinality clarified |
| 1.0 | Chief Architect approval, canonicalization and repository publication | Approved and Canonical; implementation remains unauthorized |

---

# End of Document
