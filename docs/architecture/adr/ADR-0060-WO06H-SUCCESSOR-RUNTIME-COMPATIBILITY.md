# ADR-0060 — WO-06H explicit successor-runtime compatibility

**Status:** CA-approved architectural direction; bounded engineering candidate, exact-byte and shared-runtime owner review pending. Production enrollment and recovery are not authorized.
**Version:** 1.0.0
**Owner:** EA-Intraday / WO-06H; Chief Architect; EA-Swing/shared runtime.
**Authority:** Sponsor engineering order 65369fc4-a443-4df0-8879-c50e080b197c, CA_APPROVES_BOUNDED_WO06H_SUCCESSOR_COMPATIBILITY_WORK, 10 October 2026.
**Extends:** ADR-0043, ADR-0044, ADR-0047, ADR-0048 and ADR-0050 additively. None is superseded or rewritten.

## Purpose and context

The released research-only WO08 composition changes Discovery, Trusted-Time and Accounting implementation digests. Retained acceptance also predates the deterministic epoch digest. Complete equality and the narrow legacy 1.1.0→1.2.0 exception correctly reject this runtime. Diagnosis package SHA-256 c6831b3e1f7095b36041d6fed623c3086d85765b0a7328cf37f62358c6db0481 establishes reviewed semantic compatibility, not implementation equality or enrolled authority.

## Decision

Add a separate immutable `successor_compatibility` record with relation schema `KRONOS-WO06H-SUCCESSOR-RUNTIME-COMPATIBILITY/1.0.0` in the existing epochs-v1 store/envelope. Preserve exact equality, legacy compatibility class/schema/validator/selection and historical bytes. Restoration tries equality, then lawful legacy relation, then one exact approved successor relation. Otherwise it remains SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE or a bounded integrity/compatibility failure. Malformed matching authority is not skipped in search of another permission.

The relation binds the original acceptance, epoch, window, original start/end, complete sorted source and target declaration maps, exact configuration and independently recomputed aggregate identities. It declares SOURCE_TO_TARGET and non_transitive=true. Its changed set must equal the exact complete recomputed difference: each row retains predecessor/successor identity, version and implementation digest, source-delta hash, reason for digest change, semantic impact, owning/protected qualification hashes and failure behavior. Added/removed capabilities are outside this bounded V1. Frozen WO_06H_LIVE_SHADOW calculation equality remains mandatory.

It binds semantic-assessment identity/hash, this ADR identity/version, evidence-package identity/hash, and approval references for EA-Intraday/WO06H, CA, EA-Swing/shared runtime and Sponsor. References and content hashes are not digital signatures. The existing trusted local enrollment boundary must retain only separately approved exact documents; arbitrary local JSON is not Sponsor authority. No enrollment endpoint or automatic enrollment is added.

The complete content-addressed relation binds each approval/evidence reference to the exact source/target and reviewed change set. All required approvals must be APPROVED for restoration. An offline draft check may verify exact binding with pending approvals, but every restoration caller uses the approval-enforcing default. That draft does not confer runtime authority.

## Direction and selection

Lookup requires exact epoch/source aggregate/target aggregate. No wildcard, reverse relation, proof substitution, parent intermediate, relation traversal or A→B→C inference exists. More than one matching relation is ambiguous and rejected, including differing approval/evidence records. The relation validates complete target map/configuration; another implementation digest or version requires another independently governed direct relation.

## Identity and provenance

Implementation provenance stays exact. Existing marshal/code-object derivation for composed operations is unchanged, including position metadata. Existing acceptance-epoch AST derivation is unchanged; its explicit policy/callable inputs add the successor grammar and validator/selector. The component version remains 1.2.0; its exact digest changes. The successor relation version is independent. An unchanged version never implies equivalence.

The final candidate map must be computed after all protected changes. The future relation binds the original accepted map directly to that final target, including the changed epoch digest and the three composition digests. It must not bind the pre-correction 2a4983... map or chain through healthy parent90b5e3.... Candidate map calculation is engineering evidence; actual clean loaded declarations must match at future recovery.

## Restoration, persistence and window

Existing no-follow directory traversal, canonical encoding, exclusive immutable hard-link publication, fsync, locks and current-pointer validation are reused. No new store, coordinator, pointer or transaction framework is introduced. Successor restoration only rebinds process-local authority using the existing restoration/reconciliation path. It creates no acceptance, epoch, window, observation, transition, compatibility record or backfill.

The original window remains 2026-09-12T07:50:33.006722+05:30 through 2026-10-12T07:50:33.006722+05:30. Validation requires start ≤ current time < end. Equality at end rejects. No restamping, extension, new acceptance, replacement window or fenced-period reconstruction is permitted. Recovery after expiry cannot activate this window.

## Qualification and release

Owning tests cover exact binding, full deltas, versions, reverse/chained/wildcard relations, missing evidence, pending approvals, tampering, duplicate/conflicting relations, storage failure, direct restart, legacy precedence and original-window expiry. Protected suites cover research calculations/cohorts, trusted time, accounting, acquisition/callback isolation, startup/maintenance, 120-second readiness, Swing restoration and WO08 Option A.

Exact-byte independent review precedes EA-Intraday, CA and EA-Swing/shared-runtime owner review. No Browser or launcher contract changes are included. Production enrollment, commit/publication/install/runtime transition and maintenance exit require separate Sponsor authority. PID12985 remains FAILED_ACTIVE with Provider disconnected throughout this engineering task.
