# ADR-0046 — WO-11 V1 post-entry analytical invalidation capability

**Status: Approved by explicit Sponsor/EA policy and engineering correction, 2026-09-12.**

This supersedes ADR-0045/N7 only where automatic post-entry analytical invalidation
was a required V1 lifecycle exit. It does not authorize production use or runtime load.

POST_ENTRY_ANALYTICAL_INVALIDATION_AUTOMATIC_EXIT = NOT_COMMISSIONED_V1.
The original immutable WO-10 invalidation definition remains THESIS_DEFINITION /
CONTEXT. It is not an observed event, ongoing reassessment or close trigger.
No tick, Stop/Target traversal, historical adapter or Chart Analyst inference
creates analytical invalidation. No reassessment producer is added.

After model Entry, V1 has exactly three trading exit reasons: STOP_LOSS, TARGET
and SPONSOR_EXIT. A Sponsor request is priced only by the first subsequent
eligible governed WebSocket LTP. Lawful final session/contract boundaries are
lifecycle safety boundaries, not trading exits. Missing pricing, monitoring
interruption and ordering ambiguity retain separate fail-closed terminal/data
statuses. `exit_reason` and `terminal_status` are never combined.
Already-governed upstream supersession can terminate pre-entry eligibility; it
cannot become a post-entry analytical exit. Contract/expiry boundaries retain
separate exact instrument authority.

Every V1 record retains the explicit capability state. The WO-12 handoff separately
carries the original thesis definition and NOT_COMMISSIONED_V1. Absence is never
NOT_INVALIDATED. POST_ENTRY_ANALYTICAL_INVALIDATION_V2 is a reserved future
capability, not implemented or enabled; future commissioning must preserve V1
policy/checksum and record meaning.

The obsolete analytical-source blocker is removed from source composition while
operational admission, maintenance, Provider and Sponsor-action gates remain.
Qualification uses isolated stores and capabilities. Production operations,
runtime load, staging, commit and push remain prohibited by this engineering order.
