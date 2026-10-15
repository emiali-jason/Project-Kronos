# Theta V3 combined Astra Answer contract — TE-04A

**Status:** Sponsor-authorized, implemented isolated contract candidate. No
publication, runtime commissioning or production acceptance.
**Owner:** EA-Theta Earners.
**Authority:** Sponsor TE-04A contract-slice order, 12 October 2026.
**Baseline:** develop 37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3.
**Boundary:** Evidence contract only. TE-03 authority, TE-04B intake/persistence,
TE-05 classification, Browser orchestration and Outlook changes are not implemented.

## Versioned contracts

| Identity | Version | Responsibility |
| --- | --- | --- |
| KRONOS-THETA-QUESTION-V1 | 3.0.0 | One exact commodity Question with E1/E2 and public authority descriptors |
| KRONOS-THETA-ANSWER-V1 | 3.0.0 | One independently validated commodity Answer |
| KRONOS-THETA-COMBINED-ANSWER-V1 | 1.0.0 | Transport convenience containing exactly five child slots |
| KRONOS-THETA-TRANSPORT-V1 | 2.0.0 | Pure contract descriptor for a complete V3 Question batch |

The existing TE-02 transport 1.0.0 and runtime Question/Answer 1.0.0/2.0.0 remain
unchanged. The transport successor records exact Question hashes and one shared
Macro binding. It is not a new analytical authority. The contract helper does not
commission Questions, persist them, acquire target authority or upgrade older
Questions. Ordinary runtime remains on its retained versioned path.

## One definition and exact binding

schema_v3.py is the governed definition for closed JSON structures, bounds,
availability/classification/relationship vocabulary, blank placeholders and
semantic producer rules. contracts_v3.py derives Question-bound schemas and the
combined template from that definition. The local schema-subset validator follows
the same structural definition, following current Swing's discipline without
importing its analytical schema. No third-party dependency was added.

Every object is closed. All defined object properties are required. Nullable
evidence is explicit, never an omitted field. Completed numeric forecasts are
required for E1 and E2; no NOT_EVALUABLE forecast branch exists.

The Question ID is TEQ- plus SHA-256 of its canonical core excluding question_id.
Question integrity in the Answer is SHA-256 of the complete canonical Question.
Batch ID is TEB- plus SHA-256 of its canonical core excluding batch_id. The
combined Answer pins the complete canonical batch hash separately.

Each Answer contains:
- exact Question identity/hash and per-Question T0;
- commodity/canonical subject, cycle, commodity and Macro chart
  identity/revision/SHA-256;
- public methodology identity/version/hash and target-authority identity/version/hash;
- Analyst identity/model/provenance and truthful analysis completion;
- closed structured research and exactly E1/E2 forecast slots.

The exact target includes option expiry/aware endpoint, underlying exchange future,
futures expiry, settlement-reference identity, exchange/public authority references
and governed price unit. Hashes/references are consumed bindings, not proof that
an owner is commissioned. Genuine TE-03 authority is still not established by
this contract slice.

## Provider-neutral external boundary

V3 has no fields for Kite instrument tokens, Provider connection/request/response
state, broker accounts, orders, holdings, positions, P&L, margin, intended strikes,
intended expression or Sponsor direction/preferences. It exports no internal
Provider object. Public identity fields reject explicit Provider/Kite/broker
implementation components. Source URLs reject embedded credentials, credential
query fields, localhost and private IP addresses; version locators use public
URL/public-identity forms.

Producer guidance requires independent forecasts and expressly excludes all
internal Provider/broker/Sponsor-trade state from the analytical information set.
No Provider or broker call is part of any contract operation. Closed structures
and guidance are not claimed to independently verify arbitrary free-text truth
or act as a universal secret-detection system.

## Structured research

Research retains nine bounded classified/available narrative families:
chart assessment; reference-vs-MCX; bullish evidence; bearish evidence;
macro/fundamental research; commodity-specific research; reconciliation;
counterevidence; uncertainty.

Additional bounded record families:
- chart observations: exact chart, panel, role, displayed instrument/timeframe,
  observation, classification, optional genuinely established visible time,
  completion and unavailable reason;
- evidence claims: identity, statement, classification, sources/observations,
  horizon applicability and assumptions;
- relationships: typed local references, horizons, explanation, limitations;
- scheduled events: known schedule source/time, exact time or honest window,
  horizons, claims, possible impact and limitations;
- assumptions and limitations: identities, scope, horizons, supporting/affected
  references and unresolved consequence;
- sources: publisher/title/kind, public URL/reference, separate publication,
  availability and retrieval, supported availability evidence, observation period,
  original-information/derivative lineage, archive/version locator, relevance and
  linked claims.

Relationship vocabulary is SUPPORT, OPPOSITION, ALIGNMENT, DIVERGENCE,
RECONCILIATION, UNRESOLVED_CONTRADICTION. These are Astra assertions only.
Unresolved contradiction requires an explicit limitation explanation. No strength
state, criterion pass/fail, score, promotion or option-suitability judgment exists.

AVAILABLE evidence contains its defined information; UNAVAILABLE/NOT_APPLICABLE
contain explicit reasons, not fabricated available values. A partially unreadable
chart observation may still retain genuinely established instrument/timeframe/time
information. Missing observation text is not turned into an analytical direction.

## Forecasts

E1/E2 preserve independent exact targets, decimal-string lower/upper/confidence,
rationale, counterevidence, uncertainty, path risk, confidence justification and
material evidence/source/assumption/limitation references. LOWER < UPPER is strict
in V3 only. Confidence is mathematical 0–100, not a methodology threshold.
Negative prices and exact decimal trailing zeroes remain supported. No floats,
scientific notation, nonfinite values, normalization or replacement confidence.

## Temporal and reference integrity

ADR-0066 is preserved. Per-Question T0 equals commissioned created_at exactly.
Different child T0 values are lawful in one combined transport. Analysis completes
at/after T0 and no later than receipt, before both target endpoints, within the
Question's authority applicability.

Known publication <= T0; supported availability <= T0;
availability <= retrieval <= analysis <= receipt.
Publication and earliest availability are independent clocks; no unsupported
publication-before-availability ordering is imposed. Unknown publication is null.
Known schedules may describe events after T0, but their knowledge/source availability
must precede T0. Later actual event outcomes are outside this contract.

Timestamps are aware YYYY-MM-DDTHH:MM:SS with Z or explicit HH:MM offset, at most
six fractional digits, and no leap-second representation. Unsupported precision
fails rather than being silently truncated by Python datetime.

All internal references resolve within their own commodity graph or exact
Question. Entity IDs are unique within the child across families; E1/E2 are
reserved forecast references. Horizon-specific references must include that
horizon. Sources' linked claims exactly mirror claim source links. UNKNOWN lineage
has no invented origin/derivative links. Known local derivative lineage must be
resolvable and acyclic. None of these mechanical checks proves factual authenticity.

## Validation and independent child disposition

Invalid JSON/duplicate keys/nonfinite values/size/depth/node excess, wrong wrapper
identity/version/cycle/batch, wrong population or extra wrapper fields reject the
combined wrapper. After valid wrapper topology, each child is structurally and
semantically validated independently. One failed child does not erase four valid
siblings; the pure result reports complete=false and controlled child failure codes.
A duplicate valid answer_id rejects its colliding children, not unrelated siblings.

The standalone JSON Schema expresses structural constraints and exact commissioned
constants. Decimal comparisons, chronology and graph resolution are governed
semantic rules implemented by the validator and included in generated producer
guidance; JSON Schema alone does not establish those cross-field facts.

All failures are controlled THETA_V3_* codes without raw payload/value echo.
The completed-Answer template contains deliberately invalid null placeholders.
No analytical repair or truncation occurs.

## Original byte representation and later TE-04B

json_evidence.py defines a bounded pure parser/offset contract. Whole-file raw
SHA-256 differs from canonical package SHA-256 where formatting/escapes differ.
For each answers.<subject> value it returns exact original UTF-8 bytes, raw hash,
canonical child hash and end-exclusive UTF-8 byte offsets. Member name, colon and
surrounding whitespace are outside that child value span; everything remains
preserved in the whole original file.

This works with Unicode text, escaped keys/characters, quotes and formatting.
Parse-and-reserialize is never described as original child bytes. No inbox access,
acceptance receipt, history/selection update or intake persistence is implemented.
Pure replay comparison allows identical identity/raw-hash replay, rejects same
identity/different raw hash, and distinguishes a new identity. Later intake owns
durable identity conflict enforcement and currentness, not this comparison helper.

## Technical bounds

| Bound | Value / existing basis |
| --- | --- |
| Child raw bytes | 2 MiB, retained Theta V2 ceiling |
| Combined raw bytes | 5 × 2 MiB + 64 KiB wrapper allowance |
| Narrative strings | 16,000 characters, retained Theta convention |
| Sources per commodity | 200, preserving the prior two × 100 horizon capacity |
| Evidence / relationships / reference arrays | 200 |
| Chart observations | 96, supporting multiple observations across all composite panels |
| Events / assumptions / limitations | 100 each |
| Identity / hash / decimal | 100 / 64 / 128 characters |
| JSON depth / nodes | 64 / 250,000 |

These are interface resource bounds, not analytical counts or criteria. Exceeding
them is rejection; content is never silently truncated. The generated schema is
the exact source for each leaf string/array bound.

## Qualification and hold

Focused tests cover positive/negative schemas, independent child failure, bindings,
decimals, chronology, unavailable evidence, graph references, lineage, hostile JSON,
raw byte spans, replay comparison, bounds and historical compatibility. Retained
Theta and focused Swing contract tests are also run through tools/kronos_test.py,
whose kernel layer denies production stores, credentials and external networking.

TE-05 methodology remains unapproved. Structured evidence retention is ready for a
future approved deterministic policy; it is not a quality classifier, empirical
validation of research, or trading authority.

TE-04B COMBINED INTAKE/PERSISTENCE: NOT STARTED.
