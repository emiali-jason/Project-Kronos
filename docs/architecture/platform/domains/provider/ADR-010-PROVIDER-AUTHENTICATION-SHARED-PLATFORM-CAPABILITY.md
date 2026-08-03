# ADR-010 — Provider Authentication Shared Platform Capability

**Document ID:** ADR-010
**Title:** Provider Authentication Shared Platform Capability
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Approved Canonical Architecture
**Classification:** Architecture Decision Record
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Approved By:** Chief Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md`
**Capability Name:** Provider Authentication and Authenticated Context Establishment
**Decision Scope:** Platform
**Authority Basis:** Chief Architect Decision — Approved; Engineering Architect Execution — Phase 1
**Architecture Decision:** Approved
**Implementation Authority:** None
**Runtime Authority:** None

---

# 1. Context

KRONOS requires a provider-neutral Shared Platform capability that initiates Provider authentication, accepts a bounded authentication callback, establishes a candidate Provider Context, verifies the candidate principal against the intended Provider registration and establishes an Authenticated Provider Context only after that binding succeeds.

Zerodha Kite is the first Provider adapter. Kite is not the permanent capability identity, semantic owner or platform boundary.

The repository already defines Configuration-owned authentication meaning, Provider-owned Authentication Activity and Authenticated Provider Context, and an existing Kite authentication implementation. Those existing meanings and implementation paths remain inputs to a required implementation-conformance review; their existence does not prove conformance with this decision.

This approved canonical architecture grants no implementation, credential-use, browser, listener, SDK, endpoint or runtime authority.

# 2. Decision

Establish **Provider Authentication and Authenticated Context Establishment** as a provider-neutral capability owned by **Shared Platform**.

The first adapter is **Zerodha Kite**. Additional Provider adapters may be considered only through separately approved architecture and engineering authority.

The capability covers:

- authentication initiation;
- Authentication Attempt lifecycle;
- callback acceptance;
- credential-retrieval boundaries;
- Provider-specific protocol translation;
- candidate Provider Context establishment;
- principal verification;
- intended Provider registration binding;
- Authenticated Provider Context establishment;
- local KRONOS session disposal; and
- sanitized authentication and Provider-availability projections.

# 3. Authority Separation

Authentication or Authenticated Provider Context establishment grants no:

- Provider capability;
- account entitlement;
- Dataset Permission;
- Acquisition Authority;
- product eligibility;
- execution authority;
- trading permission;
- account-mutation authority; or
- authority to invoke any Provider operation not separately approved.

An Authenticated Provider Context is a bounded prerequisite only. It carries no downstream business meaning.

# 4. Ownership Model

Each meaning has one owner. No shared ownership is introduced.

## 4.1 Configuration

Configuration owns:

- credential meaning;
- Provider identity configuration;
- intended Provider registration;
- redirect-registration meaning; and
- configuration validity.

## 4.2 Secure Credential capability

The Secure Credential capability owns:

- protected credential-storage mechanics;
- protected credential-retrieval mechanics;
- operating-system backend abstraction;
- custody evidence; and
- retrieval-failure reporting.

It does not own credential meaning or Provider authentication outcomes.

## 4.3 Provider Authentication Service

The Provider Authentication Service owns:

- Authentication Activity;
- Authentication Attempt creation and lifecycle;
- login initiation;
- callback acceptance;
- callback-consumption state;
- sanitized Authentication Outcome;
- candidate Provider Context establishment;
- principal-binding orchestration;
- Authenticated Provider Context establishment; and
- local context disposal.

## 4.4 Kite adapter

The Kite adapter owns:

- Kite-specific login-URL translation;
- Kite request-token interpretation;
- Kite session exchange;
- Kite-specific profile and principal-evidence translation; and
- Kite SDK interaction.

## 4.5 Presentation

Presentation owns:

- explicit user initiation;
- sanitized state presentation; and
- sanitized failure presentation.

Presentation owns no credential or token custody, authentication decision, principal-binding decision or Provider protocol logic.

# 5. Dependency Model

```text
Presentation
    → Provider Authentication Service
        → Configuration contract
        → Secure Credential contract
        → Provider authentication contract
            → Provider adapter
                → Provider SDK
```

The Provider Authentication Service depends on provider-neutral contracts. Provider-specific SDK types, responses, exceptions, credentials and tokens remain adapter-local.

# 6. Authentication Attempt

Authentication Attempt is a first-class architectural construct representing one bounded, explicitly initiated effort to establish an Authenticated Provider Context for one intended Provider registration.

An Authentication Attempt contains or preserves these meanings:

- internal attempt identity;
- Provider identity;
- intended Provider registration identity;
- creation time;
- start time;
- expiry time;
- lifecycle state;
- callback-consumed state;
- terminal state;
- sanitized outcome;
- correlation evidence;
- callback-acceptance evidence;
- principal-binding evidence; and
- local listener identity where applicable.

The internal identity shall be non-sequential and cryptographically random through an injectable identity source. It shall not be exposed to the user unless separately required for sanitized support or audit evidence.

Required invariants are:

1. At most one active Authentication Attempt exists per Provider registration.
2. Each attempt has a bounded lifetime.
3. A callback may be consumed at most once.
4. A request token may be accepted and exchanged at most once.
5. A terminal attempt cannot return to an active state.
6. No attempt exposes credentials or tokens.
7. Token-exchange success alone does not establish a usable Authenticated Provider Context.
8. Mismatched or unconfirmed principal binding fails the attempt.
9. Completion produces only a sanitized outcome.
10. Automatic retry creates no attempt.
11. A new attempt requires a new explicit user action and separate authority where governance requires it.

# 7. Authentication State Model

The authentication lifecycle is:

- `NOT_AUTHENTICATED`
- `AUTHENTICATING`
- `AUTHENTICATED`
- `FAILED`
- `EXPIRED`
- `ENDED`

Permitted transitions are:

```text
NOT_AUTHENTICATED → AUTHENTICATING

AUTHENTICATING → AUTHENTICATED
AUTHENTICATING → FAILED
AUTHENTICATING → EXPIRED

AUTHENTICATED → EXPIRED
AUTHENTICATED → ENDED
```

`FAILED`, `EXPIRED` and `ENDED` are terminal for the applicable attempt or context. Returning to `AUTHENTICATING` requires a new explicitly initiated Authentication Attempt.

The earlier proposal's `NOT_CONNECTED`, `CONNECTING` and `CONNECTED` terms map respectively to `NOT_AUTHENTICATED`, `AUTHENTICATING` and `AUTHENTICATED`. `CONNECTED` is not retained as an authentication state.

# 8. Provider Availability and Verification

Provider availability is a separate projection:

- `NOT_VERIFIED`
- `VERIFYING`
- `AVAILABLE`
- `UNAVAILABLE`
- `INDETERMINATE`

`AUTHENTICATED` does not imply `AVAILABLE`.

Temporary Provider Unavailability during a separately initiated verification shall not rewrite an established authentication result as `FAILED`. An Authenticated Provider Context may remain authenticated while verification is temporarily unavailable. Authoritative invalid-token evidence may transition the context to `EXPIRED` or another separately approved authentication-invalid state.

# 9. Callback Acceptance Contract

Callback acceptance is an architectural decision owned by the Provider Authentication Service. Transport mechanics are delegated to a loopback callback component. The transport component shall not decide authentication success.

The approved callback boundary is:

```text
http://127.0.0.1:8765/kite/callback
```

Mandatory controls are:

- bind only to `127.0.0.1`;
- fixed port `8765`;
- exact path `/kite/callback`;
- GET only;
- exact Host-header validation for `127.0.0.1:8765`;
- one outstanding Authentication Attempt;
- one callback;
- one request token;
- bounded timeout;
- duplicate rejection;
- wrong-method rejection;
- wrong-path rejection;
- wrong-host rejection;
- missing-token rejection;
- multiple-token rejection;
- sanitized Provider rejection or error handling;
- no URL or query-string logging;
- no default HTTP request logging;
- a sanitized completion page; and
- immediate listener shutdown after terminal acceptance or failure.

# 10. Callback Correlation and Residual Risk

Provider-returned state or nonce round-trip support is unproven. Version 1 does not claim full state-based CSRF protection.

Available correlation evidence is limited to:

- one explicitly initiated attempt;
- one internally generated attempt identity;
- one active listener;
- listener start and expiry;
- exact configured host, port and path;
- expected Provider identity;
- expected Provider registration identity;
- callback time within attempt lifetime;
- callback-consumed state;
- one request-token cardinality; and
- principal-binding evidence after exchange.

Compensating controls are explicit initiation, short listener lifetime, loopback binding, exact Host validation, exact path, GET only, one active attempt, one callback, one token, duplicate rejection, bounded timeout, immediate shutdown and post-exchange principal binding.

Residual risk remains: without proven Provider-returned state correlation, a malicious local process or browser-mediated callback injection may attempt to deliver a token to the active loopback listener. These controls reduce but do not eliminate that risk.

# 11. Principal-Binding Contract

The mandatory establishment flow is:

```text
authentication exchange outcome
    → candidate Provider Context
    → principal verification
    → intended Provider registration binding
    → Authenticated Provider Context
```

Principal verification uses the separately approved Provider verification path and produces only the minimum evidence required for binding. Binding compares translated principal evidence with the intended Provider registration owned by Configuration.

Binding outcomes are:

- `MATCHED`: the Authenticated Provider Context may be established.
- `MISMATCHED`: dispose of the candidate locally, fail the attempt and permit no manual override.
- `UNCONFIRMED`: dispose of the candidate locally, fail the attempt and permit no manual override.
- `UNAVAILABLE`: do not treat as `MATCHED`; dispose of the candidate locally and terminate the pilot attempt as `FAILED` with a sanitized `PRINCIPAL_BINDING_UNAVAILABLE` outcome. The Provider availability projection is `INDETERMINATE`.

The `UNAVAILABLE` recommendation does not rewrite a previously established Authenticated Provider Context as failed. It applies before establishment, while the context remains a candidate.

Minimum retainable sanitized binding evidence is:

- binding outcome category;
- Provider identity;
- non-sensitive intended-registration reference approved by Configuration;
- attempt lifecycle and terminal category;
- verification time category or timestamp where governance permits; and
- confirmation that the candidate was established or disposed.

No account identifier, profile field, Provider payload, token or raw exception may enter the UI, logs or retained evidence.

# 12. Candidate Provider Context

A candidate Provider Context exists only after token exchange and before successful principal binding.

It is unavailable to products, acquisition, trading and all Provider operations other than the approved principal-verification operation. It has no reuse eligibility and cannot be published as authenticated.

Mismatch, unconfirmed binding, binding unavailability, expiry or any terminal failure requires immediate local disposal.

# 13. Credential Custody

Configuration owns credential meaning and intended Provider registration. The Secure Credential capability owns protected storage and retrieval mechanics.

The API key is obtained from approved Configuration and is neither displayed by the daily login UI nor logged.

The API secret is retrieved through a provider-neutral secure-credential interface. Apple Keychain is the first backend; Windows Credential Manager is a future backend. The secret is returned only for the bounded exchange operation. It is not stored in source code, repository fixtures, browser storage, command-line arguments, logs, screenshots, plain-text configuration or `.env`, and it is not entered in the normal daily login UI.

The request token is one-use, in-memory, accepted once, exchanged once, never displayed, never logged, never persisted and discarded immediately after exchange.

The access token remains only inside the authenticated Kite client and Provider Context. It has no public getter, UI exposure, Version 1 persistence or cross-context reuse after local disposal.

No secure-memory-erasure claim is made for any secret or token.

# 14. End KRONOS Session

**End KRONOS Session** means:

- local Authenticated Provider Context disposal;
- local candidate-context disposal where applicable;
- removal of local eligibility for reuse;
- transition to `ENDED` for an established context;
- no Provider token invalidation;
- no remote logout;
- no Provider mutation; and
- no automatic reauthentication.

The existing Kite termination path calls Provider-side access-token invalidation. That path cannot implement End KRONOS Session without a separately designed local-only disposal path.

# 15. Existing-Pipeline Reuse

The default decision is to reuse the existing Kite authentication pipeline after a formal implementation-conformance review.

Known conformance gaps requiring wrappers, amendments or controlled production changes are:

- authentication is currently executed as one synchronous operation rather than a first-class bounded Authentication Attempt;
- redirect handling is injected but the repository has no approved loopback listener with the mandatory callback controls;
- the API secret is currently loaded into Settings and passed into the authentication object rather than retrieved through a Secure Credential capability;
- token exchange currently marks the SDK handle authenticated before principal verification;
- the current profile verification validates only response shape and does not bind the verified principal to Configuration's intended Provider registration;
- candidate-context isolation and binding evidence are absent;
- lifecycle vocabulary does not expose the approved provider-neutral attempt states;
- current termination performs remote Provider invalidation; and
- local-only End KRONOS Session is absent.

Existing adapter-local error sanitization, one-use API-secret consumption, request-token cardinality checks, profile-payload discard, expiry calculation and Provider-availability separation are reusable only after conformance is proven.

# 16. Engineering Lifecycle Separation

This architecture publication contains no engineering design artifact or implementation authority.

Any downstream Engineering Design activity shall begin through its own separate authorization, drafting, verification, review and publication lifecycle.

Existing login behavior is not evidence of architectural or future engineering conformance by itself.

# 17. Cross-Document Verification Plan

Canonical publication verification compares ADR-010 and DOMAIN-006 Version 1.1 with:

- canonical DOMAIN-006 Version 1.0;
- Configuration architecture and ADP-001F/ADP-001G;
- Secure Credential ownership and operating-system backend boundaries;
- Provider contracts and Kite authentication architecture;
- Domain Ownership and Dependency matrices;
- mandatory architecture indexes; and
- the Document Register.

The review shall prove consistent use of Provider Authentication and Authenticated Context Establishment, Authentication Attempt, candidate Provider Context, Authenticated Provider Context, intended Provider registration, principal binding, End KRONOS Session, authentication state and Provider availability state.

# 18. Decision Status

ADR-010 Version 1.0 is Approved Canonical Architecture.

**Implementation Authority:** None

**Runtime Authority:** None

**Credential-Use Authority:** None

**Endpoint Authority:** None

# 19. Related Documents

- [DOMAIN-006 — Provider Domain](ARCHITECTURE.md)
- [ADP-001F — Configuration to Provider Runtime Configuration Boundary](../../../products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-RUNTIME-CONFIGURATION-BOUNDARY.md)
- [ADP-001G — Configuration to Provider Authentication Boundary](../../../products/swing/SWING-PHASE-1-CONFIGURATION-PROVIDER-AUTHENTICATION-BOUNDARY.md)
- [DOC-001 — Document Identification, Classification & Metadata Standard](../../../../governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)

---

# End of Document
