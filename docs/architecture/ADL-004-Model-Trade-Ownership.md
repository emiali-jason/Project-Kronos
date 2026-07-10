# ADL-004 - Model Trade Ownership

**Status:** Approved
**Date:** 2026-07-10

## Context

KR-380 can confirm BUY NOW or SELL NOW even when the user does not personally enter. If trade management depended on a user's unrecorded personal action, KRONOS could not evaluate its own decisions consistently or maintain an objective management state.

The current Pine implementation has no broker-position or personal-fill interface.

## Decision

**KR-390 manages the objective KRONOS model trade independently of whether the user personally entered.**

A confirmed KR-380 BUY NOW or SELL NOW event may create one KRONOS model trade. KR-390 then maintains that model until EXIT or INVALIDATED according to its public contract.

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
  -> confirmed BUY NOW / SELL NOW
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

- KR-370 owns direction and readiness.
- KR-380 owns entry timing.
- KR-390 owns the post-trigger model state.
- KR-400 owns alerts.
- No current engine owns personal broker-position state.

See [Data Flow](DATA_FLOW.md) and [Engine Ownership](ENGINE_OWNERSHIP.md).
