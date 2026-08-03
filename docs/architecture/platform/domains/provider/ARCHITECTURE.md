# DOMAIN-006 — Provider Domain
Status: Approved
Canonical Status: Approved Canonical Architecture
Owner: Chief Architect
Version: 1.1
Previous Canonical Version: 1.0
Classification: Architecture Standard
Review Authority: Chief Architect
Repository Location: `docs/architecture/platform/domains/provider/ARCHITECTURE.md`
Governing Decision: ADR-010 Version 1.0
Implementation Authority: None
Runtime Authority: None

## Purpose

Own Provider Integration as the platform responsibility for interacting with external Providers while preventing Provider-specific information from acquiring Instrument, product, Observation, Validation, Risk, execution, or other business-domain meaning.

Provider preserves Provider-owned information and evidence so that separately authorized downstream domains may evaluate it through approved contracts.

Provider does not create canonical Instrument meaning.

## Governing Authority

The Provider Domain derives its architectural meaning from:

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md);
- [EAIC-002 — Provider → Instrument Submission Contract](../../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md);
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md);
- [ADR-007 — Provider Capability Assessment Architecture](ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md);
- [ADR-008 — Provider Entitlement Assessment Architecture](ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md);
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md);
- [Domain Ownership Matrix](../../DOMAIN_OWNERSHIP_MATRIX.md);
- [Domain Dependency Matrix](../../DOMAIN_DEPENDENCY_MATRIX.md); and
- [Project KRONOS Data Flow](../../../DATA_FLOW.md).

ADR-009 governs Provider-bounded Instrument Master acquisition.

EAIC-002 governs the Provider-to-Instrument submission boundary.

MIG-001 governs coordinated repository alignment and does not itself activate runtime behavior.

## Governing Principle

> Acquire Broadly (within an authorised dataset).
>
> Interpret Canonically.
>
> Consume Explicitly.

Within one separately approved Provider, dataset, and operation, Provider acquisition shall preserve the complete safely representable returned dataset.

Provider acquisition shall not be filtered by:

- Swing membership;
- Intraday membership;
- any other product membership;
- product eligibility;
- a current product universe;
- current strategy demand;
- current execution markets;
- current Instrument support;
- current implementation convenience; or
- product inactivity.

Instrument performs canonical interpretation independently.

Products consume only through separately approved explicit product-consumption boundaries.

## Provider Responsibilities

Provider exclusively owns:

- Provider Integration;
- Provider-specific adapter isolation;
- Provider Context;
- Provider capability assessment;
- Provider entitlement assessment;
- Provider-bounded acquisition;
- Approved Acquisition Scope;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider Catalogue;
- Provider-and-Dataset Catalogue Partitions;
- Provider Snapshots;
- Provider Records;
- Provider Record Identity;
- Provider record dispositions;
- Snapshot Currentness;
- Snapshot Supersession;
- Submission Eligibility;
- Provider limitations;
- Provider provenance;
- acquisition provenance; and
- safe submission provenance supplied through EAIC-002.

Provider shall preserve Provider meaning without converting it into canonical, product, or business meaning.

Provider capability, Provider entitlement, Dataset Permission, Acquisition Authority, Provider Context, Provider Operational Availability, Provider Usability, Submission Eligibility, submission authority, and runtime authority remain independent determinations.

No one determination implies another.

## Proposed Provider Authentication and Authenticated Context Establishment Capability

This Version 1.1 section is approved canonical architecture published under the Chief Architect Decision and Engineering Architect Execution — Phase 1. It supersedes Version 1.0 as the canonical Provider Domain architecture while preserving unrelated Version 1.0 meaning.

### Capability Identity and Scope

**Provider Authentication and Authenticated Context Establishment** is a provider-neutral Shared Platform capability. Zerodha Kite is the first Provider adapter only.

The capability covers authentication initiation, Authentication Attempt lifecycle, callback acceptance, bounded credential retrieval, Provider-specific protocol translation, candidate Provider Context establishment, principal verification, intended Provider registration binding, Authenticated Provider Context establishment, local KRONOS session disposal and sanitized authentication and Provider-availability projections.

Authentication grants no Provider capability, account entitlement, Dataset Permission, Acquisition Authority, product eligibility, execution authority, trading permission or account-mutation authority.

### Single-Owner Model

Configuration owns credential meaning, Provider identity configuration, intended Provider registration, redirect-registration meaning and configuration validity.

The Secure Credential capability owns protected storage and retrieval mechanics, operating-system backend abstraction, custody evidence and retrieval-failure reporting.

The Provider Authentication Service owns Authentication Activity, Authentication Attempt creation and lifecycle, login initiation, callback acceptance and consumption state, sanitized Authentication Outcome, candidate Provider Context establishment, principal-binding orchestration, Authenticated Provider Context establishment and local context disposal.

The Kite adapter owns Kite-specific login-URL translation, request-token interpretation, session exchange, profile and principal-evidence translation and SDK interaction.

Presentation owns explicit initiation and sanitized state or failure presentation only. It owns no credential, token, authentication decision, principal-binding decision or Provider protocol logic.

No shared ownership is introduced.

### Dependency Direction

```text
Presentation
    → Provider Authentication Service
        → Configuration contract
        → Secure Credential contract
        → Provider authentication contract
            → Kite adapter
                → Kite SDK
```

Provider-specific SDK mechanics, responses, exceptions, tokens and credentials remain adapter-local.

### Authentication Attempt

Authentication Attempt is a first-class Provider Authentication Service construct for one bounded, explicitly initiated attempt against one intended Provider registration.

It preserves an internal non-sequential cryptographically random attempt identity, Provider identity, intended Provider registration identity, creation/start/expiry times, lifecycle state, callback-consumed state, terminal state, sanitized outcome, correlation evidence, callback-acceptance evidence, principal-binding evidence and local listener identity where applicable.

At most one attempt may be active per Provider registration. Each attempt is bounded in time. A callback and request token may each be accepted at most once. A terminal attempt cannot reactivate. No attempt exposes credentials or tokens. No automatic retry creates an attempt; another attempt requires explicit user action and separate authority where governance requires it.

### Authentication Lifecycle

The provider-neutral authentication lifecycle is:

- `NOT_AUTHENTICATED`
- `AUTHENTICATING`
- `AUTHENTICATED`
- `FAILED`
- `EXPIRED`
- `ENDED`

Permitted transitions are:

```text
NOT_AUTHENTICATED → AUTHENTICATING
AUTHENTICATING → AUTHENTICATED | FAILED | EXPIRED
AUTHENTICATED → EXPIRED | ENDED
```

`FAILED`, `EXPIRED` and `ENDED` are terminal for the applicable attempt or context. A new explicit attempt is required to return to `AUTHENTICATING`. `CONNECTED` is not an authentication state.

### Provider Availability

Provider availability is represented separately as `NOT_VERIFIED`, `VERIFYING`, `AVAILABLE`, `UNAVAILABLE` or `INDETERMINATE`.

`AUTHENTICATED` does not imply `AVAILABLE`. Temporary Provider Unavailability during later verification does not rewrite an established authentication result as `FAILED`. Authoritative invalid-token evidence may transition the context to `EXPIRED` or another separately approved invalid state.

### Callback Acceptance

Callback acceptance is owned by the Provider Authentication Service; the loopback component owns transport mechanics and cannot decide authentication success.

The approved callback boundary is:

```text
http://127.0.0.1:8765/kite/callback
```

The listener shall bind only to `127.0.0.1` on fixed port `8765`, accept GET only on `/kite/callback`, validate the Host header exactly, serve one outstanding Authentication Attempt, accept one callback and one request token, enforce a bounded timeout, and reject duplicate, wrong-method, wrong-path, wrong-host, missing-token and multiple-token requests. Provider rejection and error callbacks become sanitized terminal outcomes.

The component shall log no URL or query string, suppress default HTTP request logging, return only a sanitized completion page and stop immediately after terminal acceptance or failure.

Live execution remains prohibited until the Sponsor confirms the external Provider registration uses the exact approved callback URL. This architecture authorizes no external configuration change.

### Correlation and Residual Risk

Provider-returned state or nonce round-trip support is unproven. Version 1 does not claim full state-based CSRF protection.

Available correlation evidence is one explicitly initiated attempt, one internal attempt identity, one active listener, listener start and expiry, exact configured host/port/path, expected Provider and registration identities, callback time within the attempt lifetime, callback-consumed state, one-token cardinality and post-exchange principal-binding evidence.

Compensating controls are explicit initiation, short lifetime, loopback binding, exact Host and path validation, GET only, one active attempt, one callback, one token, duplicate rejection, bounded timeout, immediate shutdown and principal binding.

Residual risk remains: without proven Provider-returned state correlation, a malicious local process or browser-mediated callback injection may attempt to deliver a token to the active loopback listener. The controls reduce but do not eliminate this risk.

### Principal Binding and Context Establishment

```text
authentication exchange outcome
    → candidate Provider Context
    → principal verification
    → intended Provider registration binding
    → Authenticated Provider Context
```

Token-exchange success creates only a candidate Provider Context. The candidate is unavailable to products and to all other Provider operations except the approved principal-verification operation.

Principal verification uses the approved Provider verification path and returns only minimum evidence needed to compare against Configuration's intended Provider registration.

- `MATCHED` permits Authenticated Provider Context establishment.
- `MISMATCHED` requires local candidate disposal and terminal attempt failure without manual override.
- `UNCONFIRMED` requires local candidate disposal and terminal attempt failure without manual override.
- `UNAVAILABLE` is never treated as matched; for the pilot it requires local candidate disposal, terminal `FAILED` authentication with sanitized `PRINCIPAL_BINDING_UNAVAILABLE`, and `INDETERMINATE` Provider availability.

The `UNAVAILABLE` pilot rule applies before authentication is established and does not rewrite an already Authenticated Provider Context as failed.

Retainable binding evidence is limited to the sanitized binding category, Provider identity, a non-sensitive intended-registration reference, attempt terminal category, permitted time evidence and confirmation of candidate establishment or disposal. Account identifiers, profile fields, raw Provider payloads and raw exceptions are prohibited from UI, logs and retained evidence.

### Credential Custody

The API key comes from approved Configuration and is not displayed or logged.

The API secret is retrieved through a provider-neutral Secure Credential contract. Apple Keychain is the first backend and Windows Credential Manager is a future backend. It is returned only for the bounded exchange operation and is excluded from source code, repository fixtures, browser storage, command-line arguments, logs, screenshots, plain-text configuration, `.env` and normal daily UI entry.

The request token is one-use and in-memory, accepted once, exchanged once, never displayed, logged or persisted, and discarded immediately after exchange.

The access token remains inside the authenticated Provider client and Provider Context. It has no public getter, UI exposure, Version 1 persistence or cross-context reuse after local disposal. No secure-memory-erasure claim is made.

### End KRONOS Session

End KRONOS Session performs local Authenticated Provider Context disposal, local candidate disposal where applicable, removal of reuse eligibility and transition to `ENDED`. It performs no Provider token invalidation, remote logout, Provider mutation or automatic reauthentication.

The existing Kite termination path performs Provider-side token invalidation and cannot be reused for End KRONOS Session without separation from a local-only disposal path.

### Engineering Lifecycle Separation

This architecture amendment contains no engineering design or implementation authority.

Any downstream Engineering Design activity requires its own governed authorization, drafting, verification, review and publication lifecycle. Existing login behavior alone does not prove architecture or future engineering conformance.

### Architecture Authority Boundary

This amendment grants no implementation, credential-use, browser, listener, endpoint, runtime, commit or push authority. It authorizes no CAR-014 execution and does not reopen CAR-015.

## Provider Catalogue

### First-Class Architectural Artifact

Provider Catalogue is a first-class Provider-owned platform architectural artifact.

It is composed of strictly isolated Provider-and-Dataset Catalogue Partitions containing durable lineages of:

- immutable Provider Snapshots;
- Provider Records;
- record dispositions;
- Approved, Requested, and Received Acquisition Scope;
- technical acquisition results;
- Acquisition Outcomes;
- currentness and supersession evidence;
- Provider limitations; and
- non-sensitive provenance.

Provider Catalogue is independent from:

- one Provider adapter implementation;
- one product;
- one product universe;
- the Canonical Instrument Catalogue;
- one Instrument interpretation outcome;
- one persistence technology; and
- one physical schema.

It shall not become:

- an implementation cache;
- an adapter-local collection;
- a temporary product filter;
- a raw Provider payload archive;
- a canonical Instrument store;
- an Observation store; or
- a business-decision store.

### Partition Isolation

Each Provider-and-Dataset Catalogue Partition is bounded independently by:

- Provider identity;
- dataset identity;
- Provider Context or operational-environment class where materially required;
- approved Provider operation;
- Acquisition Authority;
- security classification;
- retention boundary;
- snapshot lineage; and
- provenance.

No Provider Record, Provider Snapshot identity, currentness state, supersession relationship, or Provider-native identifier may cross a Provider-and-Dataset Catalogue Partition.

A future Provider shall use a separate:

- Provider identity;
- Provider Context;
- adapter;
- capability evidence;
- entitlement evidence where applicable;
- Dataset Permission;
- Acquisition Authority;
- catalogue partition;
- scope;
- outcomes; and
- provenance.

Provider vocabulary or evidence from one Provider shall not complete, reinterpret, overwrite, or establish equivalence with another Provider.

### Identity Scope

Provider Catalogue Partition Identity is scoped by at least:

- Provider identity;
- dataset identity; and
- operational environment or Provider Context class where materially required.

Provider Snapshot Identity is unique only within one Provider-and-Dataset Catalogue Partition.

Provider Record Identity is unique only within one Provider Snapshot.

Provider tokens, exchange tokens, symbols, row positions, and other Provider-native identifiers shall not alone establish:

- globally permanent Provider Record Identity;
- cross-snapshot permanence;
- cross-partition permanence;
- cross-Provider identity equivalence; or
- canonical Instrument identity.

### Currentness and Supersession

Snapshot Currentness is Provider-owned meaning identifying the snapshot currently applicable for Provider reference use.

Snapshot Supersession is Provider-owned, explicit, traceable, and non-destructive.

A superseding Provider Snapshot:

- does not mutate or erase an earlier snapshot;
- does not change historical Provider evidence;
- does not establish Instrument lifecycle;
- does not establish canonical identity continuity;
- does not establish Provider mapping continuity;
- does not establish product eligibility; and
- does not establish Market state.

Record-added, record-absent, record-changed, symbol-change, and token-reuse evidence remain Provider-owned snapshot-difference meanings.

They do not create Instrument lifecycle or canonical identity.

## Acquisition Boundary

Provider acquisition may begin only under separately approved Provider, dataset, operation, capability, permission, context, authority, environment, security, licensing, and retention boundaries.

Provider shall preserve separately:

- Approved Acquisition Scope;
- Requested Acquisition Scope;
- Received Acquisition Scope;
- technical acquisition success or failure; and
- exactly one Acquisition Outcome.

Acquisition Outcome shall preserve the applicable canonical meaning:

- Complete;
- Partial;
- Empty;
- Missing;
- Unsupported; or
- Failed.

Technical success does not imply Complete outcome.

Partial, Empty, Missing, and bounded limitation outcomes shall not be silently converted into failure, completeness, Instrument meaning, or product meaning.

The acquisition boundary ends with Provider-owned technical result, scope, outcome, safe records, dispositions, currentness evidence, and provenance.

It creates no Instrument or product meaning.

## Dataset Boundary

This migration aligns the Provider Domain only for the Instrument Master dataset governed by ADR-009.

Instrument Master acquisition is:

- Provider-bounded;
- dataset-bounded;
- operation-bounded;
- product-neutral; and
- subject to separately approved authority.

For the approved Instrument Master operation, broad acquisition means the complete safely representable returned dataset within the approved boundary.

It does not mean every Provider dataset.

Instrument references, including Options instrument references returned within the approved Instrument Master dataset, remain Instrument Master Provider records.

The following are outside the ADR-009 Instrument Master boundary:

- Futures OI;
- Options OI;
- Quotes;
- Historical Data;
- Streaming;
- Market Depth;
- Option Chain; and
- every other separately governed Provider dataset.

Each additional dataset requires its own separately approved:

- Provider capability;
- Dataset Permission;
- entitlement evidence where applicable;
- Acquisition Authority;
- engineering design;
- endpoint invocation authority;
- implementation authority; and
- runtime authority.

Instrument Master architecture shall not be reused, extended, or interpreted as authority for another dataset.

## Provider Record Dispositions

Provider record disposition is multidimensional and shall not become Instrument lifecycle.

Every preserved Provider Record has exactly one preservation fact:

- `ACQUIRED`.

Every preserved Provider Record has exactly one structural disposition:

- `STRUCTURALLY_VALID`; or
- `STRUCTURALLY_INVALID`.

Zero or more evidence-quality flags may coexist:

- `AMBIGUOUS`;
- `DUPLICATE`;
- `INTERNALLY_INCONSISTENT`;
- `MISSING_REQUIRED_PROVIDER_ASSERTION`;
- `UNRECOGNIZED_PROVIDER_VOCABULARY`; and
- `PROVIDER_LIMITATION_PRESENT`.

Every preserved Provider Record has exactly one quarantine disposition:

- `NOT_QUARANTINED`; or
- `QUARANTINED`.

Every preserved Provider Record has exactly one interpretation-support disposition:

- `INTERPRETATION_SUPPORT_ESTABLISHED`;
- `INTERPRETATION_SUPPORT_LIMITED`; or
- `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`.

Every evaluated Provider Record or explicitly bounded Submission Unit has exactly one submission disposition:

- `SUBMISSION_ELIGIBLE`; or
- `SUBMISSION_INELIGIBLE`.

`STRUCTURALLY_INVALID` requires:

- `QUARANTINED`;
- `INTERPRETATION_SUPPORT_NOT_ESTABLISHED`; and
- `SUBMISSION_INELIGIBLE`.

`QUARANTINED` always requires `SUBMISSION_INELIGIBLE`.

Evidence of ambiguity, duplication, inconsistency, missingness, unrecognized vocabulary, and Provider limitations shall remain explicit and shall not be silently repaired, selected, discarded, or converted into Instrument meaning.

## Submission Eligibility

Submission Eligibility is a deterministic Provider-owned boundary determination.

Provider may establish `SUBMISSION_ELIGIBLE` only when every applicable ADR-009 and EAIC-002 condition is independently satisfied.

Failure to establish any mandatory condition requires `SUBMISSION_INELIGIBLE`.

Submission Eligibility:

- is independent for each Provider Record or explicitly bounded Submission Unit;
- does not require a Complete Acquisition Outcome;
- may remain established for independently eligible records originating from a Partial Acquisition Outcome while partiality remains explicit;
- does not authorize submission;
- does not establish Instrument acceptance;
- does not establish Instrument interpretation;
- does not establish canonical identity;
- does not establish Provider mapping;
- does not establish product membership or eligibility;
- does not establish Observation authority;
- does not establish Validation or Risk judgment;
- does not establish execution authority; and
- does not establish runtime or implementation authority.

Provider owns Submission Eligibility.

Instrument owns all later interpretation meaning.

## Provider-to-Instrument Boundary

EAIC-002 is the sole approved platform contract through which eligible Provider-owned Instrument Master information may cross into the Instrument boundary.

Provider shall:

- construct only deterministic EAIC-002 Submission Units;
- preserve Provider, dataset, partition, snapshot, record, disposition, scope, and provenance meaning;
- establish Submission Eligibility independently;
- obtain separate Provider-to-Instrument Submission Authority;
- preserve sensitive-data and adapter isolation;
- preserve rejection evidence without transferring ownership; and
- remain responsible for Provider-owned evidence after receipt or rejection.

Provider shall never:

- write directly into Instrument-owned state;
- create or mutate canonical Instrument identity;
- create canonical classification;
- perform Instrument interpretation;
- create Provider mapping;
- perform cross-Provider reconciliation;
- populate the Canonical Instrument Catalogue;
- treat technical receipt as semantic acceptance; or
- permit products to consume Provider Catalogue records or submission envelopes directly.

EAIC-002 receipt, validation, and interpretation admission remain separate from Instrument interpretation, canonical identity decision, Provider mapping decision, canonical catalogue publication, and product consumption.

EAIC-002 remains inactive until every activation condition in that contract and MIG-001 is satisfied and the Chief Architect separately authorizes activation.

This Domain alignment does not authorize Provider-to-Instrument submission.

## Non-Responsibilities

Provider does not own:

- Instrument interpretation;
- canonical Instrument identity;
- canonical classification;
- canonical relationship meaning;
- Provider mapping;
- cross-Provider reconciliation;
- Instrument lifecycle;
- Canonical Instrument Catalogue publication;
- product-universe membership;
- product eligibility;
- Swing eligibility;
- Intraday eligibility;
- Observation or Market Facts;
- Market Schedule or Market state;
- Validation or Business Judgment;
- Risk semantics or Risk Approval;
- execution authority;
- trading decisions;
- orders;
- positions;
- Portfolio meaning;
- Audit Trail ownership;
- Runtime Configuration meaning; or
- the Execution Context Provider responsibility defined by ADR-006.

Instrument owns interpretation, canonical identity, canonical classification, Provider mapping, cross-Provider reconciliation, Instrument lifecycle meaning, and Canonical Instrument Catalogue publication.

Products own their respective membership and eligibility meanings.

Observation owns factual Market Facts.

Market owns Market Schedule and approved market-state meaning.

Validation owns Business Judgment.

Risk owns Risk Approval and Risk semantics.

Audit owns the Audit Trail without acquiring ownership of recorded Provider or Instrument facts.

## Published Contracts

Provider publishes only Provider-owned meaning through approved platform contracts.

Applicable approved boundaries include:

- Provider capability assessment governed by ADR-007;
- Provider entitlement assessment governed by ADR-008; and
- Provider-to-Instrument submission governed by EAIC-002.

EAIC-002 is the only approved downstream contract for eligible Instrument Master Provider Records.

Publication through an approved contract does not transfer semantic ownership.

## Consumed Authority and Dependencies

Provider may consume only separately approved authority and context required for the bounded Provider activity, including:

- Runtime Configuration and Configuration Eligibility from Configuration;
- Provider capability evidence;
- Provider entitlement evidence where applicable;
- Dataset Permission;
- Provider Context;
- Acquisition Authority;
- security classification;
- environment reference;
- licensing and retention authority; and
- Provider Operational Availability and Provider Usability evidence.

Provider has no business-pipeline dependency.

Provider remains outside the:

> Instrument → Observation → Validation → Risk → Execution → Portfolio

business pipeline.

Provider dependencies shall not reverse the approved Domain Dependency Matrix or transfer ownership.

## Provenance

Provider provenance preserves, where applicable:

- Provider identity;
- Provider API and official operation basis;
- official documentation basis;
- SDK name and version basis;
- adapter identity;
- adapter revision basis;
- Provider version or revision basis;
- Provider vocabulary;
- documented limitations;
- licensing and retention limitations; and
- evidence currentness.

Acquisition and submission provenance preserve the applicable:

- Provider Context reference;
- dataset and operation identity;
- capability basis;
- entitlement basis where applicable;
- Dataset Permission reference;
- Acquisition Authority reference;
- Provider-to-Instrument Submission Authority reference where applicable;
- Approved, Requested, and Received Acquisition Scope;
- technical acquisition result;
- Acquisition Outcome;
- Provider Catalogue Partition identity;
- Provider Snapshot Identity;
- Provider Record Identity;
- request initiation time;
- response receipt time;
- snapshot closure time;
- acquisition effective time;
- submission initiation time;
- submission receipt time;
- contract validation time;
- interpretation admission time;
- Configuration context;
- environment;
- security classification;
- limitations;
- missingness;
- partiality;
- duplicate and inconsistency evidence;
- disposition; and
- supersession relationship.

No provenance time may silently substitute for another.

Credentials, tokens, authorization headers, raw Provider payloads, raw SDK clients, SDK response objects, SDK exceptions, private transport state, and unapproved sensitive information shall not become Provider Records, provenance, logs, errors, or Audit evidence.

## Architectural Constraints

- Provider-specific mechanics remain inside Provider adapters.
- Provider SDK types, responses, exceptions, credentials, and private transport state shall not cross Provider-neutral contracts.
- Provider information remains external, non-canonical, product-neutral, and Provider-owned.
- Provider shall not infer canonical meaning from symbols, tokens, price behavior, product demand, or implementation convenience.
- Provider shall not use product membership to filter approved Instrument Master acquisition.
- Provider shall not silently discard returned Provider records because no current product consumes them.
- Provider shall not create architectural authority through capability, entitlement, availability, usability, catalogue presence, disposition, or eligibility.
- Provider acquisition, persistence, submission, interpretation, implementation, endpoint, and runtime authorities remain separate.
- Provider shall communicate with Instrument only through EAIC-002 when separately activated and authorized.
- Business domains shall not depend on Provider internals.
- No architecture in this document authorizes implementation, endpoint invocation, live acquisition, persistence, runtime behavior, or EDD-004.

## Ownership and Dependency Conformance

This architecture remains within the Domain Ownership Matrix assignment:

> Provider Integration → Provider

Provider Catalogue, Provider acquisition, Provider records, dispositions, Submission Eligibility, scope, outcomes, Provider Context, and Provider provenance are Provider Integration responsibilities.

They do not create a new domain or transfer any responsibility from Instrument, Observation, Market, Validation, Risk, Execution, Portfolio, Configuration, Event, or Audit.

This architecture remains within the Domain Dependency Matrix assignment:

> Provider → None (Business)

The Provider-to-Instrument boundary is an approved platform support contract.

It does not place Provider inside the business pipeline or permit business domains to depend on Provider internals.

## Approved Constitutional References

- CA-013 — Domain Identity
- CA-014 — Responsibility Classes
- CA-015 — Contract-Based Dependencies
- CA-016 — Single Semantic Ownership
- CA-017 — Domain Communication (Platform Only)
- CA-018 — Human Workflow Independence
- CA-019 — Architecture Freeze
- [PLATFORM-000 — KRONOS Platform Constitution](../../PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](../../PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](../../DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](../../DOMAIN_OWNERSHIP_MATRIX.md)

## Related Approved Repository Documents

- [ADR-006 — Execution Context Provider Architecture](../../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADR-007 — Provider Capability Assessment Architecture](ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [KRONOS Engine Ownership](../../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../../DATA_FLOW.md)

## Migration and Authority Status

This Provider Domain alignment is one controlled MIG-001 work package.

It does not:

- complete the coordinated migration;
- activate ADR-009 or EAIC-002;
- amend the Instrument Domain;
- amend ownership or dependency matrices;
- amend DATA_FLOW;
- amend any ADP or EAP;
- authorize Provider communication;
- authorize endpoint invocation;
- authorize live acquisition;
- authorize persistence;
- authorize Provider-to-Instrument submission;
- authorize EDD-004;
- authorize implementation; or
- authorize runtime behavior.
