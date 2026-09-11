# WO-06H successor epoch commissioning V1

**Status:** Approved bounded engineering, Sponsor / EA 11 September 2026; operational enrollment/commissioning not authorized by engineering.
**Governing decision:** [ADR-0043](../adr/ADR-0043-WO06H-SUCCESSOR-ACCEPTANCE-EPOCHS.md).
**Owner:** Intraday acceptance infrastructure; Browser supplies process maintenance and quiescence facts.

## Request and response

`POST /control/intraday-live-shadow/successor-epoch/v1`, same-origin, `application/json`, no query, at most 4096 bytes. Exact keys: `action` = `COMMISSION_SUCCESSOR_EPOCH`, `request_identity` = 1–128 ASCII alphanumeric/underscore/hyphen characters, `authorization_identity` = exact retained `WO06H-AUTHORIZATION-<sha256>` identity. Unknown fields reject. No caller-supplied active/idle/authorized booleans are accepted.

Success returns `ESTABLISHED` or `ALREADY_ESTABLISHED`, exact epoch identity and read-only live-shadow status. Rejection is HTTP 409 with `SHADOW_SUCCESSOR_COMMISSIONING_REJECTED` (same-origin admission may reject earlier). Domain exceptions retain bounded detailed failure codes for isolated qualification; arbitrary HTTP request bodies or secrets are not persisted. Ordinary `/intraday/live-shadow/accept-runtime` is unchanged and blocked by maintenance dispatch. It never commissions a successor.

The server holds its Sponsor-work/shutdown lock through dispatch. Other admitted Sponsor work, analysis, native review, in-flight Provider connection or live monitoring test rejects. Product checks additionally reject active Intraday Discovery or V2 Review operations. Maintenance remains active after success. There is no Provider call or maintenance-exit dispatch in the commissioning dependency path.

## Immutable authority documents

Namespace: existing research store `live-shadow-v1/epochs-v1/`. Exact document envelope: `policy`, `kind`, `body`, `identity`, `integrity`. Policy is `KRONOS-WO06H-ACCEPTANCE-EPOCH/1.0.0`. `identity` is a kind-prefixed SHA-256 of the canonical policy/kind/body core; `integrity` hashes that core plus identity. Unknown keys, noncanonical encoding, identity mismatch, symlinked paths and missing records reject.

Exact body keys by kind:

| Kind | Keys |
| --- | --- |
| authorization | request, predecessor, proof, diagnosis, expires_at, sponsor_reference |
| diagnosis | classification, subject_revision, predecessor_proof, calculation_digest, changed_semantics, report_sha256, sponsor_reference |
| epoch | acceptance, window, start, end, proof, methodology, narrow_cpr, classification, created_at, predecessor, diagnosis, request |
| transition | epoch, previous, request, authorization, effective_at |

Runtime `proof` uses the existing exact shape: manifest, pid, revision, source_state, startup, configuration, capabilities. Capability entries bind identity/version/implementation_digest. `methodology` is `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2/2.2.0`; `narrow_cpr` is the existing methodology publication identity, not a new formula. Actual acceptance/window artifacts retain their existing schemas; their proofs/identities/time bounds must agree with the epoch.

Before commissioning, a separately authorized trusted operator must enroll the exact reviewed diagnosis and explicit Sponsor authorization. The diagnosis binds report SHA-256, classified material change, diagnosed source revision, predecessor proof and unchanged calculation. Authorization binds that diagnosis, predecessor epoch, current process proof, bounded expiry and Sponsor evidence reference. No HTTP method enrolls these records. Filesystem access is the existing local evidence trust boundary; hashes prove integrity, not the initiating human. No Sponsor attribution is inferred from localhost or an Origin header.

Commissioning verifies actual `develop`, HEAD, origin/develop and directly queried remote against the authorized loaded revision, clean worktree, and diagnosed-commit ancestry. Network failure or unverifiable remote rejects before authority publication. Tests substitute an isolated repository gate. Exact-repeat idempotency still verifies maintenance, idle state, exact proof and repository; it does not mint authority after expiry. Reuse of a completed noncurrent request rejects.

## Read/accounting contract

Existing status retains current-only `window`, `acceptance_identity`, `counts`, `enabled` and disposition. Additive fields: `current_epoch`, `epochs`, `all_epoch_counts`, `epoch_failure`. Each epoch entry exposes identity, acceptance, window, dates, methodology, CPR publication, predecessor/successor, superseded_at, current, compatibility, counts. There is exactly one current entry when authority is established. Historical incompatibility does not prevent historical reporting. Corrupt authority yields an explicit read failure; zero or an older compatible epoch is never substituted.

Original singleton metadata remains read-only and deterministic. New observations carry explicit epoch + acceptance + window, while historical observations without the additive fields map only through their bound original window. Current ledgers and EOD reads cannot select another epoch's row. Supersession never moves observations. Explicit all-epoch reporting aggregates counts only; no production admission, P&L or outcome authority is implied.

## Failure and restart contract

Wrong/dirty process, repository drift, missing authorization/diagnosis, non-material diagnosis, wrong predecessor, changed calculation, unbound or unreviewed Trusted-Time semantics, current compatibility, active work, conflicting request, window/epoch conflict, invalid chain or pointer all fail closed. Authority publication creates only immutable acceptance/window/epoch/transition and necessary integrity/lock/legacy-anchor records. Current-pointer replacement occurs last and is atomic. Failed unpublished preparation requires review; do not delete it or backdate a later attempt.

Restart loads exactly CURRENT and bound chain, validates the current proof against the new process, and restores only if compatible and within the current window. No recency scan, old-epoch fallback, historical rewrite, acceptance creation, Provider operation or backfill occurs. For future production use: separately authorize publication, controlled clean load, exact authority enrollment, successor commissioning, verification, then any maintenance exit. This order implements capability only.

## Capability-boundary bridge — successor contract 1.1.0

**Status:** Approved bounded correction by [ADR-0044](../adr/ADR-0044-WO06H-SUCCESSOR-CAPABILITY-BOUNDARY.md); no production enrollment under engineering.

This section supersedes cross-epoch equality of the composed Trusted-Time capability. Same-epoch restoration still uses exact complete capability/configuration equality. `WO_06H_ACCEPTANCE_EPOCH/1.1.0` declares the corrected infrastructure; original document policy and existing persisted schemas remain readable.

New immutable `bridge` kind uses `WO06H-BRIDGE-<sha256>` identities and the existing canonical envelope/integrity mechanism. Exact body fields:

| Field | Required binding |
| --- | --- |
| predecessor | Exact validated predecessor epoch identity |
| predecessor_capability | `WO06H-CAPABILITY-<sha256>` over its sorted complete capability map and configuration |
| current_proof | Exact server-derived clean runtime proof, including revision, manifest, configuration, PID, startup and all declarations |
| current_capability | Independently recomputed capability identity for current_proof |
| diagnosis | Exact retained material-change diagnosis identity |
| classification | ACCEPTANCE_MATERIAL_CHANGE |
| changed_capabilities | Sorted exact rows `{identity, predecessor, successor}`; absent declarations use null; versions/digests and all added/removed classes are explicit |
| unchanged_capabilities | Sorted full equal declarations; no omission or extra entry |
| changed_semantics | Exact nonempty reviewed diagnosis changed_semantics text |
| unchanged_semantics | Exactly `[METHODOLOGY_2_2_0, NARROW_CPR, TRUSTED_TIME_ADMISSION, WO_06H_CALCULATION]` in this order |
| methodology | Existing full methodology identity ending /2.2.0 |
| narrow_cpr | Existing unchanged CPR publication identity |
| sponsor_reference | Exact explicit Sponsor evidence reference also bound by authorization |

New authorization bodies include the existing six fields plus `bridge`. Historical six-field authorization documents remain readable; they cannot commission a new successor. The reference chain authorization → bridge → diagnosis binds Sponsor approval without a circular hash dependency. The diagnostic report's SHA-256, predecessor proof, source revision and reviewed semantic change remain mandatory. A semantic-invariant statement alone does not grant approval: enrollment must use the separately approved exact report and Sponsor evidence; a content hash is not a human signature.

The application checks current startup and manifest integrity, clean process identity, exact authorized revision/proof, repository synchronization, predecessor raw window/acceptance/epoch consistency, bridge integrity, complete recomputed capability delta and unchanged research calculation. Current Trusted-Time/WO-05A, Discovery and WO-05B declarations match the explicitly authorized current proof. They need not equal the predecessor composite declarations. This grants authority to create B only; it never marks A compatible with B.

The current material-change report proves unchanged admission behavior despite the changed WO-05A composite digest. No offline-computed digest is substituted for a running runtime proof. Future enrollment must read the actual clean runtime proof after deployment and bind it to the reviewed transition.

Canonical failures include `SHADOW_PREDECESSOR_EPOCH_INVALID`, `SHADOW_PREDECESSOR_CAPABILITY_INVALID`, `SHADOW_CURRENT_CAPABILITY_INVALID`, `SHADOW_CURRENT_RUNTIME_NOT_CLEAN_COMMIT`, `SHADOW_SUCCESSOR_REVISION_MISMATCH`, `SHADOW_COMPATIBILITY_DIAGNOSIS_MISSING`, `SHADOW_COMPATIBILITY_DIAGNOSIS_MISMATCH`, `SHADOW_COMPATIBILITY_CLASSIFICATION_NOT_MATERIAL`, `SHADOW_SUCCESSOR_CAPABILITY_NOT_BOUND`, and `SHADOW_SUCCESSOR_AUTHORIZATION_MISSING`. Existing predecessor/pointer/immutable-conflict codes cover conflicting successor requests. HTTP continues to return the existing bounded `SHADOW_SUCCESSOR_COMMISSIONING_REJECTED` envelope. Same-epoch mismatch retains `SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE`; changed research calculation retains `SHADOW_FROZEN_IMPLEMENTATION_CHANGED`.

Atomic CURRENT publication, strict chain validation, original research dates, zero initial successor counts, no backfill and separate maintenance exit are unchanged. No bridge can be supplied in the HTTP request or self-enrolled by that request. Ordinary Acceptance POST remains blocked during maintenance.
