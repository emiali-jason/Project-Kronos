# CAR-015 — Replacement One-Time Kite Profile Verification Pilot Authorization

**Document ID:** CAR-015
**Title:** Replacement One-Time Kite Profile Verification Pilot Authorization
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-015-REPLACEMENT-ONE-TIME-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVE WITH CONDITIONS
**Implementation Authorization:** Authorized with Constraints — CAR-015 pilot-local tkinter harness only
**Runtime Authority:** Consumed — no further CAR-015 execution authorized
**Provider Endpoint Authority:** Consumed — no further CAR-015 Provider endpoint invocation authorized
**Credential-Use Authority:** Consumed — no further CAR-015 credential use authorized
**Token-Generation Authority:** Withheld
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Implementation Baseline:** `0908d3eca75ff926c6cb6d1b51c81418818567c5`
**Publication Date:** 2026-08-02
**Authority Expiry Date:** 2026-08-09
**Approved Environment Class:** Sponsor-controlled local non-production macOS environment
**Authority Status:** Consumed
**Consumption Basis:** Failed authorized attempt
**Sanitized Outcome Category:** `ACCESS_TOKEN_INVALID_OR_EXPIRED`
**Outcome Revision:** CAR-015 Version 1.1 sanitized outcome recorded

---

# 1. Purpose

This Chief Architect decision authorizes implementation publication, offline verification and one later Sponsor-initiated Kite profile-connectivity verification attempt through a temporary pilot-local tkinter harness.

CAR-015 is independent of CAR-011. CAR-011 remains permanently closed and consumed. CAR-015 does not reopen, renew, amend, reuse or replace the identity or consumed authority of CAR-011.

The harness is a temporary local pilot utility. It is not the future KRONOS browser application, a reusable GUI framework, a production Provider implementation or a continuing runtime capability.

# 2. Governing Basis

CAR-015 is governed by:

- [CAR-011 Version 1.1 — consumed Kite profile pilot outcome](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md);
- [CAR-012 — authoritative profile operation and transport interpretation](CAR-012-CAR-011-PROFILE-OPERATION-AND-TRANSPORT-BOUNDARY-CLARIFICATION.md);
- [EP-004 — Minimum Read-Only Kite Connectivity](../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

CAR-012 remains the authoritative transport interpretation for this replacement pilot. Its one-operation meaning applies without reopening CAR-011.

# 3. Decision

> **APPROVE WITH CONDITIONS**

CAR-015 Version 1.0 authorizes only:

1. this controlled authorization record and its Document Register entry;
2. one isolated pilot-local standard-library tkinter harness;
3. one fake-only offline test file;
4. publication and offline verification of those artifacts;
5. after publication, successful preflight and a separate explicit Sponsor instruction, one Sponsor-initiated local non-production execution;
6. exactly one KRONOS-controlled `KiteConnect.profile()` SDK invocation through exactly one `KiteConnectivityService.probe()` invocation;
7. one local `shutdown()` attempt where service construction succeeds; and
8. one documentation-only Version 1.1 revision containing only the authorized sanitized outcome.

No authority shall be inferred beyond these grants.

# 4. Independent Replacement Authority

The following statements are controlling:

1. CAR-015 is independent of CAR-011.
2. CAR-011 remains closed and consumed.
3. CAR-015 does not reopen, renew, amend or reuse CAR-011.
4. CAR-012 remains the authoritative transport interpretation.
5. CAR-015 creates one new replacement attempt under its own identity and lifecycle only.
6. CAR-015 grants no authority to execute CAR-014.

# 5. One-Operation Transport Boundary

One call means one KRONOS-controlled `KiteConnect.profile()` SDK invocation.

The authorized runtime path is:

```text
Sponsor final confirmation
    → CAR-015 execution started and authority consumed
    → one Settings construction attempt
    → one KiteConnectivityService construction attempt
    → one KiteConnectivityService.probe() invocation
    → one KiteConnect.profile() SDK invocation
    → sanitized outcome only
    → one local shutdown() attempt where service construction succeeded
```

Wire-level HTTP transmission count is not asserted. Redirect presence or absence is not asserted. Ordinary unchanged SDK transport handling remains internal to the single Provider operation under CAR-012.

No KRONOS retry, second invocation, reprobe, manual redirect or transport instrumentation is permitted.

# 6. Consumption and One-Attempt Rule

CAR-015 is consumed when the Sponsor accepts final confirmation and runtime construction begins. The harness shall mark execution started and authority consumed before constructing `Settings` or `KiteConnectivityService`.

Success or failure consumes CAR-015. Configuration failure, service-construction failure, transport failure, Provider failure, response failure, local processing failure and shutdown failure all leave the authority consumed.

No second attempt is authorized. Restarting, reopening or reconstructing the utility does not create new authority. The current process shall expose no retry, reset, reauthorization or second-Run path.

# 7. Authority Expiry

CAR-015 authority expires at the earliest of:

1. initiation of the first authorized attempt;
2. 2026-08-09, seven calendar days after Version 1.0 publication; or
3. Chief Architect revocation.

Expiry, success or failure creates no replacement or renewed authority.

# 8. Credential Boundary

The pilot may accept only:

- one ephemeral Kite API key; and
- one newly obtained valid access token.

The pilot shall not request or accept an API secret, request token, password, PIN, TOTP or browser login.

Credentials shall never be printed, logged, serialized, persisted, written to `.env`, written to configuration files, written to fixtures, included in documentation, included in screenshots, included in raw exceptions or passed through command-line arguments.

The harness shall mask both input controls, copy the two values only into short-lived local variables after final confirmation, clear the widgets, hide or destroy the credential frame, construct the approved objects directly and delete local credential references immediately after service construction. It shall not claim secure or cryptographic memory erasure.

# 9. GUI Boundary

The window shall contain only:

1. one masked Kite API-key field;
2. one masked newly obtained access-token field;
3. local validation status;
4. the controlling one-attempt warning;
5. one **Run One-Time Profile Verification** button;
6. one **Cancel** button; and
7. one sanitized result area.

Opening the window shall construct no service or SDK client, access no credential, invoke no Provider method and print nothing.

The Run button shall remain disabled until both credential fields are non-empty. Rejecting final confirmation invokes no Provider method and consumes no authority.

# 10. Sanitized Result

The GUI may display only:

```text
Profile connectivity: AVAILABLE / UNAVAILABLE / INDETERMINATE
Controlled error code: <approved sanitized code or NONE>
Local shutdown: SUCCESS / SANITIZED FAILURE
CAR-015 authority: CONSUMED
```

The GUI shall not display or retain raw profile payloads, profile fields, user ID, account ID, user name, email, broker details, entitlements, credentials, raw SDK or Provider exceptions, tracebacks, HTTP responses, headers, authorization headers, redirect URLs or redirect history.

Production harness execution shall print nothing to stdout or stderr.

# 11. Expressly Withheld Authorities

CAR-015 grants no authority for:

- Instrument Master;
- historical data;
- quote, LTP or OHLC;
- WebSocket or streaming;
- orders, trades, holdings, positions, funds, margins or other account state;
- any broker write or Provider-side mutation;
- login URL generation, request-token exchange, token generation, refresh, invalidation or session termination;
- persistence, caching, payload retention or replay;
- CAR-014 execution;
- production deployment, background execution, polling or scheduling;
- a second attempt or retry; or
- future browser-application implementation.

# 12. Frozen Version 1.0 Boundary

The following are frozen:

- implementation baseline `0908d3eca75ff926c6cb6d1b51c81418818567c5`;
- publication date 2026-08-02;
- authority expiry date 2026-08-09;
- Sponsor-controlled local non-production macOS environment class;
- one final confirmation and one-attempt boundary;
- ephemeral API-key and newly obtained access-token boundary;
- exactly one SDK profile invocation;
- one local shutdown attempt where possible;
- the four sanitized result fields in Section 10;
- all withheld authorities in Section 11; and
- Version 1.1 as the sole sanitized-outcome lifecycle.

# 13. Pre-Execution Conditions

No live execution may occur until all of the following are proven:

1. CAR-015 Version 1.0 and all four authorized files are committed and synchronized to `origin/develop`.
2. The exact execution SHA is recorded and the working tree is clean.
3. CAR-015 remains unused and unexpired.
4. All focused and complete offline tests pass at the execution SHA.
5. The exact runtime path still contains one `probe()` call site, no retry and no secondary endpoint.
6. Both credential controls remain masked and credentials remain transient.
7. The execution environment is an identified Sponsor-controlled local non-production macOS environment.
8. No HTTP capture, proxy or inspection tool retains request headers or payloads.
9. The Sponsor gives a new explicit instruction to execute CAR-015.

Publication alone does not initiate or consume the authority.

# 14. Version 1.1 Outcome Lifecycle

Version 1.1 is reserved only for the sanitized outcome after the first attempt or expiry. Version 1.1 shall preserve the complete Version 1.0 decision, mark authority consumed or expired and authorize no second attempt.

Version 1.1 may retain only:

- execution date and time;
- local environment identifier;
- exact execution SHA;
- Python version;
- Kite SDK version;
- endpoint classification;
- sanitized outcome category;
- one SDK profile invocation confirmation;
- no-retry confirmation;
- payload-discard confirmation;
- no-secret or account-detail logging confirmation;
- no Provider mutation confirmation;
- no other endpoint confirmation;
- wire-level transmission count not asserted;
- redirect presence or absence not asserted;
- CAR-015 authority consumed; and
- no second attempt authorized.

No raw profile data, credential, account information, transport detail or raw exception may be retained.

# 15. Publication and Decision Effect

Version 1.0 permits one implementation-and-documentation commit containing only the four authorized CAR-015 files and one push to `origin/develop` after Engineering Architect acceptance.

This decision becomes effective only after that commit is synchronized to `origin/develop`. Publication creates implementation, bounded future runtime and endpoint authority only on the exact conditions stated here. It does not itself execute the pilot, access credentials, construct a real SDK client or consume CAR-015.

# 16. Version 1.1 Sanitized Outcome

The complete Version 1.0 decision is preserved above. The following is the only retained outcome of the consumed authorized attempt:

| Outcome Field | Sanitized Record |
|---|---|
| Execution date and time | 2026-08-03 — exact local time not retained in the approved sanitized evidence |
| Exact execution SHA | `dd03f49e97255d4c3b209d279ce2d3886a8a94b0` |
| Python version | 3.13.14 |
| Kite SDK version | 5.2.0 |
| Endpoint classification | AUTHENTICATED PROFILE CONNECTIVITY |
| Profile connectivity | UNAVAILABLE |
| Controlled error code | `ACCESS_TOKEN_INVALID_OR_EXPIRED` |
| Local shutdown | SUCCESS |
| One probe invocation confirmed | YES |
| One SDK profile invocation confirmed | YES |
| No retry confirmed | YES |
| No second endpoint confirmed | YES |
| No credential logging confirmed | YES |
| No payload retention confirmed | YES |
| No raw exception displayed | YES |
| CAR-015 authority consumed | YES |
| Second attempt authorized | NO |

CAR-015 is closed. No later execution, credential use or Provider operation may rely on CAR-015.

## Related Authority

- [CAR-011 Version 1.1](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md)
- [CAR-012](CAR-012-CAR-011-PROFILE-OPERATION-AND-TRANSPORT-BOUNDARY-CLARIFICATION.md)
- [EP-004](../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md)
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
