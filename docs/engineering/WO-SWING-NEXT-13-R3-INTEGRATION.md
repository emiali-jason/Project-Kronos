# WO-SWING-NEXT-13 — Notifications R3 integration after MCX deployment

**Status:** Sponsor-authorized isolated engineering candidate, pending exact-byte
review and separate publication/load/runtime acceptance. This record does not
approve a new notification family, trading rule or delivery operation.

## Frozen inputs and authority

The deployed source baseline is `7f783d10530557e7d19a36297a79f43861ca7f49`.
The retained Notifications R3 checkpoint is based on `8002dde347e397f04dcd31d0a121631ba46f7102`,
with manifest SHA-256 `d660139238d4c504775b3466e467fd57a83552a65928e6a7c4b5e7bd5012e780`
and archive SHA-256 `bb92d1e2175ef415f9583c331c63c71e48a567397c62fdc5daa6941ce0652203`.
Its historical 430-test result qualifies that checkpoint only. See the preserved
[R3 implementation record](WO-SWING-NEXT-13.1-NOTIFICATIONS-CORRECTION.md) for
the original source and recovery semantics. ADR-0052 and its Intraday notification
contract retain their existing authority; ADR-0059 retains shared maintenance
ownership. The current Sponsor order authorizes this bounded integration.

## Four source overlaps

| Path | Integration decision |
| --- | --- |
| `src/kronos/application/swing_native_review.py` | Add exact-position notification evidence delegation. Retain MCX selection, advisory planning, manual-LIVE/PAPER admission and historical restoration. |
| `src/kronos/browser/server.py` | Add R3 centre synchronization, per-owner indicators and retained-evidence routes over the current server. Preserve canonical MCX composition before restoration, request diagnostics, mutation guards, counted server pulses, final bookkeeping and terminal-analysis cleanup. |
| `src/kronos/browser/views.py` | Add notification presentation/evidence rendering only. Retain dedicated MCX V1 selection, plan/admission/exit forms and unknown monetary facts. |
| `src/kronos/swing/v1/native_active_trade_lifecycle.py` | Retain deployed exact-contract subscription, physical-connection checks, stale-callback rejection and quote invalidation. Add notification observation state without replacing MCX fields. Publish notification observation only after lifecycle acceptance, so an ignored stale/wrong-context tick cannot restore a card. Clear it on connection transitions. |

The native lifecycle has two textual conflicts: initialization and connection
callback invalidation. Both retain the deployed state and append R3 notification
state. Notification reads also reuse the deployed current-subscription fence:
an invalidated MCX subscription hides its old quote even without a new callback.
Other overlaps are reviewed at the behavior level, regardless of clean
textual merging. The older complete R3 files must never replace current MCX files.

## Preserved responsibilities

Existing owned server pulses synchronize notification presentation. Notification
GETs read projections and retained bindings; they never synchronize, reserve an
MCX run, acquire candles, Connect or send Telegram. The legacy Intraday fallback
remains in the pulse only and is skipped when the modern Intraday owner exists.
No new timer, WebSocket session, Provider interface or notification authority is
introduced. Startup retains R3's initial Swing centre synchronization; it does
not invoke the legacy Intraday fallback.

Per-card monitoring uses the exact registered position/watch and accepted
observation. Reconnection or a CONNECTED header does not prove continuity.
MCX V1 can lawfully monitor factual CMP with trade-level continuity unverified;
the notification badge must remain truthful and cannot veto MCX lifecycle work.
Dismissal affects presentation only and does not detach, close or rebind a
position. Existing historical-contract monitoring and factual exits remain
independent of new-run or new-entry eligibility.

R3 keeps semantic progression, linked connectivity incidents, restart/replay
reconciliation and ordering boundaries. Telegram dispatch retains an attempt
before transport. Ambiguous acceptance remains DELIVERY_UNCERTAIN with no
automatic resend; only existing explicit nonacceptance cases permit bounded
retries. No real Telegram test message is part of engineering qualification.

## Qualification and release boundary

The review packet must contain the exact manifest, base-relative integration
patch, overlap decisions, updated acceptance matrix, invocation/environment,
complete logs/JUnits, static checks and before/after governed inventories.
Run owning and affected Swing/Browser/MCX/Intraday protections, then freeze and
review WO-13. Integrate and review WO-14 before one complete protected
qualification on the final combined frozen bytes. Historical results are separate.
The integration also updates the existing expected-maintenance-disconnect test
to inspect R3's retained structured connection checkpoint, verify that it closes
without an incident or delivery, and verify the same checkpoint after restart.
The old tuple-index assertion failed before those guarantees were checked. Its
failed isolated reproduction and interrupted pre-correction protected attempt
remain separate evidence; neither qualifies the corrected candidate.
Shared Browser/notification/monitoring consumers require review of the integrated
delta before a separately authorized release. Unchanged Provider and Intraday
source files do not acquire new responsibilities.

This documentation is in repository-relative release scope for durable GitHub
coverage; local qualification reports do not replace it. Publication, launcher
installation, runtime load and live Telegram/runtime acceptance remain pending.

MCX PAPER admission, activation, monitoring and factual exit remain
**WAITING FOR QUALIFYING MCX OPPORTUNITY — NOT YET EXERCISED**. Preserve the
existing no-opportunity result. Use the existing governed schedule, genuine
Review/accepted Answer/V2/advisory evidence and explicit Sponsor one-lot PAPER
admission with subsequent factual exact-contract CMP. Do not repeat analysis
to force a positive result.

The next sequence is WO-13 review, WO-14 integration/review, one combined
protected regression, then separately authorized publication/load. Continue
WO-12, WO-16 and WO-15. MCX opportunity-dependent acceptance continues alongside.


## Market-specific acceptance amendment

Status: Sponsor-required qualification and acceptance scope; genuine runtime
acceptance remains gated to the separately authorized combined release.

NSE and GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS must each appear in
the acceptance matrix. NSE consumes admitted completed-bar progression watches,
exact V2 READY/NOW transitions and retained position lifecycle events. MCX consumes
exact KR-370 V2 analytical transitions using its native/reference receipt roles,
and admitted exact-contract position-monitoring and Stop/Target lifecycle events;
a completed-1H advisory is not an NSE tick-trigger or a new notification family.
The shared Swing monitoring owner supplies connectivity incidents; do not invent
five physical outages for one shared incident. Each card still resolves its own
watch/position and subscription evidence.

Owning qualification must cover per-item monitoring, exact retained evidence
navigation, restart/replay and dismissal, physical reconnect invalidation, and
Telegram SENT, disconnected/PENDING and DELIVERY_UNCERTAIN behavior for all five
MCX families. Uncertain delivery cannot cause automatic resend. Isolated retained
positions and mocked socket/Telegram adapters prove engineering behavior only.
Production acceptance must record genuine admitted source identities separately
for each market/family. No current MCX opportunity is a truthful observation;
family coverage stays in scope and opportunity-dependent acceptance is WAITING
FOR QUALIFYING MCX OPPORTUNITY — NOT YET EXERCISED, never fixture-qualified PASS.

Intraday ownership, source and delivery policies remain unchanged. Freeze and
review WO-13 after owning/affected qualification; integrate WO-14 against the
accepted bytes, then run one protected regression on the final combined
executable candidate. Historical WO-13-only full results do not satisfy that gate.
