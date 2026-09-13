# Intraday WO-14 shared Trading Journal interface V1

**Status:** Sponsor/EA frozen implementation contract; engineering candidate, not production commissioned.
**Policy:** `KRONOS-INTRADAY-WO14-TRADING-JOURNAL-POLICY / 1.0.0`

| Producer | Accepted facts |
| --- | --- |
| WO-12 opportunity-origin store | Exact retained `opportunity_id`, `opportunity_identity`, subject, market family and origin time |
| WO-10 Futures | NONE selection, decision identity, plan/expression identities, selected-lots context and immutable geometry/contract facts |
| WO-11 lifecycle | DO NOTHING, PAPER/Observation track, entry/exit, terminal state and retained metrics |
| WO-11 owner projection | Per-track LIVE, INTERRUPTED, IDLE, NOT_REQUIRED or UNAVAILABLE |

Every adapter reloads an exact immutable record. It cannot regenerate an
opportunity identity, calculate a metric, infer an exit, create lifecycle truth
or use Notifications as factual authority.

The compact record contains opportunity and decision lineage, subject,
direction, market/session, truth/disposition, compact plan/Future facts,
selected-lots context, fixed one-lot model quantity, retained entry/exit and
timestamps, terminal/exit state, retained metrics and bounded source
identities. Missing facts remain unavailable. Raw ticks, charts, PDFs, answer
packs, full upstream JSON, credentials, headers and local paths are excluded.

Identity is a canonical digest of INTRADAY, opportunity identity, decision
identity, optional track identity, truth class and disposition. Revision
identity digests the exact compact payload. Current pointers advance without a
new Journal identity.

`GET /journal?product=INTRADAY` reads compact current and suppression indexes.
Search, filters, stable event-time sorting and drill-down are read-only and do
not run WO-12 UPDATE RESEARCH or scan upstream evidence.

`POST /journal/intraday/delete` requires exact Journal/current-revision/action
identities and retains presentation suppression only. Source, track, owner,
subscription, Notification and research population remain unchanged. V1 has no
restore control.

PAPER OBSERVATION is visibly counterfactual. NONE and DO NOTHING carry no
entry, exit, P&L or owner. No-entry tracks carry no invented P&L. LIVE remains
uncommissioned.
