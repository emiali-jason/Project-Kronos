# Theta TE-04A — V3 contract candidate closure

**Status:** QUALIFIED — isolated contract slice only, 12 October 2026.
**Authority:** Sponsor TE-04A V3 Combined Astra Answer Contract order.
**Worktree:** /Users/imranali/Documents/Project-KRONOS/.theta-te01-v1.
**Publication / production acceptance:** NOT GRANTED.
**Next:** TE-04B combined intake/persistence — NOT STARTED.

## Baseline and preservation

Local authoritative develop, origin/develop and the independently read GitHub
develop branch all resolved to 37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3.
The retained Theta candidate has the same detached HEAD plus its pre-existing
qualified, unpublished changes. No rebase, reset, staging, commit or push occurred.

The TE-01R source checkpoint remains
6462f830019fb1f53c5219fa610116c0abbfffcfef68950381cbdb423c4febb3.
All 18 checkpointed files remained byte-identical. Existing contracts.py,
workflow.py, store.py, packs.py, transport.py, question_pack.py, Browser routes,
chart intake and theme were not modified by TE-04A.

## Implemented contract-only components

- schema_v3.py: one closed definition for fields, limits, availability, relationship
  vocabulary, template placeholders, shape validation and producer rules.
- contracts_v3.py: pure public Question/batch construction and validation;
  exact-bound combined schema/template derivation; independent child validation;
  controlled failures and side-effect-free replay comparison.
- json_evidence.py: bounded UTF-8 JSON parsing and original child-value byte spans,
  with raw/canonical hash separation. No intake or persistence.
- Synthetic fixture and focused tests, plus a test-only output option.

The complete local contract is documented in
../architecture/interfaces/KRONOS-THETA-V3-COMBINED-ANSWER-CONTRACT.md.
The historical interface was append-only extended with a link and explicit slice
boundary, not rewritten.

Prospective identities:
KRONOS-THETA-QUESTION-V1 /3.0.0;
KRONOS-THETA-ANSWER-V1 /3.0.0;
KRONOS-THETA-COMBINED-ANSWER-V1 /1.0.0.
The existing convenience transport identity is reused at /2.0.0 for a pure,
complete V3 Question-batch descriptor. Historical /1.0.0 transport remains intact.

## Trust, evidence and methodology boundaries

Five exact subject slots: GOLDM, SILVERM, COPPER, CRUDEOIL, NATURALGAS.
Macro is one exact supporting chart, not a sixth analytical authority. Per-child
Question/cycle/chart/Macro/methodology/target/T0 binding is immutable by contract.

Only public exchange/KRONOS identity descriptors cross the external boundary.
No Kite token/session/request/response, broker account/position/order, P&L, margin,
intended strikes or contemplated expression is exported. Producer guidance
requires independent forecasts and explicitly excludes those internal facts.

Research is structured into bounded observations, sources, claims, relationships,
events, assumptions, limitations and classified narratives. Each E1/E2 forecast
has independent rationale/counterevidence/uncertainty/path risk/confidence
justification and material references. These are Analyst assertions. No TE-05
classifier, strength score, pass/fail, promotion or suitability verdict exists.

The numeric path remains mandatory. Strict LOWER < UPPER applies only to V3.
V1/V2 zero-width behavior remains valid under its own rules. Exact decimal strings,
negative bounds and trailing zeroes are preserved; confidence remains Astra's
terminal-containment percentage, never recalculated.

ADR-0066 clocks remain separate. Pre-T0 publication/availability, truthful later
retrieval/analysis and per-Question cutoff are validated. No one common T0 is
invented for the five-child wrapper. Unsupported timestamp precision is rejected,
not rounded. No independent source truth/as-of verification is claimed.

## Qualification chronology

1. Initial focused contract run: 133 PASS.
2. Initial retained Theta + focused Swing run: 400 PASS.
3. Additional directly related representation/chronology boundary cases and
   producer-guidance refinements: focused 155 PASS.
4. Final exact-source combined qualification: 422 PASS, 0 failed/errors/skipped.

Final groups:
- TE-04A contract/schema cases: 155.
- Retained Theta chart/Question/transport/Answer/Browser/isolation cases: 237.
- Current Swing Chart Analyst V2 contract and reconciliation discipline: 30.

No full Swing/Intraday programme regression was represented as necessary or run:
no shared implementation or product methodology was changed.

Command, using the existing repository isolation launcher:

    /Users/imranali/Documents/GitHub/Project-Kronos/.venv/bin/python tools/kronos_test.py tests/unit/theta tests/unit/swing/v1/test_chart_analyst_v2.py tests/unit/swing/v1/test_chart_analyst_v2_layer2.py -q --theta-v3-contract-output=/Users/imranali/Documents/Project-KRONOS/.theta-te01-v1/output/theta-te04a-final/theta-te04a-contract --junitxml=/Users/imranali/Documents/Project-KRONOS/.theta-te01-v1/output/theta-te04a-final/theta-te04a-contract/qualification.xml

The surrounding command sandbox initially denied the launcher's disposable
loopback probe. The authorized retry retained the existing inherited kernel
sandbox: production stores/Review Pack, credentials/process helpers and external
network were denied. No isolation guard was weakened.

## Actual changed-file manifest for this slice

1. src/kronos/theta/schema_v3.py — new.
2. src/kronos/theta/contracts_v3.py — new.
3. src/kronos/theta/json_evidence.py — new.
4. tests/unit/theta/v3_fixture.py — new, synthetic.
5. tests/unit/theta/test_contract_v3.py — new.
6. tests/unit/theta/conftest.py — two-line additive test output option.
7. docs/architecture/interfaces/KRONOS-THETA-V3-COMBINED-ANSWER-CONTRACT.md — new.
8. docs/architecture/interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md — append-only successor note.
9. docs/engineering/THETA-TE04A-CONTRACT-CANDIDATE.md — this new closure record.

Other pre-existing worktree changes belong to earlier slices and are not TE-04A
changes.

## Retained synthetic acceptance artifacts

Final evidence directory:

    output/theta-te04a-final/theta-te04a-contract/

It contains:
- closed V3 Question and batch schemas;
- five synthetic V3 Questions and exact synthetic Question batch;
- Question-bound combined JSON Schema;
- blank five-child Astra Answer template (deliberately invalid until completed);
- complete synthetic Answer for contract qualification only;
- generated Astra producer instructions;
- whole-file/child raw and canonical hash plus byte-offset proof;
- integrity manifest and final JUnit qualification.

The nine manifest entries validate exactly. All five child spans hash to their
recorded raw hashes, and whole-file raw SHA matches. The separate source checkpoint
at closure binds exact final source and qualification bytes.

The initial 400-test artifact set remains in output/theta-te04a-contract/ as
historical pre-refinement qualification evidence. It was not overwritten or
silently presented as the final contract snapshot.

All synthetic data is NOT FOR GENUINE FORECASTING. Nothing was published to
KRONOS QUESTIONS or CHATGPT ANSWERS.

## Impact and genuine limitations

Swing impact: NONE; no Swing-owned source changed.
Intraday impact: NONE; no Intraday-owned source changed.
Shared runtime/Browser impact: NONE.
Provider/broker impact: NONE; no market acquisition or broker operation.
Production 8947: no modification/restart/store access.
Sponsor sandbox 8948: no restart, deployment or mutation by this slice.

V3 is a pure contract candidate, not an integrated runtime producer/intake.
Current V1/V2 runtime paths remain unchanged. Genuine E1/E2 authority and
methodology commissioning remain separate dependencies. Source authenticity,
historical page availability and image truth remain external Analyst assertions,
not facts independently certified by schema acceptance.

TE-04B will own actual original-byte retention, receipts, durable replay/conflict
checks, independent child acceptance and currentness. Those are not implemented.
TE-05 methodology is still unapproved and no classifier is implemented.
No one-button import, Outlook population/redesign, Provider acquisition, broker
behavior or production publication was started.
