# ADR-0048: WO-06H same-epoch compatibility restoration

**Status:** Approved bounded engineering; production invocation remains separately authorized.

## Context

WO-06H has three different lifecycle operations. Successor commissioning creates a new epoch, acceptance and research window under an exact commissioning authorization. Exact restoration rebinds an existing acceptance when the current capability equals the accepted proof. A deterministic-digest correction can instead leave the accepted semantics unchanged while changing the `WO_06H_ACCEPTANCE_EPOCH` proof from 1.1.0 to 1.2.0. In that last case, an immutable `DIGEST_SCOPE_COLLATERAL` compatibility record establishes authority for the one historical/current proof pair.

The successor endpoint previously revalidated its original commissioning authorization before reaching its idempotent branch. That authorization correctly remains bound to the process and revision that created the epoch, so it cannot authorize restoration on a later compatible process.

## Decision

Add `KRONOS-WO06H-SAME-EPOCH-COMPATIBILITY-RESTORATION/1.0.0` as a distinct maintenance-only application contract. Its request binds the existing epoch, acceptance and window; the complete server-observed current runtime proof; its complete capability identity; one retained compatibility identity; the compatibility record's Sponsor/EA authorization reference; and content-addressed request identity and integrity.

The application validates CURRENT and the complete epoch chain, the bound acceptance/window artifacts, clean current process identity, the exact 1.2.0 capability proof, compatibility and diagnosis integrity, `DIGEST_SCOPE_COLLATERAL`, the exact historical/current proof pair, unchanged configuration, unchanged live-shadow calculation, and every other protected capability. It then calls the existing `restore_epoch` operation. It neither calls nor weakens successor commissioning.

The surface is available only during server-owned maintenance and quiescence. Same-origin transport accepts only the exact JSON schema. Unknown fields, including new epoch, acceptance, window, migration or backfill parameters, fail closed. Duplicate invocation revalidates all authority and returns the same process-local restored state.

## Consequences

- Successor commissioning continues to require its original exact commissioning authorization and remains the only path that can create a successor epoch.
- Ordinary exact restoration remains unchanged and requires no compatibility record.
- Compatibility restoration applies only to one current existing epoch and one exact immutable 1.1.0 to 1.2.0 record.
- No revision allowlist, digest allowlist, force flag or generic compatibility switch exists.
- Restoration creates no acceptance, epoch, window, pointer, cohort, research period, observation or backfill record.
- Provider, Discovery, Review, Chart Analyst, WO-07F, WO-09, WO-10, WO-11 and broker authority remain outside this contract.

## Qualification boundary

Qualification uses isolated stores and an exact documented production-case inventory. It proves current counts `0/0/0`, historical counts `34/66/0`, preservation of the retained epoch/acceptance/window, idempotency, strict invalid-record cases, unchanged exact restoration and unchanged successor commissioning. Production compatibility restoration and maintenance exit require separate operational authorization.
