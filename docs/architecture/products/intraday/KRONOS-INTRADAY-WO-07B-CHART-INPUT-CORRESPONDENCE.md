# WO-07B — Chart input correctness and observability

**Status:** Sponsor-frozen engineering scope; implementation candidate, pending qualification/publication review.
**Owner:** KRONOS Intraday.
**Authority:** Sponsor WO-07B sections 1–58, 8 September 2026.
**Baseline:** `a00a0a9fef0107b734fea7229d192fb95c473093`.

## Problem and boundary

WO-07A established that a received chart digest and exact Review association do
not prove the time, identity or completeness of the pixels. This candidate adds
a chart correspondence gate before NEW operational V2 visual evidence is retained.
It does not qualify a trade, change an analytical conclusion or alter admission.
The accepted WO-06H window, methodology 2.2.0, Narrow CPR and 09:30 Opening remain
unchanged. No source from another Review or a later observation fills a gap.

The governing audit is the external `Project-KRONOS/output/WO-07A/WO-07A-AUDIT.md`.
Its immutable chart, exact inbox, existing questions and historical-evidence
NO_CHANGE requirements are preserved. Existing product documents and ADR-0018
remain the identity authority. This is a bounded implementation of the frozen
Sponsor contract, not a new shared architectural decision.

## Frozen chart families

NSE: one composite containing 1D, 1H, 15M and 5M. Candles, readable identity,
exchange/timeframe, axes and contextual lead-in are core. Volume, CPR and factual
technical/reference overlays remain permitted. Their exact values remain machine
facts. An absent optional overlay is not absent market structure.

MCX: top international/reference row, bottom native MCX row; each has 1D, 4H, 15M,
5M. Preserve currency/unit context and currently visible RSI. Do not relabel 4H as
1H. Keep the existing generic paired registry and contract binding. No question,
RSI interpretation, PDF, Pine or Browser layout change is made.

BUY/SELL/WATCH/READY, confidence, scores and recommendation tables are excluded
from the future Analyst input. Observed presence prevents input qualification;
unknown absence remains unproven. Historical pictures are not edited or deleted.
There is no OCR, image rewrite or automatic opinion-label detector in this slice.

## Expected and independently observed evidence

`IntradayChartInputGate` loads the exact retained cycle, handoff, Probables run,
result, mapping, completed selection and chart binary. It checks the result's
membership in that run and the complete selection/subject/boundary association.
It never consults the latest producer pointer to decide Review currentness.

For each required role/timeframe, it selects the last completed candle in that
exact governed selection. Daily and prior-session 1H remain lawful at Opening;
no forming current-day hour is required. DOMAIN-008 supplies source session,
timezone and permitted candle endpoints. Missing source/session is UNVERIFIABLE.

`ChartInputObservation` is a separately versioned, machine-bound receipt of
independent observations. It is NOT a Q1–Q10 or M/R/X Answer schema. Its envelope
binds revision, payload digest, Review cycle, Probables run/result and observation
provenance. Each panel independently retains raw visible subject, venue, timeframe,
reference listed series where applicable, currency/unit, date/session/timezone,
start/end/completion, capture time, last visible endpoint, full-panel coverage,
opinion-overlay presence and content observability. No internal hash is asked
as a visual observation. Missing values remain null, not inferred defaults.

The explicit store method accepts a receipt from a separately governed independent
observation producer. No Browser route, Answer parser, upload, currentization,
GET or startup constructs a receipt from expected metadata. Engineering fixtures
supply synthetic observations and do not constitute real pixel qualification.
No production observation acquisition mechanism is newly authorized here.

## Identity and MCX reference treatment

Raw visible identity and machine canonical identity remain separate. Reuse the
exact, effective-dated DOMAIN-001 resolver; no alias dictionary, punctuation
normalization or Provider symbol fallback. M&M does not become MANDM/M_M/M AND M.
NIFTY/BANKNIFTY remain analytical indices; volume proxies are not manufactured.
Missing/ambiguous visual relationship is UNVERIFIABLE, not a forced match.

Native MCX resolves to the governed derivative contract independently of intended
metadata. The existing receipt-effective native relationship remains separate
from the analysis-time temporal comparison. A September relationship cannot prove
historical pixels or make a June series valid.

Reference observed commodity/display identity resolves independently to the
registry's reference analytical subject and exact venue. Raw listed series is
retained separately and must agree with the Answer's raw reference observation.
There is no listed-series-to-continuous constituent membership claim or test.
Production reference relationships are not invented by this candidate. Missing
lawful context relationships remain UNVERIFIABLE. Synthetic CRUDE/NGAS fixtures
qualify the mechanism, not new production publications.

## Existing validator reuse and conservative results

`compare_completed_panel_time` extracts the existing exact comparison from
`validation.py::_panel_temporal`. Existing factual requests, records, codecs,
required facts and conservative outcomes are unchanged. The chart gate uses the
same comparison after source/session checks rather than copying its algorithm.

Source must be complete, available by analysis, and exactly match subject,
timeframe and DOMAIN-008 schedule. Observed endpoints/session/timezone must match
it. Capture follows the source endpoint and precedes receipt; independent observation
follows receipt and must not occur after the import check's clock. No tolerance.

A visible endpoint after analysis is NOT_VALIDATED. Missing endpoint, incomplete
latest candle, missing capture evidence or incomplete panel coverage is UNVERIFIABLE.
Even a matching selected candle cannot prove absence of later pixels: full-panel
coverage and the latest visible endpoint must be independently retained and agree.
Sparse axis labels and the words “completed chart” cannot supply this evidence.
Later screenshot receipt alone neither proves nor disproves future contamination.

The pure adapter accepts existing Market `DerivedBarEvidence` for 4H and reuses
`derive_session_four_hour_bars` to verify its governed bucket/constituent boundaries.
It does not introduce a new 4H session clock or claim TradingView numeric equivalence.
The current operational Probables selection supplies neither a reference-market
source nor a 4H source. Those slots stay UNVERIFIABLE; 1H/native sources never fill
them. No acquisition or new source producer is introduced to hide this limitation.

## Content and uncertainty

Core content: candles, identity, timeframe, price axis, time axis, contextual lead-in.
Each must be exactly observed/readable. A cropped or incompletely examined panel
cannot prove core correctness. Optional inventory: volume, CPR, SMA, VWAP, RSI,
factual levels. `ContentRequirement` distinguishes CORE_REQUIRED, QUESTION_REQUIRED
and OPTIONAL. WO-07C may supply a bounded question-required mapping; this candidate
freezes none. Missing/loading optional content leaves unrelated core observations
intact; the projected content state remains available for later question handling.
No indicator arithmetic, threshold or opinion score is calculated.

## Persistence and import integration

The existing Review V2 store adds `chart-input-observations`, one immutable sealed
receipt per exact chart revision. No new chart store, session service, identity
registry or current pointer exists. Canonical JSON and SHA-256 bind receipt content;
exact replays are idempotent and conflicting bytes cannot overwrite it. Independent
re-observation with conflicting facts requires a new immutable chart revision.

Bounded descriptor-based reads reject symlinks at every ancestor/final component,
non-regular files, oversized/changing files, traversal and corrupt content. Atomic
no-clobber publication protects concurrent store instances. A failed receipt write
moves no chart or Review pointer. Bytes and machine/visual identity are rechecked
at import, not trusted from a caller-supplied VALIDATED flag.

Both ordinary individual/batch and paired V2 operational import require validated
core identity/temporal correspondence before retaining new imported visual evidence.
Standard imports recheck the receipt immediately before per-member evidence writes.
Existing schema, native identity, exact filename, idempotency and conflict checks
remain. Existing historical imported evidence and identical replay remain untouched;
absence of a new receipt never upgrades old evidence into temporal qualification.

The original paired engine's pure contracts and lower-level historical persistence
remain available for restoration/codec qualification. The current operational entry
is the Review V2 paired adapter, which enforces the new gate before calling that
engine. No production bypass flag is provided.

## Current coverage and deployment consequence

Existing chart bytes and Q Answers lack this independent panel receipt. Newly
attempted imports under this candidate therefore remain conservatively unqualified
unless all required proof is lawfully retained. Existing imported Answers remain
readable and immutable. The current eight-latest/nine-retained Review divergence is
not changed. No receipt is backfilled from WO-07A screenshots or later market data.

This is a correctness capability, not a claim that current production charts are
qualified. Later operational deployment must acknowledge the proof-availability
requirement. No receipt capture UI, Analyst operation or runtime activation occurs
in WO-07B. Missing real coverage is a truthful data/authority limitation, not an
invitation to weaken the gate.

## Handover and exclusions

WO-07C: consume per-panel observability and decide bounded independent evidence
collection, question-required context and successor Answer contract after Sponsor
freeze. Q1–Q10 and M01–X01 are byte-identical in this candidate.

WO-07D: Browser card/grid/preview/navigation improvements remain unstarted.
PDF presentation is unchanged; exact existing pack/chart association is sufficient
for the machine gate and no extra PDF change is required.

WO-09: latest-producer policy, stale imports after producer advance, rejected-import
receipts and final reconciliation currentness remain wholly separate. No latest
Probables recheck or producer-race policy is implemented here.

WO-08 remains reserved for TradingView/Astra. No current correctness defect is
silently deferred into that successor. No Swing runtime, Provider/shared maintenance,
live-shadow, retention/purge, Excel, methodology or broker behavior changes.

## Qualification scope

Run new identity/temporal/content/receipt/import tests, the full existing panel
validator tests, affected Review/MCX/DOMAIN-001/DOMAIN-008/Browser/WO-06H/accounting
regression, then the complete active `tests/` tree with frozen source/test hashes.
Record exact counts/durations and static/security checks externally. Retired
`archive/` tests are not part of the active suite. Production baseline is inventoried
before/after; concurrent additions are separately preserved and never attributed
without evidence. Publication and runtime acceptance require separate Sponsor gates.


## WO-07B-MCX — Sponsor asymmetric authority correction (9 September 2026)

**Status:** Sponsor-approved bounded engineering requirement; candidate pending qualification/publication review.

This decision supersedes the earlier requirement above for independent machine
correspondence on all eight MCX panels. Native MCX remains primary: all four
native 1D/4H/15M/5M panels require independent machine correspondence. International
reference panels remain present as SUPPORTING_VISUAL_CONTEXT_ONLY. Their independent
correspondence is explicitly NOT_INDEPENDENTLY_ESTABLISHED, never VALID/VERIFIED.
Exact reference commodity/venue/visible identity and core observability still apply;
known future/forming, wrong or cropped evidence cannot pass by being a reference.
Missing international market-source/session evidence is not fabricated or promoted.

Native 4H now consumes exact contract-bound retained native hourly candles through
the existing governed Market aggregation path. It never relabels one hourly candle
as four hours. See [the bounded source/authority contract](KRONOS-INTRADAY-WO-07B-MCX-ASYMMETRIC-CORRESPONDENCE.md)
for constituent, calendar, cutoff, partial-bucket and persistence rules. The prior
source-gap finding remains historically true; this correction supplies native 4H
and changes only the reference authority requirement by direct Sponsor decision.

## WO-07E source decision successor - 10 September 2026

The separate pre-Answer producer prerequisite above is superseded by
[ADR-0032](../../adr/ADR-0032-INTRADAY-CHART-ANALYST-CORRESPONDENCE-SOURCE.md).
The Sponsor-assisted Chart Analyst Answer supplies the independent observations.
After exact import-time validation, KRONOS retains them through the existing
immutable receipt store. Upload itself supplies no independent visual facts.
All comparison, identity, temporal and MCX asymmetric boundaries remain in force.
