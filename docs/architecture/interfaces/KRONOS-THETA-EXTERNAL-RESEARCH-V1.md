# KRONOS Theta external research V1

**Status:** Sponsor-authorized engineering contract candidate. Not published,
deployed or commissioned for production.

**Owner:** EA-Theta Earners. Instrument and Market ownership remain unchanged.

**Authority:** `KRONOS-THETA-TE01-V1-END-TO-END-CLOSURE-01`, Sponsor order
supplied 11 October 2026; [Living Architecture Record V1](https://docs.google.com/document/d/1Xidhi90vHpDDY5msGDPxlqBAl7mzYUi3aeb2KnuxLm8/edit),
updated 7 October 2026. The order opens bounded engineering, not broker or
Provider authority. TE-RQ-001 and TE-RQ-002 are retained.

## Product contract

**OPERATIONAL_AUTHORITY:** The order authorizes building the external research
workflow: Sponsor charts → portable Question Pack → external Analyst → exact
manual Answer intake → validate/bind/persist → summary/detail presentation.
This statement describes the engineering mandate, not production activation.
No internal range engine, strategy, strike recommendation, execution, Greeks,
sold-strike capture or position monitoring is commissioned.

**FACT:** The five intended labels reuse the existing DOMAIN-001 mappings:

| Theta label | Existing canonical subject | Existing family label |
| --- | --- | --- |
| GOLDM | MCX-SUBJECT-GOLDM | GOLDM |
| SILVERM | MCX-SUBJECT-SILVERM | SILVERM |
| COPPER | MCX-SUBJECT-COPPER | COPPER |
| CRUDEOIL | MCX-SUBJECT-CRUDE | CRUDE |
| NATURALGAS | MCX-SUBJECT-NATGAS | NATGAS |

These mappings come from `instrument.active_derivative`; Theta creates no
canonical option classification and does not extend Intraday's NATGAS policy.

## Exact target dependency

**FACT:** The inspected current Instrument contracts establish commodity
subjects and active futures selection, not the exact next two applicable
option expiries and their exchange-defined underlying/settlement references.
An active future or Provider master presence does not establish those targets.
No inspected source establishes a Theta-applicable methodology binding either.
Both dependencies are **NOT_ESTABLISHED** for production.

`ThetaWorkflow.authority_provider(subjects, aware_timestamp)` is an explicit
consumer injection point for a commissioned owner adapter. It is not a Browser
upload, auto-enrolment file, Provider interface or new source of authority.
Default composition supplies no adapter and fails closed before Question
generation. Chart intake and unavailable-state presentation remain usable.
No import can succeed without a previously retained, bound Question.

The owner must supply an `AuthorityBundle` whose validity interval applies at
Question creation. For each requested subject it supplies exactly E1 and E2,
with each target containing:

- subject and existing canonical subject;
- E1/E2 horizon;
- exact option expiry date and timezone-aware expiry endpoint;
- exact exchange-defined underlying futures identity and futures expiry;
- applicable settlement price identity, preserved verbatim;
- approving authority reference and applicable exchange evidence reference;
- canonical target `OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE`.

It also supplies the approving methodology reference and verbatim applicable
instructions. Nonempty references, date ordering and structural validation do
not prove source authority. The commissioning owner must establish eligibility,
calendar/session applicability, next/second-next cardinality, provenance and
exact mappings. Theta must not select the nearest future, create arbitrary
30/60-day horizons or assume E1/E2 share a future. It never equates Daily
Settlement Price with Due Date Rate. Synthetic bundles are test doubles only.

## Question and chart contract

`KRONOS-THETA-QUESTION-V1 / 1.0.0` has a content-addressed `TEQ-<SHA256>`
identity over the canonical JSON core. It binds exact original chart bytes,
Sponsor-declared chart labels and information cutoffs, subjects, owner targets,
methodology, instructions, owner validity limit and aware creation time.

PNG/JPEG chart input is bounded to 16 MiB and 40 million pixels per commodity.
The label and cutoff are Sponsor declarations, not independently verified
visible identity/time proof. One supplied image can contain multiple panels.
Charts may be supplied separately; each selected commodity has one current
chart revision. A new revision clears that subject's Question selection.
Repeated identical bytes with identical declarations are idempotent.

### TE 01 composite chart intake

**OPERATIONAL_AUTHORITY:** The Sponsor's TE-01 Swing-style chart-intake order
authorizes a focused paste card and Choose File fallback for each of GOLDM,
SILVERM, COPPER, CRUDEOIL and NATURALGAS, plus one shared GLOBAL_MACRO card.
The five commodity subjects and their existing canonical mappings are unchanged.
GLOBAL_MACRO is supporting evidence, not a forecast subject or a new Question
generation gate. Its inclusion and final blocking policy belong to TE-02.

Each commodity expects one original TradingView composite: reference COMEX/NYMEX
1D, 4H and 1H panels and corresponding MCX 1D, 4H and 1H panels. GLOBAL_MACRO
expects one composite supporting DXY, US 10Y, US 30Y, USD/INR, Nasdaq-100,
USD/CNH, CSI 300 and Dow Jones. The focused card is Sponsor's role attestation.
KRONOS neither reads nor verifies panel identities, prices or visible times.
It does not split, OCR, rewrite or interpret the original image.

The raw PNG/JPEG Browser action binds its explicit subject/role, selected analysis
cycle and expected revision. The first accepted chart creates an intake-cycle
identity; mere observation does not create one. All six roles share that cycle.
Sibling intake does not invalidate another card's revision. A stale cycle or
selected revision is rejected rather than rebound to the latest evidence.

Original bytes and seven-field chart records retain their existing content
identities. A separate immutable intake revision records cycle, role, commodity
subject or GLOBAL_MACRO, chart identity, aware acceptance time, media type, byte
length, original SHA-256, predecessor revision and time basis. Replacement
selects a new revision for that role only. Other five roles are unchanged;
original records and complete selection history remain retained. There is no
directory-order or mtime selection rule. Legacy selected chart records remain
readable without inventing their historical cycle or acceptance timestamp.

Card intake uses KRONOS receipt time, explicitly labelled
`INTAKE_RECEIPT_NOT_CHART_TIME`. The existing chart metadata field
`information_cutoff` receives this receipt bound; it is not proof of the image's
visible timestamp, latest candle, research cutoff or freshness. The existing
declared-cutoff JSON action remains compatible. TE-01 adds no Question or Answer
schema field and establishes no chart-time analytical authority.

Exact-current preview reads require the selected role, cycle and revision;
stale preview URLs fail closed. Question readiness reflects actual current
Question selection and existing authority checks, not a fabricated implication
that CHART READY means a Question can be generated. Commodity replacement clears
only that commodity's Question selection. Macro intake/replacement does not
invalidate commodity Question selections or alter the existing five-chart pack.
Question methodology, Macro transport inclusion and Answer semantics are not
redesigned in this slice.

The portable ZIP contains a PDF with embedded charts, `question.json`,
`answer-template.json`, exact original chart files and a checksum manifest.
PDF/ZIP binaries are retained immutably; downloads never rerender them.
Instructions require commodity-specific macro, supply/demand, inventory,
currency, event/geopolitical and global research, distinct E1/E2 ranges and
confidence, sources, supporting/opposing evidence, uncertainty and reasoning.
They prescribe no new indicator, threshold or analytical model.

Question packs may cover any nonempty subset of the five commodities, in fixed
subject order. Every requested subject requires both horizons. A subset pack
is never represented as a complete ten-forecast assessment. One combined pack
has ten forecasts only when all five subjects are included.

## External Answer schema

`KRONOS-THETA-ANSWER-V1 / 1.0.0` is one UTF-8 JSON object, at most 2 MiB,
without fences, duplicate keys, nonfinite JSON values or additional fields.
The template carries all required identities; null placeholders are deliberately
invalid. KRONOS never completes or repairs them.

| Field | Representation and validation |
| --- | --- |
| schema_identity / schema_version | Exact constants above |
| answer_id | 1–100 ASCII alphanumeric, underscore or hyphen characters |
| question_id / question_sha256 | Exact retained Question and canonical JSON hash |
| analyzed_at | Aware ISO timestamp, at/after Question creation and no later than receipt |
| information_cutoff | Aware ISO timestamp, at/after all supplied chart cutoffs and no later than analysis T0 |
| analyst | Exactly identity, model, provenance; nonempty bounded strings |
| forecasts | Exactly two distinct bound targets for every requested subject |

Each forecast has exactly `target`, `chart_sha256`, `lower`, `upper`,
`confidence_pct`, `analysis`, `sources`. `target` must equal the complete retained
target dictionary; its horizon, subject, expiry, future and settlement identity
cannot be repaired or substituted. `chart_sha256` matches that subject's bytes.

Range and confidence values are **decimal strings**, not floating-point JSON
numbers. Optional leading minus, integer part and optional decimal fraction
are accepted; scientific notation, whitespace, bool, NaN and Infinity are not.
The original strings remain unchanged, including decimal trailing zeroes.
`lower <= upper`; confidence is within the mathematical percentage
representation `[0,100]`. These are representation checks, not trading gates or
confidence thresholds. Negative bounds are not silently forbidden or rounded.

`analysis` contains exactly `chart_analysis`, `global_research`,
`supporting_evidence`, `opposing_evidence`, `uncertainty`, `reasoning`. Each is
an object with exactly classification and text. Classification is FACT,
RESEARCH_RESULT or HYPOTHESIS. These are external Analyst assertions; accepting
their structure does not verify their truth. The Analyst cannot grant
OPERATIONAL_AUTHORITY. Text is preserved exactly and HTML-escaped for display.

`sources` has 1–100 objects, each with title, HTTP(S) URL, published_at,
accessed_at and evidence text. Access/publication cannot be after the information
cutoff. Unknown publication time is null and displays NOT_ESTABLISHED; KRONOS
does not fabricate it. Retrieval or independent source verification is not an
intake side effect. Bounded strings and source counts protect the local interface,
not analytical usefulness.

Acceptance occurs only before every bound expiry endpoint and while its Question
is still selected for every requested subject and its authority validity applies.
No arbitrary freshness TTL is introduced. Replaced chart/Question selection,
expired targets and expired authority validity are explicit, not “current”.
The original E2 is not promoted/relabelled E1 after E1 expiry.

## Local persistence and intake

The existing KRONOS directory conventions are reused, with product isolation:

- Evidence: `~/Library/Application Support/KRONOS/evidence/theta-v1`.
- Sponsor Question outbox: `~/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`.
- Sponsor Answer inbox: `~/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/CHATGPT ANSWERS`.
- Exact expected Answer filename: `<question_id>_ANSWERS.json`.

**OPERATIONAL_AUTHORITY:** TE-01A records the Sponsor-frozen subsequent-slice
transport destinations exactly as follows:

- Outbound Questions: `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`.
- Inbound Answers: `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/CHATGPT ANSWERS`.

This UX slice does not switch the sandbox to those production directories or
redesign Question/Answer intake. Disposable test paths remain in force. Paths
remain configuration/evidence, not normal Sponsor-page content. Applying the
production transport configuration belongs to its subsequent authorized slice.

All defaults are independent of checkout/worktree location. The manual import
action reads only the expected file; it never scans arbitrary files, rewrites,
moves or deletes Sponsor input. No background collector, external upload,
Analyst connection or Provider session is created.

Directories and files are accessed with no-follow descriptors. Nonregular
files, symlinks, hardlinked intake and excessive bytes fail closed. A
cross-process file lock serializes reads, writes and selections. Temporary bytes
are flushed/fsynced before no-clobber immutable publication. Atomic replacement
is limited to the presentation selection pointer, whose complete versions are
retained in selection history. Missing/corrupt selected dependencies never cause
a fallback to an older forecast.

Raw Answer bytes are content-addressed and retained **unchanged** before an
immutable acceptance receipt commits them. The receipt binds Question hash,
Answer hash/identity and accepted-at time. The single Answer identity cannot bind
different bytes or another Question. Identical accepted replay is idempotent,
including after supersession/expiry; it validates the original acceptance and
never reselects historical evidence or manufactures a new T0. New/late or
superseded pending Answers still fail closed. Conflicting bytes always fail;
different raw bytes conflict even if their parsed values appear similar.
SHA-256 integrity does not prove Analyst authorship, source truth or calibration.

TE-RQ-002 later outcome records are separately appended through an owner-only
Python consumer method; no Sponsor/Provider/outcome API is introduced. The exact
target, authoritative terminal value/reference, aware observation time and
original Answer hash bind the outcome. Inclusive containment is PASS only when
lower <= terminal <= upper. Outcome records never rewrite an Answer, receipt or
selection and do not claim option exercise, profitability or trading authority.

## Presentation and qualification

The existing Browser product seam owns `/theta-earners`, `/theta-earners/new-analysis`, detail, Question
download and exact original Answer download. Bounded POST actions retain charts,
generate Question packs and explicitly import expected local Answers. Shared
loopback, same-origin and maintenance admission remain server-owned.

Optional Theta registration follows the unchanged Intraday route owner. A Theta
import, construction or registry-validation exception leaves the existing
product registry intact and registers no Theta mutation route. The unchanged
shared Theta placeholder may still answer GET requests; it supplies no forecast.
The guard does not catch failures constructing the existing Intraday owner.
Theta never owns Swing or Intraday paths and supplies no new runtime coordinator.

**OPERATIONAL_AUTHORITY:** TE-01A separates Sponsor reading from preparation.
`/theta-earners` opens OUTLOOK by default; `/theta-earners/new-analysis` opens
NEW ANALYSIS. Both use the current Browser shell and tab conventions. No shared
Browser source or frontend framework change is required.

OUTLOOK presents current accepted E1/E2 ranges/confidence first, exact expiry
dates second, and compact current-analysis timestamps/status. Displayed local
times use Asia/Kolkata; exact original aware timestamps remain in HTML time
metadata and retained detail. With no current accepted analysis, one clean
empty state links to NEW ANALYSIS instead of five unavailable placeholder rows.
Partial current selections show no fabricated or older replacement forecast.
OUTLOOK contains no chart intake, Question/import controls, filesystem paths,
manual-workflow prose or engineering diagnostics. Missing, pending, invalid,
expired and superseded data are not numeric current forecasts.

NEW ANALYSIS contains the qualified six chart cards and existing Question/Answer
controls, compact counts and short operational context. The paste script, card
renderer, validation and immutable intake/persistence remain unchanged. View
switching is observational and does not create a cycle or rewrite selection.
Successful/failing Question and Answer actions return to NEW ANALYSIS; chart
refresh links stay there. Macro policy and analytical contracts are unchanged.

Current commodity links reach retained detail, which supplies BACK TO OUTLOOK.
Detail presents exact target identities, all external
analysis/source sections, original chart, T0/cutoff and original Answer integrity.
Confidence is explicitly Analyst-stated terminal containment, never calibrated
KRONOS probability or economic/no-touch probability. No second analytical
opinion is added.

**RESEARCH_RESULT:** Protected synthetic tests qualify implementation mechanics
only. Predictive usefulness and confidence calibration remain NOT_ESTABLISHED.
Without authoritative terminal evidence, historical accuracy is NOT_EVALUABLE;
unoccurred expiry events are NOT_YET_EXERCISED. Production activation, natural
Sponsor/Analyst round trip, qualified publication and exact owner commissioning
remain separate from passing tests.

## TE-02 prospective Question Pack successor

**Status:** Sponsor-authorized isolated engineering candidate, 2026-10-11.
The TE-02 order and its explicit Option 1 temporal authorization govern this
section. [ADR-0066](../adr/ADR-0066-THETA-PROSPECTIVE-INFORMATION-SET-AND-RETRIEVAL-TIMES.md)
records that narrow decision. Earlier sections remain historical version `1.0.0`
behavior, not instructions to reinterpret old artifacts.

NEW ANALYSIS commissions five independent canonical commodity Questions through
`commission_questions`. The retained `create_question` seam supports legacy V1
compatibility/rehearsal; it is not the new Sponsor action. Each new Question is
`KRONOS-THETA-QUESTION-V1 / 2.0.0`, one commodity and exactly two target slots.
It binds the current analysis cycle, commodity and shared Macro chart IDs,
revision IDs, original SHA-256, exact E1/E2 authority, methodology and the matching
`KRONOS-THETA-ANSWER-V1 / 2.0.0` template. GLOBAL_MACRO is mandatory supporting
evidence for this new commissioning path, never a sixth forecast subject.

T0 is `information_cutoff`, exactly frozen at Question `created_at`. Both chart
declaration/receipt cutoffs must be no later than T0. Repeated identical inputs
reuse the exact identity, T0 and retained binaries. Changed commodity chart,
shared Macro, target or methodology produces a new Question identity; previous
Question and transport bytes remain immutable. A changed Macro makes all bound
prospective Questions noncurrent without rewriting historical selections or V1
semantics. Old prospective Answers cannot become current against changed bindings.

The prospective Answer preserves Question T0 verbatim. Each source adds required
`available_at` to the retained field set, with these ordering rules:

- supported `available_at <= T0`;
- known `published_at <= T0`; unknown publication remains `null`;
- `available_at <= accessed_at <= analyzed_at`;
- Question creation `<= analyzed_at <= receipt`.

Actual retrieval and analysis may be after T0, without a research-speed deadline.
First publication/availability after T0 is excluded; later retrieval alone is not.
Evidence text must support availability when publication is unknown. KRONOS does
not verify source truth. Historical `1.0.0` retains retrieval/publication at/before
its Answer cutoff. Version pairing is exact; no coercion, old-record rewrite or
new Answer-import UX is introduced. All other retained numeric representation,
classification, receipt and lossless/raw-byte rules remain unchanged. Astra is
instructed to use strict LOWER < UPPER; this slice does not broaden the authorized
temporal correction into a historical range-validator redesign.

Individual portable ZIPs contain readable Question PDF, canonical JSON, exact
commodity and Macro originals, governed blank Answer template and SHA-256 manifest.
The combined ZIP preserves all independent Question/template identities, stores
Macro once, and binds explicit per-commodity READY/BLOCKED status. Four ready of
five is PARTIAL, not a complete cycle. Existing nonempty subset support is retained,
not a new Sponsor commissioning policy.

New transports use deterministic cycle/subject/identity filenames, with a visible
SYNTHETIC prefix for qualification. Frozen outbound is KRONOS REVIEW PACK / Theta
Earners / KRONOS QUESTIONS. Safe no-follow, conflict preflight, atomic individual
file publication, readback verification and immutable replay are retained; no
arbitrary latest/mtime authority is used. Failed generation selects no valid pack
for the failed commodity. Independently complete files may remain after a later
I/O failure, but are never silently selected as a completed combined cycle.
The future Answer destination is instructions only; TE-04/TE-05 UX is not started.

PDFs preserve full original composites on separate landscape A3 pages and readable
text on A4 pages. No crop, stretch, redraw, annotation, OCR or panel splitting is
performed. The mandate requires independent deep global/commodity research,
counterevidence, horizon-specific events, reference/MCX reconciliation, independent
E1/E2 and terminal containment confidence distinct from intraperiod path/no-touch
risk. No strategy, strike, adjustment, trading or broker advice is authorized.

Genuine authority remains fail-closed. Explicit `qualification_mode=True` permits
only clearly marked synthetic rehearsal; default composition supplies no target
adapter. No Astra API, Provider research, broker action, production write or later
slice is commissioned by this successor.

## TE-04A prospective contract-only successor — 12 October 2026

The Sponsor's TE-04A order authorizes the isolated
[V3 combined Answer contract](KRONOS-THETA-V3-COMBINED-ANSWER-CONTRACT.md),
with provider-neutral public bindings and assessment-ready evidence retention.
Question/Answer 3.0.0 and transport-only combined Answer 1.0.0 are separate from
the retained 1.0.0/2.0.0 historical paths above. Existing runtime producers,
intake, chart/Question behavior and Browser projections remain unchanged.
This section records a later contract slice, not a rewrite of TE-01/TE-02
chronology. TE-03 authority and TE-05 methodology are not commissioned here;
TE-04B intake/persistence and production publication are not started.
