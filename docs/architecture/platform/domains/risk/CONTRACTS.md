# Risk Contracts
Status: Approved for product-specific Swing V1 and Intraday V1 bounded contracts
Owner: Chief Architect
Version: 1.2

## KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1

One immutable result binds an exact current Native run, canonical instrument,
KR-370 source, UX-05 handoff, persisted Step-31 Trade Plan and digest,
Portfolio State cycle and digest, evaluation boundary, policy identity/version,
provenance, and integrity SHA.

States are `APPROVED`, `CONSTRAINED`, `REJECTED`, and `UNAVAILABLE` under
ADR-0013. It grants objective entry-timing permission only and owns no geometry,
quantity, Sponsor action, order, fill, or broker authority.

Under [ADR-0015](../../../adr/ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md),
`REJECTED` and `UNAVAILABLE` remain hard fail-closed results at every boundary
that requires Risk permission. `APPROVED` and `CONSTRAINED` remain permission
for objective timing only. Reason, constraint, and availability facts are
retainable observation evidence, but no result substitutes for a Sponsor
`LIVE`, `PAPER`, or `IGNORE` choice. Observation-phase contract expansion must
be separately versioned and must not reinterpret existing V1 records.

ADR-0016 prospectively permits an explicitly started, non-position Paper
Observation Track for an exact blocked `PAPER` decision. This does not change
`KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1`: Risk remains hard for Sponsor
Position and objective activation, and the Track receives no permission,
override, or bypass. The decision-time Risk identity and state are retained as
research evidence only.

## KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1

ADR-0023 commissions an immutable Intraday advisory observation bound to one
exact WO-13 Trade Plan, execution vehicle where required, instrument economics,
any used capital/portfolio/margin snapshots, evaluation boundary, methodology
`1.0.0`, provenance and integrity.

States are `RISK_OBSERVED`, `RISK_ALERT` and `RISK_UNAVAILABLE`.
`RISK_ALERT` is informational and remains dormant until a separate threshold
methodology is commissioned. `RISK_UNAVAILABLE` preserves truthful absence and
does not reject a trade. No state grants or denies WO-15 progression.

The contract may report structural and monetary Risk per unit, reference or
Sponsor-selected quantity loss at Stop, capital percentage, notional, open and
aggregate Risk and margin facts where authoritative. It owns no geometry,
execution-vehicle selection, final quantity, Entry timing, Sponsor choice,
position, order, fill or broker authority.

The Intraday contract is not a new version of the Swing permission result and
states must never be translated between the two families.
