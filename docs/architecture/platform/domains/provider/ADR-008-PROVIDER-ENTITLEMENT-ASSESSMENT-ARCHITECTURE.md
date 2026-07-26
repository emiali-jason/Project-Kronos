# ADR-008 — Provider Entitlement Assessment Architecture

**Document ID:** ADR-008
**Title:** Provider Entitlement Assessment Architecture
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Approved Canonical Architecture
**Classification:** Architecture Decision Record
**Owner:** Chief Architect
**Prepared By:** Codex Engineering Team
**Approved By:** Chief Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/architecture/platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md`
**Decision Scope:** Platform Provider Domain
**Architecture Impact:** Bounded Provider Entitlement Assessment authority
**Engineering Impact:** None
**Runtime Impact:** None
**EDD-003 Drafting Authorization:** None
**Implementation Authorization:** None

---

# 1. Purpose

This document defines the platform architecture for Provider Entitlement Assessment within Project KRONOS.

Provider Entitlement Assessment determines which account-specific entitlements a Provider explicitly reports for one authenticated Provider account.

This architecture preserves the distinction between:

- Authentication;
- Provider Capability;
- Provider-Reported Entitlement;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Service Availability;
- Provider Operational Availability;
- Execution permission; and
- Business Meaning.

This document defines architecture only.

It authorizes no:

- Engineering Design Document;
- implementation;
- dependency change;
- authenticated profile operation;
- runtime activity;
- acquisition;
- order activity; or
- downstream business operation.

# 2. Authority and Applicability

This architecture applies to every KRONOS product or engineering capability that needs to represent account-specific entitlement reported by a Provider.

It derives from:

- PLATFORM-000 — KRONOS Platform Constitution;
- DOMAIN-006 — Provider Domain;
- Domain Ownership Matrix;
- Domain Dependency Matrix;
- ADR-007 — Provider Capability Assessment Architecture;
- EDD-001 — Provider Access and Provider Context Engineering Design;
- EDD-002 — Provider Capability Assessment Engineering Design;
- DOC-001 — Document Identification, Classification & Metadata Standard; and
- GOV-002 — KRONOS Governance Lifecycle.

Official Provider documentation may establish the documented meaning of Provider fields.

Official SDK evidence may establish the availability of suitable Provider transport mechanics.

Neither Provider documentation nor SDK evidence may redefine KRONOS architecture, semantic ownership, entitlement meaning, or operational authority.

Where Provider documentation, SDK behavior, or implementation conflicts with canonical KRONOS architecture, canonical KRONOS architecture shall prevail.

## 2.1 Architectural Stability Principle

Provider-Reported Entitlement shall be established, changed, or withdrawn only through governed Provider Entitlement Assessment using approved account-specific evidence.

A runtime condition may identify a need for reassessment. It shall not silently create, extend, narrow, withdraw, or redefine Provider-Reported Entitlement.

Reassessment is a governed activity.

Reassessment shall produce a new traceable Provider Entitlement Assessment Record and, where applicable, non-destructive supersession of the earlier record.

## 2.2 Entitlement Scope Principle

Capability is Provider-scoped.

Entitlement is Account-scoped.

Dataset Permission is Platform-scoped.

Acquisition Authority is Operation-scoped.

These scopes are independent and shall not be substituted, merged, or inferred from one another.

## 2.3 Positive Evidence Principle

Provider Entitlement Assessment represents only explicit Provider-reported entitlement.

Missing values shall not be interpreted as denial unless the Provider contract explicitly assigns that meaning.

# 3. Architectural Question

This architecture answers exactly one question:

> Given a valid Authenticated Provider Context, what account-specific entitlements does the Provider explicitly report for this authenticated account?

No other architectural meaning shall be established by this assessment.

# 4. Terminology

| Term | Architectural meaning |
|---|---|
| Provider Entitlement Assessment | One bounded, read-only, Provider-owned assessment of account-specific entitlement explicitly reported for one authenticated Provider account. |
| Entitlement Assessment Request Processing | Pre-boundary determination of whether the approved inputs and context-reuse conditions required to begin an assessment exist. |
| Entitlement Assessment Activity | The Provider-owned assessment activity performed for one Provider, one authenticated account context, and the approved Provider Entitlement Identifier family. |
| Provider Entitlement Identifier | A stable provider-neutral category identifying the kind of account-specific entitlement being assessed. |
| Provider Entitlement Evidence | Account-specific Provider evidence used to determine Provider-Reported Entitlement. |
| Authenticated Profile Evidence | Provider Entitlement Evidence obtained through an explicitly authorized, read-only authenticated profile operation. |
| Provider-Reported Entitlement | A Provider-owned determination that the Provider explicitly reported one account-specific entitlement value in an approved entitlement category. |
| Entitlement Indeterminate | A Provider-owned determination that available evidence cannot establish a Provider-Reported Entitlement safely and conclusively. |
| Entitlement Assessment Outcome | The bounded result of request processing or an Entitlement Assessment Activity. |
| Provider Entitlement Assessment Record | The immutable Provider-owned record produced when an Entitlement Assessment Activity begins. It contains the outcome, reported entitlements, indeterminate evidence, currentness, provenance, and applicable supersession references. |
| Entitlement Currentness | The stated account, context, evidence, and temporal basis under which a Provider Entitlement Assessment Record remains applicable. |
| Entitlement Reassessment | A later governed Provider Entitlement Assessment performed using a newly authorized evidence basis. |
| Entitlement Supersession | Non-destructive replacement of an earlier entitlement assessment by a later governed assessment. |
| Account Continuity | The Provider-owned determination that the Provider account and authorization context applicable to the assessment remain unchanged. |
| Unrecognized Provider Vocabulary | An evidence-classification or failure cause arising when a Provider-reported value cannot be safely represented under the approved provider-neutral entitlement model. It results in Entitlement Indeterminate and is not an independent entitlement determination. |
| Provider Capability | Provider-wide technical support governed by ADR-007. It is independent of account-specific entitlement. |
| Dataset Permission | Platform-scoped architectural permission for a governed dataset. It is not established by Provider Entitlement Assessment. |
| Acquisition Authority | Operation-scoped, separately approved authority for one bounded acquisition operation. It is not established by Provider Entitlement Assessment. |
| Runtime Authority | Explicit authority to perform a runtime operation. It is not established by Provider Entitlement Assessment. |
| Business Meaning | Meaning owned by an approved business domain. Provider Entitlement Assessment creates none. |

# 5. Provider Ownership

Provider is the exclusive semantic owner of:

- Provider Entitlement Assessment;
- Entitlement Assessment Request Processing;
- Entitlement Assessment Activity;
- Provider Entitlement Identifiers;
- Provider Entitlement Evidence;
- Provider-Reported Entitlement;
- Entitlement Indeterminate;
- Entitlement Assessment Outcomes;
- Provider Entitlement Assessment Records;
- entitlement currentness;
- entitlement reassessment;
- entitlement supersession;
- entitlement provenance;
- entitlement-assessment failure; and
- account continuity within the Provider boundary.

This assignment is a bounded specialization of the Provider Integration responsibility assigned to Provider by the Domain Ownership Matrix.

Provider ownership shall not transfer ownership of:

- Configuration Meaning;
- Provider Capability;
- Dataset Permission;
- Acquisition Authority;
- Instrument identity;
- Market meaning;
- Observation facts;
- Validation judgment;
- Risk approval;
- Execution permission;
- Orders;
- Portfolio state;
- Event meaning;
- Audit meaning; or
- Business Meaning.

Audit may consume published Provider entitlement evidence read-only.

Audit shall not acquire Provider entitlement ownership or modify the recorded meaning.

# 6. Assessment Boundary

## 6.1 Pre-Boundary Request Processing

Entitlement Assessment Request Processing occurs before the Provider Entitlement Assessment boundary.

Request processing shall establish whether all approved assessment inputs exist.

Required inputs are:

1. one approved Provider identity;
2. one valid Authenticated Provider Context;
3. explicit Context Reuse Eligibility for the exact entitlement-assessment operation;
4. unchanged authenticated account identity;
5. unchanged authorization context;
6. unchanged operating environment;
7. unchanged Configuration approval context;
8. an approved entitlement evidence source;
9. an assessment time; and
10. available sensitive-material containment.

Where a required input is missing or invalid:

- the Entitlement Assessment Activity shall not begin;
- the outcome shall be `ASSESSMENT_NOT_PERFORMED`;
- no Provider Entitlement Assessment Record shall be produced;
- no Provider-Reported Entitlement shall be established; and
- no negative entitlement conclusion shall be made.

## 6.2 Assessment Boundary Entry

The Provider Entitlement Assessment boundary begins only after all required inputs and context-reuse conditions have been established.

The boundary contains:

- the authorized read-only entitlement-evidence operation;
- Provider-specific evidence isolation;
- evidence classification;
- data minimization;
- provider-neutral entitlement representation;
- Provider-Reported Entitlement determination;
- Entitlement Indeterminate determination;
- assessment outcome determination;
- currentness;
- provenance;
- failure representation;
- reassessment references; and
- supersession references.

## 6.3 Assessment Boundary Exit

Once an Entitlement Assessment Activity begins, it shall produce exactly one:

- Entitlement Assessment Outcome; and
- Provider Entitlement Assessment Record.

The record may contain:

- zero or more Provider-Reported Entitlements;
- zero or more indeterminate entitlement evidence entries;
- one currentness determination;
- one evidence basis;
- one assessment time;
- applicable non-sensitive provenance; and
- applicable supersession references.

A structurally valid Provider response containing an empty entitlement category may produce a completed assessment with no Provider-Reported Entitlement for that category.

An absent value shall not establish entitlement denial.

## 6.4 Publication Boundary

Only provider-neutral Provider-Reported Entitlement information may cross the Provider publication boundary.

The following shall remain inside the Provider adapter boundary:

- raw profile payloads;
- SDK response objects;
- SDK exceptions;
- SDK clients;
- authentication tokens;
- authorization headers;
- Provider credentials;
- personal identity information; and
- adapter-private transport state.

# 7. Explicit Non-Implications

Provider Entitlement Assessment shall never imply:

- Provider Capability;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Service Availability;
- Provider Operational Availability;
- Observation;
- Instrument meaning;
- Market meaning;
- Validation;
- Risk;
- Execution permission;
- order permission;
- Portfolio meaning;
- Business Meaning;
- implementation authority; or
- permission to initiate any operation.

Authentication, Provider Capability, and Provider-Reported Entitlement are independent architectural determinations.

Authentication Success shall not establish Provider-Reported Entitlement.

Provider Capability shall not establish Provider-Reported Entitlement.

Provider-Reported Entitlement shall not establish Provider Capability.

No combination of Authentication Success, Provider Capability, and Provider-Reported Entitlement shall establish Dataset Permission, Acquisition Authority, Runtime Authority, or Business Meaning.

# 8. Provider Entitlement Identifier Family

ADR-008 establishes one provider-neutral identifier family:

**Provider Entitlement Identifier**

The family contains exactly three initial categories:

| Provider Entitlement Identifier | Architectural scope |
|---|---|
| Exchange Entitlement | Account-specific exchange entitlement explicitly reported by the Provider. |
| Product Entitlement | Account-specific product entitlement explicitly reported by the Provider. |
| Order-Type Entitlement | Account-specific order-type entitlement explicitly reported by the Provider. |

The three categories are mandatory and non-interchangeable.

A Provider-reported product value shall not be classified as an exchange or order-type entitlement.

A Provider-reported exchange value shall not establish:

- canonical venue identity;
- Instrument scope;
- Market Schedule;
- Market state;
- dataset scope; or
- Execution permission.

A Provider-reported product value shall not establish product behavior, margin behavior, or an Execution rule.

A Provider-reported order-type value shall not establish order semantics or permission to submit an order.

Future Provider Entitlement Identifiers require separate architectural approval.

# 9. Provider Entitlement Representation

A provider-neutral Provider-Reported Entitlement shall identify:

- Provider identity;
- protected authenticated-account context reference;
- Provider Entitlement Identifier;
- sanitized Provider-scoped entitlement value;
- evidence class;
- evidence time;
- currentness;
- assessment record reference; and
- non-sensitive provenance reference.

A Provider-scoped entitlement value shall remain descriptive Provider evidence.

It shall not become:

- canonical Market vocabulary;
- canonical Instrument vocabulary;
- canonical Execution vocabulary;
- a Dataset Permission;
- an operational instruction; or
- a business-domain contract.

Provider-specific vocabulary shall not be exposed as an SDK constant, SDK type, or raw Provider payload.

Where Provider vocabulary cannot be safely classified, Unrecognized Provider Vocabulary shall be recorded as an evidence-classification or failure cause and shall result in Entitlement Indeterminate.

# 10. Authenticated Profile Evidence

The initial Provider evidence basis is the authenticated Provider profile.

For Kite, official Provider documentation identifies:

- `exchanges` as exchanges reported for the authenticated account;
- `products` as margin product types reported for the authenticated account; and
- `order_types` as order types reported for the authenticated account.

These fields may supply Provider Entitlement Evidence only.

The official Provider documentation does not grant KRONOS authority to:

- perform the profile operation;
- retain the profile payload;
- interpret the values as Business Meaning;
- infer Dataset Permission;
- infer Acquisition Authority; or
- initiate an operation.

The official pykiteconnect SDK supplies authenticated profile transport mechanics only.

SDK mechanics shall not create Provider entitlement architecture.

# 11. Profile Field Classification

| Provider field | Provider meaning | Architectural owner | ADR-008 treatment | Later architectural treatment |
|---|---|---|---|---|
| `exchanges` | Account-specific exchanges reported by the Provider | Provider for Provider-Reported Entitlement | Included as Exchange Entitlement evidence | Venue, Instrument, Market, and Execution interpretation remain separate |
| `products` | Account-specific margin product types reported by the Provider | Provider for Provider-Reported Entitlement | Included as Product Entitlement evidence | Product behavior and operational use require later Execution architecture |
| `order_types` | Account-specific order types reported by the Provider | Provider for Provider-Reported Entitlement | Included as Order-Type Entitlement evidence | Order semantics and operational use remain Execution-owned |
| `user_id` | Permanent Provider account identity | Provider for bounded account correlation only | May establish account continuity through a protected reference | Shall not become canonical person or business identity |
| `user_name` | Personal identity | Outside Provider entitlement ownership | Excluded | No ownership assigned by ADR-008 |
| `user_shortname` | Abbreviated personal identity | Outside Provider entitlement ownership | Excluded | Presentation concern |
| `email` | Personal contact information | Outside Provider entitlement ownership | Excluded and redacted | No Provider entitlement use |
| `avatar_url` | Presentation metadata | Outside Provider entitlement ownership | Excluded | No Provider entitlement use |
| `user_type` | Provider account classification | Provider metadata | Excluded from Provider-Reported Entitlement | Requires separate authority for later use |
| `broker` | Provider or account-affiliation metadata | Provider metadata | May support non-sensitive Provider provenance only | Shall not redefine canonical Provider identity |
| `meta.demat_consent` | Provider-specific consent metadata | Not assigned by this architecture | Excluded | Requires later separately approved account-operation or Execution architecture |
| Other personal identity | Provider-held personal information | Outside Provider entitlement ownership | Excluded | No ownership assigned by ADR-008 |

The authentication token-exchange response may include authentication material and session metadata that do not appear in the dedicated profile response.

Such fields are governed by EDD-001 and are prohibited from Provider Entitlement Assessment.

# 12. Evidence Transformation Chain

Provider Entitlement Assessment shall use an evidence transformation chain rather than treating processing stages as separate evidence authorities.

## 12.1 Authorized Authenticated Profile Evidence

Authenticated Profile Evidence is the primary account-specific evidence.

It may establish only what the Provider explicitly reported for the authenticated account at the evidence time.

It shall not establish:

- Provider-wide support;
- cross-account entitlement;
- permanent entitlement;
- current Service Availability;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority; or
- Business Meaning.

## 12.2 Provider-Specific Evidence Classification

Provider-specific evidence classification occurs inside the Provider adapter boundary.

It shall:

- identify the approved entitlement fields;
- separate personal identity;
- separate Provider metadata;
- separate later-domain information;
- reject sensitive material;
- identify malformed evidence;
- identify Unrecognized Provider Vocabulary; and
- preserve the Provider evidence source.

Provider-specific evidence classification shall not reinterpret the reported value.

## 12.3 Provider-Neutral Entitlement Representation

A Provider-neutral representation may be established only after approved evidence classification and data minimization.

The representation shall preserve:

- entitlement category;
- Provider-scoped reported value;
- account continuity;
- evidence time;
- currentness; and
- non-sensitive provenance.

## 12.4 Governed Reassessment

Runtime or later evidence may identify a need for reassessment.

It shall not mutate an existing record or silently redefine Provider-Reported Entitlement.

A reassessment shall:

- be separately governed;
- satisfy the complete assessment boundary again;
- produce a new record;
- preserve the prior record; and
- record any supersession relationship.

# 13. Assessment Outcomes

Entitlement Assessment Outcome shall use exactly one of:

- `ASSESSMENT_NOT_PERFORMED`;
- `ASSESSMENT_COMPLETED`; or
- `ASSESSMENT_FAILED`.

## 13.1 Assessment Not Performed

`ASSESSMENT_NOT_PERFORMED` applies only before the assessment boundary.

It shall produce:

- one request-processing outcome;
- no Entitlement Assessment Activity;
- no Provider Entitlement Assessment Record;
- no Provider-Reported Entitlement; and
- no entitlement determination.

## 13.2 Assessment Completed

`ASSESSMENT_COMPLETED` applies when the approved evidence operation and classification activity complete within the authorized boundary.

It may produce:

- one or more Provider-Reported Entitlements;
- no Provider-Reported Entitlements for a valid empty category;
- indeterminate evidence entries where a bounded portion cannot be classified; and
- one immutable Provider Entitlement Assessment Record.

## 13.3 Assessment Failed

`ASSESSMENT_FAILED` applies after an Entitlement Assessment Activity begins but cannot complete safely.

It shall produce:

- exactly one safe Provider Entitlement Assessment Record;
- Entitlement Indeterminate;
- the applicable non-sensitive failure cause;
- currentness appropriate to the failed evidence basis; and
- no negative entitlement conclusion.

# 14. Provider-Reported Entitlement Semantics

Provider-Reported Entitlement requires:

- a valid approved evidence source;
- one approved Provider Entitlement Identifier;
- one explicitly reported Provider-scoped value;
- unchanged Provider identity;
- established account continuity;
- an applicable evidence time;
- successful sensitive-data containment; and
- no unresolved evidence conflict for that value.

Provider-Reported Entitlement means only that the Provider reported that account-specific entitlement at the evidence time.

Provider-Reported Entitlement shall not mean that:

- the Provider supports a related technical capability;
- KRONOS implements the related capability;
- a dataset is permitted;
- an acquisition is authorized;
- an operation may run;
- the related service is available;
- an order may be submitted; or
- a business action is permitted.

# 15. Entitlement Indeterminate

Entitlement Indeterminate applies when available evidence is:

- absent;
- incomplete;
- malformed;
- stale;
- conflicting;
- unauthorized;
- unavailable;
- unsafe to publish;
- associated with an invalid context;
- associated with unresolved account continuity; or
- affected by Unrecognized Provider Vocabulary.

Entitlement Indeterminate shall not be strengthened into:

- entitlement denial;
- Provider capability non-support;
- Dataset Permission denial;
- Acquisition Authority denial;
- Runtime Authority denial; or
- business prohibition.

An absent value shall not independently establish a negative entitlement determination.

Unrecognized Provider Vocabulary is a cause of Entitlement Indeterminate only.

It is not an independent entitlement determination, outcome, or published entitlement state.

# 16. Context Reuse

An EDD-001 Authenticated Provider Context may be reused only for an explicitly authorized, read-only Provider Entitlement Assessment operation.

Context reuse requires:

1. a valid Authenticated Provider Context;
2. explicit Context Reuse Eligibility for the exact entitlement operation;
3. unchanged Provider identity;
4. unchanged authenticated account identity;
5. unchanged authorization context;
6. unchanged operating environment;
7. unchanged Configuration approval context;
8. unchanged lifecycle boundary;
9. unchanged sensitive classification;
10. adapter-private containment; and
11. no expansion into another capability or operation.

A context that is invalidated or terminated shall not be reused.

Context reuse shall not establish Provider-Reported Entitlement by itself.

Context reuse shall not grant:

- Provider Capability;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Service Availability;
- Provider Operational Availability; or
- Business Meaning.

# 17. Entitlement Currentness

Every Provider Entitlement Assessment Record shall state its currentness.

Currentness shall use:

- `CURRENT`;
- `STALE`;
- `SUPERSEDED`; or
- `UNDETERMINED`.

## 17.1 Current

A record may be `CURRENT` only while:

- Provider identity remains unchanged;
- account continuity remains established;
- the evidence basis remains applicable;
- no later assessment supersedes the record;
- no evidence conflict is known; and
- its Authenticated Provider Context remains valid for current operational reliance.

## 17.2 Stale

A record shall become `STALE` when:

- its source context is invalidated;
- its source context is terminated;
- Provider identity changes;
- account continuity is lost;
- the evidence basis is no longer current;
- a known Provider change makes the evidence uncertain; or
- continued applicability cannot be established.

This architecture defines no fixed expiry interval, polling interval, or reassessment schedule.

## 17.3 Superseded

A record becomes `SUPERSEDED` only through a later governed assessment that explicitly references and replaces it.

Supersession shall be non-destructive.

## 17.4 Undetermined Currentness

Currentness shall be `UNDETERMINED` where available evidence cannot establish whether the record remains applicable.

Undetermined currentness shall prevent current operational reliance.

# 18. Context Invalidation and Termination

Context Invalidation and Context Termination shall end eligibility to rely on context-specific Provider-Reported Entitlement as current operational evidence.

They shall not:

- erase the Provider Entitlement Assessment Record;
- erase provenance;
- rewrite the earlier assessment;
- convert the result into entitlement denial;
- change Provider Capability; or
- create a new entitlement determination.

Historical entitlement evidence survives Context Invalidation and Context Termination for traceability and audit.

Historical evidence shall not remain eligible as current operational evidence merely because it is preserved.

# 19. Reassessment and Supersession

Entitlement reassessment is a governed Provider-owned activity.

Reassessment shall require:

- a valid assessment request;
- current Context Reuse Eligibility;
- a valid Authenticated Provider Context;
- account continuity;
- an approved evidence source;
- a new assessment time; and
- complete security containment.

Reassessment shall produce a new immutable Provider Entitlement Assessment Record.

A later record may:

- confirm an earlier Provider-Reported Entitlement;
- add newly reported entitlement;
- omit a previously reported entitlement without declaring denial;
- produce Entitlement Indeterminate;
- establish that the prior record is stale; or
- supersede the prior record.

Reassessment shall not mutate the prior record.

# 20. Failure Semantics

The following failure meanings are approved:

| Failure meaning | Architectural treatment |
|---|---|
| Assessment Not Performed | Required pre-boundary input or authority was absent. No assessment record or determination is produced. |
| Context Invalid | The required Authenticated Provider Context is invalid or terminated. No entitlement conclusion is produced. |
| Profile Unavailable | Authorized profile evidence could not be obtained. Entitlement remains indeterminate. |
| Insufficient Evidence | Evidence cannot support a Provider-Reported Entitlement safely. |
| Malformed Profile | The Provider evidence cannot be classified reliably. The activity fails safely. |
| Unrecognized Provider Vocabulary | Evidence classification cannot represent the Provider value under an approved entitlement category. It results in Entitlement Indeterminate. |
| Provider Operational Failure | Provider could not support the assessment activity at that time. No capability or entitlement conclusion follows. |
| Entitlement Indeterminate | Evidence cannot support a determinate Provider-Reported Entitlement. |

A failure shall not retroactively change a prior valid record.

Failure shall not imply:

- Provider capability is unsupported;
- entitlement is denied;
- Dataset Permission is denied;
- Acquisition Authority is denied;
- Runtime Authority is denied; or
- business activity is prohibited.

# 21. Provenance

Every Provider Entitlement Assessment Record shall preserve:

- Provider identity;
- protected account-context reference;
- Provider Entitlement Identifier;
- sanitized Provider-scoped entitlement values;
- evidence class;
- official Provider-documentation basis;
- applicable Provider or API basis;
- assessment time;
- assessment outcome;
- currentness;
- non-sensitive failure cause where applicable;
- prior record reference where applicable;
- supersession reason where applicable; and
- non-sensitive audit reference.

Provenance shall not contain:

- raw personal identity;
- raw profile payloads;
- authentication material;
- SDK objects;
- SDK exceptions;
- authorization headers; or
- adapter-private state.

Provenance shall preserve source meaning without acquiring authority over it.

# 22. Security and Sensitive-Data Boundaries

Provider Entitlement Assessment shall apply deny-by-default data minimization.

The following shall never enter Provider Entitlement Assessment requests, records, published representations, provenance, audit evidence, GUI projections, logs, or errors:

- API secrets;
- request tokens;
- access tokens;
- refresh tokens;
- checksums;
- authorization headers;
- SDK clients;
- SDK response objects;
- raw SDK exceptions;
- reconstructable authentication material;
- adapter-private transport state;
- raw profile payloads;
- personal names;
- email addresses;
- avatar references; or
- unnecessary account identity.

Provider-specific responses shall remain inside the Provider adapter boundary.

Sensitive and excluded fields shall be discarded after the approved non-sensitive meaning has been established.

SDK and Provider exceptions shall be translated into Provider-owned, provider-neutral failure meanings.

SDK debug logging shall not be enabled through this architecture.

The SDK client shall not become:

- the Authenticated Provider Context;
- Provider Entitlement Evidence;
- a Provider Entitlement Assessment Record; or
- a published Provider contract.

# 23. Dependencies

Provider Entitlement Assessment depends on:

- approved Provider identity;
- canonical Provider ownership;
- a valid Authenticated Provider Context;
- explicit Context Reuse Eligibility;
- account continuity;
- approved Provider Entitlement Identifiers;
- authorized Authenticated Profile Evidence;
- official Provider documentation;
- approved adapter containment;
- locked SDK evidence where applicable; and
- repository governance for traceability and reassessment.

It does not depend on:

- Instrument;
- Observation;
- Validation;
- Risk;
- Execution;
- Portfolio;
- the business pipeline;
- Dataset Permission;
- Acquisition Authority; or
- Runtime Authority.

This architecture creates no new business-domain dependency.

# 24. Explicit Exclusions

This architecture excludes:

- Provider Capability Assessment;
- capability reassessment;
- Provider implementation disposition;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Service Availability;
- Provider Operational Availability assessment;
- Instrument acquisition;
- Instrument interpretation;
- Provider-to-Instrument mapping;
- historical acquisition;
- current-quote acquisition;
- live streaming;
- Observation processing;
- Market interpretation;
- Validation;
- Risk;
- Execution;
- orders;
- positions;
- holdings;
- funds;
- margins;
- GTT;
- mutual funds;
- account administration;
- demat-consent interpretation;
- personal-identity governance;
- retries;
- scheduling;
- caching;
- batching;
- persistence;
- APIs;
- payloads;
- schemas;
- SDK selection changes;
- deployment;
- GUI design;
- EDD-003 engineering design; and
- implementation.

# 25. GUI Readiness

A future Administration Console may consume read-only, provider-neutral Provider entitlement information consisting of:

- Provider identity;
- protected account-context reference;
- Provider Entitlement Identifier;
- sanitized Provider-scoped entitlement value;
- Entitlement Indeterminate indication where applicable;
- assessment outcome;
- assessment time;
- currentness;
- supersession indication;
- non-sensitive failure cause; and
- non-sensitive provenance reference.

The Administration Console shall not represent Provider-Reported Entitlement as:

- Provider Capability;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Service Availability;
- Provider Operational Availability;
- trading permission;
- order permission;
- business readiness;
- implementation authority; or
- permission to initiate an operation.

This section is non-authoritative for GUI design.

It defines no:

- screen;
- workflow;
- interaction;
- API;
- payload;
- access-control mechanism; or
- implementation.

# 26. Consequences for EDD-003

EDD-003 may be authorized for drafting only after ADR-008 is approved and canonical and separate Chief Architect Draft Authorization is issued.

If separately authorized, EDD-003 may translate this architecture into implementation-neutral engineering design for:

- Entitlement Assessment Request Processing;
- Entitlement Assessment Activity;
- Provider Entitlement Identifiers;
- Authenticated Profile Evidence;
- evidence classification;
- Provider-Reported Entitlement;
- Entitlement Indeterminate;
- assessment outcomes;
- record cardinality;
- currentness;
- reassessment;
- supersession;
- provenance;
- context reuse;
- Provider-internal composition;
- security verification; and
- deterministic verification requirements.

EDD-003 shall not:

- reopen Provider Capability Assessment;
- alter ADR-007;
- alter EDD-001;
- alter EDD-002;
- establish Dataset Permission;
- establish Acquisition Authority;
- establish Runtime Authority;
- define execution behavior;
- authorize profile endpoint invocation;
- implement entitlement assessment; or
- authorize EDD-004.

Canonicalization of ADR-008 shall not itself authorize EDD-003 drafting or implementation.

# 27. Relationship to Existing Authority

## 27.1 Platform Constitution

This architecture preserves:

- stable Provider domain identity;
- single semantic ownership;
- contract-based dependencies;
- separation of Platform support from Business Meaning; and
- the architecture-freeze rule requiring a new ADR for this bounded responsibility.

## 27.2 Domain Ownership Matrix

Provider Entitlement Assessment is assigned to Provider as a bounded Provider Integration responsibility.

This assignment does not alter any existing business-domain ownership.

## 27.3 Domain Dependency Matrix

Provider Entitlement Assessment introduces no dependency on the business pipeline.

Any future consumer requires an approved published contract and separate dependency authority where applicable.

## 27.4 ADR-007

ADR-007 remains authoritative for Provider Capability Assessment.

ADR-008 does not modify:

- Capability Identifiers;
- Provider-support determinations;
- KRONOS implementation dispositions;
- capability evidence;
- capability currentness; or
- capability supersession.

Profile fields excluded by ADR-007 are consumed only within the separately governed entitlement boundary established by ADR-008.

## 27.5 EDD-001

EDD-001 remains authoritative for Provider access, Authentication Activity, Authentication Outcome, Authenticated Provider Context, Context Validity, Context Invalidation, Context Termination, Provider Availability, and Provider Usability.

ADR-008 may consume only the approved provider-neutral context meanings.

It shall not expose or enlarge EDD-001 adapter internals.

## 27.6 EDD-002

EDD-002 remains authoritative for Provider Capability Assessment engineering design.

ADR-008 shall not change its contracts, identifiers, evidence, lifecycle, or implementation disposition.

# 28. Resolved Architecture Decisions

The following decisions are established by this architecture:

1. Provider owns Provider Entitlement Assessment.
2. Provider Entitlement Assessment is Account-scoped.
3. Provider Capability is Provider-scoped.
4. Dataset Permission is Platform-scoped.
5. Acquisition Authority is Operation-scoped.
6. Authentication, Capability, and Entitlement are independent.
7. One typed Provider Entitlement Identifier family is used.
8. The initial categories are Exchange Entitlement, Product Entitlement, and Order-Type Entitlement.
9. Authenticated Profile Evidence is the initial account-specific evidence source.
10. Provider-Reported Entitlement uses positive evidence only.
11. Missing values shall not establish entitlement denial unless the Provider contract explicitly assigns that meaning.
12. Unrecognized Provider Vocabulary results in Entitlement Indeterminate.
13. Unrecognized Provider Vocabulary is not an entitlement determination.
14. Request processing occurs before the assessment boundary.
15. Assessment Not Performed creates no record.
16. Every activity that begins creates exactly one record and one outcome.
17. Reassessment creates a new record.
18. Supersession is non-destructive.
19. Historical evidence survives context termination.
20. Historical evidence does not remain current merely because it is preserved.
21. No raw profile or SDK representation crosses the Provider boundary.
22. Provider-Reported Entitlement grants no operational or Business Meaning.
23. ADR-008 creates no business-domain dependency.

# 29. Architectural Invariants

1. Provider shall remain the sole owner of Provider Entitlement Assessment.
2. Provider Entitlement Assessment shall apply to one Provider and one authenticated account context.
3. Provider Capability shall remain Provider-scoped.
4. Provider-Reported Entitlement shall remain Account-scoped.
5. Dataset Permission shall remain Platform-scoped.
6. Acquisition Authority shall remain Operation-scoped.
7. A valid Authenticated Provider Context shall be required.
8. Context Reuse Eligibility shall be explicit and operation-specific.
9. Authentication Success shall not establish Provider-Reported Entitlement.
10. Provider Capability shall not establish Provider-Reported Entitlement.
11. Provider-Reported Entitlement shall not establish Provider Capability.
12. Provider-Reported Entitlement shall not establish Dataset Permission.
13. Provider-Reported Entitlement shall not establish Acquisition Authority.
14. Provider-Reported Entitlement shall not establish Runtime Authority.
15. Provider-Reported Entitlement shall not establish Service Availability.
16. Provider-Reported Entitlement shall not establish Provider Operational Availability.
17. Provider-Reported Entitlement shall not establish Execution permission.
18. Provider-Reported Entitlement shall not create Business Meaning.
19. Exactly one typed Provider Entitlement Identifier family shall govern the initial assessment.
20. Exchange, Product, and Order-Type Entitlement categories shall remain distinct.
21. Provider-specific values shall not silently become canonical cross-domain vocabulary.
22. Only explicitly reported evidence shall establish Provider-Reported Entitlement.
23. Missing values shall not establish entitlement denial unless the Provider contract explicitly assigns that meaning.
24. Unrecognized Provider Vocabulary shall result in Entitlement Indeterminate.
25. Unrecognized Provider Vocabulary shall not be an independent entitlement determination.
26. Assessment Not Performed shall occur before the assessment boundary.
27. Assessment Not Performed shall create no Provider Entitlement Assessment Record.
28. Every Entitlement Assessment Activity that begins shall produce exactly one outcome.
29. Every Entitlement Assessment Activity that begins shall produce exactly one record.
30. Assessment failure shall produce a safe record and Entitlement Indeterminate.
31. Assessment failure shall not retroactively alter an earlier valid record.
32. Reassessment shall be governed.
33. Reassessment shall produce a new record.
34. Supersession shall be non-destructive.
35. Context Invalidation shall end current operational reliance.
36. Context Termination shall end current operational reliance.
37. Context Invalidation or Termination shall not erase historical evidence.
38. Raw profile payloads shall not cross the Provider boundary.
39. SDK types, responses, clients, and exceptions shall not cross provider-neutral contracts.
40. Authentication material shall not enter entitlement evidence.
41. Personal identity shall not enter Provider Entitlement Assessment Records.
42. Audit shall not acquire Provider entitlement ownership.
43. GUI projection shall remain read-only and non-authoritative.
44. ADR-008 approval shall not authorize EDD-003 or implementation.

# 30. Architecture Review Criteria

Chief Architect review shall verify:

- the architectural question remains singular and bounded;
- Provider ownership is explicit;
- the Entitlement Scope Principle is preserved;
- the Positive Evidence Principle is preserved;
- the Provider domain remains outside the business pipeline;
- ADR-007 capability authority remains unchanged;
- EDD-001 context authority remains unchanged;
- EDD-002 engineering authority remains unchanged;
- Provider Entitlement Identifier categories are provider-neutral;
- Provider-Reported Entitlement uses positive evidence only;
- missing values do not become entitlement denial without an explicit Provider contract;
- Unrecognized Provider Vocabulary results only in Entitlement Indeterminate;
- Context Reuse Eligibility remains explicit;
- currentness and supersession are non-destructive;
- historical evidence survives termination without remaining operationally current;
- no SDK or raw Provider representation crosses the boundary;
- personal identity and authentication material are excluded;
- Dataset Permission remains separate;
- Acquisition Authority remains separate;
- Runtime Authority remains separate;
- Execution permission remains separate;
- Business Meaning remains separate;
- GUI readiness remains non-authoritative;
- no engineering design is introduced;
- no implementation is introduced; and
- no EDD drafting or implementation authority is created.

# 31. Unresolved Architecture Decisions

No unresolved architecture decision is identified in this architecture.

# 32. Architecture Risks

| Risk | Architectural control |
|---|---|
| Authentication interpreted as entitlement | Authentication and Provider-Reported Entitlement remain independent determinations. |
| Capability interpreted as account entitlement | ADR-007 and ADR-008 maintain separate assessment boundaries and scopes. |
| Missing profile value interpreted as denial | The Positive Evidence Principle prohibits missing-value-as-denial without explicit Provider contract meaning. |
| Provider vocabulary leaks into business domains | Provider-scoped values remain inside a provider-neutral Provider contract. |
| Product or order-type entitlement becomes Execution permission | Explicit non-implications preserve Execution ownership. |
| Exchange entitlement becomes Market or Instrument meaning | Entitlement categories remain descriptive Provider evidence only. |
| Stale entitlement remains operationally relied upon | Currentness and context lifecycle rules end current reliance. |
| Reassessment destroys history | Supersession is non-destructive. |
| Personal information leaks into records or GUI | Deny-by-default minimization excludes personal identity. |
| SDK mechanics become architecture | SDK evidence remains subordinate and adapter-private. |
| Provider failure becomes entitlement denial | Failure produces Entitlement Indeterminate. |
| GUI presentation becomes operational authority | GUI readiness is read-only and non-authoritative. |

# 33. ADR Determination

**ADR Required:** Yes

This document is the required Architecture Decision Record assigning and bounding Provider Entitlement Assessment within the frozen Platform Architecture.

Approval of this ADR establishes architecture only.

It does not authorize:

- EDD-003 drafting;
- implementation;
- profile endpoint invocation;
- runtime activity;
- dependency changes;
- acquisition;
- Execution; or
- EDD-004.

# 34. Review History

| Version | Review stage | Result |
|---|---|---|
| 0.1 | Initial architecture drafting from approved ADR-008 discovery | Draft prepared for Chief Architect review |
| 0.1 | Controlled architectural amendment | Entitlement Scope Principle and Positive Evidence Principle added |
| 1.0 | Chief Architect approval and canonicalization | Approved Canonical Architecture |

# 35. Approval Record

**Chief Architect Decision:** Approved
**Architecture Verification:** Complete
**Canonical Status:** Approved Canonical Architecture
**ADR Required:** Yes
**EDD-003 Drafting Authorization:** None
**Implementation Authorization:** None
**Runtime Authority:** None
**Commit Authorization:** None
**Push Authorization:** None
**Next Authorized Capability:** None

# 36. Governance Statement

This Version 1.0 document is approved canonical architecture.

It authorizes no:

- Engineering Design Document;
- implementation;
- dependency change;
- Provider operation;
- endpoint invocation;
- runtime activity;
- Dataset Permission;
- Acquisition Authority;
- Runtime Authority;
- Execution activity;
- business activity; or
- repository publication beyond this authorized canonical publication candidate.

Repository commit and push require separate authorization.

---

# End of Document
