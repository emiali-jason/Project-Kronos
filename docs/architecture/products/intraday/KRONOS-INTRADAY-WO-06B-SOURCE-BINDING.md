# WO-06B — Relative-context and CPR source binding

**Status:** Implementation candidate under explicit Sponsor/EA WO-06B engineering authorization; publication review pending.

## Authority and scope

This correction enforces source integrity for the approved phase-aware Probables methodology. [WO-06A 2.2.0](KRONOS-INTRADAY-WO-06A-OPENING-ADMISSION-CORRECTION.md) remains the analytical authority. Its payload, checksum, formulas, thresholds, phase selection and admission consequences are unchanged. DOMAIN-001 supplies canonical identity; DOMAIN-008 supplies current and previous trading-session schedules. This work adds no Provider, Risk, Trade Construction, broker or OpenAI authority.

## Independently reproduced defensive gaps

At published baseline `af13782476d93928155f5471417f9a592e9ce7e7`:

- `nifty_relative_context.py:233` accepted a requested `NSE-EQ-RELIANCE` assessment with a valid `NSE-EQ-HDFCBANK` subject candle. `_aligned` checked interval and benchmark separation but did not join the requested canonical identity to the source canonical identity. A synthetic 5.00% relative return changed NOT_ADMITTED to LONG_PROBABLE.
- `opening_semantic.py:224` checked CPR subject and non-future observation but did not join CPR to the selected previous Daily. The synthetic selection required `NSE:2026-08-27:NONSTANDARD`; CPR from `NSE:2026-08-25:NONSTANDARD` changed NOT_ADMITTED to LONG_PROBABLE. The V2 semantic builder had the corresponding incomplete source check.

These are **defensive evidence-integrity gaps**, not evidence of production corruption or trading-performance defects. The normal producer constructs CPR from the exact Daily payload it supplies to the mapper; that production acquisition/construction order is unchanged.

## Exact relative-context binding

The new builder revalidates existing immutable candle identities/digests and requires the subject candle's canonical identity to equal the requested canonical identity exactly. It does not normalize `RELIANCE`, infer from display names, or treat Provider symbols as canonical authority. The benchmark independently remains `NSE-INDEX-NIFTY`; it is not required to equal the subject. BANKNIFTY remains an analytical index subject compared to NIFTY, without derivative-contract inference. NIFTY self-reference and MCX non-applicability remain unchanged.

Both supplied candles bind to their own typed DOMAIN-008 schedules, exchange, trading date, exact session and governed first completed 15M interval. Existing market, interval, completion and observation-boundary alignment still applies. The approved comparison permits distinct lawful NSE equity and NIFTY session identities; arbitrary session-string equality is not required. Missing schedule proof or a mismatched session fails closed. The mapper passes its governed subject and benchmark schedules, already retained in replay facts. No new session registry or inferred compatibility relation is introduced.

The first 15M source open must also agree with the supplied session-open value. Wrong-subject input returns the existing typed UNAVAILABLE architecture with `SUBJECT_IDENTITY_INVALID`; wrong benchmark returns `BENCHMARK_IDENTITY_INVALID`; corrupt or absent integrity returns `SOURCE_INTEGRITY_INVALID`. Required missing sources remain unavailable. Such failures cannot supply informational support or silently substitute another subject.

## Exact CPR binding

`source_binding.require_cpr_source_binding` consumes the existing completed-evidence selection, not a newly inferred calendar date. It requires exactly one selected `DAILY / PREVIOUS_SESSION_DAILY` source and revalidates its immutable payload and the existing CPR fact. It joins canonical subject, previous session, current observation session, source candle identity, source integrity and exact source H/L/C; it also enforces non-future availability and observation. The selected candle carries the timeframe, date and session proof already validated by the governed selection builder.

The DOMAIN-008 calendar source selects the actual previous trading session, including weekends and exchange holidays. No date-minus-one rule is added. A CPR fact from an older, future, foreign-subject or different-identity Daily fails even when the numerical CPR values are equal. Missing provenance or tampered integrity fails closed. Both Opening and later-phase semantic builders enforce the check. The production mapper retains a per-member `MANDATORY_EVIDENCE_UNAVAILABLE` result with a bounded CPR binding/integrity reason and continues independently valid members.

One immutable CPR fact may be reused across same-session Opening/Structure assessments when its selected Daily identity and integrity remain unchanged and its observation is lawful. No recalculation or acquisition is required by this guard. Pivot, width, Narrow CPR threshold and admission consequence remain unchanged. Opening additionally requires relative evidence to name its exact selected first 15M source, and semantic composition checks the matching CPR and relative-evidence identities plus nested integrity.

## Explicit evidence versioning and replay

| Contract | Historical | New processing |
| --- | --- | --- |
| Analytical methodology | 2.0.0 / 2.1.0 / 2.2.0 retained | **2.2.0 unchanged** |
| Source-binding builder policy | 1.0.0 | 1.1.0 |
| NIFTY fact/evidence and Opening fact/evidence | 1.0.0 | 1.1.0 |
| V2 semantic evidence envelope | 2.0.0 | 2.1.0 |
| Discovery-to-Probables mapper policy | 2.0.0 | 2.1.0 |

New live composition defaults to the strict builder and mapper policies; operational requests cannot select a legacy bypass. Replay explicitly selects the retained envelope's mapper policy and original methodology. Methodology alone cannot determine source-binding semantics because historical 2.2.0 evidence already exists. Legacy builder selection is for exact historical/research reproduction. The frozen MCX research caller and retained WO-10 test fixture explicitly select their old builder contract; research and WO-10 analytical policy are unchanged.

Existing persisted types and version fields are reused. No historical artifact bytes or current pointers are migrated. The existing 108 pre-WO-06A historical golden cases remain unchanged; an additional 54 pre-WO-06B 2.2.0 run hashes were captured before editing and are retained as immutable test expectations. New version artifacts restore through existing persistence machinery.

## Qualification and retained evidence limits

Focused tests cover exact canonical and benchmark separation, LONG/SHORT, NIFTY self-reference, BANKNIFTY, Provider-label non-authority, missing/tampered sources, lawful distinct published NSE sessions, wrong CPR source/session/day, equal-value wrong sources, same-session reuse, Monday/Friday and Republic Day holiday selection, nested binding integrity, isolated mapper rejection/restoration, and the 54 historical 2.2.0 goldens. WO-06A truth-table and WO-05 trusted-time/accounting/runtime tests remain required, including lawful 09:30 Opening without a completed current-day 1H.

The read-only audit covers nine retained production runs (882 member records) and 11 replay envelopes. Combined applicable binding coverage: 583 verifiable, zero invalid, 299 unverifiable. CPR alone: 666 valid, zero invalid, 216 unverifiable. Relative context: 86 valid, zero invalid, 299 unverifiable and 497 non-applicable/later-phase records. Unverifiable means absent retained mapping/source proof or an already-unavailable comparison; it is not counted as valid and does not establish corruption. No claim extends beyond this inspected population.

The current retained run `INTRADAY-PROBABLES-V2-RUN-35EA4FEE81D7368AE2441A794479F294A0C02B8239DAED71525420EAFA151F85` has 98 subjects, 97 evaluable, eight admitted (three LONG, five SHORT), one unavailable and 89 not admitted. It is a 2.1.0 later-phase run. Read-only strict-binding comparison preserves all 98 state/direction/reason outcomes, with no new binding rejection. The 2.2.0 shadow likewise retains eight admitted. No shadow is published.

Eight retained runs replay exactly from their envelopes. One older 2.0.0 run has a pre-existing MCX commissioning replay discrepancy, separately checked against published baseline code; it must not be represented as an exact historical replay or silently repaired by WO-06B. The WO-06B legacy builder path preserves the published baseline replay result. Retained evidence itself remains immutable.

Full focused/affected/active-suite counts, candidate hashes, syntax/diff/secret checks and production inventory comparison are returned with the engineering report. Publication and runtime acceptance require separate Sponsor/EA authority. WO-06C and later work remain unstarted.
