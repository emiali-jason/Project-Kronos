# EDD-001 — Provider Authentication and Authenticated Context Establishment Engineering Design

**Document ID:** EDD-001
**Title:** Provider Authentication and Authenticated Context Establishment Engineering Design
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Engineering Design Document
**Owner:** Engineering Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md`
**Draft Authorization:** Engineering Architect Work Order — Phase 2
**Previous Canonical Version:** EDD-001 Version 1.0
**Governing Architecture:** ADR-010 Version 1.0 and DOMAIN-006 Version 1.1
**ADR Required:** Satisfied by ADR-010 Version 1.0
**Implementation Authorization:** None
**Runtime Impact:** None

---

# Version 1.1 Canonical Amendment — Provider Authentication and Authenticated Context Establishment

## A.1 Amendment purpose and authority boundary

This draft amendment translates ADR-010 Version 1.0 and DOMAIN-006 Version 1.1 into an implementation-ready, provider-neutral engineering design for Provider Authentication and Authenticated Context Establishment. It preserves the published Version 1.0 design except where this amendment defines a more specific authentication, candidate-context, principal-binding, credential-custody or local-disposal contract.

This amendment is Approved and Canonical. EDD-001 Version 1.1 supersedes Version 1.0 as the current canonical Engineering Design while preserving Version 1.0 below as historical baseline content. This publication grants no implementation, credential-use, browser, listener, SDK, endpoint, Provider-call or runtime authority. Separate controlled implementation and runtime authorizations are required.

## A.1.1 Version 1.0 to Version 1.1 precedence

Version 1.1 uses the amendment-with-precedence-matrix model and is the current canonical EDD-001. The following matrix determines the effective rule wherever the preserved Version 1.0 text and the Version 1.1 amendment differ:

| Version 1.0 section/topic | Version 1.1 treatment | Effective rule after Version 1.1 canonicalization |
|---|---|---|
| Provider-neutral ownership and dependency boundary | Retained | Version 1.0 remains effective where not specifically amended |
| Existing authentication design | Superseded | Version 1.1 Authentication Attempt lifecycle and typed service contracts govern |
| Credential loading | Superseded for the new authentication capability | Secure Credential and Intended Principal custody contracts govern; `.env` secret loading is not an authentication input |
| Context establishment | Superseded | Only a `SUCCEEDED` attempt with `MATCHED` binding may atomically establish an `ACTIVE` context |
| Context termination | Superseded for End KRONOS Session | Version 1.1 local-only disposal governs; remote token invalidation is a separate unauthorized operation |
| Redirect handling | Superseded | Version 1.1 loopback callback acceptance, first-request terminality and cancellation contracts govern |
| Availability verification | Superseded | Version 1.1 independent availability projection and explicit verification contract govern |
| Context validity and Kite expiry | Amended | Provider-neutral validity accepts adapter policy; next-06:00 Asia/Kolkata is Kite-specific |
| Error sanitization | Retained and strengthened | Version 1.0 sanitization remains effective plus Version 1.1 redaction/non-retention rules |
| Configuration and Provider ownership | Retained | Canonical ownership remains unchanged; protected custody implements but does not acquire credential meaning |
| Implementation authority | Retained | None |
| Runtime authority | Retained | None |

Version 1.1 governs every topic explicitly listed as amended or superseded. Version 1.0 governs all other preserved topics. No preserved Version 1.0 wording may be used to bypass a Version 1.1 control.

## A.2 Code-evidence conformance assessment

The assessment below is against the repository at `5b0bd2259dbb0afcfe66d3bce27f813037510f4f`. Classification meanings are:

- `CONFORMANT`: the required meaning and control are implemented as required;
- `PARTIALLY CONFORMANT`: reusable evidence exists, but the complete canonical requirement is not implemented;
- `NON-CONFORMANT`: current behavior conflicts with the canonical requirement; and
- `NOT IMPLEMENTED`: no implementation evidence exists.

| Canonical requirement | Current code evidence | Classification | Required disposition |
|---|---|---|---|
| Configuration owns Provider identity, redirect-registration meaning and intended Provider registration | `Settings` owns Provider, API key and redirect URL, but has no intended-registration reference | PARTIALLY CONFORMANT | Add a non-sensitive intended-registration reference to the provider-neutral configuration boundary |
| Secure Credential capability owns protected retrieval mechanics | `load_settings()` loads `KRONOS_KITE_API_SECRET` through `python-dotenv`; `Settings` carries the secret | NON-CONFORMANT | Remove daily authentication dependence on plain-text settings and retrieve through a Secure Credential contract |
| Secret values are excluded from object representations | `Settings` marks API key, API secret and access token `repr=False` | CONFORMANT | Preserve and extend no-representation rules |
| Provider Authentication Service owns one first-class Authentication Attempt | `KiteAuthentication.authenticate()` performs one synchronous activity with an internal activity identifier | PARTIALLY CONFORMANT | Introduce an explicit attempt aggregate and service lifecycle |
| At most one active attempt per Provider registration | No active-attempt registry or registration-scoped exclusion exists | NOT IMPLEMENTED | Enforce one active attempt keyed by Provider identity and intended-registration reference |
| Non-sequential cryptographically random injectable attempt identity | `uuid4().hex` is random but is created directly and is not injectable | PARTIALLY CONFORMANT | Inject an attempt-identity source and retain the identity internally |
| Bounded attempt lifetime | No listener/attempt deadline exists; only established-context expiry is calculated | NOT IMPLEMENTED | Inject a timezone-aware clock and absolute attempt deadline |
| Exact loopback callback transport controls | Redirect handling is injected; no repository loopback listener exists | NOT IMPLEMENTED | Add standard-library listener with the exact controls in A.7 |
| Callback acceptance remains a service decision | `_request_token()` currently combines URI validation and Provider-result interpretation inside `KiteAuthentication` | PARTIALLY CONFORMANT | Separate transport result from service-owned acceptance and terminal decision |
| One callback, one token, one exchange | Existing parser requires exactly one token and adapter consumes its secret once; callback consumption is not modeled | PARTIALLY CONFORMANT | Add explicit callback-consumed and exchange-started guards |
| Login URL and SDK mechanics remain adapter-local | Kite login URL, exchange and exceptions remain inside Kite adapter/client boundaries | CONFORMANT | Preserve SDK and Provider-specific type containment |
| Token exchange creates only a candidate Provider Context | `_KiteAuthenticationClientHandle.exchange()` marks its handle authenticated and the Provider establishes context immediately on successful outcome | NON-CONFORMANT | Return an opaque candidate handle that is unpublished and unusable except for binding verification |
| Principal verification uses minimum translated evidence | Existing `profile()` validation checks only that the payload is a mapping | PARTIALLY CONFORMANT | Translate only the configured principal-binding attribute to internal comparison evidence, then discard the payload |
| Binding compares candidate principal with intended Provider registration | No intended registration or binding comparison exists | NOT IMPLEMENTED | Add a provider-neutral binder with deterministic outcomes |
| Intended principal resolves through protected one-operation custody | No intended-principal resolver or lease exists | NOT IMPLEMENTED | Add `IntendedPrincipalResolver` and `IntendedPrincipalLease`; prohibit direct reference comparison |
| Mismatch, unconfirmed or unavailable binding disposes the candidate | Candidate-context and binding outcomes do not exist | NOT IMPLEMENTED | Fail closed and locally dispose candidate state for every non-match |
| Established context is published only after `MATCHED` | Current context establishment follows token-exchange success directly | NON-CONFORMANT | Require successful binding before context construction/publication |
| Access token remains private inside the client/context | Client handle has no public access-token getter; verification discards the profile mapping | CONFORMANT | Preserve opaque client ownership and payload discard |
| Request token is transient, one-use and non-retained | Request token is a local value and is passed once, but explicit disposal/consumption evidence is absent | PARTIALLY CONFORMANT | Represent only consumption state; clear local references immediately after exchange invocation |
| Active Authentication Attempt supports explicit local cancellation | No cancellation contract or late-callback invalidation state exists | NOT IMPLEMENTED | Add idempotent `cancel_authentication_attempt()` and `CANCELLED` terminal state |
| Every sensitive carrier is redacted and non-serializable | `Settings` fields are repr-hidden, but no comprehensive URL/token/principal wrapper policy exists | PARTIALLY CONFORMANT | Apply the representation and non-retention rules in A.8.1 |
| Attempt, context and availability are separate state models | Current outcome/context models mix activity outcome, validity and termination meanings and expose no corrected attempt lifecycle | NON-CONFORMANT | Implement the three independent models and transitions in A.5 and A.12 |
| Provider availability uses canonical verification projection | Existing availability distinguishes `NOT_ESTABLISHED`, `AVAILABLE`, `UNAVAILABLE`; no `VERIFYING` or `INDETERMINATE` | PARTIALLY CONFORMANT | Add the independent five-state projection in A.12 |
| Temporary verification unavailability does not rewrite a completed attempt or active context as failed | Current context validation preserves context on unavailable Provider evidence | CONFORMANT | Preserve this behavior and keep the completed attempt immutable |
| End KRONOS Session is local-only | Current termination calls `invalidate_access_token()` at the Provider | NON-CONFORMANT | Add a distinct local-disposal operation and exclude remote invalidation from it |
| Errors and evidence are sanitized | Adapter maps SDK/transport exceptions to controlled codes; raw payloads are not returned | CONFORMANT | Preserve controlled categories and prohibit raw exception retention |
| Presentation owns explicit initiation and sanitized display only | Existing CAR-015 GUI demonstrates a pilot-local one-run sanitized pattern, not a production authentication assistant | PARTIALLY CONFORMANT | A future separately authorized presentation shall depend only on the service contract |
| No automatic retry or reauthentication | Existing authentication pipeline contains no retry loop | CONFORMANT | Preserve; a new attempt requires explicit initiation |

No contradiction with ADR-010 Version 1.0 or DOMAIN-006 Version 1.1 was identified. The non-conformant findings are implementation gaps explicitly anticipated by ADR-010 Section 15.

## A.3 Proposed component model and dependency direction

```text
Presentation
    -> ProviderAuthenticationService
        -> ProviderAuthenticationConfiguration
        -> SecureCredentialSource
        -> IntendedPrincipalResolver
        -> AuthenticationCallbackListener
        -> ProviderAuthenticationAdapter
            -> Kite SDK client
        -> PrincipalBindingVerifier
        -> ProviderContextPublisher
```

The service is the sole lifecycle coordinator. Configuration supplies meanings, not secure-storage mechanics. The Secure Credential backend supplies one bounded secret lease, not authentication decisions. The callback listener supplies a transport result, not an authentication result. The adapter owns Kite translations and SDK objects. The binding verifier owns comparison only. The publisher accepts only a bound candidate. Presentation receives sanitized projections only.

No lower component may depend on Presentation. No provider-neutral component may expose a Kite SDK type, raw Provider payload, request token, access token, API secret, authorization header or raw exception.

## A.4 Exact provider-neutral typed contracts

The following signatures define the required public engineering boundary. Names may change only through Engineering Verification if semantic equivalence is proven.

```python
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

type AttemptId = str
type ProviderId = str
type RegistrationRef = str

class AuthenticationAttemptState(StrEnum):
    CREATED = "CREATED"
    LISTENER_READY = "LISTENER_READY"
    BROWSER_OPEN_REQUESTED = "BROWSER_OPEN_REQUESTED"
    AWAITING_CALLBACK = "AWAITING_CALLBACK"
    CALLBACK_ACCEPTED = "CALLBACK_ACCEPTED"
    EXCHANGING = "EXCHANGING"
    BINDING_PRINCIPAL = "BINDING_PRINCIPAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"

class AuthenticatedContextState(StrEnum):
    ABSENT = "ABSENT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ENDED = "ENDED"

class ProviderAvailabilityState(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFYING = "VERIFYING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INDETERMINATE = "INDETERMINATE"

class CallbackCategory(StrEnum):
    ACCEPTED = "ACCEPTED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    INVALID_METHOD = "INVALID_METHOD"
    INVALID_PATH = "INVALID_PATH"
    INVALID_HOST = "INVALID_HOST"
    TOKEN_MISSING = "TOKEN_MISSING"
    TOKEN_MULTIPLE = "TOKEN_MULTIPLE"
    DUPLICATE = "DUPLICATE"
    TIMED_OUT = "TIMED_OUT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"

class PrincipalBindingResult(StrEnum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNCONFIRMED = "UNCONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"

class IntendedPrincipalResolutionOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    ACCESS_DENIED = "ACCESS_DENIED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    SANITIZED_FAILURE = "SANITIZED_FAILURE"

@dataclass(frozen=True, slots=True)
class IntendedPrincipalResolutionResult:
    outcome: IntendedPrincipalResolutionOutcome
    binding_result: PrincipalBindingResult | None

class AuthenticationAttemptCancellationResult(StrEnum):
    CANCELLED = "CANCELLED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    NO_ACTIVE_ATTEMPT = "NO_ACTIVE_ATTEMPT"

class AuthenticationFailureCode(StrEnum):
    CONFIGURATION_INELIGIBLE = "CONFIGURATION_INELIGIBLE"
    ATTEMPT_ALREADY_ACTIVE = "ATTEMPT_ALREADY_ACTIVE"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    LOGIN_INITIATION_FAILED = "LOGIN_INITIATION_FAILED"
    CALLBACK_REJECTED = "CALLBACK_REJECTED"
    CALLBACK_TIMED_OUT = "CALLBACK_TIMED_OUT"
    TOKEN_EXCHANGE_REJECTED = "TOKEN_EXCHANGE_REJECTED"
    TOKEN_EXCHANGE_UNAVAILABLE = "TOKEN_EXCHANGE_UNAVAILABLE"
    PRINCIPAL_MISMATCHED = "PRINCIPAL_MISMATCHED"
    PRINCIPAL_UNCONFIRMED = "PRINCIPAL_UNCONFIRMED"
    PRINCIPAL_BINDING_UNAVAILABLE = "PRINCIPAL_BINDING_UNAVAILABLE"
    ACCESS_TOKEN_INVALID_OR_EXPIRED = "ACCESS_TOKEN_INVALID_OR_EXPIRED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ATTEMPT_TIMED_OUT = "ATTEMPT_TIMED_OUT"
    LOCAL_CLEANUP_FAILED = "LOCAL_CLEANUP_FAILED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"

class CallbackReadiness(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    CLOSED = "CLOSED"

class BrowserOpenCategory(StrEnum):
    OPENED = "OPENED"
    DECLINED = "DECLINED"
    FAILED = "FAILED"

@dataclass(frozen=True, slots=True, repr=False)
class ProviderAuthenticationConfiguration:
    provider: ProviderId
    _api_key: str = field(repr=False)
    redirect_uri: str
    intended_registration_ref: RegistrationRef
    credential_ref: str

    def use_api_key(self, operation: Callable[[str], None]) -> None: ...
    def __repr__(self) -> str: return "<ProviderAuthenticationConfiguration redacted>"
    def __str__(self) -> str: return "<ProviderAuthenticationConfiguration redacted>"

@dataclass(frozen=True, slots=True)
class SessionStatus:
    attempt_state: AuthenticationAttemptState | None
    context_state: AuthenticatedContextState
    provider_availability: ProviderAvailabilityState
    failure_code: AuthenticationFailureCode | None
    attempt_active: bool
    context_reusable: bool

@dataclass(frozen=True, slots=True)
class AuthenticationOutcomeEvidence:
    attempt_id: AttemptId
    provider: ProviderId
    intended_registration_ref: RegistrationRef
    state: AuthenticationAttemptState
    binding_result: PrincipalBindingResult | None
    failure_code: AuthenticationFailureCode | None
    callback_consumed: bool
    candidate_disposed: bool
    completed_at: datetime

class AuthenticationAttemptHandle(Protocol):
    """Opaque, non-serializable service capability; not a user identity."""

@dataclass(frozen=True, slots=True, repr=False)
class BrowserOpenRequest:
    official_login_url: str

@dataclass(frozen=True, slots=True)
class BrowserOpenResult:
    category: BrowserOpenCategory

class OneUseRequestToken(Protocol):
    def consume_for_call(self, operation: Callable[[str], object]) -> object: ...
    def close(self) -> None: ...

class CallbackAcceptanceResult(Protocol):
    def category(self) -> CallbackCategory: ...
    def consume_request_token(
        self,
        operation: Callable[[OneUseRequestToken], object],
    ) -> object: ...
    def close(self) -> None: ...

class PrincipalEvidence(Protocol):
    def close(self) -> None: ...

class IntendedPrincipalLease(Protocol):
    def compare_once(self, evidence: PrincipalEvidence) -> PrincipalBindingResult: ...
    def close(self) -> None: ...

class IntendedPrincipalResolver(Protocol):
    def use_resolved_once(
        self,
        registration_ref: RegistrationRef,
        operation: Callable[[IntendedPrincipalLease], PrincipalBindingResult],
    ) -> IntendedPrincipalResolutionResult: ...

class SecretLease(Protocol):
    def reveal_for_call(self, operation: Callable[[str], object]) -> object: ...
    def close(self) -> None: ...

class SecureCredentialSource(Protocol):
    def acquire(self, credential_ref: str) -> SecretLease: ...

class AuthenticationCallbackListener(Protocol):
    def readiness(self) -> CallbackReadiness: ...
    def receive_once(self, *, deadline: datetime) -> CallbackAcceptanceResult: ...
    def close(self) -> None: ...

class ProviderCandidateContext(Protocol):
    def principal_evidence(self) -> PrincipalEvidence: ...
    def dispose_local(self) -> None: ...

class ProviderAuthenticationAdapter(Protocol):
    def login_url(self, redirect_uri: str) -> str: ...
    def exchange_once(
        self,
        request_token: OneUseRequestToken,
        api_secret: SecretLease,
    ) -> ProviderCandidateContext: ...

class PrincipalBindingVerifier(Protocol):
    def verify_principal_binding(
        self,
        evidence: PrincipalEvidence,
        intended_registration_ref: RegistrationRef,
    ) -> PrincipalBindingResult: ...

class LoginNavigator(Protocol):
    def open_official_login(
        self,
        request: BrowserOpenRequest,
    ) -> BrowserOpenResult: ...

class ProviderAuthenticationService(Protocol):
    def begin_login(self) -> AuthenticationAttemptHandle: ...
    def complete_callback(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence: ...
    def cancel_authentication_attempt(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationAttemptCancellationResult: ...
    def verify_provider_availability(self) -> ProviderAvailabilityState: ...
    def session_status(self) -> SessionStatus: ...
    def authentication_attempt_status(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence | None: ...
    def end_kronos_session(self) -> None: ...

def establish_authenticated_context(
    candidate: ProviderCandidateContext,
    binding: PrincipalBindingResult,
) -> "AuthenticatedProviderContext": ...
```

`CallbackAcceptanceResult`, `OneUseRequestToken`, `PrincipalEvidence`, `IntendedPrincipalLease`, `SecretLease`, `AuthenticationAttemptHandle` and `ProviderCandidateContext` are internal boundary values. Sensitive wrappers expose values, where required, only inside their single bounded callback or comparison operation. They are non-serializable, have explicitly redacted `repr()` and `str()`, expose no raw-value getter and never enter retained evidence. `ProviderAuthenticationConfiguration` disables generated representation; serialization is prohibited; debug logging receives `SessionStatus` only. `AuthenticationOutcomeEvidence` contains only approved sanitized fields; support/audit exposure of `attempt_id` remains disabled by default.

`establish_authenticated_context()` requires `binding is MATCHED`; every other input is rejected and the candidate is disposed locally. The concrete service constructor requires `ProviderAuthenticationConfiguration`, `SecureCredentialSource`, listener and adapter factories, `PrincipalBindingVerifier`, `LoginNavigator`, an injectable clock, an injectable identity source and a process-scoped active-attempt registry.

Lifecycle preconditions and results are exact:

| Operation | Precondition | Result | Controlled failures |
|---|---|---|---|
| `begin_login()` | eligible Configuration; no active attempt for registration; no reusable authenticated context | ready listener, browser-open attempt, opaque active handle | configuration ineligible, attempt active, listener unavailable, login initiation/browser open failed |
| listener `readiness()` | owned listener exists | `NOT_READY`, `READY` or `CLOSED` | none; it exposes no socket or token |
| `open_official_login()` | listener is `READY`; official adapter URL exists | `OPENED`, `DECLINED` or `FAILED` | raw browser exception is sanitized inside navigator |
| `complete_callback(...)` | matching active handle; browser result `OPENED`; unexpired attempt | one terminal sanitized outcome | callback rejection/timeout, credential failure, exchange failure, binding failure, expiry, internal failure |
| `verify_principal_binding()` | unpublished candidate; verification not previously consumed | one binding outcome | `UNAVAILABLE` is fail-closed; no retry |
| `establish_authenticated_context()` | candidate plus `MATCHED` evidence from same attempt | one private authenticated context | any non-match or provenance mismatch disposes candidate |
| `cancel_authentication_attempt()` | opaque handle for an active or terminal attempt | idempotent sanitized cancellation result | no Provider operation; terminal attempt remains unchanged |
| `verify_provider_availability()` | `ACTIVE` unexpired context; explicit invocation | one availability projection | invalid token expires context; temporary failure changes availability only |
| `end_kronos_session()` | any local state | local state `ENDED` where established; otherwise locally cleared | cleanup category only; no remote action |
| `session_status()` | none | current sanitized authentication/availability projection | none |
| `authentication_attempt_status()` | valid opaque handle issued by this service | current/terminal sanitized attempt evidence | unknown handle rejected without existence disclosure |

No method has a public token, secret, profile, principal-value, SDK-client or raw-exception getter.

## A.5 Authentication Attempt implementation design

One mutable service-private aggregate represents an attempt:

```python
@dataclass(frozen=True, slots=True)
class _CorrelationEvidence:
    provider: ProviderId
    intended_registration_ref: RegistrationRef
    listener_ref: str
    callback_host: str
    callback_port: int
    callback_path: str
    started_at: datetime
    expires_at: datetime

@dataclass(frozen=True, slots=True)
class _CallbackEvidence:
    category: CallbackCategory
    within_lifetime: bool
    callback_consumed: bool
    exactly_one_token: bool

@dataclass(frozen=True, slots=True)
class _BindingEvidence:
    outcome: PrincipalBindingResult
    verified_at: datetime
    candidate_disposed: bool

@dataclass(slots=True, repr=False)
class AuthenticationAttempt:
    attempt_id: AttemptId
    provider: ProviderId
    intended_registration_ref: RegistrationRef
    created_at: datetime
    started_at: datetime
    expires_at: datetime
    state: AuthenticationAttemptState
    callback_consumed: bool
    exchange_started: bool
    candidate_created: bool
    candidate_disposed: bool
    terminal_code: AuthenticationFailureCode | None
    binding_result: PrincipalBindingResult | None
    listener_ref: str
    correlation_evidence: _CorrelationEvidence
    callback_evidence: _CallbackEvidence | None
    binding_evidence: _BindingEvidence | None
    sanitized_outcome: AuthenticationOutcomeEvidence | None
```

The identity source is injected and shall use `secrets.token_urlsafe(32)` by default. The clock is injected and timezone-aware. The Phase 3 implementation authority shall select and document one attempt duration not exceeding five minutes; until then no duration or listener activation is authorized.

The service uses a process-scoped active-attempt registry keyed by `(provider, intended_registration_ref)`. `begin_login()` atomically reserves the key and creates the attempt in `CREATED`, rejecting a second non-terminal attempt even if a second service façade exists. An attempt becomes terminal exactly once. Terminal cleanup closes the listener, closes any secret or principal lease, invalidates one-use token references, locally disposes an unpublished candidate where present and removes the registry entry.

Permitted attempt transitions are:

```text
CREATED -> LISTENER_READY
LISTENER_READY -> BROWSER_OPEN_REQUESTED
BROWSER_OPEN_REQUESTED -> AWAITING_CALLBACK
AWAITING_CALLBACK -> CALLBACK_ACCEPTED
CALLBACK_ACCEPTED -> EXCHANGING
EXCHANGING -> BINDING_PRINCIPAL
BINDING_PRINCIPAL -> SUCCEEDED

Any non-terminal state -> FAILED | CANCELLED
Any non-terminal state before its deadline -> its next permitted state
Any non-terminal state at its deadline -> TIMED_OUT
```

`SUCCEEDED`, `FAILED`, `CANCELLED` and `TIMED_OUT` are terminal. A successful attempt ends at `SUCCEEDED`; an attempt never becomes `EXPIRED` or `ENDED`. Cancellation is permitted only while non-terminal. No terminal attempt reactivates. No retry, polling, automatic repetition or automatic reauthentication exists. A new attempt requires a new explicit Presentation action and applicable governance authority.

### A.5.1 Cancellation contract

`cancel_authentication_attempt()` is idempotent and local-only. GUI close during an active attempt, explicit Cancel, application shutdown, listener startup failure and browser-open failure select `CANCELLED`. Reaching the bounded deadline selects `TIMED_OUT`, not `CANCELLED`. A technical failure after callback acceptance selects `FAILED`.

Cancellation stops an existing listener, invalidates callback eligibility, rejects late callbacks, releases secret and intended-principal leases, invalidates transient request-token wrappers, locally disposes any candidate, records a sanitized reason and makes no Provider call, remote logout or token invalidation. An already-terminal attempt is unchanged. GUI-close behavior is deterministic: no active attempt closes normally; a non-terminal attempt is cancelled locally before close; a terminal attempt closes without lifecycle mutation.

## A.6 Ordered authentication orchestration

The service shall execute this order:

1. `begin_login()` validates Configuration and creates `CREATED`;
2. it starts the listener and proves readiness before moving to `LISTENER_READY`;
3. it obtains the adapter-translated official URL and moves to `BROWSER_OPEN_REQUESTED` before submitting the redacted `BrowserOpenRequest`;
4. if browser opening is declined or fails, it invokes cancellation, closes the listener, returns `CANCELLED` with `LOGIN_INITIATION_FAILED`, and performs no credential retrieval, SDK exchange or Provider call;
5. if browser opening succeeds, it moves to `AWAITING_CALLBACK`;
6. `complete_callback(...)` receives the first terminal callback before the deadline;
7. an accepted callback moves to `CALLBACK_ACCEPTED`; a rejected first request moves to `FAILED`; deadline expiry moves to `TIMED_OUT`;
8. it retrieves the API secret only after acceptance, moves to `EXCHANGING` and exchanges one token exactly once;
9. it closes the secret lease, invalidates the request-token wrapper and holds the SDK client only as a candidate;
10. it moves to `BINDING_PRINCIPAL`, resolves the intended principal through protected custody and invokes principal verification once;
11. it immediately disposes raw and expected principal values;
12. `MATCHED` atomically commits attempt `SUCCEEDED` and context `ACTIVE`; every other binding result disposes the candidate and commits attempt `FAILED`; and
13. it closes the listener and exposes sanitized attempt, context and availability projections only.

Token exchange alone never succeeds the attempt or establishes a context. Principal binding never changes Provider Availability. A newly established context starts at `NOT_VERIFIED`; only explicit `verify_provider_availability()` may move availability to `VERIFYING` and a subsequent result.

## A.7 Standard-library loopback callback listener

The listener shall use only Python standard-library HTTP and socket capabilities (`http.server`, `socketserver`, `threading` and `urllib.parse`). No third-party server or browser dependency is proposed.

Exact network contract:

```text
Bind address: 127.0.0.1
Port: 8765
Accepted Host header: 127.0.0.1:8765
Method: GET
Path: /kite/callback
Accepted callback count: 1
Accepted request_token cardinality: exactly 1 non-empty value
Maximum active lifetime: bounded by the attempt deadline
```

Controls are mandatory:

- construct the server with an explicit `("127.0.0.1", 8765)` address and reject wildcard or hostname binding;
- set `allow_reuse_address = False` before binding;
- accept no proxy-derived host, forwarded host or alternate loopback notation;
- require exactly one Host header; parse it as an authority using `urlsplit("//" + value)`; reject user information, path, query, fragment, malformed port and ambiguous forms; require parsed hostname `127.0.0.1`, parsed port `8765` and canonical raw serialization `127.0.0.1:8765`;
- reject request bodies and ignore no alternate HTTP method;
- parse the query using `parse_qs(..., keep_blank_values=True, strict_parsing=False)` and accept exactly one non-empty `request_token` value;
- treat Provider `status=error` or Provider error fields as a sanitized rejection without retaining query values;
- atomically mark callback consumption before returning a token wrapper;
- reject every duplicate, including a duplicate arriving while terminal cleanup is underway;
- never log request lines, headers, URLs, query strings or socket peer details; override default request/error logging with no-op methods;
- return only fixed sanitized HTML for success, rejection or expiry, with no reflected input;
- enforce the absolute attempt deadline using an injected clock plus bounded socket/server timeouts;
- close the listening socket immediately on accepted callback, terminal rejection, timeout, cancellation or internal failure; and
- join its worker with a bounded wait and report only a sanitized local cleanup category.

Version 1 treats the first request reaching the approved listener as terminal for the active attempt whether accepted or rejected. Wrong method, path or Host, missing/multiple token, malformed input and duplicates are rejected and cannot be exchanged. A duplicate racing with shutdown receives a fixed rejection. Transport rejection does not expose whether a particular attempt or registration exists.

This sharply limits callback cardinality and listener lifetime. The accepted availability trade-off is that a malformed, accidental or malicious first local request may terminate the attempt and deny the legitimate callback. This is a bounded local-pilot denial-of-service risk. No silent retry is permitted; a new attempt requires explicit user action and any required fresh authority.

The listener is closed immediately if browser opening is declined, raises or returns `FAILED`. An opened browser that never completes login is bounded by the same attempt deadline. Provider error callbacks translate to `PROVIDER_REJECTED` without retaining Provider parameters.

Residual risk remains that, because Provider-returned state/nonce round-trip support is unproven, a malicious local process or browser-mediated injection may race the legitimate callback. Exact loopback controls, one callback and principal binding reduce but do not eliminate this risk. The listener result and adapter login contract reserve an optional opaque correlation-evidence field for a future Provider-returned state/nonce; it remains disabled until Provider support and a separate architecture amendment are proven.

## A.8 Secure Credential interface and Apple Keychain backend

Configuration owns the meaning of `credential_ref`; it contains a logical service/account reference and never a secret. The Secure Credential capability owns retrieval mechanics. The API key remains Configuration input. The API secret is not accepted by the normal daily UI and is not loaded from `.env`, source, fixtures, arguments or browser storage for this capability.

The first backend is `AppleKeychainCredentialSource`, implementing `SecureCredentialSource` by invoking macOS `/usr/bin/security` with an argument vector, never a shell. Lookup construction is exact:

```text
service = "com.project-kronos.provider-authentication." + lower(provider)
account = "api-secret:" + credential_ref
command = /usr/bin/security find-generic-password -w -s <service> -a <account>
```

`provider` must match the configured provider slug and `credential_ref` must be a Configuration-owned, non-sensitive opaque reference matching `[A-Za-z0-9._-]{1,64}`. No account identifier is used as the lookup reference.

Retrieval result categories are `FOUND`, `MISSING`, `ACCESS_DENIED`, `BACKEND_UNAVAILABLE`, `TIMED_OUT` and `MALFORMED`. Only `FOUND` returns a closed-by-default one-operation lease; every other category maps to `CREDENTIAL_UNAVAILABLE` plus backend-category evidence permitted only for sanitized support. The implementation shall:

- require an allow-listed service prefix and non-empty account reference;
- use `subprocess.run()` with `shell=False`, `stdin=DEVNULL`, captured binary output, a bounded timeout and a minimal inherited environment;
- place no secret in command arguments;
- accept the secret only from successful stdout and never log stdout/stderr;
- translate exit status, timeout, missing item, denial and malformed output to sanitized credential categories;
- copy no secret into `Settings`, Configuration records, outcomes, logs or UI;
- return a one-operation `SecretLease` with redacted `repr` and no serialization;
- close the lease immediately after exchange and delete ordinary Python references; and
- make no secure-memory-erasure claim.

Keychain writes, updates, deletion, enumeration, UI prompts and credential provisioning are outside Version 1.1. The backend is retrieval-only. A future Windows backend must implement the same contract without changing Provider Authentication Service semantics.

### A.8.1 Sensitive-object representation and non-retention

`ProviderAuthenticationConfiguration` and every object carrying an API key, API secret, request token, access token, intended principal, raw principal evidence or callback URL with query material disables generated representation. `repr()` and `str()` return fixed redacted type labels. Pickle/dataclass conversion and general serialization are prohibited or emit a separately defined sanitized projection. Exceptions contain controlled codes only. Debug logging accepts only `SessionStatus` or other sanitized evidence.

`SecretLease` invokes exactly one callback with the secret during exchange. The callback may return a candidate object but cannot return or embed the secret. The service, controller and view never store the callback argument. The lease closes once on success, failure, cancellation or timeout; post-close use fails deterministically. Fake leases record acquisition, use and release counts. Tests inspect closure cells and reachable service/controller/view state where reasonably possible to prove no retained secret reference. No physical-memory-erasure claim is made.

`OneUseRequestToken` is accepted once and consumed once through a bounded operation. Post-consumption access and duplicate use fail deterministically. `repr()` and `str()` are redacted; serialization is prohibited; no long-lived service state retains it. Cancellation, rejection, exchange failure and timeout close or invalidate it. Tests inspect service/controller/view state after every terminal path. No physical-memory-erasure claim is made.

## A.9 Kite adapter, candidate isolation and principal binding

The Kite adapter shall retain SDK ownership and translate provider-neutral calls:

- `login_url(redirect_uri)` delegates to the official SDK login URL construction;
- `exchange_once()` calls `generate_session()` once with the one-use request token and bounded API secret;
- the returned SDK client becomes an opaque `_KiteCandidateContext`;
- no product, acquisition, trading or general Provider method accepts that candidate;
- `principal_evidence()` invokes only the separately authorized profile verification path;
- the adapter reads only the configured principal-binding field, creates minimum normalized evidence and immediately discards the raw mapping; and
- `dispose_local()` closes local HTTP/session resources and drops the client reference without calling any Provider endpoint.

The internal intended-registration reference is not a Provider account identifier and is never compared directly with Provider evidence. `IntendedPrincipalResolver` accepts that reference, resolves the expected principal through approved protected custody and supplies it only as a one-operation `IntendedPrincipalLease`. Resolution outcomes are `RESOLVED`, `NOT_FOUND`, `ACCESS_DENIED`, `BACKEND_UNAVAILABLE`, `INVALID_CONFIGURATION` and `SANITIZED_FAILURE`. No raw expected principal reaches Presentation, retained Configuration evidence, service state, exceptions or logs.

The required sequence is:

```text
internal registration reference
    -> bounded intended-principal resolution
    -> minimum Provider principal evidence
    -> normalized comparison
    -> binding result
    -> immediate disposal of expected and raw principal values
```

Kite minimum principal evidence is only the `user_id` field from the profile mapping. Both Provider evidence and the protected expected value must be strings, must already equal their stripped values, and must match `[A-Za-z0-9]{1,64}`. No case folding, Unicode normalization, truncation, coercion or aliasing is permitted. Comparison is exact and case-sensitive. Missing, malformed or non-canonical evidence produces `UNCONFIRMED`; temporary profile transport/Provider failure produces `UNAVAILABLE`; inequality produces `MISMATCHED`; equality produces `MATCHED`.

The comparison occurs inside the lease callback. The raw mapping, raw `user_id` and resolved expected value are discarded immediately after comparison; no value is stored on long-lived service state. `IntendedPrincipalLease` has redacted `repr()` and `str()`, no value getter, equality, sensitive hashing or serialization, and closes immediately after one comparison. Fake lease injection proves acquisition/use/release without protected-store access. No secure-memory-erasure claim is made.

Retained binding evidence is limited to internal Authentication Attempt ID, Provider identity, internal registration reference, `PrincipalBindingResult`, timestamp and sanitized reason code. No Provider account identifier is retained.

Binding outcomes have these deterministic effects:

| Binding or verification result | Authentication Attempt | Context | Provider Availability | Candidate/action |
|---|---|---|---|---|
| Principal binding `MATCHED` | `SUCCEEDED` | `ACTIVE` | `NOT_VERIFIED` | atomically transfer opaque client ownership; publish once |
| Principal binding `MISMATCHED` | `FAILED` | `ABSENT` | `NOT_VERIFIED` or absent | dispose locally; no context |
| Principal binding `UNCONFIRMED` | `FAILED` | `ABSENT` | `NOT_VERIFIED` or absent | dispose locally; no context; no manual override |
| Principal verification `UNAVAILABLE` | `FAILED` with `PRINCIPAL_BINDING_UNAVAILABLE` | `ABSENT` | `NOT_VERIFIED` or absent | dispose locally; this is not availability verification |
| Explicit availability verification | completed attempt unchanged | requires `ACTIVE` | controls `VERIFYING` then `AVAILABLE`, `UNAVAILABLE` or `INDETERMINATE` | no candidate exists |

No manual override exists. Order of cleanup does not change the binding outcome. Cleanup failures are secondary sanitized evidence and never convert a non-match to a match.

## A.10 Authenticated Provider Context establishment

Only the service may transfer a matched candidate into `AuthenticatedProviderContext`. Establishment and the attempt's transition to `SUCCEEDED` form one atomic local commit. The resulting context starts at `ACTIVE`; the candidate remains unpublished until the context contains provider identity, non-sensitive configuration provenance, attempt provenance, adapter-supplied bounded validity, reuse eligibility and the private adapter/client handle.

The context exposes no credential, token, principal field, SDK client or candidate reference. It is unavailable to products until `ACTIVE`. Existing context validity and Provider usability remain separate meanings. A successful attempt does not establish acquisition authority, capability, entitlement, Dataset Permission, Market Fact, Validation Result, submission authority, trading authority or runtime authority.

If local construction cannot be completed, the atomic commit does not occur, the candidate is disposed locally and the non-terminal attempt moves to `FAILED`; partial publication is prohibited. Once committed, later context expiry or ending never rewrites the completed `SUCCEEDED` attempt.

## A.11 End KRONOS Session implementation

`end_kronos_session()` is a local operation. It shall:

1. atomically make the current context unavailable for new reuse;
2. close local adapter HTTP/session resources once;
3. clear the local candidate or established client reference;
4. clear local context and reuse references; and
5. transition an `ACTIVE` context to `ENDED`.

It shall not call `invalidate_access_token()`, terminate a Provider session, log out remotely, revoke a token, open a browser, retrieve credentials, start a new attempt or make any Provider request. The current remote termination method must remain separately named and unreachable from End KRONOS Session unless a later explicit authority governs remote invalidation.

Local cleanup failure produces a sanitized cleanup category, but the context remains locally ended and ineligible for reuse. End KRONOS Session is idempotent and performs no automatic reauthentication.

## A.12 State projections

The service exposes three completely separate models.

Authentication Attempt lifecycle:

- `CREATED`;
- `LISTENER_READY`;
- `BROWSER_OPEN_REQUESTED`;
- `AWAITING_CALLBACK`;
- `CALLBACK_ACCEPTED`;
- `EXCHANGING`;
- `BINDING_PRINCIPAL`;
- `SUCCEEDED`;
- `FAILED`;
- `CANCELLED`; and
- `TIMED_OUT`.

`SUCCEEDED`, `FAILED`, `CANCELLED` and `TIMED_OUT` are terminal. The attempt model has no `EXPIRED` or `ENDED` state.

Authenticated Provider Context lifecycle:

- `ABSENT`: no established context;
- `ACTIVE`: one bound, locally reusable context exists;
- `EXPIRED`: adapter-supplied validity elapsed or authoritative authentication-invalid evidence was received; and
- `ENDED`: local End KRONOS Session disposed the context.

Only `ACTIVE -> EXPIRED` and `ACTIVE -> ENDED` are permitted. `EXPIRED` and `ENDED` are terminal for that context. Neither transition changes the completed attempt.

Provider Availability:

- `NOT_VERIFIED`: every newly established `ACTIVE` context starts here;
- `VERIFYING`: explicit `verify_provider_availability()` is active;
- `AVAILABLE`: verification produced valid provider evidence;
- `UNAVAILABLE`: an established context's separately initiated verification encountered temporary Provider unavailability; and
- `INDETERMINATE`: pre-establishment verification or binding could not establish availability/binding.

Principal binding never sets `AVAILABLE`. Only explicit availability verification may leave `NOT_VERIFIED`. Temporary unavailability never rewrites a `SUCCEEDED` attempt or an `ACTIVE` context as `FAILED`. Authoritative invalid-token evidence may move the context to `EXPIRED`; that is distinct from ordinary Provider Unavailability. Presentation receives the three projections and controlled failure code, never raw evidence.

For established-context availability verification, only authoritative adapter translation to `ACCESS_TOKEN_INVALID_OR_EXPIRED` moves the context to `EXPIRED`. Network timeout, connection failure, rate limiting and Provider service failure affect only availability (`UNAVAILABLE`) and preserve context `ACTIVE`. Unexpected response or an unclassifiable sanitized adapter failure sets availability to `INDETERMINATE`. None of these results changes the completed attempt.

Kite's next-06:00 Asia/Kolkata expiry calculation belongs to the Kite adapter or Kite authenticated-context validity policy. The provider-neutral context accepts an adapter-supplied expiry or validity projection and defines no universal Provider expiry time. Earlier authoritative invalidation remains possible.

The canonical ADR-010 authentication vocabulary remains available only as a read-only architecture compatibility projection; it is not an implementation state store and cannot mutate the three models:

| ADR-010 architecture term | Derived engineering evidence |
|---|---|
| `NOT_AUTHENTICATED` | context `ABSENT` and no non-terminal attempt; a locally `CANCELLED` attempt remains separate evidence |
| `AUTHENTICATING` | any non-terminal Authentication Attempt state |
| `AUTHENTICATED` | completed attempt `SUCCEEDED` plus context `ACTIVE` |
| `FAILED` | terminal attempt `FAILED` |
| `EXPIRED` | context `EXPIRED`, or compatibility reporting for an attempt that terminally `TIMED_OUT` without changing that attempt state |
| `ENDED` | context `ENDED` |

This crosswalk preserves canonical terminology while preventing attempt, context and availability state mutation from being conflated.

## A.12.1 Temporary tkinter pilot controller and view

A future separately authorized CAR-016 presentation consists of a thin controller and tkinter view in one pilot-local file. Importing the module and constructing or opening the view perform zero browser, listener, credential, SDK, network or Provider activity. Reusable authentication, callback, credential, binding and context logic remains in production modules and imports no tkinter.

The view displays only `Login to Kite`, sanitized attempt/context state, sanitized Provider availability, `Cancel`, `Verify Provider Availability` and `End KRONOS Session`. It has no API key, API secret, request-token, access-token, intended-principal, password, PIN or TOTP field. The controller invokes `begin_login()` only after explicit confirmation, performs `complete_callback(...)` on one bounded worker, marshals immutable sanitized projections onto the tkinter main thread and disables Login while an attempt or reusable context exists. Availability verification and End KRONOS Session require separate explicit actions. Cancel and GUI close call `cancel_authentication_attempt()` only for a non-terminal attempt; close then waits for bounded local cleanup. No active attempt closes normally, and a terminal attempt closes without mutation. No raw exception, traceback, URL, payload, principal or credential is displayed or written to stdout/stderr.

## A.13 Proposed implementation file scope

The following is the exact proposed scope for a later, separately authorized implementation. The list grants no authority.

New production files:

1. `src/kronos/configuration/credentials.py` — Secure Credential contracts and sanitized failures;
2. `src/kronos/configuration/principals.py` — Intended Principal resolver, lease and sanitized resolution outcomes;
3. `src/kronos/configuration/apple_keychain.py` — retrieval-only Apple Keychain backend;
4. `src/kronos/provider/models/authentication.py` — attempt, context-state, availability, binding and sanitized outcome models;
5. `src/kronos/provider/contracts/provider_authentication.py` — service, listener, adapter, candidate and binder protocols;
6. `src/kronos/provider/callbacks/__init__.py` — callback package boundary;
7. `src/kronos/provider/callbacks/loopback.py` — standard-library loopback listener; and
8. `src/kronos/provider/services/provider_authentication.py` — provider-neutral orchestration and lifecycle.

Existing production files requiring modification:

1. `src/kronos/configuration/settings.py` — add non-sensitive intended-registration and credential references; stop requiring a plain-text API secret for the new service;
2. `src/kronos/configuration/loader.py` — exclude API-secret `.env` loading from the new authentication path;
3. `src/kronos/provider/adapters/kite/client.py` — return an opaque candidate, translate minimum principal evidence and add local-only disposal;
4. `src/kronos/provider/adapters/kite/authentication.py` — implement the new adapter/candidate contract and separate local disposal from remote invalidation;
5. `src/kronos/provider/kite/auth/kite_authentication.py` — replace synchronous lifecycle ownership with the provider-neutral service boundary;
6. `src/kronos/provider/kite/adapter/kite_provider.py` — publish only a bound context and route End KRONOS Session locally;
7. `src/kronos/provider/contracts/authentication.py` — retire or adapt the single-call authentication contract without broadening consumers;
8. `src/kronos/provider/models/context.py` — accept only sanitized attempt/binding provenance required for an established context; and
9. `src/kronos/provider/services/access.py` — prohibit direct context establishment from exchange success.

No third-party production dependency is proposed. Existing `kiteconnect` remains adapter-local. The listener and Keychain invocation use the Python standard library and the macOS system executable.

A future CAR-016 pilot or runtime package, if separately authorized, would require these governance/presentation files:

1. `docs/governance/reviews/CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md`;
2. `docs/indexes/DOCUMENT-REGISTER.md`;
3. `tools/provider_pilots/car016_provider_authentication_gui.py`; and
4. `tests/unit/tools/test_car016_provider_authentication_gui.py`.

CAR-016 is not drafted by this amendment. Its identifier, title, scope and file identity remain subject to controlled allocation and Chief Architect authority.

## A.14 Offline fake-only test matrix

All tests below use injected fakes, fixed clocks, deterministic identity sources, synthetic tokens/secrets and local socket fixtures only. No test may access Keychain, open a browser, construct a real Kite SDK client, make a Provider request or contain real credential material.

New test files:

1. `tests/unit/configuration/test_secure_credentials.py`;
2. `tests/unit/configuration/test_intended_principal.py`;
3. `tests/unit/configuration/test_apple_keychain.py`;
4. `tests/unit/provider/test_authentication_attempt.py`;
5. `tests/unit/provider/test_loopback_authentication_callback.py`;
6. `tests/unit/provider/test_provider_authentication_service.py`; and
7. `tests/unit/provider/test_principal_binding.py`.

Existing test files requiring modification:

1. `tests/unit/provider/test_kite_authentication_adapter.py`;
2. `tests/unit/provider/test_kite_edd001_authentication.py`;
3. `tests/unit/provider/test_edd001_provider_access.py`; and
4. `tests/unit/configuration/test_kite_connectivity_settings.py`.

Required cases:

| Area | Required offline evidence |
|---|---|
| Attempt identity | injectable, non-sequential default contract; identity not displayed or serialized |
| Attempt exclusion | second active attempt for the same registration rejected; different registrations isolated |
| Import/view safety | import, controller construction and GUI opening cause zero browser, listener, credential, SDK, network or Provider activity |
| Attempt time | bounded deadline; timeout becomes `TIMED_OUT`; naive clocks rejected; terminal states immutable |
| Callback bind | exact `127.0.0.1:8765`; wildcard/alternate host impossible |
| Callback readiness/browser | readiness precedes browser request; open failure/decline closes listener and performs no credential or exchange activity |
| Callback method/path/Host | only exact GET/path/parsed canonical Host accepted; malformed and ambiguous Host cases rejected |
| Callback cardinality | missing, blank, multiple and duplicate tokens rejected; one accepted callback consumed once |
| Provider callback | Provider rejection/error becomes one sanitized terminal outcome with no parameter retention |
| Callback privacy | no default request log, URL, header, query, token, exception or reflected HTML output |
| Browser completion | only fixed sanitized HTML; no reflected input; browser history/URL never enters KRONOS evidence |
| Listener cleanup | socket closes for success, rejection, timeout, cancellation and internal failure |
| Credential retrieval | exact allow-listed Keychain argv; no shell; bounded timeout; stdout/stderr never logged |
| Secret lease | fake backend retrieved once; one reveal operation; redacted repr; close in success/failure; no serialization; real Keychain prohibited |
| Login/exchange | one login initiation; one exchange; request token cleared; no retry |
| Candidate isolation | candidate unreachable by Provider/product contracts; only principal verification allowed |
| Principal translation | raw mapping and account fields discarded; only comparison result leaves adapter |
| Principal outcomes | matched publishes; mismatched/unconfirmed/unavailable dispose locally and never publish |
| State separation | successful attempt ends `SUCCEEDED`; context independently starts `ACTIVE`; context expiry/ending never changes the attempt |
| Availability | new context starts `NOT_VERIFIED`; binding never sets availability; only explicit verification changes it; temporary unavailability preserves context `ACTIVE` and the completed attempt |
| Invalid token | authoritative invalid-token evidence transitions context to `EXPIRED`; completed attempt remains `SUCCEEDED`; no automatic login |
| Explicit verification | exactly one Provider verification only after explicit action; no polling or retry |
| Context publication | no context before match; atomic publication; failure disposes candidate |
| End KRONOS Session | local close once; no invalidate/logout/Provider call; reuse removed; state `ENDED`; idempotent |
| Intended principal | internal reference resolves through a fake resolver; direct comparison is impossible; expected/raw values are one-use and absent from retained evidence |
| Redaction | Configuration, secret/principal leases, token wrapper and callback URL representations are redacted; exceptions/logs contain no sensitive values |
| Cancellation | GUI close before/during/after attempt; repeated cancel; late callback; candidate disposal; lease/token release; zero Provider calls |
| First-request terminality | valid first request accepted; invalid first request terminates; later valid callback rejected deterministically |
| Non-retention | secret lease released once and token consumed once; no secret/token remains after success, failure, cancellation or timeout |
| Expiry | Kite adapter supplies next-06:00 Asia/Kolkata policy; provider-neutral tests prove no universal 06:00 assumption; earlier invalidation handled |
| Precedence | every Version 1.0 topic resolves through the Version 1.1 precedence matrix without conflicting effective rules |
| Public surface | no token getter, secret getter, principal getter, SDK getter or candidate consumer exists |
| Sanitization | no credential/token/profile/raw exception in repr, logs, stdout, stderr, outcomes or snapshots |
| Fake isolation | no real browser, Keychain, SDK, network route or Provider call |
| GUI concurrency | worker state is immutable at the tkinter boundary; all widget mutation occurs on the main thread |
| Dependency boundary | provider-neutral modules import no Kite SDK; Presentation imports service contract only |
| Regression | existing EDD-001 access/context invariants and adapter error mappings remain valid |
| Suite | focused tests and the complete offline suite remain green under the later implementation authority |

## A.15 Engineering risks and mitigations

| Risk | Required mitigation |
|---|---|
| Local callback injection without Provider state round-trip | Exact loopback controls, one active attempt, short deadline, one callback, immediate shutdown and mandatory principal binding; retain the documented residual risk |
| Port already occupied or malicious local binder | Fail before browser navigation where possible; no alternate port fallback; sanitized failure; no exchange |
| Host-header ambiguity or proxy behavior | One Host header, safe parsed host/port validation plus canonical raw form; no forwarded headers or hostname aliases |
| Duplicate callback race | Atomic consumed guard set before token return; listener shutdown; exchange-started guard |
| Browser callback URL/history exposure | Never display, log or retain login/callback URLs; use only the official Provider browser flow; document that browser-managed history is outside KRONOS custody and requires runtime acceptance |
| Browser opens but login never completes | Absolute attempt deadline, fixed sanitized expiry page and immediate listener shutdown |
| Secret leakage through subprocess output or diagnostics | Capture binary streams, never log them, sanitize every failure, redacted lease, no shell or command-line secret |
| macOS Keychain CLI prompts, exit codes or output vary | Retrieval-only exact argv, bounded timeout, fake subprocess contract tests and fail-closed category mapping; no parsing of diagnostic text |
| Python cannot guarantee secret erasure | Minimize lifetime and references; document that secure erasure is not claimed |
| Candidate accidentally exposed through existing Provider contracts | Separate opaque candidate type; no public getter; service-only transfer after match; dependency tests |
| Wrong-account authentication | Configuration-owned intended reference plus mandatory translated principal binding; no manual override |
| Profile schema change | Fail `UNCONFIRMED`, dispose candidate and retain no payload |
| Temporary Provider failure confused with attempt/context failure | Independent availability projection; completed attempt unchanged; ordinary unavailability preserves context `ACTIVE` |
| Existing remote invalidation called by local End Session | Separate names/contracts; negative tests proving zero Provider calls |
| `.env` API-secret compatibility path remains reachable | New service accepts only `SecureCredentialSource`; test that loader secret cannot satisfy the new contract |
| Raw SDK exception or payload reaches evidence/UI | Adapter-local catch/translation and exhaustive sanitization scans/tests |
| Attempt cleanup masks the primary outcome | Preserve primary terminal category; record only secondary sanitized local-cleanup category |
| Asynchronous shutdown leaks listener/client state | One service-owned cleanup path, cancellation event, bounded join and idempotent close tests for every terminal branch |
| Cross-thread state mutation corrupts lifecycle | Service lock around transitions, immutable projection snapshots and tkinter-main-thread-only widget updates |
| Application exits during authentication | Registered local cancellation/cleanup path closes listener and disposes candidate; no remote action and no restart |
| Established context becomes stale | Aware next-06:00 Asia/Kolkata validity, pre-operation expiry checks and authoritative invalid-token transition to `EXPIRED` |
| Principal evidence is unavailable | Fail closed as `PRINCIPAL_BINDING_UNAVAILABLE`, availability `INDETERMINATE`, candidate local disposal and no retry |
| Windows backend changes authentication semantics | Provider-neutral `SecureCredentialSource`, identical sanitized categories and shared contract tests for a future Credential Manager backend |
| Governance conflates design with activation | Metadata and all proposed file lists state no implementation/runtime authority; require separate implementation and CAR/runtime approvals |

## A.16 Verification and acceptance obligations

Engineering Verification shall prove:

- every canonical requirement maps to an implemented control or an explicit unresolved blocker;
- owner and dependency directions match ADR-010 and DOMAIN-006;
- typed contracts expose no credential, token, SDK type, Provider payload or raw exception;
- successful Authentication Attempt, authenticated-context and availability transitions are tested as three independent state models;
- the intended-registration reference cannot be compared directly with Provider evidence and all intended-principal resolution outcomes are sanitized;
- Configuration, URL, secret, token and principal-bearing objects have redacted `repr()`, `str()`, serialization, logging and exception behavior;
- `SecretLease`, `IntendedPrincipalLease` and `OneUseRequestToken` are single-use, deterministically closed/invalidated and absent from reachable long-lived state after every terminal path;
- cancellation is idempotent, rejects late callbacks, disposes local state and causes zero Provider calls;
- first-request terminality and its accepted denial-of-service trade-off are deterministic and have no retry;
- Kite expiry is adapter-supplied and no provider-neutral 06:00 rule exists;
- the Version 1.0/1.1 precedence matrix resolves every conflicting effective rule;
- all callback, attempt, candidate, binding and disposal invariants have offline tests;
- the exact Kite `user_id` principal-binding field and strict comparison rule complete Chief Architect review before implementation;
- the proposed file scope is revalidated against the then-current baseline;
- no implementation reopens CAR-011 or CAR-015 or authorizes CAR-014;
- no runtime, browser, credential-use, endpoint or Provider-call authority is inferred from EDD approval; and
- any implementation and any live verification receive separate controlled authority.

## A.17 Canonical disposition

**EDD Status:** Approved — Canonical

**Implementation Authority:** None

**Runtime Authority:** None

**Credential-Use Authority:** None

**Browser/Listener Authority:** None

**SDK/Endpoint Authority:** None

**CAR-016 Status:** Not drafted

**CAR-014 Status:** Unexecuted and unauthorized for execution

**Live Authentication Authority:** None

**Keychain Access Authority:** None

**Instrument Master Authority:** None

**Historical Data Authority:** None

**Quote/LTP/OHLC/WebSocket Authority:** None

**Orders/Trades/Account Mutation Authority:** None

---

# Published Version 1.0 Baseline (Preserved)

# 1. Purpose

This Engineering Design Document defines the provider-neutral engineering design for establishing, maintaining and terminating one trusted Provider Context.

It answers exactly one engineering question:

> How does KRONOS establish, maintain and terminate a trusted Provider Context while preserving approved architectural ownership and boundaries?

The design translates the approved Configuration → Provider architecture into bounded engineering contracts, representations, evidence and verification obligations. It introduces no architectural ownership, new domain, new dependency, implementation authority or runtime authority.

# 2. Scope

EDD-001 covers only the Provider access and Provider Context boundary:

- approved Runtime Configuration consumption through Configuration Eligibility;
- Provider-owned Authentication Activity;
- Authentication Outcome;
- establishment of one Authenticated Provider Context;
- bounded Context Validity;
- Context Invalidation;
- Context Termination;
- Provider Availability;
- Provider Usability;
- non-sensitive provenance and audit evidence;
- failure distinctions required to preserve the approved meanings; and
- engineering verification of the above boundary.

The design is provider-neutral. Provider-specific mechanics remain deferred to separately authorized work.

# 3. Repository Traceability

The design is subordinate to and traceable to:

- `PLATFORM-000` — KRONOS Platform Constitution;
- the Domain Ownership Matrix;
- the Domain Dependency Matrix;
- the Platform Business Pipeline;
- `ENGINE_OWNERSHIP`;
- `DATA_FLOW`;
- ADP-001F — Configuration → Provider Runtime Configuration Boundary;
- ADP-001G — Configuration → Provider Authentication Boundary;
- EAP-001 Version 1.0 — Configuration-to-Provider Authenticated Context Engineering Architecture;
- EAS-001 through EAS-007;
- DOC-001 — Document Identification, Classification & Metadata Standard;
- GOV-002 — Governance Lifecycle; and
- the Document Register.

EAP-001 is the direct engineering authority. ADP-001F and ADP-001G are the direct architectural authorities. Where this document is silent, those authorities prevail.

# 4. Architectural Context

Configuration remains the semantic owner of Runtime Configuration, Configuration Meaning, Configuration Eligibility, Operational Configuration Validity, sensitive classification and Configuration Provenance.

Provider remains the semantic owner of Provider Integration, Authentication Activity, Authentication Outcome, Authenticated Provider Context, Context Validity, Context Invalidation, Context Termination, Provider Usability and Provider Availability.

The Provider Context boundary does not transfer ownership, create a shared owner or join the business decision chain. A Provider Context is a bounded prerequisite and carries no downstream business meaning.

# 5. Business Context

Provider access supports the platform without becoming a business decision. A successful Authentication Outcome allows a bounded Provider Context to be established, but it does not establish a business fact, judgment, permission or action.

The design therefore preserves the separation between operational access and all downstream semantic responsibilities. No downstream consumer may infer a business result from Context Validity, Provider Usability or Provider Availability.

# 6. Responsibilities

## 6.1 Configuration

Configuration shall:

- publish only approved Runtime Configuration meanings;
- establish Configuration Eligibility and Operational Configuration Validity;
- preserve Configuration-owned reason meaning and provenance;
- classify sensitive information; and
- supply eligible meaning through the approved boundary.

Configuration shall not produce Authentication Activity, Authentication Outcome, Authenticated Provider Context or context lifecycle meaning.

## 6.2 Provider

Provider shall:

- consume eligible Configuration meaning;
- perform the separately authorized Authentication Activity;
- produce exactly one Authentication Outcome for an activity;
- establish an Authenticated Provider Context only after Authentication Success;
- determine Context Validity, Context Invalidation and Context Termination;
- produce Provider Usability and Provider Availability; and
- preserve non-sensitive Provider and authentication provenance.

Provider shall not reinterpret Configuration Meaning or create authority outside this boundary.

## 6.3 Engineering Architect

The Engineering Architect owns preparation, traceability and verification of this document. This stewardship does not alter semantic ownership or authorize implementation.

# 7. Out of Scope

EDD-001 does not define or authorize:

- any Provider capability or account-information expansion;
- any dataset acquisition or downstream data operation;
- any canonical identity, semantic interpretation or mapping activity;
- any factual-state publication or business judgment;
- any decision, permission, action, holding or account administration;
- Dataset Permission or Acquisition Authority;
- a generic session abstraction;
- renewal, refresh, replacement or expiry mechanisms;
- APIs, SDKs, payloads, schemas, transport, persistence or databases;
- runtime services, deployment, user-interface behavior or production code; or
- any implementation sequence beyond the contracts and verification obligations in this document.

# 8. Engineering Constraints

The design shall remain:

- provider-neutral;
- implementation-neutral;
- contract-based;
- ownership-preserving;
- dependency-direction preserving;
- non-sensitive by construction at all downstream boundaries; and
- independently verifiable.

No physical field, class, module, package, endpoint, protocol, storage mechanism, executable state machine or provider-specific representation is prescribed.

# 9. Provider Context Architecture

The bounded engineering direction is:

```text
Configuration Eligibility
        ↓
Operational Configuration Validity
        ↓
Authentication Activity
        ↓
Authentication Outcome
        ↓
Authenticated Provider Context
        ↓
Context Validity
        ├── Context Invalidation
        └── Context Termination
```

Provider Availability and Provider Usability remain Provider-owned meanings alongside this flow. They do not replace Authentication Outcome or Context Validity.

One Authentication Activity produces one Authentication Outcome. Only Authentication Success establishes one bounded Authenticated Provider Context. Rejection and Failure establish no context.

## 9.1 Provider Context State Model

The following state model represents approved engineering meanings only:

```text
No Provider Context
        │
        ▼
Authentication Activity
        ├── Authentication Rejection or Authentication Failure
        │       └── No Provider Context
        └── Authentication Success
                ▼
        Authenticated Provider Context
                ▼
        Context Validity
                ├── Context Invalidation
                └── Context Termination
```

The model defines no refresh, renewal, retry, timeout algorithm or implementation behaviour.

## 9.2 Provider Context Boundary

The ownership boundary is:

```text
Configuration
      ↓
Authentication Activity
      ↓
Provider
      ↓
Authenticated Provider Context
      ↓
Later separately authorized engineering capabilities
```

Configuration retains ownership of Configuration meanings. Provider owns Authentication Activity and the Authenticated Provider Context. Later separately authorized engineering capabilities receive only the approved bounded context meaning. This boundary does not participate in the business pipeline and does not introduce implementation components.

# 10. Authentication Activity

Authentication Activity is Provider-owned technical activity using eligible Configuration-owned meaning within an approved Provider and operational context.

### Preconditions

- Configuration Eligibility is established.
- Operational Configuration Validity is established.
- Authentication Eligibility is established where applicable.
- Provider and operational context are approved.
- No invalidating boundary condition is present.

### Postconditions

- Exactly one Authentication Outcome is represented.
- Authentication Success establishes one Authenticated Provider Context.
- Authentication Rejection and Authentication Failure establish no context.
- No Configuration ownership or lifecycle authority is transferred.

The design does not specify how the activity is performed.

# 11. Authentication Outcome

| Outcome | Engineering meaning | Does not establish |
|---|---|---|
| Authentication Success | The approved activity produced the Authentication Outcome Success and establishes one separate Context Establishment meaning for one Authenticated Provider Context. | Provider Capability, Dataset Permission, Acquisition Authority or business meaning. |
| Authentication Rejection | Supplied meaning was not accepted within the attempted activity and no context was established. | Configuration invalidity, withdrawal or supersession. |
| Authentication Failure | The technical activity did not establish a context for a reason distinct from rejection. | Configuration invalidity, Provider Availability or any downstream meaning. |

Authentication Outcome is Provider-owned and remains distinct from Configuration-owned eligibility and validity meanings.

# 12. Authenticated Provider Context

Context Establishment is the separate Provider-owned engineering meaning that one Authenticated Provider Context was established by Authentication Success. The Authenticated Provider Context is the bounded Provider-owned condition itself.

It is bounded by:

- Provider identity;
- authorization and authentication context;
- approved capability context, without creating capability authority;
- Configuration approval context;
- operating environment;
- lifecycle or effective context;
- sensitive classification; and
- approved operational context.

The context contains no raw sensitive material and does not transfer Configuration ownership. It does not imply Provider Capability, Dataset Permission, Acquisition Authority, availability of any dataset or any downstream semantic outcome.

# 13. Context Validity

Context Validity is the Provider-owned meaning that an established Authenticated Provider Context remains valid within its approved boundaries.

Validity shall not be assumed perpetual. A validity determination shall preserve its applicable Provider context, authorization context, approved operational context and non-sensitive provenance.

Context Validity is distinct from:

- Configuration Eligibility;
- Operational Configuration Validity;
- Provider Usability;
- Provider Availability; and
- Authentication Outcome.

Any reuse of an established context requires the already-approved Provider-owned Context Reuse Eligibility meaning and a separately approved operation. This EDD defines no generic reuse mechanism and no scope expansion.

No expiry calculation or time-based mechanism is defined.

# 14. Context Invalidation

Context Invalidation is the Provider-owned determination that an established context can no longer be treated as valid.

Invalidation shall:

- preserve the applicable non-sensitive reason;
- terminate eligibility for further context use within the affected boundary;
- preserve provenance of the invalidation; and
- avoid redefining Configuration Meaning.

Configuration withdrawal, supersession or invalidity remains Configuration-owned and shall not be rewritten as a Provider Authentication Outcome.

# 15. Context Termination

Context Termination is the Provider-owned architectural end of an Authenticated Provider Context.

Termination shall:

- preserve the context identity and non-sensitive termination provenance;
- establish no new authority;
- transfer no ownership; and
- remain distinct from Configuration withdrawal and Provider Availability.

This section defines the engineering meaning only. It does not define cleanup, revocation, persistence or runtime procedures.

# 16. Provider Availability

Provider Availability is a Provider-owned current technical meaning that Provider cannot presently support the relevant approved activity or context use.

Provider Availability is distinct from:

- Configuration Availability;
- Operational Configuration Validity;
- Authentication Rejection;
- Authentication Failure; and
- Context Validity.

Provider Availability does not authorize retry, renewal, refresh or any other activity.

# 17. Provider Usability

Provider Usability is a Provider-owned technical meaning concerning whether supplied eligible Configuration meaning can be used during the separately approved activity.

Provider Usability:

- does not establish Authentication Success;
- does not establish Context Validity;
- does not create Provider Capability;
- does not grant Dataset Permission or Acquisition Authority; and
- does not create downstream business meaning.

Provider Usability shall not be inferred from Configuration Eligibility or Authentication Success alone.

# 18. Service Contracts

These are conceptual engineering contracts, not APIs or runtime services.

## 18.1 Configuration Supply Contract

**Producer:** Configuration
**Consumer:** Provider
**Inputs:** Approved Runtime Configuration meaning, Configuration Eligibility, Operational Configuration Validity, applicable Authentication Eligibility and non-sensitive Configuration provenance.
**Outputs:** Eligible Configuration meaning supplied through the approved Configuration → Provider boundary.
**Preconditions:** Configuration Eligibility, Operational Configuration Validity, approved Provider context and applicable Authentication Eligibility are established.
**Postconditions:** Provider may use the eligible supplied meaning for the separately authorized Authentication Activity; Configuration ownership, sensitivity classification and provenance remain unchanged.
**Failure Conditions:** Configuration ineligibility, invalidity, withdrawal, supersession or unavailable meaning is preserved as Configuration-owned and does not become a Provider Authentication Outcome.

## 18.2 Authentication Activity Contract

**Producer:** Provider
**Consumer:** Provider authentication boundary
**Inputs:** Eligible Configuration meaning and the approved Provider and operational context.
**Outputs:** Exactly one Authentication Outcome.
**Preconditions:** Eligible Configuration meaning is available, the Authentication Activity is authorized within this boundary and no invalidating boundary condition is present.
**Postconditions:** Authentication Success establishes one Authenticated Provider Context; Authentication Rejection and Authentication Failure establish no context.
**Failure Conditions:** Rejection or Failure is represented distinctly, with no conversion into Configuration invalidity, Provider Availability or downstream meaning.

## 18.3 Authenticated Provider Context Contract

**Producer:** Provider
**Consumer:** Later separately authorized engineering capabilities
**Inputs:** Authentication Outcome Success, Context Establishment meaning and applicable non-sensitive Provider provenance.
**Outputs:** One bounded Authenticated Provider Context with its Context Validity meaning and applicable non-sensitive provenance.
**Preconditions:** Authentication Success has been established and the Provider-owned context boundary remains applicable.
**Postconditions:** The bounded context may be consumed only within its approved boundary; no ownership, capability authority or downstream business meaning is created.
**Failure Conditions:** No context is supplied when Authentication Outcome is Rejection or Failure, or when the Provider-owned context cannot be established within the approved boundary.

## 18.4 Context Lifecycle Contract

**Producer:** Provider
**Consumer:** Later separately authorized engineering capabilities
**Inputs:** An established Authenticated Provider Context and Provider-owned lifecycle meaning.
**Outputs:** Context Validity, Context Invalidation or Context Termination as distinct meanings, with applicable non-sensitive provenance.
**Preconditions:** The relevant Authenticated Provider Context exists or an approved termination/invalidation meaning is being recorded for that context.
**Postconditions:** The lifecycle meaning remains Provider-owned and does not redefine Configuration validity or create new authority.
**Failure Conditions:** A lifecycle condition that cannot be represented shall not be silently converted into another lifecycle meaning or into Configuration ownership.

# 19. Event Contracts

Event records are non-sensitive engineering evidence of approved boundary meanings. They are not Platform Event semantics, runtime implementation events or a new event authority.

## 19.1 Provider Context Event Contract

**Producer:** Provider
**Consumer:** Approved engineering observability and audit-evidence consumers
**Event Meaning:** Authentication Activity represented; Authentication Outcome represented; Authenticated Provider Context established; Context Validity changed; Context Invalidation represented; or Context Termination represented.
**Ordering Constraints:** Authentication Activity precedes its Authentication Outcome; Authentication Success precedes Context Establishment; Context Establishment precedes applicable Context Validity, Context Invalidation or Context Termination meaning. Unrelated activities need not share an ordering.
**Ownership:** Provider owns Provider Authentication and context lifecycle meanings. Configuration ownership of Configuration meaning and provenance remains unchanged.
**Failure Behaviour:** Rejection, Failure, Invalidation and Termination preserve their distinct non-sensitive meanings and reasons where available. Missing or ineligible evidence shall not be converted into a different outcome, ownership or downstream meaning.

Each record shall preserve source meaning, applicable context, reason where available and provenance without exposing secrets or reconstructable sensitive information. These fields describe engineering evidence only and prescribe no runtime event mechanism, scheduling or transport.

# 20. Audit and Provenance

Audit evidence shall be read-only and non-sensitive.

Provider provenance shall preserve Provider source context, Provider assertions, technical outcome and context lifecycle evidence.

Configuration provenance shall preserve Configuration authority, approval context and applicable lifecycle meaning without exposing Authentication Material.

Audit evidence shall not:

- acquire ownership of Provider or Configuration meaning;
- alter a source contract;
- create a new decision;
- expose secrets, tokens or reconstructable sensitive content; or
- become a downstream business input.

# 21. Failure Classification

Failure classification shall preserve the approved distinctions:

| Meaning | Owner | Required distinction |
|---|---|---|
| Configuration ineligibility or invalidity | Configuration | Preserve the applicable Configuration-owned reason. |
| Provider Unavailability | Provider | Current Provider technical condition; not Configuration invalidity. |
| Authentication Rejection | Provider | Supplied meaning was not accepted; no context established. |
| Authentication Failure | Provider | Technical activity failed distinctly from rejection; no context established. |
| Context Invalidation | Provider | Existing context is no longer valid. |
| Context Termination | Provider | Existing context has ended. |

No failure category may be silently converted into another category. No provider-specific exception taxonomy is exposed as a cross-domain contract.

# 22. Security Considerations

- Authentication Material remains Configuration-owned.
- Provider may hold supplied sensitive meaning only through bounded Temporary Operational Custody.
- Secrets and tokens shall not enter downstream contracts, event records or audit evidence.
- Provenance shall be non-sensitive and non-reconstructive.
- No durable ownership, redistribution or cross-context reuse is authorized.
- Sensitive classification remains Configuration-owned.
- Security design does not define storage, encryption, masking, secret managers or rotation mechanisms.

# 23. Non-Functional Requirements

EDD-001 shall satisfy the following engineering qualities:

- Provider neutrality;
- deterministic contract meanings;
- explicit ownership;
- bounded context scope;
- distinguishable outcome and failure meanings;
- non-sensitive observability;
- auditable provenance;
- no hidden downstream authority;
- no provider-specific leakage; and
- reproducible Engineering Verification.

These requirements do not prescribe a language, framework, deployment model or runtime mechanism.

# 24. Verification Requirements

Engineering Verification shall demonstrate the following:

| Requirement | Verification Objective | Expected Result | Evidence Required |
|---|---|---|---|
| Ownership separation | Confirm Configuration and Provider responsibilities remain distinct. | Configuration owns Configuration meanings; Provider owns Provider access and context meanings. | Traceability and contract review evidence. |
| Authentication outcome cardinality | Confirm each Authentication Activity produces one Authentication Outcome. | Exactly one Outcome is represented for each activity. | Conceptual contract conformance evidence. |
| Context establishment | Confirm Context Establishment remains separate from Authentication Outcome. | Only Authentication Success establishes one Authenticated Provider Context. | State-model and contract evidence. |
| Rejection and Failure | Confirm non-success outcomes do not establish context. | Authentication Rejection and Authentication Failure establish no context. | Outcome representation evidence. |
| Context lifecycle separation | Confirm Context Validity, Context Invalidation and Context Termination remain distinct. | Each meaning is represented independently and retains its Provider ownership. | Lifecycle contract evidence. |
| Availability and Usability | Confirm Provider Availability and Provider Usability are not conflated. | Each remains a distinct Provider-owned meaning. | Boundary and failure-classification evidence. |
| Authority containment | Confirm Authentication does not imply capability, entitlement, Dataset Permission or Acquisition Authority. | No such authority is produced by this design. | Contract, boundary and negative-conformance evidence. |
| Sensitive containment | Confirm sensitive information cannot cross the approved boundary in contracts, event records or audit evidence. | Only non-sensitive evidence crosses the boundary. | Sensitive-information review evidence. |
| Lifecycle mechanism exclusion | Confirm no generic session abstraction or renewal/refresh mechanism is introduced. | No such abstraction or mechanism is defined. | Scope and design review evidence. |
| Downstream separation | Confirm no downstream business meaning or ownership is introduced. | The context remains a bounded prerequisite only. | Boundary and traceability evidence. |
| Provider neutrality | Confirm Provider-specific mechanics do not leak into provider-neutral contracts. | Contracts contain no Provider-specific implementation representation. | Contract review evidence. |
| Provenance preservation | Confirm provenance remains non-sensitive, attributable and ownership-preserving. | Provider and Configuration provenance remain attributable without ownership transfer. | Provenance and audit evidence. |
| Conceptual contract form | Confirm service and event contracts remain conceptual and implementation-neutral. | No API, runtime event or implementation design is prescribed. | Contract structure review evidence. |
| Authority consistency | Confirm consistency with ADP-001F, ADP-001G and EAP-001. | No conflict with governing architecture or engineering architecture is identified. | Authority traceability matrix and verification record. |

# 25. Architecture Traceability Matrix

| Authority | Requirement preserved by EDD-001 |
|---|---|
| PLATFORM-000 | Single ownership, contract-based dependencies and architecture-before-engineering. |
| Domain Ownership Matrix | Configuration owns Runtime Configuration; Provider owns Provider Integration; no shared ownership. |
| Domain Dependency Matrix | Provider and Configuration remain outside the business decision chain. |
| ADP-001F | Configuration Eligibility, Operational Configuration Validity, sensitive containment and Temporary Operational Custody. |
| ADP-001G | Authentication Eligibility, Activity, Outcome, Authenticated Provider Context and context lifecycle meanings. |
| EAP-001 | Engineering contracts, representations, observability, producer/consumer responsibilities and downstream gates. |
| EAS-001–EAS-006 | Engineering architecture, repository, dependency, interaction, verification and delivery conformity. |
| EAS-007 | EDD lifecycle, traceability, review, approval and separate implementation authorization. |
| DOC-001 / GOV-002 | Controlled metadata, lifecycle and governance traceability. |

# 26. Appendix

## A. Approved Terminology

- Runtime Configuration
- Configuration Meaning
- Configuration Eligibility
- Operational Configuration Validity
- Provider Usability
- Provider Availability
- Authentication Activity
- Authentication Outcome
- Authenticated Provider Context
- Context Validity
- Context Invalidation
- Context Termination
- Temporary Operational Custody
- Configuration Provenance
- Provider Provenance

## B. Authorization Boundaries

- This Draft authorizes no production code.
- This Draft authorizes no runtime deployment or operational activity.
- This Draft authorizes no dataset or downstream semantic operation.
- Implementation requires separate explicit Implementation Authorization.
- Any expansion beyond this Provider Context boundary requires separate Chief Architect authorization.

## C. Review History

- Draft authorization: Chief Architect Draft Authorization approved.
- Corrected Provider Requirements Catalogue incorporated.
- EDD-001 Version 0.1 prepared for Engineering Verification.

## D. Open Verification Questions

- Does the implementation preserve one bounded Provider Context for each successful Authentication Outcome?
- Are all context lifecycle meanings attributable without exposing sensitive information?
- Can every failure meaning be distinguished without provider-specific leakage?
- Does any proposed implementation introduce authority beyond this document?
