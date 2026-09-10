# WO-07E FB02 / FB03 — Sponsor Question PDF and Answer Protocol

Status: Engineering candidate — Sponsor/EA review required; unpublished.
Authority: direct Sponsor FB02/FB03 engineering authorization and subsequent
Q6/Q9 governed-anchor decision. Baseline: develop fe7ab1080f850bef5828cf4b32a21113a1adef03.
FB01 performance, empirical Analyst execution and WO-07F remain outside scope.

## Sponsor transport

The existing individual current-Review generation produces one Question PDF for
one exact candidate in the existing KRONOS QUESTIONS directory. Both Sponsor
batch routes now invoke the same individual generation machinery for each current
candidate; no combined multi-candidate PDF is added by that action. The batch
requires every current candidate chart before publishing any member. Existing
producer/workspace locks, chart validation, lineage and currentness guards remain.
Individual generation still works without requiring other candidates' charts.

The PDF includes the exact bound structured Answer template as extractable JSON.
The Sponsor supplies this single Question PDF to the existing Chart Analyst
workflow, then places the completed Answer in the unchanged CHATGPT ANSWERS inbox.
No companion `_ANSWERS.json` input file is written into KRONOS QUESTIONS.
`expected_answer_filename` is the output filename for the completed Answer, not
an additional Sponsor input artifact. Internal Review stores retain the template,
PDF, transport manifest, hashes, batch/pack/cycle/chart identities and currentness
binding. Application result `answer_template_path` points only to that internal
store, never to a Sponsor-facing companion. The PDF-extracted template round-trips
exactly to the internal JSON; tests complete it and exercise exact inbox import.

No new Answer engine or relaxed parser exists. Exact filename lookup, ancestor
symlink containment, integrity, candidate/Question/Review/chart binding, partial
Answer availability and identical replay use their published mechanisms. Existing
combined transports/imports remain readable for compatibility; the Sponsor batch
action no longer creates new combined transport populations.

Existing retained transports and their exported historical files are never
rewritten or deleted. V2 Question generation uses a presentation-transport edition:
NSE 2.1.0 / paired MCX 1.1.0. For a current pack with only an older transport,
create a successor transport and filename for the same immutable Question Pack,
cycle, chart and Answer template. No new chart or analytical Question identity is
required. Exact expected Answer lookup then uses that successor's filename.
Legacy transports remain decodable and readable; an existing current-edition
transport re-exports its retained bytes deterministically. Answer schema/version,
question semantics and imported evidence are unchanged. Paired transport pointers
use a separate edition namespace so the historical pointer remains immutable.
An existing directory may contain historical files from earlier operations; no
housekeeping or purge is authorized. The one-PDF guarantee describes outputs of
the new Sponsor operation, with deterministic reuse for identical generation.

## Exact V2 Answer Protocol

`visual_contract_v2.py`, published question wording/order/enums, seven-field
observation schema and all validation rules are unchanged. The PDF explains:

- OBSERVED requires the complete governed question scope, truthful nonempty
  visible_basis and an allowed answer. visible_timeframes must equal the full
  scope in governed order. Never append an unassessed panel to satisfy validation.
- PARTIAL requires genuine assessable scope, truthful nonempty visible_basis and
  status_detail explaining the limitation. List only genuinely assessed qualified
  panels, ordered without duplication. A limitation within all listed panels can
  also be PARTIAL; this is not a command to manufacture missing timeframes.
- NOT_VISIBLE, UNAVAILABLE and INVALID use null answer/basis, empty timeframes
  and nonempty status_detail. NOT_APPLICABLE uses the same null/empty fields;
  its detail may be null. Non-null text is trimmed and at most 2000 characters.
- NSE candidate global OBSERVED requires every Q1-Q10 OBSERVED. Global PARTIAL
  requires at least one OBSERVED/PARTIAL, not all OBSERVED, and no INVALID.
  Any other global status requires all questions to have that exact status.
  No batch-global key is invented. MCX has no global-status field; none is added.
- Q6/Q8/Q9 require 15M/5M, Q7/Q10 all four NSE timeframes. R5 requires
  4H/15M/5M, M5 requires 15M/5M, X1-X5 all four MCX timeframes. R is reference,
  M native and X both roles at each listed timeframe. X scope is the genuinely
  assessable intersection of roles, never the union of unrelated panels.
- Q10/X5 NONE still requires truthful scope/status/basis and null
  why_not_covered_elsewhere. MATERIAL_OBSERVATION requires a nonempty explanation
  of why prior questions do not cover it. All other questions require that field
  null. Unobservable scope is not NONE; neither escape value relaxes validation.

Native MCX remains primary and independently machine-corresponded. Reference
NYMEX/COMEX remains SUPPORTING_VISUAL_CONTEXT_ONLY and independent correspondence
NOT_INDEPENDENTLY_ESTABLISHED. No reference source, constituent relationship,
latency/causality assertion, Promotion or trading authority is invented.

## Governed anchor disposition

SELECTED_Q6_Q9_ANCHOR = NOT_ESTABLISHED.
The PDF retains PREVIOUS_COMPLETED_DAILY_HIGH and PREVIOUS_COMPLETED_DAILY_LOW
with their exact retained candle source identities as machine-owned factual
orientation. Neither direction nor nearest/distance selection chooses a barrier.
Chart Analyst must not choose PDH versus PDL. Where a single qualified anchor is
required but absent, existing NOT_OBSERVABLE/UNCLEAR semantics apply. No substantive
interaction classification is forced. Missing native M5 anchor authority is also
reported conservatively; R5/X3 retain their existing structural-evidence meaning.

**Separate downstream requirement for Sponsor/EA review:** a machine-owned
selected governed-anchor producer with explicit source/selection authority.
It is not implemented, activated or inferred in FB03.

## Qualification and preservation

Deterministic BANKNIFTY tests use analytical subject NSE-INDEX-BANKNIFTY and the
exact Q7 failure class: incomplete OBSERVED rejects; truthful PARTIAL plus detail
and consistent global status passes; genuinely complete all-four OBSERVED passes.
Equivalent multi-scope NSE/MCX tests preserve ordering, no duplicates, required
detail, full-scope strictness and Q10/X5 conditions. All five MCX families exercise
PDF-only generation, exact inbox import, native correspondence, supporting
reference disposition and replay through the existing isolated application gate.

The governed test launcher denies production roots and external operations before
application imports. Focused, affected and full regression, PDF extraction/render
checks, syntax/diff/secret checks and final candidate SHA-256 are recorded in the
external evidence pack. These are deterministic engineering proofs, not empirical
Chart Analyst reliability or qualification of any invented visual fact. No real
Analyst/Provider call, production Review/Question/Answer operation, runtime restart,
Refresh/Discovery, broker operation, staging, commit or push is performed.
