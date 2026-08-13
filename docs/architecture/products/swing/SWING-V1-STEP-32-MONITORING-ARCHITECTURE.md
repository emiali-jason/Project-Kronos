# Swing V1 Step 32 — Kite WebSocket Monitoring Architecture

**Status:** Approved as amended
**Version:** 1.1
**Approval date:** 2026-08-13
**Owner / approved by:** Chief Architect
**Operational authority:** SHADOW / VALIDATION ONLY

## Transport supersession

The previous 32H TradingView/Pine active-trade webhook transport is `RETIRED` for Swing V1. Public KRONOS webhook ingress is `NOT REQUIRED`. Historical approval is preserved in repository history; this amendment changes transport only and does not redesign Step 32, modify Pine, or create broker authority.

## Governed paths

```text
Kite Connect WebSocket market data
  → KRONOS Provider market-data adapter
  → instrument binding, normalization, continuity and provenance validation
  → DOMAIN-002 governed Observation
  → KR-380 Entry timing / KR-390 objective lifecycle
  → DOMAIN-009 lifecycle Event

Kite Connect WebSocket order update (optional)
  → KRONOS Provider order-evidence adapter
  → candidate + instrument + Sponsor Decision binding
  → Sponsor Position evidence only
```

One connection may carry both message classes, but their semantic paths never merge. Sponsor order outcomes cannot create Entry, Stop, Target, analytical invalidation, objective closure, or model history.

## Provider and DOMAIN-002 boundary

Kite market ticks are factual Provider input. The Provider adapter privately owns Kite instrument tokens and SDK objects, binds the current governed execution instrument, normalizes timestamps and prices, retains source/connection provenance, and detects sequence or continuity gaps where evidence permits. DOMAIN-002 remains sole owner of governed Observation. Neither layer determines Entry authorization, Stop/Target outcome, analytical invalidation, model closure, or Sponsor Decision.

## MCX and NSE execution instruments

MCX lifecycle crossings use only the governed current MCX execution contract. COMEX/NYMEX or another reference market cannot trigger lifecycle. NSE crossings use the explicitly governed NSE execution instrument; sector/index context cannot trigger another instrument. Provider Foundation owns current Provider mapping while Swing owns canonical analytical identity. Wrong instrument, exchange, product, candidate, or binding fails closed.

## Entry, Stop, Target, and Daily invalidation

Kite observations may establish factual boundary crossings. KR-380 alone applies the consecutive accepted-observation Entry rule and never infers a fill. KR-390 alone derives Stop/Target consequences. No new threshold or lifecycle state is introduced. Analytical invalidation is evaluated only from governed completed-Daily evidence plus immutable Step-31 invalidation condition; a tick cannot directly establish analytical invalidation.

## Disconnect, reconnect, and recovery

Disconnection records disconnect time, last accepted observation, affected subscriptions, reconnect time, and first post-reconnect observation. A gap never implies continuous observation, and the first post-reconnect tick cannot manufacture Entry/Stop/Target order. If the missing interval could contain lifecycle-order-sensitive evidence, the affected context is `RECONCILIATION_REQUIRED`.

An approved authoritative Kite/Provider historical source may reconstruct the interval only when source, timestamps, granularity, provenance, and ordering capability are retained. If authoritative order cannot be recovered, the model remains fail closed. OpenAI, TradingView screenshots, bar direction, and favourable or conservative assumptions cannot manufacture event order. Stop/Target ambiguity remains reconciliation; irrecoverable ambiguity closes as `OUTCOME_UNRESOLVED` under existing KR-390 semantics.

## Subscription lifecycle

Subscribe only to instruments needed for current responsibilities: Risk-permitted candidates waiting for Entry, active objective model trades, and applicable Sponsor LIVE/PAPER positions that require market observation. Remove a subscription when lifecycle monitoring ends unless another active KRONOS responsibility still needs it. The 98-instrument analytical universe does not authorize an uncontrolled 98-instrument active-monitoring subscription. Restart restores only validated active subscriptions after contract/state integrity checks.

## Optional order-update evidence

Kite order updates may provide factual order identity, status, filled quantity, average/fill information where authoritative, timestamps, instrument, and side. Evidence binds to Sponsor Position, candidate, instrument, and Sponsor Decision. One update is not assumed to be complete current order state where reconciliation is required. The objective model remains independent.

## Persistence and Browser

Durable owners retain candidate, judgment, Risk, Sponsor revisions, binding/subscription state, Entry outcome, objective model, Sponsor position, accepted/rejected Provider evidence, governed Observations, Events, and Audit evidence. Restart validates identity/integrity/version, restores required subscriptions, and compares deterministic reconstruction with stored state.

The Browser exposes operational meaning only: `KITE MONITORING: CONNECTED | RECONNECTING | CONTEXT INCOMPLETE`, and per affected trade `MONITORING OK | RECONCILIATION REQUIRED`. Raw ticks, Provider internals, credentials, and tokens are not displayed.

## Authority

The Kite connection is read/observe only. No `place_order`, `modify_order`, `cancel_order`, exit order, automatic Stop, or automatic Target exists. Broker execution authority is `NONE`; Pine dependency is `NONE`; public webhook dependency is `NONE`.
