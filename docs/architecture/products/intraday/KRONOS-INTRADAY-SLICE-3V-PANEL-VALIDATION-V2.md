# Slice 3V V2 — panel temporal and factual correspondence

Status: WO-02B engineering candidate; publication review pending.
Owner: KRONOS Intraday.
Authority: Sponsor WO-02B explicit bounded engineering instruction.
Baseline: 476209b7ceb5061b9570c313851f1c4c1c69e776.
Contract: KRONOS-INTRADAY-SLICE-3V-PANEL-VALIDATION-V2 / 2.0.0.

## Boundary and compatibility

This additive contract strengthens the existing Slice 3V implementation in
validation.py and validation_persistence.py. It reuses the V1 exact,
approximate and relational comparison primitive. V1 contracts, record bytes,
loaders, tests and interpretation remain unchanged. Historical qualitative
Review Answers are not V2 observations and have no upgrade path.

This is validation evidence only. Machine prices and candles remain governed
machine authority. No admission, direction, Readiness, Promotion, trade
construction, Risk, timing, execution or broker state is produced or changed.
Review Q1–Q10, chart intake, Browser routes and production runtime are unchanged.

## Machine-owned request and independent observation

PanelValidationRequest retains:
- the existing frozen MachineEvidence, including run/evidence identity,
  canonical subject, exchange, analysis boundary and immutable factual values;
- exact chart revision identity, expected payload SHA-256 and chart receipt time;
- the panel context key and exact PanelSource records;
- the complete versioned required-fact inventory and machine-owned applicability;
- request provenance and contract/version.

Each PanelSource retains its context key, machine source evidence identity and
the complete existing GovernedCandle, including candle identity, subject,
timeframe, session/date, endpoints, completion, observation boundary and source
provenance. The request producer must bind these from the selected immutable
machine and chart records, never from a newest-file search or observer claims.
Candle and previous-session H/L/C facts are also checked against source values.

PanelVisualObservation is an independent observer payload: raw observed subject,
exchange, panel timeframe, capture time, Answer time, observed temporal contexts
and factual observations. It contains no canonical ID, machine evidence/run
identity, machine prices, direction or analytical conclusions. A context key
is an opaque question role, not a machine candle identity.

The observed session is the visible session description (for example,
CONTINUOUS_TRADING), compared with the governed schedule's session type.
The Analyst is not asked to manufacture a KRONOS session identity.
Machine session identities remain in the retained machine and schedule envelope.

The application supplies actual chart bytes and their selected revision identity
separately. Matching bytes/revision establish FILE_IDENTITY only. DOMAIN-001's
existing exact, effective-dated VisualIdentityResolver establishes visual
identity; its full resolution/provenance references are retained. No local
alias map, trimming, case folding, ticker inference or fuzzy fallback exists.
Zero or ambiguous relationships fail closed.

## Temporal correspondence

Each observed temporal context independently reports:
- trading date;
- session description;
- timezone name;
- timeframe;
- candle start and end;
- completed/incomplete state.

Missing fields remain missing. Capture time, chart receipt time, analysis time,
machine freeze time, Answer time and comparison time remain separate.
This comparison service performs no Answer import: ANSWER_IMPORT stays
NOT_VALIDATED and imported_at stays null. Comparison time never becomes import
time. No visual-reliability assessment is performed.

The service consumes the existing DOMAIN-008 MarketCalendarPublisher subject
session profile at the machine analysis boundary. It retains the exact selected
continuous or closing-auction schedule, including identity/version and provenance.
It reuses Intraday expected_candle_boundaries against those authoritative
windows. Session IDs and endpoints must match the actual source candle.

The source candle must be governed COMPLETE and end no later than analysis.
The observed candle must match the exact source date/session/timeframe/endpoints,
with the governed timezone name and COMPLETE status. Missing proof or incomplete
evidence is UNVERIFIABLE. Explicit contradictory dates, sessions, timezones or
endpoints are NOT_VALIDATED. Capture must follow the candle endpoint and precede
receipt; Answer must follow machine freeze and receipt; comparison follows all.

Previous-session 1D/1H panel context is lawful: panel end need not equal the
analysis minute. Previous-session level, pivot and CPR requirements bind a daily
source from the previous trading date in the existing DOMAIN-008 publication.
A different older daily source cannot pass merely because the observer agrees
with that wrong source. The machine source evidence identity and full candle
remain retained. No calendar convention or exchange schedule is invented here.

## Required facts and observability

Every panel request contains all 30 slots, in this fixed order:

1. candle.open, candle.high, candle.low, candle.close
2. previous.high, previous.low, previous.close, previous.pdh, previous.pdl
3. pivot.p, pivot.r1, pivot.r2, pivot.r3, pivot.r4,
   pivot.s1, pivot.s2, pivot.s3, pivot.s4
4. cpr.pivot, cpr.lower, cpr.upper, cpr.width
5. structure.local_high, structure.local_low, structure.range, structure.break,
   structure.retest, structure.return_through, structure.boundary_interaction
6. volume.participation

CPR lower/upper consume the governed normalized lower/upper equivalents; visual
intake cannot swap levels or infer a new numeric interpretation. Structure and
participation values are existing machine facts, not new indicators or rules.
Each slot links an exact source context. Applicability is machine-owned and a
non-applicable slot requires explicit governed applicability provenance.
Visual NOT_APPLICABLE cannot override an applicable requirement.

Each observation has EXACT, APPROXIMATE, RELATIONAL, NOT_VISIBLE, UNVERIFIABLE
or NOT_APPLICABLE observability. The last three prohibit a value and value kind.
EXACT reuses exact kind/value comparison. APPROXIMATE stays unverifiable even if
its digits equal the machine value. RELATIONAL requires explicit per-requirement
permission and an identical governed relationship; it cannot validate a number.
There is no numerical tolerance.

## Coverage and result states

Every result contains all 30 expected slots with disposition:
OBSERVED, NOT_VISIBLE, UNVERIFIABLE, NOT_APPLICABLE or MISSING.
Omitted machine facts remain explicitly MACHINE_FACT_UNAVAILABLE.
Subset requests cannot shrink the required inventory.

Coverage is separate from correctness and temporal proof:
- COMPLETE_REQUIRED_FACT_COVERAGE: each slot has an observation and machine fact,
  or an explicitly corroborated machine-owned NOT_APPLICABLE disposition.
- PARTIAL_REQUIRED_FACT_COVERAGE: some but not all slots satisfy that accounting.
- NO_REQUIRED_FACT_COVERAGE: none do.

NOT_VISIBLE, UNVERIFIABLE and MISSING do not count as covered. An approximate
value counts as observed but remains factually UNVERIFIABLE. Complete coverage
can coexist with a mismatch or unproven time; it is never an automatic pass.

Each fact records its result and bounded reason. Applicable factual results
roll up as:
- VALIDATED: all applicable facts match under permitted precision and proven time;
- NOT_VALIDATED: an explicit contradiction or identity failure exists;
- PARTIALLY_VALIDATED: some facts validate and others remain unverifiable;
- UNVERIFIABLE: none validate and proof remains unavailable.
An entirely non-applicable scope does not produce factual validation.

The record separately exposes FILE_IDENTITY, VISUAL_IDENTITY,
TEMPORAL_CORRESPONDENCE, FACTUAL_CORRESPONDENCE, ANSWER_IMPORT and
VISUAL_RELIABILITY. Identity failures gate factual comparisons. The overall
result cannot upgrade missing temporal proof or a factual mismatch.

## Persistence

The existing LocalSlice3VValidationStore gains retain_panel_record and
load_panel_record. New records live only in panel-validation-v2, selected by
exact deterministic identity. Legacy directories are untouched.

Records retain the complete request and observation, actual chart digest,
selected revision, DOMAIN-001 resolution, DOMAIN-008 schedules, per-context
temporal results, per-fact outcomes, states, timestamps and integrity identities.
The chart binary remains referenced by immutable revision/digest; it is not
rewritten or copied into the record.

Canonical tagged serialization preserves Decimal values, tuple ordering, dates,
aware timestamps, enums and the closed set of allowed contract types. Unknown
versions/types or changed integrity fail restoration. Exact duplicates are
idempotent. Atomic no-clobber publication prevents concurrent store instances
from replacing an existing record. Reads reject nonconforming record identities;
there is no latest-file or current-pointer API.

## Qualification and next gate

Focused synthetic tests cover all four NSE timeframes, equity/index resolution,
wrong/unavailable/ambiguous identities, source/session/date/timezone/endpoint
mismatches, incomplete/missing timing, lawful previous-session context, every
required fact, observability, applicability, completeness, exact source binding,
immutable/idempotent storage, partial restoration, tamper and legacy safety.

These are mechanism tests, not real chart-correspondence evidence or empirical
visual reliability. Production capture, Answer import and new real-market
comparison remain for separately authorized WO-02C after engineering review.

The implementation has no fixed instrument-population capacity. It consumes
governed NSE equity/index identities generically. Immediate V2 requests are
NSE-only. Existing MCX paired architecture and 4H evidence remain unchanged;
nothing relabels 4H as 1H or transfers reference prices into native truth.

## References

- [V1 contract](KRONOS-INTRADAY-SLICE-3V-FACTUAL-VISUAL-VALIDATION-CONTRACT-V1.md)
- [Current Authority Manifest](KRONOS-INTRADAY-CURRENT-AUTHORITY-MANIFEST-V1.json)
- [DOMAIN-001 visual identity](../../adr/ADR-0018-DOMAIN-001-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-V1.md)
- [DOMAIN-008](../../platform/domains/market/ARCHITECTURE.md)
- Accepted WO-02A coverage reconciliation and Sponsor WO-02B work order.
