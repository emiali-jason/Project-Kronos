# KRONOS Intraday WO-13 Notifications V1

**Status:** Sponsor/EA frozen implementation contract; qualified engineering candidate, not production commissioned.

WO-13 is the Intraday adaptation of the existing shared Notifications product.
The Sponsor uses the same Notifications destination and selects `SWING` or
`INTRADAY`. Intraday provides the same ALL, LIVE, EXPIRED, search, dismissal,
delete-expired, sorting and restart-restoration behavior.

The ten commissioned Sponsor titles and their exact upstream triggers are:

| Title | Authoritative trigger | Telegram | Monitoring |
| --- | --- | --- | --- |
| 4/5 READY | Current WO-09 first reaches four satisfied criteria with no hard gate | Eligible | UNAVAILABLE unless an exact owner exists |
| 5/5 NOW | Current WO-09 first reaches five satisfied criteria with no hard gate | Eligible | UNAVAILABLE unless an exact owner exists |
| TRADE CANDIDATE | WO-10 executable comparison/plan/Future expression | Eligible | NOT_REQUIRED |
| PAPER ENTRY | WO-11 PAPER_POSITION establishes retained model Entry | Eligible | Exact track owner |
| OBSERVATION ENTRY | WO-11 PAPER_OBSERVATION establishes retained model Entry | Eligible | Exact track owner |
| TARGET | WO-11 retained TARGET exit | Eligible | NOT_REQUIRED |
| STOP LOSS | WO-11 retained STOP_LOSS exit | Eligible | NOT_REQUIRED |
| SPONSOR EXIT | WO-11 retained SPONSOR_EXIT and request identity | Eligible | NOT_REQUIRED |
| MONITORING INTERRUPTED | WO-11 retains a material exact gap | Eligible | INTERRUPTED |
| ACTION REQUIRED | WO-10 retains a policy-allowlisted material unavailable reason | Eligible | NOT_REQUIRED |

An unavailable plan never appears as a Trade Candidate. Three of five, ordinary
Discovery/Review/Provider/Browser activity, unchanged readiness, ticks, metrics
advances without a notification event, WO-12 ALREADY_UP_TO_DATE and generic
technical errors are silent.

The stable origin identity is produced at admitted Probables persistence using
the existing WO-12 origin contract. Repeated refreshes retain one origin. A new
same-session origin requires a retained terminal WO-11 track followed by a
later admitted event. WO-13 cannot regenerate either identity. WO-12 remains
the owner of research projection and explicit local XLSX publication.

Notification deletion and dismissal do not delete upstream evidence, create or
close positions, perform Sponsor Exit, stop monitoring or unsubscribe a stream.
Opening, refreshing or filtering Notifications likewise has no monitoring,
Provider or analytical side effect.

PAPER Position and Paper Observation each remain exactly one lot, use governed
WebSocket `last_price`, preserve the five-second inclusive lateness policy, and
remain distinct exposure and counterfactual truth classes. Exits remain exactly
STOP_LOSS, TARGET and SPONSOR_EXIT. LIVE_POSITION and post-entry analytical
invalidation remain NOT_COMMISSIONED_V1.

The compact persistence and Telegram allowlists reject credentials, headers,
local paths, raw upstream JSON, raw ticks and unnecessary Provider identifiers.
Telegram is delivery transport only. A failed delivery cannot invalidate the
underlying WO-09, WO-10 or WO-11 event.
