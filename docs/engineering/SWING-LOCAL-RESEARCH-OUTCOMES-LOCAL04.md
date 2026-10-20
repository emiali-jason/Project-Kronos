# LOCAL-04 — retained research outcome measurement

Status: isolated Release B candidate; independent owner review and deployment pending.
Measurement contract: `KRONOS-SWING-LOCAL-OUTCOMES-1.0`.
LOCAL-01 analysis methodology remains `KRONOS-NSE-LOCAL-RESEARCH-1.0`, byte unchanged.

## Sources and timing

Reuse the existing WO-12 immutable store, original Local owner, governed calendar,
FollowupCandle records and retained NSE equity corporate-action authority. No new
store, Provider, model, scheduler or route. The existing LOCAL-03 recorder freezes
these projections in its immutable BASE/SUPPLEMENT intent and workbook. Reading a
projection performs no acquisition, recording, notification, position or model call.

An observation is one validated immutable Local original, not a unique security or
an independent statistical sample. Exact Native run/assessment/instrument/direction
must resolve to exactly one retained WO-12 origin and exact contract binding. No
origin or ambiguous origin means unavailable measurement; symbols are not used as
substitutes for exact contract identity. Repeated original assessments remain
separate observations; counts disclose distinct instruments. Method versions are
never pooled. The Native comparator is explicitly `NATIVE_PAIRED`: the Native
hypothesis evaluated at the *Local completion clock*, not a reconstruction of an
earlier independent Native signal. Support, rejection/challenge and abstention
cohorts are fixed by the original Local conclusion, never subsequent outcomes.

Signal time is the original completion timestamp. Reference price is its bound
retained 1D close, explicitly not an entry or live signal-time quote. The whole
signal date is excluded. Only the next completed governed sessions count. Existing
WO-12 1/3/5/10 checkpoint semantics are unchanged; this separate versioned projection
adds a 20-session measurement when actual calendar and candle coverage permits.
No weekday-calendar inference. A complete retained calendar sequence, captured by
the cut, must cover the signal date through the due date. Conflicting overlapping
calendars are unavailable. Future captures/revisions are excluded before candle
revision selection. Missing sessions, incomplete coverage, unresolved revisions,
capture before close, wrong contract/session and unverified common price basis
withhold metrics. Existing official corporate-action reports are reused read-only
under a nonwaiting authority lock. Busy/unknown authority remains unavailable;
corporate-action windows without a governed comparable basis are not scored.

## Measurements, denominators and limitations

Direction-adjusted change = `(horizon close / original retained close - 1) * 100`,
negated for SHORT. Candle MFE = max(0, highest favourable excursion from reference);
candle MAE = min(0, most adverse excursion from reference), both in percent. These
are subsequent covered candle excursions, **not position or lifecycle MFE/MAE**.
Flat results remain unchanged, not wins. Reports expose observed, pending,
unavailable and abstained denominators and with/against/unchanged counts. No
estimated win probability, confidence interval or independent-sample claim.
Positive matched Native outcomes in the rejected/challenged cohort are labelled
observable missed-opportunity evidence. Unscanned securities are unobservable.

Every original structural radius, direction and scenario remains distinct. Entry
windows are the predeclared horizon maximum: SHORT 3, MEDIUM 10, LONGER 20 sessions.
An entry-zone intersection is only a level touch; conditional activation, volume,
intrabar path and a fill are not established. A terminal level on the same candle
as first entry touch, or both target/invalidation on a later candle, is AMBIGUOUS.
There is no favourable ordering assumption. A later single terminal level is a
labelled target/invalidation touch, not a trade win/loss. No entry touch before
window expiry is ENTRY_NOT_REACHED; an entry without a terminal touch is
ENTRY_TOUCH_ONLY. All require full window evidence, even if an earlier touch exists.
Original theoretical reward/risk is retained; realized R and monetary P&L are
unavailable from these hypothetical scenarios. Actual pre-existing PAPER lifecycle
facts are shown separately with their owner event, timestamps and source economics;
no new position, fill, cost or return is calculated.

## Export, history and lifecycle

The six original WO-12 sheets and LOCAL-03 Local_Research sheet remain intact.
Optional Local_Outcomes and Local_Performance sheets are additive. Outcome rows
show scalar directional/scenario results and retain the exact full measurement JSON,
its content identity, original identity, calendar/candle source identities and
corporate-action proof identities. Daily frozen source references include outcome
dependencies from earlier dates. Old prepared projections omit the new optional
fields and reproduce their old workbook bytes; no migration or rewriting occurs.
Later outcomes/revisions produce a new SUPPLEMENT with the earlier BASE untouched.
Restart replays the original frozen publication intent before considering a new cut.

No new runtime worker or trigger is introduced. LOCAL-03 existing counted research
worker, archival source reader, maintenance fence, shutdown lock, 23:00 IST pulse
and retained-only manual action remain authoritative. Busy corporate-action reads
return UNKNOWN without waiting on an import. Existing acquiring Historical Research
UPDATE is separate and is never invoked by recording or projection.

## Acceptance boundary

Synthetic qualified cases demonstrate arithmetic, LONG/SHORT, rejected/abstained
cohorts, unknown coverage, additive 20 sessions, future leakage, immutable replay,
workbook compatibility, no GET writes, no acquisition/model access and desktop/narrow
rendering. They do not establish genuine market performance, deployment, a successful
23:00 production recording, PAPER economics or Sponsor acceptance. Release B still
requires exact successor owner review, Release Policy closure and separate operational
authorization. No retired source is deleted; API-based SW-FAST-03 remains excluded.
