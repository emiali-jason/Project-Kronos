# ADR-0065 — WO12 considered-opportunity journey reporting

Status: Sponsor-approved bounded Choice A; exact candidate qualification, independent review and EA technical acceptance remain release gates.
Date: 2026-10-11
Owner: EA-Intraday
Authority: Sponsor Daily Excel/Opportunity Chronology order and subsequent explicit Choice A clarification.

## Decision

Extend the existing explicit local WO12 publication with workbook presentation version 2.3.0 and a seventh `Opportunity_Journey` worksheet, view version 1.0.0. Preserve the six existing worksheets, their definitions and historical 2.2.0 reconstruction. This is a reporting extension to ADR-0049, ADR-0063 and ADR-0064. It changes no analytical, first-five, watch, notification, lifecycle, market-data or trading policy.

The denominator is the retained WO12 consideration cohort: an exact opportunity and original WO08 method entering WO09. It is neither the complete 98-member audit population nor only READY/NOW records. Low-count, unavailable and nonadvanced considered opportunities remain visible. The readable opportunity ID and machine opportunity identity remain distinct from the consideration identity. Existing opportunity/reset authority is unchanged.

Original prediction, direction, criteria, reasons, disposition and Assessment Price remain bound to the original admission. Progression, watch, first-five and construction/lifecycle attribution use that original direction, session, method and exact MCX contract. Later direction changes remain visible through the overall final WO09 state/direction and other-scope references; they cannot supply a target or first-five under the original direction. No new origin is invented for reversal. Original terminal directional classification remains owned by ADR-0063.

## Choice A chronology boundary

Only retained governed WO11 lifecycle events establish model Entry, Target or Stop. The current published lifecycle graph must validate its authorization, intake, predecessors and embedded events. Orphan event files do not establish chronology. Exact WO10 comparison/plan/expression links provide separately labeled constructed canonical and futures levels; construction does not imply model entry.

A unique retained track may report its retained Entry and TARGET/STOP_LOSS exit timestamp. The corresponding status is YES. Missing events, absent track, multiple tracks or insufficient coverage are NOT_EVALUABLE, never a market-path NO. Multiple tracks retain references without splicing an Entry from one with an Exit from another. OUTCOME_AMBIGUOUS cannot revive an earlier exit; monitoring gaps are explicitly disclosed. A known positive retained event remains positive despite a separately disclosed gap. TARGET_FIRST/STOP_FIRST describes the unique track's retained terminal model event, not both subsequent market touches or continuous path coverage.

No completed-candle OHLC touch inference, same-bar ordering, counterfactual execution, or continued observation after the terminal model event is commissioned. SAME_INTERVAL rehearsal is DEFERRED and excluded from V1 acceptance under the Sponsor's Choice A clarification.

## Temporal and publication boundaries

Prospective first-five observed time comes only from its retained fact. The first retained five-satisfied snapshot time is a separate field and cannot substitute for that event. A four-satisfied snapshot uses its retained observation time; a direct jump to five does not fabricate a four-satisfied snapshot. Stage measurements are explicitly analytical completed-5M closes, distinct from original Assessment Price, constructed Entry and actual model Entry price. Durations require both lawful timestamps and nonnegative order; otherwise NOT_ESTABLISHED. New-sheet timestamps display retained precision in IST.

Projection and workbook reads perform no acquisition or publication. Explicit UPDATE RESEARCH retains the existing research records and publishes through the existing lock, durability, atomic replacement and hash/readback receipt path. The new semantic row content participates in the publication source boundary, including watch/hint changes. No new endpoint, schedule, automatic Analysis, Provider request, notification or activation is introduced.

The frozen research-record policy identity/version/checksum and six-sheet `SHEETS` declaration remain unchanged for historical validation. The additive presentation version is separate. Receipt reconstruction dispatches by recorded workbook version and must reproduce the exact receipt hash; failure remains closed. Existing 2.0/2.1 records are not silently upgraded or promised new reconstruction capability.

## Acceptance and deferral

Required evidence includes baseline 2.2.0 exact-byte comparison, historical receipt recovery, source-row comparisons, considered nonadvanced/matched/false-advanced/unavailable cases, selective watch and first-five distinctions, LONG/SHORT NSE/MCX composed disposable rehearsals, governed lifecycle target/stop and ambiguity/gap protection, read-only preservation and protected owner tests. Disposable fixture evidence is not naturally occurring production activity. Production UPDATE RESEARCH is not needed for technical acceptance. IWO-UX is next; no further phase is implicitly authorized.
