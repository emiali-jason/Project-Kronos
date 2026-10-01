# WO-SWING-NEXT-13.1 — Existing Notifications Correction

**Status:** Sponsor-authorized engineering candidate; qualification and owner review required. WO-13 acceptance remains open. No publication, runtime load or live delivery authorization.

**Authority:** Sponsor's WO-SWING-NEXT-13.1 coordinating decisions and retained WO-13 mapping at base `8002dde347e397f04dcd31d0a121631ba46f7102`. This is an implementation record, not approval of a new event family or trading rule. ADR-0052 / Intraday WO13 Notifications remain unchanged in authority.

## Reused owners

The existing Swing UX10 service owns notification event persistence, recovery context and Telegram dispatch. The shared centre owns presentation revisions and dismissal. Existing progression and lifecycle consumers own their sessions. The Browser's existing admitted server pulse synchronizes Swing centre records and due reminder history; no new timer or scheduler is introduced. GET reads centre/owner projections and exact retained bindings only.

## Swing behavior

An existing watch card advances from PROGRESSION_WATCH to PROMOTION_WATCH_REACHED once its retained source is TRIGGERED, even though both shell states are LIVE. Identity and dismissal are preserved; factual summary, priority and presentation history change. A dismissed card is not resurrected by rereading that event. A different eligible analytical transition has its own existing UX10 source-derived notification identity. Legacy watch deletion still hides/detaches its governed source and also dismisses corresponding centre presentation cards; hidden watch delivery copies do not reappear on later pulses. Centre dismissal never calls the watch owner.

The promotion baseline retains source identity, semantic assessment digest, classification, run and ordering timestamps. The semantic digest excludes rendering/retention creation time and includes authoritative assessment content. It is not an opportunity identity and cannot authorize analysis or manufacture upstream origin. V2 retains its supplied opportunity identity in the evidence binding; V1 has no invented origin. READY→NOW can occur within one run when a changed authorized assessment supports it. Initial NOW, known replay, unchanged semantics and older assessments are silent. The caller remains responsible for supplying exact-current governed assessments. No thresholds or evaluator rules change.

Recovery context is maintained by the existing UX10 store in its `context` child: checksummed promotion/connection baselines and compact upstream source bindings. Historical notification IDs and old record integrity remain compatible. Missing legacy bindings display UPSTREAM EVIDENCE UNAVAILABLE; no historical identifiers are backfilled. Context integrity failure fails closed; it is not silently reset to an empty baseline.

Connection callbacks retain one open incident identity and its start. Repeated outage states/restart do not create another incident. A material context-gap escalation and restoration bind that incident. CONNECTED without a known open incident establishes only a baseline. Old timestamps do not create a new restoration. These callbacks prove transport observation only, never per-owner recovered continuity.

Per-card monitoring reads the exact watch or position consumer, actual registration/session state and its latest accepted session observation. No tick/unknown registration means UNAVAILABLE. Interrupted or unresolved evidence remains INTERRUPTED. Closed/inactive/stale/triggered owners are NOT_REQUIRED. Reconnection alone does not produce LIVE: continuity, previous interval and ordering must be established and the observation must not be recovered. Notifications do not register, subscribe, detach or close owners.

Every Swing card provides a separate exact upstream-evidence destination. Retained source/run/instrument/watch/plan/position identifiers are exposed only where supplied by the producer. Source bindings and notification-delivery records are distinguished from presentation history. An old run is shown as historical; a missing current run is not proof of historical or current authority. No historical route substitutes a current run alias. Compact retained source bindings do not claim that the full upstream artifact has been fetched or that historical eligibility is current.

## Telegram attempt protocol

New records use RETAINED_ATTEMPT_V1. Before transport, the existing writer retains an attempt identity and DELIVERY_UNCERTAIN state. The in-process claim prevents overlapping dispatch. Confirmed transport success becomes SENT; a crash before send, during send, or before success persistence remains uncertain on restart and is not automatically resent. The Browser notification remains retained.

Only an explicit rate-limit rejection from the existing transport is automatically retryable, within the existing four-attempt bound. Timeout, undecodable response, generic transport/configuration failure or unclassified rejection cannot prove nonacceptance; they remain uncertain. Explicit pre-send message/private-chat validation failures and disabled delivery are final. No exactly-once claim is made. Legacy pending/retryable records without the attempt protocol also fail closed to uncertainty rather than guessing whether an old process already sent them.

The shared Telegram integration and Intraday dispatcher are unchanged. No real Telegram test is required or used in this candidate.

## Qualification and integration boundaries

Focused owning and affected shared tests must bind the final candidate manifest. Include exact owner/session, progression, evidence identity/currentness, observational routes, restart/replay/dismissal, incident recovery, attempt-claim failures and Intraday preservation. Historical passing runs do not qualify modified shared bytes.

The active MCX candidate and its frozen artifacts are not changed. MCX Step31 remains held. Browser integration requires review against the final MCX diff. One combined release candidate must receive the coordinated full protected regression after shared integration; separate concurrent full regressions are not requested by this order.

Legacy Intraday WO09 fallback relocation received bounded Intraday owner approval, retained verbatim in the review output. It must never execute during constructor/startup, GET/status, or when the modern Intraday owner exists.

## R3 — connectivity recovery correction

**Status:** Sponsor-authorized bounded correction; source qualification and review are separate from WO-13 acceptance, combined regression, publication/load and live delivery.

The existing connectivity owner reconciles retained connectivity events against recovery context at construction without writing or emitting alerts. A newer retained incident or restoration supersedes a lagging checkpoint, including an older CONNECTED checkpoint. R2 `at` context remains readable; `incident_started_at` and `observed_at` now retain distinct start and latest accepted observation boundaries. Existing source bindings establish incident linkage; retained start events supply the start for R2 gap bindings. A valid duplicate observation may repair a lagging checkpoint at the existing owned observation boundary.

All supported accepted observations, including silent repeats, advance the durable observation boundary while preserving incident start and gap escalation. Older observations are rejected before incident mutation, alerts, expected-disconnect deferral or checkpoint writes. Restoration duration uses incident start. Restart/replay does not reopen an incident already restored by retained evidence.

Checkpoint publication uses a proposed copy and advances memory only after persistence succeeds. If publication raises, the owner re-reads retained events, source bindings and checkpoint bytes and reconciles them before propagating the error. A partially persisted event is therefore neither lost behind stale context nor blindly recreated. Source bindings without a retained event do not establish an incident. Reading a file after a directory-sync failure does not certify durability: the original persistence exception still propagates.

Deterministic qualification injects failures before/after source-binding, event and recovery-checkpoint writes for disconnect, gap and restoration, plus silent-observation checkpoint failures. It covers old CONNECTED checkpoint crash recovery, repeat disconnect suppression, T0 outage / T20 gap / rejected T10 restoration / valid T30 restoration, replay/restart and R2 schema recovery. Telegram attempt protocol, centre dismissal, observational GET, Intraday ownership, shared Browser files and commissioned event families remain as reviewed in R2. R3 does not modify the active MCX candidate or launch a full regression.
