# CAR-017 — Live Composition Layer Implementation Authorization

**Document ID:** CAR-017
**Title:** Live Composition Layer Implementation Authorization
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-017-LIVE-COMPOSITION-LAYER-IMPLEMENTATION-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVED FOR CANONICAL PUBLICATION WITH FINAL CONDITIONS
**Implementation Authority:** Authorized with Constraints — Stage 1 only after publication
**Runtime Authority:** None
**Live Authority:** None
**Credential Authority:** None
**Keychain Authority:** None
**Browser Authority:** None
**Listener Authority:** None
**SDK Authority:** None
**Provider Endpoint Authority:** None
**Network Authority:** None
**Trading Authority:** None
**CAR-014 Authority:** None
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Exact Implementation Baseline:** `8c401890f1bfd8bf587621d7f31d2f7f75f531c8`
**Frozen Upstream CAR-016 Implementation SHA:** `bb5aa16fbc4fda2609376d53161d591fb0fe0d36`
**Exact Implementation/Test Path Count:** 8

---

# 1. Purpose

CAR-017 Version 1.0 is the bounded implementation authority for the Live Composition Layer required to assemble the completed CAR-016 authentication platform into a reviewed live-capable but externally inert composition.

Canonical publication activates Stage 1 implementation and fake-only verification only. It grants no Stage 1 commit or push without the separate gates in Section 14 and no runtime, credential, Keychain, browser, listener, SDK, Provider endpoint, network, trading, live-execution or CAR-014 authority.

Stage 2 and all external effects remain withheld.

# 2. Governing Authority

CAR-017 is subordinate to:

- [ADR-010 Version 1.0 — Provider Authentication Shared Platform Capability](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md);
- [DOMAIN-006 Version 1.1 — Provider Domain](../../architecture/platform/domains/provider/ARCHITECTURE.md);
- [EDD-001 Version 1.1 — Provider Authentication and Authenticated Context Establishment Engineering Design](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
- [CAR-016 Version 1.1 — completed implementation and conformance](CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

CAR-017 cannot amend architecture, DOMAIN-006, ADR-010, EDD-001 or CAR-016 semantics. It supplies only a bounded composition implementation around previously reviewed components.

CAR-016 Version 1.1 freezes the completed implementation at `bb5aa16fbc4fda2609376d53161d591fb0fe0d36`. The final accepted CAR-017 Stage 2 SHA becomes the future Live Composition Layer baseline. CAR-016 Version 1.2 must later reference that final CAR-017 SHA before any live activation can be considered.

# 3. Exact Implementation Scope

The following is the sole authoritative enumeration of the implementation and test scope. Each path appears once, has one path identifier and belongs to one stage. No ninth path is authorized.

## 3.1 Production

1. **P1** — `src/kronos/configuration/apple_keychain.py`
2. **P2** — `src/kronos/provider/adapters/kite/navigation.py`
3. **P3** — `src/kronos/provider/kite/composition.py`

## 3.2 Pilot presentation

4. **P4** — `tools/provider_pilots/car016_provider_authentication_gui.py`

## 3.3 Tests

5. **P5** — `tests/unit/configuration/test_apple_keychain.py`
6. **P6** — `tests/unit/provider/test_kite_login_navigator.py`
7. **P7** — `tests/unit/provider/test_kite_authentication_composition.py`
8. **P8** — `tests/unit/tools/test_car016_provider_authentication_gui.py`

No package export, dependency, configuration, fixture, documentation, production, pilot or test path may be added to an implementation-stage change.

# 4. Exact Stage Allocation

Every path identifier from Section 3 is allocated exactly once.

## 4.1 Stage 1 — Live composition infrastructure

**Allocation:** P1, P2, P3, P5, P6 and P7.

Stage 1 implements:

- retrieval-only intended-principal resolution through the existing injected Apple Keychain subprocess seam;
- strict API-secret and intended-principal purpose separation;
- one concrete Kite LoginNavigator behind an injected browser opener;
- the immutable `LiveActivationContext` type and its activation-capability provenance;
- provenance validation, activation-capability validation and type validation;
- immutable construction, redacted representation and prohibited serialization;
- fake/live activation separation and pre-factory safe-construction validation;
- rejection of invalid activation before any external-effect dependency construction;
- the externally inert Kite composition root; and
- fake-only tests for those responsibilities.

Proposed Stage 1 commit message:

```text
feat(authentication): add live composition infrastructure
```

The proposed message grants no commit authority.

## 4.2 Stage 2 — Pilot presentation integration

**Allocation:** P4 and P8.

Stage 2 receives an already accepted Stage 1 `LiveActivationContext`.

Stage 2 integrates it through presentation seams only.

Stage 2 implements:

- presentation integration using the already accepted Stage 1 activation capability;
- preservation of effect-free import and inspection-only ordinary launch;
- presentation-only consumption of the accepted capability; and
- fake-only presentation tests.

Stage 2 cannot create, redefine, validate, extend, mutate, reinterpret, infer, replace or bypass `LiveActivationContext`.

Stage 2 does not define or own `LiveActivationContext`, weaken or extend its semantics, change composition semantics, add an alternative activation mechanism, or infer activation from GUI state, Configuration, environment or module state.

Proposed Stage 2 commit message:

```text
feat(provider-pilot): integrate CAR-017 live composition
```

The proposed message grants no commit authority.

## 4.3 Stage allocation invariant

No path is shared between stages. Stage 2 may not amend a Stage 1 allocation. If any cross-stage amendment becomes necessary, work stops and the Engineering Architect must issue a revised scope, baseline and stage instruction.

# 5. Composition Rules

The composition layer performs wiring only.

It introduces:

- no authentication logic;
- no Provider logic;
- no callback logic;
- no credential logic; and
- no SDK logic.

It only composes previously reviewed components. The existing components retain their approved responsibilities:

- Configuration supplies validated non-secret meanings and protected references;
- the Apple Keychain backend owns retrieval mechanics;
- the intended-principal resolver owns one-operation protected resolution;
- the LoginNavigator owns one sanitized browser-opening boundary;
- the loopback component owns callback transport mechanics;
- the Kite adapter owns SDK translation and opaque client containment;
- the Provider Authentication Service owns Authentication Attempt, callback acceptance, candidate isolation, principal binding and authenticated-context establishment;
- the Kite facade preserves provider-specific context-expiry policy; and
- Presentation receives sanitized projections only.

The composition layer shall not introduce:

- a second authentication lifecycle;
- a second callback lifecycle;
- a second Provider path;
- a second context-establishment path; or
- a second availability path.

The authoritative path remains unchanged:

```text
Presentation
    -> KiteProvider
    -> KiteAuthentication
    -> ProviderAuthenticationService
    -> existing injected contracts and Kite adapter
```

No direct exchange-to-context path, principal-binding bypass, immediate `AVAILABLE` state, remote token invalidation or alternate supported authentication path may be added.

# 6. LiveActivationContext

Stage 1 shall define and implement the immutable `LiveActivationContext` used only as the reviewed activation capability boundary.

Stage 1 exclusively owns:

- definition of the `LiveActivationContext` type;
- immutable construction;
- provenance validation;
- activation-capability validation;
- type validation;
- redacted representation;
- prohibited serialization;
- fake/live activation separation;
- pre-factory safe-construction validation; and
- rejection before any external-effect dependency construction.

It contains only non-sensitive references required to compose the existing implementation:

- activation-authority reference;
- frozen implementation SHA reference;
- Sponsor environment reference;
- Provider configuration reference;
- secure-credential reference;
- intended-principal registration reference;
- composition dependency-set reference; and
- separately authorized availability-verification authority reference, when one exists.

It stores no:

- API key or API secret;
- request token or access token;
- intended or observed principal value;
- callback target, query or callback data;
- SDK or HTTP-session handle;
- candidate or authenticated Provider Context;
- Provider payload; or
- raw exception.

The type shall be immutable, non-serializable and redacted in `repr()` and `str()`. Ordinary Configuration and environment values cannot create, substitute for or activate this capability.

During CAR-017 Version 1.0 implementation and testing, only synthetic fake activation contexts may exist. No context carries live authority.

Stage 1 shall prove that `LiveActivationContext` cannot be created, inferred, enabled or substituted by:

- Configuration values;
- environment variables;
- command-line values;
- module globals;
- file presence;
- successful module imports;
- successful offline tests;
- successful dependency construction; or
- ordinary GUI launch.

Stage 1 shall additionally prove:

- synthetic activation cannot create activation;
- malformed activation cannot create activation; and
- wrong-provenance activation cannot create activation.

Only an explicitly injected, reviewed activation capability may satisfy the activation contract. Version 1.0 tests inject only a fake capability with reviewed provenance; this does not create live authority.

# 7. Safe Construction Gate

Before constructing any external-effect dependency, the composition boundary shall verify all of the following using only local, non-sensitive state and injected seams:

1. the activation capability is the reviewed immutable type;
2. activation state is eligible for composition;
3. the composition is complete and contains every required dependency seam;
4. injected dependency factories are present and callable;
5. the frozen implementation reference is present; and
6. availability-verification authority remains separately represented.

Failure of any check prevents construction of every external-effect dependency. The failure returns only a sanitized local category and shall not:

- execute Keychain retrieval;
- create or bind a listener;
- invoke a browser opener;
- construct a Kite SDK client;
- generate a login URL;
- create an Authentication Attempt;
- invoke a Provider endpoint; or
- retry composition.

Dependency availability in this gate means the local injected seam is structurally available. The gate shall not probe an operating-system service, browser, socket, SDK or Provider to determine availability.

Stage 1 fake-only safe-construction tests shall prove that invalid, synthetic, malformed, unreviewed or wrong-provenance activation material is rejected before constructing:

- Apple Keychain source;
- IntendedPrincipalResolver;
- Browser opener;
- Callback listener;
- Kite SDK adapter;
- ProviderAuthenticationService composition; or
- Provider endpoint dependencies.

No external-effect factory may run before activation validation succeeds. Rejection shall occur before any related factory or effect seam is invoked. Required evidence includes separate zero-call counters for the Apple Keychain source, IntendedPrincipalResolver, Browser opener, Callback listener, Kite SDK adapter, ProviderAuthenticationService composition and Provider endpoint dependency factories or seams.

# 8. Inspection Mode and Activation Separation

The required inspection behavior is:

```text
Direct import
    -> no activity

Direct construction
    -> no activity

Direct GUI launch
    -> inspection only
```

Under Version 1.0 ordinary launch:

- Login is disabled;
- Verify Provider Availability is disabled;
- End KRONOS Session is disabled;
- no live composition is created;
- no activation context is inferred; and
- no external-effect dependency is constructed.

Configuration values must never activate live composition.

Environment variables must never activate live composition.

Command-line values, module globals, file presence, successful import, successful tests and canonical publication must never activate live composition.

Successful dependency construction and ordinary GUI launch must never activate live composition.

Only an explicitly injected reviewed activation capability may make the reviewed composition path eligible, and only later live authority may permit that eligible path to exercise an external effect.

The existing offline fake activation capability and the reviewed live activation capability are non-interchangeable. A fake activation must reject any real Keychain runner, browser opener, production listener factory, real SDK factory or Provider adapter factory.

# 9. Frozen Keychain Convention

CAR-017 freezes this retrieval-only naming convention:

```text
service = com.project-kronos.provider-authentication.<lower-provider>
API-secret account = api-secret:<credential_ref>
intended-principal account = intended-principal:<intended_registration_ref>
command = /usr/bin/security find-generic-password -w -s <service> -a <account>
```

The API-secret and intended-principal account purposes are distinct and not interchangeable. All reference components must satisfy the existing protected-reference allow-list. The intended registration reference is internal and is not a Provider account identifier.

No secret or principal value enters the command vector. Only successful stdout may supply the one-use value. Stdout and stderr are immediately consumed, never logged and never retained as evidence. API-secret retrieval produces only a one-use secret lease. Intended-principal retrieval supplies only a one-operation intended-principal lease within the resolver callback.

Keychain writes, updates, deletion, enumeration, provisioning and UI collection are prohibited. Version 1.0 implementation and tests shall not execute the real system command or access a real Keychain.

# 10. Frozen Kite Login URL Policy

The Kite LoginNavigator may accept only a URL satisfying every condition below:

1. scheme is exactly `https`;
2. hostname is exactly `kite.zerodha.com`;
3. username and password are absent;
4. an explicit non-default port is absent;
5. path is exactly `/connect/login`;
6. fragment is absent;
7. query contains exactly one non-empty `api_key` value;
8. query contains exactly one `v=3` value;
9. no duplicate, blank or unexpected query field exists; and
10. canonical parsing succeeds without normalization to another destination.

The navigator invokes the injected browser opener at most once. A rejected URL invokes it zero times. A false opener result becomes `DECLINED`; an exception becomes `FAILED`; only a positive result becomes `OPENED`. There is no fallback browser, retry, URL logging, exception retention, command-line browser invocation or browser-process inspection.

If the reviewed SDK behavior cannot satisfy this policy, implementation stops. The policy may not be weakened without revised authority.

# 11. Composition-Root Contract

The composition root assembles this dependency chain:

```text
LiveActivationContext
    -> ProviderAuthenticationConfiguration reference
    -> AppleKeychainCredentialSource
    -> AppleKeychainIntendedPrincipalResolver
    -> Kite LoginNavigator
    -> LoopbackAuthenticationCallbackListener factory
    -> Kite authentication adapter factory
    -> ProviderAuthenticationService
    -> KiteAuthentication
    -> KiteProvider
```

The composition factory returns only the existing supported Kite Provider authentication facade. It exposes no credential, token, principal, callback, candidate, SDK-client, HTTP-session or raw-service getter.

Import and safe construction perform no external activity. The composition does not create an Authentication Attempt and does not call availability verification. Once later live authority exists, the existing service remains responsible for the ordering after explicit Login:

```text
begin_login()
    -> create and bind exact loopback listener
    -> prove listener READY
    -> construct deferred Kite adapter
    -> generate one official login URL
    -> request one browser open
    -> await one callback
```

Port `8765` failure is fail-closed. There is no alternate port, hostname substitution, wildcard bind, listener retry or browser navigation before readiness.

# 12. Version 1.0 External-Effect Boundary

Version 1.0 implementation and tests use only fakes for:

- Keychain;
- Intended Principal;
- Browser;
- Listener;
- SDK; and
- Provider.

There is no live dependency. Tests use injected subprocess results, synthetic intended-principal leases, fake browser openers, fake listener/server seams, fake adapter factories and synthetic Provider results only.

No test may access the real Keychain, bind production port `8765`, open a browser, construct the real Kite SDK, make a network request or invoke a Provider endpoint.

# 13. Availability Separation

Composition alone cannot verify Provider availability. A newly established context retains availability `NOT_VERIFIED`.

Verify Provider Availability remains disabled unless:

1. the context is `ACTIVE`;
2. a later live-activation authority expressly includes one verification operation; and
3. the Sponsor explicitly initiates it within that authority.

Authentication authority does not imply availability-verification authority.

# 14. Commit, Push and Stage Gates

## 14.1 Stage 1 gate

Stage 1 permits exactly one reviewed commit and exactly one separately authorized push after Engineering Architect evidence acceptance.

Required evidence includes:

- starting branch and exact SHA;
- complete Stage 1 diff and allocation proof;
- EDD-001 conformance mapping;
- focused tests and full offline regression;
- Keychain purpose-separation evidence;
- URL-policy and browser-call evidence;
- safe-construction and zero-external-effect evidence;
- activation provenance/type validation and activation-source prohibition evidence;
- zero-call counters for every prohibited external-effect factory or seam;
- listener-readiness-before-browser and fixed-port evidence;
- secret and sensitive-material scans;
- `git diff --check`; and
- clean post-push alignment.

The accepted pushed Stage 1 commit becomes the frozen Stage 1 SHA.

## 14.2 Stage 2 gate

Stage 2 starts only after both:

1. the accepted Stage 1 commit has been pushed and its SHA frozen; and
2. the Engineering Architect issues explicit Stage 2 start authority naming that SHA.

Stage 2 permits exactly one reviewed commit and exactly one separately authorized push after Engineering Architect evidence acceptance.

Required evidence includes:

- accepted pushed Stage 1 SHA and clean alignment;
- complete Stage 2 diff and allocation proof;
- focused Stage 2, all CAR-017 focused and full offline regression results;
- direct-import, direct-construction and ordinary-launch zero-activity evidence;
- presentation-seam evidence that the already accepted Stage 1 capability is passed without interpretation;
- proof that Stage 2 only consumes the accepted Stage 1 capability and does not define or alter it;
- proof that Stage 2 neither changes composition semantics nor adds an activation mechanism;
- one-Login and no-retry evidence;
- separately gated availability evidence;
- sanitized-state and no-sensitive-field evidence;
- exact eight-path completion verification;
- secret and sensitive-material scans;
- `git diff --check`; and
- clean post-push alignment.

Evidence acceptance, commit authority, push authority and next-stage authority are separate decisions. No proposed commit message grants authority.

# 15. Mandatory Stop Conditions

Work stops and escalates to the Engineering Architect if:

- CAR-016 semantics change;
- CAR-016 implementation changes, except the single bounded pilot-presentation injection seam expressly allocated by P4;
- any ninth implementation or test path is required;
- architecture changes;
- EDD-001 changes;
- a dependency is added;
- a dependency version changes;
- a live dependency is required for implementation or verification;
- an unrelated Provider refactor is required;
- a public contract expands beyond the immutable activation capability and bounded composition factory expressly defined here;
- a second authentication, callback, Provider, context-establishment or availability path appears;
- Keychain purpose separation cannot be preserved;
- the Kite login URL policy cannot be preserved;
- listener readiness cannot precede browser navigation;
- port `8765` requires fallback;
- fake activation can enable live dependencies;
- availability verification cannot remain separately gated;
- CAR-014 is affected; or
- sensitive material appears in logs, errors, representation or retained evidence.

The required disposition is:

```text
STOP — ESCALATE TO ENGINEERING ARCHITECT
```

# 16. Controlled Revision Lifecycle

- **Version 1.0 — Implementation authority:** after separate canonical publication, activates Stage 1 only and governs the two-stage fake-only implementation lifecycle. It grants no live authority.
- **Version 1.1 — Implementation conformance:** records accepted Stage 1 and Stage 2 SHAs, final eight-path completion, offline verification and the frozen final CAR-017 implementation SHA. It grants no live authority.
- **Version 1.2 — Live activation authority:** may authorize one bounded live activation only after Version 1.1 publication, exact external redirect confirmation, Sponsor-environment verification, protected-custody readiness and separate Chief Architect approval.
- **Version 1.3 — Sanitized consumed outcome:** records only approved sanitized evidence and consumed-authority state. It creates no renewed attempt.

Every revision requires separate review, publication, commit and push authority. No revision implies the next.

# 17. Explicitly Withheld Authority

The following remain `NONE` throughout Version 1.0 preparation, implementation and offline verification:

- Runtime;
- Credentials;
- Keychain;
- Browser;
- Listener;
- SDK;
- Provider Endpoints;
- Network;
- Trading; and
- CAR-014.

Version 1.0 also withholds:

- live authentication;
- real activation-context creation;
- real API-key, API-secret, intended-principal, request-token or access-token use;
- real callback receipt;
- login URL generation through a real SDK;
- request-token exchange or `generate_session()`;
- principal-profile verification;
- Provider availability verification;
- retry or a second attempt;
- remote token invalidation or remote logout;
- Instrument Master, historical data, quote, LTP, OHLC and WebSocket;
- orders, trades, holdings, positions, funds, margins and every Provider mutation;
- credential, token, principal, callback or Provider-payload persistence;
- `.env`, source, fixture, command-line, log, screenshot or documentation credential writes;
- deployment, polling, scheduling or automatic login; and
- commit or push without the exact applicable gate.

# 18. Canonical Disposition

CAR-017 Version 1.0 is Approved and Canonical upon synchronization of its authorized governance-only publication commit to `origin/develop`.

Publication activates Stage 1 implementation and fake-only verification only. Stage 1 evidence acceptance, commit and push remain separately gated. Stage 2, Version 1.1 conformance, Version 1.2 live activation and Version 1.3 outcome recording each remain separately governed.

**Implementation Authority:** Authorized with Constraints — Stage 1 only after publication

**Runtime Authority:** None

**Live Authority:** None

**External-Effect Authority:** None

**CAR-014:** Unexecuted and unauthorized

# 19. References

- [ADR-010 Version 1.0](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md)
- [DOMAIN-006 Version 1.1](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [EDD-001 Version 1.1](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md)
- [CAR-016 Version 1.1](CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md)
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)
