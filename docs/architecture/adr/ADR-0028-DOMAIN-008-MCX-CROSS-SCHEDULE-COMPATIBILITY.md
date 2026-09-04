# ADR-0028 — DOMAIN-008 MCX Cross-Schedule Compatibility

## Metadata

- **ADR Number:** ADR-0028
- **Decision Identity:** `KRONOS-DOMAIN-008-MCX-CROSS-SCHEDULE-COMPATIBILITY-V1`
- **Title:** DOMAIN-008 MCX Cross-Schedule Compatibility
- **Status:** APPROVED — ENGINEERING VALIDATION PENDING
- **Date:** 2026-09-04
- **Decision Owner:** Chief Architect / DOMAIN-008
- **Approved By:** Chief Architect
- **Decision Scope:** Platform / DOMAIN-008 / MCX schedule provenance
- **Authority:** `MARKET_SCHEDULE_COMPATIBILITY_ONLY`
- **Runtime / Provider / Analytical / Trading / Broker Authority:** NONE

## Context

DOMAIN-008 publishes the base `KRONOS-MARKET-CALENDAR-V1` schedule and a
family-specific MCX expiry-session specialization. On an expiry trading date,
completed-evidence selection may therefore need the derived current session
and an ordinary previous session from the base publication. Matching clocks do
not prove that two differently identified schedule authorities belong to one
governed lineage.

## Decision

### 1. DOMAIN-008 ownership

DOMAIN-008 alone owns schedule compatibility. Downstream products may consume
an exact compatibility fact; they may not infer, create or broaden it.

Schedule identity identifies one schedule contract. Schedule lineage records
its authoritative publication provenance. Compatibility is a separate,
directional statement that one exact derived schedule specializes one exact
base schedule for a bounded context. It is neither identity nor equivalence.

### 2. Immutable compatibility contract

DOMAIN-008 publishes
`KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V1 / 1.0.0` under policy
`KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V1 / 1.0.0`.

Each immutable artifact binds the exact derivative family, exchange, market,
segments, timezone, trading date, previous trading date, analysis boundary,
current and previous session identities, base and derived contract identities
and versions, source publication identities, versions and digests, source
boundaries, effective interval, status, supersession reference, provenance and
integrity identity.

The direction is always base schedule to derived family-specific expiry
schedule. `A compatible with B` is not a valid substitute.

### 3. Exact publication relationship

The derived schedule must be the exact governed family-specific expiry-session
specialization returned by the current `MarketCalendarPublisher` for GOLDM,
SILVERM, COPPER, NATURALGAS or CRUDEOIL. NATGAS and CRUDE are only the existing
explicit governed aliases. The previous session must be the exact governed
base-calendar schedule.

Both source publications and their digests must be current and valid at the
analysis boundary. The artifact applies only to its bound family, expiry,
trading dates, sessions, publications and boundary. A superseded artifact is
not applicable.

### 4. Fail-closed consumption

An unchanged same-authority pair continues through the existing ordinary
validation path. A different-authority pair is accepted only with the exact
applicable compatibility artifact. Missing, stale, superseded, tampered,
wrong-family, wrong-date, wrong-session, wrong-market, wrong-exchange or
wrong-lineage proof fails closed.

Clock equality has no compatibility authority. Exchange or family equality
alone has no compatibility authority. Wildcard compatibility is prohibited;
arbitrary mixed schedules are prohibited.

### 5. Historical and roll boundaries

Compatibility does not rewrite historical session truth. Historical
completed-evidence artifacts remain immutable. Successor evidence retains both
schedule lineages plus the compatibility artifact. Historical publications and
artifacts remain immutable.

Compatibility is not contract-roll continuity and cannot bridge contracts,
select an active derivative or migrate an existing binding.
NATGAS commissioning hold is unchanged.

### 6. Negative authority

The contract grants no analytical, admission, promotion, Trade Construction,
Risk, Entry Timing, Sponsor, position, Provider, execution, trading or broker
authority. It changes no Intraday or Swing methodology.
It grants no trading or broker authority.

## Consequences

The governed expiry-session current schedule can be paired with the governed
regular previous session without discarding either provenance. Unrelated mixed
schedules remain rejected, and existing same-source and historical V1 behavior
remain unchanged.

## Related Records

- [DOMAIN-008 Architecture](../platform/domains/market/ARCHITECTURE.md)
- [DOMAIN-008 Engineering](../platform/domains/market/ENGINEERING.md)
- [ADR-0017 — Governed Active Derivative Contract Selection](ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md)
