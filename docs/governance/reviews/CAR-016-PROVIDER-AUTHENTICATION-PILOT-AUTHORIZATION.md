# CAR-016 — Provider Authentication and Authenticated Context Establishment Implementation and Pilot Authorization

**Document ID:** CAR-016
**Title:** Provider Authentication and Authenticated Context Establishment Implementation and Pilot Authorization
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVED FOR CANONICAL PUBLICATION
**Current Implementation Authorization:** Stage 1 Authorized with Constraints
**Current Runtime Authority:** None
**Current Provider Endpoint Authority:** None
**Current Credential-Use Authority:** None
**Current Browser/Listener Authority:** None
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Exact Implementation Baseline:** `3a7c35b4c0db672cfe53d498034afbc320921bc6`

---

# 1. Purpose

CAR-016 Version 1.0 defines the bounded implementation-publication and pilot governance for Provider Authentication and Authenticated Context Establishment.

Canonical Version 1.0 activates only Stage 1 within the exact sequential implementation, fake-only verification and inspection-safe pilot governance described below. Later stages require their own stage-start authority. Publication does not authorize live credentials, Keychain access, listener creation, browser opening, real SDK construction, Provider calls or endpoint use.

Any live pilot requires successful publication, the external Kite redirect-confirmation gate, a clean frozen implementation SHA, successful preflight and a separate explicit Sponsor execution instruction. No one condition implies another.

# 2. Governing Authority

CAR-016 is subordinate to:

- [ADR-010 Version 1.0 — Provider Authentication Shared Platform Capability](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md);
- [DOMAIN-006 Version 1.1 — Provider Domain](../../architecture/platform/domains/provider/ARCHITECTURE.md);
- [EDD-001 Version 1.1 — Provider Authentication and Authenticated Context Establishment Engineering Design](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

CAR-016 cannot amend architecture or Engineering Design. EDD-001 Version 1.1 definitions, state separation, precedence, custody, redaction, non-retention and local-disposal rules control.

# 3. Approved Decision and Authority Phases

> **APPROVED FOR CANONICAL PUBLICATION**

## 3.1 Draft phase — historical state

Before canonical publication, the Draft authorized documentation preparation and review only. It granted no implementation, test, pilot, credential, Keychain, browser, listener, SDK, network, Provider or runtime authority.

## 3.2 Published Version 1.0 — implementation phase

Canonical Version 1.0 publication requires one governance-only commit containing exactly:

1. `docs/governance/reviews/CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md`; and
2. `docs/indexes/DOCUMENT-REGISTER.md`.

The governance publication commit is separate from every implementation-stage commit. It contains no production, test or pilot file.

After Chief Architect approval, separate publication authority, commit and push, canonical Version 1.0 activates **Stage 1 only**. It authorizes:

1. changes only to the Stage 1 files in Section 14.2;
2. Stage 1 implementation of only the EDD-001 Version 1.1 component design;
3. Stage 1 fake-only offline tests and repository verification;
4. preparation of the Stage 1 evidence package, without commit or push; and
5. no work on Stages 2 through 6.

Published Version 1.0 still grants no Stage 2-6 authority, live credential use, Keychain access, listener creation, browser opening, real SDK client construction, Provider endpoint or runtime authority.

## 3.3 Separately instructed live pilot

A live pilot is unavailable by default. It requires prior canonical Chief Architect live-activation authority, every gate in Sections 16 and 17 and then an explicit Sponsor execution instruction identifying the frozen implementation commit, local non-production environment and exact permitted live operations. Sponsor instruction operates only inside already-approved Chief Architect authority and creates no live authority by itself.

The prior Chief Architect activation may permit one Authentication Attempt only. The later Sponsor instruction must initiate within that boundary and state separately whether one post-establishment `verify_provider_availability()` operation is included. If prior Chief Architect activation authority is absent, the Sponsor instruction must not be acted upon.

Success, failure, cancellation or timeout after live initiation consumes the one-attempt authority. A second attempt requires fresh authority.

# 4. Exact Authorized File Scope

No file outside this list may enter any governed publication or stage commit. Each stage commit is further limited to its exact Section 14.2 allocation.
The count of 32 includes both governance files. Every path belongs to exactly one category: 2 governance + 8 new production + 9 modified production + 8 new test + 4 modified test + 1 pilot GUI = 32.

## 4.1 Governance files

1. `docs/governance/reviews/CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md`
2. `docs/indexes/DOCUMENT-REGISTER.md`

## 4.2 New production files

1. `src/kronos/configuration/credentials.py`
2. `src/kronos/configuration/principals.py`
3. `src/kronos/configuration/apple_keychain.py`
4. `src/kronos/provider/models/authentication.py`
5. `src/kronos/provider/contracts/provider_authentication.py`
6. `src/kronos/provider/callbacks/__init__.py`
7. `src/kronos/provider/callbacks/loopback.py`
8. `src/kronos/provider/services/provider_authentication.py`

## 4.3 Existing production files authorized for bounded modification

1. `src/kronos/configuration/settings.py`
2. `src/kronos/configuration/loader.py`
3. `src/kronos/provider/adapters/kite/client.py`
4. `src/kronos/provider/adapters/kite/authentication.py`
5. `src/kronos/provider/kite/auth/kite_authentication.py`
6. `src/kronos/provider/kite/adapter/kite_provider.py`
7. `src/kronos/provider/contracts/authentication.py`
8. `src/kronos/provider/models/context.py`
9. `src/kronos/provider/services/access.py`

Each modification is limited to the responsibility assigned by EDD-001: Configuration references and protected custody; candidate and SDK containment; corrected authentication contracts; attempt orchestration; principal binding; atomic context establishment; separate availability verification; and local-only disposal.

## 4.4 New fake-only test files

1. `tests/unit/configuration/test_secure_credentials.py`
2. `tests/unit/configuration/test_intended_principal.py`
3. `tests/unit/configuration/test_apple_keychain.py`
4. `tests/unit/provider/test_authentication_attempt.py`
5. `tests/unit/provider/test_loopback_authentication_callback.py`
6. `tests/unit/provider/test_provider_authentication_service.py`
7. `tests/unit/provider/test_principal_binding.py`
8. `tests/unit/tools/test_car016_provider_authentication_gui.py`

## 4.5 Existing test files authorized for bounded modification

1. `tests/unit/provider/test_kite_authentication_adapter.py`
2. `tests/unit/provider/test_kite_edd001_authentication.py`
3. `tests/unit/provider/test_edd001_provider_access.py`
4. `tests/unit/configuration/test_kite_connectivity_settings.py`

## 4.6 Temporary pilot files

1. `tools/provider_pilots/car016_provider_authentication_gui.py`

No dependency, fixture, `.env`, screenshot, architecture, EDD or other governance change is authorized.

## 4.7 Modified-production path analysis

### `src/kronos/configuration/settings.py`

- **Existing responsibility:** immutable Provider settings and authentication/connectivity validation, including API key, API secret, access token and redirect URL fields.
- **EDD-001 gap:** A.8 and A.8.1 require protected one-operation API-secret custody and prohibit the normal Configuration object from carrying the secret into the new service; A.4 requires configuration meanings rather than storage mechanics.
- **Authorized modification:** add only the non-sensitive protected-credential and intended-principal references required by `ProviderAuthenticationConfiguration`; ensure the new authentication path cannot be satisfied by a plaintext secret field; preserve redacted representation.
- **Prohibited refactor:** no general Settings redesign, environment framework change, unrelated validation change or removal of legacy fields needed by unaffected paths.
- **Regression evidence:** existing configuration tests plus new assertions for redacted representations, reference validation, legacy-path stability and inability of plaintext secret configuration to satisfy CAR-016 authentication.

### `src/kronos/configuration/loader.py`

- **Existing responsibility:** loads supported environment-backed configuration values into `Settings`.
- **EDD-001 gap:** A.15 identifies the reachable `.env` API-secret compatibility path as a risk; A.8 requires the new authentication service to obtain the secret only through `SecureCredentialSource`.
- **Authorized modification:** prevent loader-supplied plaintext secret material from entering or satisfying the CAR-016 authentication composition while preserving unrelated loading behavior.
- **Prohibited refactor:** no new configuration source, dotenv replacement, global loader rewrite or change to unrelated environment keys.
- **Regression evidence:** loader tests proving unchanged non-authentication loading, no CAR-016 secret acquisition through `.env`, no secret in representations/errors and no new dependency.

### `src/kronos/provider/adapters/kite/client.py`

- **Existing responsibility:** contains Kite SDK handles for login URL, session exchange, profile probing and remote token invalidation.
- **EDD-001 gap:** A.9 requires an opaque candidate with no token/SDK getter and only principal verification before publication; A.11 requires local disposal and keeps remote invalidation unreachable from End KRONOS Session.
- **Authorized modification:** create or adapt candidate-local SDK containment, one session exchange, minimum `user_id` evidence translation, explicit availability verification support and local reference disposal; keep live operations uncallable without later authority.
- **Prohibited refactor:** no SDK replacement, transport change, retry, additional endpoint, public client/token getter or removal/repurposing of remote invalidation.
- **Regression evidence:** fake-client tests proving one exchange, one conditional profile operation per explicit action, candidate isolation, payload discard, local disposal, zero remote invalidation and sanitized exception translation.

### `src/kronos/provider/adapters/kite/authentication.py`

- **Existing responsibility:** translates Kite authentication operations and failures, retains a secret until exchange and creates context evidence.
- **EDD-001 gap:** A.4, A.8 and A.9 require one-use secret custody, a candidate rather than an active context after exchange, minimum principal evidence and fail-closed binding outcomes.
- **Authorized modification:** conform the adapter to `ProviderAuthenticationAdapter`, consume a `SecretLease` only during exchange, return an opaque candidate, translate only minimum principal evidence and provide local candidate disposal.
- **Prohibited refactor:** no orchestration ownership, UI/callback logic, Provider-neutral policy, alternate endpoint, retry or remote termination in the new lifecycle.
- **Regression evidence:** fake-adapter tests for secret use/release counts, exchange cardinality, candidate opacity, four binding outcomes, profile non-retention, controlled errors and local-only disposal.

### `src/kronos/provider/kite/auth/kite_authentication.py`

- **Existing responsibility:** coordinates the current synchronous Kite login flow, redirect parsing, secret use, context creation, immediate availability and expiry policy.
- **EDD-001 gap:** A.5-A.6 require a first-class attempt service; A.7 moves callback transport to the listener; A.12 separates attempt, context and availability; A.8 removes secret ownership from this class.
- **Authorized modification:** migrate existing entry points to the new service contracts, remove ownership of plaintext secret/redirect parsing/immediate availability, preserve only Kite-specific translation and next-06:00 Asia/Kolkata validity policy where applicable.
- **Prohibited refactor:** no second orchestration path, compatibility bypass, browser/listener ownership, automatic authentication, retry or platform-wide expiry rule.
- **Regression evidence:** migrated fake tests proving canonical attempt transitions, no immediate `AVAILABLE`, no retained secret, no duplicate exchange, adapter-supplied expiry and compatibility entry points cannot bypass the service.

### `src/kronos/provider/kite/adapter/kite_provider.py`

- **Existing responsibility:** exposes Kite Provider authentication, context validation/availability and termination behavior to the Provider boundary.
- **EDD-001 gap:** A.10 permits publication only after matched binding; A.12 requires explicit availability verification; A.11 requires End KRONOS Session to be local-only instead of remote token invalidation.
- **Authorized modification:** publish only a bound active context, route explicit availability verification separately, and route End KRONOS Session to local disposal.
- **Prohibited refactor:** no unrelated Provider operation change, capability expansion, automatic profile call, endpoint addition or change to remote invalidation as a separately named unreachable operation.
- **Regression evidence:** provider fake tests proving unmatched candidates never publish, initial `NOT_VERIFIED`, one explicit verification, context-expiry translation, local end, idempotence and zero Provider call on end.

### `src/kronos/provider/contracts/authentication.py`

- **Existing responsibility:** defines the current synchronous authentication Provider contract.
- **EDD-001 gap:** A.4 requires lifecycle methods and opaque handles/candidates; the synchronous contract cannot represent begin, callback completion, cancellation, separate verification or local session ending.
- **Authorized modification:** adapt or retire only the conflicting contract surface in favor of the EDD-001 typed provider-authentication contract while preserving unaffected consumers until migrated in-scope.
- **Prohibited refactor:** no broader Provider contract consolidation, public sensitive getter, raw exception surface or endpoint expansion.
- **Regression evidence:** contract/static tests proving canonical methods, opaque boundaries, no sensitive getters and no remaining in-scope caller using the superseded synchronous bypass.

### `src/kronos/provider/models/context.py`

- **Existing responsibility:** models authentication outcomes, context validity/provenance and Provider availability used by the current access path.
- **EDD-001 gap:** A.5 and A.12 require three independent models: terminal attempt, `ABSENT/ACTIVE/EXPIRED/ENDED` context and five-state availability; current models conflate these meanings.
- **Authorized modification:** align or bridge existing public context models to the canonical independent projections and sanitized provenance without storing candidate or principal material.
- **Prohibited refactor:** no domain expansion, general event redesign, payload persistence, Provider-specific expiry in provider-neutral types or change to unrelated models.
- **Regression evidence:** model tests for independent transitions, immutability of completed attempts, no universal 06:00 assumption, sanitized serialization and no sensitive fields.

### `src/kronos/provider/services/access.py`

- **Existing responsibility:** converts authentication results into the current Provider context and availability service state.
- **EDD-001 gap:** A.10 forbids establishment before `MATCHED`; A.12 requires a new active context to start `NOT_VERIFIED`; A.11 requires local-only ending.
- **Authorized modification:** require a succeeded attempt plus matched binding for atomic context establishment, maintain the independent availability projection, expose explicit verification and implement local End KRONOS Session semantics.
- **Prohibited refactor:** no authentication orchestration duplication, automatic availability call, retry, Provider-specific logic, remote invalidation or unrelated access-service redesign.
- **Regression evidence:** fake service tests for atomic matched publication, rejection/disposal of every non-match, initial `NOT_VERIFIED`, temporary failure preservation, authoritative expiry, idempotent local end and zero cleanup endpoint.

# 5. Authentication Attempt Implementation Scope

Implementation shall preserve these separate states exactly:

```text
CREATED
LISTENER_READY
BROWSER_OPEN_REQUESTED
AWAITING_CALLBACK
CALLBACK_ACCEPTED
EXCHANGING
BINDING_PRINCIPAL
SUCCEEDED
FAILED
CANCELLED
TIMED_OUT
```

`SUCCEEDED`, `FAILED`, `CANCELLED` and `TIMED_OUT` are terminal. At most one non-terminal attempt exists per Provider registration. Callback and request-token consumption are single-use. No terminal attempt reactivates. No automatic retry, repeat, polling, scheduling or reauthentication exists.

The implementation shall use an injectable cryptographically random identity source, aware clock, bounded deadline and process-scoped active-attempt registry. Sanitized attempt evidence retains no credential, token, account identifier, callback query, Provider payload or raw exception.

# 6. Loopback Callback Scope

The implementation boundary is exactly:

```text
Bind address: 127.0.0.1
Port: 8765
Path: /kite/callback
Method: GET
Canonical Host: 127.0.0.1:8765
```

The standard-library component shall:

- prove listener readiness before a browser-open request;
- bind no wildcard, hostname alias, alternate port or alternate path;
- require one safely parsed canonical Host header;
- accept one terminal request and at most one non-empty request token;
- reject wrong method, path, host, missing token, multiple token and duplicate requests;
- apply one bounded timeout;
- disable default HTTP request/error logging;
- never log headers, URLs, queries or peer details;
- return only fixed sanitized HTML with no reflected input; and
- close immediately on acceptance, rejection, timeout, cancellation or browser-open failure.

Version 1 first-request terminality is controlling: the first request reaching the listener terminates the attempt whether accepted or rejected. This sharply bounds listener lifetime but accepts a local denial-of-service risk from a malformed, accidental or malicious first request. No silent retry is authorized.

# 7. Secure Credential and Apple Keychain Scope

Implementation may create the provider-neutral `SecureCredentialSource` and single-operation `SecretLease` contracts plus one retrieval-only Apple Keychain backend.

The backend may use `/usr/bin/security find-generic-password` only through an argument vector with `shell=False`, bounded timeout, captured binary streams and no secret in arguments. It may retrieve but not create, update, enumerate or delete credentials. Result categories are limited to `FOUND`, `MISSING`, `ACCESS_DENIED`, `BACKEND_UNAVAILABLE`, `TIMED_OUT` and `MALFORMED`.

The API secret is excluded from normal UI, `.env`, source, fixtures, arguments, logs, screenshots, exceptions and retained state. Secret leases are redacted, non-serializable, one-use and released on every terminal path. No secure-memory-erasure claim is authorized.

# 8. Intended Principal Resolution and Custody

The internal Provider registration reference shall never be compared directly with raw Provider evidence.

`IntendedPrincipalResolver` may resolve the expected principal only through approved protected custody and a one-operation `IntendedPrincipalLease`. Outcomes are limited to `RESOLVED`, `NOT_FOUND`, `ACCESS_DENIED`, `BACKEND_UNAVAILABLE`, `INVALID_CONFIGURATION` and `SANITIZED_FAILURE`.

The expected principal is available only inside the binding operation. It has no public getter, representation, equality, sensitive hashing or serialization and is never stored on service, controller or view state. It is discarded immediately after comparison. Retained evidence contains only attempt ID, Provider identity, internal registration reference, binding result, timestamp and sanitized reason.

# 9. Candidate Provider Context Isolation

Token exchange produces only an opaque candidate Provider Context. It is unavailable to products, acquisition, trading and all general Provider operations. Its only permitted Provider operation is the separately bounded principal-verification operation.

The candidate has no public token or SDK getter and no reuse eligibility. Mismatch, unconfirmed evidence, verification unavailability, cancellation, timeout or any terminal failure requires immediate local disposal. No external candidate consumer is authorized.

# 10. Principal Binding and Fail-Closed Outcomes

The exact sequence is:

```text
one session exchange
    -> candidate Provider Context
    -> one minimum principal verification
    -> one protected intended-principal resolution
    -> one exact comparison
    -> binding result
    -> active authenticated context or local disposal
```

Kite principal verification may read only transient `user_id` from the profile mapping. Provider and expected values must be canonical strings matching the EDD-001 rule; comparison is exact and case-sensitive. Raw profile, raw principal and expected principal values are discarded immediately.

| Binding result | Attempt | Context | Availability | Required action |
|---|---|---|---|---|
| `MATCHED` | `SUCCEEDED` | `ACTIVE` | `NOT_VERIFIED` | atomic local establishment |
| `MISMATCHED` | `FAILED` | `ABSENT` | not established | candidate local disposal |
| `UNCONFIRMED` | `FAILED` | `ABSENT` | not established | candidate local disposal; no override |
| `UNAVAILABLE` | `FAILED` with `PRINCIPAL_BINDING_UNAVAILABLE` | `ABSENT` | not availability verification | candidate local disposal |

# 11. Authenticated Context and Availability Scope

Authenticated context states are `ABSENT`, `ACTIVE`, `EXPIRED` and `ENDED`. Only a `SUCCEEDED` attempt with `MATCHED` binding may atomically establish `ACTIVE`. Later context expiry or ending never changes the completed attempt.

Provider Availability is separate: `NOT_VERIFIED`, `VERIFYING`, `AVAILABLE`, `UNAVAILABLE` and `INDETERMINATE`. Every new active context starts `NOT_VERIFIED`. Principal binding cannot set availability.

Only a separate explicit `verify_provider_availability()` action may leave `NOT_VERIFIED`. Future canonical Chief Architect activation authority must include that operation before a Sponsor may instruct it; otherwise the control remains disabled. Sponsor instruction creates no endpoint authority. Temporary Provider failure changes availability only. Authoritative invalid-token evidence may expire the context but does not rewrite the completed attempt.

Kite next-06:00 Asia/Kolkata validity is adapter policy. No universal Provider expiry is authorized.

# 12. Local Cancellation and End KRONOS Session

`cancel_authentication_attempt()` is idempotent and local-only. It stops any listener, invalidates callback eligibility and transient token wrappers, releases credential/principal leases, disposes a candidate and rejects late callbacks. It makes no Provider call or remote token change.

End KRONOS Session moves an active context to `ENDED`, removes local reuse and releases local client/context references. It shall not call `invalidate_access_token()`, perform remote logout, revoke a token, retrieve credentials or automatically reauthenticate.

# 13. Temporary tkinter Pilot Scope

The pilot is temporary and local. Reusable authentication logic remains tkinter-independent.

Importing the module, constructing the controller and opening the GUI perform zero credential, Keychain, browser, listener, SDK, network or Provider activity. Before separately authorized live activation the view is inspection-only.

The view may display only:

- **Login to Kite**;
- sanitized attempt and context state;
- sanitized Provider Availability;
- **Cancel**;
- **Verify Provider Availability**, disabled unless separately authorized and context-active;
- **End KRONOS Session**; and
- sanitized terminal evidence.

It shall contain no API key, API secret, intended-principal, request-token, access-token, password, PIN or TOTP field. No URL, query, payload, principal, account identifier, SDK exception or traceback is displayed or printed.

GUI close with a non-terminal attempt invokes local cancellation before close. Closing with no active attempt or a terminal attempt causes no lifecycle mutation.

# 14. Fake-Only Offline Test Matrix

All tests use deterministic fakes, synthetic sensitive markers and injected clocks/identities. Tests access no real Keychain, browser, SDK, external network or Provider endpoint.

The matrix shall prove:

1. zero activity on import, controller construction and GUI opening;
2. exact attempt transitions, terminal enforcement and registration exclusion;
3. listener readiness before browser request;
4. exact loopback address, port, path, GET and Host validation through fakes and handler-level synthetic requests;
5. first-request terminality, invalid-first-request denial, duplicate rejection and bounded timeout;
6. no HTTP, URL, query, header or sensitive logging;
7. browser-open failure selects local cancellation and closes listener state;
8. fake Keychain success and every sanitized retrieval failure;
9. exactly one secret acquisition/use/release and no retained secret;
10. exactly one request-token acceptance/use/invalidation and no retained token;
11. intended-principal resolution outcomes, one-use lease and no expected-principal retention;
12. one exchange and candidate isolation;
13. `MATCHED`, `MISMATCHED`, `UNCONFIRMED` and fail-closed `UNAVAILABLE`;
14. raw profile/principal disposal and sanitized retained evidence;
15. successful attempt `SUCCEEDED`, context `ACTIVE` and availability `NOT_VERIFIED`;
16. explicit availability verification only, with no effect on the completed attempt;
17. invalid-token context expiry versus ordinary Provider Unavailability;
18. cancellation before listener, during wait, after callback and with a candidate;
19. idempotent cancellation, late-callback rejection and zero Provider cleanup call;
20. local End KRONOS Session and no remote invalidation;
21. Kite-supplied next-06:00 policy and no platform-wide 06:00 assumption;
22. redacted `repr`, `str`, serialization, exceptions, logs, stdout and stderr;
23. no public credential, token, principal, candidate or SDK getter;
24. no retry, polling, scheduling or alternate endpoint;
25. authorized-file import and dependency boundaries; and
26. the complete offline suite remains green.

## 14.1 Test authority is not live authority

### Credential tests

Authorized: fake credential sources, fake `SecretLease` objects, synthetic secret markers, an injected subprocess runner and exact command-vector assertions.

Not authorized: real Apple Keychain access; reading, writing, updating, enumerating or deleting any real credential; or executing real `/usr/bin/security` against user storage.

### Callback tests

Authorized: handler-level synthetic requests; injected socket/server fakes; and bounded test-only loopback fixtures on test-controlled ephemeral ports where repository tests require real socket semantics, provided they perform no external or live authentication activity and remain within EDD-001.

Not authorized: activation of production callback port `8765`; a listener waiting for real browser activity; acceptance of a real Kite redirect; external authentication activity; or any Provider callback.

### Browser tests

Authorized: an injected browser-opener fake and assertions about readiness/open-request ordering and sanitized failure handling.

Not authorized: opening the real default browser, navigating to Kite or conducting real login activity.

### SDK tests

Authorized: fake SDK handles/clients and synthetic responses/exceptions.

Not authorized: constructing a real Kite SDK client or making any SDK request.

### Profile implementation

Authorized: adapter implementation, fake profile-response handling and sanitized principal/availability projections.

Not authorized: a live `profile()` invocation or any Provider endpoint access.

Passing any test creates no credential, Keychain, browser, listener, SDK, endpoint, runtime or live authority.

## 14.2 Controlled sequential implementation stages

The two governance files in Section 4.1 are authority-package files, not implementation-stage files. After Version 1.0 publication, CAR-016 Version 1.0 and its Document Register row are frozen throughout Stages 1-6. Neither governance file may be amended in a stage commit. Versions 1.1, 1.2 and 1.3 may be prepared only through separately authorized documentation revisions after their applicable lifecycle gates.

The remaining 30 paths are allocated below. Stages are strictly sequential and parallel work is not authorized. Engineering must not implement all 30 implementation/test paths in one uncommitted candidate. Only the currently authorized stage may be implemented; later-stage files remain unchanged until explicit Engineering Architect stage-start authority is granted. No stage may begin from an unreviewed or dirty baseline.

Every stage gate requires, at minimum: the complete stage diff; exact changed-file list; path-specific EDD-001 mapping; focused fake-only results; redaction and non-retention evidence; proof of no unauthorized import or dependency; secret and sensitive-material scans; confirmation of no credential, Keychain, real browser, live listener, real SDK, network or Provider activity; and confirmation that no file outside the stage scope changed. Any missing evidence stops the stage.

Every stage also requires the complete offline regression suite, `git diff --check`, exact stage-scope validation, dependency-manifest comparison, prohibited-import checks and static scans for sensitive getters, retry/polling/scheduling, remote invalidation and unauthorized endpoints. Exactly one reviewed commit and one authorized push are required for each stage.

The four controlled actions are separate:

1. **Stage evidence acceptance:** confirms that the uncommitted candidate satisfies the stage gate; creates no commit, push or next-stage authority.
2. **Commit authority:** authorizes exactly one stage commit containing only the accepted files and approved message.
3. **Push authority:** authorizes pushing that accepted stage commit to `origin/develop`.
4. **Next-stage authority:** after the push is verified and its SHA frozen, explicitly authorizes work on the next stage from that clean accepted SHA.

No one action implies another. A proposed commit message grants no commit authority. Each later stage requires acceptance of the prior stage, separate commit authority, separate push authority, the pushed commit SHA as its frozen baseline and explicit Engineering Architect next-stage authority before work begins.

### Stage 1 — Provider-neutral foundations

**Objective:** establish the provider-neutral types, contracts, one-use custody boundaries and three independent state models without concrete external-effect behavior.

**Required starting baseline:** the clean, published CAR-016 Version 1.0 commit synchronized between local `develop` and `origin/develop` (`CAR016_V1_0_SHA`).

**Permitted files:**

- `src/kronos/configuration/credentials.py`
- `src/kronos/configuration/principals.py`
- `src/kronos/provider/models/authentication.py`
- `src/kronos/provider/contracts/provider_authentication.py`
- `src/kronos/provider/models/context.py`
- `tests/unit/configuration/test_secure_credentials.py`
- `tests/unit/configuration/test_intended_principal.py`
- `tests/unit/provider/test_authentication_attempt.py`

**Design outcomes:** EDD-001 A.4 typed boundaries; A.5 terminal attempt aggregate; A.8.1 redacted one-use leases; A.9 intended-principal custody; A.12 independent attempt/context/availability projections. No concrete Provider, storage or transport behavior.

**Permitted changes:** only the listed provider-neutral models, protocols, leases and focused fake tests needed for those outcomes.

**Fake-only tests:** deterministic attempt transitions; one-use/close behavior for fake secret and principal leases; redacted `repr`/`str`; serialization rejection; opaque handles/candidates; independent state projections; no public sensitive getter.

**Prohibited activity:** no Keychain subprocess, listener/socket, browser, Kite import, SDK construction, Provider call, integration wiring, GUI or dependency change.

**Completion evidence:** focused results for the three Stage 1 test files, type/import-boundary evidence, reachable-state non-retention checks and the common gate evidence above.

**Full regression checks:** complete offline suite, repository documentation checks, local-link checks and existing context/authentication regression tests.

**Static safety checks:** provider-neutral modules import no Kite SDK or tkinter; no token/secret/principal/SDK/candidate getter; no serialization; no retry, polling, scheduling, endpoint or dependency change.

**EA review gate:** the Engineering Architect must explicitly accept Stage 1 evidence before Stage 2 begins. No commit or push is authorized.

**Proposed commit message:** `feat(authentication): add provider-neutral authentication foundations`

**Push condition:** only after Stage 1 evidence acceptance, separate commit authority for exactly one Stage 1 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes `STAGE_1_SHA`; Stage 2 remains unauthorized until the push is verified and the Engineering Architect grants explicit Stage 2 start authority from clean aligned `STAGE_1_SHA`.

**Stop conditions:** any Provider-specific policy entering foundations, sensitive value becoming observable/serializable, inability to keep the three state models independent, or any out-of-stage file need.

### Stage 2 — Callback and credential infrastructure

**Objective:** implement the exact loopback callback transport and retrieval-only credential backend through injected, offline-testable boundaries.

**Required starting baseline:** clean local/origin `develop` alignment at accepted pushed `STAGE_1_SHA`, plus explicit Engineering Architect Stage 2 start authority.

**Permitted files:**

- `src/kronos/configuration/apple_keychain.py`
- `src/kronos/provider/callbacks/__init__.py`
- `src/kronos/provider/callbacks/loopback.py`
- `src/kronos/configuration/settings.py`
- `src/kronos/configuration/loader.py`
- `tests/unit/configuration/test_apple_keychain.py`
- `tests/unit/provider/test_loopback_authentication_callback.py`
- `tests/unit/configuration/test_kite_connectivity_settings.py`

**Design outcomes:** EDD-001 A.7 exact loopback acceptance and first-request terminality; A.8 retrieval-only injected Keychain backend; A.8.1 secret redaction/non-retention; A.15 closure of the `.env` secret compatibility path for CAR-016.

**Permitted changes:** only the listed callback, credential-backend, configuration-reference and focused-test changes required for those outcomes.

**Fake-only tests:** injected subprocess outcomes and exact argv/`shell=False`/timeout assertions; no diagnostic retention; synthetic handler requests for method/path/Host/token/cardinality/timeout/cancellation; no HTTP logging; loader/reference regression tests. Deterministic loopback fixtures are allowed only without external authentication or browser use.

**Prohibited activity:** no real `/usr/bin/security`, real credential, live authentication listener, real redirect, browser, SDK, Provider request, settings redesign or dependency change.

**Completion evidence:** focused results for all three Stage 2 tests, listener cleanup evidence for every terminal branch, command-vector evidence and the common gate evidence.

**Full regression checks:** complete offline suite, configuration regressions, documentation checks and local-link checks.

**Static safety checks:** no real subprocess execution; exact injected argv with `shell=False`; no default HTTP logging; no wildcard bind/alternate path; no `.env` secret use in CAR-016; no new dependency/import.

**EA review gate:** explicit Stage 2 evidence acceptance is required before Stage 3. No commit or push is authorized.

**Proposed commit message:** `feat(authentication): add callback and secure credential infrastructure`

**Push condition:** only after Stage 2 evidence acceptance, separate commit authority for exactly one Stage 2 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes `STAGE_2_SHA`; Stage 3 remains unauthorized until the push is verified and the Engineering Architect grants explicit Stage 3 start authority from clean aligned `STAGE_2_SHA`.

**Stop conditions:** real protected-store access is needed; callback controls cannot be proven with fakes; a listener persists beyond a fixture; secret/query/header material appears; or an out-of-stage file/dependency is needed.

### Stage 3 — Kite adapter conformance

**Objective:** make Kite exchange, candidate containment, principal evidence and availability verification conform to EDD-001 while retaining SDK mechanics inside the adapter.

**Required starting baseline:** clean local/origin `develop` alignment at accepted pushed `STAGE_2_SHA`, plus explicit Engineering Architect Stage 3 start authority.

**Permitted files:**

- `src/kronos/provider/adapters/kite/client.py`
- `src/kronos/provider/adapters/kite/authentication.py`
- `tests/unit/provider/test_kite_authentication_adapter.py`

**Design outcomes:** EDD-001 A.9 one exchange to opaque candidate, minimum transient `user_id` evidence, fail-closed binding translation, separate explicit availability translation and local candidate disposal; A.11 no remote invalidation from local cleanup.

**Permitted changes:** only the listed Kite client/adapter containment, translation and fake-adapter regression changes.

**Fake-only tests:** fake SDK construction handles only; one exchange; candidate opacity; one profile call only per explicitly invoked fake operation; four binding outcomes; exact canonical comparison inputs; payload/principal discard; controlled errors; zero retry, alternate endpoint or remote invalidation.

**Prohibited activity:** no real SDK client, network/Provider call, browser/listener, secret store, transport change, retry, new endpoint or unrelated adapter refactor.

**Completion evidence:** focused adapter results, endpoint-call counters, fake payload reachability/non-retention evidence and the common gate evidence.

**Full regression checks:** complete offline suite, existing Kite adapter error-mapping regressions, documentation checks and local-link checks.

**Static safety checks:** fake SDK construction only; no public SDK/token/candidate getter; no retry or alternate endpoint; no transport modification; no remote invalidation from local disposal; no dependency change.

**EA review gate:** explicit Stage 3 evidence acceptance is required before Stage 4. No commit or push is authorized.

**Proposed commit message:** `feat(authentication): conform Kite authentication adapter`

**Push condition:** only after Stage 3 evidence acceptance, separate commit authority for exactly one Stage 3 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes `STAGE_3_SHA`; Stage 4 remains unauthorized until the push is verified and the Engineering Architect grants explicit Stage 4 start authority from clean aligned `STAGE_3_SHA`.

**Stop conditions:** candidate isolation requires a public token/client getter; SDK behavior requires transport instrumentation; any live call is needed; another endpoint/refactor is required; or sanitized translation cannot be proven.

### Stage 4 — Service integration

**Objective:** establish the sole provider-neutral lifecycle coordinator, protected binding, atomic matched-context publication, explicit availability verification and local cleanup semantics.

**Required starting baseline:** clean local/origin `develop` alignment at accepted pushed `STAGE_3_SHA`, plus explicit Engineering Architect Stage 4 start authority.

**Permitted files:**

- `src/kronos/provider/services/provider_authentication.py`
- `src/kronos/provider/services/access.py`
- `tests/unit/provider/test_provider_authentication_service.py`
- `tests/unit/provider/test_principal_binding.py`
- `tests/unit/provider/test_edd001_provider_access.py`

**Design outcomes:** EDD-001 A.5-A.6 sole lifecycle coordination; A.9 protected exact binding; A.10 atomic matched-only context establishment; A.11 cancellation/end local disposal; A.12 separate explicit availability verification.

**Permitted changes:** only the listed service/access orchestration and focused fake-test changes required for those outcomes.

**Fake-only tests:** complete state/precedence table; readiness-before-open with fake navigator; one callback/token/exchange/binding; all credential/resolver failures; matched-only publication; cancellation in every phase; late callback rejection; explicit availability projections; authoritative expiry; local end and zero Provider cleanup call.

**Prohibited activity:** no concrete Keychain/browser/listener/SDK, real credential/network, UI behavior, retry, polling, remote invalidation or alternate Provider endpoint.

**Completion evidence:** focused service/access/binding results, orchestration cardinality evidence, terminal-path lease/token/candidate cleanup and the common gate evidence.

**Full regression checks:** complete offline suite, existing Provider access/context regressions, documentation checks and local-link checks.

**Static safety checks:** one lifecycle coordinator; no sensitive/candidate getter; no direct exchange-to-context establishment; no automatic availability call; no retry/polling; no remote cleanup call; no dependency change.

**EA review gate:** explicit Stage 4 evidence acceptance is required before Stage 5. No commit or push is authorized.

**Proposed commit message:** `feat(authentication): integrate authenticated context service`

**Push condition:** only after Stage 4 evidence acceptance, separate commit authority for exactly one Stage 4 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes `STAGE_4_SHA`; Stage 5 remains unauthorized until the push is verified and the Engineering Architect grants explicit Stage 5 start authority from clean aligned `STAGE_4_SHA`.

**Stop conditions:** service must expose sensitive/candidate state, cannot establish atomically, conflates availability with binding, invokes cleanup remotely, or requires an out-of-stage contract.

### Stage 5 — Existing-path migration

**Objective:** remove the supported synchronous bypass by routing supported production entry points through the authoritative service without changing unrelated compatibility behavior.

**Required starting baseline:** clean local/origin `develop` alignment at accepted pushed `STAGE_4_SHA`, plus explicit Engineering Architect Stage 5 start authority.

**Permitted files:**

- `src/kronos/provider/kite/auth/kite_authentication.py`
- `src/kronos/provider/kite/adapter/kite_provider.py`
- `src/kronos/provider/contracts/authentication.py`
- `tests/unit/provider/test_kite_edd001_authentication.py`

**Design outcomes:** remove the in-scope synchronous bypass; route existing entry points through the accepted service/contracts; retain Kite-specific expiry policy; expose bound context, explicit verification and local End KRONOS Session only as EDD-001 A.4, A.10-A.12 require.

**Permitted changes:** only the listed supported-entry-point, Provider adapter, superseded-contract and focused migration-test changes required to eliminate the bypass.

**Fake-only tests:** migrated caller behavior; no duplicate orchestration; no immediate availability; next-06:00 adapter policy; explicit verification only; local end idempotence; no remote logout; no superseded contract route remaining in scope.

**Prohibited activity:** no unrelated Provider refactor, new compatibility wrapper that preserves the bypass, endpoint expansion, real SDK/network, architecture/EDD amendment or dependency change.

**Completion evidence:** focused migration tests, static call-path evidence, full offline suite at the stage boundary and the common gate evidence.

**Full regression checks:** complete offline suite, all legacy authentication/access tests, unrelated Kite compatibility regressions, documentation checks and local-link checks.

**Static safety checks:** one supported public authentication path; no direct exchange-to-context call; no immediate `AVAILABLE`; no remote-invalidating End KRONOS Session; no legacy principal-binding bypass; no dependency or endpoint expansion.

**EA review gate:** explicit Stage 5 evidence acceptance is required before Stage 6. No commit or push is authorized.

**Proposed commit message:** `refactor(authentication): migrate to authoritative authentication service`

**Push condition:** only after Stage 5 evidence acceptance, separate commit authority for exactly one Stage 5 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes `STAGE_5_SHA`; Stage 6 remains unauthorized until the push is verified and the Engineering Architect grants explicit Stage 6 start authority from clean aligned `STAGE_5_SHA`.

**Stop conditions:** an existing public path cannot conform within its bounded responsibility, unrelated Provider behavior must change, or both old and new authentication paths remain reachable.

### Stage 6 — Pilot GUI

**Objective:** add the inspection-safe temporary tkinter pilot as a thin sanitized presentation over the accepted service seams.

**Required starting baseline:** clean local/origin `develop` alignment at accepted pushed `STAGE_5_SHA`, plus explicit Engineering Architect Stage 6 start authority.

**Permitted files:**

- `tools/provider_pilots/car016_provider_authentication_gui.py`
- `tests/unit/tools/test_car016_provider_authentication_gui.py`

**Design outcomes:** EDD-001 A.12.1 thin tkinter-independent-controller boundary; inspection-safe view; explicit actions; sanitized projections; deterministic local cancel-on-close; no sensitive input/display.

**Permitted changes:** only the listed pilot GUI and its new fake-only test file.

**Fake-only tests:** zero activity on import/controller/view opening; injected controller/service/browser seams; action ordering; disabled availability control without authority/active context; close/cancel behavior; one-attempt UI lockout; no raw output, URL, principal, payload, exception or credential field.

**Prohibited activity:** no real GUI live activation, browser, listener, Keychain, credential, SDK, network, Provider call, production GUI framework or reusable authentication logic in the pilot file.

**Completion evidence:** focused GUI results, widget/content inspection, fake call counters, the exact Stage 6 diff, complete offline suite and the common gate evidence.

**Full regression checks:** complete offline suite, all Stage 1-5 focused suites, documentation checks and local-link checks.

**Static safety checks:** import/construction/launch produce zero effects; no sensitive field/output; Login unavailable without an explicitly injected fake seam before live authority; no production tkinter import; no retry, second attempt or dependency change.

**EA review gate:** explicit Stage 6 evidence acceptance is required before any commit action. Acceptance alone authorizes neither commit nor push.

**Proposed commit message:** `feat(provider-pilot): add CAR-016 authentication pilot`

**Push condition:** only after Stage 6 evidence acceptance, separate commit authority for exactly one Stage 6 commit, and separate push authority for that accepted commit.

**Resulting SHA rule:** the accepted pushed commit becomes the frozen `STAGE_6_IMPLEMENTATION_SHA`; no live preflight may use another SHA.

**Stop conditions:** opening/constructing the GUI causes activity, sensitive data can enter presentation state, a second attempt is reachable, reusable logic is GUI-bound, or any out-of-stage file is needed.

### Cross-stage amendment rule

No later stage is authorized to amend a path allocated to an earlier stage. The allocation is intentionally single-owner by stage. If integration proves that a later stage must change an earlier-stage file, work stops and the Engineering Architect must issue a revised allocation, starting-SHA and review instruction. No such cross-stage amendment is pre-authorized.

## 14.3 Controlled baseline and SHA chain

```text
CAR016_V1_0_SHA
    -> accepted STAGE_1_SHA
    -> accepted STAGE_2_SHA
    -> accepted STAGE_3_SHA
    -> accepted STAGE_4_SHA
    -> accepted STAGE_5_SHA
    -> frozen STAGE_6_IMPLEMENTATION_SHA
```

`CAR016_V1_0_SHA` is the canonical governance-only publication commit containing exactly the two governance files and no implementation-stage file. Each later symbol is exactly one stage commit produced only after evidence acceptance and separate commit authority, then pushed only after separate push authority. Local `develop`, `origin/develop` and the working tree must be clean and aligned at the preceding accepted pushed SHA, and the Engineering Architect must grant explicit next-stage authority, before work begins. An uncommitted, unreviewed, rebased, amended or divergent baseline cannot enter the chain.

## 14.4 Authoritative path and dual-path removal

The final supported production path is exactly:

```text
Provider Authentication Service
    -> Authentication Attempt
    -> callback acceptance
    -> bounded secret retrieval
    -> Kite exchange
    -> candidate Provider Context
    -> principal binding
    -> authenticated Provider Context
    -> explicit Provider Availability verification
```

The existing synchronous path shall delegate to the authoritative service where compatibility requires a supported entry point, or become unreachable from supported production entry points. Compatibility behavior unrelated to CAR-016 shall not be deleted.

Exact migration responsibilities and regression evidence are:

- `src/kronos/provider/kite/auth/kite_authentication.py` and `tests/unit/provider/test_kite_edd001_authentication.py`: remove synchronous lifecycle ownership and prove supported callers delegate once to the service; no immediate exchange-to-context path remains.
- `src/kronos/provider/kite/adapter/kite_provider.py` and `tests/unit/provider/test_kite_edd001_authentication.py`: publish only a matched context, begin at `NOT_VERIFIED`, require explicit verification, and prove no immediate availability-`AVAILABLE` path remains.
- `src/kronos/provider/services/access.py` and `tests/unit/provider/test_edd001_provider_access.py`: reject direct establishment from exchange success, require `SUCCEEDED` plus `MATCHED`, and prove no legacy caller bypasses principal binding.
- `src/kronos/provider/contracts/authentication.py` and `tests/unit/provider/test_kite_edd001_authentication.py`: retire or adapt the conflicting supported contract and prove no second public authentication route remains.
- `src/kronos/provider/adapters/kite/client.py`, `src/kronos/provider/adapters/kite/authentication.py`, `src/kronos/provider/kite/adapter/kite_provider.py` and `tests/unit/provider/test_kite_authentication_adapter.py`: separate local disposal from the existing remote invalidation operation and prove End KRONOS Session invokes no remote invalidation or Provider endpoint.

Static call-graph/import scans plus focused fake call counters shall prove there is one supported public path, one exchange, one principal-binding verification, no context before match, no automatic availability verification and no remote call during cancellation or End KRONOS Session.

If the dual path cannot be eliminated within these exact files and responsibilities, Stage 5 stops and escalates. A wrapper that leaves the bypass reachable is insufficient.

## 14.5 Runtime-inert dependency-injection controls

Every external-effect boundary shall accept dependency injection or an equivalent deterministic test seam for:

1. aware clock;
2. cryptographically random attempt identity;
3. secure credential source;
4. intended-principal resolver;
5. subprocess runner;
6. listener/server factory;
7. callback transport;
8. browser opener;
9. Kite SDK/client handle;
10. session exchange;
11. principal verifier; and
12. Provider availability verifier.

Offline tests may use only fakes, synthetic markers/requests/responses and bounded fixtures. No offline test may cross a real external-effect boundary. No dependency addition, removal or version change is authorized.

Implementation of executable login, exchange, callback, browser, Keychain or profile code remains runtime-inert: its existence and passing tests create no authority to activate it.

## 14.6 Pilot GUI inspection safety

Under Version 1.0, direct import, controller/view construction and ordinary launch of `tools/provider_pilots/car016_provider_authentication_gui.py` are inspection-only. Live controls are disabled and no real composition root is constructed. These actions shall cause zero credential access, Keychain backend construction or access, production callback-listener construction, real browser-opener construction or invocation, real SDK/client construction, network activity or Provider endpoint call.

Before later live activation, Login remains unavailable in ordinary direct launch. Functional interaction is permitted only through explicitly injected fake seams in offline tests. The GUI contains no credential, principal, token, PIN, password or TOTP field and displays only sanitized state. Static inspection and fake call counters shall prove these invariants.

## 14.7 Live authority under Version 1.0

All live authority under CAR-016 Version 1.0 publication is **NONE**.

- Executable login code creates no login authority.
- Executable session-exchange code creates no exchange authority.
- Executable callback code creates no listener authority.
- Executable browser code creates no browser authority.
- Executable Keychain code creates no credential authority.
- Executable profile-adapter code creates no profile endpoint authority.
- Passing tests creates no runtime authority.
- Publication creates no live authority.
- Sponsor instruction creates no live authority.
- No Provider endpoint may be called without prior canonical Chief Architect live-activation authority, an approved frozen implementation SHA, successful governed preflight, exact redirect-registration confirmation, satisfied credential/intended-principal custody gates and then an explicit Sponsor instruction within that authority.

## 14.8 Mandatory stop-and-escalate rule

Engineering shall stop immediately and escalate to the Engineering Architect if:

1. any file outside Section 4 is required or changed;
2. any path classification changes;
3. any stage requires a path not allocated to it;
4. any architecture or EDD amendment is needed;
5. any dependency addition, removal or version change is needed;
6. any public-contract expansion beyond EDD-001 Version 1.1 is required;
7. any live access is required;
8. any unrelated Provider refactor is encountered;
9. dual-path removal cannot be achieved within scope;
10. any test requires a real Keychain, browser, listener, SDK client, network or Provider endpoint;
11. any credential, token, principal or callback material appears in logs, exceptions, diffs or test output;
12. any stage cannot be independently reviewed; or
13. CAR-014 or any unrelated authority would be affected.

No engineer may widen scope implicitly. No later stage may begin after a stop condition without a new written Engineering Architect disposition.

# 15. External Kite Redirect Confirmation Gate

No live listener, browser navigation or authentication may occur until the Sponsor supplies a non-sensitive, independently recorded confirmation that the intended official Kite application registration accepts exactly:

```text
http://127.0.0.1:8765/kite/callback
```

The confirmation must identify the Kite application registration through an approved non-sensitive internal reference and confirm exact scheme, host, port and path. It must not contain an API key, API secret, request token, access token, account identifier, screenshot with credentials or Provider response.

Repository inference, Configuration defaults, local code, a successful bind or a generated login URL cannot satisfy this gate. If exact redirect registration cannot be proven, live execution is prohibited and must be escalated.

# 16. Live Preflight and Sponsor Gate

Before any Sponsor execution instruction can be acted upon, all of the following must be proven at one exact published SHA:

1. canonical Chief Architect live-activation authority exists through CAR-016 Version 1.2 and is synchronized to `origin/develop` after Version 1.1 recorded accepted EDD conformance at `STAGE_6_IMPLEMENTATION_SHA`;
2. only authorized implementation files were published through the accepted six-stage SHA chain;
3. working tree is clean and local/origin develop align;
4. focused and complete offline tests pass;
5. secret, sensitive-material, dependency and prohibited-endpoint scans pass;
6. external Kite redirect confirmation in Section 15 is current;
7. intended principal and API secret protected-custody entries are confirmed available without exposing them;
8. the environment is Sponsor-controlled local non-production macOS;
9. no capture, proxy, inspection or diagnostic tool retains sensitive requests or callback queries;
10. CAR-014 remains unexecuted;
11. no prior CAR-016 live attempt has begun; and
12. the Sponsor issues a new explicit instruction freezing the environment, SHA, one-attempt boundary and whether availability verification is included.

The Sponsor instruction is last in this chain and creates no live authority. If prior canonical Chief Architect activation is absent, it must not be acted upon. Failure of any condition returns a preflight blocker and causes no live activity.

# 17. Future Live Attempt Boundary

Only after canonical Chief Architect activation, frozen-SHA approval, successful preflight, exact redirect confirmation, custody gates and a Sponsor instruction within that authority may one live attempt begin. It is consumed when `begin_login()` reserves the Authentication Attempt and listener construction starts. Success, failure, cancellation, timeout, listener failure, browser failure, credential failure, exchange failure, principal failure or local cleanup failure consumes the attempt.

The separately authorized path may contain at most:

1. one listener start;
2. one official login URL generation;
3. one browser-open request to the official Provider login flow;
4. one terminal callback;
5. one Keychain API-secret retrieval;
6. one intended-principal resolution;
7. one request-token exchange;
8. one principal `profile()` verification;
9. one atomic local context establishment on match;
10. at most one additional `profile()` operation only when the Sponsor instruction explicitly authorizes availability verification; and
11. local cancellation or End KRONOS Session cleanup without Provider mutation.

There is no retry, corrected credential, second browser flow, second callback attempt, token refresh, remote invalidation or automatic reauthentication. A failed or cancelled attempt stops. Fresh authority is required for any later attempt.

# 18. Explicitly Withheld Authority

CAR-016 Version 1.0 withholds:

- all live authority; Sponsor instruction cannot activate Version 1.0;
- all real credential access and use;
- all real Apple Keychain access and real `/usr/bin/security` execution against user storage;
- all real browser opening and Kite navigation;
- all live authentication listener and real callback acceptance;
- all real SDK client construction, request-token exchange and profile invocation;
- all external network authentication and runtime authentication;
- all Provider endpoints except the exact future operations expressly frozen by that instruction;
- a default post-establishment availability call;
- every public token, secret, principal, candidate and SDK-client getter;
- request-token refresh, access-token refresh, token invalidation and remote logout;
- Instrument Master and historical data;
- quote, LTP, OHLC and WebSocket/streaming;
- orders, trades, holdings, positions, funds, margins, GTT and all Provider mutation;
- persistence of secrets, tokens, principal values, profile payloads or account identifiers;
- Provider Catalogue, Instrument, Observation, Market Fact or Validation output;
- production GUI, background service, polling, scheduling or automatic repetition;
- a second Authentication Attempt;
- architecture or EDD amendment;
- CAR-014 execution; and
- production deployment or general runtime authority.

# 19. Pre-Commit Review Gate

Before any implementation commit, Engineering shall return to the Engineering Architect:

1. starting branch and SHA;
2. complete diff;
3. exact changed-file list and authorization mapping;
4. focused test results;
5. complete offline-suite result;
6. documentation and local-link results;
7. state-transition and endpoint-count evidence;
8. redaction and non-retention evidence;
9. secret, credential, sensitive-material and prohibited-payload scans;
10. confirmation of no credentials, Keychain, real browser, real listener, real SDK, external network or Provider activity;
11. confirmation CAR-014 remains unexecuted; and
12. confirmation no live authority has been inferred.

Engineering shall not commit or push until the Engineering Architect explicitly accepts the current stage evidence. Evidence acceptance creates neither authority. The Engineering Architect must then separately grant commit authority for exactly one stage commit with the confirmed files/message and separately grant push authority for that accepted commit. Next-stage work requires a fourth explicit authority after the pushed SHA is verified and frozen. No general publication or later-stage authority is inferred from this Draft.

# 20. Publication and Runtime Separation

Version 1.0 publication is one governance-only commit containing exactly CAR-016 and the Document Register. It is separate from all implementation commits and activates Stage 1 only.

Each of Stages 1-6 requires exactly one separately reviewed commit and one separately authorized push. No stage commit contains either governance file or files from another stage. Stage 2-6 work requires explicit next-stage authority after the preceding pushed SHA is verified and frozen.

Publication does not access credentials, use Keychain, start a production listener, open a real browser, construct a real SDK client, make a Provider call or consume the live attempt.

The governance phases are distinct: this Draft authorizes documentation review only; published Version 1.0 activates Stage 1 implementation and fake-only tests only; evidence acceptance, commit authority, push authority and next-stage authority are four separate actions; Version 1.1 records completed implementation without live authority; Version 1.2 may provide canonical Chief Architect live activation; Sponsor instruction may then initiate only within that existing authority; and Version 1.3 records the sanitized outcome. None is implied by another.

# 21. Outcome and Consumption Record

The controlled CAR-016 revision lifecycle is:

- **Version 1.0:** canonical sequential implementation and fake-only offline-test governance. Publication activates Stage 1 only; Stages 2-6 each require explicit next-stage authority after the preceding accepted push. It grants no live authority.
- **Version 1.1:** completed implementation and EDD-001 conformance record at the frozen `STAGE_6_IMPLEMENTATION_SHA`. It grants no live authority.
- **Version 1.2:** possible live-activation authorization only after Version 1.1 approval, exact redirect-registration confirmation, frozen implementation SHA, clean preflight, protected credential/intended-principal custody availability and separate Chief Architect and Sponsor approval.
- **Version 1.3:** sanitized consumed-outcome record after the one authorized live attempt.

Every revision requires its own governed review and publication authority. No revision authorizes retry unless it states that authority explicitly. A failed, cancelled or timed-out future live attempt consumes the one-attempt authority. A later attempt requires fresh Chief Architect and Sponsor authority.

No raw credential, request token, access token, intended principal, Provider principal, profile payload, account identifier, callback URL/query, header, SDK exception, Provider exception or traceback may be retained.

# 22. Canonical Disposition

**CAR-016 Status:** Approved — Canonical

**Implementation Authority:** Stage 1 Authorized with Constraints

**Runtime Authority:** None

**Credential-Use Authority:** None

**Keychain Authority:** None

**Browser/Listener Authority:** None

**SDK/Provider Endpoint Authority:** None

**CAR-014 Status:** Unexecuted

## Related Authority

- [ADR-010 Version 1.0](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md)
- [DOMAIN-006 Version 1.1](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [EDD-001 Version 1.1](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md)
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
