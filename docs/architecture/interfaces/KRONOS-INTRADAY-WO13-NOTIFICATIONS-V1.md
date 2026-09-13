# Intraday WO-13 shared Notifications interface V1

**Status:** Sponsor/EA frozen implementation contract; engineering candidate, not production commissioned.
**Policy:** `KRONOS-INTRADAY-WO13-NOTIFICATIONS / 1.0.0`
**Policy checksum:** `39d19d885c2a03b76ebe9d1eee61b2eab7eaa7b9f93fb2f536059842337ed810`

## Producers

| Source | Accepted semantic event |
| --- | --- |
| Admitted Probables persistence | Stable opportunity origin retention only; no notification family |
| WO-09 current readiness | First lawful 4/5 or 5/5; current hard gate must be NONE |
| WO-10 Futures | Executable Trade Candidate, or allowlisted material unavailable state |
| WO-11 lifecycle | Model Entry, TARGET, STOP_LOSS, SPONSOR_EXIT or material monitoring interruption |

Every adapter reloads and validates the exact immutable source. It may select
only allowlisted compact fields. It cannot evaluate readiness, construct a
trade, infer a crossing, calculate a new result or alter lifecycle state.

## Opportunity and notification identity

The origin record supplies the Sponsor-readable `opportunity_id` and the
machine `opportunity_identity`. It is retained at admitted Probables persistence
without UPDATE RESEARCH or XLSX publication. Source records are related by exact
subject, DOMAIN-008 session, source identity/integrity and event time. An origin
after the source event is invalid.

Notification identity is a canonical digest of product, opportunity identity,
family, semantic transition, optional track identity and optional truth class.
Source-record churn that preserves these semantics deduplicates. A changed
semantic transition is a new notification.

## Output and lifecycle

The output is one `INTRADAY_WO13` record in the shared Sponsor notification
centre. It contains the compact policy-bound detail JSON and delivery state.
Shared LIVE/EXPIRED, dismissal, delete-expired, filtering, search, sorting and
restoration apply. Presentation operations address notification records only.

Telegram dispatch uses the existing shared service. Dispatch intent is retained
before transport so a process interruption cannot cause an automatic duplicate.
A failed send remains isolated from the producer event.

Per-card monitoring reads the existing lifecycle owner projection. Values are
LIVE, INTERRUPTED, IDLE, NOT_REQUIRED or UNAVAILABLE. Notifications never own,
open, close or restore a WebSocket subscription.

Browser `/notifications/intraday` and `/notifications/status?product=INTRADAY`
read the restored centre projection. GET, search, filters and product switching
perform no source scan, event creation, Provider action or research publication.
