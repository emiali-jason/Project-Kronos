# Risk Contracts
Status: Approved for Swing V1 bounded contract
Owner: Chief Architect
Version: 1.1

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
