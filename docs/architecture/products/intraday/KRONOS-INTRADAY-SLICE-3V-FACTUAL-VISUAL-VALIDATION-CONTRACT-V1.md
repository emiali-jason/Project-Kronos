# KRONOS Intraday Slice 3V Factual / Visual Validation Contract

**Status:** WO-02 review candidate; not published; not final

**Authority:** VALIDATION ONLY

**Owner:** KRONOS Intraday

**Version:** 1

**Baseline:** `356f1d0f089a7ad2a2ee90226e7c819ae992e4f5`

## 1. Purpose

Slice 3V answers one question:

> Does KRONOS's governed factual representation accurately describe what is independently observable on the chart?

It does not answer whether KRONOS should trade.

Slice 3V owns comparison, factual validation, discrepancy classification, evidence preservation, and engineering-validation statistics. It owns no Discovery, candidate, PROBABLE, Readiness, Trade Construction, Entry, Stop, Target, Risk, execution, or PAPER/LIVE eligibility meaning.

The initial subject for WO-03 is RELIANCE run `INTRADAY-RUN-02490E741DA64343AAB2916271E98299`. WO-02 performs no RELIANCE comparison and consumes no screenshot.

### 1.1 DOMAIN-003 boundary

“Validation” in Slice 3V means engineering factual-conformance validation. It is not DOMAIN-003 Business Judgment. Slice 3V does not interpret facts into business meaning, publish the Business Judgment Contract, or acquire KR-370 analytical-promotion authority. Any future path from Slice 3V evidence into DOMAIN-003 requires separate explicit architecture and contract authority.

## 2. Trust boundary and independence

Machine evidence must be immutable and `FROZEN` before visual comparison begins. The visual reviewer receives chart context and factual questions, not machine conclusions. The reviewer may observe the chart but cannot rewrite machine facts, populate KRONOS machine identities or internal provenance, manufacture hidden precision, alter persisted evidence, or determine trading consequence.

KRONOS alone owns:

- validation-run identity;
- visual-evidence identity after intake;
- machine-evidence identity and binding;
- canonical Instrument binding;
- comparison-policy execution;
- discrepancy records;
- record integrity; and
- validation consequence.

The visual Answer payload is deliberately independent of machine evidence hashes, run hashes, canonical IDs, persistence identities, Provider tokens, and KRONOS provenance.

## 3. Immutable contract identities

| Contract | Identity |
| --- | --- |
| Question set | `KRONOS-INTRADAY-SLICE-3V-QUESTION-SET-V1` |
| Visual Answer schema | `KRONOS-INTRADAY-SLICE-3V-VISUAL-ANSWER-V1` |
| Comparison policy | `KRONOS-INTRADAY-SLICE-3V-COMPARISON-POLICY-V1` |
| Validation record schema | `KRONOS-INTRADAY-SLICE-3V-VALIDATION-RECORD-V1` |

Published versions are immutable. A change in questions, payload meaning, comparison semantics, binding, identity generation, or persistence meaning requires a new version. Historical records must not be reinterpreted under a later policy.

## 4. Timeframe independence

V1 supports exactly:

- 1D;
- 1H;
- 15m; and
- 5m.

Each timeframe is independently bound and compared. A 15m result establishes nothing about 5m correctness. Swing's 1W / 1D / 4H / 1H hierarchy is outside this contract.

## 5. Intraday-specific question set

Q1 and Q2 are strict Answer-header questions. Q3–Q12 are ordered bounded Answer entries. A chart-available Answer missing an entry, changing order, duplicating an entry, or using another version is rejected as partial or invalid.

| ID | Question | Bounded factual scope |
| --- | --- | --- |
| Q1 | `CHART_IDENTITY` | Visible symbol, exchange/market, trading date/context; canonical binding remains KRONOS-owned |
| Q2 | `TIMEFRAME_CONTEXT` | Timeframe and observation boundary |
| Q3 | `COMPLETED_CANDLE` | Latest supportable completed boundary, OHLC, direction, completed/incomplete distinction |
| Q4 | `PREVIOUS_SESSION` | PDH, PDL, previous close |
| Q5 | `CLASSIC_PIVOTS` | P, R1–R4, S1–S4; exact values only where visible, otherwise placement/relationship |
| Q6 | `CPR` | Pivot, BC/lower, TC/upper, width where visible, relative placement |
| Q7 | `STRUCTURAL_BARRIERS` | Visible factual levels and relationships; no support/resistance semantics |
| Q8 | `STRUCTURAL_EVENTS` | Existing factual relationships such as `CLOSE_ABOVE_BOUNDARY` or `RETEST_FROM_ABOVE` |
| Q9 | `VOLUME_PARTICIPATION` | Visible volume and independently observable comparisons; no threshold consequence |
| Q10 | `CURRENT_INCOMPLETE_CANDLE` | Explicit separation of current incomplete evidence from completed structural authority |
| Q11 | `SESSION_BOUNDARY` | Governed market/session consistency, including continuous/CAS separation where relevant |
| Q12 | `ADDITIONAL_FACTUAL_DISCREPANCY` | Bounded factual discrepancy or explicit `NO_ADDITIONAL_DISCREPANCY` |

The question set does not reuse Swing Visual Review Q1–Q10, labels, analytical states, or trading methodology.

## 6. Visual Answer contract

### 6.1 Visual-only top-level fields

The imported reviewer payload contains only:

```text
schema_identity
question_set_identity
visible_symbol
exchange
trading_date
timeframe
observation_boundary
chart_observed_at
chart_available
answers
```

Each Q3–Q12 Answer contains:

```text
question
state
unavailability_reason
observations
```

Each visual observation contains:

```text
question
fact_key
precision
value_kind
value
factual_note
```

`factual_note` is bounded and is mandatory for `OTHER_GOVERNED_FACTUAL_DISCREPANCY`. Open trading interpretation is prohibited.

### 6.2 Machine-owned fields excluded from reviewer payload

The reviewer payload contains none of:

- machine evidence identity or hash;
- machine run identity or hash;
- validation run or record identity;
- canonical Instrument ID;
- Instrument mapping identity;
- Provider instrument token;
- internal persistence identity;
- machine/KRONOS provenance placeholder; or
- machine conclusion.

KRONOS derives `visual_evidence_identity` and integrity after schema-valid intake. Those fields appear only in KRONOS's persistence envelope, never in the reviewer Answer contract.

### 6.3 Answer states

| State | Meaning |
| --- | --- |
| `OBSERVED` | One or more bounded visual observations are supplied. |
| `NOT_OBSERVABLE` | The chart cannot reliably support the requested observation; a bounded reason is required. |
| `NO_ADDITIONAL_DISCREPANCY` | Q12 only; no extra factual discrepancy was observed. |

If the chart is unavailable, `chart_available=false` and no synthetic question answers are permitted.

## 7. Numeric observation model

Machine numbers remain exact `Decimal` facts.

| Visual precision | Comparison rule |
| --- | --- |
| `EXACT` | Same value kind and exact value are required for `MATCH`. |
| `APPROXIMATE` | `NOT_VISUALLY_VERIFIABLE`; V1 has no numerical tolerance. |
| `RELATIONAL_ONLY` | May `MATCH` only an identical machine relationship; it cannot validate an exact number. |
| `NOT_OBSERVABLE` | `NOT_VISUALLY_VERIFIABLE`. |

V1 defines no tolerance, rounding allowance, percentage band, pixel distance, or chart-scale heuristic. An exact-looking approximate observation does not become exact merely because its displayed digits equal the machine fact. Any tolerance requires separate authority and a new comparison-policy version.

## 8. Comparison results

Individual observations use this closed enum:

```text
MATCH
MISMATCH
NOT_VISUALLY_VERIFIABLE
CHART_EVIDENCE_UNAVAILABLE
IDENTITY_MISMATCH
TIMEFRAME_MISMATCH
OBSERVATION_BOUNDARY_MISMATCH
```

`PASS` and `FAIL` are not individual results because they could imply trading quality. Engineering acceptance, if later required, is a separate governed state with no threshold in V1.

Preflight order is fail closed:

1. machine evidence exists and is not superseded;
2. machine evidence was frozen before comparison;
3. visual Answer is current relative to that freeze;
4. chart availability;
5. visible symbol and exchange;
6. trading date/context;
7. timeframe;
8. observation boundary; and
9. question-by-question factual comparison.

## 9. Discrepancy family

`MISMATCH` requires one of:

```text
CANDLE_VALUE_DISCREPANCY
LEVEL_VALUE_DISCREPANCY
LEVEL_PLACEMENT_DISCREPANCY
STRUCTURAL_EVENT_DISCREPANCY
VOLUME_DISCREPANCY
SESSION_BOUNDARY_DISCREPANCY
COMPLETED_VS_INCOMPLETE_DISCREPANCY
SOURCE_CHART_IDENTITY_DISCREPANCY
OTHER_GOVERNED_FACTUAL_DISCREPANCY
```

`OTHER_GOVERNED_FACTUAL_DISCREPANCY` requires a bounded factual explanation. No discrepancy record may state trade quality, direction authority, readiness, Risk, or execution consequence.

## 10. KRONOS-owned machine-to-visual binding

The immutable validation record binds:

- validation-run identity;
- canonical Instrument ID;
- trading date;
- observation boundary;
- timeframe;
- evidence family;
- machine-evidence identity;
- visual-evidence identity;
- question-set identity/version;
- visual-Answer schema identity/version;
- comparison-policy identity/version;
- comparison results;
- discrepancy records;
- comparison timestamp;
- validation-record identity/schema; and
- integrity identity.

The visual reviewer populates none of these machine-side identities. KRONOS binds the schema-valid Answer after intake.

Validation-run identity is deterministic from the exact binding and contract versions. Validation-record identity and integrity are deterministic from that binding plus comparison results, discrepancy records, and comparison timestamp.

## 11. Persistence and selection

V1 persistence is append-only, restart-safe, explicit-identity-bound, and tamper-evident through deterministic integrity identities and canonical serialization.

- Visual Answers are retained by `visual_evidence_identity`.
- One immutable logical visual binding maps to one visual-evidence identity.
- An identical duplicate is idempotent.
- A different Answer for the same logical binding is a conflict and is rejected.
- Validation records are retained and loaded by `validation_record_identity`.
- No API selects the newest file.
- File timestamps and directory order have no authority.

Selection therefore never uses “latest file wins.” A changed methodology or revised evidence requires a separately governed new version/binding rather than mutation.

## 12. Sanitized failure states

| Condition | Fail-closed outcome |
| --- | --- |
| Missing chart | `CHART_EVIDENCE_UNAVAILABLE`; no synthetic answers |
| Wrong instrument/exchange | `IDENTITY_MISMATCH` + source/chart identity discrepancy |
| Wrong timeframe | `TIMEFRAME_MISMATCH` |
| Wrong observation boundary | `OBSERVATION_BOUNDARY_MISMATCH` |
| Wrong trading date/context | `WRONG_TRADING_CONTEXT` |
| Visual schema failure | `VISUAL_ANSWER_SCHEMA_FAILURE` |
| Partial/unordered Answer | `PARTIAL_ANSWER` |
| Answer predating machine freeze | `STALE_ANSWER` |
| Duplicate/conflicting Answer | `DUPLICATE_CONFLICTING_ANSWER` |
| Machine evidence absent | `MACHINE_EVIDENCE_UNAVAILABLE` |
| Machine evidence superseded | `MACHINE_EVIDENCE_SUPERSEDED` |
| Invalid comparison request | `COMPARISON_FAILURE` |

All failure codes are sanitized. Import, reconstruction, or comparison failure must be explicit; no silent fallback, inferred value, or neutral substitution is permitted.

## 13. Engineering-validation statistics

Future aggregates may report:

- observations compared;
- count and percentage by comparison result;
- discrepancy count by family;
- timeframe breakdown; and
- canonical Instrument breakdown.

These are engineering-validation statistics only. V1 defines no acceptance, production, analytical-promotion, or trading threshold. Statements such as “90% match means production ready” are prohibited without later authority.

## 14. MCX extension seam

The evidence-family enum reserves two distinct families:

```text
NATIVE_CHART
MCX_REFERENCE_MARKET_RELATIONSHIP_V0
```

V1 implements Native factual/chart comparison only. Attempting to run Native V1 comparison policy against `MCX_REFERENCE_MARKET_RELATIONSHIP_V0` fails closed as not implemented.

A future relationship contract/version must separately bind:

- native MCX identity;
- COMEX/NYMEX reference identity;
- matching timeframe;
- absolute event timestamps; and
- event order.

It must not perform cross-market price arithmetic or create trading consequence. Native MCX chart validation and MCX↔reference-market relationship validation remain separate evidence families.

## 15. Minimum WO-03 workflow

```text
machine evidence frozen
    → independent chart/review pack generated
    → visual Answer completed without machine conclusions
    → schema-valid Answer imported
    → KRONOS visual identity generated
    → machine/visual identity and context validated
    → deterministic comparison
    → immutable discrepancy and validation record
    → engineering review
```

Browser presentation is derivative. WO-02 does not change the Browser, redesign the Intraday main page, add analytical labels, call OpenAI, or execute visual analysis.

## 16. Implementation boundary

The V1 proof is product-owned under:

- `src/kronos/intraday/validation.py`;
- `src/kronos/intraday/validation_persistence.py`; and
- `tests/unit/intraday/test_validation.py`.

No Swing, Provider, Instrument, Market, shared monitoring, shared notification, shared Browser, Pine, OpenAI, Risk, execution, or broker surface is changed.

## 17. Explicit non-authority

This contract introduces:

```text
Trading authority:             NONE
Analytical promotion:          NONE
Risk authority:                NONE
PAPER / LIVE eligibility:      NONE
OpenAI execution/calls:        NONE
Broker execution capability:   NONE
```

## 18. References

- [Living Engineering, Methodology & Architecture Record V0.1](KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md)
- [Intraday Shared-File Change Rule](../../../engineering/INTRADAY-SHARED-FILE-CHANGE-RULE.md)
- [DOMAIN-003 Validation Architecture](../../platform/domains/validation/ARCHITECTURE.md)
- KRONOS Swing → Intraday Engineering & Architecture Handover V1.0, dated 2026-08-22, as supplied under WO-02.
