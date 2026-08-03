# CAR-017 — Live Composition Layer Implementation Authorization

**Document ID:** CAR-017
**Title:** Live Composition Layer Implementation Authorization
**Version:** 1.2
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-017-LIVE-COMPOSITION-LAYER-IMPLEMENTATION-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVED — CANONICAL COORDINATED VERSION 1.2
**Implementation Authority:** Completed
**Runtime Authority:** None
**Live Authority:** None — Separate Sponsor execution instruction required
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
**CAR-017 Version 1.0 Publication SHA:** `6539e6282d482da0cc7f1f181db74aa4b4d6f692`
**Stage 1 SHA:** `1769dd641e8af1d6ea4eddb7dea8a0d1177a2eb8`
**Stage 2 and Frozen Final Implementation SHA:** `7ea79305b2330721fbb6d5549034b0c05cb6e162`
**Completed Implementation/Test Path Count:** 8
**Coordinated Activation Identity:** `KRONOS-COORD-AUTH-20260803-001`
**Logical CAR-016 Publication Reference:** `CAR-016-V1.2-KRONOS-COORD-AUTH-20260803-001`
**Logical CAR-017 Publication Reference:** `CAR-017-V1.2-KRONOS-COORD-AUTH-20260803-001`
**Actual Coordinated Governance Publication Commit SHA:** `PENDING — ESTABLISHED BY CANONICAL PUBLICATION`

---

# 1. Purpose

CAR-017 Version 1.2 is the CAR-017 half of the canonical coordinated Live Activation Authority identified by `KRONOS-COORD-AUTH-20260803-001`. It governs complete Activation Context validation and the bounded Live Composition Layer.

Version 1.0 authorized the exact two-stage implementation and fake-only verification described below. Version 1.1 recorded completed implementation and EDD-001 Version 1.1 conformance at `7ea79305b2330721fbb6d5549034b0c05cb6e162`. Version 1.2 changes no implementation, production code, pilot code, test, dependency, architecture or Engineering Design.

Canonical publication grants no runtime or live activity by itself. CAR-016 Version 1.2 and CAR-017 Version 1.2 are jointly necessary and individually insufficient. Bounded execution exists only after coordinated governance-only publication, exact coordinated preflight and a later final Sponsor confirmation that cannot define or expand the activation identity.

# 2. Governing Authority

CAR-017 is subordinate to:

- [ADR-010 Version 1.0 — Provider Authentication Shared Platform Capability](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md);
- [DOMAIN-006 Version 1.1 — Provider Domain](../../architecture/platform/domains/provider/ARCHITECTURE.md);
- [EDD-001 Version 1.1 — Provider Authentication and Authenticated Context Establishment Engineering Design](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
- [CAR-016 — coordinated authentication lifecycle authority](CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

CAR-017 cannot amend architecture, DOMAIN-006, ADR-010, EDD-001 or CAR-016 semantics. It supplies only a bounded composition implementation around previously reviewed components.

CAR-016 freezes its completed implementation at `bb5aa16fbc4fda2609376d53161d591fb0fe0d36`; CAR-017 freezes its completed Live Composition Layer at `7ea79305b2330721fbb6d5549034b0c05cb6e162`. Neither frozen implementation or authority record is sufficient alone.

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
- **Version 1.2 — Live activation authority:** canonical coordinated governance permits one bounded live activation only after exact external redirect confirmation, Sponsor-environment verification, protected-custody readiness, successful preflight and a separate explicit Sponsor instruction. Publication itself grants no runtime or live activity.
- **Version 1.3 — Sanitized consumed outcome:** records only approved sanitized evidence and consumed-authority state. It creates no renewed attempt.

Every revision requires separate review, publication, commit and push authority. No revision implies the next.

# 17. Explicitly Withheld Authority

The following remain `NONE` throughout Version 1.0 preparation, implementation and offline verification and Version 1.1 conformance recording:

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

Versions 1.0 and 1.1 also withhold:

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

# 18. Version 1.1 Completed Implementation and Conformance Record

## 18.1 Controlled SHA chain

The completed governed implementation chain is:

| Gate | Exact commit SHA | Controlled result |
|---|---|---|
| CAR-017 Version 1.0 publication | `6539e6282d482da0cc7f1f181db74aa4b4d6f692` | Governance-only staged implementation authority published |
| Stage 1 | `1769dd641e8af1d6ea4eddb7dea8a0d1177a2eb8` | Live composition infrastructure completed |
| Stage 2 | `7ea79305b2330721fbb6d5549034b0c05cb6e162` | Pilot presentation integration completed |

The Stage 2 SHA is the frozen final CAR-017 implementation SHA. The completed implementation consists of exactly these eight authorized paths:

1. `src/kronos/configuration/apple_keychain.py`;
2. `src/kronos/provider/adapters/kite/navigation.py`;
3. `src/kronos/provider/kite/composition.py`;
4. `tools/provider_pilots/car016_provider_authentication_gui.py`;
5. `tests/unit/configuration/test_apple_keychain.py`;
6. `tests/unit/provider/test_kite_login_navigator.py`;
7. `tests/unit/provider/test_kite_authentication_composition.py`; and
8. `tests/unit/tools/test_car016_provider_authentication_gui.py`.

No ninth implementation or test path entered either stage. No architecture, EDD, dependency, configuration, fixture or unrelated Provider path changed.

## 18.2 Verification evidence

| Verification | Result |
|---|---|
| Focused Stage 2 tests | 31 PASSED |
| All CAR-017 focused tests | 116 PASSED |
| Complete offline regression | 643 PASSED |
| Secret scan | PASS |
| Sensitive-material scan | PASS |
| Ordinary direct launch | Inspection-only |
| `LiveActivationContext` ownership | Stage 1 only |
| Live composition responsibility | Wiring only |
| Duplicate authentication or Provider path | ABSENT |
| Real external-effect activity | NONE |
| CAR-014 execution | NO — remains unexecuted |

No verification accessed credentials or Apple Keychain, opened a browser or production listener, constructed a real Kite SDK client, or made a network or Provider call.

## 18.3 EDD-001 Version 1.1 conformance

The frozen implementation conforms to EDD-001 Version 1.1 within the exact CAR-017 scope:

1. `LiveActivationContext` remains immutable, redacted and non-serializable, and Stage 1 exclusively owns its definition, construction, provenance validation, activation-capability validation, type validation, fake/live separation and pre-factory enforcement;
2. Configuration, environment, command-line, module, file, import, successful-test, synthetic, malformed and wrong-provenance material cannot create activation authority;
3. invalid activation is rejected before Keychain, intended-principal, browser, callback-listener, SDK-adapter, service or Provider dependency construction;
4. the Apple Keychain integration remains retrieval-only and preserves separate API-secret and intended-principal purposes;
5. the Kite LoginNavigator preserves the exact governed URL policy, one browser-opener invocation maximum and no retry or fallback;
6. the live composition layer performs wiring only and introduces no authentication, callback, credential, Provider, SDK, context-establishment or availability logic;
7. Stage 2 consumes the already accepted Stage 1 capability through presentation seams only and does not define, validate, mutate, reinterpret, infer, replace or bypass it;
8. ordinary import and direct launch remain effect-free and inspection-only, with all lifecycle controls disabled without accepted activation;
9. Login remains one-shot, availability verification remains separately gated, and GUI close preserves required local cancellation;
10. only sanitized state and outcomes are displayed; and
11. no duplicate authentication, callback, Provider, context-establishment or availability path exists.

All external effects remain deferred behind the existing reviewed seams.

## 18.4 Authority disposition

- **Implementation status:** Complete at `7ea79305b2330721fbb6d5549034b0c05cb6e162`.
- **Further implementation authority:** None.
- **Runtime authority:** None.
- **Live authority:** None.
- **Credential-use authority:** None.
- **Keychain authority:** None.
- **Browser/listener authority:** None.
- **SDK/Provider endpoint authority:** None.
- **Network authority:** None.
- **CAR-014 status:** Unexecuted.

Version 1.1 is a conformance record only. It does not activate Version 1.2, authorize live execution, access any protected value or consume an Authentication Attempt.

# 19. Version 1.2 Canonical Coordinated Live Activation Authority

## 19.1 Frozen coordinated Activation Context and workstation prerequisites

The complete coordinated Activation Context consists only of the following frozen non-sensitive values:

| Field | Exact frozen value |
|---|---|
| Coordinated activation identity | `KRONOS-COORD-AUTH-20260803-001` |
| Logical CAR-016 publication reference | `CAR-016-V1.2-KRONOS-COORD-AUTH-20260803-001` |
| Logical CAR-017 publication reference | `CAR-017-V1.2-KRONOS-COORD-AUTH-20260803-001` |
| Frozen CAR-016 implementation SHA | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` |
| Frozen CAR-017 implementation SHA | `7ea79305b2330721fbb6d5549034b0c05cb6e162` |
| Authority effective | `2026-08-03T20:30:00+05:30`<br>`Asia/Kolkata` |
| Authority expiry | `2026-08-10T20:30:00+05:30`<br>`Asia/Kolkata` |
| Authentication Attempt timeout | `300 seconds` |
| Sponsor environment | `SPONSOR-MACOS-LOCAL-NONPROD-01` |
| Provider identity | `ZERODHA_KITE` |
| Provider configuration | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` |
| Kite application registration | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` |
| Secure credential | `KITE-API-SECRET-PRIMARY` |
| Intended principal registration | `KITE-INTENDED-PRINCIPAL-PRIMARY` |
| Composition dependency set | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` |
| Provider Availability Verification Authority | `WITHHELD` |
| Maximum Provider Availability verification operations | `0` |
| Attempt cardinality | `ONE` |
| Initial coordinated consumption state | `UNUSED` |
| Controlled invalid-activation category | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` |

No value may be renamed, normalized, reinterpreted, derived, inferred, substituted or expanded. The workstation must be exactly `SPONSOR-MACOS-LOCAL-NONPROD-01`. The implementation content must remain identical to both frozen implementation SHAs, the working tree must be clean, and the coordinated package must be within its exact effective and expiry timestamps. No socket bind or other external-effect operation is permitted during preflight.

The two logical publication references above are identifiers, not Git commit SHAs.

```text
Actual Coordinated Governance Publication Commit SHA:
PENDING — ESTABLISHED BY CANONICAL PUBLICATION
```

One coordinated commit containing exactly the three authorized governance files establishes the actual coordinated governance publication SHA. The resulting SHA is obtained only after the coordinated commit is created and pushed, becomes authoritative post-publication evidence, and is not required inside the original publication commit. The post-publication report must record the resulting SHA. No amendment of the original Version 1.2 publication commit is required merely to insert its own SHA.

**Provider Availability Verification Authority:** `WITHHELD`

**Maximum Provider Availability verification operations:** `0`

Sponsor instruction cannot request, enable or imply `verify_provider_availability()`.

CAR-016 Version 1.2 and CAR-017 Version 1.2 are jointly necessary and individually insufficient:

| Authority component | CAR-016 Version 1.2 | CAR-017 Version 1.2 | Coordinated result |
|---|---|---|---|
| Authentication Attempt lifecycle, callback, exchange, principal binding and matched-only context establishment | Required | Insufficient alone | Available only when both exact logical publication references and authoritative post-publication SHA evidence validate |
| Live composition, Activation Context validation and external-effect dependency wiring | Insufficient alone | Required | Available only when both exact logical publication references and authoritative post-publication SHA evidence validate |
| Provider Availability Verification Authority | `WITHHELD` | `WITHHELD` | `WITHHELD` |
| Attempt cardinality | `ONE` | `ONE` | `ONE` coordinated attempt, not one per CAR |
| Consumption state | Shared | Shared | One atomic coordinated `UNUSED` to `CONSUMED` transition |

## 19.2 Exact external redirect verification

Before execution, the Sponsor must supply a current non-sensitive confirmation that the intended official Kite application registration accepts exactly:

```text
http://127.0.0.1:8765/kite/callback
```

The confirmation must identify the Kite application registration only as `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` and confirm the exact scheme, host, port and path. It must contain no API key, API secret, request token, access token, intended principal, Provider principal, account identifier, credential-bearing screenshot or Provider response.

Repository content, Configuration defaults, successful tests, local listener availability, browser behavior or generated login URLs cannot satisfy this gate. Any mismatch, uncertainty or stale confirmation returns a preflight blocker and causes no live activity.

## 19.3 Protected-custody readiness

The Sponsor must attest, without retrieving or exposing either value during preflight, that the execution identity has retrieval-only Apple Keychain readiness for `KITE-API-SECRET-PRIMARY` and `KITE-INTENDED-PRINCIPAL-PRIMARY`. The two purposes remain separate. Both references must match `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` and the validated coordinated Activation Context. The intended-principal registration reference is not a Provider account identifier.

The API key must be available only through the approved Configuration boundary. The API secret and intended principal must not be placed in Configuration values, environment variables, command-line values, module globals, source, `.env`, fixtures, logs, screenshots, documentation, clipboard evidence or GUI fields.

Preflight does not execute `/usr/bin/security`, enumerate Keychain, retrieve a value or test a secret. Failure of the first authorized retrieval after the attempt begins consumes the attempt.

## 19.4 Environment readiness and exact live preflight

Environment readiness requires the reviewed live activation capability whose frozen implementation, Sponsor environment, Provider identity, Provider configuration, Kite application registration, secure-credential, intended-principal and composition dependency-set references exactly match Section 19.1. The dependency set must be `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1`; an offline fake capability or fake dependency set cannot enable a live dependency.

Configuration, environment variables, command-line values, module globals, file presence, imports, successful tests, GUI state and ordinary launch cannot create or substitute for activation. Provider Availability verification must be `WITHHELD`. Any mismatch fails before constructing an external-effect dependency and yields only `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH`.

Every item below must pass before the Sponsor execution instruction is acted upon:

1. CAR-016 Version 1.2 and CAR-017 Version 1.2 have separate Chief Architect approval and are published as one coordinated governance package;
2. `CAR-016-V1.2-KRONOS-COORD-AUTH-20260803-001` and `CAR-017-V1.2-KRONOS-COORD-AUTH-20260803-001` both validate as logical publication references;
3. one coordinated commit containing exactly the three authorized governance files has been created and pushed, and its resulting SHA is recorded in the post-publication report as authoritative post-publication evidence;
4. implementation content matches `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` and `7ea79305b2330721fbb6d5549034b0c05cb6e162`;
5. the current time is within `2026-08-03T20:30:00+05:30` `Asia/Kolkata` and `2026-08-10T20:30:00+05:30` `Asia/Kolkata`;
6. the workstation is `SPONSOR-MACOS-LOCAL-NONPROD-01`;
7. `ZERODHA_KITE`, `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY`, `ZERODHA-KITE-APP-REGISTRATION-PRIMARY`, `KITE-API-SECRET-PRIMARY`, `KITE-INTENDED-PRINCIPAL-PRIMARY` and `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` all match the accepted Activation Context;
8. the exact redirect confirmation in Section 19.2 is current;
9. Keychain readiness in Section 19.3 is attested without retrieval or access;
10. Authentication Attempt timeout is `300 seconds`, attempt cardinality is `ONE`, coordinated consumption state is `UNUSED`, Provider Availability Verification Authority is `WITHHELD`, and Maximum Provider Availability verification operations is `0`;
11. the local branch is `develop`;
12. local `develop` is aligned with `origin/develop`;
13. `HEAD` equals the resulting coordinated governance publication SHA recorded in the post-publication report;
14. the working tree is clean;
15. the final Sponsor execution instruction includes the resulting coordinated governance publication SHA;
16. no proxy, capture, inspection, diagnostic or logging tool can retain sensitive request or callback material;
17. no socket is bound and no external-effect dependency is constructed or invoked during preflight;
18. port `8765` has no alternate port, host or fallback;
19. CAR-014 remains unexecuted; and
20. final Sponsor confirmation is obtained only after complete coordinated Activation Context validation.

Any failed or unproven item returns `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH`. Preflight failure performs no credential retrieval, listener bind, SDK construction, browser opening, network activity or Provider call and does not consume the coordinated authority. Sponsor instruction cannot define or expand the activation identity. Any ambiguity returns to the Chief Architect.

## 19.5 Exact one-attempt boundary and live sequence

Version 1.2, if approved and published together with CAR-016 Version 1.2, authorizes attempt cardinality `ONE`. The two records are jointly necessary and individually insufficient.

The exact sequence is:

1. validate the complete coordinated Activation Context;
2. obtain final Sponsor confirmation;
3. atomically mark coordinated authority `CONSUMED`;
4. reserve the one Authentication Attempt;
5. construct the one listener;
6. bind the listener under the canonical loopback callback contract as the first socket operation, with no alternate port or retry;
7. generate one official Kite Login URL;
8. launch one browser;
9. receive one terminal callback;
10. retrieve `KITE-API-SECRET-PRIMARY` from Keychain once;
11. exchange the accepted request token once;
12. isolate the resulting candidate Provider Context;
13. retrieve `KITE-INTENDED-PRINCIPAL-PRIMARY` from Keychain once;
14. perform one principal profile verification;
15. on `MATCHED` only, establish one authenticated context; and
16. perform local-only cleanup and retain only sanitized projections.

No socket bind occurs during preflight. Listener bind is the first socket operation. Bind failure occurs after the atomic consumption transition and consumes authority.

Authorized live-operation counts are therefore:

| Operation | Maximum coordinated cardinality |
|---|---:|
| Authentication Attempt | `ONE` |
| Listener | `ONE` |
| Official login URL generation | `ONE` |
| Browser launch | `ONE` |
| Terminal callback | `ONE` |
| API-secret Keychain retrieval | `ONE` |
| Request-token exchange | `ONE` |
| Intended-principal Keychain retrieval | `ONE` |
| Principal profile verification | `ONE` |
| Matched-only authenticated-context establishment | `ONE` |
| Local-only cleanup | `ONE` bounded cleanup sequence |
| Provider Availability verification | `0 — WITHHELD` |

The Authentication Attempt timeout is `300 seconds`. The two protected-store reads are purpose-separated. Neither authorizes enumeration, writing, updating, deletion or any other Keychain operation. Sponsor instruction cannot request, enable or imply `verify_provider_availability()`.

## 19.6 Consumption boundary

The coordinated authority begins in state `UNUSED`. Preflight and inspection-only launch do not consume authority. After complete Activation Context validation and final Sponsor confirmation, the coordinated state is atomically changed to `CONSUMED` before Authentication Attempt reservation and listener construction.

After consumption, every success, failure, cancellation, timeout, listener-bind failure, browser failure or decline, callback rejection, credential failure, exchange failure, principal-resolution failure, principal mismatch, Provider failure, context-establishment failure or local-cleanup failure terminates the authority. No corrected credential, second click, retry, reprobe, second callback, second browser flow, second exchange or automatic reauthentication is permitted.

If coordinated validation fails before consumption, no live operation starts and the controlled outcome is `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH`. After consumption, bind failure and every other terminal outcome consume authority.

The Engineering Architect cannot renew consumed or failed live authority. Any later Authentication Attempt requires fresh Chief Architect live authority and a new explicit Sponsor instruction. Any ambiguity returns to the Chief Architect.

## 19.7 Explicitly withheld operations and authorities

Version 1.2 does not authorize:

- Provider Availability verification, which remains `WITHHELD`, or any second `profile()` operation;
- retry, a second Authentication Attempt, second browser launch, second callback, second exchange or alternate token;
- request-token refresh, access-token refresh, remote token invalidation, Provider logout or remote session termination;
- Instrument Master, historical data, quote, LTP, OHLC, WebSocket or streaming;
- trading, order placement, order modification, order cancellation, GTT or any Provider mutation;
- orders, trades, holdings, positions, funds, margins or account-resource access;
- credential, token, principal, callback query, profile payload, SDK response or Provider data persistence;
- an alternate callback host, port, method or path;
- background execution, polling, scheduling, automation or deployment;
- CAR-014 execution; or
- any architecture, EDD, production, pilot, test, dependency or configuration change.

End KRONOS Session and cancellation remain local-only and must not invoke Provider-side invalidation or mutation.

## 19.8 Version 1.3 sanitized outcome record

After the coordinated attempt ends, both CAR records are consumed and a coordinated documentation-only CAR-016 Version 1.3 and CAR-017 Version 1.3 package may record only:

- coordinated activation identity;
- both Version 1.2 logical publication references, the resulting coordinated governance publication SHA from authoritative post-publication evidence, and both frozen implementation SHAs;
- effective and expiry timestamps and sanitized execution date and time;
- `SPONSOR-MACOS-LOCAL-NONPROD-01`, `ZERODHA_KITE`, `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY`, `ZERODHA-KITE-APP-REGISTRATION-PRIMARY`, `KITE-API-SECRET-PRIMARY`, `KITE-INTENDED-PRINCIPAL-PRIMARY` and `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` as non-sensitive references only;
- Authentication Attempt timeout and final coordinated consumption state;
- one sanitized outcome category, including `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` where applicable;
- sanitized Authentication Attempt, authenticated-context and Provider Availability states;
- actual counts for every operation in Section 19.5;
- confirmation of final Sponsor confirmation, no retry, no alternate port and no second attempt;
- confirmation that Provider Availability verification remained `WITHHELD` and was not invoked;
- local-only cleanup result;
- confirmation that no secret, token, principal, callback query, account detail, raw exception or Provider payload was logged or retained; and
- confirmation that no other Provider endpoint or Provider mutation occurred.

Version 1.3 must not retain an API key, API secret, request token, access token, intended or observed principal, account identifier, callback URL/query, header, raw SDK or Provider exception, traceback, profile response or browser history. Controlled failure categories are required in place of raw exception text.

# 20. Canonical Disposition

CAR-017 Version 1.2 is Approved and Canonical through coordinated publication with CAR-016 Version 1.2. Publication alone does not initiate execution or grant runtime or live activity. Successful exact preflight and later final Sponsor confirmation are mandatory.

**Implementation Status:** Completed at `7ea79305b2330721fbb6d5549034b0c05cb6e162`

**Further Implementation Authority:** None

**Runtime Authority:** None

**Live Authority:** None — Separate Sponsor execution instruction required

**Provider Availability Verification:** WITHHELD

**External-Effect Authority:** None

**CAR-014:** Unexecuted and unauthorized

# 21. References

- [ADR-010 Version 1.0](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md)
- [DOMAIN-006 Version 1.1](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [EDD-001 Version 1.1](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md)
- [CAR-016 coordinated authority record](CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md)
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)
