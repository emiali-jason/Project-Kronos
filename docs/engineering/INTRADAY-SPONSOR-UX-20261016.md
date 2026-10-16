# Intraday Sponsor UX — 16 October 2026

**Status:** Engineering candidate, unpublished; independent/affected-owner review pending.

Work order: KRONOS-INTRADAY-SPONSOR-UX-20261016-01. Sponsor: Imran. Issuing owner: EA-Intraday V8. Base: `58fcc5626613eb08bb3a84bfae32a68ba3672059`.

This candidate changes Intraday presentation over existing validated read models. Intraday V1 retains its later `CLOSED_WITH_AUTHORIZED_HOLDS` programme disposition. Candidate behavior is not deployed behavior.

## A — Machine Review controls

Both the current Secondary Review table and complete Diagnostics table have independent, local controls. Security search includes retained canonical subject and exact MCX contract identities. Direction, actual score, displayed status/current-versus-retained context, outstanding criterion and monitoring filters compose with optional Assessment Price bounds. Security, score and price sorting preserve assessment/detail pairs, expanded details and candidate anchors. Clear All restores the original order/population and clears the Diagnostics Secondary Review-only toggle.

Unavailable and not-applicable scores remain non-numerical, separately selectable and sorted after numerical values in either direction. Price comparison uses exact normalized decimal strings, including exponent notation; missing prices never become zero. Only the retained projected Assessment Price is used. No fresh quote or experimental P substitution occurs.

Controls operate over rows already rendered. There are no new store scans, requests or publication operations. Labels, native keyboard controls, live result counts, empty-result feedback and a no-script explanation accompany readable evidence. Primary Opportunities retains only eligible current READY/NOW; controls are on Machine Review/Diagnostics.

## B — Visible operation duration

Opportunities displays the latest retained attempt's result, explicitly labeled Analysis boundary and completion time, owning-operation duration and retained analysed population. Every field comes from one entry in the existing bounded newest-five Analysis History projection. Duration requires retained provenance/accounting identity and operation-accounting authority. Missing timing/binding displays unavailable. The last successful population's boundary is still shown separately, never combined with a different failed attempt's timing. Exact timing remains in expandable history.

The existing `analysis_history_entry` producer verifies accounting identity, Discovery run and Analysis boundary. This candidate does not change that producer or infer click/request/render duration.

## C — Historical machine discovery: design stop

No C implementation is included. Complete historical WO08 populations are readable by exact run identity, and WO09 readiness records by exact readiness identity. Existing current pointers, bounded recent Analysis history and stable opportunity origins do not provide a complete bounded historical assessment-to-readiness catalogue. `Wo09Store.load_notifications` scans all source files and returns the latest per subject. It cannot serve as the requested bounded original READY/NOW history.

Implementing dated discovery with original score, retained price and notification lineage therefore requires a separately reviewed bounded catalogue/read contract and explicit composition decision. No persistent index, arbitrary symbol/time join, current monitoring substituted for historical monitoring, or unbounded GET scan is introduced. The existing legacy visual-history route and historical evidence access remain unchanged. The review package records the exact source-level gap and proposed next design decision.

## Ownership and protected boundaries

Changed production paths are the Intraday-owned `browser/intraday_wo08.py` and new pure `browser/intraday_machine_controls.py`. Shared Browser server, wrapper, routing, CSS, canonical composition, Provider, session/calendar, persistence and runtime are unchanged. PCP review of rendered behavior and EA-Intraday exact-byte review remain required; affected shared/Swing protection results are engineering evidence, not owner approval. No independent approval is claimed.

WO08 methodology, I1–I5, first-five, WO09 eligibility, watch/WO13 notification authority, WO12 denominator, WO11/WO17 entered-position safety, NATGAS HELD, exact MCX bindings and immutable original evidence remain outside the changed implementation.

## Qualification and release boundary

Repository tests use `tools/kronos_test.py` and disposable stores. The local review package retains exact commands, final and intermediate JUnit/logs, source/base copies, complete patch, hashes, preservation scope and rendered HTML fixtures. An isolated DOM contract harness exercises the actual client handler; it is not a visual browser result. The browser URL policy rejected the disposable `file:` page, so desktop/narrow visual browser rehearsal remains unverified and must be completed through an approved rehearsal surface before final UX acceptance.

No commit, push, publication, installation, production package build, runtime/maintenance transition, production HTTP, Provider operation, Analysis, notification, research publication or position/trading operation is authorized or performed under this candidate order. Release and production acceptance require separate instructions after applicable reviews.
