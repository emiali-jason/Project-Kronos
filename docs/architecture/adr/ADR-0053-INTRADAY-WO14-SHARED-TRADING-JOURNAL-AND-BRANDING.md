# ADR-0053 — Intraday WO-14 shared Trading Journal and UI-BRAND-01

**Status:** Sponsor/EA authorized bounded engineering; candidate subject to qualification and Sponsor review. Publication, runtime load and production Journal use remain separately gated.

## Decision

Prospective WO-14 adapts Intraday facts into the existing shared Trading Journal
and its `SWING | INTRADAY` selector. It creates no second Journal, lifecycle,
monitoring system, deletion authority, Portfolio or Reports surface. Historical
Intraday WO-14 Risk Observation documents, records and modules retain their
meaning; the successor implementation uses the explicit `wo14_journal`
namespace.

The Intraday book is a compact presentation projection of retained WO-10 and
WO-11 facts. It includes PAPER Position, Paper Observation, NONE, DO NOTHING,
no-entry and terminal dispositions. LIVE remains
`LIVE_POSITION_NOT_COMMISSIONED_V1`. It consumes the stable `opportunity_id`
and `opportunity_identity` created at admitted Probables persistence. Missing
or ambiguous origins fail closed.

## Identity and suppression

Journal identity binds product, opportunity identity, Sponsor-decision
identity, optional track identity, truth class and disposition. Content-derived
revisions and atomic current pointers make repeated reads and restarts
idempotent.

DELETE retains an immutable record-specific presentation-suppression fact. It
does not mutate lifecycle evidence, close a track, remove monitoring, delete a
Notification, alter WO-12 population or remove future Reports evidence.
Suppression survives restart and source successors. Swing has no Journal
undelete product, so none is added.

## Monitoring and boundaries

Tracked rows read the exact WO-11 owner registration as LIVE, INTERRUPTED,
IDLE, NOT_REQUIRED or UNAVAILABLE. Terminal records are NOT_REQUIRED. Provider
REST state cannot substitute for owner state. Journal reads and suppression
create zero transports, owners or subscriptions.

WO-12 retains metric and denominator authority. WO-13 remains the independent
attention/Telegram product. WO-15 Portfolio and WO-16 Reports remain
unimplemented.

## Shared brand

UI-BRAND-01 preserves the supplied Sponsor master bytes and uses optimized
local derivatives in the shared Browser shell, favicon and macOS template
resources. Swing and Intraday use one identity. There is no remote dependency,
new polling or semantic change. Bundle identifier, signing identity, APP-01A
guard and runtime authority are unchanged. A later governed build/install must
qualify any bundle hash change.

## Preservation

The trading exits remain STOP_LOSS, TARGET and SPONSOR_EXIT. PAPER and
Observation remain one-lot WebSocket `last_price` models with separate truth.
WO-06H, WO-07F, WO-09, WO-10, WO-11, WO-12, WO-13, RUNTIME-01 and Swing retain
their authorities. This candidate performs no production operation.
