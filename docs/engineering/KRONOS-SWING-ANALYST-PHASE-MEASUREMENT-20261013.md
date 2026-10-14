# Swing Analyst phase measurement — Slice 2, 13 October 2026

Status: Sponsor-authorized bounded diagnostic engineering candidate; review,
publication and genuine measured execution are separate gates. No production
performance defect or optimization is established. Slice 1 R2 is frozen,
engineering PASS and undeployed; its files are not changed here.

## Ownership and current base

Base: `d44b191289da3e6c05b034310267f04fdd084a2f`, freshly clean and equal to
tracking and direct remote. The observed 12 October execution ran in the
independent manual Chart Analyst worker, thread
`01a10fcd-6b05-72c1-89eb-56c1885fa040`, turn
`01a12f28-a819-7448-8f41-a6dc24160d1e`. Canonical Visual V3 consumes the supplied
PDF after that external work. Older optional OpenAI adapter/cache/telemetry
paths are separate and are not used to reinterpret this manual execution.

The new `tools/swing_chart_analyst_measurement.py` is opt-in external EA Swing
tooling using only the standard library. It is not imported by any application,
startup, Browser, Provider, Review, Reports, Portfolio or Intraday owner. It
creates no server route, capability or automatic operation. It changes no
existing artifact builder/extractor/validator or test-isolation harness.
No shared production interface is touched. Applicable shared-owner review is
therefore not required for this isolated standalone tooling scope; historical
Slice 1 owner approvals do not transfer. Reassess any later integration/hook.

## Diagnostic contract and attribution

Each exclusive caller-owned run directory binds one public Analyst execution
identity and exact Question PDF identity/hash/size, plus ordered candidate and
chart metadata copied from the verified handoff: exact instrument, candidate,
leg, timeframe, request, subject, revision and chart hash. The helper verifies
Question bytes and internal descriptor/hash consistency. It does **not** certify
canonical currentness, PDF transport, chart eligibility or analytical bindings.
Those remain with their existing owners and the separately authorized workflow.
The descriptor is a diagnostic sidecar, never an Answer/Question schema change.

Direct operation spans use `monotonic_ns` in one explicit process clock domain.
Wall-clock timestamps provide correlation only; wall rollback does not change
monotonic elapsed time. A new Meter/process gets a distinct clock domain.
Restart reads retain unfinished spans as INCOMPLETE, never infer their duration
or resume the operation. The context manager records around the existing call;
the optional CLI passes the original command, environment, stdout/stderr and
exit result through in serial order. Disabled is the CLI default and records
nothing. No child command or automatic retry is embedded or scheduled.

Fixed/pack, per-candidate, per-timeframe and total-execution attribution are
separate. FIXED_PACK means an observed once-per-pack invocation, not proof that
its cost is constant across page/candidate counts. Batch decode/preparation
cannot be divided into invented candidate costs. Total M17 is not counted as
fixed pack cost. Descriptor order is retained; the helper neither schedules nor
reorders candidate/timeframe work or changes serial work into concurrency.

| Phase | Observable boundary and limitation |
| --- | --- |
| M01 | Question identity/integrity operation; raw hash check is not currentness certification |
| M02 | Existing PDF extraction operation |
| M03 | Existing contract/template parser operation |
| M04 | Existing binding/metadata preparation, pack or candidate as actually observed |
| M05 | Existing composite decode; batch remains pack-attributed |
| M06 | Existing panel preparation/crop/enlargement, candidate/timeframe when actually scoped |
| M07 | Candidate visual-assessment envelope **only if** genuine public start/end boundaries exist |
| M08 | Timeframe visual-assessment envelope **only if** genuine public boundaries exist, with exact leg/chart binding |
| M09 | Observable governed observation-construction operation; model-side authoring otherwise UNKNOWN |
| M10 | Observable combined Answer construction |
| M11 | Existing schema/enum/duplicate-key/binding validation operation |
| M12 | Existing PDF/artifact build operation |
| M13 | Existing transport/extraction verification operation |
| M14 | Observable rendered-QA operations; unobservable visual/model inspection remains UNKNOWN |
| M15 | Delivery/library export public operation receipt or direct wrapper |
| M16 | Explicitly observed orchestration/context overhead, never arithmetic remainder |
| M17 | Whole execution envelope or a minimal public execution receipt with legitimately recorded duration |

There is currently no public internal model/visual-reasoning callback for the
observed chat. M07/M08 and model-side portions of M09/M14 therefore remain
UNKNOWN unless the next authorized execution genuinely exposes attributable
boundaries. A `view_image` tool duration is not visual assessment duration.
Do not collect hidden reasoning, hidden tokens or chain-of-thought. Phase names
are diagnostic labels, not a new Analyst instruction or analytical requirement.

The strict minimal public-receipt importer records DERIVED_PUBLIC_RECEIPT with
canonical public-receipt content digest (not raw transport-byte identity) and recorded operation hash, wall bounds, elapsed nanoseconds,
outcome, allowlisted failure code and optional result hash. It accepts no raw
logs, reasoning, argv, stdout/stderr, credentials or Provider/control tokens.
It does not derive duration from wall time or invent missing boundaries.
Operation SUCCEEDED means the observed call returned normally/exited zero, not
analytical confirmation or readiness. A controller observing a returned validator
rejection must supply the existing diagnostic VALIDATION_REJECTED code; the
wrapper never parses or rewrites child output to invent that result. Direct
events are DIRECT_MONOTONIC. Failure messages are not stored; allowlisted
codes include PROCESS_EXIT_NONZERO, OPERATION_EXCEPTION, JSON_DECODE_ERROR and
VALIDATION_REJECTED. The operator may retain separate governed safe diagnostics
through the existing owning path; this tool does not ingest that content.

The report retains every start/end, elapsed duration, candidate/timeframe/leg,
operation/result hash where supplied, outcome, explicit retry flag/link, source
receipt digest and method. All phases without recorded observable boundaries
are UNKNOWN. Started without completion is explicitly INCOMPLETE. Different
clock domains are not silently combined into a fabricated timeline.

Measured-stage sum may overlap. Only a same-clock direct M17 envelope enclosing
all stages supports an interval-union covered duration and numerical unattributed
remainder. Overlap is counted once in that union. Missing total/cross-domain or
derived boundaries yield UNKNOWN remainder. Same-clock contradictions reject.
No remainder is assigned to M16 or used to infer hidden assessment boundaries.

## Persistence, replay and operational use

Run creation is exclusive, private0700, with private0600 records. START and
END records are immutable separately, so failure/interruption remains visible.
Each event binds the run descriptor and an exact sequence/hash. An exclusive
run lock protects append; no-overwrite hard-link publication and file/directory
fsync retain existing bytes. Malformed fields, changed bindings, unexpected
files, symlinks, duplicate JSON keys, wrong candidate/chart attribution,
conflicting replay and conflicting/ambiguous totals fail safely. Production
store paths are denied by the helper; qualification also kernel-denies them.
Read/report is write-free. Identical public-receipt replay returns the existing
immutable event. A known already-recorded direct operation identity is rejected
before another child dispatch; no result is fabricated. Explicit retries need
an actual retained failed predecessor and a new operation identity.

For a future separately authorized genuine Review, an execution controller can
initialize a new directory from the verified handoff descriptor and apply:

```text
python tools/swing_chart_analyst_measurement.py init --root ABSOLUTE_NEW_DIRECTORY --binding VERIFIED_DIAGNOSTIC_DESCRIPTOR --question-pdf ORIGINAL_QUESTION_PDF
python tools/swing_chart_analyst_measurement.py measure --enabled --root ABSOLUTE_DIRECTORY --phase M02 --operation-sha256 PUBLIC_OPERATION_ID_HASH -- ORIGINAL_UNCHANGED_EXTRACTION_COMMAND
python tools/swing_chart_analyst_measurement.py report --root ABSOLUTE_DIRECTORY
```

These are usage forms, not execution authorization or populated findings.
Use a context-manager span for in-process callbacks and import-public-receipt
for minimal legitimately exposed external timing receipts. No re-run of the
completed ADANIPORTS/INFY Review, new opportunity, Analyst task/message, changed
prompt, Question Pack, template or genuine Answer is part of qualification.
Enabling measurement never authorizes the wrapped operation.

## Qualification and overhead

Synthetic owning qualification covers timing, attribution/order, fixed/total
separation, UNKNOWN and unfinished state, failure/retry/replay, strict fields
and privacy, unchanged operation output/stdout/stderr/exit, disabled/default
behavior, concurrent-writer immutable publication primitives (storage exclusivity only,
not parallel Analyst assessment) and invalid evidence
preventing child dispatch. The failed derived-method checkpoint is preserved.
Existing NSE/MCX visual-contract and isolation suites are affected protections;
all production source bytes remain identical to base. Slice 1 R2 hashes remain
unchanged and paths are disjoint; no release composition is made here.

Journal overhead is real: measurement samples include empty direct operations
at1/16/64 spans and record the disabled baseline and enabled elapsed separately.
The five-second64-span catastrophic-overhead test bound is an engineering
fixture guard, not a market/trading policy, latency promise or genuine acceptance
limit. Direct operation duration excludes its journal publication; enclosing
M17 includes actual orchestration/journal time without falsely naming it M16.
CLI interpreter startup can add further overhead; its end-to-end enabled/default
comparison is retained separately. Actual future environment/Review overhead
remains to be observed. No zero-overhead or speedup claim is made.

## Carried gates

Historical baseline remains783.266 seconds total,13.453 seconds reported tools,
769.813 seconds unattributed: INSUFFICIENT TIMING EVIDENCE, no demonstrated
production performance defect. No new genuine execution is performed here.

The45,142-byte Analyst PDF versus70,111-byte host PDF transformation remains
unresolved. Matching working-JSON hash establishes no demonstrated content
alteration, not PDF equivalence. Optional result hashes can improve future
boundary attribution without changing artifacts or redesigning transport.
No transformation record or latency relationship is manufactured here.

Slice3: DEFERRED — GENUINE MEASURED EXECUTION REQUIRED. No parallel assessment,
optimization or numerical speed target. Slice4 Reports UX remains separate.
A fresh impact-based regression decision is required on actual final composition;
this standalone non-runtime sidecar does not automatically require a full run.
All production/Provider/Review/admission/trading/research operations are ZERO.


## Future release-authority consideration

The unchanged explicit WO12 commissioning verifier permits src/tests/docs and
only tools/kronos_browser.py, and requires exact changed-path equality. It
would reject tools/swing_chart_analyst_measurement.py if added to a new
commissioning manifest. This external diagnostic candidate requests no
commissioning or runtime distribution and does not widen that guard. A later
release/distribution proposal must resolve its source-authority scope explicitly
with the owner while preserving the original commissioning boundary. This is
a future integration gate, not a demonstrated production defect or authority
for rebinding/recommissioning. No runtime load is needed to qualify the helper.


## Preserved first freeze and bounded replay successor

The first305-pass packet remains unchanged historical evidence. Final persistence
review reproduced identical public-receipt duplication when operation identity
was legitimately unavailable. This successor corrects only that diagnostic
replay boundary: an identical receipt and attribution returns its retained event;
changed receipts in the same identity-unavailable scope or identical receipts
rebound to another candidate reject as ambiguous/conflicting replay. Multiple
distinct observations in such a scope need genuine operation identity; the
helper does not invent it. The failed reproduction is preserved, with positive
known/unavailable identity and cross-candidate rejection coverage. No existing
production/shared module changed. Unchanged affected evidence is retained with
explicit source-continuity proof; final owning qualification binds these bytes.


Final security qualification also covers case-folded canonical production-root
aliases on macOS. The prior case-sensitive guard's two negative failures are
retained. The final diagnostic guard conservatively denies those aliases before
reading or creating a run; no production/shared guard is changed. Historical
intermediate frozen packets remain unchanged.

## Bounded final-regression R2 concurrency correction

The unchanged fourteen-path final composition's protected R2 run failed at one
concurrent diagnostic writer, with only `DIAGNOSTIC_MEASUREMENT_FAILED` retained.
That original exception remains unattributed; its exact hidden predicate cannot
be recovered from the surviving R2 bytes. R2 remains FAIL, not reclassified.

The authorized isolated forensic reproduction uses the actual unchanged
`Meter` and CLI `main`. It pauses one writer only at the existing no-overwrite
publication boundary while the exclusive append lock is held and the private
`.timing-` staging file exists. A second genuine diagnostic writer reaches
`_values -> events` outside that lock and raises
`MeasurementError: DIAGNOSTIC_INCOMPLETE_PUBLICATION`. Complete traceback,
child exit status and staging evidence are retained in the R2 failure-resolution
output. This proves a supported two-writer storage defect, without claiming
that the original R2 child necessarily failed at this same hidden predicate.

The bounded correction makes public validated event reads hold a shared lock.
Append still holds the existing exclusive lock through complete validation,
exclusive publication and final readback. Operation-identity and retry checks
now consume that same locked snapshot before a START/DERIVED commit; duplicate
identity cannot pass two independent pre-append reads. Public-receipt replay
selection and append use one exclusive scope, preserving identical replay and
conflict rejection. Private `_events` / `_append_locked` methods are called only
by code holding the respective lock. No file is ignored, validation weakened,
sequence fabricated or overwrite allowed. Read/report remains write-free;
all incomplete, failure, retry, attribution, permission and default-off rules
remain unchanged. No application imports or production owner is added.

A deterministic two-process regression holds real publication staging and
requires the reader to wait for release, then validates four START/END records,
sequence integrity, private permissions and observational report bytes. It
fails unchanged predecessor source and passes corrected source. Existing
concurrent CLI, malformed evidence, replay/conflict, candidate/timeframe and
NSE/five-family contract tests remain required. Another owning regression
prepares two identical operation starts before append and requires the second
to reject before dispatch without another write.

The same authorized failure-resolution packet separately preserves two
unchanged-base exclusive rehearsal-summary collisions and one unchanged-base
Intraday wording expectation failure. Those are test orchestration/assertion
corrections, not production Intraday changes. Authentic historical restoration
coverage uses the checksum-verified retained IWO-06A snapshot and its existing
canonical-filename child, not fabricated authority. Exact successor review,
scoped qualification and a separately authorized full R3 remain release gates.
S3 remains DEFERRED — GENUINE MEASURED EXECUTION REQUIRED. Storage concurrency
correctness does not establish parallel Analyst execution or a speedup.
