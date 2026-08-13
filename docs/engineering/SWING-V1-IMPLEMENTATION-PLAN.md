# KRONOS Swing V1 Implementation Plan

- **Status:** Slice 4 implementation authorized by the current engineering instruction
- **V1 architecture status:** Approved implementation authority for this programme
- **V0 status:** Published / frozen / unchanged
- **Current delivery boundary:** Slice 4 — provider-neutral Chart Analyst evidence, deterministic reconciliation, barriers, Clear Air and candidate Readiness
- **Runtime authority:** None beyond existing read-only analytical inputs

## Purpose

This plan translates the approved Swing V1 Architecture Candidate, same-98 Shadow
Validation, TradingView validation, Mandatory TradingView Context Gate, and
Readiness Amendment into a dependency-ordered implementation sequence.

Slices 1–2 remain additive beside the frozen V0 control. Slice 3 adds only
instrument-level TradingView review requirements, source-preserving Sponsor
chart intake, structured Layer-2 evidence contracts, durable retention, and a
compact Browser workflow. It stops before automated image interpretation,
barrier synthesis, Readiness, Trade Construction, R:R, viability, ranking,
Pre-Decision, Sponsor Decision, or execution.

Slice 4 now adds the amended provider-neutral AI Chart Analyst boundary,
deterministic reconciliation, barriers, Clear Air and candidate Readiness. It
still stops before Trade Construction, R:R, viability, ranking, decision and
lifecycle work.

## Dependency-Ordered Delivery Map

| Order | Layer | Engineering responsibility | Principal policy or contract | Slice |
| ---: | --- | --- | --- | --- |
| 1 | Policy registry | Publish stable V1 policy identities without altering V0 identities | V1 Stage 4–13 candidate policies | 1 |
| 2 | Domain contracts | Define immutable availability, structural, evidence, probable, reconciliation, run, and side-by-side comparison objects | Provider-neutral V1 Layer-1 contracts | 1 |
| 3 | Input interface | Consume the existing immutable `SwingDailyDataset`; accept approved benchmark relationships explicitly; expose no Provider-private identity | Completed-Daily V0/V1 same-facts boundary | 1 |
| 4 | Structural discovery | Retain deterministic pivot alternatives and moving-average trend-quality facts without selecting an unapproved production pivot algorithm | `SWING-PHASE1-V1-STRUCTURAL-DISCOVERY-POLICY` | 1 |
| 5 | Probable formation | Evaluate the two approved setup families independently and retain probable, unsupported, incomplete, and unresolved outcomes | `SWING-PHASE1-V1-PROBABLE-FORMATION-POLICY` | 1 |
| 6 | Evidence enrichment | Retain volume, candle, volatility, futures positioning, impulse/maturity, relative context, and gap evidence with explicit availability | V1 Stage 6–12 policy identities | 1 |
| 7 | Reconciliation | Preserve exactly two setup records for every one of the 98 members, including unavailable inputs and unresolved policy | `SWING-PHASE1-V1-PROBABLE-RECONCILIATION-POLICY` | 1 |
| 8 | Application orchestration | Run V0 unchanged and V1 Layer 1 over the same dataset and exact completed-Daily boundary | Same-facts side-by-side comparison contract | 1 |
| 9 | TradingView/context interface | Request one run-scoped chart package per unique probable instrument; retain source-preserved Sponsor uploads and separate Pine/structured evidence | `SWING-PHASE1-V1-TRADINGVIEW-CONTEXT-POLICY` | 3 |
| 10 | Chart-evidence interface | Interpret each retained original through one fixed, versioned question set and a strict provider-neutral response; preserve manual and OpenAI adapters | `SWING-V1-CHART-QUESTION-SET-V1` | 4 |
| 11 | Reconciliation and barrier interfaces | Preserve Layer-1/chart facts separately, reconcile structure/SMA20/Volume, group correlated price/TradingView barriers, keep Options OI unavailable and synthesize Clear Air | V1 Stages 14–17 | 4 |
| 12 | Readiness | Apply only deterministic KRONOS candidate Readiness rules after complete chart context; preserve Setup/Readiness/Monitoring separation | `SWING-PHASE1-V1-READINESS-ASSESSMENT-POLICY` | 4 |
| 13 | Trade construction | Construct Entry, invalidation, Stop, realistic Target, R:R, and viability only after context and Readiness permit | V1 Stages 19–20 | Deferred |
| 14 | Opportunity ordering | Preserve all viable opportunities and apply only a validated ordering policy | V1 Stage 21 | Deferred |
| 15 | Browser workflow | Present all unique probables, upload slots, explicit analysis state and deterministic candidate Readiness without trade geometry | Browser application projection | 4 |
| 16 | Decision and lifecycle | Pre-Decision, Sponsor Decision, Entry Thesis, Monitoring, Exit, and Journal | V1 Stages 22–27 | Deferred |

## Slice-1 Domain and Interface Map

Slice 1 introduces a separate `kronos.swing.v1` package. The package depends on
provider-neutral Swing completed-Daily contracts and may retain the frozen V0
market assessment only as a comparison control. V0 does not depend on V1.

The public Slice-1 result preserves:

- one exact observation boundary;
- all 98 canonical identities in deterministic universe order;
- exactly two independent setup records per instrument;
- every structural-definition alternative used by the research policy;
- moving-average trend-quality facts and explicit unavailable longer-history facts;
- setup-aware volume measurements;
- completed-candle morphology and contextual labels;
- volatility measurements;
- futures-positioning availability and roll-normalization gaps;
- impulse/pullback maturity measurements where applicable;
- benchmark-relative context where a reliable mapping and aligned series exist;
- gap/abnormal-move context;
- probable classification, reconciliation state, reasons, missing evidence, and
  an explicit TradingView-context gate state for probables;
- per-setup V0/V1 comparison classifications, including explicit incomplete
  comparison inputs; and
- the unchanged V0 control result at the same boundary.

No Slice-1 object contains Entry, Stop, Target, R:R, viability, rank, Top-2,
Readiness, execution, position sizing, Provider token, raw Kite client, or
TradingView-derived evidence.

## Slice-1 Verification Map

Focused verification must prove:

1. deterministic repeatability and immutable contracts;
2. exact 98-instrument / 196-setup reconciliation;
3. same completed-Daily boundary for V0 and V1;
4. preservation of unavailable, not-applicable, incomplete, and unresolved evidence;
5. independent setup-family evaluation without V0-qualified population leakage;
6. no production threshold, weighted score, trade geometry, ranking, or Top-2 authority;
7. no Provider-private or secret-bearing fields;
8. unchanged V0 policy identities and V0 regression behavior; and
9. full repository compilation and regression success.

## Slice-3 Browser and Evidence Workflow

`RUN V1 LAYER 1` consumes the latest retained provider-neutral daily dataset.
The Browser projects every unique probable instrument with all linked setup
hypotheses and every explicitly required timeframe. Daily is mandatory;
supporting 4H/1H charts are policy-configurable. Uploads are bound by the known
run/instrument/timeframe slot, never by filename. The original bytes and every
replacement revision are retained outside Git at
`~/Library/Application Support/KRONOS/evidence/swing-v1`.

The Browser exposes only `TRADINGVIEW_REVIEW_REQUIRED`, `CONTEXT_INCOMPLETE`,
and `TRADINGVIEW_CONTEXT_RECEIVED`. It does not expose READY/WAIT/INVALIDATED,
Trade Plans, geometry, R:R, or ranking. Automated image-to-structured-evidence
extraction remains deferred until a deterministic approved boundary exists.

## Change Control

No V0 policy or V0 implementation file may be changed by this plan. No threshold
may be tuned from the shadow observations. No commit or push is authorized by
this delivery.

## Slice-4 AI Chart Analyst Amendment

The Slice-4 provider boundary is `ChartEvidenceProvider`. Core Swing receives
only a versioned `ChartEvidenceResponse`; it has no OpenAI request, credential,
transport or retry dependency. `MANUAL_CHART_EVIDENCE_PROVIDER` and
`OPENAI_CHART_EVIDENCE_PROVIDER` emit the same contract so frozen charts can be
compared human-versus-AI without changing deterministic consumers.

Every call is Sponsor-triggered for a retained run/instrument/timeframe image.
The fixed question-set identity is `SWING-V1-CHART-QUESTION-SET-V1`. The
provider output contains visual observations only. Readiness, trade viability,
Entry, Stop, Target, R:R and ranking are absent from its schema. Provider
timeout, refusal, invalid schema, identity conflict and undeterminable critical
context fail closed to `CONTEXT_INCOMPLETE`.

Original images and structured results remain under the durable local evidence
root. The external request sends the original chart, fixed questions, chart
binding and the minimum Layer-1 factual thesis context. It sends no Kite token,
Provider credential, position, portfolio or order data. OpenAI credentials are
retrieved at call time through the existing Configuration-owned Apple Keychain
boundary and a one-use secret lease. The Browser accepts write-only credential
replacement but never returns the stored value. No credential enters ordinary
configuration, request audits or evidence. Runtime controls are:

- `KRONOS_CHART_ANALYST_ENABLED` (default `false`);
- `KRONOS_CHART_ANALYST_MODEL` (default `gpt-5.6`);
- `KRONOS_CHART_ANALYST_TIMEOUT_SECONDS` (default `45`);
- `KRONOS_CHART_ANALYST_MAXIMUM_RETRIES` (default `1`, maximum `2`); and
- `KRONOS_CHART_ANALYST_QUESTION_SET` (must equal the frozen V1 identity).

Ordinary tests use frozen structured responses and injected transports. They
never call the external API. The seven named Sponsor-chart cases remain a
validation programme, not a tuning set; trusted human-versus-live-AI authority
requires the actual frozen images plus explicit live-provider authorization.
