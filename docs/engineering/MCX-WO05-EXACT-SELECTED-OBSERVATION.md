# MCX-WO-05 exact selected-future observation

Status: Proposed engineering candidate; exact-byte owner reviews and separate release authorization required.
Base: dc2a7f40bf29c4ad9ea56d87634e8e8193450469.
Authority: Sponsor MCX-WO-05 bounded exact-selected-contract observation correction, 7 October 2026; existing ADR-0010 Provider custody, ADR-0030 connection governance and ADR-0059 maintenance ownership.

## Bounded operation

One explicit same-origin POST `/swing/mcx-v1/observe` accepts an operation identity, retained run, family, exact selection integrity and publication hash. It validates the actual SUCCEEDED run/generation, immutable selection and governed expiry eligibility through the installed Swing composition. The historical authenticated master establishes the selected identity only. The operation retrieves current normalized MCX records and current typed Provider instrument assertions through the existing authenticated capability. Exact expiry/record and unambiguous symbol/token/tick/lot bindings must agree. No family resolver or silent roll is used.

The installed shared monitoring hub supplies the temporary reference-counted owner and applied subscription. `MonitoringSubscriptionEvidence.provider_instrument_token` is additive and optional for existing consumers; the Kite adapter supplies its actual applied record-to-token mapping. Only the new operation requires this value to match the fresh assertion. Existing `admits`, tick normalization and NSE/Intraday behavior are unchanged.

The existing governed Market calendar publication is adapted field-for-field to MarketSessionService. Request, observation, receipt and final checks require OPEN in the same governed window. A positive exact-contract tick must be on the active connection, strictly after the applied subscription, non-recovered under existing subscription rules, ordered and within the bounded freshness window. The operation does not claim trade-level continuity or first-market-quote priority. Distinct exchange time remains UNKNOWN unless separately supplied; the normalized Provider timestamp and actual KRONOS receipt are retained.

The 15-second Settings observation budget bounds the quote wait and accepted freshness window; existing synchronous Provider resolution keeps its own transport timeouts. Slow resolution can therefore fail this observation rather than certify stale data. No additional cancellation, worker or retry architecture is introduced.

## Durability, ownership and cleanup

An exclusive private operation directory retains an immutable request and digest-bound receipt. Identical replay reads the same historical receipt, never reacquires or represents it as live-now; conflicting or incomplete replay rejects. Receipt GETs are observational, including unavailable/error paths. Construction, startup and workspace GETs neither acquire nor subscribe nor create operation records.

The operation owns a counted MONITORING_CALLBACK ticket through Provider work, subscription release and receipt publication. Browser POST retains its existing BROWSER_POST ticket. The existing shared connection listener may retain its normal notification connection baseline; this is an expected observation delta, not a position or current stream-health claim. Cleanup releases only the temporary registration; other shared NSE/Intraday/position owners remain attached. Unproved cleanup or incomplete final bookkeeping retains the operation ticket and blocks new observations and retirement. Such failure requires diagnosis, not automatic retry. A terminal FAILED receipt never grants admissible CMP or trading authority.

## Boundaries

This operation creates no plan, advisory, PAPER/LIVE position, entry, order or research update. It does not change selection, analysis, accepted Answer/V2, commissioning or any generic MCX hold. Current withheld V2 does not prohibit factual non-position observation and does not become confirmed through it. All five MCX families share the same exact-contract path. Physical/monetary multipliers, costs and trading authority remain outside this operation.

Engineering tests use isolated fake Provider evidence through the actual shared hub and Kite adapter. They establish source behavior, not genuine live market acceptance. Publication/build/install/load and one genuine WO-05 observation require separate Sponsor authorization. WO-01–04 remain closed; WO-06–13, UX and WO-16/15 remain paused.


## Bounded rejected-quote attribution

An optional additive `quote_validation` diagnostic is retained before the
existing quote guard, in the same immutable receipt. It contains only the exact
normalized ProviderMarketTick and MonitoringSubscriptionEvidence available at
that decision, their subscription digest, decision/request/valid-through times,
and the ordered guard results. The first false guard is FAIL; evaluated true
guards are PASS; short-circuited guards remain UNKNOWN. The immutable tick and
context expose the individual identity, connection and timestamp constituents
of `admits` and the ordered-time condition without another Provider read.
An absent typed tick or context is represented by null, never serialized from
an arbitrary object. No authentication payload or raw Provider exception is
retained. Distinct exchange timestamp remains UNKNOWN.

The diagnostic is not an accepted observation, admissible CMP, subscription
recovery or trading authority. Failed receipts retain observation=null. All
existing freshness, positive-price, token, identity, session, selection and
final-currentness gates remain in force, including their short-circuit order
and one evaluation of mutable guard properties. No retry, quote buffering,
timestamp adjustment, budget extension or acceptance fallback is introduced.
Historical receipts without the optional diagnostic remain immutable and
readable/replayable; no records are upgraded or rewritten. The next genuine
attempt requires separate Sponsor authorization after exact-byte review and
release. This addition cannot retrospectively identify the missing predicate
values of operation d688ffd13aa4448d8e07f8bd6d7919f9.
