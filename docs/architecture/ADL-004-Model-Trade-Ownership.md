# ADL-004 - Model Trade Ownership

**Document ID:** ADL-004
**Title:** Model Trade Ownership
**Document Family:** Legacy Architecture Decision Log
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Not stated
**Classification:** Legacy Architecture Decision Log
**Owner:** Not stated
**Prepared By:** Not stated
**Review Authority:** Not stated
**Repository Location:** `docs/architecture/ADL-004-Model-Trade-Ownership.md`
**Date:** 2026-07-10

## Context

KR-380 can confirm LONG_ENTRY_TRIGGERED or SHORT_ENTRY_TRIGGERED even when the user does not personally enter. If trade management depended on a user's unrecorded personal action, KRONOS could not evaluate its own decisions consistently or maintain an objective management state. Historical KR-380 Version 1 records used BUY NOW / SELL NOW for these entry-timing outcomes and retain that historical meaning.

The current Pine implementation has no broker-position or personal-fill interface.

## Decision

**KR-390 manages the objective KRONOS model trade independently of whether the user personally entered.**

A confirmed current KR-380 Version 2 LONG_ENTRY_TRIGGERED or SHORT_ENTRY_TRIGGERED event may create one KRONOS model trade. A KR-370 analytical BUY NOW / SELL NOW record is invalid at this boundary. KR-390 then maintains that model until EXIT or INVALIDATED according to its public contract. Historical Version 1 restoration may preserve an already-recorded model but cannot create a new current model trade.

## Model Trade Versus Personal Position

| KRONOS model trade | Personal position |
|---|---|
| Starts from a confirmed KR-380 event | Starts only when the user or broker actually executes |
| Uses the confirmed MCX 1H trigger-bar close as a model price | Uses the broker fill price |
| Uses KR-390A model structure references | May use user-selected risk and order rules |
| Persists objectively inside KRONOS | Depends on personal action, quantity, and broker state |
| Supports system validation and consistent panel state | Requires a future personal-position layer |

The model entry, stops, and targets are analytical references. They are not broker instructions.

## Objective Lifecycle

```text
NO TRADE
  -> confirmed LONG_ENTRY_TRIGGERED / SHORT_ENTRY_TRIGGERED
  -> HOLD
  -> PROTECT
  -> TRAIL
  -> EXIT

Invalid entry/stop data -> INVALIDATED
```

KR-390 ignores new triggers while a model trade is active and does not silently reverse direction.

## Why Objectivity Matters

An objective model trade allows KRONOS to:

- evaluate whether its confirmed entries would have progressed or failed;
- preserve consistent management output for every trader;
- validate stop and state transitions without personal execution ambiguity;
- support future strategy-performance research without rewriting historical decisions around a user's discretionary fills.

This is not a claim of profitability and is not broker automation.

## Future Personal-Position Layer

A later layer may accept personal entry, quantity, broker fill, manual exit, or risk preferences. That layer must be separate from KR-390's objective model so personal actions do not mutate the canonical model history.

Until that layer exists, KR-705's trade-management display refers to the KRONOS model trade, not the user's account.

## Ownership Boundaries

- KR-370 owns analytical promotion and has no Entry Outcome or model-trade authority.
- KR-380 owns entry timing.
- KR-390 owns the post-trigger model state.
- KR-400 owns alerts.
- No current engine owns personal broker-position state.

See [ADR-0011](adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md), [Data Flow](DATA_FLOW.md), and [Engine Ownership](ENGINE_OWNERSHIP.md).
