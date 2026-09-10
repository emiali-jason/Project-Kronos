# WO-07E — Temporal correspondence contract correction

**Status:** Sponsor-authorized engineering candidate; qualification and publication gates separate.
**Authority:** [ADR-0033](../../adr/ADR-0033-INTRADAY-VISUAL-TEMPORAL-CONTRADICTION.md).
**Baseline:** fa9f3a4558ca8d0c0507ab6c42f2f6db939d8611.

## Machine and visual authority

Machine facts remain exact: analysis boundary, expected trading date, selected
completed source candle start/end, canonical session/timezone/calendar and
ordered panel/timeframe set. The existing DOMAIN-008/source integrity, source
availability, exact subject/contract binding and lawful MCX 4H aggregation checks
run unchanged. Missing native source remains unverifiable; visual compatibility
cannot supply it. Daily/prior completed 1H context remains lawful at 09:30.

Analyst facts are independent pixels: observed identity/venue/timeframe, readable
panel/core content, full right edge, visible temporal labels and explicit findings
on later, forming, stale or other conflicting evidence. Raw display timezone or
session labels are retained without requiring IANA/canonical string equality.

candle_start, candle_end, latest_visible_end, trading_date, session, timezone,
completion and captured_at may remain null where not visible. They are never
filled from expected data. Supplied aware timestamps/date/completion still
undergo applicable future, chronology, stale-context and selected-source checks.
No tolerance, fallback or approximate exact endpoint is introduced. An explicitly
observed qualified trading date must match the selected source day, and an exact
latest qualified endpoint must match the selected completed endpoint even when a
later observed value remains before the analysis boundary. Raw axis/display dates
and blank ticks belong in visible_labels, not qualified-candle fields.

## Header 1.1.0

Every observed panel gains nullable temporal_context. A non-null object has
exactly these fields, no extra keys:

| Field | Type and meaning |
| --- | --- |
| context_sufficient | true/false/null; sufficient full visible context for the window contradiction check |
| visible_labels | 0–16 distinct readable label strings, not machine orientation |
| later_evidence | PRESENT / ABSENT / UNKNOWN |
| forming_evidence | PRESENT / ABSENT / UNKNOWN; countdown/live marker means PRESENT |
| forming_excluded | true/false/null; whether visibly separated from all qualified evidence |
| excluded_forming_date | visible YYYY-MM-DD or null, never inferred from machine endpoint |
| other_contradiction | PRESENT / ABSENT / UNKNOWN, including stale/conflicting visible context |
| basis | nonempty visible-evidence explanation or null |
| exclusion_basis | nonempty explanation of forming/qualified regions or null |

Strings are trimmed and bounded to 2000 characters. Template defaults are
unknown/null/empty, never positive. ABSENT is an affirmative supported observation,
not lack of a finding. A blank future tick is not a future candle. Null context
retains the stricter old temporal path; it is not a compatibility shortcut.

## Outcomes and fail-closed rules

CONFIRMED_COMPATIBLE requires context_sufficient=true, readable labels and basis,
later_evidence=ABSENT, other_contradiction=ABSENT and no prohibited forming scope.
The panel's strict role/identity/timeframe, core content and source checks must
also pass for native overall correspondence. A temporal result alone grants no
analytical, Promotion or trading authority.

VISIBLY_CONTRADICTED covers known later-day, later completed candle, future exact
time, stale native context, inconsistent optional exact endpoint/chronology,
qualified INCOMPLETE candle or non-excluded forming evidence. Known contradictory
facts override a supplied assertion of compatibility.

INSUFFICIENT_VISUAL_EVIDENCE covers unknown findings, missing labels/basis,
uncertain scope, incomplete coverage or unproven forming exclusion. Missing or
cropped panel/right edge is rejected before preparation; unreadable temporal
axis fails core content even if temporal findings claim compatibility.

Forming evidence PRESENT can be excluded only when forming_excluded=true, visible
same-window date and nonempty exclusion_basis establish the unqualified region.
A later-day chart or completed future evidence remains rejected. With forming
ABSENT require forming_excluded=false and exclusion fields null. Absence of a
countdown alone proves nothing. Every analytical answer must use only qualified
completed evidence under unchanged OBSERVED/PARTIAL rules.

Reference panels retain explicit visual findings but have no invented native
calendar/independent source. Their optional aware temporal facts and known visual
contradictions are checked. Independent correspondence remains
NOT_INDEPENDENTLY_ESTABLISHED in every case; insufficient visual context is not
silently accepted through that reference exception.

## Successor transport and persistence

NSE transport 2.3.0 succeeds 2.2.0. MCX 1.3.0 succeeds 1.2.0 using a separate
immutable pack-transport pointer namespace. New header 1.1.0 cannot be imported
under an old transport commission. Restored old transports remain readable.
The one PDF embeds the exact internal template and full Answer Protocol; the
Sponsor does not manage another input JSON file. Exact Answer lookup is unchanged.

Receipt schema 1.1.0 retains context and existing source/Answer/chart bindings.
Legacy receipt serialization omits the added null field, preserving exact bytes.
Old header 1.0.0 cannot carry the new field; legacy null endpoints remain
unverifiable. Successful receipts/Answers restore and replay immutably. Failed
imports cannot create a receipt or current Answer pointer. Existing historical
imports retain their original authority and bytes.

## Minimum current Sponsor presentation

1. Use the current Opportunities-bound Review and its one Question PDF.
2. Capture the matching subject with NSE 1D/1H/15M/5M, or paired MCX rows at
   1D/4H/15M/5M. Keep readable titles, venue/timeframe, dates/time-axis labels,
   full right edge, price axis, candles and context. Do not type machine times
   onto the image. No particular chart vendor or Replay product is mandated.
3. Capture for the same analytical window; same date alone is insufficient.
   Exclude a forming region from the presentation, or make its separation from
   all qualified completed evidence visually unambiguous. Never hide later-day
   or completed future evidence with an exclusion claim.
4. Analyst reports only visible facts and explicit unknowns. If the viewport
   cannot establish the contradiction check, improve the presentation; do not
   guess timestamps or force an Answer. Historical/later-live mixing rejects.

## Qualification and preservation

Predeclared chart-equivalent images cover aligned, later-day, future candle,
forming, countdown, cropped edge, unreadable temporal axis, wrong timeframe and
wrong identity for fresh ADANIGREEN and BANKNIFTY. Positive exact temporal fields
are all null. Separate tests cover optional factual contradiction, strict codec,
missing machine source, exclusion, old edition binding, immutable replay and
five-family asymmetric MCX import. Drawings are engineering fixtures, not real
Sponsor images, OCR outputs or empirical Analyst responses.

The real 10 September ADANIGREEN REV002 chart against a 9 September Review stays
negative evidence. No import retry, byte repair, observation backfill or
reclassification occurs. Full regression preserves methodology 2.2.0, Narrow
CPR, 09:30, currentness, live shadow and trading boundaries. No runtime/Provider/
Refresh/Review/Question/Answer/OpenAI/broker production operation is authorized.
