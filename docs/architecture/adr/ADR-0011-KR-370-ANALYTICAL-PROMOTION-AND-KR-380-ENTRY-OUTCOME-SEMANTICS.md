# ADR-0011 — KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics

## Metadata

- **ADR Number:** ADR-0011
- **Decision Identity:** KR-370-ADR-01
- **Title:** KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics
- **Status:** APPROVED
- **Date:** 2026-08-21
- **Decision Owner:** Chief Architect
- **Proposed By:** Sponsor / Swing Engineering Architect
- **Reviewers:** Chief Architect
- **Approved By:** Chief Architect
- **Decision Scope:** Platform / Swing Product / Interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved in repository
- **Engineering Status:** Architecture and contracts activated; KR-370 V1 classifier implementation not started by this ADR

## Context

The historical KRONOS architecture used the literals `BUY NOW` and `SELL NOW`
for final KR-380 entry-timing outcomes. KR-370 stopped at `BUY READY` or
`SELL READY`. The Sponsor has approved a different current analytical language:
KR-370 must describe whether all governed analytical-promotion criteria are
satisfied now, while KR-380 must continue to own the separate downstream entry
timing and Entry Outcome.

Reusing one unqualified literal for both meanings would allow an analytical
classification to be mistaken for an Entry Outcome, model-trade input, alert
event, Sponsor position, or broker action. This decision separates those
meanings by owner, state family, contract version, and event identity.

## Previous ownership

Before this ADR:

- KR-370 owned direction and readiness through `AVOID`, `WAIT`, `WATCH LONG`,
  `WATCH SHORT`, `BUY READY`, and `SELL READY`.
- KR-380 consumed KR-370 readiness and the governed Entry Execution Context,
  owned final entry timing, and published `NO TRIGGER`, `FORMING`, `BUY NOW`,
  `SELL NOW`, `EXTENDED`, and `FAILED`.
- KR-390 and KR-400 consumed confirmed KR-380 `BUY NOW` / `SELL NOW` outcomes.

Those KR-380 literals retain that meaning only for historical KR-380 Entry
Outcome Version 1 records.

## Decision

### KR-370 analytical-promotion ownership

KR-370 owns the current Sponsor-facing analytical-promotion state family:

- `BUY NOW`;
- `SELL NOW`;
- `BUY READY`;
- `SELL READY`;
- `POTENTIAL BUY SETUP`;
- `POTENTIAL SELL SETUP`;
- `NO SETUP`.

KR-370 `BUY NOW` or `SELL NOW` means only that all governed KR-370
analytical-promotion criteria are satisfied at the bound evaluation point. It
has no broker, execution, Risk-approval, Sponsor-decision, position, fill,
Entry Outcome, alert-event, or model-trade authority.

Only exact current KR-370 `BUY NOW` or `SELL NOW` may make the bound analytical
subject eligible for the existing governed Step-31 path. `BUY READY`,
`SELL READY`, either potential state, and `NO SETUP` do not enter Step 31.

### KR-380 entry-timing ownership

KR-380 retains final entry timing and Entry Outcome ownership. The current
KR-380 public state family is:

- `NO_TRIGGER`;
- `FORMING`;
- `LONG_ENTRY_TRIGGERED`;
- `SHORT_ENTRY_TRIGGERED`;
- `EXTENDED`;
- `FAILED`.

The Sponsor-facing labels for the two triggered states are:

- `ENTRY TRIGGERED — LONG`;
- `ENTRY TRIGGERED — SHORT`.

KR-380 remains the sole authorized consumer of the Entry Execution Context. It
continues to require the current immutable candidate, Step-31 geometry, Risk
permission, monitoring binding, governed Observation, Execution Context
qualification, and final timing facts required by approved Swing architecture.
It cannot infer direction, change geometry, infer a fill, or bypass Risk.

### Analytical-versus-entry distinction

The current contracts use distinct identities:

| Meaning | Owner | State family | Contract |
| --- | --- | --- | --- |
| Current analytical promotion | KR-370 / DOMAIN-003 Validation | `KR370_ANALYTICAL_PROMOTION` | `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1` |
| Current Entry Outcome | KR-380 / DOMAIN-004 Execution | `KR380_ENTRY_OUTCOME` | `KRONOS-KR-380-ENTRY-OUTCOME-V2` |
| Historical Entry Outcome | KR-380 / DOMAIN-004 Execution | `KR380_ENTRY_OUTCOME` | `KRONOS-KR-380-ENTRY-OUTCOME-V1` |

No consumer may route a state by display text alone. Owner identity, state-family
identity, contract identity, contract version, and bound source identity are
mandatory routing inputs.

## Authority boundaries

This decision preserves the following ownership:

```text
Native Discovery
  -> candidate discovery and thesis
V3 Review
  -> governed machine and independent visual evidence
KR-370
  -> analytical promotion classification
Step 31
  -> Entry, Stop, Target, invalidation, and R:R geometry
DOMAIN-007 Risk
  -> Risk permission and constraints
KR-380
  -> entry timing and Entry Outcome
KR-390
  -> objective model lifecycle
Sponsor Decision
  -> LIVE / PAPER / IGNORE where governed
Broker execution
  -> no new authority
```

KR-370 analytical `BUY NOW` / `SELL NOW` never bypasses Step 31, Risk, or
KR-380. Step 31 remains the geometry owner; KR-380 consumes but cannot change
that geometry. Risk remains independent and cannot be inferred from KR-370.

## Current flow

```text
Native PROBABLE
  -> V3 Review
  -> KR-370 analytical promotion

KR-370 NO SETUP / POTENTIAL / READY
  -> analytical only

KR-370 BUY NOW / SELL NOW
  -> eligible for Step 31
  -> immutable geometry
  -> DOMAIN-007 Risk
  -> KR-380 entry timing
  -> LONG_ENTRY_TRIGGERED / SHORT_ENTRY_TRIGGERED
  -> governed downstream lifecycle
```

## Historical compatibility

Historical `KRONOS-KR-380-ENTRY-OUTCOME-V1` records remain readable and
restorable with their original `BUY NOW` / `SELL NOW` entry-timing meaning.
They are never reclassified as KR-370 analytical promotion records.

Current producers must not emit Version 1 KR-380 outcomes. Historical
restoration may reconstruct already-recorded consequences but must not create a
new current event, model trade, Sponsor position, or broker action.

## Contract migration

The migration is fail closed:

1. Current KR-370 records use `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1`.
2. Current KR-380 records use `KRONOS-KR-380-ENTRY-OUTCOME-V2`.
3. Historical KR-380 Version 1 records remain read-only/restorable.
4. KR-390 accepts a new Entry Outcome only from KR-380 Version 2 in
   `LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED`.
5. KR-400 accepts a new entry-alert source only from the same KR-380 Version 2
   triggered states and their distinct entry-trigger event identities.
6. KR-370 records are invalid at the KR-390 and KR-400 Entry Outcome boundaries
   even when their display labels contain `BUY NOW` or `SELL NOW`.
7. Unsupported, missing, mismatched, stale, or ambiguous owner/state-family/
   version binding produces no progression.

The Version 2 KR-380 Entry Outcome changes terminology only. Execution Context,
Risk, geometry, timing, ordering, and fail-closed gates are unchanged.

## KR-400 and event safety

Current KR-400 entry alerts consume only the governed KR-380 Version 2 Entry
Outcome transition into `LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED`.
Current event identities and labels are distinct from KR-370 promotion:

- `KR380_LONG_ENTRY_TRIGGERED` / `ENTRY TRIGGERED — LONG`;
- `KR380_SHORT_ENTRY_TRIGGERED` / `ENTRY TRIGGERED — SHORT`.

No KR-370 analytical transition creates a KR-400 entry alert. New KR-370
notifications require a separate UX-10 authorization.

## Prohibited consequences

This ADR does not:

- implement the KR-370 five-criterion classifier;
- change E01, E02, E03, Native Discovery, V3 Review, or Pine;
- create or modify Entry, Stop, Target, invalidation, or R:R geometry;
- approve Risk;
- record a Sponsor LIVE/PAPER/IGNORE decision;
- create a Sponsor position or objective model trade;
- infer a fill, quantity, order, or broker action;
- authorize Telegram, UX-10, or a new watcher;
- change Intraday product behavior.

## Rollback and fail-closed expectations

Rollback must restore a coherent contract family and all of its consumers. A
mixed deployment in which KR-370 analytical `BUY NOW` is routed to a historical
KR-380 consumer is prohibited. If compatible owner, family, and version
bindings cannot be established, Step 31, Risk, KR-380, KR-390, and KR-400 do
not progress.

Persisted records are immutable. Rollback never rewrites Version 1 history and
never relabels Version 2 history.

## Supersession

This ADR supersedes only the clauses that:

- reserve the literals `BUY NOW` / `SELL NOW` exclusively to KR-380;
- prohibit KR-370 from publishing those literals as analytical promotion;
- name current KR-380 triggered outcomes or KR-400 entry alerts with those
  literals;
- route current KR-390 or KR-400 behavior from unversioned `BUY NOW` /
  `SELL NOW` text.

It does not supersede KR-380 final entry-timing ownership, the KR-380A provider
boundary, KR-380's sole-consumer status, Step-31 geometry, Risk ownership,
KR-390 lifecycle ownership, Sponsor-decision separation, or broker prohibitions.

Affected clauses include PLATFORM-000 CA-018 and Existing Authority; ADR-006
Decision, Architecture, KR-370, and KR-380 ownership clauses; ENGINE_OWNERSHIP
KR-370/KR-380/KR-400 state-name clauses; DATA_FLOW Decision, Execution Timing,
Model Trade, Alert, and display clauses; PP-007 KR-380 state naming; ECPC-001
KR-380 behavior mapping; ADL-004 model-entry naming; and ADL-005 alert naming.

ADR-006 remains an approved historical architecture record and is superseded
only for the affected terminology and analytical-promotion ownership clauses.

## Consequences

### Positive

- Sponsor analytical readiness is expressed directly without granting execution.
- Entry timing remains a separate, exact, Risk-gated authority.
- Historical and current records are unambiguous.
- KR-390 and KR-400 cannot consume analytical promotion accidentally.

### Cost

- Current Entry Outcome and alert consumers require version-aware migration.
- Presentation must always display the owning state family.
- Historical restoration must support both Entry Outcome versions.

## Validation requirements

- KR-370 analytical promotion has no execution authority.
- Current KR-380 states use `LONG_ENTRY_TRIGGERED` and
  `SHORT_ENTRY_TRIGGERED`.
- Historical KR-380 `BUY NOW` / `SELL NOW` remains readable.
- KR-370 cannot enter KR-390 or trigger KR-400 entry alerts.
- KR-380 Entry Outcome remains downstream of Step 31, Risk, and Execution
  Context gates.
- Step-31, Risk, Sponsor, broker, Intraday, and Pine authority remain unchanged.

## Supersedes

- Affected clauses of [ADR-006](ADR-006-Execution-Context-Provider-Architecture.md)
- Affected state-name and ownership clauses identified in this ADR

## Superseded By

None.

## Related documents

- [PLATFORM-000](../platform/PLATFORM-000-CONSTITUTION.md)
- [Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Data Flow](../DATA_FLOW.md)
- [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [KR-370/KR-380 state-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [Swing V1 Step-32 Platform amendments](ADR-SWING-STEP-32-PLATFORM-AMENDMENTS.md)

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-21 | 1.0 | Chief Architect / Engineering activation | Initial approved ownership and terminology supersession | APPROVED |
