# ADR-0049 — WO-12 local monthly research publication

**Status:** Approved bounded engineering; production update and runtime load remain separately gated.

## Decision

Prospective WO-12 owns an immutable Intraday opportunity/research ledger and a
Sponsor-readable monthly XLSX publication. It has research authority only. It
does not promote candidates, construct trades, manage positions, connect a
Provider, or create broker authority. Historical WO-12 KR-370 records retain
their original meaning under ADR-0038.

The canonical Sponsor location is
`/Users/imranali/Documents/Project-KRONOS/Statistics/Intraday`. Each month has
one current file named `KRONOS_Intraday_Research_YYYY_MM.xlsx`. An explicit
Sponsor `UPDATE RESEARCH` operation composes only retained Probables, WO-07F,
WO-09, WO-10 and WO-11 evidence. It builds in operation staging, validates the
package, atomically replaces the monthly path, reads the bytes back, verifies
their SHA-256, and then publishes an immutable receipt plus an atomic pointer.
`OPEN MONTHLY EXCEL` is available only while the file matches that receipt.
GET, startup and restore perform no update.

Google Drive, OAuth, refresh tokens, Drive folders and sync are not commissioned
for V1. No automatic schedule is commissioned. The current
`STATISTICS / EXCEL` snapshot remains a separate current-state export.

## Opportunity identity

The first lawful origin is the earliest retained admitted Probables V2 result
for the canonical subject and DOMAIN-008 session. The permanent Sponsor ID is
`<SYMBOL>-<YYYYMMDD>-<HHMMSS>` in Asia/Kolkata. It is column 1 of
`Opportunities` and the linking column in `Tracks`, `Events` and
`Data_Quality`. The separate content-derived `opportunity_identity` binds the
programme, product, subject, session, origin timestamp, Sponsor ID and policy.

Refreshes, direction changes and elapsed time do not mint another opportunity.
A later same-session origin requires a retained terminal WO-11 track followed
by a later admitted Probables event. The reset and successor origin are both
immutable. Historical events are never backfilled from guesses.

## Workbook contract

The ordered sheets are `Opportunities`, `Tracks`, `Events`, `Analysis`,
`Data_Quality` and `Metadata`. Each sheet has a real Excel table, frozen header
and filter. Audited formulas calculate rates and research metrics. The workbook
contains no macros, external links, scripts, images, charts, raw ticks, raw
candles, depth payloads, Provider tokens or secrets.

PAPER Position and Paper Observation remain separate one-lot truth classes.
Numeric R and monetary metrics use only governed WO-11 results. No-entry,
ambiguous and unavailable results remain countable but are excluded from R
arithmetic. Monitoring gaps preserve lawful entry/exit metrics while excluding
full-path MFE/MAE. Zero-R outcomes enter expectancy and are excluded from
average-win, average-loss and payoff calculations.

WO-09 readiness history, WO-10 construction/market/Risk facts and WO-11
lifecycle facts are projected by exact retained identities. Missing facts are
represented as unavailable and surfaced in Data_Quality; WO-12 does not rerun
upstream calculations. Workbook formulas use ordinary bounded cell ranges so
the saved file recalculates without external links or table-formula engine
dependencies.

## Browser placement

`RESEARCH / ANALYSIS DETAILS` is a secondary action under `OPPORTUNITIES`, not
a sixth Intraday tab. The five canonical tabs remain Opportunities, Review,
Trade Candidates, Active and Closed.

## Consequences

- Local publication can be rebuilt deterministically from the compact ledger.
- A partial or unverifiable workbook never becomes current authority.
- Finalized-month corrections require a separately governed future operation.
- Production invocation, runtime load, commit and publication remain separate gates.
