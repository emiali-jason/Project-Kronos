# KRONOS Intraday V1 — WO-05B Bounded Operational Control

**Status:** WO-05B engineering review candidate

**Control identity:** `KRONOS-INTRADAY-DISCOVERY-OPERATIONAL-CONTROL-V0 / 0.1.0`

**Service:** `KRONOS-INTRADAY-DISCOVERY-OPERATION-SERVICE-V0 / 0.1.0`

## Defect and scope

WO-05B freezes the defect as
`DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE`. WO-05A composes the
governed operation inside the KRONOS process, but no external bounded surface
could invoke it without another process, another Provider context or intrusive
process attachment.

WO-05B adds only:

- `GET /control/intraday-discovery/status`;
- `POST /control/intraday-discovery`.

This is an Intraday commissioning control, not a generic Browser action
framework or Sponsor trading action.

## Transport and security

The existing Browser remains bound to `127.0.0.1`. Status requires the exact
loopback Host and accepts no query. POST requires exact Host and same Origin,
`application/json`, a body no larger than 512 bytes, no query, and exactly:

```json
{
  "request_identity": "CONTROLLED-WO-05B-REAL-PROOF-001",
  "observation_boundary": "2026-08-24T10:17:00+05:30"
}
```

The request identity is bounded to 1–96 uppercase identity characters. Unknown
fields, naive/invalid timestamps, foreign Host/Origin, invalid content type and
oversized bodies fail closed. GET cannot run Discovery. No GET or normal
`/intraday` render performs Provider work.

## Composition

`IntradayDiscoveryOperationalControl` receives the exact
`IntradayDiscoveryOperationService` and `IntradayDiscoveryApplication` already
created by `create_intraday_runtime`. `tools/kronos_browser.py` composes that
control over the same `SharedAuthenticatedProviderRuntime` instance already
used by Swing and the Platform Provider operation. It creates no Provider
runtime, client, authentication manager or credential context.

The POST preserves WO-05A's deterministic operation identity, one-active-run
rule, duplicate idempotency, `OPERATION_CONFLICT`, minimized
`INSTRUMENTS + HISTORICAL_DATA` lease, no-retry rule, 93/5 boundary and modeled
maximum of 372 historical requests. Five prerequisite-unavailable MCX members
remain outside acquisition.

## Response and status

Responses contain only bounded identities, state, actual context lifecycle,
stage, observation boundary, counts, run identity, persistence/snapshot flags,
failure code and timestamps. They contain no OHLCV, Provider record, instrument
token, credential, SDK object, traceback or raw exception.

Status exposes service/operation availability, actual context state, active
identity, last bounded result, and last-successful run/timestamp. A later failed
operation does not erase the last successful analysis.

## Shared-file declaration

`SHARED-FILE / PLATFORM CHANGE REQUIRED`

- `src/kronos/browser/server.py`: bounded GET/POST transport dispatch only;
- `tools/kronos_browser.py`: inject the Intraday-owned control into the existing
  running server object graph.

An Intraday adapter alone cannot make an object inside the existing process
externally reachable. No shared renderer, generic route registry, Provider,
Swing state or launcher-hardening implementation is changed.

## Readiness and authority

`REAL_DISCOVERY_RUN_READY = YES` for this combined engineering candidate. No
real Provider operation, restart or authentication is performed by WO-05B. The
controlled operation remains separately authorized after review/publication and
restart; authenticate once only if the actual shared context is inactive.

Current universe V1/1.0.0 remains immutable at 98. The approved future
publication-driven variable-cardinality successor is recorded only and is not
implemented. Candidate methodology, trading, Risk, Entry Timing, execution
eligibility, notification, monitoring and broker authority remain absent.

## WO-05C publication-validity closure

A governed Discovery operation fails closed with `PUBLICATION_STALE` when its
observation boundary predates the effective `valid_from` of the bound universe
publication. Historical commissioning before universe activation is not
permitted: no override may backdate, mutate or bypass publication validity, and
Provider availability cannot supersede that authority.

The next controlled real proof must use the first completed governed trading
session boundary that is both at or after the universe `valid_from` and valid
under DOMAIN-008. No calendar date is hardcoded; DOMAIN-008 remains authoritative
for session existence, special or shortened sessions, and the completed
boundary. Publication-validity failure remains at `UNIVERSE_RESOLUTION`, causes
no Provider acquisition or persistence, and is projected without raw exception
text, traceback, credentials or Provider tokens.
