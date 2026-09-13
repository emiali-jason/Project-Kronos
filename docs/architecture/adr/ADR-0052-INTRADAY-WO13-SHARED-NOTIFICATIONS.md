# ADR-0052 — Intraday WO-13 shared Notifications adaptation

**Status:** Sponsor/EA authorized bounded engineering; candidate subject to qualification and Sponsor review. Publication, runtime load and production notification delivery remain separately gated.

## Decision

Prospective-programme WO-13 adapts Intraday events into the existing shared
Notifications product. It does not create a second application, lifecycle,
store, Telegram transport, WebSocket owner or Sponsor destination. The shared
shell retains the `SWING | INTRADAY`, `ALL | LIVE | EXPIRED`, search, dismissal,
delete-expired, sorting and restart-restoration semantics.

The commissioned families are 4/5 READY, 5/5 NOW, TRADE CANDIDATE, PAPER ENTRY,
OBSERVATION ENTRY, TARGET, STOP LOSS, SPONSOR EXIT, MONITORING INTERRUPTED and a
bounded ACTION REQUIRED allowlist. Three of five, ordinary refresh, ordinary
Provider state, every tick, every successor record, Browser reads and WO-12
publication events do not create notifications.

Notifications are presentation facts. Each compact record binds an immutable
upstream source identity and integrity, the stable `opportunity_id` and
`opportunity_identity`, the semantic transition, and the track/truth class when
applicable. Identity is deterministic over those semantics, so rereading an
equivalent successor cannot generate Sponsor noise. A genuine transition such
as 4/5 to 5/5 or Entry to Target remains distinct.

## Opportunity origin

The existing WO-12-compatible origin producer is commissioned synchronously
after admitted Probables persistence. It retains the earliest admitted event
for a subject/session and permits a successor only after a retained terminal
WO-11 track followed by a later admitted event. Repeated Probables persistence
is idempotent. This producer does not run UPDATE RESEARCH, calculate research,
publish an XLSX or make WO-13 the identity owner.

WO-09, WO-10 and WO-11 notification adapters resolve their exact source lineage
against that retained origin. WO-13 consumes the two origin identities unchanged.
WO-12 later consumes the same origin during an explicit UPDATE RESEARCH.

## Lifecycle and monitoring

Dismissal, expiration and delete-expired alter only shared notification
presentation records. They never delete or mutate Probables, readiness, Trade
Candidates, lifecycle tracks or research evidence. They never close a track,
stop an owner or unsubscribe a market stream. Browser GET and status routes are
read-only cached projections.

Per-card monitoring is resolved from the exact WO-11 owner state as LIVE,
INTERRUPTED, IDLE, NOT_REQUIRED or UNAVAILABLE. Provider REST connectedness and
maintenance state cannot fabricate those values. Terminal events are
NOT_REQUIRED. Notifications never open shared-monitoring sessions.

## Telegram and security

Intraday uses the existing governed Telegram delivery service. The compact
message identifies product, family, subject, direction, opportunity ID and
bounded event facts. PAPER Position and Paper Observation remain explicit
one-lot model truth classes. No credentials, headers, filesystem paths, raw
JSON, raw market ticks or complete upstream payloads enter the compact record
or message. Delivery failure changes only delivery status and never upstream
event truth.

## Preservation

Swing event identities, lifecycle, Telegram behavior and monitoring ownership
remain unchanged. RUNTIME-01 startup/restoration, WO-06H, WO-07F, WO-09, WO-10,
WO-11 and WO-12 retain their authorities. LIVE Intraday execution stays
uncommissioned. WO-14 Journal, WO-15 Portfolio and WO-16 Reports remain separate
future products. This engineering candidate performs no production operation.
