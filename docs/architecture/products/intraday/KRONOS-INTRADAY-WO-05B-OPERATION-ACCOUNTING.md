# WO-05B — Actual Provider request and operation accounting

Status: IMPLEMENTED CANDIDATE — PUBLICATION REVIEW PENDING

Authority: Sponsor/EA WO-05B work order, 7 September 2026. Published baseline:
`ced25fd55c51b6686e25b6585d07db13a11ec1bc`. This implements the Current Authority
Manifest's approved accounting correction, preserving the WO-05A trusted-time
contract and the accepted 09:30 IST Opening assessment.

## Existing meanings retained

`DiscoveryRuntimeExecution.timeframe_fact_requests`, also retained in V2 replay
envelopes, means nominal evaluation-member count × four timeframe slots. It
never meant actual Provider activity. That field and historical identities are
unchanged. `source_operation_count` means attempted member-source operations.

`DiscoveryOperationResult.historical_request_count` remains the legacy source
counter: historical attempts only, excluding instrument calls, and possibly zero
when the source counter was not propagated on a global failure. Its existing
meaning is preserved, with an explicit API semantics label. It must not be used
as the operation's actual total. `probables_provider_request_count` remains zero;
Probables consumes the acquired Discovery evidence and does not acquire data.

## Exact counting rule

`actual_provider_requests` counts actual invocations of the existing DOMAIN-006
acquisition APIs by this operation: lease `historical_candles`, lease
`instrument_records`, and runtime `acquire_provider_instrument_master_records`.
Each call is counted immediately before invocation, including calls that raise.
Arguments are constructed first. Planned calls, returned candle rows, source
cache hits, restored facts, Browser GET, chart work and Review work do not count.

This is **acquisition API invocation/attempt accounting**, not physical SDK/HTTP
wire accounting. A call may be refused within DOMAIN-006 (for example revoked
capability or unresolved token) before network dispatch. Physical HTTP attempts
are explicitly `NOT_RETAINED`; no network count is inferred from API attempts.
The inspected adapter delegates to one SDK call per admitted acquisition and
introduces no retry loop in these paths. Every repeated boundary invocation is
counted; WO-05B adds no retry, request, caching, filtering or reordering.

One instance-local collector spans the consolidated master and factual source.
The master service receives a narrow product-owned delegate implementing its
existing Provider runtime protocol. It forwards unchanged properties and the
existing acquisition method. Shared Provider implementation is unchanged.
Telemetry clock/storage failure cannot suppress or repeat acquisition. Missing
first-invocation time remains `NOT_RETAINED` independently of a known request
count; a later invocation cannot fabricate the missing first timestamp. If an
accounting artifact cannot be sealed/retained, presentation reports
`NOT_RETAINED`, never a fabricated zero.

## Categories and benchmark subset

The following exclusive categories sum to the recorded actual total:

| Category | Existing invocation purpose |
| --- | --- |
| CURRENT_SESSION_CANDLE_REQUEST | Current-session 1H, 15M and 5M queries |
| PREVIOUS_SESSION_DAILY_REQUEST | Daily query used for governed previous-session context |
| PREVIOUS_SESSION_INTRADAY_REQUEST | Additional V2 previous-session 1H query |
| INSTRUMENT_BINDING_REQUEST | Consolidated master and exchange instrument-record reads |

The Daily query's existing requested range can extend into the current date;
its governed selected purpose remains previous-session Daily context. No query
range or selection rule changes.

`benchmark_subject_requests` is an overlapping subset for the exact governed
NIFTY member, not a fifth summable category. NIFTY is acquired in the population
loop regardless of phase. Its selected 15M evidence is reused in Opening mapping;
there is no additional per-equity benchmark acquisition. No quote/observation or
other acquisition path exists in this operation, so no unsupported categories
or inferred extra work are fabricated.

Successful exchange instrument records are reused from the existing source
cache. Failed lookup is not cached: later members can attempt another lookup.
All those attempts count; they are not a newly introduced retry policy.

## Populations and representative fixture

The current consolidated-master composition retains all 98 governed subjects,
including MCX. The NSE/index focus subset is projected from governed exchange
membership: currently 93, comprising 91 equities plus NIFTY and BANKNIFTY.
No NSE-only producer filter is activated. The focus is not a capacity limit.

Nominal evaluation members follow the existing operation composition: all
members when active-derivative resolution is configured, otherwise the existing
reconciliation's consumable members. Four slots per nominal evaluation member
remain planned coverage even on rejection or early failure.

The current V2 fixture has 98 nominal evaluation members / 392 slots. Its five
MCX bindings fail and 93 factual bundles succeed. Actual calls are 279 current
intraday + 93 previous Daily + 93 prior 1H + 2 instrument/binding = **467**.
NIFTY contributes five of those calls; they are not added again. Legacy at the
same completed boundary makes 374 calls, with no additional V2 prior-1H query.

A first/middle/last subject failing on its first historical request makes 463
calls in that fixture, while population and nominal coverage stay 98 / 392.
Consolidated-master failure makes one call and leaves all 98 members not reached.
Unavailable Provider context or WO-05A future admission makes zero calls.

Factual availability/failure counts reuse the Discovery coordinator's actual
bundle/member outcomes, including outcomes completed before a later run-write
failure. They are not Probables admission counts. A missing prior-1H mapping
can leave a valid mandatory Discovery bundle while making downstream Probables
unavailable. Prior method semantics are preserved.

## Timing and duration

| Time | Authority and retained meaning |
| --- | --- |
| Requested analysis | Original request boundary; never replaced with current time |
| Request receipt | Existing V2 provenance `received_at`; legacy receipt NOT_RETAINED |
| Trusted admission | Published WO-05A comparison instant |
| Operation start | Captured when the operation passes admission and takes its active slot |
| Provider acquisition start | Captured immediately before its first acquisition API invocation |
| Operation completion | Existing result completion instant; excludes subsequent receipt storage/response transport |
| Control dispatch/return | Existing V2 provenance start/completion stamps, exposed with distinct labels |
| Response sent | NOT_RETAINED; not inferred from control return |

The versioned operation record derives exact integer microseconds from aware UTC
start/completion instants. Finish-before-start, naive time and negative duration
fail validation. Unstarted admission has no start/duration; zero requests is
known, not missing. Fixed test clocks legitimately yield zero elapsed duration.
No Browser-render, analysis age or Chart Analyst turnaround is treated as
operation duration. No latency SLA or performance/trading consequence is added.

## Persistence, compatibility and presentation

`KRONOS-INTRADAY-DISCOVERY-OPERATION-ACCOUNTING / 1.0.0` seals counts, categories,
population, analysis/operation/run bindings and captured timing with integrity
identities. Records live under `native-discovery/operation-accounting/records`.
They are immutable and atomically retained without clobbering. A kind-specific
latest pointer is diagnostic projection only, not analytical/current-run authority.

V2 request provenance 1.3.0 links the exact accounting identity. POST/replay and
status load that exact artifact; no count is reconstructed from current code.
Legacy control exposes the same typed result and its restored last-operation
accounting. These are bounded API changes; Browser pages are not redesigned.
No new button, automatic GET acquisition or analytical Browser calculation exists.

Provenance versions 1.0.0, 1.1.0 and 1.2.0 remain readable under their original
integrity rules. Missing accounting identity returns NOT_RETAINED / null actual
requests and duration, distinct from a retained zero. No historical run or
request bytes are rewritten, and old records are not assigned new identities.
Exact accounting artifacts can also be loaded directly by identity without a
Provider call. Missing or tampered referenced records fail closed.

## Qualification and authority boundary

Deterministic tests independently spy the Provider fixtures and cover complete
operations, first/middle/last failures, each timeframe, prior and benchmark
failure, missing bindings, unavailable context, repeated failed lookups, future
admission, late persistence failure, immutable replay/restoration, legacy records,
zero versus unknown, time ordering, corruption, path containment, API output and
operation-local counters. Published/candidate acquisition traces and market
identities/evidence are compared in isolated fixtures. Full repository regression
is required before publication review.

No production Provider/OpenAI/broker operation, Refresh, chart write, Question
Pack, Answer import, runtime restart or production mutation is authorized.
No WO-05C/D, WO-06, VWAP, Statistics, WO-10 or WO-18 work is included. Publication
remains separately gated. This telemetry grants no candidate, Risk, trading,
liquidity, performance or execution authority.
