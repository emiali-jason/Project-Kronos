# Swing MCX V1 — separate close-confirmed advisory

Status: PROPOSED for exact-byte release review; production NOT COMMISSIONED.
Engineering instruction: Sponsor's MCX 2F RULE DECISION — V1 ADVISORY.
Scope: Swing GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS only.

This decision does not amend or relabel P32-002, ADR-0011 or ADR-0013.
Their historical KR-380 trade-level outcome records and NSE consumers remain
unchanged. The separate schema is KRONOS-MCX-CLOSE-CONFIRMED-ADVISORY-V1;
its rule is SWING-MCX-COMPLETED-1H-ADVISORY-V1. It reports ADVISORY,
intrabar trade continuity UNVERIFIED, and broker authority NONE.

Two confirmed completed consecutive one-hour candles P and C must belong to
the selected exact future and one eligible continuous session. No missing
candle or opening gap across Entry is permitted. LONG requires P.close < Entry,
C.open < Entry and C.close >= Entry. SHORT requires P.close > Entry,
C.open > Entry and C.close <= Entry. A wick alone is insufficient. Partial,
revised, stale-binding and cross-expiry observations reject. Hourly OHLC is not
represented as proof about every intrabar trade.

The issuer binds the current run, exact selected contract/master record,
retained MTF lineage, plan, Review receipt, V2, risk record and session. It
compares repeated source reads and rechecks the retained plan, master and MTF
under the existing Review owner final fence before immutable retention. A
different replay is rejected. Status and view GETs do not issue advice or
write records. Resolver, calendar and Intraday decision interfaces are unchanged.
The reconnect correction below adds read-only Provider subscription evidence;
that shared delta requires Provider/monitoring-owner and EA-Intraday review.

PAPER remains one lot. Confirmation time is retained separately from candle
completion. Only a newly observed admissible same-contract CMP received after
confirmation can activate it; its actual receipt time is the model fill time.
The tick that caused confirmation cannot also become its retrospective fill.
Disconnected, recovered or unavailable observations delay activation. A fresh
post-interruption observation is required. No first-market-quote claim or
contiguous Provider tick sequence is made. Exit uses a factual same-contract
observation. Monetary values without authenticated multiplier remain UNKNOWN;
costs and net P&L remain UNKNOWN.

Manual LIVE is a Sponsor record, never a broker order. It retains positive
whole lots, exact contract, actual fill price/time, submitted broker bytes and
hash before position/closure recording. A qualifying advisory is bound where
present; without it the immutable record and projection say
SPONSOR-DIRECTED / OUTSIDE MODEL, with no fabricated signal identity. Broker
evidence is Sponsor-submitted, not falsely labeled broker-authenticated.

Historical positions restore the retained exact future, never today's family
resolver. New-entry gates do not disable their factual monitoring or exits.
Retained exit intent/attestation permit bounded restart reconciliation; an
identical replay yields one closure and conflicts reject.

The monitoring owner may resume MCX V1 factual CMP observation after
CONTEXT_INCOMPLETE only with its current exact subscription evidence. The Kite
adapter assigns a new opaque connection identity on every physical connection
and records the subscription timestamp only after subscribe and full-mode
dispatch succeed. The existing shared registration exposes those facts only
while capability, ownership and exact subscription remain active. It does not
reattach the position or create another transport. The accepted CMP must match
that identity and future, and its observation time must follow resubscription.
The actual CONTEXT_INCOMPLETE state and unverified intrabar continuity remain
unchanged. A missing proof, failed subscription, stale callback or interrupted
session cannot authorize activation or a cached factual exit. Armed positions
retain the same advisory; active positions retain their entry and outcome.
The entry final fence rechecks the subscription proof alongside current plan
and outcome. This is observation recovery, not reconstruction of missed trades.

Lock protocol: the Provider evidence lock protects only factual snapshots and
is released before socket calls and consumer callbacks. The hub releases its
state lock before dispatching consumers. The lifecycle callback lock serializes
its state/tick handling, then follows the existing application/Review/lifecycle
ordering; application reads of latest CMP use an immutable publication and
transport recheck without acquiring that callback lock in reverse order.

Composition continues to withhold MCX_STEP31_NOT_COMMISSIONED on production
mutation routes. No Browser controls or broker execution capability are
commissioned by isolated fixtures. Exact-byte review, full qualification,
publication, governed load and genuine live acceptance are separate gates.
WO-13, WO-14, WO-12, WO-16 and WO-15 remain separate follow-on work.
