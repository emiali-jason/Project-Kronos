# ADR-0064 — Experimental PAPER criteria, first-five provenance and selective watches

Status: Sponsor-approved experiment and implementation; exact-byte qualification, independent/impact-owner review and technical acceptance remain release gates.
Date: 2026-10-11
Owner: EA-Intraday
Authority: IWO-01/02/03 IMPLEMENTATION CONTINUATION; controlling design ZIP SHA-256 `4d2adb3b0800b5f9824d631a2797d380eda9c6d60842ba41b7f7f5586e706f8c`.

The prospective method is `KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER / 0.1.0`. It is experimental, PAPER-only and not established as predictively or economically useful. This decision supersedes the uncommissioned I2–I5 producer boundary prospectively. It does not rewrite ADR-0062 historical assessments, turn old records into positive assessments, or revive new WO07F intake. There is no LIVE or broker authority, no automatic position creation, and NATGAS remains HELD.

Only exact validated Native PULLBACK selections with inherited LONG/SHORT direction and normal completed 15M structure can establish positive experimental criteria. Opening and BREAKOUT are outside this method. The complete 98-member population retains negative, CONFLICTING, non-admitted and unavailable members. Integrity and storage failures remain failures, not missing analytical evidence.

## Exact experiment

Let Q be the selected qualification 15M candle, B the selected pullback extreme, T the selected prior impulse extreme, and F1/F2 the latest consecutive completed 5M candles through the analysis boundary. P is F2.close. P is a separately identified analytical measurement; it never substitutes for the immutable original Assessment Price, Entry, quote or fill.

| Criterion | LONG | SHORT |
| --- | --- | --- |
| I1 | Existing completed 1H regime and normal 15M structure support LONG | Existing completed 1H regime and normal 15M structure support SHORT |
| I2 | F1.start >= Q.end; F1.end = F2.start; F1.close > Q.high; F2.close > F1.close; F2.low > B | F1.start >= Q.end; F1.end = F2.start; F1.close < Q.low; F2.close < F1.close; F2.high < B |
| I3 | P < T and no enumerated level L satisfies P <= L < T | P > T and no enumerated level L satisfies T < L <= P |
| I4 | Every completed 15M after the pullback's right confirmation through the boundary, including Q, has low > B | Every such 15M has high < B |
| I5 | B < P < T | T < P < B |

I3 requires the complete finite population before corridor filtering: governed prior-session high/low, existing classic R1–R4/S1–S4, governed CPR boundaries/pivot, current-session completed-15M high/low, and every strict immediate-neighbour confirmed 15M pivot with its right-confirmation source. Coincident levels retain each provenance. Equality at P blocks; the T endpoint is excluded. A complete-empty pivot class differs from a missing class. This is a finite model corridor, not an assertion that all market obstacles are absent.

Schedule-backed coverage uses existing DOMAIN-008 completion semantics, including lawful shortened bars. I2 is OUTSTANDING if the schedule proves the post-Q bars cannot yet be completed, but UNAVAILABLE if expected bars are missing. Missing I3 population or I4 coverage is unavailable. A known I4 breach is not erased by subsequent recovery. No older-cycle search, ATR, percentage tolerance, extra obstacle, magnitude threshold, rolling base or statistical independence claim is introduced.

The existing candle contract establishes completion relative to the governed schedule and boundary. This experiment does not establish official publication/revision/as-of finality by implication, or treat receipt time as market-event time. Broader finality assurance remains separately governed. Missing required evidence cannot be created by adding a field or making an extra request.

## Prospective event and publication

A first-five event means the first prospectively source-validated, durably retained five-satisfied experimental evaluation for a claim. It does not mean the first instant in the market at which conditions held. The claim binds the existing opportunity identity, subject, direction, DOMAIN-008 session, exact MCX contract/roll where applicable and method tuple. The observed record also retains the exact originating run, assessment, criteria and source identities. The claim excludes run and Native cycle IDs because ordinary refreshes must not reset it.

Use the trusted observation clock. Repetition, 5→4→5 and restoration retain the original event and timestamp. Historical reads, replay, GET, notification replay and research cannot reconstruct an event. Original first-five time <= readiness observation time <= handoff time; existing first-five/handoff freshness remains unchanged. A new assessment publication time is not a replacement event time.

Upstream owner guards precede the existing root/subject WO09 transaction. Under a fixed complete expectation, verify current authority, retain or reuse the first-five fact, retain exact readiness and publish its current pointer. No automatic recapture/retry, nested public mutation or claim of multi-file atomicity is introduced. A fact retained before a later pointer failure is truthful observation evidence but grants no handoff. Handoff requires exact current assessment, readiness, pointer and first-five provenance. Storage/conflict failure produces no success notification. Notifications follow committed truth and release of source guards.

## Selective advisory monitoring

A watch requires current, otherwise eligible experimental 4/5, exactly one known OUTSTANDING I2 or I3, zero unavailable criteria and no hard gate. All98, all Probables, 3/5 and missing I4/I5 are excluded. Bind origin, assessment/readiness generation, subject/session/direction/contract, method, outstanding criterion, source lineage, start/currentness and existing session expiry. Supersession, expiry, roll, maintenance or continuity loss cannot resurrect old watch authority.

Existing WebSocket observations may establish an advisory wake hint only. They never establish a completed candle, I2, obstacle completeness, 5/5, first-five, READY/NOW or trade authority. The next separately authorized ordinary Analysis must evaluate completed evidence. No watch-triggered REST, Analysis, new socket or Provider connect/disconnect is permitted. Missing existing lawful subscription is missing delivery availability, not permission to create a connection. Shared monitoring changes must preserve existing owners and receive actual-impact review.

Hints coalesce per generation and remain distinct from commissioned WO13 READY_FOUR/READY_FIVE transitions. WO13 continues to own notification deduplication, opt-in delivery and transport. No second notification subsystem or uncommissioned Telegram event is created.

## Downstream and research preservation

Explicit versioned machine types carry experimental PAPER-only scope; no fabricated legacy visual IDs or type conversion grants LIVE authority. PAPER Position and Observation remain exactly one lot under existing lifecycle pricing. Analytical currentness applies before Entry; an entered position's monitoring, Stop, Target, Sponsor Exit, terminal handling and restoration remain independent.

WO12 associates the original prediction/Assessment Price, exact experimental criteria and reasons, actual WO09 progression, first-five, watches/hints and governed terminal-directional outcome. ADR-0063 MATCHED/NOT_MATCHED/NOT_EVALUABLE semantics remain unchanged. Excursions and progression do not redefine terminal direction. No threshold tuning, research-triggered acquisition, automatic research publication or success-only denominator is introduced.

NSE and MCX retain independent session authority. MCX requires native exact binding, session, expiry/roll and contract; supporting international references are not analytical authority. Technical commissioning and naturally occurring business events are reported separately. Absence of a real qualifying opportunity is NOT_YET_EXERCISED, not an engineering failure or evidence of predictive usefulness.
