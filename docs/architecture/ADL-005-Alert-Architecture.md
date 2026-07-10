# ADL-005 - Alert Architecture

**Status:** Approved
**Date:** 2026-07-10

## Context

TradingView alerts are useful only when they preserve the same ownership and confirmation rules as KR-380. Alert logic must not become a second decision or timing engine, and a persistent trigger state must not generate repeated notifications.

## Decision

**KR-400 owns confirmed BUY NOW and SELL NOW TradingView alert events.**

The current scope contains exactly two alert types:

1. KRONOS BUY NOW;
2. KRONOS SELL NOW.

No alerts are created for NO TRIGGER, FORMING, EXTENDED, FAILED, WATCH, READY, HOLD, PROTECT, TRAIL, or EXIT.

## Trigger Source

- The BUY alert consumes the KR-380 public BUY output.
- The SELL alert consumes the KR-380 public SELL output.
- KR-400 does not calculate trend, direction, acceptance, compression, confidence, momentum, opportunity, entry timing, stops, targets, or trade management.

## Event-Edge Behavior

An alert event is true only on the transition into BUY NOW or SELL NOW.

```text
BUY state false -> true  = one BUY alert event
BUY state true  -> true  = no duplicate event
SELL state false -> true = one SELL alert event
SELL state true  -> true = no duplicate event
```

The current implementation uses the prior public trigger value to suppress repeated events.

## Execution Restriction

KR-400 inherits KR-380's execution contract:

- MCX chart;
- 1H timeframe;
- confirmed bar;
- valid KR-370 READY direction;
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

Validate BUY and SELL separately:

- one event on the confirmed transition;
- no duplicate while state persists;
- no event from any non-BUY/SELL state;
- no event on reference charts;
- TradingView alert creation is available;
- delivery evidence is recorded separately from static source verification.

See [Testing Protocol](../validation/TESTING.md) and [MCX Metals Validation](../validation/MCX-METALS-VALIDATION.md).
