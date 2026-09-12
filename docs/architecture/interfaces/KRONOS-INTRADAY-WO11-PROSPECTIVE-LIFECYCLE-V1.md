# Prospective WO-11 lifecycle interface V1

**Status: Approved contract under ADR-0046; engineering candidate, not production commissioned.**

Input: exact current WO10_SELECTED_TRADE_HANDOFF_V1. All nested copies must
match reloaded source records, exact Native authority and current WO-09/WO-10
pointers. Browser input is only handoff/action/action identity, or claim/action
identity for manual closure. No quantity or price field is accepted.

Pricing input: ProviderMarketTick, exact InstrumentRecord and DOMAIN-008 session.
Eligibility retains original observed/received times, computed microseconds,
source/connection/nullable sequence, continuity flags, recovered state, reason,
source fact, pricing methodology and latency policy identity/version/checksum.

Timing input: owner-sealed completed candle and semantic facts from the existing
factual source and completed-evidence/5M semantic producers. No source is
substituted with market-tick arithmetic. No Native selection is rerun.

Analytical capability: post_entry_analytical_invalidation = NOT_COMMISSIONED_V1
on every record. No analytical reassessment input or producer is commissioned.
Original WO-10 invalidation remains exact intake lineage, not an event. Close
requests reject analytical reasons. Upstream supersession cancels pre-entry
eligibility only. Future POST_ENTRY_ANALYTICAL_INVALIDATION_V2 requires its own
versioned authority and cannot change the meaning of V1 records.

Storage: independent WO11_* immutable schema families, canonical payload,
programme/policy identity/version/checksum and content-derived integrity. Current
pointers are atomic and compare predecessor identities under an exclusive lock.
One claim spans both truth classes for each opportunity/semantic expression.

Output: separate Position/Observation states, model entry/exit, event and closure
request sources, monitoring gaps, coverage/metrics, and WO11_WO12_HANDOFF_V1.
After Entry, `exit_reason` permits only STOP_LOSS, TARGET or SPONSOR_EXIT.
Session/contract end, pre-entry cancellation, interruption, ambiguity and
unavailability remain separately represented by `terminal_status`. A Sponsor
request identity is retained and its exit price is the first subsequent eligible
WebSocket LTP; before Entry it cannot become SPONSOR_EXIT.
The handoff carries the exact opportunity, truth class, one lot, geometry,
timing, entry/exit, closure, gaps, metrics and retained upstream quantity context.
It never creates LIVE fills, broker authority, notification delivery or Portfolio
exposure for Observation. WO-12 additionally retains original_thesis_invalidation,
thesis_invalidation_role=THESIS_DEFINITION_CONTEXT_ONLY, and the explicit
post_entry_analytical_invalidation capability. No NOT_INVALIDATED inference is allowed.


Contract boundary input remains the existing exact ActiveDerivativeBindingArtifact,
including its active_binding identity/contract and DOMAIN-008 expiry eligibility
boundary. WO11_CONTRACT_BOUNDARY_V1 retains a new governed roll artifact as source;
a same-contract refresh is not an analytical exit. Missing current contract
source is unavailable/interrupted, not a fabricated roll event. Retained earlier
expiry and final session boundaries terminate without using a cached model price.
The whole predecessor/source graph is verified before restoring a current track.

WO11_AUTHORITY_CHECK_V1 distinguishes an exact upstream supersession result from
missing/corrupt/unavailable source authority. The latter interrupts eligibility
and requires a fresh baseline; it is not a fabricated supersession or close.
