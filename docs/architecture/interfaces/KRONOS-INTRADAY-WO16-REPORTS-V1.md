# WO-16 Intraday Reports V1

**Status:** Sponsor/EA authorized engineering candidate; publication, runtime load and production use remain separately gated.

**Authority:** KRONOS-INTRADAY-WO16-REPORTS-POLICY / 1.0.0.
**Policy checksum:** `4ed55ea343aa536fe81bb0c6bed123f7db194768501105d70afeaf8e25ad7620`.

WO-16 adapts canonical WO-10 NONE selections and WO-11 DO_NOTHING actions and
current retained track outcomes into the shared historical Reports framework.
It includes PAPER, counterfactual Observation, no-entry, ambiguity, unavailable,
active and terminal history. LIVE is explicitly uncommissioned. Model quantities
and all points/R/MFE/MAE/economics are copied from WO-11, never recalculated.
WO-12 exclusively owns research denominators, funnel rates and research metrics.
Overview has simple record/truth/terminal counts and no combined net model P/L.

Views: OVERVIEW, PAPER, LIVE, PAPER_OBSERVATIONS, ALL_RECORDS. Shared pagination
and date range, opportunity/subject/contract, direction, status/outcome filters
are reused; exit-reason and monitoring-completeness filters are added for Intraday.
No universal TODAY boundary is inferred across NSE/MCX; exact date ranges remain
available. Sorting uses retained exit/entry/decision timestamp then stable row ID.
Observation stays distinguishable from PAPER in every export and row.

CSV, JSON and XLSX reuse the shared export writers. XLSX uses REPORT/SUMMARY,
inline text cells and numeric cells for known numeric facts; CSV prefixes dangerous
text formulas while preserving numeric negatives. JSON is a compact exact field
allowlist. Exports reflect all current filters. They are transient factual reports,
not WO-12 monthly research publication, and write no canonical research path or
receipt. Dates/timestamps remain explicit ISO text, preserving timezone provenance.

Journal suppression and Notification dismissal cannot remove source history.
Retained terminal monitoring context and metric completeness are factual;
Reports never calls the monitoring owner or reconstructs research eligibility.

## Shared source binding and preservation

`IntradaySourceAdapter` reuses the exact identity/source extraction previously
used for Journal. WO15/16 consume source stores directly, never Journal rows or
Notification records. Stable opportunity_id and opportunity_identity come from
the existing retained origin producer unchanged. Only a separate deterministic
presentation row ID is calculated. Source lifecycle/decision IDs remain available.

`IntradayBooks` is a process-local disposable compact projection, not a durable
lifecycle store. Composition/binding performs no I/O and creates no owner. First
use lazily hydrates typed selection/action/current-pointer populations and verifies
existing source graphs once. Thereafter committed source callbacks replace rows;
GET/filter/export does not scan sources or rebuild lifecycle graphs. Capacity is
bounded to 10,000 compact rows and typed source populations. Overflow or broken
source lineage fails explicitly unavailable rather than truncating history. A
source failure latches unavailable for that instance; restart can rebuild from
canonical evidence. No source evidence or workbook is copied/backfilled.

No raw ticks, full lifecycle payloads, Provider secrets or private paths enter
payloads/exports. UI-BRAND-01 assets and the shared top-level navigation are
preserved. Neither product creates subscriptions, owners, Provider connections,
notifications, research updates or lifecycle facts. RUNTIME-01, Swing, WO-06H,
WO-07F, WO-09/10/11/12/13/14 and NATGAS HELD retain their authority.

## Legacy current-statistics export preservation

The earlier Intraday current-statistics exporter already owns the legacy
`/reports/export.xlsx?product=INTRADAY` request without a view. Its workbook,
route and links remain unchanged. WO-16 Reports links always carry an explicit
`view=OVERVIEW|PAPER|LIVE|PAPER_OBSERVATIONS|ALL_RECORDS` and reach the shared
factual export writer. The WO-16 filename uses `KRONOS_INTRADAY_FACTUAL_REPORT`
to distinguish it from current statistics and WO-12 monthly research.
