# KRONOS Intraday V1 — WO-06 Part 3 V0 Probables Methodology

**Status:** WO-06 Part-3 production commissioning candidate

**Owner:** KRONOS Intraday

**Authority:** Sponsor/EA WO-06 Part 3

**Outcome evidence:** `ABSENT_PENDING`

## Purpose and meaning

Part 3 freezes and commissions the first production Intraday Probables
methodology from the approved WO-06S Variant-G real-evidence conclusion. A
Probable means only that a governed Native member satisfies the V0 conditions
for deeper KRONOS review. It does not mean high probability, expected profit,
trade quality, Analytical Promotion, Entry readiness, Risk permission, a
Sponsor position or broker authority.

| Contract | Identity | Version |
|---|---|---|
| Methodology | `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V1` | `1.0.0` |
| Member result | `KRONOS-INTRADAY-PROBABLE-V1` | `1.0.0` |
| Run | `KRONOS-INTRADAY-PROBABLES-RUN-V1` | `1.0.0` |
| Population diagnostics | `KRONOS-INTRADAY-PROBABLES-POPULATION-DIAGNOSTICS-V1` | `1.0.0` |

## Approved evidence basis

The freeze basis is the immutable WO-06S evidence for 17–21 August 2026: 465
factually resolvable subject-session observations, 93/93 resolvable subjects,
25 MCX prerequisite-unavailable subject-session observations, zero Provider
failures, 47,945 completed candle payloads, 4,185 semantic facts and no
look-ahead.

Production reproduction of Variant G is exact:

| Session | Probables |
|---|---:|
| 17-Aug-2026 | 14 |
| 18-Aug-2026 | 7 |
| 19-Aug-2026 | 6 |
| 20-Aug-2026 | 17 |
| 21-Aug-2026 | 18 |

Aggregate direction is 17 Long and 45 Short. This establishes population
health only. It establishes no outcome, profitability or predictive claim.

## Frozen stage sequence

1. Factual eligibility.
2. Narrow CPR admission support.
3. 1H directional regime.
4. 15M directional structure.
5. Explicit 1H/15M direction coherence.
6. Participation support.
7. Directional Probable output.

No additional admission stage, score, rank, Top-N, minimum, maximum, quota,
fallback admission or tie-break exists.

## Evidence roles

`NARROW_CPR_KGS_V0 = TRUE` is `ADMISSION_SUPPORT_REQUIRED`. FALSE is
`NOT_ADMITTED`; unavailable is `UNAVAILABLE`. Narrow CPR supplies no direction,
rank, volatility claim or performance claim.

The completed 1H regime, completed 15M structure and exact 1H/15M coherence
facts are mandatory. Long requires all three to be Long; Short requires all
three to be Short. Explicit opposition is `DIRECTION_CONFLICTING` and is not
admitted. Non-directional states are not admitted and are never inverted into
Short.

Participation is `SUPPORTING_NON_BLOCKING`. `ABOVE`, `BELOW`, `AT` and
`UNAVAILABLE` are retained in lineage but do not change admission. No RVOL
threshold or volume veto exists.

Completed 1D context, completed 5M progression, PDH/PDL relationships, CPR
location and Classic Pivot P/R1–R4/S1–S4 relationships are informational. They
do not admit, veto, score or rank.

## States, reasons and unavailability

Every governed member resolves to `LONG_PROBABLE`, `SHORT_PROBABLE`,
`NOT_ADMITTED` or `UNAVAILABLE`. Bounded reasons distinguish Narrow CPR FALSE,
1H/15M non-directional states, conflict and coherence failure from unavailable
prerequisites, Provider facts, Narrow CPR, 1H, 15M and semantic facts.

`UNAVAILABLE` is not `NOT_ADMITTED`, no-setup, weakness or a negative outcome.
The five governed MCX members remain represented and unavailable while their
prerequisites are unavailable. NSE analysis continues when one member fails.
Only a run-level prerequisite or integrity failure fails the whole run.

## Boundaries, refresh and immutability

Only governed completed candles may contribute. Every fact must satisfy
`available_at <= member observation boundary <= run analysis boundary`.
Subject-aware market/session identities and boundaries remain exact within one
multi-member run.

Every authorized future Refresh Analysis creates a new immutable run. Same
methodology, facts and boundary reproduce the same result and identity. A new
boundary or changed evidence creates a new identity. Previous-session Narrow
CPR and levels remain session-stable; 1H, 15M, coherence, participation, 5M and
current-level relationships may evolve at completed boundaries.

Browser GET/refresh is presentation only and creates no analysis run. The
current Part-3 publication performs no real current-market refresh. WO-06V owns
controlled multi-refresh/adversarial qualification and WO-06E2E owns real
current-market commissioning.

A later analytical refresh cannot rewrite an existing PAPER/LIVE lifecycle,
Trade Construction, entry thesis, Stop, Target, Risk, Entry Timing, Sponsor
decision or position history.

## Persistence, lineage and projection

Methodology, member results, population diagnostics and runs use canonical
serialization, deterministic identities, atomic immutable writes, idempotent
identical retention, conflicting-duplicate rejection, integrity validation and
explicit-identity reload. There is no latest-file-wins authority. Earlier runs
remain independently reconstructable.

Every admitted member binds canonical subject, methodology/version, exact
source factual run and member identity, observation boundary, Narrow CPR, 1H,
15M, coherence, participation, informational fact identities and result/run
integrity. Provider tokens, credentials and raw SDK objects are prohibited.

The application preserves the last successful run and timestamp when a later
refresh fails. Current failure remains separately inspectable. Browser is a
Provider-free derivative projection showing Long, Short, Not Admitted,
Unavailable and last-successful state without becoming analytical authority.

## Population diagnostics

Diagnostics report starting population, evaluable and unavailable members,
Long, Short, total Probables, Not Admitted, conflicts, retention, attrition,
stage survivors and buckets `0`, `1–5`, `6–10`, `11–15`, `16–19`, `20+`.
Buckets never relax or truncate the methodology.

## Deferred authority and remaining closure

Barrier hierarchy/path, extension, ATR, SMA, Entry Timing, Trade Construction,
Risk and outcome optimization remain deferred. Part 3 introduces no 3V Review,
Analytical Promotion, lifecycle, journal, report, notification, Sponsor
PAPER/LIVE/IGNORE or broker execution authority.

Part-3 success means `PROBABLES METHODOLOGY COMMISSIONED`; WO-06 remains open.
The remaining gates are WO-06V multi-refresh/adversarial qualification, WO-06L
restart/replay/reconstruction closure and WO-06E2E real current-market
commissioning.
