# MCX-CONTEXT-01 — Twice-Daily Supporting Context V1

**Status:** Approved
**Version:** 1.0
**Owner:** KRONOS Swing
**Approved By:** Chief Architect
**Authority:** Supporting evidence only

## Decision

KRONOS Swing owns one immutable, twice-daily MCX Supporting Context evidence
family. It records bounded visual observations for research, audit, provenance,
and later outcome comparison. It has no analytical, Readiness, KR-370,
trade-construction, Risk, entry-timing, Sponsor Decision, lifecycle, notification,
broker, or execution authority.

The record family is
`KRONOS-SWING-MCX-DAILY-SUPPORTING-CONTEXT-V1` Version 1.0. The Question
contract is `KRONOS-SWING-MCX-CONTEXT-QUESTION-V1`; the Answer contract is
`KRONOS-SWING-MCX-CONTEXT-ANSWER-V1`.

## Trading-date and slot model

DOMAIN-008 is the sole MCX trading-date authority. Each governed MCX trading
date has four logical slots:

- METALS / MORNING
- ENERGY / MORNING
- METALS / EVENING
- ENERGY / EVENING

METALS binds only GOLDM, SILVERM, and COPPER. ENERGY binds only CRUDEOIL and
NATURALGAS. Families never cross-bind. A non-trading date creates no required
slot and a new trading date starts with all four slots not provided.

## Frozen composites

The METALS composite contains exactly, in order: US Dollar Index Futures / DXY
1D; US Government Bonds 10Y Yield 1D; US Government Bonds 30Y Yield 1D;
USD / INR 1D; COMEX Copper Futures 1D; USD / CNH 1D; CSI 300 1D; COMEX Gold
Futures 1D.

The ENERGY composite contains exactly, in order: NYMEX / Henry Hub Natural Gas
1D; NYMEX / Henry Hub Natural Gas 4H; USD / INR 1H; WTI / NYMEX Light Crude
Oil 1D; Brent Crude Oil 1D; DXY 1H.

These ENERGY observations do not activate or broaden NYMEX Readiness authority.
The existing candidate-specific COMEX/NYMEX reference-evidence family remains
separate and unchanged.

## Sponsor-mediated file transport

One MORNING and one EVENING Question Pack each contain both family sections.
The governed default paths are:

- `~/Documents/Project-KRONOS/KRONOS REVIEW PACK/Support Charts/KRONOS QUESTIONS`
- `~/Documents/Project-KRONOS/KRONOS REVIEW PACK/Support Charts/CHATGPT ANSWERS`

The flow is Question Pack → independent Chart Analyst → Answer Pack → strict
KRONOS validation/import. Browser owns secure local image intake and transport,
not interpretation. No additional OpenAI credential or direct interpretation
path exists.

## Question and Answer contract

METALS Q1–Q4 record exact panel validation (`MATCH`, `MISMATCH`, `UNREADABLE`),
visible direction (`RISING`, `FALLING`, `RANGE`, `UNCLEAR`), evidence quality
(`CLEAR`, `PARTIAL`, `UNREADABLE`), and visible structure (`TRENDING`,
`CONSOLIDATING`, `TRANSITIONING`, `UNCLEAR`). ENERGY Q5–Q8 use the same bounded
fields. Q9 records WTI/Brent alignment and Q10 Natural Gas 1D/4H alignment as
`ALIGNED`, `DIVERGENT`, or `UNCLEAR`.

The Answer is strict, ordered, versioned JSON embedded in the PDF transport.
KRONOS requires exact date, slot, pack identity, schema, family order, panel
count/order, independently observed identity/timeframe, and enums. Missing,
wrong, or unreadable required panels fail the family closed. No fuzzy matching,
free-form analysis, BUY/SELL, tailwind/headwind, score, RSI conclusion, event
risk, or downstream consequence is admitted.

## Immutable persistence and temporal binding

Each family/slot import creates an append-only revision. Corrections create the
next revision; no record is overwritten. An invalid import cannot replace the
latest valid record.

An MCX assessment may reference only the latest valid record for its exact
family and governed trading date whose accepted/imported boundary is at or
before that assessment boundary. Future context never binds past assessment and
later evidence never retroactively rewrites historical assessment. Before any
eligible record, presentation is `NOT AVAILABLE AT ASSESSMENT TIME`.

Records retain schema/version, record identity, product, market, trading date,
slot, family, revision, pack identities, capture/import times, bounded panel
observations, ENERGY alignments, availability, supporting-only authority, and
integrity SHA-256. This lineage permits later offline research joins through
Native assessment, KR-370, Step-31, Sponsor Decision, KR-380, KR-390, and
Step-33 without granting a live consequence.

## Browser presentation

Review shows one thin MCX CONTEXT · SUPPORTING ONLY strip with MORNING and
EVENING family statuses and bounded CREATE PDF / UPLOAD ANSWER controls. Image
inputs remain compact. Analysis Details may show the exact temporally eligible
record and must state `SUPPORTING EVIDENCE ONLY · NO KR-370 CONSEQUENCE`.

Dashboard, Settings, Telegram/UX-10, Native Discovery, V3/V3.1, Readiness,
KR-370 K1–K5 and hard gates, Steps 31–33, DOMAIN-007, ECPC, KR-380, KR-390,
Sponsor Decision, lifecycle, Risk, and broker authority remain unchanged.

## Deferred scope

Directional context policy and scheduled event risk are not commissioned.
MCX-CONTEXT-02 is reserved for any future scheduled-event-risk architecture.
No autonomous trading is authorized.
