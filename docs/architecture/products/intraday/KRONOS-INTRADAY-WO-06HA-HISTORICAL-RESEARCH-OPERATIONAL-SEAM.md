# KRONOS Intraday WO-06HA Historical Research Operational Seam

**Status:** Engineering candidate; no real Provider acquisition performed

**Operation:** `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-V0 / 0.1.0`

**Request:** `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-REQUEST-V0 / 0.1.0`

**Boundary:** `KRONOS-INTRADAY-COMPLETED-SESSION-EOD-RESEARCH-V0 / 0.1.0`

## Authority and isolation

The seam reconstructs research-only WO-06H factual bundles for explicit
completed sessions. It cannot create or update production Discovery, candidate,
Probable, promotion, construction, Risk, entry, execution, Sponsor-position,
notification or broker state. Production publication validity remains strict:
an observation before the production universe `valid_from` remains
`PUBLICATION_STALE`.

The implementation is Intraday-owned and is not composed into normal startup or
the Browser. Invocation is through a narrow typed harness only. It accepts no
arbitrary symbol, interval or Provider query language.

## Explicit completed-session boundary

Every request binds an ordered, duplicate-free list of trading date plus exact
session identity pairs. `LATEST`, `NEWEST`, `CURRENT`, rolling discovery and
automatic backfill are invalid. DOMAIN-008 supplies the actual target schedule,
its final governed window close and the previous governed trading schedule.
No normal-session clock or calendar-day subtraction is an authority.

Input facts must be available no later than the target session's final governed
close. The timeframe set is exactly 1D, 1H, 15M and 5M. Narrow CPR for target D
reuses the Part-1 `NARROW_CPR_KGS_V0` implementation and the previous governed
completed Daily session; D's Daily candle is not its pre-existing CPR input.
Future outcome acquisition is not automatic and V0 rejects outcome families.

## Provider boundary and request planning

The operation verifies the actual `SharedAuthenticatedProviderRuntime` lifecycle
and stops on absent or expired context. It has no authentication authority. One
operation-scoped read-only lease is requested with only `INSTRUMENTS` and
`HISTORICAL_DATA`; no second runtime, context, order or mutation capability is
created.

Before obtaining the lease, the planner derives:

`eligible subjects × explicit sessions × 4 historical timeframes`

plus one exchange-scoped instrument-record acquisition for each represented
eligible exchange. The caller supplies a finite request ceiling, bounded by the
contract maximum. Exceeding it returns `REQUEST_BOUND_EXCEEDED` before Provider
work. Execution is sequential, has no automatic retry and permits one operation
at a time. A duplicate completed identity returns the retained in-process
terminal result without new work. Restart neither resumes nor reacquires.

## Subject resolution and MCX

Membership derives from the current governed Intraday universe. Exact canonical
and Provider factual bindings derive from its governed P5 reconciliation; this
does not let Provider presence create membership. The current reviewed state is
98 represented subjects: 93 exact NSE historical paths and five MCX
`HISTORICAL_PREREQUISITE_UNAVAILABLE` paths. GOLDM, SILVERM, COPPER, NATGAS and
CRUDE remain in accounting and cause zero Provider history requests. There is no
active, nearest, front-month, volume, OI, liquidity or fuzzy-symbol selection.

## Persistence, output and corpus separation

Successful artifacts reuse the immutable WO-06H subject, binding, session,
previous-session, fact-bundle, reconstruction and eligibility contracts and
store. Every write is followed by explicit-identity document and object reload,
identity verification and equality comparison. There is no latest-file or
directory-order resolution.

The generic result exposes only bounded counts, governed identities, typed
failure categories and state. Raw credentials, Provider tokens, records,
candles, SDK objects, exception prose and tracebacks are not projected. A
successful reconstruction is only eligible for later explicit corpus-binding
review; automatic corpus binding is false.

## Bounded five-session proposal

For one later separately authorized operational proof, DOMAIN-008 publication
`KRONOS-NSE-CAPITAL-MARKET-2022-2026 / 2026.1.2` supports the explicit sessions
2026-08-17 through 2026-08-21. This is a bootstrap proposal, not production
policy or an evidence-sufficiency constant. With the current governed 98/93/5
resolution it plans 1,860 historical requests plus one NSE instrument-record
operation, total ceiling 1,861. No request in this proposal was executed by
WO-06HA.

## Readiness and next sequence

`HISTORICAL_REAL_BOOTSTRAP_READY = CONDITIONALLY_YES`: engineering proof is
complete, while real execution still requires publication/runtime loading,
Sponsor authentication only if the actual shared context is not active, and a
separate operational authorization. The later sequence is acquire, persist,
reload, review and explicitly bind an approved corpus before Part-2 analysis.
WO-06 Part 3 remains not started.
