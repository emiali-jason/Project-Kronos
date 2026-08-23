# KRONOS Intraday V1 — WO-05A Operational Invocation

**Status:** WO-05A engineering review candidate
**Service identity:** `KRONOS-INTRADAY-DISCOVERY-OPERATION-SERVICE-V0 / 0.1.0`

## Bounded operational composition

WO-05A composes one explicit Intraday application operation over the existing
`SharedAuthenticatedProviderRuntime`. It verifies actual runtime lifecycle,
requests one operation-scoped `INSTRUMENTS + HISTORICAL_DATA` lease, constructs
the Provider-backed factual source, invokes the existing WO-05 Discovery
service, verifies persistence and updates the Intraday application snapshot.

Startup, Browser GET and status inspection perform no Provider acquisition.
WO-05A itself defines no Browser POST/control endpoint. WO-05B supplies a later
bounded loopback transport over this exact service. Authentication remains
explicit and DOMAIN-006-owned. The operation creates no Provider context and
always releases its lease.

## Factual acquisition

The source resolves exact reconciliation-owned Provider symbols against one
normalized NSE instrument record set. It requests exactly 1D, 1H, 15M and 5M
history for each machine-fact-consumable member. The current model therefore
uses one normalized instrument-record request and 372 historical requests for
93 members. The five prerequisite-unavailable MCX members never reach Provider
lookup or history acquisition.

One operation binds a deterministic composite of all eligible subject-scoped
DOMAIN-008 session identities and windows plus one timezone-aware observation
boundary. Current/incomplete intraday candles are excluded from structural
evidence. Missing completed evidence becomes a bounded member factual failure;
remaining members continue.

## Concurrency, failure and projection

An operation request identity deterministically binds caller request identity
and observation boundary. One active operation is permitted. A same-identity or
different-identity concurrent request returns `OPERATION_CONFLICT` without new
Provider workload. A duplicate completed request returns its retained sanitized
result and does not execute again. There is no automatic retry.

Operational results contain only bounded state, context lifecycle, stage,
counts, run identity, persistence/snapshot status and failure code. Provider
records, tokens, credentials and raw exceptions do not enter the result or
Browser. A later global operation failure preserves the last successful run.

## Preserved authority boundaries

Candidate admission remains uncommissioned. Successful factual paths remain
`NOT_EVALUATED`; no candidate admission/rejection, trading, Risk, Entry Timing,
notification, monitoring, execution eligibility or broker authority is added.

The Chief Architect successor-universe decision is recorded as a separate
bounded follow-up: current V1/1.0.0 remains immutable at 98 members; a future
publication-driven non-empty variable-cardinality successor may be implemented
separately. WO-05A makes no universe-contract or membership change.

## Controlled real proof boundary

No real Provider-backed operation, authentication or restart is part of this
candidate. After review/publication, one separately authorized proof may load
the candidate, authenticate only if the shared context is inactive, execute one
explicit operation, reload its deterministic run and verify `/intraday`.

## WO-05B transport binding

The Intraday-owned WO-05B control accepts one validated request label and one
timezone-aware observation boundary, creates this service's existing
deterministic request, and returns only the bounded result document. It neither
rebuilds the runtime nor changes the WO-05A identity, concurrency, workload or
failure model.
