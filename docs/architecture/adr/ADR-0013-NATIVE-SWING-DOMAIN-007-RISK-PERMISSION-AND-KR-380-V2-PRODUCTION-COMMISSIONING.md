# ADR-0013 — Native Swing DOMAIN-007 Risk Permission and KR-380 V2 Production Commissioning

## Metadata

- **ADR Number:** ADR-0013
- **Decision Identity:** SWING-PROD-CLOSURE-01
- **Status:** APPROVED
- **Date:** 2026-08-21
- **Decision Owner / Approved By:** Chief Architect / Sponsor
- **Scope:** Swing V1 / DOMAIN-005 / DOMAIN-007 / KR-380A / KR-380 / KR-390
- **Engineering Status:** Authorized for the exact bounded Native V1/V2 path below
- **Broker Authority:** NONE
- **Autonomous Trading:** NOT AUTHORIZED

## Decision

### DOMAIN-007 V1

DOMAIN-007 V1 is a fail-closed objective-model Risk Permission gate. It decides
whether one exact current, valid, persisted Step-31 Trade Plan may enter
objective KR-380 entry-timing monitoring.

The policy identity is `KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1`, version
`1`. Results use the existing states:

- `APPROVED`: every mandatory binding is current and valid and no explicit
  governed prohibition applies;
- `CONSTRAINED`: an existing governed constraint permits bounded objective
  evaluation; V1 creates no constraint;
- `REJECTED`: an existing governed hard prohibition prevents objective timing;
- `UNAVAILABLE`: a mandatory input or binding is missing, stale, invalid,
  mismatched, superseded, or unavailable.

`APPROVED` and `CONSTRAINED` permit objective timing only. They are not Sponsor
recommendations, positions, quantities, orders, fills, or execution.

### Portfolio State V1

DOMAIN-005 publishes the immutable factual contract
`KRONOS-SWING-PORTFOLIO-STATE-V1`, version `1`. It binds a cycle identity,
as-of boundary, restored objective-model exposures, restored Sponsor-position
exposures, source completeness, provenance, and integrity. An empty state is
valid only after every governed source was loaded successfully and proved
empty. Missing source evidence is not an empty portfolio.

### Exclusions

V1 does not calculate quantity, risk percentage, capital allocation, notional,
margin, leverage, concentration, correlation, drawdown, sector limits,
maximum positions, or daily loss. Those are reserved for a future separately
approved DOMAIN-007 V2. Step-31 remains the sole owner of Entry, Stop, Target,
invalidation, and R:R geometry; Risk introduces no R:R threshold.

### Binding and validity

Every Risk result binds the current run, canonical instrument, KR-370 source,
UX-05 handoff, Step-31 plan and integrity, Portfolio State cycle and integrity,
policy version, evaluation boundary, provenance, and integrity digest. It is
valid only while the exact plan and Portfolio cycle remain current. Cycle or
plan supersession invalidates it; no clock-based expiry is introduced.

### ECPC V2 and shared monitoring

KR-380A is commissioned as the Native producer of the already-approved ECPC
V2 public contract. It packages the governed direction-bound, Risk-permitted,
plan-bound monitoring context and preserves the approved `PENDING`,
`QUALIFIED`, `EXTENDED`, `FAILED` semantics and blocker precedence. It does not
infer direction, change geometry, create Risk, or create an Entry Outcome.

`SharedSwingMonitoringHub` remains the single Provider-neutral factual
transport. It owns no Risk, entry-timing, lifecycle, or broker meaning.

### KR-380 V2 commissioning

`KRONOS-KR-380-ENTRY-OUTCOME-V2`, version `2`, state family
`KR380_ENTRY_OUTCOME`, is commissioned as the current authoritative Swing
objective-model entry-timing contract. Its states are `NO_TRIGGER`, `FORMING`,
`LONG_ENTRY_TRIGGERED`, `SHORT_ENTRY_TRIGGERED`, `EXTENDED`, and `FAILED`.

The producer preserves exact plan/Risk/context/monitoring bindings, monotonic
observation ordering, source sequence, session continuity, prior-interval
availability, pre-entry-side proof, and exact directional crossing. First
observation beyond Entry, gaps, disorder, ambiguity, staleness, and mismatches
fail closed and do not trigger.

Current Risk permission and `QUALIFIED` ECPC context are mandatory for a
triggered state. Immutable records are atomically persisted, integrity checked,
and restored without replaying or duplicating a trigger.

### KR-390 and Sponsor separation

KR-390 may activate a current objective model only from an exact current V2
`LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED` record. `NO_TRIGGER`,
`FORMING`, `EXTENDED`, `FAILED`, KR-370 promotion, UX-10 events, and historical
V1 records cannot activate it.

Objective-model truth is independent of Sponsor `LIVE`, `PAPER`, `IGNORE`, or
no decision. Objective activation creates no Sponsor position, order, fill, or
actual P&L.

### Historical and UX isolation

Historical KR-380 V1 `BUY NOW` / `SELL NOW`, intermediate Step-32 validation
records, historical Review evidence, plans, and models remain immutable and
separate. UX-10 remains notification/monitoring delivery only. Settings and
Dashboard acquire no new authority.

## Consequences

- The exact Native path supersedes `SHADOW / VALIDATION ONLY` for DOMAIN-007
  V1, ECPC V2, KR-380 V2, persistence/restoration, and legitimate KR-390
  handoff only.
- Missing or invalid mandatory evidence remains fail closed.
- No autonomous trading or broker capability is introduced.

## Related documents

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0012](ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md)
- [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [Swing V1 Step-32 contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md)
- [DOMAIN-007](../platform/domains/risk/ARCHITECTURE.md)
- [DOMAIN-005](../platform/domains/portfolio/ARCHITECTURE.md)
