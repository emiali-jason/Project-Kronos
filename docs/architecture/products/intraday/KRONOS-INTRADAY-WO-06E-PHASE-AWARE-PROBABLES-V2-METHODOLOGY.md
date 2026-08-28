# KRONOS Intraday V1 — WO-06E Phase-Aware Probables V2 Methodology

**Status:** Approved methodology freeze — implementation not started

**Owner:** KRONOS Intraday

**Authority:** EA/Sponsor WO-06E-FREEZE

**Methodology:** `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2 / 2.0.0`

**Publication:** `INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-7B75EE711558F706CFB97B4548952B8924A8CBD8E519EFEEE61B53828FDD9F89`

**Canonical payload:** [WO-06E V2 methodology payload](KRONOS-INTRADAY-WO-06E-PROBABLES-V2-METHODOLOGY-PAYLOAD.json)

**Payload SHA-256:** `7b75ee711558f706cfb97b4548952b8924a8cbd8e519efeee61b53828fdd9f89`

**Checksum encoding:** UTF-8 JSON with recursively sorted object keys,
`ensure_ascii=true`, and separators `,` and `:` with no insignificant whitespace

**Implementation authority:** None under this publication

**Runtime authority:** None under this publication

## 1. Purpose and immutable predecessor

This record freezes the phase-aware successor to the V1 Intraday Probables
methodology. It is analytical admission authority for deeper review only. It
does not authorize Chart Review, WO-10 reconciliation, Promotion, Entry Timing,
Trade Construction, Risk, PAPER/LIVE or broker activity.

`KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V1 / 1.0.0` remains immutable. V1
facts, runs, members, stores, pointers and replay retain V1 meaning. No V1
artifact is migrated or reinterpreted as V2.

The accepted research authorities are:

- `INTRADAY-PHASE-AWARE-COMPLETED-EVIDENCE-RESEARCH-D55631CD05BC47A605277496C5F04ED2F75EDE7FAF87938EF5E491E84347153D`;
- `INTRADAY-OPENING-PHASE-NIFTY-RELATIVE-RESEARCH-093DAFC4CCEE6B67C8EA16CFB9C7F9974C9276FEC4A02B947C09AA1111BCE7F7`.

No outcome, profitability, accuracy, expected-R or timing-superiority claim is
made.

## 2. Exact phase family and selector

The production enum is `IntradayAnalysisPhase` with exactly these values:

1. `OPENING`
2. `STRUCTURE`
3. `FIRST_CURRENT_SESSION_1H`
4. `CURRENT_SESSION_ESTABLISHED`

The selector is fact-driven and uses governed completed evidence. Its priority
is established 1H, first 1H, Structure, Opening:

| Phase | Exact selection predicate |
|---|---|
| `CURRENT_SESSION_ESTABLISHED` | Current-session completed 1H count is at least two. |
| `FIRST_CURRENT_SESSION_1H` | Current-session completed 1H count is exactly one. |
| `STRUCTURE` | Current-session completed 1H count is zero and completed 15M count is at least two. |
| `OPENING` | Current-session completed 1H count is zero and completed 15M count is exactly one. |

Before the first current-session 15M is complete, no V2 phase is selected and
the assessment is unavailable. Clock labels are never predicates. A selected
phase can still be unavailable when its mandatory evidence is missing.

Every boundary creates new immutable evidence. Later phases never mutate
Opening or earlier phase assessments. Candidate continuity is not assumed.

## 3. Completed-evidence authority

`KRONOS-INTRADAY-PHASE-AWARE-COMPLETED-EVIDENCE-SELECTION-V1 / 1.0.0`
binds the analysis boundary, phase, canonical subject, market/session,
calendar identity/version, selected candle identities and timeframes, original
source sessions and timestamps, completion boundaries, current/prior roles,
policy identity/version, provenance and integrity.

Only governed completed candles are eligible. Forming, misaligned or
integrity-invalid candles fail closed. Replay loads the exact persisted
selection identity; it never asks for the current “latest” candles.

Cross-session 1H selection uses DOMAIN-008 to locate the immediately preceding
valid governed session. Original session, timestamp, completion boundary and
prior-session role remain explicit. There is no calendar-yesterday assumption
and no relabelling as current-session evidence.

## 4. Opening semantics and admission

Opening uses `KRONOS-INTRADAY-OPENING-SEMANTIC-FACT-V1 / 1.0.0` and
`KRONOS-INTRADAY-OPENING-SEMANTIC-EVIDENCE-V1 / 1.0.0`. A single opening 15M
is never serialized as normal `15M_STRUCTURE`.

Mandatory factual evidence is:

- governed previous completed 1D context and `NARROW_CPR_KGS_V0`;
- the prior valid session's completed 1H regime context, preserving its two
  source candles and identifying its latest candle as contextual focus;
- exactly the first completed current-session 15M;
- exactly its three constituent completed current-session 5M candles; and
- aligned NIFTY Opening relative context for applicable NSE subjects.

Opening direction is `LONG` when first-15M close is above open, `SHORT` when
below, and `NON_DIRECTIONAL` when equal. The three-5M progression is `LONG`
when both consecutive high/low/close transitions are all above, `SHORT` when
both are all below, `CONFLICTING` when one transition is Long and the other
Short, and `NON_DIRECTIONAL` otherwise.

The prior-1H, Opening-5M and applicable NIFTY relationships are typed
independently as supporting, conflicting or informational. Their combination
is deterministic: any conflict wins; otherwise any support wins; otherwise the
combination is informational.

Opening admission requires all of:

1. mandatory evidence available and valid;
2. `NARROW_CPR_KGS_V0 = TRUE`;
3. a directional Opening 15M; and
4. combined Opening relationship `SUPPORTING`.

Narrow CPR false, non-directional Opening, a combined conflict, or no supporting
relationship is `NOT_ADMITTED`. Missing or invalid mandatory evidence is
`UNAVAILABLE`. A conflicting prior 1H, conflicting Opening-5M progression, or
conflicting NIFTY context blocks admission without creating or flipping
direction. This explicitly freezes the accepted research model's
conflict-fails-closed consequence.

## 5. Later-phase methodologies

`STRUCTURE` uses the prior-valid-session completed 1H regime as explicit
context and normal latest-two-current-15M structure. Admission requires Narrow
CPR true, both directions present and exact coherence. Opposition or a
non-directional required state is not admitted.

At `FIRST_CURRENT_SESSION_1H`, the first completed current-session 1H becomes
primary immediately. Its 1H transition direction is the governed high/low/close
movement from the prior valid session's latest completed 1H candle to the first
current-session completed 1H. The prior candle remains comparator/context and
cannot overwrite the first current candle. Admission requires Narrow CPR true,
directional transition 1H, directional latest-two-current-15M structure and
exact coherence.

At `CURRENT_SESSION_ESTABLISHED`, the latest two completed current-session 1H
candles supply the qualified existing regime comparison. Admission requires
Narrow CPR true, directional latest-two-current-1H regime, directional
latest-two-current-15M structure and exact coherence. Forming candles are
prohibited at every phase.

From Structure onward, 5M progression is informational and participation is
supporting/non-blocking, preserving the V1 consequence philosophy.

## 6. NIFTY relative context

The canonical benchmark is `NSE-INDEX-NIFTY`. DOMAIN-001 owns identity.
Intraday owns `KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-FACT-V1 / 1.0.0` and
`KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-EVIDENCE-V1 / 1.0.0`.

For Opening:

```text
subject_return_pct = ((subject_opening_15m_close / subject_session_open) - 1) * 100
benchmark_return_pct = ((nifty_opening_15m_close / nifty_session_open) - 1) * 100
relative_return_pct = subject_return_pct - benchmark_return_pct
```

Positive is `OUTPERFORMING`, negative is `UNDERPERFORMING`, and exact zero is
`EQUAL`. No epsilon, score, magnitude threshold, rank, weight or quota exists.

For Long, outperforming supports and underperforming conflicts. For Short,
underperforming supports and outperforming conflicts. Equal or a
non-directional subject is informational. NIFTY never creates direction.

Subject and benchmark require exact timeframe, candle start/end,
exchange/market context and completed boundary. Their distinct legitimate
DOMAIN-008 session identities are retained and need not be equal. Interpolation,
nearest timestamp, stale substitution and alternate benchmarks are prohibited.

NSE equities and BANKNIFTY use NIFTY. NIFTY self-reference is
`NOT_APPLICABLE:BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE`; no synthetic zero or
`EQUAL` is created. MCX is `NOT_APPLICABLE`.

The optional O4 three-point relative progression is strictly increasing
`IMPROVING`, strictly decreasing `DETERIORATING`, all equal `FLAT`, otherwise
`MIXED`. It is supporting/non-blocking and unavailable-tolerant.

Current-boundary NIFTY calculations for Structure, first-1H and established-1H
are deferred because WO-06E-RS did not qualify their exact intervals. The
Opening fact remains immutable historical lineage with no later-phase admission
consequence.

Each NIFTY fact/evidence record binds canonical subject and benchmark, analysis
boundary, timeframe/interval, subject and benchmark candle identities, both
source-session identities, subject/benchmark/relative returns, relationship and
applicability states, policy identity/version, source provenance and integrity.
Conflicting retention fails closed.

## 7. Reference facts and semantic families

| Family | Opening | Structure and later |
|---|---|---|
| `1D_CONTEXT` | Mandatory availability; informational consequence | Same |
| `1H_REGIME` | Phase-adapted prior context; conflict input | Phase-adapted mandatory coherence |
| `15M_STRUCTURE` | Deferred; Opening semantic used instead | Mandatory normal structure |
| `DIRECTIONAL_COHERENCE` | Phase-adapted combined relationship | Mandatory 1H/15M coherence |
| `5M_PROGRESSION` | Mandatory availability; typed conflict input | Informational |
| `VOLUME_PARTICIPATION` | Supporting/non-blocking; unavailable-tolerant | Same |
| `PDH_PDL_RELATIONSHIP` | Informational; unavailable-tolerant | Same |
| `CPR_LOCATION` | Informational; unavailable-tolerant | Same |
| `CLASSIC_PIVOT_RELATIONSHIPS` | Informational; unavailable-tolerant | Same |
| governed gap/opening relationships | Informational; unavailable-tolerant | Same |

Reference/location facts cannot create direction, replace mandatory evidence,
or manufacture a Probable. Narrow CPR remains separately required admission
support.

## 8. Failure, persistence and replay

NIFTY failures are typed as `BENCHMARK_FACT_UNAVAILABLE`,
`BENCHMARK_IDENTITY_INVALID`, `BOUNDARY_MISMATCH`, `SOURCE_INTEGRITY_INVALID`
or `SUBJECT_FACT_UNAVAILABLE`. Phase evidence also distinguishes previous-valid
session unavailable, insufficient/misaligned completed evidence and forming
candle rejection.

`UNAVAILABLE` means legitimate evaluation was impossible. `NOT_ADMITTED` means
all mandatory evidence existed but the analytical predicates failed. Each phase
is evaluated independently.

Selections, Opening semantics, NIFTY facts, V2 semantics, mappings, members,
diagnostics, runs, refresh states and current pointers are immutable,
canonical, integrity-bound and retained in version-specific namespaces.
Conflicting rewrites fail closed. Restart restores exact identities without a
Provider call or latest-file substitution.

## 9. Browser projection and MCX limit

Browser projects persisted state only. It shows methodology version, phase,
analysis boundary, 1H provenance, NIFTY relationship/applicability, Probables
state and exact reason. It shows no score, rank, confidence or recommendation.

`MCX_V2_EMPIRICAL_COMMISSIONING = NO`. MCX displays NIFTY as `NOT_APPLICABLE`
and V2 operational state as
`STRUCTURALLY_SUPPORTED_NOT_EMPIRICALLY_COMMISSIONED`. Until separate real MCX
qualification, an MCX V2 member is
`UNAVAILABLE:MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED`.

## 10. Authoritative phase table

| Phase | Mandatory evidence | Supporting | Deferred | 1H role | 15M role | 5M role | NIFTY role | Availability/admission/conflict | Transition |
|---|---|---|---|---|---|---|---|---|---|
| `OPENING` | prior 1D/Narrow CPR; prior-session 1H context; first 15M; exactly three constituent 5M; NIFTY when applicable | volume; O4 progression | normal 15M structure; later-phase RS | prior context | Opening direction, not structure | required and conflict-typed | mandatory presence; sign relationship | Missing mandatory → unavailable. Narrow CPR true + directional 15M + combined support → Probable. Any typed conflict → not admitted. | second 15M completes, unless first 1H already governs |
| `STRUCTURE` | prior 1D/Narrow CPR; prior 1H regime; latest two current 15M | volume | current Structure RS | prior context/coherence | primary normal structure | informational | Opening lineage only | Missing mandatory → unavailable. Narrow CPR true + exact 1H/15M coherence → Probable; opposition/non-directional → not admitted. | first current 1H completes |
| `FIRST_CURRENT_SESSION_1H` | prior 1D/Narrow CPR; prior latest 1H; first current 1H; latest two current 15M | volume | current first-1H RS | cross-session transition, current candle primary | mandatory coherence | informational | Opening lineage only | Missing mandatory → unavailable. Narrow CPR true + exact transition-1H/15M coherence → Probable; conflict/non-directional → not admitted. | second current 1H completes |
| `CURRENT_SESSION_ESTABLISHED` | prior 1D/Narrow CPR; latest two current 1H; latest two current 15M | volume | current established-phase RS | primary latest-two regime | mandatory coherence | informational | Opening lineage only | Missing mandatory → unavailable. Narrow CPR true + exact 1H/15M coherence → Probable; conflict/non-directional → not admitted. | remains; rolls on each new completed boundary |

## 11. Contract and version table

| Contract | Version |
|---|---|
| `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2` | `2.0.0` |
| `KRONOS-INTRADAY-PHASE-AWARE-COMPLETED-EVIDENCE-SELECTION-V1` | `1.0.0` |
| `KRONOS-INTRADAY-OPENING-SEMANTIC-FACT-V1` | `1.0.0` |
| `KRONOS-INTRADAY-OPENING-SEMANTIC-EVIDENCE-V1` | `1.0.0` |
| `KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-FACT-V1` | `1.0.0` |
| `KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-EVIDENCE-V1` | `1.0.0` |
| `KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-FACT-V2` | `2.0.0` |
| `KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-EVIDENCE-V2` | `2.0.0` |
| `KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-V2` | `2.0.0` |
| `KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-MAPPER-V2` | `2.0.0` |
| `KRONOS-INTRADAY-PROBABLE-V2` | `2.0.0` |
| `KRONOS-INTRADAY-PROBABLES-POPULATION-DIAGNOSTICS-V2` | `2.0.0` |
| `KRONOS-INTRADAY-PROBABLES-RUN-V2` | `2.0.0` |
| `KRONOS-INTRADAY-DISCOVERY-PROBABLES-REFRESH-STATE-V2` | `2.0.0` |
| `KRONOS-INTRADAY-CURRENT-PROBABLES-POINTER-V2` | `2.0.0` |

The V2 mapper binds phase, selection identity, Opening or normal semantic
identity, NIFTY identity/applicability, canonical subject, direction, boundary,
methodology publication, provenance and integrity. Every V2 member/run is
unmistakably V2-bound. A V2 member also binds its exact source Discovery
run/member, selected evidence and result reason. A V2 run binds the V2
methodology publication/checksum, exact population, member identities,
diagnostics, boundary and integrity; it cannot be deserialized through a V1
schema.

## 12. Ownership and deferred decisions

DOMAIN-001 owns canonical subject and benchmark identity. DOMAIN-008 owns
calendar, session and completion boundaries. Provider supplies read-only
historical facts. Intraday owns selection, phase semantics, NIFTY context and
Probables admission. Browser projects only. Swing source and methodology are
unchanged.

Still deferred are sector benchmarks, numeric relative-strength thresholds,
later-phase current NIFTY interval semantics, outcome/performance consequences,
MCX empirical commissioning and future benchmark families.

## 13. WO-06E-IMPLEMENT acceptance

Implementation must prove Opening, Structure, first-1H and established phase
selection; prior-valid-session bridging; exact first-15M/three-5M selection;
NIFTY alignment/unavailability/self-reference/BANKNIFTY/MCX handling; typed
Opening conflicts; each phase transition; V1 and V2 replay isolation; immutable
persistence; restart without Provider; conflicting/tampered artifact rejection;
and projection-only Browser behavior. It must bind the exact publication and
checksum above.
