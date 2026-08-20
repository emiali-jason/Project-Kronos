# ADL-005 - Alert Architecture

**Document ID:** ADL-005
**Title:** Alert Architecture
**Document Family:** Legacy Architecture Decision Log
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Not stated
**Classification:** Legacy Architecture Decision Log
**Owner:** Not stated
**Prepared By:** Not stated
**Review Authority:** Not stated
**Repository Location:** `docs/architecture/ADL-005-Alert-Architecture.md`
**Date:** 2026-07-10

## Context

TradingView alerts are useful only when they preserve the same ownership and confirmation rules as KR-380. Alert logic must not become a second decision or timing engine, and a persistent trigger state must not generate repeated notifications.

## Decision

**KR-400 owns confirmed KR-380 LONG_ENTRY_TRIGGERED and SHORT_ENTRY_TRIGGERED TradingView alert events.**

The current scope contains exactly two alert types:

1. KRONOS ENTRY TRIGGERED — LONG;
2. KRONOS ENTRY TRIGGERED — SHORT.

No entry alerts are created for KR-370 analytical BUY NOW / SELL NOW, NO SETUP, POTENTIAL, READY, or any KR-380 NO_TRIGGER, FORMING, EXTENDED, or FAILED state. A new KR-370 notification family requires separate UX-10 authority.

## Trigger Source

- The long alert consumes only a versioned KR-380 LONG_ENTRY_TRIGGERED transition with event identity KR380_LONG_ENTRY_TRIGGERED.
- The short alert consumes only a versioned KR-380 SHORT_ENTRY_TRIGGERED transition with event identity KR380_SHORT_ENTRY_TRIGGERED.
- KR-370 analytical promotion is not an entry-alert source, regardless of display text.
- KR-400 does not calculate trend, direction, acceptance, compression, confidence, momentum, opportunity, entry timing, stops, targets, or trade management.

## Event-Edge Behavior

An alert event is true only on the transition into LONG_ENTRY_TRIGGERED or SHORT_ENTRY_TRIGGERED.

```text
LONG_ENTRY_TRIGGERED false -> true  = one long-entry alert event
LONG_ENTRY_TRIGGERED true  -> true  = no duplicate event
SHORT_ENTRY_TRIGGERED false -> true = one short-entry alert event
SHORT_ENTRY_TRIGGERED true  -> true = no duplicate event
```

The current implementation uses the prior public trigger value to suppress repeated events.

## Execution Restriction

KR-400 inherits KR-380's execution contract:

- MCX chart;
- 1H timeframe;
- confirmed bar;
- exact current KR-370 analytical promotion, Step-31 geometry, and Risk permission;
- completed KR-380 timing requirements.

COMEX/NYMEX reference charts cannot fire executable MCX alerts.

## Delivery and Automation Boundary

KR-400 defines TradingView alert conditions. The trader must create and enable the alert in TradingView.

- TradingView delivers desktop, email, webhook, or mobile notifications according to the user's settings.
- Mobile push depends on TradingView notification configuration.
- KRONOS does not place a broker order.
- KRONOS does not execute or manage a live account position.
- A webhook configured by a user is outside the current KRONOS broker-automation contract.

## Validation Requirements

Validate long-entry and short-entry events separately:

- one event on the confirmed transition;
- no duplicate while state persists;
- no event from any non-BUY/SELL state;
- no event on reference charts;
- TradingView alert creation is available;
- delivery evidence is recorded separately from static source verification.

See [Testing Protocol](../validation/TESTING.md) and [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).

## Historical compatibility

Historical KR-380 Version 1 BUY NOW / SELL NOW alert records retain their
original entry-timing meaning and remain readable. Current producers and KR-400
use only the Version 2 Entry Outcome names. Historical restoration does not
emit a new current alert. See [ADR-0011](adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md).
