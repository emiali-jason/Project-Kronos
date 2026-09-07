# WO-06A — Opening admission policy / implementation correction

**Status:** Implementation candidate; explicit Sponsor/EA WO-06A policy correction authorized; publication review pending.

## Governing policy and confirmed mismatch

The approved [phase-aware methodology](KRONOS-INTRADAY-WO-06E-PHASE-AWARE-PROBABLES-V2-METHODOLOGY.md), section 4, and its [frozen payload](KRONOS-INTRADAY-WO-06E-PROBABLES-V2-METHODOLOGY-PAYLOAD.json) require valid mandatory evidence, Narrow CPR, a directional first completed 15M candle and combined support. Combined relationships use conflict dominance, then any applicable support, then informational.

At published revision `3a4a5fb3d545a0a6c24d3fec97bbb2d83faaefab`, `src/kronos/intraday/probables_v2.py:1052` additionally rejects every Opening 5M relationship other than SUPPORTING. A LONG or SHORT Opening with supporting prior 1H, informational 5M and informational NIFTY therefore incorrectly rejects despite combined support. Classification: **POLICY / IMPLEMENTATION MISMATCH**. This correction implements existing approved policy; it introduces no trading-performance claim.

## Governed correction publication

Version **2.2.0** succeeds **2.1.0** for newly evaluated runs. Its [payload](KRONOS-INTRADAY-WO-06A-OPENING-CORRECTION-V2.2-METHODOLOGY-PAYLOAD.json) has canonical JSON SHA-256 `e7f8bd9316571148b39183e47220e97982d9a956e0309469d3aa9d4e8573a0e9`. The publication identity is `INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-E7F8BD9316571148B39183E47220E97982D9A956E0309469D3AA9D4E8573A0E9`.

The payload records this bounded correction and inherits unchanged predecessor semantics. It does not supersede the historical evidence meaning of 2.0.0 or 2.1.0. Their constants, publication checksums, provenance, admission branches and persisted identities remain intact. Explicit `create_probables_v2_methodology(version=...)` selects a retained publication; the default selects 2.2.0. `legacy=True` retains exact 2.0.0 compatibility. Replay-envelope mapping selects the envelope's original version rather than the current default. Evaluation of that mapping must supply its matching methodology; mismatched evaluation fails closed.

Current Browser request metadata, request validation, diagnostic envelope creation and ordinary new mapping/evaluation use 2.2.0 consistently. Restoring an existing run does not re-evaluate it or advance a current pointer. No persisted production run is rewritten by engineering.

## Exact admission rule

Applicable inputs are prior completed 1H, Opening 5M and governed NIFTY relationships:

| Relationship set | Combined | Opening admission, after all other gates |
| --- | --- | --- |
| Any conflict | CONFLICTING | NOT ADMITTED |
| No conflict, at least one support | SUPPORTING | LONG/SHORT PROBABLE according to first completed 15M |
| No conflict or support | INFORMATIONAL | NOT ADMITTED |

5M evidence remains mandatory. Its relationship may be INFORMATIONAL when another applicable relationship supplies support. Missing evidence never becomes informational. A 5M conflict still blocks through the existing validated combined relationship. The correction uses that existing calculation, with no new relationship engine.

The existing historical `OPENING_5M_NOT_SUPPORTING` rejection is retained for 2.0.0 and 2.1.0. Under 2.2.0, combined non-support without an earlier conflict reason uses `OPENING_RELATIONSHIP_NOT_SUPPORTING`. Directions never flip because of a conflict.

## Preserved boundaries

- LONG and SHORT use identical logic.
- NIFTY itself remains NOT_APPLICABLE for self-comparison; this supplies no support.
- Required prior completed 1H, three Opening 5M candles, first 15M, previous daily/CPR and applicable NIFTY evidence retain existing fail-closed checks.
- At trusted/requested 09:30 IST, the 09:15–09:30 15M and three constituent 5M candles are complete. Prior completed 1H context is allowed; forming current-day 1H is excluded. Opening need not wait for a current-day completed 1H.
- Future admission at trusted 09:29/requested 09:30 still rejects before acquisition, with no tolerance.
- Completion-driven phase selection, all later phases, Narrow CPR formula/threshold/authority, MCX commissioning and Provider acquisition order remain unchanged.
- WO-06B source-subject/source-day defenses, assessment-price provenance, outcome measurement, VWAP and downstream trading authority are outside this correction.

## Qualification and retained comparison

`tests/unit/intraday/test_opening_admission_correction.py` tests all 27 relationship combinations for both directions, both historical versions against 108 pre-edit artifact hashes, immutable restoration, missing evidence, NIFTY self-reference, Narrow CPR, later-phase equality, payload integrity, replay version selection and non-directional 15M rejection. Historical golden hashes were captured from the published baseline before modification; they must not be regenerated to accommodate changed historical results.

The retained production run `INTRADAY-PROBABLES-V2-RUN-35EA4FEE81D7368AE2441A794479F294A0C02B8239DAED71525420EAFA151F85`, at `2026-09-07T10:53:59.014257+00:00`, uses 2.1.0: 8 admitted (3 LONG, 5 SHORT), 97 evaluable, NATGAS unavailable. All 98 subjects are in CURRENT_SESSION_ESTABLISHED. Exact old-version replay reproduces the complete run. Read-only 2.2.0 shadow evaluation yields the same 8 admitted, zero additions/removals and all 98 member outcomes unchanged. This later-phase comparison does not measure Opening population impact.

The accepted Opening research artifact has 372 rows (93 subjects × 4 sessions). Its independently recounted 241 combined-support rows comprise 190 informational-5M and 51 supporting-5M rows. These are **research relationship states only**, not 190 excluded production Probables, trades, winners or profitable opportunities; the artifact does not apply every final admission gate or outcome.

Focused/affected, WO-05A and complete regression results, syntax checks, changed-scope secret scanning and byte-preservation evidence are returned in the WO-06A candidate report. Publication, production acceptance and WO-06B require separate Sponsor/EA action. No runtime restart or live operation is authorized by this candidate.
