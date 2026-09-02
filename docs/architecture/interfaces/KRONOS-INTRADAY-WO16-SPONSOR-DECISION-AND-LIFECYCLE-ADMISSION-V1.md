# KRONOS Intraday WO-16 Sponsor Decision and Lifecycle Admission V1

**Status:** APPROVED ARCHITECTURE CONTRACT — PUBLICATION PENDING

**Version:** `1.0.0`

**Owner:** `KRONOS-INTRADAY`

**Authority:** `EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY`

**Governing ADR:** [ADR-0026](../adr/ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-LIFECYCLE-ADMISSION.md)

## Purpose

Define the exact immutable contract boundary between current Intraday Trade
Construction/Risk/Timing evidence and one explicit Sponsor decision. This
contract records intent and admission disposition only.

## Inputs

The request must bind:

| Source | Required binding |
| --- | --- |
| WO-13 | Trade Plan identity/integrity, policy identity/version/checksum, canonical subject, market family, Instrument, direction, setup and complete geometry |
| WO-14 | Risk Observation identity/integrity and exact WO-13 plan binding; observation state may be `RISK_OBSERVED`, `RISK_ALERT` or `RISK_UNAVAILABLE` |
| WO-15 | Current non-superseded Timing Handoff identity/integrity in `TIMING_QUALIFIED`, cycle/observation/transition identities, completed-5M evidence boundary, predecessor/supersession and policy lineage |
| WO-15 session | Session-binding identity/integrity, exchange, trading date, session identity, calendar identity/version and open/close boundary |
| DOMAIN-008 | Exact available `OPEN` fact for the same exchange/date/session/calendar; `session_end=false` |
| Canonical lineage | Subject, market family, Instrument and, for MCX, exact actual contract and roll lineage |

An immutable upstream identity/integrity pair remains authoritative. Projected
display fields are provenance conveniences and cannot overwrite the source.

## Sponsor Decision Snapshot

Identity: `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SNAPSHOT-V1 / 1.0.0`.

The snapshot must contain:

- snapshot identity and integrity;
- WO-13 Trade Plan identity/integrity and policy binding;
- WO-14 Risk Observation identity/integrity;
- WO-15 Timing Handoff identity/integrity and timing state;
- WO-15 session-binding identity/integrity;
- canonical subject, market family, Instrument, direction and setup;
- actual MCX contract and roll lineage where applicable;
- decision-eligible DOMAIN-008 observation timestamp and session identity;
- snapshot timestamp and provenance; and
- the WO-16 policy identity/version/checksum.

The snapshot has no geometry, Risk, timing, position, execution or broker
mutation authority.

## Sponsor Decision Record

Identity: `KRONOS-INTRADAY-WO16-SPONSOR-DECISION-V1 / 1.0.0`.

Required fields are:

- decision identity and integrity;
- request identity and integrity;
- snapshot identity and integrity;
- exact WO-15 Timing Handoff identity;
- choice: `PAPER`, `LIVE` or `IGNORE`;
- source: `LOCAL_SPONSOR_BROWSER_ACTION`;
- timezone-aware decision timestamp;
- predecessor decision identity when this is a governed successor;
- supersession-lineage identity when applicable;
- policy identity/version/checksum; and
- provenance.

There is no person-identity field, free-text note or Swing reason field in V1.

## Lifecycle Admission Record

Identity: `KRONOS-INTRADAY-WO16-LIFECYCLE-ADMISSION-V1 / 1.0.0`.

It binds the decision identity/integrity and records exactly one disposition:

| Choice | Disposition | Position consequence |
| --- | --- | --- |
| PAPER | `PENDING_POSITION_EVIDENCE` | NONE |
| LIVE | `PENDING_POSITION_EVIDENCE` | NONE |
| IGNORE | `NOT_APPLICABLE_IGNORE` | NONE |

The record also contains admission identity/integrity, recorded timestamp,
bounded factual reason, policy binding and provenance. It has factual outcome
authority only and cannot activate or manufacture a position.

## Invalid Operation

Identity: `KRONOS-INTRADAY-WO16-INVALID-OPERATION-V1 / 1.0.0`.

Malformed, stale, unavailable, mismatched, closed-session, duplicate-conflict
or integrity-invalid requests create no decision or admission. A sanitized
invalid-operation record may be retained separately from the prior current
decision. Raw credentials, Provider tokens, traceback text and local secret
paths are prohibited.

## Current projection

Identity: `KRONOS-INTRADAY-CURRENT-WO16-DECISION-V1 / 1.0.0`.

There is at most one current decision per canonical subject. Currentness
requires the exact current upstream lineage and open bound session. The alias
references immutable records and is not authority to mutate them. Latest
failure is a separate alias.

## Replay, conflict and supersession

- Same request identity and same bytes: return the retained record.
- Same request identity or Timing Handoff with different bytes: fail closed.
- Same exact Timing Handoff: one final decision; no mode revision.
- New current plan/handoff/session/MCX roll: a new decision may be created with
  explicit predecessor and supersession lineage.
- IGNORE affects only its exact lineage.

## Truth model

For PAPER and LIVE the following remain `UNAVAILABLE`:

- actual fill price;
- actual fill timestamp;
- quantity/lots;
- fees/slippage;
- monetary P&L;
- realised R;
- broker order identity;
- broker execution state.

WO-13 model geometry may be displayed as objective context but cannot be
relabeled actual. WO-14 cannot size, permit or veto the decision. WO-15 cannot
be rerun or rewritten.

## Persistence and restoration

The contract family is stored in a new Intraday-owned evidence namespace with
immutable snapshots, decisions, admissions, operations, invalid attempts and
supersessions; atomic current-per-subject and latest-failure aliases are
separate. Exact replay is idempotent and conflicting bytes are rejected.

Restoration validates all referenced identities and integrities without
recalculation, Provider calls, Sponsor action, admission replay or position
creation. Corrupt or foreign state fails closed while prior valid history
remains immutable.

## Browser/control contract

The Sponsor page must distinguish:

- objective Trade Plan;
- advisory Risk Observation;
- completed-5M Timing Handoff;
- Sponsor decision;
- admission disposition;
- actual-position facts;
- current state, immutable history and latest failure.

The control uses exact bounded JSON, JSON content type, a required non-empty
body, required/extra-field validation, query rejection, exact Host and
same-origin validation, Sponsor-work admission, nonblocking concurrency,
sanitized failures, exact lineage, idempotent replay and conflict rejection.
GET is side-effect free.

## Negative authority

This interface cannot:

- recalculate or alter WO-13 geometry;
- turn WO-14 into permission, veto or quantity;
- infer or rerun WO-15 timing;
- call Provider autonomously;
- create a Sponsor Actual Position;
- infer PAPER or LIVE execution;
- place, modify or cancel a broker order;
- create fill, P&L, realised-R, monitoring, closure, notification or Journal
  truth; or
- read or mutate Swing product state.

## Future consumers

Later separately governed Intraday position, lifecycle monitoring, closure,
notification and Journal/Analytics contracts may reference these identities.
They cannot reinterpret or backfill WO-16 V1 records.
