# WO-15 Intraday Portfolio V1

**Status:** Sponsor/EA authorized engineering candidate; publication, runtime load and production use remain separately gated.

**Authority:** KRONOS-INTRADAY-WO15-PORTFOLIO-POLICY / 1.0.0.
**Policy checksum:** `b4e76113c7f93b5cb9e78356ac89789ddd6e6e5a172736760b4f9efabf1d5249`.

WO-15 projects current entered, nonterminal WO-11 PAPER_POSITION tracks only.
Each exposure is exactly one model lot; selected WO-10 quantity is context only.
PAPER_OBSERVATION, NONE, DO_NOTHING and armed/no-entry tracks are not exposure.
LIVE_POSITION_NOT_COMMISSIONED_V1 remains explicit. No broker holdings inference.

Current display reads the exact WO-11 owner registration and actual shared
WebSocket transport state. Provider REST connectivity does not establish LIVE.
The latest process-local normalized tick must match the retained WO-11 accepted
source fact identity, ordering, connection, price and timestamp. The inclusive
five-second receipt-lateness rule is preserved. Missing, newer rejected, recovered,
unordered or interrupted evidence cannot expose a cached price. The displayed
price is labelled **Latest eligible observed price** with its observation time;
it is not an assertion of an exchange quote at Browser render time. No new
wall-clock freshness threshold or REST fallback is commissioned. Only retained
WO-11 points/economics are displayed while that evidence is available.

Badges are LIVE, INTERRUPTED, IDLE or UNAVAILABLE for each active owner.
Interruption hides price/results, never exposure. Terminal truth removes exposure.
The existing shared Portfolio route was a placeholder and has no Sponsor Exit
control to adapt. No new exit or delete action is introduced. Existing WO-11
Sponsor Exit remains the only manual-close lifecycle authority.

The shared shell adds SWING | INTRADAY; Swing's uncommissioned page remains so.
Search covers opportunity ID, subject and contract, with direction/monitoring
filters. Sorting uses retained decision time then deterministic presentation ID.
Zero active PAPER positions is healthy. Journal/Notification deletion has no effect.

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
