# WO-10 Futures snapshot policy

**Status:** Approved engineering policy; ADR-0039; version 1.0.0.

ONE full-quote request contains the exact underlying and selected NSE Future, or
one exact MCX Future. An absent daily master may be acquired through an explicitly
supplied lawful master operation first: at most two physical requests in total,
never two quote requests. Each request has operation attribution; no retry, expiry
shopping or widening; timeout seven seconds. Provider rate denial is explicit. The private quote transport forbids redirects
and repeated requests, retains zero automatic retries, and does not mutate the
shared SDK timeout/session. It stays inside the existing Provider capability;
no authentication attempt or new access token is created.

NSE selection uses the exact governed underlying Provider symbol and NFO-FUT/FUT
family name. NIFTY and BANKNIFTY use exact commissioned family identifiers. Unique
minimum expiry strictly after trading date is mandatory. Expiry-day contracts are
ineligible from session open. MCX consumes its existing active binding and exact
contract economics; it does not select another contract. MCX retains its existing
DOMAIN-008 family-specific expiry-day eligibility; NSE exclusion never overrides
that authority. NATGAS is HELD.

Retain exchange and last-trade timestamps, LTP, volume, OHLC, total pending buy/sell
quantities, bid/ask depth (at most five per side), OI, field availability and
provenance. Missing fields are unavailable, never zero-filled. Provider token is
internal evidence only. Bid/ask is distinct from total pending quantity. No
spread, depth, volume or OI threshold is introduced. Locked BBO is allowed.

Basis = same-snapshot Future LTP minus underlying LTP. LONG ticks: Entry up,
Stop down, Target down; SHORT inverse. Recompute positive risk/reward and R:R.
MCX basis is NOT_APPLICABLE, never a retained numeric zero. Underlying geometry
and invalidation remain unchanged. OI baseline is first lawful exact-contract,
Provider/master/session observation; first delta is unavailable. Later current
quotes subtract that immutable baseline; never cross roll or lineage.

OI availability is a factual boundary separate from bid/ask executability. A
current exact Future OI observation creates/uses its baseline even when missing
bid/ask makes the comparison non-executable. The first snapshot binds the new
baseline identity, integrity and observation time but retains unavailable Delta
OI. Later same-session current OI may produce Delta OI without granting trading
permission. Stale/future-dated OI never creates a baseline.
