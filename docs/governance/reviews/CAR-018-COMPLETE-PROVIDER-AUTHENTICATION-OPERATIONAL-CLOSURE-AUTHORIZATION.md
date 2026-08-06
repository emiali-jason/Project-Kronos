# CAR-018 — Complete Provider Authentication Operational Closure Authorization

**Document ID:** CAR-018
**Title:** Complete Provider Authentication Operational Closure Authorization
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Canonical
**Previous Canonical Version:** 1.0
**Version 1.0 Canonical Publication SHA:** `dd8caa77b4c896628633d269c9c56775b24f6cfa`
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-018-COMPLETE-PROVIDER-AUTHENTICATION-OPERATIONAL-CLOSURE-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVED — IMPLEMENTATION CONFORMANCE ACCEPTED
**Implementation Authority:** Completed — no new implementation authority
**Implementation Conformance:** Offline Verified
**Authority State:** Unconsumed
**Authentication Attempt State:** Not Started
**Runtime Authority:** None
**Live Authority:** None
**Preflight Authority:** None
**Sponsor Execution Authority:** None
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
**Authority-Package Baseline:** `4c5c6ec8fe1a315411725e29ff14291d98355d86`
**Current Corrected CAR-017 Implementation SHA:** `8f052d0cc3b7abc63a28c2951a3b4770c58b4454`
**Frozen CAR-018 Corrective Composite Implementation SHA:** `6273663a8ca8729833a8a0f05e06d55973ce6dc0`
**CAR-016 CA1 Logical Publication Reference:** `CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002`
**CAR-017 CA1 Logical Publication Reference:** `CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002`
**CA1 Coordinated Governance Publication Commit SHA:** `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT`

---

# Version 1.1 Approved Canonical implementation-conformance record

## Conformance purpose and boundary

This Version 1.1 Approved Canonical record documents completion of the CAR-018 implementation and
fake-only offline verification programme. It does not grant runtime, live,
credential-use, Keychain, browser, listener, SDK, network, Provider-endpoint,
trading or CAR-014 authority. It does not renew, revive, extend, replace or
consume any coordinated activation authority. It does not amend CAR-016 or
CAR-017 and is not the coordinated activation publication described by Version
1.0 Section 15.

Every conformance claim in this amendment uses exactly one of these evidence
classes:

- **IMPLEMENTED** — repository code or test structure exists at the frozen
  implementation SHA;
- **OFFLINE VERIFIED** — injected-fake or static offline verification passed;
  or
- **NOT YET LIVE VERIFIED** — no practical Provider or external-effect
  validation has occurred.

No claim in this record converts offline evidence into live evidence.

## Frozen publication and implementation chain

| Evidence | Exact SHA | Classification | Manifest evidence |
|---|---|---|---|
| CAR-018 Version 1.0 canonical publication | `dd8caa77b4c896628633d269c9c56775b24f6cfa` | IMPLEMENTED | CAR-018 Version 1.0 and Document Register; 2 documentation files |
| Stage 1 | `30e6caa8e13fcc0015d86bac4c5af14241be5148` | IMPLEMENTED | governed activation and consumption contracts; 4 implementation/test files |
| Original Stage 2 | `9a8a2e743276ee73e3c5dc82298e58d7fab2c99e` | IMPLEMENTED | governed live authentication launcher integration; 12 implementation/test files |
| Stage 2 corrective | `9b6953275145115a8cc9d2fbeb610a9be877f67c` | IMPLEMENTED | exact proof, deadline, budget and ledger integration; 4 implementation/test files |
| Stage 3 and frozen final implementation | `6273663a8ca8729833a8a0f05e06d55973ce6dc0` | IMPLEMENTED | final service conformance verification; 1 test file |

The **Frozen CAR-018 Corrective Composite Implementation SHA** is
`6273663a8ca8729833a8a0f05e06d55973ce6dc0`.

The original Stage 2 commit did not complete the canonical service integration
allocation. The separately reviewed Stage 2 corrective commit completed that
allocation without erasing or relabelling the original Stage 2 history.

## Completed 18-path implementation and test manifest

All 18 canonical implementation/test paths are complete. Each path is recorded
as **IMPLEMENTED**; its behavior is classified separately below.

### Production and pilot — 11 paths

1. `src/kronos/provider/kite/live_activation.py`
2. `src/kronos/provider/kite/composition.py`
3. `src/kronos/provider/models/authentication.py`
4. `src/kronos/configuration/settings.py`
5. `src/kronos/configuration/loader.py`
6. `src/kronos/provider/contracts/provider_authentication.py`
7. `src/kronos/provider/services/provider_authentication.py`
8. `src/kronos/provider/adapters/kite/client.py`
9. `src/kronos/provider/adapters/kite/authentication.py`
10. `tools/provider_pilots/car017_live_authentication_launcher.py`
11. `tools/provider_pilots/car016_provider_authentication_gui.py`

### Tests — 7 paths

12. `tests/unit/provider/test_kite_live_activation.py`
13. `tests/unit/tools/test_car017_live_authentication_launcher.py`
14. `tests/unit/provider/test_kite_authentication_composition.py`
15. `tests/unit/configuration/test_kite_connectivity_settings.py`
16. `tests/unit/provider/test_provider_authentication_service.py`
17. `tests/unit/provider/test_kite_authentication_adapter.py`
18. `tests/unit/tools/test_car016_provider_authentication_gui.py`

## Claim-classification matrix

| Claim | Classification | Evidence boundary |
|---|---|---|
| Trusted coordinated activation provenance and immutable activation context | IMPLEMENTED | Stage 1 repository implementation |
| Durable consumption state, strict parser and descriptor-relative no-follow contract | IMPLEMENTED | Stage 1 contracts and implementation |
| One 300-second monotonic complete-lifecycle deadline and remaining-budget contract | IMPLEMENTED | Stage 1 model and Stage 2 service integration |
| Sanitized single operation-ledger contract | IMPLEMENTED | Stage 1 model and Stage 2 integration |
| Governed configuration, no-dotenv authentication path and exact identity bindings | IMPLEMENTED | Original Stage 2 implementation |
| Sole governed launcher and one authoritative authentication path | IMPLEMENTED | Original and corrective Stage 2 implementation |
| Exact `ProvenConsumption`, deadline, budget and canonical-ledger propagation | IMPLEMENTED | Stage 2 corrective implementation |
| Proof-before-attempt and proof-before-listener ordering | IMPLEMENTED | Stage 2 corrective service integration |
| MATCHED-only authenticated-context establishment | IMPLEMENTED | Provider Authentication Service lifecycle |
| Local-only cleanup with no remote token invalidation | IMPLEMENTED | Service and launcher cleanup paths |
| Provider Availability Verification maximum count `0` | IMPLEMENTED | Governed runtime and ledger enforcement |
| Activation, persistence, deadline, ledger, composition and lifecycle behavior under injected fakes | OFFLINE VERIFIED | Accepted CAR-018 focused suites |
| Exact operation cardinality, no duplicate path and terminal cleanup matrix | OFFLINE VERIFIED | Stage 2 corrective and Stage 3 service tests plus static scans |
| Secret and sensitive-material containment in changed evidence | OFFLINE VERIFIED | Accepted scans; no finding |
| Complete repository regression | OFFLINE VERIFIED | 764 tests passed at the frozen final SHA |
| Real Apple Keychain retrieval | NOT YET LIVE VERIFIED | No real Keychain access occurred |
| Real default-browser launch and official login-page behavior | NOT YET LIVE VERIFIED | No browser was opened |
| Real loopback listener bind and terminal callback | NOT YET LIVE VERIFIED | No production listener or callback occurred |
| Real Kite SDK construction | NOT YET LIVE VERIFIED | No real SDK client was constructed |
| Real `generate_session()` request-token exchange | NOT YET LIVE VERIFIED | No request token or Provider exchange occurred |
| Real `profile()` principal verification | NOT YET LIVE VERIFIED | No Provider profile operation occurred |
| Real Provider behavior or availability | NOT YET LIVE VERIFIED | No network or Provider call occurred; availability count remains `0` |
| Real authenticated Provider Context establishment | NOT YET LIVE VERIFIED | Only injected-fake context establishment was exercised |

## Accepted offline verification evidence

| Evidence set | Result | Classification |
|---|---|---|
| Stage 2 corrective focused composition and service tests | 51 passed | OFFLINE VERIFIED |
| Stage 2 corrective CAR-018 focused suites | 255 passed | OFFLINE VERIFIED |
| Stage 2 corrective complete offline regression | 755 passed | OFFLINE VERIFIED |
| Stage 3 focused Provider Authentication Service tests | 37 passed | OFFLINE VERIFIED |
| Final CAR-018 focused suites | 264 passed | OFFLINE VERIFIED |
| Final complete offline regression | 764 passed | OFFLINE VERIFIED |
| Duplicate-path scan | PASS | OFFLINE VERIFIED |
| Secret scan | PASS | OFFLINE VERIFIED |
| Sensitive-material scan | PASS | OFFLINE VERIFIED |
| `git diff --check` at accepted stage gates | PASS | OFFLINE VERIFIED |

All verification used injected fakes, synthetic data, injected clocks and
isolated local test boundaries. No real credential, Keychain, browser,
production listener, callback, SDK client, request-token exchange, profile
operation, network request, Provider behavior or authenticated-context
establishment was practically validated.

## Preserved authority and operational state

| State | Recorded value | Classification |
|---|---|---|
| Runtime Authority | None | IMPLEMENTED |
| Live Authority | None | IMPLEMENTED |
| Coordinated authority state | Unconsumed | OFFLINE VERIFIED |
| Authentication Attempt | Not Started | OFFLINE VERIFIED |
| Provider Availability verification operations | `0` | OFFLINE VERIFIED |
| External-effect activity during implementation and verification | None | OFFLINE VERIFIED |
| CAR-014 execution | Unexecuted | OFFLINE VERIFIED |
| Activation renewal, revival or replacement | None | IMPLEMENTED |

This canonical conformance record grants no activation renewal, live preflight
authority or Sponsor execution authority. Any later preflight or live execution
requires its own explicit Chief Architect authority.

## Approved Canonical coordinated activation disposition

The Chief Architect-authorized four-file canonical publication records this
disposition without executing it:

| Controlled value | Exact disposition |
|---|---|
| Previous coordinated activation identity | `KRONOS-COORD-AUTH-20260803-001` |
| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |
| New coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` |
| Effective | `2026-08-06T09:00:00+05:30 Asia/Kolkata` |
| Expiry | `2026-08-13T09:00:00+05:30 Asia/Kolkata` |
| Attempt cardinality | `ONE` |
| Consumption state | `UNUSED` |
| Provider Availability | `WITHHELD — MAXIMUM 0` |
| Frozen corrective composite implementation SHA | `6273663a8ca8729833a8a0f05e06d55973ce6dc0` |
| CAR-016 controlled amendment | `CAR-016-V1.2-CA1` |
| CAR-017 controlled amendment | `CAR-017-V1.2-CA1` |
| CAR-016 CA1 logical publication reference | `CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` |
| CAR-017 CA1 logical publication reference | `CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` |
| CA1 coordinated governance publication commit SHA | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` |
| CAR-014 | `UNEXECUTED` |

### Complete coordinated Activation Context equality matrix

Every field below must match byte-for-byte across CAR-016 CA1, CAR-017 CA1
and CAR-018 Version 1.1. A missing field, additional field, normalization,
case change, whitespace change, reinterpretation, derivation, substitution or
other unequal representation fails closed.

| Activation Context field | CAR-016 CA1 | CAR-017 CA1 | CAR-018 Version 1.1 | Equality |
|---|---|---|---|---|
| Coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` | `KRONOS-COORD-AUTH-20260804-002` | `KRONOS-COORD-AUTH-20260804-002` | MATCH |
| CA1 coordinated governance publication commit SHA | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | MATCH; replaced by the resulting publication SHA as post-publication evidence |
| Logical CAR-016 CA1 publication reference | `CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | `CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | `CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | MATCH |
| Logical CAR-017 CA1 publication reference | `CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | `CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | `CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` | MATCH |
| Frozen CAR-016 implementation SHA | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | MATCH |
| Frozen CAR-017 implementation SHA | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | MATCH |
| Frozen CAR-018 corrective composite implementation SHA | `6273663a8ca8729833a8a0f05e06d55973ce6dc0` | `6273663a8ca8729833a8a0f05e06d55973ce6dc0` | `6273663a8ca8729833a8a0f05e06d55973ce6dc0` | MATCH |
| Authority effective timestamp | `2026-08-06T09:00:00+05:30` | `2026-08-06T09:00:00+05:30` | `2026-08-06T09:00:00+05:30` | MATCH |
| Authority effective timezone | `Asia/Kolkata` | `Asia/Kolkata` | `Asia/Kolkata` | MATCH |
| Authority expiry timestamp | `2026-08-13T09:00:00+05:30` | `2026-08-13T09:00:00+05:30` | `2026-08-13T09:00:00+05:30` | MATCH |
| Authority expiry timezone | `Asia/Kolkata` | `Asia/Kolkata` | `Asia/Kolkata` | MATCH |
| Authentication Attempt timeout | `300 seconds` | `300 seconds` | `300 seconds` | MATCH |
| Sponsor environment reference | `SPONSOR-MACOS-LOCAL-NONPROD-01` | `SPONSOR-MACOS-LOCAL-NONPROD-01` | `SPONSOR-MACOS-LOCAL-NONPROD-01` | MATCH |
| Approved hostname | `Imrans-Mac-mini.local` | `Imrans-Mac-mini.local` | `Imrans-Mac-mini.local` | MATCH |
| Provider identity | `ZERODHA_KITE` | `ZERODHA_KITE` | `ZERODHA_KITE` | MATCH |
| Operational Provider value | `KITE` | `KITE` | `KITE` | MATCH |
| Provider configuration reference | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | MATCH |
| Kite application-registration reference | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | MATCH |
| Secure-credential reference | `KITE-API-SECRET-PRIMARY` | `KITE-API-SECRET-PRIMARY` | `KITE-API-SECRET-PRIMARY` | MATCH |
| Intended-principal registration reference | `KITE-INTENDED-PRINCIPAL-PRIMARY` | `KITE-INTENDED-PRINCIPAL-PRIMARY` | `KITE-INTENDED-PRINCIPAL-PRIMARY` | MATCH |
| Composition dependency-set reference | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | MATCH |
| Redirect URL | `http://127.0.0.1:8765/kite/callback` | `http://127.0.0.1:8765/kite/callback` | `http://127.0.0.1:8765/kite/callback` | MATCH |
| Attempt cardinality | `ONE` | `ONE` | `ONE` | MATCH |
| Provider Availability Verification Authority | `WITHHELD` | `WITHHELD` | `WITHHELD` | MATCH |
| Maximum Provider Availability verification operations | `0` | `0` | `0` | MATCH |
| CAR-014 status | `UNEXECUTED` | `UNEXECUTED` | `UNEXECUTED` | MATCH |
| Coordinated consumption state | `UNUSED` | `UNUSED` | `UNUSED` | MATCH |
| Controlled invalid-activation category | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | MATCH |

`CAR-016-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` and
`CAR-017-V1.2-CA1-KRONOS-COORD-AUTH-20260804-002` are jointly necessary and
individually insufficient. Version 1.3 remains reserved in both records for a
post-attempt sanitized outcome. No attempt has started and no authority has
been consumed while this package is prepared.

The one four-file documentation-only publication commit establishes the actual
coordinated governance publication SHA. That SHA is post-publication evidence,
is obtained only after commit creation and push, and is not inserted into the
commit that creates it. A later governed preflight must verify the resulting
SHA before any separate Sponsor execution decision can be considered.

The resulting four-file publication SHA is mandatory evidence for live
preflight, the final Sponsor execution instruction, CAR-016 Version 1.3 and
CAR-017 Version 1.3 sanitized outcome records.

Publication of this record does not itself perform preflight, reserve an
Authentication Attempt, consume authority or authorize Provider Availability
verification. Runtime and live execution remain unavailable until every later
governed gate and separate Sponsor instruction is satisfied.

---

# 1. Decision and purpose

CAR-018 is the single bounded corrective authority package for every remaining repository-visible blocker identified by the Complete Authentication Closure Review.

CAR-018 Version 1.0 authorized no implementation while Draft. After Chief Architect approval, canonical publication and synchronization to `origin/develop`, it authorized only the sequential offline implementation stages and exact paths defined here. Each stage required separate Engineering Architect start authority, evidence acceptance, commit authority and push authority.

CAR-018 grants no runtime, live, credential-use, Keychain-access, browser, listener, SDK, network, Provider-endpoint, market-data, trading or CAR-014 authority. It does not itself amend architecture or Engineering Design.

CAR-018 does not extend, renew, revive, reactivate or replace the existing coordinated CAR-016/CAR-017 authority, activation identity or authority window. CAR-018 implementation completion creates no live authority.

After Stage 3, the Chief Architect must separately decide:

- whether the existing coordinated activation identity remains usable;
- whether it is retired or superseded;
- whether a new activation identity is required;
- the applicable effective and expiry timestamps; and
- whether new CAR-016/CAR-017 activation amendments are authorized.

The intended terminal result is a fully governed, live-executable Provider Authentication path that remains externally inert until a later coordinated preflight and separate final Sponsor execution instruction.

---

# 2. Authority hierarchy and preserved meaning

CAR-018 is subordinate to and shall conform to:

- [ADR-010 Version 1.0](../../architecture/platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md);
- [DOMAIN-006 Version 1.1](../../architecture/platform/domains/provider/ARCHITECTURE.md);
- [EDD-001 Version 1.1](../../engineering/edd/EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md);
- [CAR-016](CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md);
- [CAR-017](CAR-017-LIVE-COMPOSITION-LAYER-IMPLEMENTATION-AUTHORIZATION.md); and
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md).

CAR-018 shall not redefine Provider Authentication, Authentication Attempt, Candidate Provider Context, principal binding, Authenticated Provider Context, Provider Availability, End KRONOS Session, credential custody, ownership or dependency meaning.

The operational Provider value remains `KITE`. The coordinated Provider identity remains the separate, exact reference `ZERODHA_KITE`. Neither value may replace, alias or reinterpret the other.

The official Kite behavior used by this package is limited to the documented login URL, request-token callback, `generate_session()` exchange and `profile()` principal verification described by:

- `https://github.com/zerodha/pykiteconnect`;
- `https://kite.trade/docs/pykiteconnect/v4/`; and
- `https://kite.trade/docs/connect/v3/user/`.

No conflict between those official references and the bounded KRONOS flow is known at preparation time. Any later conflict stops the applicable stage and returns to the Engineering Architect and Chief Architect; KRONOS behavior shall not be silently adapted.

---

# 3. Identity determination

`CAR-018` is the repository-recognized next valid CAR identity under DOC-001:

1. the highest allocated CAR identity is `CAR-017`;
2. `CAR-018` is absent from the repository and Document Register before this candidate;
3. no reservation for `CAR-018` exists;
4. the missing historical identifier `CAR-013` is not reused; and
5. `CAR-018` preserves the three-digit CAR family sequence and is unique.

---

# 4. Exact authorized path manifest

The following 22 paths are complete and sufficient: four governance paths and 18 implementation/test paths. No nineteenth implementation/test path, dependency file, architecture file or EDD file is required. A need for any twenty-third total path stops work and escalates.

## 4.1 Governance — four paths

1. `docs/governance/reviews/CAR-018-COMPLETE-PROVIDER-AUTHENTICATION-OPERATIONAL-CLOSURE-AUTHORIZATION.md` — new
2. `docs/governance/reviews/CAR-016-PROVIDER-AUTHENTICATION-PILOT-AUTHORIZATION.md` — separately identifiable post-Stage-3 controlled amendment, only if separately authorized by the Chief Architect
3. `docs/governance/reviews/CAR-017-LIVE-COMPOSITION-LAYER-IMPLEMENTATION-AUTHORIZATION.md` — separately identifiable post-Stage-3 controlled amendment, only if separately authorized by the Chief Architect
4. `docs/indexes/DOCUMENT-REGISTER.md` — publication and final conformance synchronization

## 4.2 Production and pilot — eleven paths

5. `src/kronos/provider/kite/live_activation.py` — new
6. `src/kronos/provider/kite/composition.py`
7. `src/kronos/provider/models/authentication.py`
8. `src/kronos/configuration/settings.py`
9. `src/kronos/configuration/loader.py`
10. `src/kronos/provider/contracts/provider_authentication.py`
11. `src/kronos/provider/services/provider_authentication.py`
12. `src/kronos/provider/adapters/kite/client.py`
13. `src/kronos/provider/adapters/kite/authentication.py`
14. `tools/provider_pilots/car017_live_authentication_launcher.py` — new
15. `tools/provider_pilots/car016_provider_authentication_gui.py`

## 4.3 Tests — seven paths

16. `tests/unit/provider/test_kite_live_activation.py` — new
17. `tests/unit/tools/test_car017_live_authentication_launcher.py` — new
18. `tests/unit/provider/test_kite_authentication_composition.py`
19. `tests/unit/configuration/test_kite_connectivity_settings.py`
20. `tests/unit/provider/test_provider_authentication_service.py`
21. `tests/unit/provider/test_kite_authentication_adapter.py`
22. `tests/unit/tools/test_car016_provider_authentication_gui.py`

The locked environment already resolves Python `3.13.14`, tkinter `9.0` and KiteConnect `5.2.0`. `uv.lock` freezes KiteConnect `5.2.0`; the governed launcher shall reject any different runtime version. Therefore modification of `pyproject.toml`, `uv.lock` or any dependency file is not required or authorized.

---

# 5. Frozen corrective governance decisions

## 5.1 Consumption persistence

CAR-018 freezes a non-sensitive durable local consumption record. A process-only flag is insufficient.

The approved Sponsor macOS record path is:

`~/Library/Application Support/KRONOS/provider-authentication/activation-consumption/<coordinated-activation-identity>.json`

The implementation shall obtain the user directory through the standard-library user-directory API. Configuration, environment variables and command-line values shall not redirect or replace this path.

The exact directory and file contract is:

| Item | Frozen value |
|---|---|
| Directory | `~/Library/Application Support/KRONOS/provider-authentication/activation-consumption` |
| File | `<coordinated-activation-identity>.json` |
| Directory permissions | `0700` |
| File permissions | `0600` |
| Ownership | current Sponsor user only |

The exact UTF-8 JSON schema is:

```json
{
  "schema_version": "1.0",
  "coordinated_activation_identity": "<exact identity>",
  "coordinated_governance_publication_sha": "<exact SHA>",
  "consumption_state": "CONSUMED",
  "consumed_at": "<RFC3339 timestamp with offset>"
}
```

The record has exactly the displayed `schema_version` discriminator and four record fields, in the displayed deterministic key order. Optional and unknown fields are prohibited. `CONSUMED` is the only terminal record state and no transition back to `UNUSED` exists. The record shall contain no credential, token, principal, account identifier, callback data, Provider payload, raw exception or transport detail.

### 5.1.1 Strict parser contract

The durable-record parser shall enforce exactly:

- encoding: UTF-8 without BOM;
- maximum total file size: 1024 bytes;
- top-level value: JSON object only;
- duplicate keys: rejected;
- unknown keys: rejected;
- missing required keys: rejected;
- comments: rejected;
- trailing non-whitespace content: rejected;
- invalid UTF-8: rejected;
- `consumed_at`: RFC3339 with a mandatory numeric UTC offset; and
- no relaxed, permissive or implementation-dependent parsing.

Any parser uncertainty fails closed as `CONSUMPTION_STATE_UNCERTAIN`. No retry is permitted.

### 5.1.2 Activation-identity filename contract

The exact coordinated activation-identity syntax is:

`^[A-Z0-9](?:[A-Z0-9_-]{0,126}[A-Z0-9])?$`

The identity is ASCII only and has length 1–128 characters. The filename is the exact coordinated activation identity followed by `.json`. There is no normalization, case conversion, trimming, alias, path separator, percent-decoding, Unicode equivalence or substitution. An invalid identity is rejected before any filesystem mutation.

### 5.1.3 Filesystem and descriptor contract

The filesystem implementation shall:

- safely create the approved directory if absent;
- open and verify the approved parent directory first and hold its verified descriptor;
- verify the parent-directory descriptor refers to the exact approved directory, is owned by the current Sponsor user, has mode exactly `0700` and is not a symlink;
- derive the target filename only from the already validated activation identity;
- create the record relative to the verified parent-directory descriptor;
- use exclusive-create and no-follow semantics;
- create the file with mode exactly `0600`;
- perform descriptor-based verification immediately after open;
- prohibit path-based fallback and reopen-by-path after creation;
- prohibit creation through unresolved aliases or alternate paths;
- reject a symlink directory or file;
- reject a hard-linked existing file;
- reject every non-regular file;
- reject wrong ownership or permissions broader than `0700` for the directory or `0600` for the file;
- reject path traversal and every activation identity that cannot map safely to exactly one filename;
- never overwrite or rename over an existing record;
- create no temporary file outside the approved directory;
- fail closed on permission, ownership, link, flush, parse or path uncertainty.

After exclusive creation, descriptor-based verification shall occur in this exact order before consumption is considered proven:

1. verify through the open descriptor that it refers to a regular file;
2. verify through the open descriptor that ownership is the current Sponsor user;
3. verify through the open descriptor that link count is exactly one;
4. verify through the open descriptor that mode is exactly `0600`;
5. write the exact deterministic JSON payload;
6. flush file contents;
7. call file `fsync`;
8. recheck regular-file status, ownership, link count and mode through the open descriptor;
9. close the file safely; and
10. call `fsync` on the approved parent directory.

Any uncertainty, failed verification, failed or short write, failed `fsync` or metadata change produces `POST_CONFIRMATION_CONSUMPTION_UNCERTAIN`. No Authentication Attempt reservation or listener construction may follow.

If the target platform or runtime cannot provide reliable descriptor-relative, exclusive, no-follow creation and verification:

`STOP — ESCALATE TO ENGINEERING ARCHITECT`

No weaker implementation, emulation, path-based fallback, race-prone precheck or silent downgrade is authorized.

Required behavior:

1. complete Activation Context validation succeeds;
2. final Sponsor confirmation succeeds;
3. the record is atomically created and authority becomes `CONSUMED`;
4. exactly one Authentication Attempt is reserved; and
5. exactly one listener is constructed.

An existing record, malformed record, unreadable record, unexpected object at the path, hard-link count other than one, ownership/permission mismatch or publication/activation mismatch fails closed. No record is overwritten, reset, repaired or deleted. Engineering cannot renew authority. Crash or restart preserves `CONSUMED` and cannot create another attempt.

`CONSUMPTION_STATE_UNCERTAIN` means the system cannot prove either that no durable consumption record was created or that one valid durable `CONSUMED` record was created and fully flushed. It includes an unknown exclusive-create result, partial write, failed file `fsync`, failed directory `fsync`, process interruption during persistence, unreadable or malformed existing record, ownership/permission/symlink/hard-link uncertainty, conflicting records or path ambiguity.

The controlled outcomes are:

| Category | Exact meaning and result |
|---|---|
| `PRE_CONSUMPTION_VALIDATION_FAILED` | Activation validation failed before final Sponsor confirmation or before durable consumption began. Authority remains unconsumed only when absence of a consumption record is proven. No external-effect factory may run. |
| `POST_CONFIRMATION_CONSUMPTION_UNCERTAIN` | Final Sponsor confirmation occurred and durable consumption began, but terminal record state cannot be proven. Classify as `CONSUMPTION_STATE_UNCERTAIN`; prohibit retry and require Chief Architect disposition. |
| `CONSUMED` | One valid durable record was exclusively created, fully written and both file and parent directory were flushed successfully. Only then may the Authentication Attempt be reserved. |

Every uncertain outcome fails closed with no Authentication Attempt reservation, listener construction, browser, Keychain, SDK or Provider call. No retry, Engineering reset, replacement or deletion is permitted. Disposition returns to the Chief Architect.

## 5.2 Timeout semantics

The Authentication Attempt timeout is a complete-lifecycle hard deadline of exactly 300 seconds. A monotonic absolute deadline starts immediately after successful durable consumption is proven and before Authentication Attempt reservation:

`deadline = monotonic_now + 300 seconds`

Before each bounded operation:

`remaining = deadline - monotonic_now`

If `remaining <= 0`, the operation shall not begin and the lifecycle terminates locally with the controlled timeout outcome.

The same absolute deadline governs:

- Authentication Attempt reservation;
- listener construction and bind;
- login URL generation;
- browser request;
- callback wait;
- API-secret Keychain retrieval;
- request-token exchange;
- intended-principal retrieval;
- `profile()` principal verification; and
- matched-only Authenticated Provider Context establishment.

Every bounded operation shall receive or derive no more than the remaining budget. The implementation shall not extend or restart the deadline between operations.

Mandatory local cleanup remains permitted after deadline expiry and shall itself use bounded local coordination. Cleanup cannot call a Provider endpoint or remotely invalidate a token.

---

# 6. Trusted activation and complete coordinated context

`src/kronos/provider/kite/live_activation.py` shall exclusively own the trusted activation-capability and coordinated Activation Context implementation.

The capability shall be immutable, redacted, non-serializable and unavailable through public constructors. Successful configuration loading, environment variables, command-line values, module globals, file presence, imports, tests, GUI state and synthetic objects cannot create activation authority.

The production provenance validator shall validate canonical repository and governance evidence before any external-effect factory. Sponsor instruction supplies final confirmation only; it cannot define, expand, repair or substitute activation identity.

The context shall represent and compare exactly and case-sensitively:

1. coordinated activation identity;
2. actual coordinated governance publication SHA;
3. logical CAR-016 publication reference;
4. logical CAR-017 publication reference;
5. frozen CAR-016 implementation SHA;
6. frozen CAR-017 implementation SHA;
7. effective timestamp and timezone;
8. expiry timestamp and timezone;
9. complete-lifecycle timeout of 300 seconds;
10. Sponsor environment reference;
11. exact hostname;
12. coordinated Provider identity `ZERODHA_KITE`;
13. operational Provider value `KITE`;
14. Provider configuration reference `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY`;
15. Kite application-registration reference `ZERODHA-KITE-APP-REGISTRATION-PRIMARY`;
16. secure-credential reference `KITE-API-SECRET-PRIMARY`;
17. intended-principal registration reference `KITE-INTENDED-PRINCIPAL-PRIMARY`;
18. composition dependency-set reference `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1`;
19. redirect URL `http://127.0.0.1:8765/kite/callback`;
20. attempt cardinality `ONE`;
21. Provider Availability authority `WITHHELD`;
22. maximum Provider Availability operation count `0`;
23. CAR-014 status `UNEXECUTED`; and
24. coordinated consumption state `UNUSED` before final confirmation.

The actual publication SHA remains post-publication evidence: it is obtained from the coordinated governance commit after creation and push, and is not required inside that commit. The trusted launcher shall require `develop`, local/origin alignment, HEAD equal to that post-publication SHA and a clean working tree.

Any missing, malformed, expired, ambiguous or mismatched field returns `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` before consumption, attempt reservation or dependency construction.

---

# 7. Configuration contract

The governed launcher shall use a dedicated authentication configuration path that does not invoke `.env` loading.

The path shall:

- preserve operational Provider value `KITE`;
- bind `ZERODHA_KITE` separately;
- bind `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` to the actual runtime configuration;
- bind `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` to the approved Kite application;
- accept only approved non-sensitive coordinated references;
- receive the Kite API key through an approved non-secret runtime mechanism outside chat, source, repository files and command arguments;
- keep API-secret and intended-principal values in Keychain only;
- never accept an API secret, access token, request token or principal value through `.env`; and
- never create activation authority.

The governed loader and launcher shall inspect only the exact allow-listed inputs below. They shall not dump or log the complete environment, enumerate all environment variables, retain a process-environment snapshot or apply a precedence rule that silently selects among conflicting settings, environment, launcher or Activation Context values. One authoritative source exists for each runtime reference. Duplicate agreeing projections may be cross-validated but not treated as independent authority; any conflicting projection fails closed before consumption or factory construction.

The exact governed process-environment projection is:

| Name | Permitted value or role |
|---|---|
| `KRONOS_PROVIDER` | exact operational value `KITE` |
| `KRONOS_KITE_API_KEY` | API key for the approved Kite application; non-secret configuration supplied in the inherited process environment only |
| `KRONOS_KITE_REDIRECT_URL` | exact value `http://127.0.0.1:8765/kite/callback` |
| `KRONOS_KITE_CREDENTIAL_REF` | exact value `KITE-API-SECRET-PRIMARY` |
| `KRONOS_KITE_INTENDED_REGISTRATION_REF` | exact value `KITE-INTENDED-PRINCIPAL-PRIMARY` |
| `KRONOS_PROVIDER_CONFIGURATION_REF` | exact value `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` |
| `KRONOS_KITE_APPLICATION_REGISTRATION_REF` | exact value `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` |

No command argument, `.env` file or GUI field may supply these values. The inherited environment is configuration evidence only. The trusted provenance function compares it with canonical coordinated governance, repository evidence, host evidence, time evidence and durable consumption state; no environment value can create or expand authority.

The remaining coordinated values are obtained as follows:

| Evidence | Authoritative runtime source |
|---|---|
| Coordinated identity, logical CAR references, frozen implementation references, activation window, timeout, Sponsor environment, Provider identity, dependency-set reference, availability boundary, cardinality and CAR-014 state | exact canonical CAR-016/CAR-017 coordinated governance content at current HEAD, verified through the trusted repository-evidence boundary |
| Actual coordinated publication SHA, branch, origin alignment and cleanliness | injected bounded Git evidence for the current worktree; no network fetch occurs |
| Hostname | standard-library hostname query, exact case-sensitive comparison |
| Runtime versions | running interpreter, tkinter and installed KiteConnect package metadata |
| Consumption state | exact durable-record path and fail-closed record inspection |
| Final Sponsor confirmation | one GUI confirmation after preflight; confirmation cannot alter any field |

The existing general loader may retain unrelated compatibility behavior. The governed authentication mode shall not call `load_dotenv()` and shall ignore authentication-secret environment fields.

No value representation, validation error, log or sanitized evidence may disclose sensitive material.

---

# 8. Real composition and sole launcher contract

The sole governed live entry point shall be:

`tools/provider_pilots/car017_live_authentication_launcher.py`

Required invocation:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/provider_pilots/car017_live_authentication_launcher.py
```

Direct import performs no activity. Ordinary direct launch of `car016_provider_authentication_gui.py` remains inspection-only.

The launcher shall:

1. load only non-sensitive governed configuration;
2. validate the complete context and trusted provenance;
3. display sanitized preflight only;
4. require final Sponsor confirmation;
5. atomically consume authority;
6. reserve one attempt;
7. compose the accepted live dependencies;
8. run no retry or second attempt; and
9. guarantee bounded local-only cleanup through a controlled terminal/finally path.

Only after successful validation and consumption may the accepted composition wire:

- `AppleKeychainCredentialSource`;
- `AppleKeychainIntendedPrincipalResolver`;
- the default operating-system browser through `KiteLoginNavigator`;
- one loopback listener on `127.0.0.1:8765` and `/kite/callback`;
- one Kite SDK authentication adapter;
- one `ProviderAuthenticationService`;
- one `KiteAuthentication`;
- one `KiteProvider`; and
- the accepted pilot controller and view.

Composition is wiring only. Construction remains externally inert until the governed sequence reaches its permitted operation. The navigator shall use the operating system default browser and shall not hardcode Chrome, Safari or any other browser.

The listener uses no alternate host or port. Port conflict, bind failure, Host mismatch, non-GET method, path mismatch, malformed callback, second request or timeout fails closed. First-request terminality remains mandatory.

Provider Availability verification remains `WITHHELD` with maximum operation count `0`. No composition or Sponsor instruction can enable, request or imply `verify_provider_availability()`.

---

# 9. Sanitized operation ledger

The one attempt shall retain a sanitized append-only operation ledger containing integer counts and controlled categories only for:

1. activation validation;
2. authority consumption;
3. attempt reservation;
4. listener construction;
5. listener bind;
6. login URL generation;
7. browser launch;
8. terminal callback;
9. API-secret retrieval;
10. `generate_session()`;
11. intended-principal retrieval;
12. `profile()` principal verification;
13. authenticated-context establishment;
14. local cleanup; and
15. Provider Availability verification.

All live-operation counts have maximum one except local cleanup, whose public outcome is one controlled terminal cleanup result, and Provider Availability verification, whose maximum and required count are zero.

The ledger shall not retain or derive secrets, tokens, principal values, callback/query material, URLs containing query data, headers, account identifiers, payloads, raw exceptions, tracebacks or Provider transport details. Its representation and any GUI projection remain sanitized.

---

# 10. Cleanup contract

Cleanup is separated into exactly these three categories.

## 10.1 `PRE_CONSUMPTION_VALIDATION_FAILED`

- occurs before final Sponsor confirmation or before durable persistence begins;
- absence of a record must be proven;
- perform local validation-object disposal only;
- perform no runtime resource cleanup because no runtime resource may have been constructed;
- no record creation or record-path mutation;
- no attempt reservation;
- no listener;
- no browser;
- no Keychain; and
- no SDK, network or Provider activity.

## 10.2 `POST_CONFIRMATION_CONSUMPTION_UNCERTAIN`

- final Sponsor confirmation occurred;
- durable persistence began;
- durable terminal state cannot be proven;
- perform local confirmation-object and persistence-object disposal only;
- perform no runtime cleanup;
- perform no further durable-record-path mutation;
- no creation, deletion, repair, truncation, reset, overwrite, replacement or rename;
- do not reserve an attempt;
- do not construct a listener;
- no browser, Keychain, SDK, network or Provider activity;
- retry is prohibited; and
- Chief Architect disposition is required.

## 10.3 `PROVEN_CONSUMPTION_RUNTIME_TERMINATION`

This category applies when a durable `CONSUMED` record was successfully created, verified and flushed and the runtime later terminates through failure, timeout, cancellation or success. Runtime construction may begin only after that proof. Bounded local cleanup applies only to runtime resources that were actually constructed. Preserve the durable `CONSUMED` record unchanged, keep authority `CONSUMED`, prohibit retry and remote token invalidation, and require CAR-016/CAR-017 Version 1.3 to record the later sanitized outcome.

Local-only runtime cleanup is mandatory after:

- attempt-reservation failure;
- listener construction or bind failure;
- browser refusal or exception;
- callback rejection or timeout;
- Keychain denial, absence or failure;
- request-token exchange failure;
- intended-principal retrieval failure;
- principal mismatch, unavailability or unconfirmed result;
- context-establishment failure;
- GUI close;
- successful context establishment followed by End KRONOS Session; and
- any unexpected controlled local failure.

Cleanup shall close local listener, HTTP-session and candidate resources where they exist, clear transient references and leave the durable consumption record intact. It shall never call `invalidate_access_token()`, terminate a Provider session or invoke another Provider endpoint.

Cleanup must never create the durable consumption record, delete it, repair it, truncate it, reset it, overwrite it, replace it, rename another file over it, alter its fields, change `CONSUMED` back to `UNUSED` or remove uncertainty through Engineering action. Only the original governed atomic-consumption operation may create the record.

Runtime cleanup begins only after durable consumption has been proven. Before proven consumption, only the narrowly defined local object disposal for the applicable pre-consumption or persistence-uncertainty category is permitted.

---

# 11. Keychain readiness contract

No CAR-018 implementation or test stage may access the real Keychain.

The later live preflight requires Sponsor attestation, without value retrieval, that these entries are provisioned:

| Purpose | Service | Account |
|---|---|---|
| Kite API secret | `com.project-kronos.provider-authentication.kite` | `api-secret:KITE-API-SECRET-PRIMARY` |
| Intended principal | `com.project-kronos.provider-authentication.kite` | `intended-principal:KITE-INTENDED-PRINCIPAL-PRIMARY` |

The API-secret entry shall correspond to the approved Kite application. The intended-principal entry shall contain the exact Kite `user_id` expected from `profile()`; its value is never displayed, logged or retained beyond one-operation custody.

API-secret and intended-principal purposes, references and accounts remain separate. Retrieval is exactly once per authorized live attempt and only after durable consumption.

---

# 12. External Kite readiness contract

Before later live authority, the Sponsor shall attest through non-sensitive evidence that:

1. the Kite application is active;
2. the configured API key belongs to `ZERODHA-KITE-APP-REGISTRATION-PRIMARY`;
3. the Keychain API secret belongs to the same application;
4. the registered redirect is exactly `http://127.0.0.1:8765/kite/callback`;
5. a valid Kite Connect subscription exists; and
6. no proxy, capture tool or browser extension is expected to alter or retain callback/request material.

The official login URL shall be generated once through the accepted Kite SDK behavior. The callback request token is exchanged once through `generate_session()`. Principal evidence is the exact `user_id` returned by `profile()`. No other profile field is required or retained.

---

# 13. Exact staged implementation authority

Canonical CAR-018 Version 1.0 publication activates Stage 1 eligibility only. It does not start Stage 1 and grants no commit or push authority by itself.

## 13.1 Stage 1 — trusted activation, durable consumption and typed contracts

**Files:**

1. `src/kronos/provider/kite/live_activation.py`
2. `src/kronos/provider/models/authentication.py`
3. `src/kronos/provider/contracts/provider_authentication.py`
4. `tests/unit/provider/test_kite_live_activation.py`

**Required result:** complete immutable coordinated context, production provenance validation, durable atomic consumption, complete-lifecycle deadline model and typed sanitized ledger contracts, with pre-factory rejection.

**Commit message after separate acceptance:**

`feat(authentication): add governed activation and consumption contracts`

**Gate:** Engineering Architect reviews the complete four-file diff, focused tests, full offline regression, durable-record behavior, ambient/synthetic rejection, secret scans and external-effect evidence. Separate commit and push authority is required. Stage 2 begins only from the accepted pushed Stage 1 SHA.

## 13.2 Stage 2 — governed configuration, composition, launcher and cleanup integration

**Files:**

1. `src/kronos/provider/kite/composition.py`
2. `src/kronos/configuration/settings.py`
3. `src/kronos/configuration/loader.py`
4. `src/kronos/provider/services/provider_authentication.py`
5. `src/kronos/provider/adapters/kite/client.py`
6. `src/kronos/provider/adapters/kite/authentication.py`
7. `tools/provider_pilots/car017_live_authentication_launcher.py`
8. `tools/provider_pilots/car016_provider_authentication_gui.py`
9. `tests/unit/tools/test_car017_live_authentication_launcher.py`
10. `tests/unit/provider/test_kite_authentication_composition.py`
11. `tests/unit/configuration/test_kite_connectivity_settings.py`
12. `tests/unit/provider/test_kite_authentication_adapter.py`
13. `tests/unit/tools/test_car016_provider_authentication_gui.py`

**Required result:** sole governed launcher, no-dotenv authentication mode, exact configuration binding, validated real-factory wiring, remaining-budget propagation, sanitized ledger integration, one-shot UI and guaranteed local cleanup.

**Commit message after separate acceptance:**

`feat(authentication): add governed live authentication launcher`

**Gate:** Engineering Architect reviews the complete thirteen-file diff, all focused tests, full regression, exact counters, cleanup matrix, import/inspection safety, runtime-version check, secret scans and proof of zero real external effects. Separate commit and push authority is required. Stage 3 begins only from the accepted pushed Stage 2 SHA.

## 13.3 Stage 3 — service conformance and final freeze

**File:**

1. `tests/unit/provider/test_provider_authentication_service.py`

**Required result:** final cross-layer conformance assertions for lifecycle deadline, atomic ordering, every terminal cleanup path, sanitized ledger, no duplicate path, Provider Availability count zero and complete offline regression. Production corrections discovered in Stage 3 are not permitted; they stop and escalate.

**Commit message after separate acceptance:**

`test(authentication): verify complete live authentication closure`

**Gate:** Engineering Architect reviews the one-file diff, all CAR-018 focused suites, complete offline regression, static path/cardinality scans, secret and sensitive-material scans, and confirms the exact 18 implementation/test paths are complete. Separate commit and push authority is required. The accepted pushed Stage 3 SHA becomes the frozen corrected implementation SHA only after final conformance acceptance.

No all-stage uncommitted candidate is authorized. No stage may amend a file allocated to another stage without a revised Chief Architect-approved scope.

---

# 14. Complete fake-only test matrix

All tests use injected fakes, synthetic callback requests, injected clocks and isolated temporary directories. They shall not use real Keychain, browser, production listener, SDK client, network or Provider endpoints.

| Obligation | Primary test file(s) |
|---|---|
| Every coordinated field, exact match and case sensitivity | `test_kite_live_activation.py` |
| Every missing, malformed and mismatched field | `test_kite_live_activation.py` |
| Trusted provenance and ambient/synthetic rejection | `test_kite_live_activation.py` |
| Publication SHA and branch/alignment/clean-state evidence | `test_kite_live_activation.py`, `test_car017_live_authentication_launcher.py` |
| Effective/expiry window and 300-second hard deadline | `test_kite_live_activation.py`, `test_provider_authentication_service.py` |
| Durable atomic consumption, restart/re-entry and corruption | `test_kite_live_activation.py` |
| Provider identity versus operational `KITE` | `test_kite_authentication_composition.py`, `test_kite_connectivity_settings.py` |
| Provider-configuration and application-registration binding | `test_kite_authentication_composition.py`, `test_kite_connectivity_settings.py` |
| No `.env` authentication-secret loading | `test_kite_connectivity_settings.py`, `test_car017_live_authentication_launcher.py` |
| Pre-factory zero-call rejection | `test_kite_authentication_composition.py`, `test_car017_live_authentication_launcher.py` |
| Sole launcher import and inspection safety | `test_car017_live_authentication_launcher.py`, `test_car016_provider_authentication_gui.py` |
| One default-browser request, no browser-specific dependency | `test_car017_live_authentication_launcher.py`, `test_car016_provider_authentication_gui.py` |
| One listener, callback, exchange and profile maximum | `test_kite_authentication_adapter.py`, `test_provider_authentication_service.py`, `test_car017_live_authentication_launcher.py` |
| Port conflict fail-closed; no alternate port | `test_car017_live_authentication_launcher.py`, `test_kite_authentication_composition.py` |
| Remaining-budget propagation; no late operation starts | `test_kite_authentication_adapter.py`, `test_provider_authentication_service.py` |
| Sanitized operation-ledger counts and non-retention | `test_provider_authentication_service.py`, `test_car017_live_authentication_launcher.py`, `test_car016_provider_authentication_gui.py` |
| Cleanup for every terminal path and UI close | `test_provider_authentication_service.py`, `test_car017_live_authentication_launcher.py`, `test_car016_provider_authentication_gui.py` |
| Provider Availability count permanently zero | `test_provider_authentication_service.py`, `test_car017_live_authentication_launcher.py`, `test_car016_provider_authentication_gui.py` |
| No duplicate authentication or Provider path | all CAR-018 focused tests plus static scan |
| Full regression, secret scan and sensitive-material scan | complete offline suite and repository scans |

---

# 15. Governance completion after implementation

After accepted and pushed Stage 3 implementation, no conformance or activation publication is implied or authorized by Stage 3 acceptance. The Chief Architect must first make the separate activation-disposition decisions in Section 1.

Only after that separate decision may a separately identifiable, separately reviewed and separately authorized documentation-only four-file conformance publication be prepared. It shall not rewrite canonical CAR-016 Version 1.2 or CAR-017 Version 1.2 in place.

If the Chief Architect authorizes that controlled amendment, it shall:

1. prepare CAR-018 Version 1.1 as the completed corrective conformance record;
2. record all three stage SHAs and the frozen corrected implementation SHA;
3. create separately identifiable controlled amendments for CAR-016 and CAR-017 that identify the prior canonical revision and preserve its complete history;
4. record the accepted Stage 3 SHA as the **Frozen CAR-018 Corrective Composite Implementation SHA** without erasing or relabelling historical CAR-016/CAR-017 implementation SHAs;
5. record the Chief Architect activation disposition;
6. record the new or retained activation identity and the new authority window, if any;
7. preserve Provider Availability `WITHHELD` and maximum count `0` unless a separate higher authority explicitly changes it;
8. synchronize the Document Register; and
9. publish exactly the four governance paths in Section 4.1 in one documentation-only coordinated governance commit.

That resulting commit establishes the new actual coordinated governance publication SHA as post-publication evidence. It need not contain its own SHA. The SHA shall be included in the post-publication report, later governed preflight, any final Sponsor instruction and the eventual CAR-016/CAR-017 Version 1.3 sanitized outcome.

The resulting coordinated publication SHA shall be recorded as post-publication evidence in the amendment history and required later evidence. It is not inserted into or required inside the commit that creates it.

After publication, rerun the complete governed preflight. Only a later explicit Sponsor instruction under the separately decided activation disposition may authorize one live attempt. CAR-018 implementation completion and conformance publication alone never grant live execution.

---

# 16. Explicit exclusions

CAR-018 does not authorize:

- architecture, DOMAIN or EDD modification;
- a nineteenth implementation/test path or twenty-third total path;
- dependency addition or dependency-file modification;
- a second authentication, callback, composition or Provider path;
- direct exchange-to-context establishment;
- automatic availability verification;
- retry, polling, scheduling or automatic login;
- alternate host, port, callback path or browser-specific dependency;
- plaintext secret, `.env` secret, token or principal persistence;
- remote token invalidation or Provider session termination;
- Provider Availability verification;
- Instrument Master, historical data, quote, LTP, OHLC or WebSocket operations;
- orders, trades, holdings, positions, funds, margins or trading;
- CAR-014 execution;
- real Keychain access, browser opening, listener binding, SDK construction, network or Provider activity during implementation and verification; or
- live execution before final coordinated governance publication, preflight and separate Sponsor authority.

---

# 17. Stop-and-escalate rules

Work stops before the affected action if:

1. any path outside Section 4 is required;
2. `pyproject.toml`, `uv.lock` or another dependency file must change;
3. architecture, DOMAIN-006 or EDD-001 must change;
4. official Kite behavior conflicts with canonical KRONOS meaning;
5. operational Provider `KITE` semantics must change;
6. another public authentication, callback, composition or Provider path is required;
7. a real external effect is required for implementation verification;
8. durable consumption cannot be implemented with the frozen standard-library abstraction;
9. the complete-lifecycle deadline cannot be enforced through the authorized adapter/service paths;
10. sensitive material would enter logs, errors, evidence or the consumption record;
11. a stage must modify a path allocated to another stage;
12. CAR-014 would be affected; or
13. current `develop`, `origin/develop`, the required stage baseline or working-tree cleanliness is not exact.

No Engineering or Sponsor instruction can waive a stop condition or renew consumed/uncertain authority. Ambiguity returns to the Chief Architect.

---

# 18. Publication and authority lifecycle

CAR-018 Version 1.0 was approved and canonically published at
`dd8caa77b4c896628633d269c9c56775b24f6cfa`. The Version 1.1
implementation-conformance amendment is Approved Canonical in the coordinated
four-file publication and remains without runtime or live authority.

Canonical Version 1.0 publication shall contain only:

1. this CAR-018 record; and
2. the synchronized Document Register.

The publication commit activates eligibility for a separately instructed Stage 1 only. It does not start implementation, authorize all stages, access credentials, create the consumption record or consume coordinated live authority.

For every stage, stage-start authority, evidence acceptance, commit authority, push authority and next-stage authority are distinct. No one gate implies another.

Version 1.1 records completed implementation conformance and the frozen
corrected implementation SHA. Its canonical publication grants no runtime or
live authority.

CAR-016 and CAR-017 Version 1.3 remain reserved for the sanitized consumed-authority outcome of any later live attempt. CAR-018 does not reuse those versions for correction.

---

# 19. Closure assertion

The exact 22-path, three-stage programme closes every known repository-visible blocker from the Complete Authentication Closure Review:

- sole live entry point;
- trusted provenance;
- complete coordinated context;
- provider identity/configuration binding;
- durable consumption;
- hard lifecycle timeout;
- sanitized cardinality evidence;
- no-dotenv governed configuration;
- real dependency composition;
- terminal cleanup;
- runtime-version freeze;
- Keychain readiness; and
- external Kite readiness.

No additional known repository blocker remains outside this package. Provider rejection, Sponsor cancellation, browser refusal, bind conflict, callback rejection, Keychain denial, exchange failure and principal mismatch remain legitimate governed runtime outcomes after closure; they are not omitted implementation scope.

---

# 20. Required pre-canonical verification

Before Chief Architect publication review, verify:

- current branch `develop` at baseline `4c5c6ec8fe1a315411725e29ff14291d98355d86`;
- local and `origin/develop` alignment;
- exactly this CAR-018 candidate and the Document Register changed;
- unique `CAR-018` identity;
- exactly 22 unique authorized paths;
- exactly four governance paths and 18 implementation/test paths;
- all 18 implementation/test paths assigned exactly once across Stages 1–3;
- governance/runtime/live authority separation;
- durable consumption and timeout decisions present;
- official-source boundary present;
- documentation and local-link checks pass;
- `git diff --check` passes;
- secret and sensitive-material scans pass; and
- no credentials, Keychain, browser, listener, SDK, network or Provider activity occurred.

---

## Approved Canonical post-correction CA2 activation disposition

**CAR-016 Controlled Amendment:** `CAR-016-V1.2-CA2`

**CAR-017 Controlled Amendment:** `CAR-017-V1.2-CA2`

**Controlled Amendment Status:** Approved

**Canonical Status:** Canonical Controlled Amendment

**Workflow Stage:** Repository Publication

**Frozen CAR-018 Corrective Composite Implementation SHA:** `7fdec7887faa94b5fd52ab59b01b023e726f7a68`

| Controlled value | Exact disposition |
|---|---|
| Previous coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` |
| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |
| New coordinated activation identity | `KRONOS-COORD-AUTH-20260806-003` |
| Effective | `2026-08-07T09:00:00+05:30 Asia/Kolkata` |
| Expiry | `2026-08-14T09:00:00+05:30 Asia/Kolkata` |
| Attempt cardinality | `ONE` |
| Consumption state | `UNUSED` |
| Provider Availability | `WITHHELD — MAXIMUM 0` |
| CAR-016 controlled amendment | `CAR-016-V1.2-CA2` |
| CAR-017 controlled amendment | `CAR-017-V1.2-CA2` |
| CAR-016 CA2 logical publication reference | `CAR-016-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` |
| CAR-017 CA2 logical publication reference | `CAR-017-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` |
| CA2 coordinated governance publication commit SHA | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` |
| CAR-014 | `UNEXECUTED` |

Every field below must match byte-for-byte across CAR-016 CA2, CAR-017 CA2 and
this CAR-018 CA2 disposition. A missing, additional, normalized, inferred,
substituted or unequal value fails closed.

| Activation Context field | CAR-016 CA2 | CAR-017 CA2 | CAR-018 CA2 | Equality |
|---|---|---|---|---|
| Coordinated activation identity | `KRONOS-COORD-AUTH-20260806-003` | `KRONOS-COORD-AUTH-20260806-003` | `KRONOS-COORD-AUTH-20260806-003` | MATCH |
| CA2 coordinated governance publication commit SHA | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | `PENDING — ESTABLISHED BY THE FOUR-FILE CANONICAL PUBLICATION COMMIT` | MATCH; replaced by the resulting publication SHA as post-publication evidence |
| Logical CAR-016 CA2 publication reference | `CAR-016-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | `CAR-016-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | `CAR-016-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | MATCH |
| Logical CAR-017 CA2 publication reference | `CAR-017-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | `CAR-017-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | `CAR-017-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003` | MATCH |
| Frozen CAR-016 implementation SHA | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | `bb5aa16fbc4fda2609376d53161d591fb0fe0d36` | MATCH |
| Frozen CAR-017 implementation SHA | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | `8f052d0cc3b7abc63a28c2951a3b4770c58b4454` | MATCH |
| Frozen CAR-018 corrective composite implementation SHA | `7fdec7887faa94b5fd52ab59b01b023e726f7a68` | `7fdec7887faa94b5fd52ab59b01b023e726f7a68` | `7fdec7887faa94b5fd52ab59b01b023e726f7a68` | MATCH |
| Authority effective timestamp | `2026-08-07T09:00:00+05:30` | `2026-08-07T09:00:00+05:30` | `2026-08-07T09:00:00+05:30` | MATCH |
| Authority effective timezone | `Asia/Kolkata` | `Asia/Kolkata` | `Asia/Kolkata` | MATCH |
| Authority expiry timestamp | `2026-08-14T09:00:00+05:30` | `2026-08-14T09:00:00+05:30` | `2026-08-14T09:00:00+05:30` | MATCH |
| Authority expiry timezone | `Asia/Kolkata` | `Asia/Kolkata` | `Asia/Kolkata` | MATCH |
| Authentication Attempt timeout | `300 seconds` | `300 seconds` | `300 seconds` | MATCH |
| Sponsor environment reference | `SPONSOR-MACOS-LOCAL-NONPROD-01` | `SPONSOR-MACOS-LOCAL-NONPROD-01` | `SPONSOR-MACOS-LOCAL-NONPROD-01` | MATCH |
| Approved hostname | `Imrans-Mac-mini.local` | `Imrans-Mac-mini.local` | `Imrans-Mac-mini.local` | MATCH |
| Provider identity | `ZERODHA_KITE` | `ZERODHA_KITE` | `ZERODHA_KITE` | MATCH |
| Operational Provider value | `KITE` | `KITE` | `KITE` | MATCH |
| Provider configuration reference | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | `ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY` | MATCH |
| Kite application-registration reference | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | `ZERODHA-KITE-APP-REGISTRATION-PRIMARY` | MATCH |
| Secure-credential reference | `KITE-API-SECRET-PRIMARY` | `KITE-API-SECRET-PRIMARY` | `KITE-API-SECRET-PRIMARY` | MATCH |
| Intended-principal registration reference | `KITE-INTENDED-PRINCIPAL-PRIMARY` | `KITE-INTENDED-PRINCIPAL-PRIMARY` | `KITE-INTENDED-PRINCIPAL-PRIMARY` | MATCH |
| Composition dependency-set reference | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | `CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1` | MATCH |
| Redirect URL | `http://127.0.0.1:8765/kite/callback` | `http://127.0.0.1:8765/kite/callback` | `http://127.0.0.1:8765/kite/callback` | MATCH |
| Attempt cardinality | `ONE` | `ONE` | `ONE` | MATCH |
| Provider Availability Verification Authority | `WITHHELD` | `WITHHELD` | `WITHHELD` | MATCH |
| Maximum Provider Availability verification operations | `0` | `0` | `0` | MATCH |
| CAR-014 status | `UNEXECUTED` | `UNEXECUTED` | `UNEXECUTED` | MATCH |
| Coordinated consumption state | `UNUSED` | `UNUSED` | `UNUSED` | MATCH |
| Controlled invalid-activation category | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | `COORDINATED_LIVE_ACTIVATION_NOT_AUTHORIZED_OR_CONTEXT_MISMATCH` | MATCH |

CA2 supersedes CA1 for execution selection only. The complete existing CA1
disposition and equality matrix remain canonical historical evidence and are
not eligible for future execution selection. Fallback, revival, renewal,
aliasing or execution through either retired activation identity is prohibited.

Publication alone performs no preflight, consumes no authority, reserves no
Authentication Attempt and grants no Sponsor execution authority. Provider
Availability Verification Authority remains `WITHHELD` with maximum operation
count `0`; CAR-014 remains `UNEXECUTED`. CAR-016 and CAR-017 Version 1.3
remain reserved for the sanitized post-attempt outcome.


# End of Document
