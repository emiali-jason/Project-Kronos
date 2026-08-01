# CAR-012 — CAR-011 Profile Operation and Transport Boundary Clarification

**Document ID:** CAR-012
**Title:** CAR-011 Profile Operation and Transport Boundary Clarification
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-012-CAR-011-PROFILE-OPERATION-AND-TRANSPORT-BOUNDARY-CLARIFICATION.md`
**Workflow Stage:** Repository Publication
**Decision Status:** APPROVED
**Decision:** APPROVE CLARIFICATION
**Priority:** P0
**Register Disposition:** None
**Draft Authorization:** None
**Implementation Authorization:** None
**Runtime Authority:** None
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Clarified Authority:** CAR-011 Version 1.0
**Publication Date:** 2026-08-01

---

# 1. Purpose

This Chief Architect clarification records the authoritative meaning of the one-call boundary in [CAR-011 — Kite Profile Verification Pilot Authorization Decision](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md).

CAR-011 authorizes exactly one KRONOS-controlled `KiteConnect.profile()` SDK invocation through one invocation of the existing `KiteConnectivityService.probe()` path. Ordinary transport handling performed internally by the unchanged official SDK and its unchanged transport dependency remains within that single Provider operation.

This clarification interprets CAR-011. It does not amend, expand, replace or consume CAR-011 authority.

# 2. Clarification Decision

> **APPROVE CLARIFICATION**

The authoritative operation boundary is:

```text
One KiteConnectivityService.probe() invocation
    → one KiteConnectivityAdapter.probe() invocation
    → one _KiteClientHandle.probe_profile() invocation
    → exactly one KRONOS-controlled KiteConnect.profile() invocation
    → unchanged SDK-managed transport activity
    → one success or sanitized failure
    → CAR-011 authority consumed
```

One call means exactly one KRONOS-controlled invocation of `KiteConnect.profile()`. Wire-level HTTP transmission count is not part of the authorized assertion.

# 3. SDK Transport Interpretation

Ordinary redirect handling performed automatically inside the unchanged official SDK and its unchanged transport dependency is permitted within the single authorized Provider operation.

The approved evidence shall not assert redirect presence, absence or route unless that information is exposed by the unchanged approved path. Where internal transport behaviour is not exposed, KRONOS shall make no claim about:

- redirect destination;
- redirect route;
- final host;
- number of physical HTTP transmissions;
- number of TCP or TLS connections; or
- whether the original request remained on one host.

This interpretation does not authorize KRONOS-controlled redirect handling, manual redirect following, runtime interception, redirect detection, transport replacement, SDK modification, redirect-specific code or an alternative invocation harness.

# 4. One-Attempt and No-Retry Boundary

The following remain mandatory:

1. one `KiteConnectivityService.probe()` invocation;
2. one adapter `probe()` invocation;
3. one `_KiteClientHandle.probe_profile()` invocation;
4. exactly one KRONOS-controlled `KiteConnect.profile()` invocation;
5. no KRONOS retry;
6. no second probe or SDK invocation;
7. no polling, scheduling, automatic repeat or automatic re-probe;
8. no manual redirect handling; and
9. no manual attempt after transport failure.

Any success or failure after execution begins consumes CAR-011 authority. A redirect-related success, redirect-related failure, transport exception, configuration failure, SDK-construction failure or Provider-processing failure permits no corrective second attempt.

# 5. Cross-Host Redirect Treatment

A cross-host redirect does not establish an approved Provider destination, architectural dependency or separately authorized Provider operation.

If a cross-host redirect is visible through the existing unchanged runtime path before completion:

1. treat the attempt as a sanitized transport failure;
2. do not manually approve, repeat or follow it;
3. discard all response material;
4. mark CAR-011 authority consumed; and
5. escalate the observation before any later pilot.

If the unchanged SDK follows a redirect internally and the existing path does not expose that fact, KRONOS shall retain no redirect URL, host, response header or response history and shall record only the permitted SDK-operation evidence. This clarification does not require instrumentation merely to detect redirects.

# 6. Permitted Outcome Evidence

The eventual CAR-011 Version 1.1 sanitized outcome may state:

- exactly one KRONOS-controlled `KiteConnect.profile()` invocation occurred;
- no KRONOS retry, second probe invocation or second Provider operation was initiated;
- transport-level wire-request count was not asserted;
- redirect presence, absence and route were not asserted unless exposed by the unchanged approved path;
- the operation resulted in a sanitized success or failure category;
- CAR-011 authority was consumed; and
- the payload was discarded and no Provider or account details were retained.

# 7. Prohibited Evidence Claims

The eventual outcome shall not state:

- exactly one HTTP transmission occurred;
- no redirect occurred;
- only one TCP or TLS connection occurred;
- the final host was verified; or
- the request never left the original host.

No raw URL, redirect history, response header, transport exception, Provider payload, credential, profile field or account identifier may be retained.

# 8. Authority Preservation

CAR-012 does not amend or expand CAR-011. The same endpoint, operation, credential boundary, one-attempt rule, expiry, evidence restrictions and withheld authorities remain in force.

CAR-011 Version 1.1 remains reserved exclusively for the authorized sanitized pilot outcome. CAR-012 does not consume that revision and creates no alternative outcome record.

CAR-012 grants no:

- source-code, test, configuration or dependency change;
- SDK, HTTP-session or transport change;
- interception, instrumentation, redirect guard or alternate invocation harness;
- Instrument Master, quote, LTP, OHLC, historical-data or streaming authority;
- Provider data persistence or cross-domain publication;
- Instrument, Observation, Market Fact or Validation creation;
- GUI or Administration Console authority;
- order, trade, holding, position, funds, margin or broker-write authority; or
- general precedent for any later Provider operation.

# 9. Execution Preconditions

The CAR-011 pilot may proceed only after:

1. CAR-012 Version 1.0 is published and synchronized to `origin/develop`;
2. the working tree is clean and local `develop` is aligned with `origin/develop`;
3. the full offline test suite passes at the exact execution commit;
4. the repository runtime path, SDK version and dependency environment remain unchanged;
5. CAR-011 remains unused and unexpired;
6. every original CAR-011 pre-execution condition remains satisfied;
7. credentials are supplied ephemerally within the approved boundary; and
8. the Sponsor gives a new explicit execution instruction.

CAR-012 publication alone authorizes no Provider call and consumes no CAR-011 authority.

# 10. Decision Effect

This clarification becomes effective only after CAR-012 Version 1.0 is committed and synchronized to `origin/develop`.

It establishes that the CAR-011 outcome field “confirmation of one call” means confirmation of one `KiteConnect.profile()` SDK invocation, not confirmation of one physical wire transmission.

No architecture, implementation, runtime, endpoint, acquisition, persistence, submission, interpretation, product or trading authority shall be inferred beyond CAR-011.

## Related Authority

- [CAR-011 — Kite Profile Verification Pilot Authorization Decision](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md)
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
