# ADL-003 - Execution Context Adapters

**Status:** Approved
**Date:** 2026-07-10

## Context

KRONOS normally requires downstream engines to consume public outputs from prior engines. Execution timing and trade management occasionally require a narrow confirmed fact that is not exposed by an existing intelligence contract.

Duplicating the complete intelligence core for Daily, 4H, and 1H would increase script size, create inconsistent rules, and weaken ownership boundaries.

## Decision

**Narrow adapters may bridge low-level market data into execution engines without duplicating complete intelligence stacks.**

An adapter is an explicit, documented exception to strict prior-engine-output-only access. It may expose only the minimum fact required by its consumer.

## Current Adapters

| Adapter | Purpose | Narrow source access | Public adapter outputs | Consumer |
|---|---|---|---|---|
| KR-380A | Execution Context Adapter | Selected KR-260/270 reference Daily, 4H, 1H and MCX execution facts, plus established public direction/readiness context | Daily bullish/bearish permission and blocker; 4H acceptance/compression readiness and blocker; 1H momentum support and blocker; MCX 1H context readiness | KR-380 |
| KR-390A | Trade Management Execution Adapter | MCX 1H execution H/L/C and MCX execution-context readiness | Execution close, prior-five-completed-bar swing low/high, context readiness, stop readiness | KR-390 |

## Allowed Scope

An adapter may:

- read a narrowly identified lower-level dataset;
- calculate a small factual condition required by one consumer;
- use completed-bar indexing when the contract requires confirmed structure;
- expose explicit readiness and unavailable/blocker outputs;
- translate model dependencies into a stable public adapter contract.

## Prohibited Scope

An adapter must not:

- duplicate KR-300 through KR-370 across multiple timeframes;
- establish bullish or bearish trade direction;
- recreate trend, quality, compression, acceptance, momentum, opportunity, confidence, or decision scoring;
- issue BUY NOW/SELL NOW;
- manage trades or emit alerts unless that is the owning engine's responsibility;
- expose broad raw datasets merely for convenience;
- become an undocumented path around a frozen public contract.

## Public Contract Rule

The adapter's consumer must use the adapter's public outputs rather than its internal calculations. Other engines should not reach through an adapter to its low-level source data.

If multiple consumers begin needing the same fact, the team must decide whether that fact belongs in an existing engine's additive public contract or in a shared formal adapter. Repetition is not an acceptable default.

## Confirmed-Bar Safety

- KR-380A supplies context, while KR-380 owns final confirmed execution timing.
- KR-390A excludes the current execution bar from its swing reference.
- KR-390 owns confirmed model-trade state transitions and managed-stop enforcement.

The adapter must not use lookahead or future-confirmed values.

## Consequences

The adapter pattern keeps the intelligence core generic and prevents three full timeframe-specific copies. The cost is that every exception must be documented, small, validated, and visible in the ownership registry.

See [Engine Ownership](ENGINE_OWNERSHIP.md) and [ADL-002](ADL-002-MCX-Self-Contained-Execution.md).
