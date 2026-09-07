# WO-05A — Trusted analysis-time admission

Status: IMPLEMENTED CANDIDATE — PUBLICATION REVIEW PENDING

Authority: Sponsor/EA WO-05A Trusted Analysis-Time Boundary work order,
7 September 2026. Baseline: `ee651ab362d12eb63d1d4fc2235908510b4b4aa7`.
This bounded correction implements the published Current Authority Manifest's
`05-trusted-time` policy. It does not revise the historical WO-05 operational
invocation or control decisions.

## Confirmed defect

In isolated fixtures, trusted time 09:29 IST and requested time 09:30 IST
previously reached 465 mocked historical acquisitions through V2 and 186
through the legacy operation. The legacy fixture subsequently failed refresh
state persistence; acquisition had already occurred. The unchanged candle
primitive excludes the 09:15–09:30 candle at 09:29 and selects it at 09:30.
This is a validation/trust-boundary defect, not a production Provider incident.

## Admission contract

`intraday.analysis_time.admit_analysis_time` samples the injected trusted clock
once and compares timezone-aware UTC instants. A future boundary rejects with
`OBSERVATION_BOUNDARY_FUTURE`, without numerical tolerance. Equality and earlier
boundaries remain eligible for existing downstream rules. The requested
boundary, timezone and historical chronology remain unchanged.

The production default clock is UTC wall time. Injection is instance-local.
Naive requests fail with `OBSERVATION_BOUNDARY_INVALID`; an unavailable, naive
or failing trusted clock raises typed `TRUSTED_TIME_UNAVAILABLE`. There is no
fallback to client time or system-local timezone.

`IntradayDiscoveryOperationService.execute` checks admission before Provider
context verification, instrument-master acquisition, leases or factual-source
creation. Its composed Native Discovery service receives the captured admission
instant. Direct `IntradayNativeDiscoveryService.execute` independently applies
the same guard before member source calls, including invocation through
`IntradayDiscoveryApplication.run_discovery`.

Protected entry paths:

- `/control/intraday-discovery/v2` → V2 control → V2 operation;
- `/control/intraday-discovery` → legacy control → legacy operation;
- either operation service invoked directly;
- Native Discovery service and its application entry point invoked directly.

A future operation returns a failed, unstarted observation-boundary result with
zero acquisition counts and no Discovery/Probables run or current-pointer write.
V2 maps this to a typed REJECTED request outcome, not market-data unavailability.
The legacy control exposes the same typed failure through its existing failure
transport. A completed identical operation/request replay returns its retained
result without new admission or acquisition.

## Time evidence and compatibility

Requested analysis, server receipt, trusted admission, operation start and
operation finish remain separate. V2 provenance 1.2.0 adds the trusted admission
time to existing integrity-protected request evidence. Future rejection retains
both compared times, no operation start, and no resulting market evidence.
This is a bounded admission-evidence extension, not WO-05B request accounting.

Existing provenance 1.0.0 and 1.1.0 retain their original identity/serialization
rules, restore without fabricated admission time, and are not rewritten.
Discovery and Probables run identities remain independent of admission time;
their analysis boundaries retain the requested historical chronology.

## Qualification and limits

Focused fixtures cover strict future rejection (including one microsecond),
equality, 13:00/10:00 history, equivalent UTC/IST, invalid clocks/naive time,
all entry paths, zero acquisition sentinels, 15M premature completion,
DOMAIN-008-derived 5M/1H/Daily edges, concurrent instance clocks, historical
identity, replay, old provenance restoration and admission-time tampering.
Existing Provider, market, candle, application and Browser regression remain
required, as does full repository regression before publication review.

No candle endpoint, session, previous-session, NIFTY relationship, Probables
methodology, MCX policy, Provider authority or broker authority is changed.
No WO-05B accounting, WO-05C runtime-build identity, WO-05D or WO-06 work is
included. Production runtime acceptance and publication require later authority.

## Exact 09:30 IST Opening acceptance

The Sponsor clarification preserves the first lawful Opening assessment at
09:30 IST: requested 09:30 equals trusted 09:30 and passes time admission.
The 09:15–09:30 15M candle and the 09:15–09:20, 09:20–09:25 and 09:25–09:30
5M constituents are completed evidence. The forming current-session 1H candle
is excluded; the existing governed prior completed 1H context remains allowed.
Opening is not deferred until current-session 1H completion. A real V2 operation
using isolated Provider doubles qualifies this exact combination through its
persisted OPENING mappings. Assessment does not guarantee a Probable outcome;
existing methodology remains responsible for that determination.
