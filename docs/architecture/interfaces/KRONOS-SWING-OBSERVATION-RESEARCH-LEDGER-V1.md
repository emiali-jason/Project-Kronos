# KRONOS Swing Observation Research Ledger V1

**Status:** Approved implementation contract
**Version:** 1
**Owner:** Swing
**Authority:** Research evidence only

## Purpose

This contract governs the prospective JOURNAL-OBS-01 population. Its primary
unit is one immutable Sponsor Observation Decision produced under
`KRONOS-SWING-SPONSOR-OBSERVATION-DECISION-V1`. The ledger links that decision
to later factual records without changing the source decision, Step-31, Risk,
KR-380, KR-390, Sponsor Position, or Step-33 authority.

## Required population

Every prospective `LIVE`, `PAPER`, and `IGNORE` observation decision is
retained. Activated and blocked decisions remain in the same population.
`IGNORE` is first-class and requires neither a position nor an outcome.
Blocked `LIVE`/`PAPER` observations likewise require neither.

The base record binds exactly to:

- decision snapshot identity and SHA-256;
- observation decision identity and SHA-256;
- activation disposition identity and SHA-256;
- Native run, canonical instrument, assessment SHA-256, choice, disposition,
  and decision timestamp.

Decision-time Step-31 severity/warnings, Risk state, KR-370 state, geometry,
and optional MCX supporting-context evidence remain immutable in the source
snapshot and are resolved by exact identity/digest. Run supersession never
rewrites an existing record.

## Append-only relationships

Later evidence is recorded only as a separate, immutable link:

- KR-380 V2 Entry Outcome;
- KR-390 Objective Model;
- closed objective-model outcome;
- Sponsor Position;
- Sponsor Position outcome.

Each link requires exact run, instrument, assessment, Trade Plan identity and
digest, source contract/version, source record identity and digest, state, and
timestamp. Sponsor-position links additionally require the exact position
identity from the activation disposition. Duplicate identical links are
idempotent; changed content for an existing identity fails closed. Missing,
late, or unavailable outcomes remain explicitly unavailable and do not remove
the primary observation.

## Query and projection

Read-only queries may filter by Sponsor choice, activation disposition,
Step-31 severity, KR-370 `BUY_NOW`/`SELL_NOW`, Risk state, objective-outcome
availability, Sponsor-position-outcome availability, and combinations.
Ordering is decision timestamp descending with record identity as the stable
tie-break.

The Browser may present a compact Observation Research section and structured
JSON/CSV projections. It must distinguish decision-time evidence, objective
model, and Sponsor Position. It must not derive or display win rate, P&L,
expectancy, selection efficacy, or any other performance metric from this V1
ledger.

## Product and authority boundaries

The ledger is:

- prospective only; no historical backfill or migration;
- not an input to Native Discovery, KR-370, Step-31, Risk, KR-380, KR-390,
  Sponsor Decision, Sponsor Position, UX-10, K5, Settings, Dashboard, or MCX
  Context;
- not a selection or methodology feedback loop;
- not position, execution, order, fill, or broker authority;
- separate from the existing Step-33 completed-trade/ignored-opportunity
  journal and its historical contracts.

MCX supporting-context linkage is retained only when it is present in the
decision-time snapshot. An NSE equity whose ticker is `MCX` must not acquire
commodity supporting context by symbol matching.

## Persistence and recovery

Records and links use append-only local files with restrictive permissions,
integrity SHA-256, deterministic replay, restart restoration, duplicate-link
prevention, and fail-closed rejection of corrupt or mismatched lineage. The
store contains no credentials, provider tokens, raw clients, broker payloads,
or autonomous-trading capability.
