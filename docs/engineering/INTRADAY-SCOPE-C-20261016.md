# Intraday limited machine history — Scope C

Status: Unpublished engineering candidate; qualification and exact-byte review pending at initial drafting. Release and runtime authority NOT GRANTED.
Owner: EA-Intraday, with PCP Browser and EA-Swing shared-composition review.
Authority: KRONOS-INTRADAY-SCOPE-C-20261016-01 Sponsor engineering order.
Base: 91231f74341c135f8ab370edf02afeea50cde108.

## Design and limits

Controlling R2 design manifest: 23bdcf5aded6ff0197ef0bcf6ba1af6dee94a31c5612cea6009d958f1b88b9f1.
Controlling reviewed ZIP: 93b68dc52e1dacea876118732ecc5e727233c2e4aa51292a19ac6e25b65b32fa.
Both PCP and EA-Swing approved that pre-implementation design. Implemented bytes require fresh exact-byte review.

GET /intraday/review/machine-history exposes existing prepared recent-five Analysis navigation and complete exact selected-run assessment populations, in original order, default25/max50. Known exact runs remain readable outside the recent window, with explicit historical-only labels. This is not a complete historical READY/NOW catalogue. Full historical discovery remains a separate requirement.

Exact supplied readiness is joined only through validated identity and full assessment/run/subject/direction/session/method/contract lineage. Missing readiness is explicit. The existing public reader conflates absent and unequal first-five proof; REQUIRED_PROOF_NOT_ESTABLISHED withholds readiness/score/criteria/first-five values for both. Decode/integrity/path/association errors remain422, storage503. No proof is bypassed or reconstructed.

The fingerprint binds complete selected evidence and page size. Conflict409 requires explicit run-only page-one reload; no automatic recapture/retry. Canonical injection reuses existing stores and bound history reader. No durable index, producer write, persistence API, global lock, Provider, monitoring, notification, lifecycle, calendar or startup behavior changes. Entered-position safety is independent of this historical view. Visual history and artifact paths are preserved.

## Engine registry synchronization assessment

Reviewed docs/ENGINE_STATUS.md and docs/architecture/ENGINE_OWNERSHIP.md against this scope. This Python/Browser historical read-model capability changes no Pine engine source, engine version, engine status, lineage or ownership. Both registries remain synchronized without content changes. TradingView compilation and representative trading-symbol validation are not applicable to these Python/Browser-only bytes; isolated source and synthetic subject/contract checks provide the applicable validation. No engine state is changed merely to satisfy a release checklist.

## Qualification and release boundary

Use canonical Python -B tools/kronos_test.py with importlib collection for the two approved same-basename owning modules. Qualify three new owning files and thirteen protected selections against frozen actual bytes. Keep all intermediate failures and exact JUnits in the external engineering package. Complete disposable desktop/narrow rehearsal before final freeze. No A/B full679/27 rerun or Sponsor acceptance reopening.

Publication, canonical app build/install, maintenance, runtime transition and deployed/Sponsor acceptance require later authority. No production workflow is authorized by this record. Candidate results and review responses belong to the exact-byte external handover; this initial record does not claim future outcomes already occurred.
