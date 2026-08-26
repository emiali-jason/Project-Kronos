# KRONOS Intraday WO-05 Native Discovery Runtime

**Status:** WO-05 engineering review candidate
**Runtime identity:** `KRONOS-INTRADAY-NATIVE-DISCOVERY-RUNTIME-V0 / 0.1.0`
**Application identity:** `KRONOS-INTRADAY-DISCOVERY-APPLICATION-V0 / 0.1.0`

## Governing bindings

The runtime consumes the exact published
`KRONOS-INTRADAY-NATIVE-UNIVERSE-V1 / 1.0.0` and
`KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1 / 1.0.0`.
Every execution binds one explicit DOMAIN-008 session identity, one session
boundary identity and one timezone-aware observation boundary. It accounts for
all governed members in publication order before producing deterministic
identities.

## Runtime architecture

`IntradayNativeDiscoveryService` coordinates the product-owned operation. An
injected factual-source boundary supplies one completed governed machine-fact
bundle for each reconciliation member whose machine-fact path is consumable.
The service does not authenticate, select Provider contracts, access private
Provider context, calculate candidate admission, or acquire Browser authority.

One member failure becomes a bounded factual-failure result while remaining
members continue. Prerequisite-unavailable members never reach the factual
source. All results preserve execution eligibility `NOT_ESTABLISHED`.

The factual adapter reuses the existing Slice 1–3 contracts for DOMAIN-008,
completed governed 1D/1H/15M/5M OHLCV, completeness reconciliation,
previous-session facts, Pivots/CPR, structure and shadow telemetry. Only the
session fact, completed four-timeframe OHLCV and four reconciliation facts are
mandatory. Telemetry cannot create candidate consequence.

## Persistence and restart

`NativeDiscoveryStore` retains machine-fact bundles, all member results and the
run by explicit deterministic identity. Writes are atomic and immutable;
identical duplicates are idempotent and conflicts fail closed. Restart
reconstruction requires an explicit run identity and then loads every referenced
bundle explicitly. Directory order and latest-file selection have no authority.

The application keeps current failure separate from the last successful run.
A failed invocation cannot erase or replace retained successful evidence.

## Application and Browser projection

`IntradayDiscoveryApplication` publishes a Sponsor-safe, read-only snapshot.
The Intraday product route consumes that snapshot. Browser code performs no
Discovery, Pivot, CPR, structure, volume, ranking or candidate calculation.

The `/intraday` page is compact factual triage with stable canonical ordering
only. It presents at most 15 ready members on the main surface, without ranking
meaning, and retains the five unavailable MCX members in a separate factual
section. Member detail routes show retained mandatory evidence and use existing
Intraday evidence renderers where richer explicitly loaded evidence exists.

No successful persisted run is presented as
`NO SUCCESSFUL DISCOVERY RUN AVAILABLE`. Current failure and source freshness
remain separate from the last-successful timestamp.

## Current accounting and methodology boundary

The current governed pre-acquisition split is 98 members, 93 machine-fact
consumable and five prerequisite unavailable. The exact five and their reasons
remain:

- GOLDM, SILVERM and COPPER — `ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE`;
- NATGAS and CRUDE — `PROVIDER_CONTRACT_UNAVAILABLE`.

Candidate admission is not commissioned. A completed factual bundle produces
`NOT_EVALUATED`, not admitted or rejected. ATR, SMA, volume consequence,
path-clearance, extension, direction, scoring and thresholds remain deferred.

## Controlled fixture capacity evidence

The WO-05 deterministic fixture processed all 98 members with 93 successful
bundles and five prerequisite results. Its accounting model represents 93
member-source operations and 372 four-timeframe fact requests. One measured
local run completed in approximately 0.04 seconds and retained 93 bundles, 98
results and one run as 192 JSON files totalling approximately 437 KB. The run
record was approximately 94 KB. The 98-member triage body was approximately
5.9 KB while presenting 15 rows.

These measurements are controlled fixture evidence only. They establish no
production performance threshold and do not claim real Provider latency.

## Operational invocation boundary

Startup loads publications and optionally reconstructs one explicitly configured
run. It does not run Discovery, acquire Provider data, authenticate or retry.
The combined WO-05A candidate now registers the missing product-owned
multi-member factual source and explicit application operation. It reuses one
shared DOMAIN-006 context through a minimized operation lease. WO-05B adds the
narrow loopback-only status/POST transport required to reach that exact service
inside the running KRONOS process. The combined candidate establishes
`REAL_DISCOVERY_RUN_READY = YES`; actual execution remains held for a separately
authorized post-publication restart, context verification and single controlled
operation.

No real Provider acquisition, authentication, restart, WebSocket operation,
notification, trading, Risk, broker mutation or WO-06 activity is part of this
candidate.

## WO-06MCX-R active-contract extension

The earlier 93/5 split above remains truthful historical commissioning evidence.
For a new Refresh, ADR-0017 now permits all five MCX members to cross the runtime
evaluation boundary after DOMAIN-001 resolves a unique active derivative
binding from one current DOMAIN-006 master and DOMAIN-008 expiry eligibility.
Successful members use the bound contract for 1D, 1H, 15M and 5M acquisition
while retaining their analytical subject identities. Resolution or Provider
failures remain isolated member-level factual unavailability.

Bindings are immutable, token-free and linked into the Discovery run source
identities. Restart projection reloads those exact identities; it never treats
the current operational pointer as authority for a historical run. The Browser
may display contract symbol, expiry and binding identity on detail only. GET is
Provider-free and side-effect-free. The existing Probables methodology is
consumed unchanged.
