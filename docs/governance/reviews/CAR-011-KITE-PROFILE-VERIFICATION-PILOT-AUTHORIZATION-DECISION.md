# CAR-011 — Kite Profile Verification Pilot Authorization Decision

**Document ID:** CAR-011
**Title:** Kite Profile Verification Pilot Authorization Decision
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md`
**Workflow Stage:** Repository Publication
**Decision Status:** APPROVED
**Decision:** APPROVE WITH CONDITIONS
**Priority:** P0
**Register Disposition:** None
**Draft Authorization:** None
**Implementation Authorization:** None
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Inspected Baseline:** `2cbfcbe923d9a93a8af336a29c1324602a8c0656`
**Publication Date:** 2026-07-30
**Authority Expiry Date:** 2026-08-06
**Outcome Revision:** CAR-011 Version 1.1
**Authority Status:** Consumed
**Consumption Basis:** Failed authorized attempt
**Sanitized Outcome Category:** ACCESS_TOKEN_INVALID_OR_EXPIRED

---

# 1. Purpose

This Chief Architect decision authorizes one Sponsor-initiated, bounded, authenticated, read-only Kite profile-connectivity verification attempt through the existing `KiteConnectivityService.probe()` path.

The pilot exists only to verify that one supplied Kite API key and existing access token can complete one `KiteConnect.profile()` operation through the already implemented EP-004 connectivity boundary. It does not verify market data, Provider capability, Provider entitlement, Instrument Master acquisition, Instrument interpretation, Observation, Market Facts, Validation, Risk, Execution, Portfolio, account state or trading readiness.

This decision creates no architecture, engineering meaning, general implementation acceptance or continuing runtime authority.

# 2. Repository Basis

CAR-011 is issued against:

- repository `emiali-jason/Project-Kronos`;
- authoritative branch `develop`;
- inspected baseline commit `2cbfcbe923d9a93a8af336a29c1324602a8c0656`;
- [EP-004 — Minimum Read-Only Kite Connectivity](../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md);
- [EDD-001 — Provider Access and Provider Context Engineering Design](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
- [EDD-002 — Provider Capability Assessment Engineering Design](../../engineering/edd/EDD-002-PROVIDER-CAPABILITY-ASSESSMENT-ENGINEERING-DESIGN.md);
- [EDD-003 — Provider Entitlement Assessment Engineering Design](../../engineering/edd/EDD-003-PROVIDER-ENTITLEMENT-ASSESSMENT-ENGINEERING-DESIGN.md);
- [EDD-004 — Provider Instrument Master Acquisition Engineering Design](../../engineering/edd/EDD-004-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-ENGINEERING-DESIGN.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

EP-004 is the implementation basis for the narrow profile-connectivity path. EDD-001 through EDD-004 retain only the authority recorded in their own metadata and governing decisions.

# 3. Chief Architect Decision

> **APPROVE WITH CONDITIONS**

Upon controlled publication and synchronization of CAR-011 to `develop`, authorize:

1. the documentation-only pre-pilot publication defined by this decision;
2. the bounded pre-execution verification defined by this decision;
3. after every pre-execution condition is proven and the Sponsor gives explicit execution instruction, exactly one invocation of the existing `KiteConnectivityService.probe()` path in one local non-production environment;
4. exactly one authenticated `KiteConnect.profile()` request within that invocation;
5. minimum response-shape validation and immediate in-memory payload discard inside the existing adapter;
6. local client and HTTP-session cleanup only where it invokes no Provider endpoint and performs no Provider-side mutation; and
7. one documentation-only Version 1.1 revision of this same CAR-011 record containing only the approved sanitized outcome.

No authority shall be inferred beyond these grants.

# 4. Historical Implementation Governance

Implementation acceptance for EDD-001, EDD-002 and EDD-003 remains withheld.

Repository implementations described as EDD-001, EDD-002 or EDD-003 implementations are governance-nonconforming historical implementations under controlled quarantine. Controlled quarantine means:

- the historical implementation remains unchanged for traceability;
- repository presence, commit history, tests and passing results do not establish implementation acceptance;
- no retrospective implementation acceptance is granted;
- no remediation, refactoring, activation, extension or runtime use is authorized by this decision; and
- CAR-011 does not resolve or reinterpret the governing EDD authority discrepancy.

The pilot is authorized only through the existing EP-004 profile-connectivity path. It shall not enter the EDD-001 authentication lifecycle, EDD-002 capability-assessment runtime or EDD-003 entitlement-assessment runtime.

# 5. EDD-004 Editorial Correction Authority

CAR-011 authorizes one editorial correction to the stale sentence in the EDD-004 Executive Summary that describes EDD-004 as Version 0.1 and not approved or canonicalized.

The correction shall state that EDD-004 is Version 1.0, Approved and Canonical, while Implementation Authorization and Runtime Authority remain None.

This editorial authority:

- does not change EDD-004 Version 1.0;
- does not change engineering scope, responsibilities, capabilities, Building Blocks, interfaces, exclusions or authority boundaries;
- does not grant implementation, runtime, endpoint, acquisition, persistence, submission, interpretation or product authority; and
- does not authorize any other EDD-004 amendment.

# 6. Exact Pilot Boundary

The authorized pilot begins only when the Sponsor explicitly instructs execution after all Section 11 conditions are proven.

The execution boundary is:

```text
Existing ephemeral Configuration inputs
    → existing KiteConnectivityService.probe()
    → existing profile-only Kite adapter
    → exactly one KiteConnect.profile() request
    → minimum mapping-shape validation
    → immediate payload discard
    → sanitized Provider-internal outcome category
```

The pilot ends immediately after the one probe invocation and any strictly local resource cleanup that performs no Provider request or mutation.

The pilot shall not invoke:

- login URL generation;
- request-token exchange;
- access-token generation, refresh, renewal or invalidation;
- authenticated-context termination;
- any generic request method;
- Instrument Master;
- quote, LTP, OHLC or historical-data endpoints;
- WebSocket or streaming;
- orders, trades, holdings, positions, funds, margins, GTT or any other account or execution endpoint; or
- any secondary Provider endpoint.

# 7. Expressly Granted Authorities

CAR-011 grants only:

1. creation and publication of CAR-011 Version 1.0;
2. the Section 5 EDD-004 editorial correction;
3. the required CAR-011 Document Register entry;
4. documentation and offline verification of the unchanged runtime path;
5. a pre-pilot documentation-only commit and push;
6. one Sponsor-instructed probe execution within the validity window and after all conditions are proven;
7. one `profile()` request with no retry;
8. transient use of the minimum ephemerally supplied API key and access token;
9. minimum response-shape validation and immediate discard;
10. retention of only the Section 13 sanitized outcome fields; and
11. a post-pilot documentation-only CAR-011 Version 1.1 commit and push.

These grants are one-time and non-transferable.

# 8. Expressly Withheld Authorities

CAR-011 withholds:

- retrospective or new implementation acceptance for EDD-001, EDD-002 or EDD-003;
- code, configuration, test, dependency or fixture changes;
- general Provider endpoint or runtime authority;
- a second attempt or retry;
- authentication automation, request-token exchange, refresh or renewal;
- access-token invalidation or any Provider-side session mutation;
- Instrument Master acquisition;
- quote, LTP, OHLC, historical data, streaming, market depth, open interest or option-chain activity;
- Provider Catalogue, Instrument, Observation, Market Facts or Validation creation;
- persistence, storage, caching, snapshots, recordings, raw payload retention or replay;
- cross-domain publication or communication;
- GUI or Administration Console work;
- account administration or access to trades, holdings, positions, funds or margins;
- order placement, modification, cancellation, GTT activity, position conversion or any broker-write behavior;
- production deployment, scheduling, polling or background execution; and
- any architecture, product, Risk, Execution, Portfolio or trading authority.

# 9. Credential Restrictions

Credentials shall:

- be supplied ephemerally outside the repository;
- be limited to the API key and existing access token required by the EP-004 probe;
- never be written to a repository file, `.env` file, fixture, command transcript, documentation, log, screenshot, shell history or retained artefact;
- never be printed, serialized, echoed, interpolated into an error or included in evidence;
- never be exposed through SDK debug output, which shall remain disabled; and
- be removed from the local execution environment after the attempt.

The pilot shall not consume an API secret, request token, user password, PIN or TOTP.

# 10. Payload and Evidence Restrictions

The raw profile response is sensitive and shall:

- remain inside the existing Kite adapter;
- be inspected only for the minimum expected mapping shape;
- not have any business or account field read for pilot evidence;
- not be printed, returned, serialized, logged, persisted, copied, recorded or included in an exception;
- be discarded immediately after shape validation; and
- not become Provider Entitlement evidence, Instrument evidence, Observation, Market Fact, Validation evidence or Audit evidence.

Raw SDK or Provider exception messages shall not be retained. Failure evidence shall use only an existing controlled, sanitized failure category.

# 11. Pre-Execution Conditions

Before the Sponsor may instruct execution, all of the following shall be proven:

1. CAR-011 Version 1.0 and its register entry are committed and synchronized to `origin/develop`.
2. The working tree is clean and the exact execution commit SHA is recorded.
3. The authority is unused and the Authority Expiry Date has not passed.
4. The full offline test suite passes at the exact execution commit.
5. The unchanged runtime path is inspected and proven to call `KiteConnect.profile()` exactly once for one probe invocation.
6. The path has no retry, token refresh, request-token exchange, persistence, access-token invalidation, authenticated-context termination, secondary endpoint or Provider mutation.
7. Logging is proven unable to include credentials, authorization headers, profile fields or account identifiers.
8. Credentials will be supplied ephemerally outside the repository.
9. Execution will occur only in an identified local non-production environment.
10. No unresolved condition, unexpected diff or conflicting authority remains.
11. The Sponsor gives a new, explicit instruction to execute the pilot.

If any condition cannot be proven, execution shall not occur and the authority remains unused unless an execution attempt was initiated.

# 12. One-Attempt, No-Retry and Expiry Rules

CAR-011 authority expires at the earliest of:

1. initiation of the first Sponsor-instructed `KiteConnectivityService.probe()` execution;
2. any success or failure arising from that first execution; or
3. the end of the seven-calendar-day authority window on 2026-08-06.

Initiating the first Sponsor-instructed probe consumes the authority even if configuration validation, SDK construction, transport or Provider processing fails before a successful response.

Failure consumes the authority. No retry, corrective second run or replacement token attempt is authorized. A second attempt requires a new Chief Architect authorization.

# 13. Approved Sanitized Outcome Fields

CAR-011 Version 1.1 may retain only:

- execution date and time;
- local non-production environment identifier;
- exact repository commit SHA;
- Kite SDK version;
- endpoint classification;
- success or sanitized failure category;
- confirmation of one call;
- confirmation of no retry;
- confirmation of payload discard;
- confirmation that no secrets or account details were logged;
- confirmation that no Provider mutation occurred; and
- confirmation that no other endpoint was invoked.

No raw response, raw exception message, credential, authorization header, profile field, account identifier or Provider payload may be added.

# 14. Outcome Revision and Authority Consumption

The eventual sanitized outcome shall be recorded only by revising this document to CAR-011 Version 1.1.

Version 1.1 shall:

- preserve the complete Version 1.0 decision;
- record only the Section 13 fields;
- state that the authority is consumed;
- record whether consumption occurred by successful attempt, failed attempt or expiry;
- retain the original publication date and authority-expiry date; and
- create no renewed, replacement or second-attempt authority.

No separate pilot-outcome document is authorized.

# 15. Publication and Commit Authority

CAR-011 permits:

1. one pre-pilot documentation-only commit containing only:
   - this CAR-011 Version 1.0 record;
   - the Section 5 EDD-004 sentence correction; and
   - the CAR-011 Document Register entry;
2. push of that commit to `origin/develop`;
3. after the one attempt or expiry, one post-pilot documentation-only commit updating this same record to Version 1.1 with the sanitized outcome and consumed-authority status; and
4. push of that Version 1.1 commit to `origin/develop`.

No source code, configuration, test, dependency, fixture, architecture or separate outcome-document change is authorized.

# 16. Decision Effect

This decision becomes effective only after CAR-011 Version 1.0 is committed and synchronized to `origin/develop`.

Publication authorizes no immediate Provider call. Pre-execution verification and a separate explicit Sponsor instruction remain mandatory.

The decision does not accept any governance-nonconforming historical implementation, alter EDD-004 engineering meaning, or establish continuing runtime authority.

# 17. Version 1.1 Sanitized Outcome

**Execution date and time:** 2026-08-01T16:37:53+0530

**Environment identifier:** SPONSOR-MAC-LOCAL-NONPROD-2026-08-01

**Repository commit SHA:** `3327d20157320f81c001c2f2a967a48aabff5322`

**Kite SDK version:** 5.2.0

**Endpoint classification:** AUTHENTICATED PROFILE CONNECTIVITY

**Sanitized outcome category:** ACCESS_TOKEN_INVALID_OR_EXPIRED

**One SDK profile invocation confirmed:** YES

**No retry confirmed:** YES

**Payload discarded:** YES

**No secret or account detail logged:** YES

**No Provider-side mutation:** YES

**No other endpoint invoked:** YES

**Wire-level HTTP transmission count asserted:** NO

**Redirect presence or absence asserted:** NO

**CAR-011 authority consumed:** YES

**Second attempt authorized:** NO

**Required disposition:** FRESH CHIEF ARCHITECT AUTHORITY REQUIRED FOR ANY LATER ATTEMPT

## Related Authority

- [EP-004 — Minimum Read-Only Kite Connectivity](../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md)
- [EDD-001 — Provider Access and Provider Context Engineering Design](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md)
- [EDD-002 — Provider Capability Assessment Engineering Design](../../engineering/edd/EDD-002-PROVIDER-CAPABILITY-ASSESSMENT-ENGINEERING-DESIGN.md)
- [EDD-003 — Provider Entitlement Assessment Engineering Design](../../engineering/edd/EDD-003-PROVIDER-ENTITLEMENT-ASSESSMENT-ENGINEERING-DESIGN.md)
- [EDD-004 — Provider Instrument Master Acquisition Engineering Design](../../engineering/edd/EDD-004-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-ENGINEERING-DESIGN.md)
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
