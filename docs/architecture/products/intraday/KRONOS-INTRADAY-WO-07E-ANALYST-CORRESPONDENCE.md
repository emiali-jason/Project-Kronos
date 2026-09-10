# WO-07E - Chart Analyst correspondence engineering contract

**Status:** Sponsor-authorized engineering candidate; qualification/publication pending.
**Owner:** KRONOS Intraday.
**Authority:** [ADR-0032](../../adr/ADR-0032-INTRADAY-CHART-ANALYST-CORRESPONDENCE-SOURCE.md).
**Baseline:** de5648712adc66bbca4e25049e55f825e575eac3.

## Transport

NSE transport 2.2.0 and MCX transport 1.2.0 succeed 2.1.0 and 1.1.0 with distinct
expected filenames/transport identities. Existing retained PDFs, templates and
Answers are never rewritten. The Sponsor receives one Question PDF. The exact
structured template remains embedded and retained internally. The governed
Answer inbox and exact filename lookup are unchanged.

Analytical schema/question version 2.0.0 is unchanged. The additive field
`chart_observation_header` has schema `KRONOS-CHART-ANALYST-CORRESPONDENCE`,
version `1.0.0`. Its exact pack, cycle and chart binding are envelope facts.
For NSE the chart binding is the uploaded immutable revision. For MCX it is
the exact paired bundle, already bound to that uploaded composite and native /
reference chart revisions. Slot keys are expected layout, not observations.

Each ordered panel slot has a panel_state, right_edge observability and observed
object. States are PRESENT, ABSENT, CROPPED, LOADING, UNREADABLE, NOT_OBSERVABLE.
Only PRESENT with EXACT right edge can qualify. The observed role/timeframe
must independently match the slot. Every observed field starts null; content
observability starts UNVERIFIABLE. Fields include raw subject/venue/listed series,
currency/unit, trading date/session/timezone, exact visible start/end/completion,
capture timestamp/latest endpoint, full-panel and opinion-overlay observations,
and the existing core/optional content observability map. Null remains unknown.
No source endpoint, internal calendar ID or inferred contract is copied into it.

No exact timestamp is demanded when pixels cannot prove it. Missing temporal
facts conservatively prevent native qualification. The one-PDF protocol states
this explicitly. Q6/Q9 have no machine-selected single anchor: PDH/PDL remain
orientation, not a direction-selected barrier. Existing unavailable / UNCLEAR /
NOT_OBSERVABLE meanings, OBSERVED/PARTIAL scope, Q10/X5 and R/M/X rules remain.

## Import and persistence

The parser canonicalizes the independent header into immutable Answer data;
Answer source/identity hashes cover it. Binding and correspondence preparation
are read-only. The existing chart gate can compare a prepared receipt directly,
without requiring one on disk. Its machine expectations still come exclusively
from exact retained source/cycle/contract/session evidence.

After successful strict comparison and final producer-currentness checks, retain
one immutable receipt per chart revision, then Answer transport/evidence and
finally its current pointer. Receipt provenance binds the entire Answer digest;
it includes exact chart payload, cycle, Probables run/result and original import
receipt timestamp. Header facts are retained in the Answer and the existing
receipt codec; neither is synthesized on restart. New NSE imported evidence
marks the header dependency in its integrity-covered provenance. Restoration
checks its exact Answer and retained receipt. MCX snapshot/replay also verifies
its retained header/receipt against the exact paired Answer.

A failed receipt write cannot publish an Answer pointer. If a later Answer write
fails, a successfully validated receipt can remain as truthful immutable partial
persistence, with no new Answer authority. Exact retry reuses that original
receipt timestamp and requires the same Answer digest/panels. Contradictory
observations conflict; they do not overwrite it. Already-imported identical
replay creates no new evidence; conflicting replay rejects.

Legacy Answers without the header remain parseable and may use an already
retained independent receipt under the historical contract. They cannot pass a
missing-receipt gate. There is no new default receipt, upload-time producer,
fixture injection, historical backfill or production evidence repair.

## Qualification and exclusions

Primary E2E scenarios independently declare constructed chart observations and
use normal upload, PDF creation, exact inbox lookup and import. No observer
receipt is injected in those paths. They establish deterministic engineering
reliability, not empirical pixel-reading accuracy. The real Sponsor / Chart
Analyst check remains separate after publication.

Preserve all historical evidence, publication 1.5.0, FB02/FB03, MCX supporting
reference authority, methodology 2.2.0, Narrow CPR, 09:30 Opening, live shadow,
producer currentness and all downstream trading boundaries. No Provider,
OpenAI, Refresh, production Review/Question/Answer, restart, stage/commit/push,
FB01 or WO-07F operation is part of this engineering candidate.
