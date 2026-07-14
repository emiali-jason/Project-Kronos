# KR-710 Deterministic Explainability Framework

**Status:** Approved Architecture Contract; Not Implemented
**Date:** 2026-07-14
**Task Type:** Architecture Audit + Documentation

## Executive Conclusion

KRONOS has enough public state, text, score, and blocker outputs to explain many current decisions, but it does not yet expose a standard deterministic evidence contract for every permission, blocker, and state transition.

KR-710 should be implemented as an additive explainability framework. It should consume existing public outputs from source engines, identify the active blocker using deterministic precedence, and publish a reproducible blocker contract. It must not become a new Decision engine, must not duplicate trading calculations, and must not alter any existing state.

Master Architecture has approved this contract with minor refinements. Implementation still requires a separate coding task because KR-710 establishes a cross-engine public contract and will influence Developer Mode validation, Trader Mode messaging, and future research data.

## Approved Principle

Every KRONOS permission, blocker and state transition must map to a deterministic evidence contract.

Narrative text may summarize the rule, but may not replace the underlying measurable contract.

Every blocker contract must be able to expose:

| Field | Meaning |
|---|---|
| Owner engine | Engine ID and engine name that own the condition, such as `KR-315 Compression` |
| Metric or condition | Named metric, state, flag, or condition |
| Current value or state | Current observed value or categorical state |
| Required value, threshold, or state | Required condition for pass |
| Comparator or rule | Numeric, categorical, boolean, or rule comparator |
| Pass/Fail result | Whether the condition passed |
| Clear condition | Human-readable condition that would clear the blocker |

Not every blocker is numeric. Valid deterministic forms include numeric, categorical, and boolean contracts.

## Current Explainability Coverage By Engine

| Engine | Readiness/state outputs | Reason/summary outputs | Numeric metrics | Categorical states | Thresholds visible today | Existing outputs sufficient? | Additive outputs required? |
|---|---|---|---|---|---|---|---|
| KR-300 Trend Foundation | `outTrendDataReady`, `outLocalTrendState`, trend flags, stage flags | `outLocalTrendText`, `outTrendStageText`, SMA and price-position text | None public for SMA values; internal SMA stack exists | Trend state, stage, SMA alignment, price position | SMA 20/50/200 ordering and price above/below stack are internal | Partly | Yes, for deterministic current/required Daily stage and alignment explanation |
| KR-310 Trend Quality | `outTrendQualityState`, quality flags, `outEvidenceReady` | `outTrendQualityText`, `outEvidenceText` | `outTrendQualityScore` | Excellent/Healthy/Weak/Extended/Neutral | Score bands and extension rules are internal | Partly | Yes, for slope, extension, pullback-respect, and railway-track condition contracts |
| KR-315 Compression | `outCompressionReady`, `outCompressionState`, expansion flags | `outCompressionText`, `outCompressionReasonText` | `outCompressionScore` | None/Building/Strong/Critical/Expansion Started | Score thresholds are internal; CPR width state is consumed | Mostly | Yes, for compression-release boolean and score threshold detail |
| KR-320 Market Acceptance | `outAcceptanceState`, acceptance flags, `outBarrierReady` | `outAcceptanceText`, `outBarrierText` | `outAcceptanceScore` | Strong Acceptance/Accepted/Testing/Neutral/Rejected | Score bands and CPR/breakout/pullback/candle rules are internal | Partly | Yes, for specific acceptance blocker: CPR, breakout, pullback, or candle close |
| KR-330 Momentum | `outMomentumReady`, `outMomentumState`, context flags | `outMomentumText`, `outContextText` | `outMomentumScore` | Building/Strong/Normal/Weakening/Exhausted | Score bands and pillar evidence are internal | Partly | Yes, for primary failed momentum pillar |
| KR-335 Price Action | `outPriceActionReady`, `outPriceActionState` | `outPriceActionReason`, `outPriceActionSummary`, pressure/expansion text | `outPriceActionScore` | Price action state, closing pressure, expansion state | Score bands are internal | Mostly | Optional, for typed current/required values if KR-335 becomes a gate |
| KR-341 Consolidated Directional Bias | `outConsolidatedDirectionalReady`, directional state, bias flags, neutral/conflict flags | `outConsolidatedDirectionalText`, reason, summary | None | Bullish/Bearish/Neutral/Conflicted/Not Ready | Weekly/Daily/4H alignment rules are internal | Partly | Yes, for exact Weekly, Daily, and 4H component states and required states |
| KR-345 Relative Intelligence | `outRelativeReady`, market/sector ready flags, state outputs | `outRelativeReason`, `outRelativeSummary` | `outRelativeScore` | Leader/Strong/Neutral/Weak/Laggard; Rising/Flat/Falling internally | Lookback constant is public in source, scoring details internal | Mostly for display | Optional until relative strength becomes a blocker |
| KR-350 Opportunity | `outOpportunityInputReady`, `outOpportunityState`, opportunity flags | `outOpportunityText` | None | Bullish/Bearish/None | Depends on context and review readiness | Partly | Yes, for why opportunity is absent |
| KR-360 Confidence | `outConfidenceReady`, `outConfidenceState`, confidence flags | `outConfidenceReason`, `outConfidenceText` | `outConfidenceScore` | Avoid/Low/Developing/High/Exceptional | Decision uses confidence > 60; scoring gates are internal | Partly | Yes, for current score, required score, comparator, and dominant cap/penalty |
| KR-370 Decision | `outDecisionReady`, `outDecisionState`, decision flags | Decision text, decision reason, blocker text, next review, and need outputs | None | AVOID/WAIT/WATCH/BUY READY/SELL READY | Decision gates and need order are internal | Good summary, weak determinism | Yes, for mapping active blocker to owner/metric/current/required |
| KR-380 Execution | `outTriggerReady`, `outTriggerState`, trigger flags, context flags | `outTriggerText`, `outTriggerReason`, ref/MCX blocker outputs, `outExecutionNeed1-3` | None | NO TRIGGER/FORMING/BUY NOW/SELL NOW/FAILED/EXTENDED | Confidence > 60 and execution-context gates are internal | Partly | Yes, for exact execution timing blocker contract |
| KR-705 Presentation | Display availability and translated text variables | Trader and Developer display text | None owned | Panel mode only | None | Presentation only | No trading outputs; may consume KR-710 and KR-711 later |

## Gaps By Engine

| Engine | Main deterministic explainability gap |
|---|---|
| KR-300 | Public contract does not expose current SMA values, price-vs-stack facts, or required stage as typed blocker fields. |
| KR-310 | Quality text/score exists, but primary failed quality condition is not exposed. |
| KR-315 | Compression score/reason exists, but release condition and required release state are not standardized as pass/fail. |
| KR-320 | Acceptance state/score exists, but the exact acceptance pillar causing a blocker is not exposed. |
| KR-330 | Momentum score/state exists, but failed pillar details are not exposed. |
| KR-335 | Strong evidence coverage, but no standard typed explainability fields. |
| KR-341 | Directional state exists, but component Weekly/Daily/4H pass/fail fields are not public. |
| KR-345 | Relative evidence is display-ready, but not yet integrated as blocker evidence. |
| KR-350 | Opportunity can be absent without explaining which prerequisite prevented opportunity. |
| KR-360 | Confidence score and reason exist, but current vs required threshold is not standardized. |
| KR-370 | Blocker and need labels exist, but they are narrative labels rather than deterministic contracts. |
| KR-380 | Execution blockers exist, but current/required/pass fields are not standardized. |
| KR-705 | Trader wording is presentation-only and cannot show deterministic Developer Mode evidence until KR-710 exists. |

## Approved KR-710 Public Contract

KR-710 should publish one Active Blocker contract and optional typed fields. KRONOS may have multiple failing conditions; the Active Blocker is the currently selected highest-priority blocker, not the only blocker.

Required outputs:

| Output | Type | Purpose |
|---|---|---|
| `outExplainabilityReady` | bool | KR-710 has enough source-engine outputs to publish a blocker contract |
| `outActiveBlockerOwner` | string | Owner engine ID and name, such as `KR-360 Confidence` or `KR-315 Compression` |
| `outActiveBlockerSeverity` | string | `INFO`, `ADVISORY`, `BLOCKING`, or `CRITICAL`; informational only |
| `outActiveBlockerCategory` | string | Stable analytics category such as `COMPRESSION` or `CONFIDENCE` |
| `outActiveBlockerMetric` | string | Metric, state, flag, or condition name |
| `outActiveBlockerCurrentText` | string | Current value/state in display-safe text |
| `outActiveBlockerRequiredText` | string | Required value/state in display-safe text |
| `outActiveBlockerComparator` | string | Comparator or rule, such as `>=`, `==`, `must be true`, or `must not oppose` |
| `outActiveBlockerPass` | bool | Whether the blocker condition has passed |
| `outActiveBlockerClearCondition` | string | Clear, deterministic condition that would clear the blocker |
| `outActiveBlockerSummary` | string | One-line Developer Mode summary |

Recommended additive typed fields:

| Output | Type | Notes |
|---|---|---|
| `outActiveBlockerSourceEngineId` | string | Stable engine ID, for example `KR-370` |
| `outActiveBlockerSourceEngineName` | string | Stable engine name, for example `Decision Engine` |
| `outActiveBlockerPriorityRank` | int | Deterministic priority used when multiple blockers exist |
| `outActiveBlockerCurrentNumber` | float | Numeric value when the blocker is numeric; `na` otherwise |
| `outActiveBlockerRequiredNumber` | float | Numeric threshold when numeric; `na` otherwise |
| `outActiveBlockerCurrentState` | string | Categorical state when categorical |
| `outActiveBlockerRequiredState` | string | Required categorical state |

Do not fabricate values. If a source engine does not expose the needed current value, KR-710 should publish a deterministic text/state contract and mark numeric fields as `na`.

## Active Blocker Severity

Severity is informational only. It does not change Decision logic, Confidence, Execution behavior, or thresholds.

Allowed values:

| Severity | Meaning |
|---|---|
| `INFO` | Informational context, not a blocker by itself |
| `ADVISORY` | Useful caution or soft validation concern |
| `BLOCKING` | Active blocker preventing the next state |
| `CRITICAL` | Direct conflict or invalidating condition |

Examples:

| Engine | Example severity |
|---|---|
| KR-315 Compression | `ADVISORY` |
| KR-341 Consolidated Direction | `CRITICAL` |
| KR-360 Confidence | `BLOCKING` |

## Active Blocker Category

Category supports future analytics such as: "What percentage of WATCH states are blocked by Compression?"

Recommended values:

```text
DATA
TREND
ACCEPTANCE
COMPRESSION
MOMENTUM
PRICE_ACTION
CONFIDENCE
EXECUTION
STRUCTURE
RELATIVE_INTELLIGENCE
OPPORTUNITY
RISK
OTHER
```

## Example Active Blocker Record

```text
outExplainabilityReady = true
outActiveBlockerOwner = "KR-341 Consolidated Direction"
outActiveBlockerSeverity = "CRITICAL"
outActiveBlockerCategory = "TREND"
outActiveBlockerMetric = "Consolidated directional bias"
outActiveBlockerCurrentText = "Conflicted"
outActiveBlockerRequiredText = "Bullish or Bearish permission"
outActiveBlockerComparator = "must not conflict"
outActiveBlockerPass = false
outActiveBlockerClearCondition = "Weekly, Daily, and 4H directional evidence no longer conflict"
outActiveBlockerSummary = "KR-341 Consolidated Direction: Conflicted; required non-conflicted directional permission."
outActiveBlockerSourceEngineId = "KR-341"
outActiveBlockerSourceEngineName = "Consolidated Direction"
outActiveBlockerPriorityRank = 3
outActiveBlockerCurrentNumber = na
outActiveBlockerRequiredNumber = na
outActiveBlockerCurrentState = "Conflicted"
outActiveBlockerRequiredState = "Bullish or Bearish permission"
```

## KR-710 Ownership Rules

KR-710 owns:

- Explainability contract assembly.
- Active Blocker priority selection.
- Typed blocker publication.
- Mapping source-engine blocker labels to owner/metric/current/required/pass fields.

KR-710 does not own:

- Trading decisions.
- Confidence scoring.
- Execution timing.
- Trend, acceptance, momentum, compression, opportunity, or relative calculations.
- Alerts, trade management, or presentation.

## Blocker Priority Model

The current KR-370 need hierarchy is:

1. Directional context / trend confirmation.
2. Compression release.
3. Acceptance confirmation.
4. Confidence threshold.
5. Momentum improvement.
6. Opportunity improvement.
7. Review gate.

KR-380 execution needs add execution-context precedence:

1. KR data pending.
2. Review blocked.
3. KR-370 not ready / direction pending.
4. Failed or extended execution setup.
5. Reference Daily blocker.
6. Reference 4H blocker.
7. Reference 1H blocker.
8. MCX 1H execution blocker.

Recommended KR-710 priority:

| Rank | Category | Reason |
|---|---|---|
| 1 | Data / readiness | Nothing deterministic can be evaluated without data |
| 2 | Review blocked / invalid context | Prevents meaningful downstream evaluation |
| 3 | Directional conflict | Direction authority must pass before readiness |
| 4 | Trend confirmation | Trend foundation is prerequisite evidence |
| 5 | Acceptance | Value acceptance gates readiness and execution |
| 6 | Compression | Compression can block otherwise valid setup progression |
| 7 | Extension / pullback | Avoids chasing extended movement |
| 8 | Confidence | Uses completed evidence; should not outrank invalid direction/data |
| 9 | Momentum | Energy confirmation after direction and value context |
| 10 | Opportunity | Context availability after evidence readiness |
| 11 | Execution trigger | Applies after KR-370 READY state |
| 12 | Relative strength | Future blocker only; currently observation evidence |
| 13 | Other context | Fallback for unmapped but deterministic source outputs |

This order is conservative and broadly consistent with current KR-370/KR-380 gate order while separating execution timing from decision readiness.

## Trader Vs Developer Presentation Model

Trader Mode should show only concise KR-711 action wording and should not add rows unless a later UI decision explicitly approves it.

Developer Mode should show KR-710 deterministic fields:

- Owner.
- Metric or condition.
- Current value/state.
- Required value/state.
- Comparator/rule.
- Pass/Fail.
- Clear condition.

KR-705 remains display-only in both modes.

## Files That Would Require Pine Changes Later

Likely Pine implementation file:

- `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`

Potential implementation areas:

- Add KR-710 after KR-380 or immediately before KR-705, depending on whether execution blockers are included in v0.1.
- Add KR-711 after KR-710 and before KR-705.
- Optionally add source-engine additive public outputs where deterministic evidence is currently internal.
- Update KR-705 Developer Mode to display KR-710 fields.
- Update KR-705 Trader Mode to consume KR-711 text.

## Compatibility Risks

| Risk | Mitigation |
|---|---|
| KR-710 accidentally becomes a Decision engine | Contract must consume existing outputs and never change state |
| Duplicate calculations drift from source engines | Prefer source-engine additive outputs; avoid recomputing conditions in KR-710 |
| Overly generic blocker fields weaken deterministic value | Require owner, severity, category, metric, current, required, comparator, pass/fail |
| Numeric fields invite fabricated scores | Numeric fields must be `na` unless source engine owns a numeric value |
| KR-705 panel clutter | Trader Mode should remain concise; Developer detail can be optional |
| Source-engine public contracts expand too quickly | Implement phase by phase, beginning with KR-360/KR-370/KR-380 blockers |

## Recommended Phased Implementation Order

1. Approve KR-710/KR-711 architecture contracts.
2. Implement KR-710 v0.1 for existing KR-370 and KR-380 blockers using available public outputs only.
3. Add missing additive source-engine explainability outputs for the most frequent blockers from validation logs.
4. Implement KR-711 v0.1 to translate KR-710 active blocker into Trader Mode wording.
5. Update KR-705 Developer Mode to show KR-710 details without changing row count unless separately approved.
6. Validate on NSE, MCX, COMEX, and US equities using decision-frequency and WATCH-conversion logs.
7. Freeze the KR-710/KR-711 public contracts only after repeated live validation.

## Master Architecture Approval

Master Architecture approval is recorded as approved with minor refinements.

Implementation still requires a separate coding task. KR-710 and KR-711 introduce cross-engine contracts that affect explainability standards, validation records, Trader Mode wording, and Developer Mode diagnostics.

## Recommendation

APPROVE
