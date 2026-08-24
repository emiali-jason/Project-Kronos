# KRONOS Swing Sponsor Observation Decision V1

**Status:** Approved implementation contract

**Version:** 1

**Governing authority:** ADR-0015 / SPONSOR-OBS-01

**Product:** KRONOS Swing V1

## Purpose

This contract records an explicit Sponsor `LIVE`, `PAPER`, or `IGNORE`
observation-phase judgment against one exact current `BUY NOW` or `SELL NOW`
evidence cycle. It does not activate a position and carries no Risk, execution,
monitoring, fill, P&L, or broker authority.

The canonical separation is:

```text
Sponsor observation decision = what the Sponsor chose
Activation disposition       = whether existing position authority activated
```

## Contract family

- `KRONOS-SWING-SPONSOR-DECISION-SNAPSHOT-V1` preserves the immutable
  decision-time facts.
- `KRONOS-SWING-SPONSOR-OBSERVATION-DECISION-V1` preserves the Sponsor choice,
  optional bounded reason, warning acknowledgement, and exact snapshot binding.
- `KRONOS-SWING-SPONSOR-ACTIVATION-DISPOSITION-V1` preserves the independently
  determined activation outcome.

All three records are append-only, integrity-bound, restart-safe, and governed
by `SWING-SPONSOR-OBSERVATION-DECISION-V1` Version 1.

## Choices

The only Sponsor choices are:

- `LIVE`
- `PAPER`
- `IGNORE`

`LIVE` and `PAPER` may be recorded against GREEN, AMBER, or RED Step-31
evidence. RED requires explicit warning acknowledgement. `IGNORE` requires no
warning acknowledgement and never creates a Sponsor Position.

## Activation dispositions

- `ACTIVATED`
- `BLOCKED_RISK_REJECTED`
- `BLOCKED_RISK_UNAVAILABLE`
- `BLOCKED_CONSTRAINT`
- `BLOCKED_MISSING_VALID_PLAN`
- `NOT_APPLICABLE_IGNORE`

`ACTIVATED` is factual evidence that the unchanged existing Sponsor Decision
V0 and Sponsor Position V0 path completed. The observation contract cannot
produce activation itself. DOMAIN-007 `REJECTED` and `UNAVAILABLE` remain hard
activation blockers. A blocked decision is never activated automatically after
later evidence changes.

## Decision-time snapshot

The snapshot binds the exact run, instrument, Native assessment, direction,
KR-370 identity/state/K1-K5/hard gate, V3/V3.1 evidence, Step-31 evidence,
geometry availability/status/severity/warnings and factual values, conventional
Trade Plan when available, DOMAIN-007 identity/state, execution context, and
applicable MCX supporting-context identity. Unavailable and invalid values are
preserved exactly and are never repaired retrospectively.

## Trust and currentness

Decision recording fails closed for foreign, stale, superseded, malformed,
corrupt, or integrity-mismatched run/instrument/assessment/KR-370/Step-31
lineage. Poor geometry is not a trust failure. Repeated identical submission is
idempotent; a different choice against the finalized evidence is rejected.

## Historical and downstream isolation

Sponsor Decision V0, Sponsor Position V0, historical Trade Plans, Risk records,
KR-380, KR-390, lifecycle, and Step-33 records retain their original meanings.
The new family does not migrate or reinterpret them. No decision mutates
KR-370, Step-31, DOMAIN-007, ECPC, KR-380, or KR-390.

## JOURNAL-OBS-01 read-only handoff

The read-only handoff exposes snapshot and decision identities, choice,
activation disposition, Step-31 evidence, optional conventional Trade Plan,
Risk identity/state, KR-370 identity, run/instrument/assessment, and optional
Sponsor Position identity. It creates no ledger or research conclusion.

The persistence API supports independent retrieval by Sponsor choice,
activation disposition, and Step-31 severity without Browser scraping.

## Explicit prohibitions

- no autonomous trading;
- no broker order, modify, or cancel authority;
- no fabricated position, fill, P&L, or actual R;
- no monitoring for a blocked or ignored decision;
- no Telegram event solely for decision recording;
- no automatic later activation of a blocked decision.
