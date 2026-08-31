# ADR-0023 — Intraday DOMAIN-007 Advisory Risk Observation Boundary

## Metadata

- **ADR Number:** ADR-0023
- **Decision Identity:** INTRADAY-WO14-RISK-OBSERVATION-GOV-01
- **Title:** Intraday DOMAIN-007 Advisory Risk Observation Boundary
- **Status:** APPROVED
- **Date:** 2026-08-31
- **Decision Owner:** Chief Architect / DOMAIN-007 / KRONOS Intraday
- **Proposed By:** Chief Architect / Sponsor
- **Reviewers:** Chief Architect / Intraday Engineering Architect
- **Approved By:** Chief Architect / Sponsor
- **Decision Scope:** Platform / Intraday Product / Interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved in repository
- **Engineering Status:** Architecture only; WO-14 production source engineering not authorized
- **Runtime Authority:** NONE
- **Broker Authority:** NONE
- **Autonomous Trading:** NOT AUTHORIZED

## Context

The approved platform DOMAIN-007 architecture and ADR-0013 commission a hard,
fail-closed Risk Permission gate for Swing V1. ADR-0015 expressly preserves
that Swing permission behavior. ADR-0022 froze Intraday WO-13 geometry but its
downstream description retained the earlier assumption that WO-14 would
approve, constrain, reject or be unavailable as a permission gate.

The Chief Architect and Sponsor have corrected the Intraday architecture.
Intraday WO-14 must answer what observable loss exposure would exist if the
already-constructed WO-13 trade were taken. It must inform the Sponsor without
vetoing, approving or rejecting the trade. This is product-specific successor
authority and does not reinterpret Swing records or the Swing permission
contract.

## Decision

### 1. Product-specific DOMAIN-007 authority

For Intraday V1, WO-14 owns `RISK_OBSERVATION_ONLY`. It owns loss-exposure
calculation, Risk telemetry and context, evidence availability, freshness,
provenance, observation-methodology identity, and factual portfolio/open-Risk
observation where authoritative inputs exist.

It does not own trade permission, trade rejection, Entry, Stop, Target,
invalidation, Model R:R, direction, setup family, position creation, final
order quantity, PAPER/LIVE/IGNORE, 5M timing or broker execution.

### 2. Geometry is immutable input

WO-14 consumes one exact immutable, integrity-valid WO-13 Trade Plan. It binds
the canonical subject, market family, direction, setup family, Entry Reference,
Stop, Target, risk/reward distance, Model R:R, geometry availability, WO-13
policy and plan identities, boundary, instrument or contract identity and
provenance.

Risk observes geometry and never rewrites it. Changed geometry requires a new
WO-13 plan. Risk may validate arithmetic but may not reconstruct Step-31 or
move a level to improve exposure.

### 3. Successor observation contract

The Intraday successor contract is
`KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1`, version `1.0.0`, with authority
`RISK_OBSERVATION_ONLY`.

Its primary states are:

- `RISK_OBSERVED`: the required factual Risk observation was calculated;
- `RISK_ALERT`: a separately governed Sponsor reference threshold was crossed,
  as informational alert only; and
- `RISK_UNAVAILABLE`: the requested Risk observation could not be calculated
  truthfully.

Initial V1 severity is `UNCLASSIFIED`. No numerical alert band is commissioned.
Therefore ordinary initial operation produces `RISK_OBSERVED` or
`RISK_UNAVAILABLE`; `RISK_ALERT` remains dormant until a successor methodology
governs reference thresholds.

None of these states grants or denies progression to WO-15. The output must not
contain `TRADE_ALLOWED`, `TRADE_BLOCKED`, `RISK_APPROVED`, `RISK_REJECTED`,
`MAX_PERMITTED_QUANTITY`, `EXECUTE`, `PAPER_ALLOWED`, `LIVE_ALLOWED` or
`BROKER_ALLOWED` authority.

### 4. Factual exposure model

The observation preserves separate factual fields rather than collapsing them:

- structural Risk per price unit;
- monetary Risk per tradable unit;
- reference quantity, when configured;
- loss at Stop;
- capital-at-Risk percentage, when a Sponsor reference exists;
- notional exposure;
- existing open Risk and aggregate Risk after the proposed trade, when
  authoritative portfolio facts exist;
- margin observations, when authoritative account facts exist; and
- unavailable fields and exact reasons.

For cash Equity, Risk per share is `abs(Entry - Stop)` and loss at Stop for a
supplied quantity is that value multiplied by quantity. Equity Risk remains
stock-local; NIFTY has no sizing, geometry or loss-calculation authority.

For MCX, the exact active futures binding and canonical instrument economics
are mandatory: lot size, multiplier/unit economics, tick size/value where
applicable, expiry, roll lineage and economics version. COMEX/NYMEX have no MCX
sizing authority. USDINR has no Risk arithmetic authority unless the governed
MCX economics explicitly require conversion. NATGAS remains held upstream.

For Index products, underlying NIFTY/BANKNIFTY geometry alone cannot establish
monetary option Risk. A separately governed execution vehicle must first be
resolved. WO-14 neither selects nor infers strike, expiry, CALL/PUT, structure
or premium vehicle. Until resolution, underlying geometry may remain valid
while option-position Risk is `UNAVAILABLE`.

### 5. Capital, quantity and portfolio context

`INTRADAY_RISK_CAPITAL_REFERENCE` is an optional Sponsor-configured contextual
amount. It is not automatically broker cash, available margin, NAV, net worth
or bank balance. Its absence makes capital-at-Risk percentage unavailable but
does not block monetary facts or WO-15.

WO-14 owns no final or maximum quantity. A future governed Risk preference may
derive an advisory reference quantity rounded down to a valid tradable unit,
but it must be labelled `REFERENCE ONLY`, `NOT EXECUTION PERMISSION` and
`NOT MAXIMUM ALLOWED QUANTITY`. Sponsor-selected actual quantity remains
Sponsor-owned.

Existing and aggregate open Risk are reported only from authoritative facts.
Missing portfolio facts make aggregate Risk unavailable and create no veto.
Margin and notional are distinct factual context; neither currently carries an
enforcement threshold.

### 6. P&L and deferred policy

WO-14 does not invent actual realised P&L, daily loss, winning/losing trades,
actual R or execution facts. LIVE realised P&L requires broker-confirmed fills
or governed Sponsor-attested execution facts; PAPER requires separately
governed simulation facts. Otherwise actual realised P&L is unavailable.

No V1 threshold exists for per-trade Risk, aggregate Risk, daily loss,
losing-trade count, margin, notional, concurrency, sector concentration,
correlation, liquidity, slippage or minimum R:R. Model R:R is context only.
ATR extension/chase and all 5M timing remain WO-15 responsibilities.

### 7. Trust, freshness and immutability

Foreign or corrupt WO-13 plans, integrity/direction/instrument mismatches,
wrong MCX contract, roll-lineage mismatch, execution-vehicle mismatch, capital
snapshot conflict or corrupt economics are hard failures of the observation
operation. They produce `RISK_OBSERVATION_INVALID` provenance and an outward
`RISK_UNAVAILABLE` observation where an outward record is valid. They never
become a trade veto.

Every observation binds the WO-13 plan, execution vehicle where applicable,
instrument economics, any capital/portfolio/margin snapshots, methodology
identity/version, observation boundary, evaluation timestamp, provenance and
integrity. Changed inputs produce a new immutable observation. Prior records
are never mutated. A later WO-15 evaluation may request a fresh observation,
but stale or unavailable Risk alone creates no automatic Entry veto.

### 8. Sponsor and WO-15 boundaries

Sponsor owns PAPER, LIVE, IGNORE, actual participation and actual quantity.
WO-14 informs that choice and preserves what was known or unavailable at the
decision boundary. There is no hidden override because there is no Risk veto.

WO-15 owns final 5M Entry timing, including any future trigger, progression,
extension or chase consequence. It may display Risk facts and alerts as
context but may not rewrite geometry to improve Risk.

### 9. Swing preservation

ADR-0013, ADR-0015 and `KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1` remain
unchanged. Swing retains `APPROVED`, `CONSTRAINED`, `REJECTED` and `UNAVAILABLE`
as permission states and retains their existing hard-gate consequences.

Intraday may reuse immutable binding, identity/integrity, fail-closed evidence,
freshness, append-only persistence and Sponsor-downstream patterns. It may use
adapters for WO-13 handoff, instrument economics, portfolio/account facts,
persistence and presentation. It must not copy Swing thresholds, permission
semantics, quantity assumptions, concentration policy, margin assumptions or
product-specific constraints.

## Rationale

Accurate loss exposure can be useful before numerical policy is mature. Keeping
the layer observational preserves raw facts, keeps the Sponsor informed, and
prevents ungoverned thresholds from becoming hidden trading authority.

## Consequences

- Intraday WO-14 architecture and factual observation methodology are frozen.
- Numerical alert bands remain uncommissioned without blocking factual work.
- WO-14 source engineering remains gated on a published stable WO-13 Trade Plan
  contract/handoff and a separate engineering instruction.
- Runtime, Browser, real Risk observation and WO-15 remain unauthorized.

## Implementation Implications

The future product-owned implementation must consume the actual WO-13 contract
rather than inventing a placeholder. It must use immutable records and must
not import or modify Swing product state. No production source implementation
is authorized by this ADR publication.

## Validation Requirements

- Authority is exactly `RISK_OBSERVATION_ONLY`.
- Geometry cannot be mutated or reconstructed.
- Risk states cannot approve, reject, block or bypass WO-15.
- Sponsor owns participation and actual quantity.
- Risk alerts and unavailable states are informational.
- Execution-vehicle selection, 5M timing and ATR extension are excluded.
- Swing DOMAIN-007 permission semantics remain unchanged.
- Broker authority remains none.

## Supersedes

- ADR-0022 Section 15 only where it describes Intraday WO-14 as approving,
  constraining, rejecting or being unavailable under a permission-oriented Risk
  policy.

## Superseded By

None.

## Related ADRs

- [ADR-0013](ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md)
- [ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
- [ADR-0022](ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)

## Related Documents

- [DOMAIN-007 Architecture](../platform/domains/risk/ARCHITECTURE.md)
- [DOMAIN-007 Contracts](../platform/domains/risk/CONTRACTS.md)
- [Intraday WO-13 V1](../products/intraday/KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md)
- [Intraday WO-14 V1](../products/intraday/KRONOS-INTRADAY-WO-14-DOMAIN-007-RISK-OBSERVATION-V1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-31 | 1.0 | Chief Architect / Sponsor, recorded by Codex | Freeze Intraday advisory Risk observation and preserve Swing Risk permission | APPROVED |
