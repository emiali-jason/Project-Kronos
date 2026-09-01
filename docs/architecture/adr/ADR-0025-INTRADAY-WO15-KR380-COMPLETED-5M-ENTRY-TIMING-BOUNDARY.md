# ADR-0025 — Intraday WO-15 / KR-380 Completed-5M Entry Timing Boundary

## Metadata

- **ADR Number:** ADR-0025
- **Decision Identity:** `KRONOS-INTRADAY-WO15-KR380-ENTRY-TIMING-BOUNDARY-V1`
- **Title:** Intraday WO-15 / KR-380 Completed-5M Entry Timing Boundary
- **Status:** APPROVED — PUBLICATION PENDING
- **Date:** 2026-09-01
- **Decision Owner:** Chief Architect / KR-380 / DOMAIN-004 / KRONOS Intraday
- **Proposed By:** Sponsor / Intraday Engineering Architect
- **Approved By:** Chief Architect / Sponsor
- **Decision Scope:** Platform / Intraday Product / Interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for bounded governance publication
- **Engineering Status:** Governance only; WO-15 production source engineering not authorized
- **Runtime / Provider / Sponsor / Broker Authority:** NONE

## Context

[ADR-0021](ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
assigns future extension/chase consequence to WO-15. [ADR-0022](ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
freezes immutable Intraday 15M Trade Construction geometry and reserves 5M for
WO-15. [ADR-0023](ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
makes Intraday WO-14 advisory Risk observation, not permission or veto.

The common KR-380 records in [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
preserve platform and Swing Entry Outcome history. Intraday now requires a
product-specific, completed-candle timing boundary that does not import Swing
timeframe grammar, Risk-permission semantics, numerical thresholds or
lifecycle assumptions.

## Decision

### 1. Authority and four-part architecture

WO-15 authority is exactly
`COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY`. It answers:

> What is completed governed 5M market behaviour doing now relative to the
> immutable WO-13 Trade Plan?

The frozen responsibilities are:

- **WO-15A:** authority, exact WO-13 handoff and trust boundary;
- **WO-15B:** exact completed-5M timing grammar;
- **WO-15C:** extension and research telemetry; and
- **WO-15D:** timing state machine, persistence and downstream handoff boundary.

This ADR authorizes no implementation. A later engineering sequence must be
WO-15A contracts/foundation, WO-15B grammar, WO-15C telemetry, WO-15D
persistence/application/handoff, WO-15E runtime/Browser/control, then separate
publication and runtime acceptance.

### 2. Non-authority and timeframe ownership

WO-15 does not own Direction, Setup Family, Entry Reference, Entry Condition,
Stop, Thesis Invalidation, Native or Canonical Target, Risk or reward distance,
Model R:R, Risk Observation, Sponsor participation, PAPER, LIVE, IGNORE,
quantity, position, order, fill or broker execution.

- 1H is upstream regime/context.
- 15M is setup, promotion and immutable WO-13 Trade Construction.
- 5M is final Entry Timing.

WO-15 never rewrites 15M geometry.

### 3. Exact WO-13 input and currentness

WO-15 consumes only exact current `KRONOS-INTRADAY-WO13-TRADE-PLAN-V1`
identity and integrity, subject, market family, direction, setup family, Entry
Reference, analysis boundary, instrument or active-contract/roll lineage,
source lineage and policy lineage.

Before evaluation the plan must be current, non-superseded, integrity-valid,
session-compatible and instrument/contract-compatible. A stale or incompatible
plan cannot create a current timing cycle.

### 4. WO-14 is independent and non-veto

WO-14 Risk Observation is contextual/advisory evidence and is not a WO-15
prerequisite. Timing may be evaluated with `RISK_OBSERVED`, `RISK_ALERT`,
`RISK_UNAVAILABLE`, or no Risk observation where the architecture permits.

`TIMING_QUALIFIED` may coexist with any of those states. WO-15 does not require
`RISK_APPROVED`, `RISK_PERMISSION` or `RISK_REJECTED`; Risk state never rewrites
Timing state. This is the Intraday product-specific application of ADR-0023.
ADR-0011/ADR-0013 Swing Risk-permission and Entry Outcome semantics remain
unchanged.

### 5. Canonical evidence and state family

Completed governed 5M candles are the only timing authority. Current incomplete
candles have none; LTP is display/context only; wick crossing has no independent
qualification authority.

The timing state family is exactly:

1. `TIMING_NOT_EVALUATED`;
2. `TIMING_WAITING`;
3. `TIMING_QUALIFIED`;
4. `TIMING_FAILED`;
5. `TIMING_EXPIRED`;
6. `TIMING_UNAVAILABLE`.

There is no score, confidence percentage or seventh state. Precedence after a
valid evaluation is: invalid/missing trust evidence → `TIMING_UNAVAILABLE`;
expiry/supersession/session end → `TIMING_EXPIRED`; explicit failure →
`TIMING_FAILED`; satisfied grammar → `TIMING_QUALIFIED`; otherwise →
`TIMING_WAITING`. `TIMING_NOT_EVALUATED` exists before first evaluation.

### 6. Common close and progression rule

LONG requires completed 5M Close strictly above immutable Entry Reference.
SHORT requires completed 5M Close strictly below it. Equality does not qualify.
There is no tick, percentage, ATR or arbitrary Entry buffer.

A close alone is insufficient: existing governed 5M progression must align
with inherited direction. A bounded adapter may expose only source-supported
`ALIGNED`, `NON_DIRECTIONAL / FORMING`, `CONTRADICTORY` or `UNAVAILABLE`.
It cannot invent a second price-analysis algorithm. Forming/non-directional
evidence remains `TIMING_WAITING` absent a higher-precedence state.

### 7. Pullback continuation

For LONG, one completed Close above Entry plus LONG-aligned progression
qualifies. SHORT is symmetric below Entry with SHORT-aligned progression. One
qualifying close is sufficient. Retest, volume, RSI and Railway/SMA confirmation
are not mandatory.

Explicit authoritative opposing governed 5M structural progression may fail
the current cycle. Remaining behind Entry while the setup forms is not itself
failure. Entry Reference is not a micro-Stop; WO-13 Stop and thesis
invalidation remain separate immutable facts.

### 8. Range-breakout Direct and Retest/Resumption paths

The exact paths are `DIRECT_ACCEPTANCE` and `RETEST_RESUMPTION`; neither is
ranked and retest is not mandatory.

- Direct LONG: completed Close above original Range High/Entry plus aligned
  LONG progression.
- Direct SHORT: completed Close below original Range Low/Entry plus aligned
  SHORT progression.
- First valid completed candle already beyond Entry uses ordinary Direct
  grammar; Entry is not moved.
- LONG retest: `Low <= Entry` and `Close >= Entry`.
- SHORT retest: `High >= Entry` and `Close <= Entry`.
- LONG resumption: first subsequent completed Close above Retest Candle High
  plus aligned LONG progression.
- SHORT resumption: first subsequent completed Close below Retest Candle Low
  plus aligned SHORT progression.

Retest tolerance is none. Wick-through and reclaim may establish the retest but
not final qualification. Retest High/Low is timing-local and cannot alter Entry,
Stop, Target, R:R or invalidation.

After active breakout timing interaction, LONG Close below original Range High
or SHORT Close above original Range Low produces `TIMING_FAILED`. Equality is
not inside the range. A 5M timing failure is not a 15M thesis invalidation.

### 9. Timing-cycle creation and immutable lifecycle

Every timing opportunity has immutable `timing_cycle_id`. Exactly one active
non-terminal cycle may exist per WO-13 plan. The first cycle is created at the
first valid governed 5M evaluation boundary strictly after the WO-13 effective
boundary, once plan, identity, direction, setup, session and policy trust pass.
Creation and first evaluation are atomic; Entry interaction is not required.

The first observation may be WAITING, QUALIFIED, FAILED or UNAVAILABLE. Preserve
plan-available time, creation time, first evaluation boundary, first Entry
interaction, first qualification, failure and expiry separately.

Multiple cycles may exist for the same immutable plan in one session only after
a prior terminal `TIMING_FAILED` cycle and deterministic reset. A successor
boundary must be later, the same plan/session/instrument/contract/direction/setup
must remain current, the exact prior failure must no longer hold, and progression
must be ALIGNED or FORMING—not contradictory.

Pullback resets when later progression is aligned/forming and no longer
opposing. Breakout LONG additionally requires later Close at/above Range High;
SHORT requires later Close at/below Range Low. The reset observation may
immediately qualify. A failed cycle is never rewritten to WAITING. There is no
bar/time cooldown, arbitrary delay or maximum attempt count.

### 10. Qualified persistence and expiry

Qualification is immutable historical truth. Current projection remains
QUALIFIED until an explicit FAILED, EXPIRED or supersession transition. Later
candles cannot create stateless `QUALIFIED → WAITING → QUALIFIED` flicker.
Later failure or expiry creates a new immutable transition and preserves the
earlier qualification.

Expiry causes are `SESSION_END`, `WO13_PLAN_SUPERSEDED`,
`UPSTREAM_CYCLE_SUPERSEDED`, `INSTRUMENT_CONTRACT_SUPERSEDED`, and applicable
DOMAIN-008 invalid/closed market/session. There is no N-bar, minute or TTL
expiry. Timing cycles do not carry overnight; a new session needs new
authoritative analysis/geometry.

### 11. Extension and research telemetry

Let `C` be latest completed governed 5M Close and `E` immutable Entry Reference.

- LONG directional extension: `C - E`.
- SHORT directional extension: `E - C`.
- Absolute extension: `abs(C - E)`.
- Where valid, normalized directional extension:
  `directional_extension / ATR14_5M`.

ATR is completed-5M Wilder/RMA ATR-14: True Range, 14-period seed mean, then
`((previous ATR * 13) + current TR) / 14`. It must bind the same Instrument,
active contract/roll, 5M lineage and boundary with sufficient completed
history. Invalid, non-positive, insufficient or mismatched ATR makes normalized
extension `UNAVAILABLE`; raw distance may remain available.

Extension authority is `ADVISORY_RESEARCH_ONLY`, severity `UNCLASSIFIED`, and
threshold/veto authority none. No 0.5/1/1.5/2 ATR or other threshold is frozen.
Maximum favourable/adverse/before-qualification extension may be retained.

Existing volume, relative-volume, percentile, RSI-14, SMA20/50/200,
stack/slope/price relation, Railway, CPR, PDH/PDL and Pivot facts are research
or context only. They cannot qualify, fail, expire or veto Timing, or rewrite
Entry. Session phase, timing latency, retest/path, WO-14 reference and later
outcome references may also be retained without authority.

### 12. Append-only observations and versioned handoff

Timing observations and transitions are append-only. Each transition binds
cycle, prior/new state, cause, exact 5M evidence and boundary, WO-13 plan,
Instrument, session, policy/version, timestamp, provenance and integrity.
Repeated WAITING observations may remain in history without repeated downstream
handoff.

`KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1 / 1.0.0` is the separately versioned
downstream trust boundary. It is created for QUALIFIED, FAILED, EXPIRED and
UNAVAILABLE transitions. A successor FAILED/EXPIRED handoff references and
does not mutate an earlier QUALIFIED handoff. Consumers use the latest current,
non-superseded handoff and cannot select an older QUALIFIED result.

The handoff preserves the exact plan/integrity, cycle/observation/transition,
states/cause, direction/setup/Entry, qualification path, 5M evidence/boundary,
timing timestamps, extension/research references, session/calendar,
Instrument/contract/roll, policy, optional Risk reference, creation time,
provenance, integrity and supersession lineage.

The Risk reference is audit/context only and establishes no freshness,
approval or permission. `TIMING_EVIDENCE_AUTHORITY = YES`; the handoff has no
Sponsor Decision, PAPER/LIVE/IGNORE, position or broker authority.

### 13. Product-family and trust boundaries

- Equity timing is the stock's own completed governed 5M evidence.
- NIFTY/BANKNIFTY timing is underlying-Index completed governed 5M evidence;
  option premium cannot substitute and WO-15 selects no option vehicle.
- MCX timing is the exact active governed MCX futures contract's completed 5M
  evidence; COMEX, NYMEX and USDINR cannot trigger or substitute.
- NATGAS may be structurally supported, but while commissioning is held its
  operational timing remains unavailable/upstream-held.

Foreign/superseded plans, direction/setup/instrument/active-contract/roll
mismatch, stale mandatory 5M evidence, incomplete candle misuse, boundary,
session/calendar or policy mismatch, corrupt evidence and integrity failure are
trust blockers. They produce `TIMING_UNAVAILABLE`, not ordinary
`TIMING_FAILED`, with an exact bounded reason.

### 14. Deferred and prohibited authority

Unresolved items remain extension/chase threshold, severity bands, ATR veto,
volume threshold/consequence, RSI consequence, Railway/SMA consequence,
CPR/PDH/PDL/Pivot proximity consequence, N-bar/time expiry, extension alert,
option-premium execution timing and new indicator gates. No values are chosen.

WO-13 mutation, LTP or wick-only triggers, buffers, two-close or mandatory
retest/indicator confirmation, ATR/R:R veto, new indicator/AI score,
reference-market substitution, Risk/Sponsor rewriting of Timing and broker
action are prohibited.

## Relationship and supersession

This ADR is additive to ADR-0021, ADR-0022 and ADR-0023. It supplies the WO-15
boundary they reserved. For Intraday only, ADR-0023 and this ADR govern over
ADR-0011's generic Risk-permission prerequisite; Swing ADR-0011/ADR-0013 and
all Swing KR-380 contracts, timing grammar, persistence and lifecycle semantics
remain unchanged.

## Reuse classification

Reuse as principles: immutable identity, append-only observations, explicit
state transitions/supersession, current-pointer and downstream-handoff patterns,
and Sponsor/broker separation. Reuse through Intraday adapters: governed 5M
evidence, DOMAIN-008 sessions, Instrument/active-contract identity and later
runtime/persistence patterns. Do not copy Swing timeframe grammar, timing
rules, Risk permission semantics, Daily invalidation, numerical thresholds or
unapproved lifecycle assumptions.

## Canonical policy artifact

The deterministic policy is
`KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1 / 1.0.0` with SHA-256
`d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26`.
No unresolved threshold has a production value.

## Attention and delivery boundaries

WO-15 may expose factual state-event identities such as `TIMING_QUALIFIED`,
`TIMING_FAILED`/`TIMING_LOST`, `TIMING_EXPIRED` and
`ENTRY_REFERENCE_RETEST`. They are not notification delivery mechanisms.
Telegram, email, desktop, sound and push delivery remain downstream. No
`EXTENSION_ALERT` exists until a threshold is separately governed.

A Sponsor manual entry cannot rewrite an unqualified timing state to
`TIMING_QUALIFIED`; any future manual-exception record belongs to a separate
downstream governance boundary.

## Consequences

- WO-15 A/B/C/D architecture is frozen but not implemented.
- Current Review candidates and all production evidence remain untouched.
- No Provider, runtime, Browser, Sponsor-decision, lifecycle or broker authority
  is created.
- Source engineering remains blocked until this exact governance commit is
  reviewed, separately authorized, published and repository synchronization is
  verified.

## Validation requirements

Architecture tests must prove exact states and precedence; completed-5M-only
authority; strict close/progression grammar; Pullback and Breakout Direct/
Retest/Resumption/failure/reset; immutable multiple-cycle statefulness; bounded
expiry; research-only extension/ATR/indicators; WO-13 immutability; WO-14
non-veto; family-local authority; fail-closed trust; handoff authority; deferred
items; and zero Sponsor/broker authority.

## Supersedes

- For Intraday WO-15 only, any generic ADR-0011 implication that current
  DOMAIN-007 Risk permission is a prerequisite to KR-380 evaluation.

## Superseded By

None.

## Related documents

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0021](ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
- [ADR-0022](ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
- [ADR-0023](ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md)
- [WO-15 product architecture](../products/intraday/KRONOS-INTRADAY-WO-15-KR380-ENTRY-TIMING-V1.md)
- [WO-15 policy](../products/intraday/KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json)
- [DOMAIN-008](../platform/domains/market/ARCHITECTURE.md)

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-09-01 | 1.0 | Chief Architect / Sponsor, recorded by Codex | Freeze Intraday WO-15 completed-5M timing architecture | APPROVED — PUBLICATION PENDING |
