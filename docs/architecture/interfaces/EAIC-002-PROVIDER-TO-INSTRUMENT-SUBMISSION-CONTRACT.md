# EAIC-002 — Provider → Instrument Submission Contract

**Document ID:** EAIC-002
**Title:** Provider → Instrument Submission Contract
**Version:** 0.1
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Interface Contract
**Owner:** Chief Architect
**Prepared By:** Codex Engineering Team
**Review Authority:** Chief Architect
**Repository Location:** `docs/architecture/interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md`
**Workflow Stage:** Repository Publication
**Governing Architecture:** ADR-009 Version 1.0
**Governing Migration:** MIG-001 Version 0.1
**Activation State:** Inactive — Pending Coordinated Migration and Separate Activation Authorization
**Migration Execution Authority:** None
**Implementation Authority:** None
**Runtime Authority:** None
**Provider Endpoint Invocation Authority:** None
**Persistence Authority:** None
**Provider-to-Instrument Submission Authority:** None
**EDD-004 Drafting Authority:** None
**Commit Authority:** None
**Push Authority:** None

---

# 1. Purpose and Scope

## 1.1 Classification and Identifier Preflight

DOC-001 defines `EAIC` as the governed Architecture Interface Contract family and `Interface Contract` as an approved classification.

`PIC` is not a governed repository document family.

The MIG-001 planning label `PIC-001` is therefore represented by the governed identifier `EAIC-002`.

This identity:

- uses the next available `EAIC` sequence after EAIC-001;
- creates no new document family;
- preserves MIG-001 traceability;
- does not create or authorize a separate PIC-001 document; and
- is aligned in MIG-001 as historical pre-classification planning traceability only.

## 1.2 Architectural Purpose

This contract defines the governed architectural submission boundary through which Provider may present a Submission Eligible unit of Provider-owned Instrument Master information to Instrument for possible product-neutral interpretation.

The contract preserves Provider meaning while preventing Provider from:

- creating Instrument meaning;
- assigning canonical identity;
- establishing Provider mapping;
- modifying the Canonical Instrument Catalogue;
- establishing product eligibility; or
- writing directly into Instrument-owned state.

## 1.3 Governed Boundary

The boundary begins when a separately authorized Provider presents one deterministically bounded, `SUBMISSION_ELIGIBLE` Submission Unit that conforms to this contract.

The boundary ends with:

- technical receipt meaning;
- contract validation meaning;
- interpretation-admission meaning; and
- the logical response record defined by this contract.

The contract does not perform Instrument interpretation.

## 1.4 Dataset Scope

Version 0.1 applies only to the Instrument Master dataset governed by ADR-009.

It excludes:

- Futures OI;
- Options OI;
- quotes;
- historical data;
- streaming;
- market depth;
- option-chain data;
- account data;
- profile data;
- Observations; and
- every separately governed Provider dataset.

Each excluded dataset requires its own Provider capability, Dataset Permission, Acquisition Authority, engineering design, endpoint invocation authority, runtime authority, and separately governed contract where applicable.

## 1.5 Product Neutrality

This contract is independent of:

- Swing membership;
- Intraday membership;
- any current product universe;
- current product implementation;
- strategy;
- trading venue preference; and
- product demand.

No product may filter Provider acquisition or submission content through this contract.

Provider neutrality requires strict isolation between Provider-and-Dataset Catalogue Partitions. Kite and any future IBKR integration shall retain separate Provider identities, records, snapshots, dispositions, provenance, Submission Units, and envelopes. Neither Provider's vocabulary, identifiers, evidence, or limitations may be used to complete, reinterpret, or overwrite the other's submission.

## 1.6 Architectural Pipeline

```text
Authorized Provider Dataset
        ↓
Provider Acquisition
        ↓
Provider Catalogue Partition
        ↓
Provider Disposition
        ↓
Submission Eligibility
        ↓
Provider → Instrument Submission Contract
        ↓
Instrument Interpretation
        ↓
Canonical Identity Decision
        ↓
Provider Mapping Decision
        ↓
Canonical Instrument Catalogue
        ↓
Explicit Product Consumption
```

The pipeline represents architectural sequencing only.

It grants no migration execution, implementation, submission, interpretation, or runtime authority.

# 2. Ownership Boundary

## 2.1 Provider Ownership

Provider exclusively owns:

- acquisition;
- Approved, Requested, and Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider Catalogue;
- Provider-and-Dataset Catalogue Partitions;
- Provider Snapshots;
- Provider Records;
- Provider Record identities;
- Provider dispositions;
- evidence-quality flags;
- quarantine disposition;
- interpretation-support disposition;
- Submission Eligibility;
- Provider limitations;
- Provider provenance; and
- acquisition provenance.

Provider retains that ownership while Instrument receives and evaluates a conforming Submission Unit.

## 2.2 Instrument Ownership

Instrument exclusively owns:

- interpretation-admission meaning after contract validation;
- Instrument interpretation;
- interpretation processing status;
- interpretation outcome;
- canonical identity decision;
- canonical classification;
- Provider mapping decision;
- Provider mapping status;
- cross-Provider reconciliation;
- canonical relationship meaning;
- Instrument lifecycle meaning; and
- Canonical Instrument Catalogue publication.

## 2.3 No Ownership Transfer

Contract receipt shall not:

- make Provider information Instrument-owned;
- make Provider assertions canonical;
- make Instrument responsible for Provider record correction;
- make Provider responsible for Instrument interpretation;
- create shared semantic ownership; or
- transfer Audit ownership of recorded facts.

## 2.4 Product Boundary

Swing, Intraday, and future products shall not consume:

- Provider Catalogue records;
- Provider Snapshots;
- Submission Units;
- submission envelopes; or
- contract response records

as substitutes for canonical Instrument identity.

Products may consume only separately approved canonical Instrument and product-consumption contracts.

# 3. Submission Authority

## 3.1 Required Authority

A Submission Unit may cross this boundary only when all of the following are established:

1. this contract is approved, canonical, and activated through the completed MIG-001 coordinated migration;
2. a separate Provider-to-Instrument Submission Authority exists for the exact Provider, dataset, partition, snapshot, Submission Unit, environment, and governed operation;
3. the Provider Context reference is valid and eligible for the applicable bounded use;
4. Dataset Permission exists for Instrument Master;
5. applicable Provider capability evidence is current;
6. applicable Provider entitlement evidence is current where required;
7. the source acquisition was separately authorized;
8. the Provider Snapshot is closed and immutable;
9. the Submission Unit has exactly one `SUBMISSION_ELIGIBLE` disposition;
10. every precondition in Section 6 is established; and
11. no governance or security prohibition applies.

Failure to establish any requirement produces no submission authority.

## 3.2 Authority Separation

Submission Eligibility is a Provider-owned boundary determination.

It does not grant:

- Provider-to-Instrument Submission Authority;
- runtime authority;
- endpoint invocation authority;
- acquisition authority;
- persistence authority;
- Instrument acceptance;
- Instrument interpretation authority;
- canonical identity;
- Provider mapping;
- product eligibility;
- trading eligibility; or
- implementation authority.

No authority in this section implies another.

# 4. Submission Unit

## 4.1 Permitted Granularity

A Submission Unit shall contain exactly one of:

1. one Provider Record; or
2. one explicitly bounded multi-record set required to preserve a duplicate, ambiguity, or internal-inconsistency relationship that would be materially lost by separate submission.

No other multi-record granularity is permitted by Version 0.1.

## 4.2 Multi-Record Unit Rules

A multi-record Submission Unit is permitted only when:

- every member belongs to the same Provider;
- every member belongs to the same dataset;
- every member belongs to the same Provider Catalogue Partition;
- every member belongs to the same Provider Snapshot;
- the bounded relationship is explicit;
- membership is complete for that bounded relationship;
- membership is immutable;
- the reason for grouping is preserved;
- no member is silently preferred, repaired, merged, or discarded; and
- all applicable Submission Eligibility conditions are evaluated for the bounded unit.

## 4.3 Submission Unit Identity

Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition.

Provider Record Identity is unique only within one Provider Snapshot.

Provider tokens, exchange tokens, symbols, and row positions shall not, alone or by implication, establish globally permanent Provider Record Identity.

These identity rules apply independently from Submission Unit identity.

Submission Unit identity shall not broaden, replace, globalize, or override:

- Provider-and-Dataset Catalogue Partition identity;
- Provider Snapshot Identity;
- Provider Record Identity.

No implementation may infer cross-partition or cross-snapshot permanence from Provider-native identifiers or Submission Unit identity.

No implementation may infer canonical Instrument identity from:

- Provider-native identifiers;
- Provider tokens;
- exchange tokens;
- symbols;
- row positions;
- Provider Record Identity;
- Provider Snapshot Identity;
- Submission Unit identity.

No implementation may infer cross-Provider identity equivalence from:

- Provider-native identifiers;
- Provider Record Identity;
- Provider Snapshot Identity;
- Submission Unit identity.

Submission Unit identity shall be unique within one Provider Catalogue Partition and Provider Snapshot.

It shall be attributable to:

- contract version;
- Provider identity;
- dataset identity;
- partition identity;
- snapshot identity;
- fixed Provider Record membership; and
- one immutable unit identity component.

A Provider token, exchange token, symbol, row position, or canonical Instrument identity shall not alone become Submission Unit identity.

## 4.4 Atomicity Boundary

Contract validation and interpretation admission apply atomically to the complete Submission Unit.

The receiver shall not:

- admit only selected members;
- split the unit silently;
- replace a member;
- repair a member;
- merge the unit with another unit; or
- infer a different unit boundary.

A rejected unit may be represented later only under a new Submission Unit identity after the Provider establishes a new, independently eligible unit.

## 4.5 Prohibited Mixing

A Submission Unit shall never mix:

- Providers;
- datasets;
- Provider Catalogue Partitions;
- Provider Snapshots;
- operational environments;
- Provider Context classes where materially distinct;
- security classifications that cannot coexist safely; or
- unrelated record relationships.

# 5. Submission Envelope

## 5.1 Required Logical Contents

Every submission envelope shall contain or preserve an approved immutable reference to:

- contract identifier and version;
- Provider identity;
- Provider Context reference;
- dataset identity;
- Provider Catalogue Partition identity;
- Provider Snapshot identity;
- Submission Unit identity;
- Provider Record identities and fixed membership;
- preservation fact `ACQUIRED`;
- structural disposition;
- evidence-quality flags;
- quarantine disposition;
- interpretation-support disposition;
- submission disposition;
- Submission Eligibility evidence;
- eligibility determination time;
- eligibility authority basis;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider provenance;
- acquisition provenance;
- timing provenance;
- Provider API basis;
- SDK name and version basis where applicable;
- adapter identity and adapter revision basis;
- Provider limitations;
- licensing and retention limitations;
- missingness;
- ambiguity;
- duplicate evidence;
- inconsistency evidence;
- security classification reference;
- Configuration context reference;
- applicable authority references; and
- an approved safe content representation or immutable content reference.

## 5.2 Content Representation

The content representation shall preserve Provider assertions without:

- converting them into Instrument meaning;
- interpreting Provider vocabulary;
- normalizing to canonical identity;
- selecting one ambiguous meaning;
- selecting one duplicate;
- silently correcting inconsistency; or
- writing into Instrument-owned state.

## 5.3 Prohibited Envelope Content

An envelope shall not contain:

- credentials;
- access tokens;
- request tokens;
- API secrets;
- authorization headers;
- raw URLs containing secrets;
- raw Provider payloads;
- SDK clients;
- SDK response objects;
- SDK exceptions;
- private transport state;
- unredacted failures;
- personal account identity;
- canonical Instrument meaning created by Provider;
- product eligibility; or
- business judgment.

## 5.4 Provider Disposition Conformance

### 5.4.1 Required Dimensions

Every preserved Provider Record in a Submission Unit shall have:

- exactly one preservation fact: `ACQUIRED`;
- exactly one structural disposition: `STRUCTURALLY_VALID` or `STRUCTURALLY_INVALID`;
- zero or more evidence-quality flags: `AMBIGUOUS`, `DUPLICATE`, `INTERNALLY_INCONSISTENT`, `MISSING_REQUIRED_PROVIDER_ASSERTION`, `UNRECOGNIZED_PROVIDER_VOCABULARY`, or `PROVIDER_LIMITATION_PRESENT`;
- exactly one quarantine disposition: `NOT_QUARANTINED` or `QUARANTINED`;
- exactly one interpretation-support disposition: `INTERPRETATION_SUPPORT_ESTABLISHED`, `INTERPRETATION_SUPPORT_LIMITED`, or `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`; and
- exactly one submission disposition after evaluation: `SUBMISSION_ELIGIBLE` or `SUBMISSION_INELIGIBLE`.

### 5.4.2 Structural and Quarantine Precedence

`STRUCTURALLY_INVALID` requires:

- `QUARANTINED`;
- `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`; and
- `SUBMISSION_INELIGIBLE`.

`QUARANTINED` always requires `SUBMISSION_INELIGIBLE`.

Neither disposition may cross this contract as a Submission Eligible unit.

### 5.4.3 Evidence-Quality Treatment

| Evidence condition | Contract requirement |
|---|---|
| `INTERNALLY_INCONSISTENT` | Reject unless an approved deterministic Provider rule has established non-materiality, preserved the inconsistency, and every Section 6 condition remains satisfied. |
| `DUPLICATE` | Preserve complete duplicate membership; permit only through an explicitly bounded multi-record unit or independently safe record unit without silent selection. |
| `AMBIGUOUS` | Preserve ambiguity; permit only when Instrument can evaluate the bounded ambiguity without Provider selecting a canonical meaning. |
| `UNRECOGNIZED_PROVIDER_VOCABULARY` | Preserve the vocabulary and at least `INTERPRETATION_SUPPORT_LIMITED`; require every Section 6 condition. |
| `MISSING_REQUIRED_PROVIDER_ASSERTION` | Reject when the missing assertion is mandatory for this contract. |
| `PROVIDER_LIMITATION_PRESENT` | Preserve the limitation and evaluate every Section 6 condition independently. |

Absence of a flag shall not imply correctness, completeness, support, or canonical meaning.

# 6. Preconditions

## 6.1 Submission Eligibility Minimum

Before a Submission Unit may cross the boundary, Provider shall establish independently that:

1. Provider identity is established.
2. Dataset identity is established as Instrument Master.
3. Provider Snapshot identity is established.
4. Every Provider Record identity is established within the Provider-and-dataset partition.
5. Structural disposition is `STRUCTURALLY_VALID`.
6. Quarantine disposition is `NOT_QUARANTINED`.
7. Required non-sensitive provenance is present.
8. Provider source, operation, acquisition context, and snapshot context are attributable.
9. Required Provider assertions for this contract are present.
10. Sensitive and transport-private information has been excluded.
11. Raw SDK and payload objects do not cross the boundary.
12. Duplicate status has been deterministically preserved and treated under Section 5.4.
13. Internal inconsistency does not remain unresolved in a way that makes the unit unsafe.
14. Ambiguity is absent or explicitly preserved and permitted for Instrument evaluation.
15. Provider limitations and missingness are explicit.
16. Submission requires no Provider inference of canonical Instrument meaning.
17. No architecture or authority condition prohibits submission.

## 6.2 Contract Preconditions

The following additional contract preconditions are mandatory:

- the envelope conforms to the active contract version;
- Provider-to-Instrument Submission Authority is established separately;
- partition and snapshot identities resolve without collision;
- Submission Unit identity is unique and immutable;
- unit membership is complete and fixed;
- the Provider Snapshot is closed;
- all referenced evidence remains available under approved retention authority;
- security classification permits the bounded crossing;
- the submission is not prohibited as stale under Section 10;
- the content representation is safe and non-sensitive; and
- the submission does not depend on product membership.

## 6.3 Deterministic Failure

If any mandatory precondition is absent, invalid, inconsistent, prohibited, or cannot be established, the unit shall be:

- `SUBMISSION_INELIGIBLE` where the failure remains within Provider eligibility determination; or
- rejected before interpretation admission where a purported submission reaches contract validation without satisfying this contract.

No missing precondition may be treated as implicitly satisfied.

# 7. Contract Receipt

## 7.1 Independent Meanings

The boundary shall preserve the following independent stages:

1. technical receipt;
2. contract validation;
3. interpretation admission;
4. interpretation processing;
5. interpretation outcome;
6. canonical identity decision; and
7. Provider mapping status.

No stage implies completion or success of a later stage.

## 7.2 Technical Receipt

Technical receipt means only that the submitted representation reached the governed boundary sufficiently to identify or classify the attempted submission.

Technical receipt does not imply:

- valid contract;
- valid authority;
- safe content;
- interpretation admission;
- Instrument acceptance;
- canonical identity; or
- mapping.

## 7.3 Contract Validation

Contract validation determines whether:

- the active version is supported;
- the envelope is structurally valid;
- authority is established;
- identities and boundaries are consistent;
- required provenance exists;
- content is safe;
- replay and ordering rules are satisfied; and
- every precondition is established.

Contract validation performs no Instrument interpretation.

## 7.4 Interpretation Admission

Exactly one interpretation-admission result shall follow completed contract validation:

- `ACCEPTED_FOR_INTERPRETATION`; or
- `REJECTED_BEFORE_INTERPRETATION`.

`ACCEPTED_FOR_INTERPRETATION` permits only separately authorized Instrument interpretation to begin.

It does not imply interpretation has begun or succeeded.

# 8. Validation and Rejection

## 8.1 Validation and Delivery Classifications

| Classification | Deterministic contract meaning | Boundary result |
|---|---|---|
| `INVALID_CONTRACT_VERSION` | The stated contract version is absent, malformed, inactive, or unsupported. | Rejection |
| `INVALID_ENVELOPE` | Required envelope structure or logical content is absent or invalid. | Rejection |
| `UNSUPPORTED_DATASET` | Dataset identity is not Instrument Master. | Rejection |
| `SUBMISSION_AUTHORITY_NOT_ESTABLISHED` | Exact Provider-to-Instrument Submission Authority is absent or invalid. | Rejection |
| `PROVENANCE_NOT_ESTABLISHED` | Required non-sensitive provenance is absent, invalid, or unattributable. | Rejection |
| `PARTITION_VIOLATION` | Content or identity crosses or conflicts with a Provider-and-Dataset Catalogue Partition. | Rejection |
| `SNAPSHOT_VIOLATION` | Snapshot identity, closure, membership, or lineage is invalid or mixed. | Rejection |
| `SUBMISSION_IDENTITY_COLLISION` | One submission identity refers to conflicting content or membership. | Rejection |
| `MIXED_PROVIDER_SUBMISSION` | More than one Provider appears in the unit or envelope. | Rejection |
| `MIXED_DATASET_SUBMISSION` | More than one dataset appears in the unit or envelope. | Rejection |
| `SUBMISSION_INELIGIBLE` | A record or unit lacks the required eligible submission disposition. | Rejection |
| `ELIGIBILITY_EVIDENCE_INCOMPLETE` | Eligibility evidence is absent, incomplete, or inconsistent with the claimed disposition. | Rejection |
| `UNSAFE_CONTENT` | Sensitive, transport-private, raw, prohibited, or otherwise unsafe content is present. | Rejection |
| `EXACT_DUPLICATE_DELIVERY` | The same immutable submission was already received and resolved. | No new admission; associate the previously established outcome |
| `CONFLICTING_DUPLICATE_DELIVERY` | The same identity is presented with different content, membership, or evidence. | Rejection |
| `REPLAY_NOT_PERMITTED` | A replay is outside the safe retry rules in Section 9. | Rejection |
| `OUT_OF_ORDER_DELIVERY` | The unit violates the applicable partition and snapshot ordering rules. | Rejection |
| `INTERNAL_INCONSISTENCY_UNSAFE` | Internal inconsistency remains materially unresolved for safe submission. | Rejection |

## 8.2 Rejection Evidence

Rejection shall preserve:

- Submission Unit identity where safely established;
- Provider, dataset, partition, and snapshot identity where trusted;
- receipt and validation times;
- rejection reason;
- non-sensitive evidence;
- relevant provenance;
- applicable evidence-quality flags;
- authority evidence status; and
- no Instrument meaning.

Untrusted identity or provenance shall not be promoted as verified evidence.

## 8.3 Ownership After Rejection

Rejection:

- does not transfer Provider record ownership;
- does not establish Instrument invalidity;
- does not alter the Provider Snapshot;
- does not create Instrument lifecycle meaning;
- does not create product exclusion; and
- does not authorize Provider mutation under the rejected submission identity.

# 9. Idempotency and Replay

## 9.1 Idempotency Identity

Idempotency identity shall be the immutable combination of:

- contract version;
- Provider identity;
- dataset identity;
- partition identity;
- snapshot identity;
- Submission Unit identity; and
- fixed record membership.

Idempotency identity is contract identity only.

It does not create canonical Instrument identity or mapping continuity.

## 9.2 Exact Duplicate Delivery

An exact duplicate has:

- the same idempotency identity;
- the same immutable envelope meaning;
- the same content reference or representation;
- the same membership;
- the same authority reference; and
- no conflicting provenance.

Exact duplicate delivery shall not create a second interpretation admission.

The contract shall return or associate the previously established receipt and validation outcome.

## 9.3 Conflicting Duplicate Delivery

Reuse of an existing idempotency identity with any changed content, membership, authority, partition, snapshot, disposition, or provenance is a conflicting duplicate.

It shall be rejected as `CONFLICTING_DUPLICATE_DELIVERY` or `SUBMISSION_IDENTITY_COLLISION`.

## 9.4 Safe Retry

A safe retry is permitted only after an indeterminate transport result and shall:

- reuse the exact idempotency identity;
- preserve identical immutable content and evidence;
- create no mutation;
- create no second admission; and
- resolve through exact duplicate recognition if the earlier attempt was received.

This contract defines no retry schedule, retry count, or transport mechanism.

## 9.5 Replay

A recognized replay shall preserve its relationship to the original submission.

Replay shall not:

- refresh eligibility silently;
- replace authority;
- alter currentness;
- create new canonical identity;
- trigger duplicate interpretation admission; or
- bypass stale-submission rules.

# 10. Ordering and Concurrency

## 10.1 Ordering Scope

No global order is required across Provider Catalogue Partitions.

Within one partition:

- snapshot lineage is authoritative;
- snapshot closure precedes submission;
- a Submission Unit is associated with exactly one snapshot;
- arrival order shall not override snapshot lineage; and
- Provider-supplied generation time shall not silently replace governed acquisition effective time.

## 10.2 Concurrent Submission Units

Submission Units from the same closed snapshot may be evaluated concurrently only when their memberships are disjoint or their bounded relationship is explicitly preserved.

Overlapping memberships shall undergo duplicate and conflict validation.

Concurrency shall not permit:

- silent selection;
- lost membership;
- duplicate admission;
- mutable envelope meaning; or
- arrival-order canonicalization.

## 10.3 Superseding Snapshots

A later current snapshot does not mutate or erase a previously submitted unit.

Snapshot supersession:

- remains Provider-owned;
- is non-destructive;
- does not establish Instrument lifecycle;
- does not retract established historical evidence automatically; and
- does not automatically change canonical identity or mapping.

## 10.4 Stale Submission

A unit from a snapshot already superseded as current Provider reference evidence shall be `REJECTED_BEFORE_INTERPRETATION` as `OUT_OF_ORDER_DELIVERY`.

Historical reconciliation or replay of a superseded snapshot requires a separately approved contract and authority outside Version 0.1.

## 10.5 Race Treatment

Race treatment shall use:

- partition identity;
- snapshot lineage;
- immutable snapshot closure;
- Submission Unit identity;
- fixed membership; and
- idempotency identity.

Arrival time alone shall not determine canonical precedence.

This section defines no queue, lock, transaction, scheduler, or concurrency technology.

# 11. Interpretation Handoff

## 11.1 Processing Status

Before admission, interpretation processing status is `NOT_STARTED`.

`ACCEPTED_FOR_INTERPRETATION` permits Instrument to begin separately authorized processing.

Processing becomes `PENDING` only when Instrument begins that processing under applicable authority.

Completed processing requires `COMPLETED`.

Contract receipt alone shall not cause `PENDING` or `COMPLETED`.

## 11.2 Interpretation Outcome

When processing is `COMPLETED`, exactly one mutually exclusive outcome shall exist:

- `INTERPRETED`;
- `UNINTERPRETED`;
- `AMBIGUOUS`; or
- `UNSUPPORTED`.

The contract does not select or predict the outcome.

## 11.3 Canonical Identity Decision

Exactly one canonical identity decision shall exist:

- `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED`; or
- `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

`CANONICAL_IDENTITY_ESTABLISHED` requires completed processing and `INTERPRETED`.

Completed identity evaluation after `UNINTERPRETED`, `AMBIGUOUS`, or `UNSUPPORTED` requires `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

## 11.4 Provider Mapping Status

Exactly one Provider mapping status shall exist:

- `NOT_EVALUATED`;
- `MAPPING_PENDING`;
- `MAPPED`;
- `NOT_MAPPED`;
- `MAPPING_AMBIGUOUS`; or
- `MAPPING_UNSUPPORTED`.

Mapping remains independent of canonical identity.

`MAPPED` requires a canonical identity target.

A canonical Instrument may exist without a current Provider mapping.

Provider mapping shall not create canonical identity.

## 11.5 No Lifecycle Creation

The four Instrument dimensions are not Instrument lifecycle states.

They shall not be collapsed into:

- one status;
- one success flag;
- Provider disposition;
- product eligibility; or
- Instrument lifecycle.

# 12. Response Contract

## 12.1 Logical Response Record

The logical response record shall preserve:

- contract identifier and version;
- Submission Unit identity;
- trusted Provider, dataset, partition, and snapshot references;
- technical receipt outcome;
- contract validation outcome;
- interpretation-admission result;
- processing reference where separately established;
- rejection reasons where applicable;
- idempotency or replay relationship;
- response time;
- non-sensitive evidence references; and
- explicit non-implications.

## 12.2 Receipt Outcomes

Exactly one receipt outcome shall exist:

- `RECEIPT_ESTABLISHED`; or
- `RECEIPT_NOT_ESTABLISHED`.

`RECEIPT_NOT_ESTABLISHED` means that sufficient technical receipt evidence does not exist.

It does not mean the submission was rejected semantically.

## 12.3 Validation Outcomes

Exactly one validation outcome shall exist when receipt is established:

- `CONTRACT_VALID`; or
- `CONTRACT_INVALID`.

`CONTRACT_VALID` is required before `ACCEPTED_FOR_INTERPRETATION`.

## 12.4 Asynchronous Separation

The response contract shall not require synchronous:

- Instrument interpretation;
- canonical identity decision;
- Provider mapping decision;
- Canonical Instrument Catalogue publication; or
- product consumption.

A processing reference may associate later Instrument-owned evidence without transferring ownership or changing the earlier receipt and validation result.

# 13. Error Semantics

| Error class | Owner and boundary meaning | Required separation |
|---|---|---|
| Transport failure | Boundary-operation evidence that reliable technical receipt was not established | Does not establish contract invalidity or rejection |
| Contract failure | Contract validation could not establish conformance | Does not become Instrument interpretation failure |
| Authority failure | Required submission authority was absent, invalid, or out of scope | Does not become Submission Eligibility or Provider capability failure |
| Validation failure | One or more envelope, identity, provenance, safety, ordering, or replay rules failed | Does not establish Instrument invalidity |
| Interpretation failure | Instrument-owned processing failure after admission | Does not retroactively alter receipt, validation, or Provider meaning |
| Canonical identity deferral | Canonical identity decision remains `NOT_EVALUATED` under the applicable Instrument process | Does not imply contract or interpretation failure |
| Mapping deferral | Provider mapping status is `MAPPING_PENDING` or `NOT_EVALUATED` | Does not imply canonical identity absence |

No error class shall be collapsed into one generic success or failure flag.

Provider operational failure, Provider record quality, contract validity, Instrument interpretation, identity decision, and mapping decision remain independent.

# 14. Provenance

## 14.1 Required Provenance

The contract shall preserve, where applicable:

- Provider identity;
- Provider Context reference;
- dataset identity;
- Provider operation identity;
- Acquisition Authority reference;
- Provider-to-Instrument Submission Authority reference;
- Dataset Permission reference;
- capability assessment reference;
- entitlement assessment reference where applicable;
- Provider Catalogue Partition identity;
- Provider Snapshot identity;
- Submission Unit identity;
- Provider Record identities;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider API basis;
- SDK name and version basis where applicable;
- adapter identity;
- adapter revision basis;
- Configuration context reference;
- security classification reference;
- limitations;
- exclusions;
- evidence-quality flags;
- submission disposition;
- snapshot supersession relationship; and
- contract outcome evidence.

## 14.2 Time Meanings

| Time meaning | Architectural definition |
|---|---|
| Request Initiation Time | When the approved Provider acquisition operation was initiated. |
| Response Receipt Time | When the Provider response was fully received by the Provider adapter boundary. |
| Snapshot Closure Time | When the immutable Provider Snapshot was finalized. |
| Acquisition Effective Time | The governed time context to which the Provider Snapshot applies. |
| Submission Initiation Time | When the separately authorized submission attempt began. |
| Submission Receipt Time | When technical receipt was established at this contract boundary. |
| Contract Validation Time | When contract validation reached its recorded outcome. |
| Interpretation Admission Time | When `ACCEPTED_FOR_INTERPRETATION` or `REJECTED_BEFORE_INTERPRETATION` was established. |

No time meaning may silently substitute for another.

Provider-supplied generation or effective time shall remain a separate Provider assertion.

## 14.3 Engineering Provenance

Provider API, SDK, and adapter basis are engineering provenance.

They do not establish:

- Provider semantic correctness;
- Instrument meaning;
- canonical identity;
- mapping;
- product eligibility; or
- business meaning.

# 15. Security and Sensitive-Data Exclusions

The contract shall enforce:

- least exposure;
- adapter-private Provider transport;
- SDK isolation;
- security classification;
- redacted failure evidence;
- non-sensitive provenance; and
- no credential propagation.

The boundary explicitly prohibits:

- credentials;
- access tokens;
- request tokens;
- API secrets;
- authorization headers;
- raw URLs containing secrets;
- raw SDK clients;
- raw SDK response objects;
- SDK exceptions;
- raw Provider payloads;
- private transport state;
- unapproved sensitive payloads;
- personal account identity;
- reconstructable authentication material; and
- unredacted Provider failure content.

Unsafe content requires `REJECTED_BEFORE_INTERPRETATION`.

Security rejection shall preserve only safe evidence and shall not expose the prohibited content in responses, provenance, logs, or Audit evidence.

# 16. Versioning and Compatibility

## 16.1 Contract Version Identity

Every envelope and response shall identify the governed contract version.

Version identity is independent of:

- Provider API version;
- SDK version;
- adapter revision;
- Provider Snapshot identity; and
- canonical Instrument version.

## 16.2 Compatibility

Backward compatibility may be claimed only when a later contract version:

- preserves all existing ownership;
- preserves existing mandatory meaning;
- preserves identity and idempotency rules;
- preserves security exclusions;
- does not reinterpret earlier fields;
- does not weaken preconditions; and
- does not broaden dataset or authority scope.

## 16.3 Breaking Changes

A change is breaking when it changes:

- ownership;
- dataset scope;
- mandatory envelope meaning;
- identity scope;
- disposition meaning;
- eligibility minimum;
- validation outcome;
- ordering;
- security boundary;
- non-implication; or
- downstream architectural effect.

A breaking change requires:

- a new governed contract version;
- Chief Architect review;
- migration impact assessment;
- compatibility determination;
- coordinated migration where required; and
- explicit activation.

## 16.4 Unknown Content

Unknown content shall not establish eligibility, authority, Instrument meaning, or compatibility.

Unknown content may be ignored only when:

- the active compatible version explicitly permits bounded optional extension;
- the content is safe and non-sensitive;
- ignoring it does not change required meaning; and
- the treatment is preserved as non-sensitive evidence.

Otherwise the envelope is `CONTRACT_INVALID`.

## 16.5 Unsupported Version

An unsupported or unknown contract version requires:

- `INVALID_CONTRACT_VERSION`;
- `CONTRACT_INVALID`;
- `REJECTED_BEFORE_INTERPRETATION`; and
- no interpretation processing.

This contract selects no serialization, schema language, transport, or storage technology.

# 17. Auditability and Evidence

## 17.1 Reconstruction Minimum

Approved evidence shall permit reconstruction of:

- why submission was permitted;
- what Submission Unit was presented;
- which records were members;
- which Provider, dataset, partition, and snapshot applied;
- which contract version applied;
- which authority applied;
- which eligibility determination applied;
- which provenance and limitations applied;
- when acquisition, submission, receipt, validation, and admission occurred;
- how receipt concluded;
- how validation concluded;
- whether replay or duplication occurred;
- why rejection or admission occurred; and
- which later processing reference was associated where applicable.

## 17.2 Audit Ownership

Audit owns the Audit Trail.

Audit does not acquire ownership of:

- Provider records;
- Provider provenance;
- Submission Eligibility;
- Instrument interpretation;
- canonical identity;
- mapping; or
- contract outcomes recorded as facts.

## 17.3 Evidence Safety

Auditability shall never require preservation of prohibited sensitive or adapter-private material.

Safe evidence shall preserve reason and traceability without exposing secrets, raw payloads, SDK representations, or private transport state.

# 18. Non-Implications

This contract shall never create automatically:

- Instrument canonical identity;
- Provider mapping;
- Instrument lifecycle state;
- canonical classification;
- product-universe membership;
- Swing eligibility;
- Intraday eligibility;
- Observation authority;
- Observation acceptance;
- Market state;
- Validation authority;
- Business Judgment;
- Risk approval;
- execution authority;
- trading eligibility;
- trading recommendation;
- Portfolio meaning;
- Provider capability;
- Provider entitlement;
- Dataset Permission;
- Acquisition Authority;
- persistence authority;
- endpoint authority;
- runtime authority;
- implementation authority; or
- EDD-004 authority.

Technical receipt does not imply contract validity.

Contract validity does not imply interpretation admission unless every admission condition is satisfied.

Interpretation admission does not imply interpretation success.

Interpretation does not imply canonical identity establishment.

Canonical identity does not imply Provider mapping.

Provider mapping does not imply product eligibility.

# 19. Activation and Migration Constraints

This Version 0.1 approved canonical Interface Contract is inactive pending coordinated migration and separate activation authorization.

It shall not activate until:

1. the contract is approved through architecture governance;
2. the contract is canonical;
3. the contract is included in the MIG-001 coordinated migration;
4. Provider and Instrument Domain Architecture are aligned;
5. the Domain Ownership Matrix is aligned;
6. the Domain Dependency Matrix is aligned;
7. DATA_FLOW is aligned;
8. affected ADPs and EAPs are aligned;
9. repository-wide Architecture Verification returns PASS;
10. coordinated canonical publication is complete; and
11. the Chief Architect separately authorizes activation.

Canonical publication alone does not activate this contract.

Activation does not itself authorize:

- implementation;
- runtime submission;
- endpoint invocation;
- acquisition;
- persistence;
- Instrument interpretation execution; or
- EDD-004.

# 20. Conformance Requirements

## 20.1 Provider Conformance

Provider shall:

- preserve Provider ownership and meaning;
- use only the Instrument Master dataset;
- preserve Provider-and-Dataset partition isolation;
- preserve immutable snapshot and record identity;
- create deterministic Submission Units;
- preserve all disposition cardinalities;
- establish Submission Eligibility independently;
- preserve required provenance and time distinctions;
- exclude sensitive and adapter-private material;
- obtain separate submission authority;
- preserve duplicate, ambiguity, inconsistency, limitation, and missingness evidence;
- submit no quarantined or structurally invalid unit;
- infer no canonical Instrument meaning;
- apply idempotency, replay, and ordering rules; and
- never write directly to Instrument-owned state.

## 20.2 Instrument Conformance

Instrument shall:

- preserve Provider ownership and attribution;
- separate receipt, validation, admission, processing, outcome, identity, and mapping;
- validate the complete Submission Unit atomically;
- reject mixed Provider, dataset, partition, or snapshot content;
- preserve rejection evidence safely;
- perform no silent Provider repair, selection, or mutation;
- preserve the four independent Instrument dimensions;
- keep canonical identity independent from mapping;
- keep interpretation independent from product membership;
- create no Instrument lifecycle state from contract status;
- prevent direct product consumption of the envelope; and
- publish canonical meaning only through separately approved Instrument architecture.

## 20.3 Cross-Boundary Conformance

Both sides shall preserve:

- one contract version;
- one immutable Submission Unit identity;
- exact unit membership;
- deterministic outcomes;
- authority separation;
- non-sensitive traceability;
- idempotency;
- no hidden ownership transfer;
- no product-coupled acquisition; and
- no runtime or implementation authority from architecture alone.

# 21. Open Decisions

No unresolved architectural decision is identified within the Version 0.1 contract scope.

The following are intentionally deferred implementation or governance matters, not open architecture:

- serialization technology;
- transport technology;
- storage technology;
- queueing or concurrency mechanism;
- physical retry mechanism;
- physical persistence;
- runtime deployment;
- migration execution authorization;
- activation authorization;
- EDD-004 authorization; and
- implementation authorization.

The MIG-001 pre-classification planning label `PIC-001` has been aligned to the governed identifier EAIC-002. It remains historical traceability only and does not identify a separate governed document.

# 22. ADR-009 Correction Traceability

| ADR-009 correction | Contract conformance |
|---|---|
| AV-ADR009-001 — Provider disposition cardinality | Sections 5 and 6 preserve all six independent dimensions, exact cardinality, precedence, and evidence-quality coexistence. |
| AV-ADR009-002 — Submission Eligibility | Sections 3 and 6 preserve all deterministic eligibility conditions, exact disposition, authority separation, and ineligibility fallback. |
| AV-ADR009-003 — Instrument interpretation dimensions | Sections 7 and 11 separate receipt from processing status, interpretation outcome, canonical identity decision, and Provider mapping status. |
| AV-ADR009-004 — Provider Catalogue partitions | Sections 4, 5, 8, and 10 prohibit cross-Provider, cross-dataset, cross-partition, and cross-snapshot collision. |
| AV-ADR009-005 — Provenance | Sections 5, 14, and 17 preserve acquisition, submission, receipt, validation, admission, API, SDK, and adapter provenance without sensitive material. |

# 23. Related Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [DOC-001 — Document Identification, Classification & Metadata Standard](../../governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Provider Domain Architecture](../platform/domains/provider/ARCHITECTURE.md)
- [Instrument Domain Architecture](../platform/domains/instrument/ARCHITECTURE.md)
- [Domain Ownership Matrix](../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [DATA_FLOW](../DATA_FLOW.md)
- [ADP-001C — Provider → Instrument Contract](../products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001H — Provider Instrument Master Acquisition](../products/swing/SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001J — Instrument Interpretation and Canonical Identity](../products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md)
- [ADR-007 — Provider Capability Assessment Architecture](../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](../platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [EAP-001 — Authenticated Provider Context](../../engineering/eap/EAP-001-CONFIGURATION-TO-PROVIDER-AUTHENTICATED-CONTEXT.md)
- [EAP-002 — Provider Instrument Master Acquisition](../../engineering/eap/EAP-002-PROVIDER-INSTRUMENT-MASTER-ACQUISITION.md)
- [EAP-003 — Provider-to-Instrument Architectural Admissibility](../../engineering/eap/EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md)
- [EAP-004 — Instrument Interpretation and Canonical Identity](../../engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md)
- [EAP-005 — Instrument-to-Observation Attribution Eligibility](../../engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md)
- [EAP-006 — Observation Acceptance](../../engineering/eap/EAP-006-OBSERVATION-ACCEPTANCE-AND-GOVERNED-OBSERVATION-ESTABLISHMENT.md)
- [EDD-001 — Provider Access and Provider Context](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md)
- [EDD-002 — Provider Capability Assessment](../../engineering/edd/EDD-002-PROVIDER-CAPABILITY-ASSESSMENT-ENGINEERING-DESIGN.md)
- [EDD-003 — Provider Entitlement Assessment](../../engineering/edd/EDD-003-PROVIDER-ENTITLEMENT-ASSESSMENT-ENGINEERING-DESIGN.md)

# 24. Review History

| Version | Review stage | Result |
|---|---|---|
| 0.1 | Classification and identifier preflight | EAIC family confirmed; EAIC-002 allocated as governed alternative to PIC-001 planning label |
| 0.1 | Initial architecture drafting | Draft prepared under ADR-009 and MIG-001 |

# 25. Approval Record

**Chief Architect Draft Authorization:** Approved

**Chief Architect Decision:** Approved

**Architecture Verification:** Complete

**Canonical Status:** Canonical

**Activation State:** Inactive — Pending Coordinated Migration and Separate Activation Authorization

**Migration Execution Authority:** None

**Implementation Authority:** None

**Runtime Authority:** None

**Provider Endpoint Invocation Authority:** None

**Persistence Authority:** None

**Provider-to-Instrument Submission Authority:** None

**EDD-004 Drafting Authority:** None

**Commit Authority:** None

**Push Authority:** None

**Next Authorized Capability:** None

# 26. Governance Statement

This Version 0.1 document is an approved canonical Interface Contract.

Architectural contract publication is complete.

Its Activation State remains inactive pending coordinated migration and separate Chief Architect activation authority.

Canonical publication does not constitute runtime activation.

It establishes no migration execution, implementation, runtime, endpoint, acquisition, persistence, submission, interpretation, product-consumption, EDD-004, commit, or push authority.

# End of Document
