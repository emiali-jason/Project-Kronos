# Theta V1 deterministic analytical assessment interface — TE-05C

**Status:** Sponsor-authorized, implemented isolated candidate. Not deployed or
accepted for production runtime.
**Owner:** EA-Theta Earners.
**Version:** `KRONOS-THETA-ANALYTICAL-ASSESSMENT-V1 / 1.0.0`.
**Authority:** ADR-0067 and the canonical assessment methodology publication
`3595575c45db9aaf8bc165ffbe903737ed71124e7280291ab2e65259da4bb785`.
**Temporal foundation:** ADR-0066.

## Purpose and boundary

TE-05C verifies the integrity and required documentary relationships of one
exact TE-04B accepted Theta V3 commodity Answer. It creates a separate immutable
KRONOS assessment. It does not judge market direction, chart pixels, economic
correctness, forecast attractiveness, forecast probability, source truth,
research completeness, option suitability or trading outcomes.

The engine performs no network, Provider, broker, LLM, OCR, image-analysis,
market-data, position, P&L, margin, strike or order operation. It neither changes
nor republishes the accepted Question, Answer, receipt, source evidence, LOWER,
UPPER or CONFIDENCE. TE-04B structural acceptance remains an independent fact.

## Application operations

`ThetaAssessmentEngine.assess_accepted_theta_answer(accepted_answer_id)` is the
only creation operation. The caller supplies only an accepted Answer identity;
it cannot supply raw JSON, a file path, an inbox object, policy text or a policy
path. The engine resolves the immutable TE-04B Answer-identity claim, receipt,
original package and child bytes, canonical child, Question/hash, targets,
chart/Macro bindings, target authority, research methodology and per-Question
T0. Missing or corrupt trusted lineage returns a bounded, unpersisted
`NOT_EVALUABLE` admission result.

`ThetaAssessmentEngine.restore_assessment(assessment_id)` restores the exact
retained record and projects currentness from its original TE-04B receipt. It
does not rerun C1–C9 or assign another assessment timestamp.

There is no watcher, scheduler, background worker, directory discovery or
automatic assessment. TE-06 may call the explicit operation later, but is not
implemented here.

## Exact policy admission

Every new assessment attempt uses `ThetaMethodologyPublication` to revalidate
the exact TE-05B decision, manifest and canonical publication bytes. An admitted
Question must be strictly prospective and bind the exact research descriptor:

`KRONOS-THETA-ASTRA-RESEARCH-METHODOLOGY-V1 / 1.0.0 /
e9caff6ccf9b4b699737187a32e8eafe56366823fe280351868da6af06db9d5d`.

The assessment binds:

`KRONOS-THETA-ANALYTICAL-ASSESSMENT-METHODOLOGY-V1 / 1.0.0 /
3595575c45db9aaf8bc165ffbe903737ed71124e7280291ab2e65259da4bb785`.

An accepted pre-policy Answer, a wrong research binding or an unavailable,
wrong or corrupt exact assessment publication produces an immutable
`NOT_EVALUABLE` record for that otherwise trusted accepted Answer. It does not
make the forecast unaccepted. Completely untrusted/unrestorable input does not
produce an assessment record because no reliable lineage exists to bind it.

## Deterministic predicates

Each horizon independently contains exactly C1–C9:

| Criterion | Mechanically verified documentary predicate | `LIMITED` condition |
| --- | --- | --- |
| C1 | Exact accepted lineage/bindings plus horizon material claims and cited material sources connected in both directions | Required material source/claim connection missing |
| C2 | Rationale cites horizon material claims; horizon-applicable portions of available commodity and Macro research are source-backed and linked to rationale | Required section, applicable claim, source or rationale link absent |
| C3 | Explicit horizon `SUPPORT` and `OPPOSITION` relations reference the forecast and claims; counterevidence links to recorded opposition | Either recorded perspective or its required counterevidence link absent; no opposition is fabricated |
| C4 | Nonempty declared assumptions/limitations have compatible horizon scope and affected references; material-claim assumptions and relationship limitations appear in the forecast references | Declaration/review-completion evidence empty or required link absent |
| C5 | The restored TE-04A/TE-04B graph already proves recorded publication/availability/T0/retrieval/analysis/original-receipt ordering | Broken accepted graph is admission failure and therefore `NOT_EVALUABLE`; later valid retrieval is not failure |
| C6 | Available horizon REFERENCE and MCX observations, source-backed reconciliation claims, available reconciliation section and typed `RECONCILIATION` relationship connect chart/research evidence | Any required documentary witness/link absent |
| C7 | Each applicable declared event has admitted source/schedule/known-at evidence and links to rationale, uncertainty or confidence evidence | Empty event set, unavailable applicable event or missing required link |
| C8 | Horizon confidence justification and path-risk statements each cite source-connected, horizon-applicable evidence | Either required explanation/link absent |
| C9 | Applicable structured relationships are inspectable and no applicable declared `UNRESOLVED_CONTRADICTION` exists | Applicable unresolved contradiction, or empty applicable relationship record |

The evaluator never searches prose for hidden contradictions or performs
semantic grading. `FACT`, `SUPPORT`, `OPPOSITION`, `RECONCILIATION` and
`UNRESOLVED_CONTRADICTION` remain Astra assertions consumed as typed records,
not independently verified market facts.

C7 retains each applicable event identity and its deterministic temporal
position relative to that horizon endpoint: `BEFORE_EXPIRY`, `ACROSS_EXPIRY` or
`AFTER_EXPIRY`. After-expiry timing is not itself a failure and no later event
outcome is consumed.

## Results and aggregation

Criterion and horizon states are only `DOCUMENTED`, `LIMITED` and
`NOT_EVALUABLE`. Admission failure gives `NOT_EVALUABLE`; otherwise any
`LIMITED` criterion gives `LIMITED`; otherwise all nine are `DOCUMENTED` and the
horizon is `DOCUMENTED`. No count, score, percentage, weight, rank, promotion,
commodity roll-up or package roll-up exists.

E1 and E2 are evaluated independently. A record tagged for both may support
both; E1-only evidence never satisfies E2. Every criterion retains one bounded
reason code plus sorted exact evidence/source/observation/relation/event/
assumption/limitation references where applicable.

The verification claim appears only on admitted assessment records:
“KRONOS verified the integrity and required documentary relationships of this
assessment.” A `NOT_EVALUABLE` admission record carries no verification claim.

## Immutable record and identity

One sealed `v3-assessments/<assessment_id>.json` is the complete commit point.
The deterministic `TAS-<sha256>` identity binds schema/version, exact accepted
Answer identity, acceptance receipt and exact assessment-policy descriptor.
The record binds subject, original package/Question/Answer/receipt identities
and hashes, complete Question binding, exact E1/E2 targets, T0, research and
assessment descriptors, first assessment timestamp, and independent C1–C9
results/reasons/references.

No mutable assessment index or current pointer is introduced. This single-record
publication avoids a partially committed assessment graph. Retention uses the
existing no-clobber, no-follow, fsync/readback and cross-process transaction
primitives. Exact replay validates and returns the existing bytes/timestamp.
Different bytes at the same identity fail `THETA_IMMUTABLE_CONFLICT` and never
overwrite history.

## Restoration, currentness and successors

Restoration validates the sealed record, deterministic identity, closed shape,
allowed states, exact C1–C9 population, aggregation, retained receipt and accepted
evidence graph. It does not recalculate criteria. Currentness is a read projection
from TE-04B (`CURRENT`, `HISTORICAL`, `STALE` or `SUPERSEDED`) and is not stored
as mutable analytical authority. Chart/Question/Answer succession can change the
projection without changing the historical assessment.

The record pins V1 policy identity/version/hash. A future policy must retain a
separately versioned result and cannot reinterpret this record as “latest”. The
identity also retains the Question/Answer/assessment association needed for a
future separately governed TE-08 terminal-outcome record; TE-08 is not present.

## Non-authority

This interface grants no production, Provider, Kite, broker, execution, strategy,
option-expression, strike, lot, threshold, confidence-override, Outlook or
Sponsor-presentation authority. Predictive usefulness and production acceptance
remain unestablished.
