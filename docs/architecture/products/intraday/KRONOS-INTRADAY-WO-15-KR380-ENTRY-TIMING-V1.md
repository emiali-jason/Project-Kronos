# KRONOS Intraday V1 — WO-15 KR-380 Final Entry Timing

**Status:** APPROVED ARCHITECTURE — PUBLICATION PENDING; SOURCE ENGINEERING NOT AUTHORIZED

**Identity:** `KRONOS-INTRADAY-WO15-ENTRY-TIMING-V1`

**Version:** `1.0.0`

**Policy:** `KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1 / 1.0.0`

**Policy SHA-256:** `d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26`

**Handoff:** `KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1 / 1.0.0`

**Owner:** `KR-380 / DOMAIN-004 / KRONOS-INTRADAY`

**Authority:** `COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY`

**Governing ADR:** [ADR-0025](../../adr/ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md)

## Purpose

Determine completed governed 5M Entry Timing relative to one exact immutable
WO-13 Trade Plan. `TIMING_QUALIFIED` means only that the approved timing
grammar qualified; it is not execution, Sponsor participation or broker action.

## WO-15 A/B/C/D boundaries

- **A — authority and trust:** exact current WO-13 plan, immutable identity,
  direction/setup/instrument/session/policy binding.
- **B — timing grammar:** strict completed-5M Pullback and Range-Breakout
  Direct/Retest/Resumption/failure/reset rules.
- **C — telemetry:** completed-5M extension/ATR and existing contextual facts,
  all research/advisory only.
- **D — lifecycle/handoff:** immutable timing cycles, append-only transitions
  and versioned downstream handoff.

## Inputs and non-authority

The exact current input is `KRONOS-INTRADAY-WO13-TRADE-PLAN-V1`, including
identity/integrity, subject/family, inherited direction/setup, Entry Reference,
boundary, instrument or MCX contract/roll and source/policy lineage. It must be
current, non-superseded, integrity-valid and session/instrument compatible.

WO-15 cannot change Direction, Setup Family, Entry Condition/Reference, Stop,
invalidation, Target, risk/reward distance or Model R:R. It owns no Risk
observation, Sponsor participation, PAPER/LIVE/IGNORE, quantity, position,
order, fill or broker authority. 1H is upstream context, 15M is immutable
construction and 5M is timing.

WO-14 Risk is independent context, never a prerequisite or veto. Timing may be
evaluated alongside `RISK_OBSERVED`, `RISK_ALERT`, `RISK_UNAVAILABLE` or absent
Risk evidence where permitted. No `RISK_APPROVED`, `RISK_PERMISSION` or
`RISK_REJECTED` state is required.

## Evidence and state machine

Only completed governed 5M candles have timing authority. Incomplete candles,
LTP and wick-only crossings do not qualify.

States are exactly `TIMING_NOT_EVALUATED`, `TIMING_WAITING`,
`TIMING_QUALIFIED`, `TIMING_FAILED`, `TIMING_EXPIRED` and
`TIMING_UNAVAILABLE`. There is no score or seventh state.

Precedence is UNAVAILABLE, EXPIRED, FAILED, QUALIFIED, otherwise WAITING.
NOT_EVALUATED is the pre-first-evaluation state. Forming/non-directional
progression is WAITING absent a higher-precedence state.

## Common qualification rule

- LONG: completed Close `>` immutable Entry Reference plus governed LONG-
  aligned 5M progression.
- SHORT: completed Close `<` immutable Entry Reference plus governed SHORT-
  aligned 5M progression.
- Equality: not qualified.

No Entry buffer exists. A progression adapter may map existing exact facts to
ALIGNED, NON_DIRECTIONAL/FORMING, CONTRADICTORY or UNAVAILABLE only; it cannot
create a new price-analysis algorithm.

## Pullback continuation

One strict completed close plus aligned progression qualifies in either
direction. No second close, retest, volume, RSI or Railway confirmation is
required. Explicit authoritative opposing governed 5M structural progression
may fail the current cycle; merely remaining behind Entry while forming does
not. Entry Reference is not a micro-Stop.

## Range breakout

Both `DIRECT_ACCEPTANCE` and `RETEST_RESUMPTION` are valid and unranked.

| Path | LONG | SHORT |
| --- | --- | --- |
| Direct | Close above original Range High plus aligned progression | Close below original Range Low plus aligned progression |
| Retest | `Low <= Entry` and `Close >= Entry` | `High >= Entry` and `Close <= Entry` |
| Resumption | subsequent Close above Retest High plus aligned progression | subsequent Close below Retest Low plus aligned progression |
| Failure after active interaction | Close below original Range High | Close above original Range Low |

Retest tolerance is none. Wick-through/reclaim can establish a retest but not
qualification. Equality is not inside the range. Retest evidence cannot rewrite
WO-13 geometry. Timing failure is not thesis invalidation.

## Cycle creation, reset and statefulness

Each opportunity owns immutable `timing_cycle_id`; only one active non-terminal
cycle exists per WO-13 plan. Creation and first evaluation occur atomically at
the first valid completed 5M boundary strictly after plan effectiveness—not
first Entry interaction. Separate timestamps preserve plan availability,
creation, evaluation, interaction, qualification, failure and expiry.

Multiple cycles against one plan/session are allowed only after terminal
failure and deterministic reset. The plan and session/identity/direction/setup
remain current, the later boundary is strict, the prior failure no longer holds
and progression is aligned/forming and not contradictory.

- Pullback reset: later aligned/forming and no longer opposing.
- Breakout LONG reset: later Close `>=` Range High and non-opposing.
- Breakout SHORT reset: later Close `<=` Range Low and non-opposing.

The reset candle may immediately qualify. Failed cycles are immutable. There is
no cooldown, delay or maximum attempt count.

Qualification remains historical truth. A later explicit failure or expiry is
a new immutable transition; no stateless downgrade to WAITING is permitted.
Expiry causes are session end, WO-13/upstream/contract supersession and
applicable DOMAIN-008 invalid/closed session. No arbitrary bar/time/TTL expiry
or overnight carry exists.

## Extension and research telemetry

For completed 5M Close `C` and Entry Reference `E`:

- LONG directional extension = `C - E`;
- SHORT directional extension = `E - C`;
- absolute extension = `abs(C - E)`;
- normalized extension = `directional_extension / ATR14_5M` when valid.

ATR is completed-5M Wilder/RMA ATR-14 with exact same Instrument, contract/roll,
lineage and boundary. Invalid/non-positive/insufficient/mismatched ATR makes
normalized extension unavailable. Extension is advisory research only,
severity is `UNCLASSIFIED`, and no threshold or veto is commissioned.

Volume, relative volume, RSI-14, SMA20/50/200/Railway, CPR, PDH/PDL, Pivots,
session phase, timing latency, retest/path and outcome references are context or
research only. Storage creates no authority.

## Observation and handoff architecture

Every completed-boundary evaluation may append an immutable observation.
Transitions bind cycle, prior/new state, cause, exact 5M evidence/boundary,
plan, Instrument/session/policy, timestamp, provenance and integrity. Repeated
WAITING observations need no repeated downstream handoff.

The separately versioned
`KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1 / 1.0.0` is created for QUALIFIED,
FAILED, EXPIRED and UNAVAILABLE. It contains at minimum:

- handoff/contract identity and version;
- WO-13 plan identity and integrity;
- timing cycle, observation and transition identities;
- prior/current state and cause;
- direction, setup, immutable Entry Reference and qualification path;
- qualifying/failing 5M evidence identity and boundary;
- first evaluation/interaction/qualification/failure/expiry times as available;
- extension and approved research references;
- session/calendar identity/version;
- canonical Instrument, active contract and roll lineage where applicable;
- policy identity/version;
- optional WO-14 reference at handoff;
- creation time, provenance, integrity and supersession lineage.

A later FAILED/EXPIRED handoff references rather than mutates an earlier
QUALIFIED handoff. Consumers use the latest current non-superseded handoff.
The Risk reference is audit/context only and grants no freshness, permission or
approval. `TIMING_EVIDENCE_AUTHORITY = YES`; Sponsor Decision,
PAPER/LIVE/IGNORE, position and broker authority are none.

Factual attention-event identities may include QUALIFIED, FAILED/LOST,
EXPIRED and Entry-reference retest. They are not delivery mechanisms;
Telegram, email, desktop, sound and push remain downstream. An extension alert
is not commissioned. Sponsor manual entry cannot rewrite Timing to QUALIFIED;
any future exception/journal record requires separate governance.

## Product-family authority

- Equity: stock-local completed 5M.
- Index: underlying NIFTY/BANKNIFTY completed 5M; option premium cannot
  substitute and no strike/expiry/option vehicle is selected.
- MCX: exact active governed futures-contract completed 5M; COMEX/NYMEX/USDINR
  cannot trigger or substitute.
- NATGAS: methodology structurally supportable, operational evaluation held and
  unavailable until upstream commissioning permits evidence.

## Trust failures

Foreign/superseded plan, direction/setup/instrument/contract/roll mismatch,
stale or incomplete 5M evidence, boundary/session/calendar/policy mismatch,
corrupt evidence and integrity failure produce `TIMING_UNAVAILABLE` with exact
reason, never ordinary `TIMING_FAILED`.

## Deferred and prohibited policy

Extension/chase threshold, severity bands, ATR veto, volume threshold/
consequence, RSI/Railway/SMA consequence, level-proximity consequence,
bar/time expiry, extension alert, option-premium execution timing and new
indicator gates remain unresolved. No values exist.

Prohibited: WO-13 mutation; LTP/wick triggers; buffers; mandatory two-close,
retest, volume, RSI or Railway gates; ATR/R:R veto; new indicators/AI score;
reference-market substitution; Risk or manual Sponsor activity rewriting
Timing; and broker action.

## Reuse and engineering sequence

Reuse immutable identity, append-only observation, state transition,
supersession, current-pointer, handoff and Sponsor/broker-separation principles.
Use adapters for Intraday 5M, DOMAIN-008, Instrument/contract and later
persistence/runtime patterns. Never copy Swing timeframe/timing/Risk/Daily/
threshold/lifecycle policy.

After separate publication authority, engineering order is WO-15A contracts,
WO-15B grammar, WO-15C telemetry, WO-15D persistence/application/handoff,
WO-15E runtime/Browser/control, then separately authorized publication and
runtime acceptance. This document implements none of those stages.

## Canonical policy

The deterministic payload is
[KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json](KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json),
SHA-256 `d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26`.
