# Native structural selection policy V1

## Current authority — ADR-0042

Status: Approved bounded engineering by direct Sponsor / EA authorization, 2026-09-11.

Native policy 1.0.0 and its deterministic checksum/rules remain unchanged. The monetary-input blocker described in the earlier text is superseded: final WO10 uses advisory Risk. Exact MCX monetary facts may be unavailable independently while valid Future construction/selection remains possible. NATGAS remains HELD. No current historical candidate is classified or backfilled.

See [ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) and [advisory Risk policy](KRONOS-INTRADAY-WO-10-ADVISORY-RISK-POLICY-V1.md).

## Preserved predecessor text

Authority: [ADR-0041](../../adr/ADR-0041-NATIVE-PULLBACK-V1-COMMISSIONING.md).
Policy: `KRONOS-INTRADAY-NATIVE-STRUCTURAL-SELECTION-POLICY / 1.0.0`.
Programme: `KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2`.
Contract: `NATIVE_STRUCTURAL_SELECTION_V1 / 1.1.0`; historical 1.0.0 remains readable.

## Deterministic selection

| Rule | LONG | SHORT |
|---|---|---|
| Origin | confirmed local LOW L0 | confirmed local HIGH H0 |
| Impulse | later confirmed HIGH H1 > L0 | later confirmed LOW L1 < H0 |
| Pullback | later confirmed LOW L2 > L0 | later confirmed HIGH H2 < H0 |
| Qualification | first candle after L2 confirmation with close > previous HIGH | first candle after H2 confirmation with close < previous LOW |
| Invalidation | any completed LOW <= L0 after origin through Q | any completed HIGH >= H0 after origin through Q |
| Entry / stop / native target | Q HIGH / L2 LOW / H1 HIGH | Q LOW / H2 HIGH / L1 LOW |

Pivots use strict immediate-neighbour comparisons on completed governed 15M candles. The right neighbour must be complete. No forming/future candle, wrong subject/session, duplicate, unordered or gapped source is accepted. The latest qualification completion wins; distinct cycle identities tied at that completion fail closed. No secondary optimization or alternative target selection is allowed.

All role references are selected by Native publication. WO-10 validates only the retained chosen cycle; it never searches alternatives. A non-forward native target remains a geometry failure. BREAKOUT is NOT_COMMISSIONED_V1 even if a barrier happens to break. No new range policy or breakout publication exists.

## Source manifest and completeness

Every required class has explicit applicability, availability, exact source/integrity, reference kind, field/level, forward flag, inclusion and reason.

| Class | Reference kind | Authority |
|---|---|---|
| SETUP_NATIVE_TARGET | SETUP_NATIVE_CANDLE_LEVEL | exact prior impulse candle |
| PDH_PDL | PRIOR_SESSION_LEVEL | governed previous-session Daily candle |
| CLASSIC_PIVOTS | DERIVED_PIVOT_LEVEL | previous-session fact and existing Classic R1–R4/S1–S4 formulas |
| CURRENT_SESSION_EXTREMES | CURRENT_SESSION_LEVEL | existing explicit session-extreme authority only |
| GOVERNED_15M_BARRIERS | GOVERNED_STRUCTURAL_BARRIER | existing explicit barrier authority only |

An original prior-session date/session is never replaced with the current session. A derived pivot has no candle identity. Complete classes with no forward constraint are explicitly COMPLETE_NO_APPLICABLE_FORWARD_CONSTRAINTS; eligible constraining rows give COMPLETE_WITH_TARGETS; missing required authority gives INCOMPLETE. WO-13 still chooses the nearest legitimate forward constraint and never extends the native target.

No existing commissioned current-session-extreme/barrier selector was established in this candidate. Their absence is recorded; this order creates neither. Required incomplete inputs cannot be upgraded through an empty default. SMA, VWAP, CPR, international references and desired R:R are not target sources.

## Publication and persistence

Native companion publication runs after completed facts and admission facts exist, before the new current population is exposed. It writes exact owner source envelopes, immutable decisions, semantic-identity bindings and a run manifest under `native-structural-selection-v1`. Policy checksum and commissioning boundary are retained. Constructors/startup/GET/replay do not write or select. Existing eight historical candidates are not reconstructed.

Decision fields cover programme/contract/policy, result and ordered reasons, subject/direction, cycle, five structural roles, run/boundary/session/date, semantic identity/integrity, instrument, exact MCX contract/roll, source identity/integrity, probable result/completed evidence IDs, target manifest/completeness, creation and integrity. A failed mapped source retains NOT_ESTABLISHED. An unmapped member lacks semantic authority and is outside prospective WO-09/WO-10 intake.

Possible reasons: NO_CONFIRMED_STRUCTURAL_CYCLE, PULLBACK_ORIGIN_NOT_ESTABLISHED, PRIOR_IMPULSE_NOT_ESTABLISHED, PULLBACK_EXTREME_NOT_ESTABLISHED, RESUMPTION_NOT_ESTABLISHED, STRUCTURAL_CYCLE_INVALIDATED, STRUCTURAL_CYCLE_AMBIGUOUS, TARGET_SOURCE_POPULATION_INCOMPLETE, BREAKOUT_SELECTOR_NOT_COMMISSIONED_V1, SOURCE_INTEGRITY_INVALID, SOURCE_SESSION_MISMATCH, SOURCE_DIRECTION_MISMATCH, SOURCE_ANALYSIS_BOUNDARY_MISMATCH, MCX_CONTRACT_BINDING_INVALID.

## WO-10 and operating boundary

Exact current WO-09 5/5 → exact Native decision → existing geometry/targets → Trade Plan → Future snapshot/expression → configured Risk → Sponsor comparison/selection → non-position WO-11 handoff. Native negatives retain TRADE_PLAN_UNAVAILABLE / STRUCTURAL_CONSTRUCTION_AUTHORITY_NOT_ESTABLISHED and their detailed reasons, without Provider acquisition. Read-only Trade Candidates shows actual retained structural availability, not policy-registration alone.

The lazy market source reads the explicit current Refresh master or exact MCX binding snapshot. Missing/stale daily master, canonical binding or session stays unavailable. Current Risk budget/open-risk totals and MCX monetary multipliers need separately governed exact source inputs; no defaults are invented. The positive isolated journey is not evidence that absent production monetary configuration has been commissioned.

WO-09 criteria, Opening, 98 identities, NATGAS HELD, WO-06H/07E/07F and all history remain unchanged. MCX exact expiry/roll is machine authority; NYMEX/COMEX remains supporting visual context only and NOT_INDEPENDENTLY_ESTABLISHED. No broker, margin, option, position, production analysis or runtime activation authority is added.
