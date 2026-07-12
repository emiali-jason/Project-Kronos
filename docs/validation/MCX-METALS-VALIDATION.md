# MCX Metals Validation Record

**Model:** MCX Metals
**Instruments:** Gold, Silver, Copper
**Record date:** 2026-07-10
**Status:** Current evidence record; live-event validation incomplete

This record separates source-level verification from TradingView compilation, visual validation, and live event observation. “Validated model” means the current architecture has been checked for the listed instruments within the evidence limits below. It does not mean that every possible market state has occurred live.

See the [Testing Protocol](TESTING.md), [Architecture Overview](../architecture/OVERVIEW.md), and [Engine Status Registry](../ENGINE_STATUS.md).

## Instruments and Reference Markets

| Execution instrument | Reference instrument | Mapping evidence | Current model status |
|---|---|---|---|
| MCX Gold futures | `COMEX:GC1!` | KR-250 source mapping and Gold root/description recognition | Supported |
| MCX Silver futures | `COMEX:SI1!` | KR-250 source mapping and Silver root/description recognition | Supported |
| MCX Copper futures | `COMEX:HG1!` | KR-250 source mapping and Copper root/description recognition | Supported |

COMEX contracts and continuous symbols are supporting reference charts. They are not MCX execution venues.

## Evidence Classes

| Class | Meaning |
|---|---|
| Statically verified | The current Pine source and its dependency path were inspected. No TradingView runtime behavior is implied. |
| Compiled in TradingView | The exact source revision compiled in TradingView without errors. This requires a dated validation log entry. |
| Visually validated | Panel/plot behavior was observed on the named symbol and timeframe. A screenshot or dated observation should be retained. |
| Live-event validated | The actual event occurred on a confirmed live/replay bar and its transition, persistence, or alert delivery was observed. |

## Current Validation Evidence

| Area | Static verification | TradingView compile evidence | Visual evidence | Live-event evidence | Notes |
|---|---|---|---|---|---|
| Asset mapping | Verified for Gold, Silver, Copper and COMEX roots GC/SI/HG | No durable compile artifact stored in repository | Prior engine validation is referenced by source/history; no screenshot stored here | Not required for mapping | Re-run on active MCX contracts and COMEX continuous/dated contracts before release. |
| Reference-symbol safety | Verified: empty/`UNKNOWN` references are guarded and reference charts use the chart symbol fallback | No durable artifact stored | No retained screenshot | Not required | Confirm no `Invalid symbol: UNKNOWN` runtime error across the symbol matrix. |
| CPR mapping | Verified: selected reference timeframe feeds prior completed H/L/C and all CPR/pivot outputs | Source contract records legacy Auto-mode validation; no compile log stored here | Auto-mode comparison was recorded in source comments; no comparison image stored here | Not required | KR-280 contains two version labels that need metadata reconciliation. |
| KR-370 decision states | Verified: direction/readiness states and exclusive public flags exist | No durable artifact stored | Source header records validation on Copper, Silver, Gold | Not every state observed | Validation applies to KR-370 ownership, not to every possible sequence. |
| KR-380 execution timing | Verified: only BUY READY/SELL READY can form confirmed execution states | No durable artifact stored | Repository history records Copper/Gold/Silver validation; no screenshot stored here | BUY NOW/SELL NOW coverage is incomplete | Source header still says v0.1.0 FOUNDATION while history describes v1.0 Frozen. |
| MCX-only confirmed triggers | Verified: MCX, intraday, 60-minute context plus `barstate.isconfirmed` gates final triggers | No durable artifact stored | No retained screenshot | Not every BUY/SELL event observed | COMEX/NYMEX reference charts cannot satisfy the MCX 1H execution gate. |
| Self-contained blocker display | Verified: KR-380 blocker queue feeds KR-705 Need/Next/Then on MCX 1H | No durable artifact stored | Prior visual validation is not retained as an artifact | Not applicable | Revalidate text truncation and ordering on all three metals. |
| KR-390 dormant state | Verified: no confirmed trigger leaves the model in NO TRADE; invalid data cannot start a valid trade | No durable artifact stored | No retained screenshot | Dormant state should be observed in replay/live validation | This does not validate HOLD/PROTECT/TRAIL/EXIT transitions. |
| BUY/SELL alert setup | Verified: exactly two alert conditions consume KR-380 BUY/SELL event edges | No durable artifact stored | Alert-condition availability not captured | Push delivery not yet evidenced | TradingView alert creation and mobile push remain user-configured. |

## Confirmed Architectural Checks

- Gold uses `COMEX:GC1!`, Silver uses `COMEX:SI1!`, and Copper uses `COMEX:HG1!`.
- Reference requests are protected from empty and `UNKNOWN` placeholders.
- COMEX/NYMEX reference charts cannot produce executable MCX triggers.
- BUY NOW and SELL NOW require confirmed MCX 1H execution context.
- KR-380 does not independently choose bullish or bearish direction.
- KR-390 starts only from confirmed KR-380 BUY/SELL outputs.
- KR-400 defines only BUY NOW and SELL NOW alert events and places no order.

## Validation Still Required

The following must not be described as fully validated until dated evidence is captured:

- every BUY NOW and SELL NOW transition;
- repeated-bar suppression after a trigger event;
- EXTENDED and FAILED final states across all three metals;
- KR-390 HOLD, PROTECT, TRAIL, EXIT, and INVALIDATED transitions;
- non-loosening managed stops across a full model-trade lifecycle;
- actual TradingView alert firing and mobile push delivery;
- chart reload/replay persistence expectations;
- behavior during illiquid, missing-volume, rollover, and session-boundary conditions.

## Release Evidence Required

Before a release claims MCX Metals validation, attach or reference:

1. the exact Git commit;
2. TradingView compile result and warning count;
3. one completed validation matrix per metal;
4. screenshots of KR-705 on MCX 1H and supporting reference contexts;
5. replay/live observations for every event claimed as validated;
6. alert creation and delivery evidence if alert delivery is part of the claim.

Use the reusable log in [TESTING.md](TESTING.md).
