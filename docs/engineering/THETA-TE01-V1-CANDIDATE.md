# Theta V1 engineering candidate and qualification

**Status:** Isolated source candidate with passing actual-impact tests and a
synthetic Browser restart rehearsal. V1 convergence, final-candidate freeze,
publication and production runtime loading are not established. Exact target
and methodology commissioning remain unresolved.

**Order:** KRONOS-THETA-TE01-V1-END-TO-END-CLOSURE-01.

**Base:** Verified `origin/develop` at
`37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3` on 11 October 2026.

## Candidate scope

**FACT:** The candidate implements external research intake and presentation
under the [Theta contract](../architecture/interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md).
It does not implement the superseded internal Expiry Range Engine or active
position monitoring. The Drive baseline remains unchanged. No production store,
Provider session, broker endpoint, launcher or deployed process was changed.

TE01A establishes existing subject identity reuse, ownership and a versioned
engineering contract. TE01B retains Sponsor charts and generates portable,
immutable Question PDF/ZIPs when the owner dependency is supplied. TE01C validates
exact manual JSON Answers without analytical repair. TE01D binds independent
E1/E2 targets and exact range/confidence strings. TE01E/F implement compact
five-row summary and retained detail. TE01G tests persistence/restoration,
conflicts, integrity and guarded failure behavior. Live target/methodology
commissioning and natural Sponsor/Analyst use are not established by these
milestones.

Only the shared production `browser/product_routes.py` composition seam changes. Its
optional Theta injection preserves existing Intraday injection and route
dispatch. All product behavior belongs in `kronos.theta` and
`browser/theta_routes.py`; shared server/views, Intraday, Swing, Provider,
Instrument, Market, Notifications and research semantics remain unmodified.
One existing Intraday Browser test assertion is aligned with the already
published `Open Analysis Review` label; production Intraday views are unchanged.

## Reuse findings

**FACT:** Intraday Review V2 and Swing rendered-artifact recovery establish the
reused engineering patterns: immutable source/binary artifacts, content hashes,
explicit selected identity, no-clobber publication, atomic presentation pointers,
restart validation and checksum-bound portable Question transport. Intraday
Question/Answer enums, probabilities, readiness, phase policies and trading
semantics were not imported into Theta. Existing local Review Pack and evidence
directory conventions are reused with separate Theta directories.

The inspected public stores are typed to Intraday/Swing analytical lineage and
cannot directly retain a Theta forecast without inheriting unrelated product
semantics. Theta's small file adapter stays in the existing evidence tree and
uses its immutable-artifact/pointer pattern; it creates no database, shared
storage platform, generic persistence refactor or new runtime.

DOMAIN-001's `ACTIVE_DERIVATIVE_FAMILY_MAPPINGS` supplies the existing commodity
labels/canonical subjects. Its futures-only classification and nearest eligible
futures rule are not repurposed as option-expiry mapping authority. The Browser
product seam supplies shared loopback transport, same-origin admission,
maintenance control, navigation and page shell without new platform runtime.

The concrete source boundaries are `instrument/semantic_v2.py` (MCX commodity
and futures classifications), `instrument/active_derivative.py` (minimum eligible
futures selection), and the retained
`MCX-CONTRACT-FAMILY-EXPIRY-SESSIONS-2026.v1.json` publication, explicitly scoped
to segment `MCX_FUTURES`. None supplies the exact option-expiry mapping. CAR-014
is a separate offline futures pilot and grants no Theta option or live Provider
authority; it was inspected, not exercised.

## Qualification procedure

Use the existing complete Python dependency environment and the required
`tools/kronos_test.py` entry point. Direct pytest is deliberately rejected.
The test runner applies an inherited macOS kernel sandbox denying production
stores, credentials, external network and installed application control. It
does not reassign HOME or load ambient provider credentials.

```sh
python tools/kronos_test.py tests/unit/theta tests/unit/browser/test_product_route_isolation.py tests/unit/browser/test_intraday_review_workflow.py -q --theta-qualification-output=/absolute/non-production/theta-te01-qualification
python tools/kronos_test.py tests/unit/theta tests/unit/browser/test_product_route_isolation.py tests/unit/browser/test_intraday_review_workflow.py tests/unit/browser/test_browser_server.py tests/unit/browser/test_browser_views.py tests/unit/instrument/test_active_derivative_selection.py tests/unit/instrument/test_semantic_v2.py -q
```

The continuation order's Section 24 scopes final qualification to actual impact;
a whole-repository run is not an automatic requirement. Earlier broader runs
remain historical evidence, not a claim of a complete or passing final run.

The first command's optional output contains only explicitly synthetic PDF/ZIP
and Browser HTML for visual QA. The source fixtures label every identity,
exchange reference, Analyst and source as synthetic. Test roots are disposable;
explicit QA output and JUnit files are caller-owned and never loaded by default
product composition.

Required evidence includes all five × two forecasts, distinct futures across
E1/E2, lossless original bytes and confidence representation, partial-subject
workflow, restart restoration, identical replay/concurrent import, conflicting
duplicates, malformed numerics, wrong subject/horizon/target/Question/chart,
partial Answers, duplicate JSON keys, future/naive timestamps, supersession,
expiry, tampering/missing dependencies, pointer deletion, symlink rejection,
failed selection/retry, HTML escaping, deterministic PDF/ZIP and separate
inclusive terminal outcomes without original mutation.

## Retained qualification evidence

**RESEARCH_RESULT:** The earlier focused run passed **72 tests in 6.61 seconds**:
Theta workflow/Browser tests plus the existing Browser product-route isolation
and complete Intraday review-workflow fixture suites. The retained report is
`output/theta-te01-focused.xml`. It covers the
positive five-by-two workflow and the negative/restoration cases listed above,
including sanitized owner-resolution failure, calendar-date (not lexical)
expiry ordering and safe identical historical replay after supersession/expiry.
Two targeted tests reproduced both mixed-ISO-date ordering failures before the
bounded fix; both pass without rewriting the supplied date representation.
Question guidance explicitly permits unknown `published_at` to remain null,
matching the existing schema; no historical publication time is invented.
All owner/Analyst/exchange/price fixtures are
explicitly synthetic; there were no real Provider or broker calls.

**RESEARCH_RESULT:** The deterministic synthetic Question PDF has 11 pages.
All eleven final page renders were visually inspected without clipping or
overlap; each E1/E2 target block stays together. Strict PDF parsing, embedded
original images, ZIP manifest checksums, byte-identical transport replay and
invalid-template rejection passed. Static JavaScript syntax checks passed for
all five scripts in the generated summary/detail HTML. Route/content/escaping
tests passed; this is not a claim of rendered Browser interaction.

**FACT:** Browser visual interaction is **NOT_ESTABLISHED**. The browser tool
rejected the local HTML preview under its file-URL security policy. No alternate
server/browser workaround was attempted, and production Browser was not used.

**FACT:** Whole-repository regression is **NOT_ESTABLISHED**. The broad runs
were interrupted; none is a qualification pass. A JUnit-enabled attempt
reported four legacy Intraday rehearsal failures caused by exclusive optional
export filenames being reused (including a repeated helper invocation), not a
Theta assertion. The subsequent no-export run was interrupted before completion
when the final date-ordering fix was made. Unrelated Intraday source is unchanged.
Earlier exports are recoverably separated under `output/interrupted-regression`.

**RESEARCH_RESULT:** Protected dependency regression covering
`tests/unit/browser`, `tests/unit/instrument`, `tests/unit/market` and
`tests/unit/theta` completed with **2,549 passed / 1 failed in 1,446.85 seconds**.
Its retained report is `output/theta-te01-final-dependencies.xml`; it is not an
all-pass report. The sole failure was
`test_opportunity_link_and_missing_current_review_focus_are_inert`, expecting
`Open Native Review` while the verified base's production view already renders
`Open Analysis Review`. `git show HEAD` establishes that mismatch in both
unchanged base files; the exact case reproduced independently before correction.
Only the stale label assertion was corrected, and its complete fixture suite
passes in the final 72-test run. The four nearby provenance-retention tests also
passed independently. The full dependency suite was not repeated after this
fixture correction and Question wording alignment. Source qualification is
scoped; no clean expanded or whole-repository final pass is implied.

**FACT:** Natural Sponsor/external-Analyst round trip, exact owner commissioning,
qualified GitHub publication and production runtime loading are
**NOT_ESTABLISHED**. Predictive usefulness and confidence calibration are
**NOT_ESTABLISHED**; absent authoritative terminal evidence, historical accuracy
is **NOT_EVALUABLE**. No natural future expiry event was manufactured;
prospective expiry outcomes remain **NOT_YET_EXERCISED**. Passing synthetic
mechanics does not establish economic benefit or operational authority.

## Manual acceptance exercise still required

**FACT:** This exercise has not been performed. After the exact owner inputs are
commissioned and the candidate is qualified/loaded through the existing runtime,
the Sponsor uses the existing Theta Browser navigation, not a new service:

1. Supply the five real PNG/JPEG charts with their declared labels and aware
   information cutoffs; retain each selected revision.
2. Generate/download the Question ZIP. Check the five original charts and ten
   independently bound E1/E2 targets, then manually give its PDF, charts and
   Answer template to the Sponsor-selected external Analyst/model.
3. Place the exact returned UTF-8 JSON under the displayed
   `<question_id>_ANSWERS.json` filename in the established Theta Answer inbox;
   explicitly import it. Do not repair its analytical contents.
4. Check all five summary rows and both horizons, then each retained detail:
   exact target, range/confidence strings, external reasoning/sources, original
   chart, T0/cutoff and original Answer bytes/integrity.
5. Restore through the existing runtime and verify retained identities/bytes and
   selected state. A later expiry/outcome requires actual authoritative evidence;
   this workflow creates no live Provider call or natural-event substitute.

## Exact unresolved owner decision

**FACT:** No inspected current governed source establishes the ten next/second-next
option targets with exact exchange-defined futures/settlement references, or an
approved Theta-applicable chart methodology. Default composition therefore has
no authority adapter. Chart capture and explicit unavailable UX work; production
Question generation/forecast acceptance cannot be called operationally complete.

**DECISION REQUIRED:** Commission and supply the exact existing Instrument/Market
owner target evidence and applicable methodology binding for Theta, or retain
the candidate with those capabilities unavailable.

**WHY SOURCE/EVIDENCE CANNOT DECIDE:** Existing futures selection is not option
mapping or settlement identity authority; the external Analyst cannot grant it.
The Drive baseline demands authoritative mappings but does not provide the
exact records or a governed retrieval/commissioning contract.

**OPTION A:** CA commissions a bounded existing-owner adapter consuming approved
target and methodology evidence. It supplies exact E1/E2 option expiries,
expiry endpoints, futures identities and exchange price references, provenance,
validity and applicable methodology. No Provider acquisition is implied.

**OPTION B:** Keep fail-closed target/methodology-unavailable behavior and defer
operational forecast intake. Do not replace missing authority with Sponsor or
Analyst guesses.

**CONSEQUENCES OF A:** Enables final real Question/Answer workflow qualification
once exact records are supplied. New acquisition authority, if genuinely needed,
requires its own instruction and remains outside this candidate.

**CONSEQUENCES OF B:** Preserves chart intake and qualified synthetic mechanics,
but no current production forecast may be accepted or displayed.

**ASTRA RECOMMENDATION — HYPOTHESIS:** Choose A using existing owners, not a new
Theta Provider or Instrument subsystem. Its feasibility remains unverified until
the owner supplies the governed records.

**WORK THAT CAN CONTINUE WITHOUT THE DECISION:** Candidate source, contracts,
Question renderer, manual intake, immutable persistence, summary/detail,
negative/restart tests, protected regression and visual QA. No production
deployment, historical rewrite or fabricated mapping is justified by test success.

## Continuation qualification on 11 October 2026

**FACT:** The continuation supplies Sections 21–44 of the closure order. It
does not supply exact owner target records, an applicable methodology approval
or a decision resolving the dependency above. The previously implemented
production source is unchanged in this continuation. The only new engineering
file is `tests/unit/theta/test_rehearsal.py`; this record is updated as well.

**RESEARCH_RESULT:** Actual-impact qualification passed **253 tests / zero
failures / zero errors / zero skips in 85.66 seconds**. The exact invocation is
the second command above with
`--junitxml=output/theta-te01-continuation-actual-impact.xml` (an absolute path
was supplied to the runner). Results by source ownership are:

| Scope | Passed |
| --- | ---: |
| Theta workflow and Browser projection | 56 |
| Theta production-shaped HTTP and restart rehearsal | 15 |
| Shared Browser server | 99 |
| Shared Browser views | 29 |
| Browser product route isolation | 5 |
| Intraday review workflow | 11 |
| Consumed Instrument active derivative and semantic contracts | 38 |
| Total | 253 |

The report SHA-256 is
`001f7599962fc7f10975e34221f9e778827079e1393c259ac47dca4980fcbe5d`.
The standalone corrected rehearsal also passed 15 tests in 16.83 seconds;
its report is `output/theta-te01-continuation-rehearsal-second.xml`.
The initial harness report is retained as
`output/theta-te01-continuation-rehearsal-first.xml`: one failure, one pass and
13 setup errors. Its causes were a missing fixture import and an assertion
expecting `NO_CHART` instead of the existing `CHART_REQUIRED` state. Both were
corrected in the test only. No production defect or authority change followed.

**RESEARCH_RESULT:** The disposable rehearsal uses the actual
`default_product_browser_routes` → `create_browser_server` composition and
loopback HTTP handlers. It supplies five synthetic charts through the chart
endpoint, generates and verifies the complete immutable ZIP, simulates an
external Answer return to the designated local inbox, imports it, and checks
the ten summary values and five detail bindings against exact original bytes.
The Browser is shut down and its domain owners are closed. Fresh workflow,
store, application and Browser instances reconstruct the selected evidence
from disk without retained Answer state or an owner adapter. Exact replay is
idempotent; changed replay conflicts. Newer orphan/prepared files and altered
mtimes never become selected. Malformed, incomplete, wrong-subject,
wrong-Question and E1/E2-conflicting returns fail closed. Missing or corrupt
selected Answer/Question/receipt/pointer evidence yields no fallback forecast.
Swing and Intraday routes remain separate; foreign-origin intake is rejected.
A forbidden Provider factory records zero invocations. This is Browser-instance
restart, not installed-launcher or production-process acceptance.

**RESEARCH_RESULT:** All 13 changed Python files parse successfully. Diff checks
pass. The six Theta production modules have no outbound-network, Provider,
OpenAI or execution imports; `http.HTTPStatus` and `urllib.parse` are local
status/encoding utilities, not Provider capabilities. Literal private-key and
provider-secret scans of the changed files find no matches; no temporary
checkout path is a production dependency. Protected server/views, Provider,
Instrument, Market, Swing, Intraday, common and application source have no diff
against the base. Prior visual PDF/ZIP evidence still applies to the unchanged
Question renderer and contract source. Rendered interactive Browser UX remains
NOT_ESTABLISHED; HTTP and deterministic HTML qualification are established.

**FACT:** The remote `develop` SHA was verified again as
`37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3`. No candidate commit, branch,
push, deployment, production load or owner acceptance is implied. A retained
source snapshot may identify the candidate bytes, but it is not a final-candidate
freeze under Section 23. Full V1 convergence remains blocked at the exact owner
decision, not at an ordinary engineering milestone. The Drive living record
remains unchanged; final closure reconciliation must not claim operational
commissioning before the missing authority is established.

## Acceptance mapping for the retained candidate

**RESEARCH_RESULT:** The mapping below applies to synthetic engineering
mechanics only. It does not commission production identities or research truth.

| Criteria | Implementation and qualification |
| --- | --- |
| AC-01 to AC-03 | Chart intake, deterministic Question PDF/ZIP, exact chart/subject and E1/E2 binding; positive HTTP rehearsal and owning tests. Real target/methodology inputs remain unavailable. |
| AC-04 to AC-09 | Exact designated-path JSON intake, strict schema/identity/numeric checks, raw bytes and immutable receipt; HTTP negatives, conflict/replay and owning tests. |
| AC-10 to AC-12 | Five-row summary and retained details share accepted Answer hashes; owning HTML tests and ten-result/five-detail HTTP checks. Rendered interactive UX is not established. |
| AC-13 | Fresh store/workflow/application/Browser construction restores selected disk evidence after clean server/domain shutdown; no mtime or orphan fallback. Installed runtime restart is not claimed. |
| AC-14 and AC-15 | Malformed/incomplete/wrong-bound/conflicting input and damaged retention fail closed; superseded/expired history stays immutable and cannot be reselected by replay. |
| AC-16 and SA-01 to SA-09 | No Provider/broker/trading path, confidence reinterpretation, strike selection, invalid repair or historical rewriting; import/source checks and synthetic invariants. |
| SA-10 | Shared Browser/Intraday/consumed Instrument regression and Swing/Intraday HTTP route isolation pass. Independent owner acceptance remains distinct. |
| SA-11 and SA-12 | Production defaults use established user evidence/Review Pack locations, not worktree paths. Synthetic evidence remains in denied-production disposable test roots or explicit QA output. |

**FACT:** No shared migrations are introduced. Theta's versioned artifacts
are separate from existing Swing/Intraday records. The later TE-01 chart intake
slice preserves read compatibility with earlier selected Theta chart records
without inventing their historical intake metadata.
Publication/runtime acceptance and final actual-impact owner review remain
unperformed. Forecast and confidence calibration and E1/E2 predictive quality
are NOT_YET_ESTABLISHED; option-selling expectancy is NOT_ESTABLISHED. These
future research outcomes do not constitute the engineering governance hold.

## Swing and Intraday coordination on 11 October 2026

**OPERATIONAL_AUTHORITY:** Sponsor Sections 43B–43F require bounded concurrency
coordination before further shared edits. They do not commission another product
to redesign Theta or create a final approval gate when its owned behavior is
unchanged. EA-Theta remains responsible for Theta. The findings below supersede
any implication that an unchanged Swing or Intraday scope needs its final review.

**FACT:** Both actual EA contexts were contacted: `Kronos EA Swing V8` and
`K EA Intraday V7`. Their six-question requests identified the shared composition
path, the unchanged Intraday owner/order, the optional Theta registration and
the test-only label correction. The requests and full responses are retained in
`output/theta-te01-concurrency-43b/coordination-request.json`,
`ea-dispositions.json` and `ea-intraday-initial.json`. Intraday's initial
shared-filename-based final-review requirement was explicitly corrected; the
clarification, not the superseded requirement, is the current disposition.

**FACT:** The first implementation and earlier test-label correction preceded
this new coordination order. That Stage-1 chronology cannot be retroactively
satisfied. Both assessments were obtained before the further shared repair
below. Full engineering convergence has not occurred, so the full-candidate
Stage-2 checkpoint remains unperformed. No freeze or delay was requested from
either programme.

| Coordination field | EA Swing | EA Intraday |
| --- | --- | --- |
| Contacted | YES | YES |
| Actual shared surface | `browser/product_routes.py` additive composition and optional failure isolation | Same shared composition; existing `test_intraday_review_workflow.py` label assertion only |
| Concurrent conflict found | NO identified in consulted records and bounded local checks | NO established in consulted records and bounded local checks |
| Programme status reported by EA | Engineering closed; methodology frozen; no active competing edit identified | Features and UX frozen at `37c9dc94`; IWO-06–08 closure sequence continues independently |
| Resolution or reuse | Existing routing/security/maintenance and immutable evidence patterns; Theta-local adapter | Same mechanics without Intraday analytical lineage, policies or persistence schemas |
| Owned behavior changed in current candidate | NO | NO |
| Final product EA review required for retained scope | NO | NO |

**FACT:** Neither EA independently inspected the local candidate's source bytes.
Their statements are coordination assessments, not release acceptance. Local
checks cover three registered worktrees in the two known repositories: the root
publication checkout, Theta candidate and Intraday reconciliation checkout. Only
the Theta candidate has working changes at the two coordinated paths. This is
not a global guarantee that no other editor or unregistered checkout exists.

**FACT:** Ownership is established from the source delta, not a passing test
count. The only shared production change is optional Theta registration in
`browser/product_routes.py`, after the unchanged Intraday construction/order.
Protected server/views, Swing, Intraday, application, Provider, Instrument,
Market and common source remain identical to the candidate base. The existing
Intraday fixture changes only its expected label to the unchanged published
`Open Analysis Review`. No analytical, lifecycle, Question/Answer, construction,
readiness, risk, timing or broker authority changes. Product ownership remains
with its existing owners; shared composition is not classified as product-owned
behavior merely because it occupies a shared filename.

**RESEARCH_RESULT:** The requested failure-isolation probe exposed a real defect:
an optional Theta import or constructor exception aborted the product registry.
The retained pre-repair report has **5 failures / 11 passes**. The bounded repair
preserves the existing registry when optional Theta construction fails and
registers no Theta mutation route. Intraday construction remains outside that
guard, so its own failures are not masked. No existing product source was
otherwise changed.

**RESEARCH_RESULT:** All **17** new Theta-local isolation cases pass in the
standalone run. They cover import/constructor/invalid-adapter failure, None and
malformed injection, existing GET/POST precedence, nine protected path-ownership
checks, and real loopback HTTP responses for Swing opportunities, review, MCX,
Portfolio, Reports, Journal, Notifications and Intraday with Theta absent/present.
The disposable application has no calendar authority: the unchanged Reports
handler returns its exact 400 response even for the valid explicit query.
Controlled legacy 409/503 responses also retain missing-evidence semantics;
these tests do not manufacture authority or certify populated Swing features.

**RESEARCH_RESULT:** The repaired current source passes **321 tests / zero
failures / zero errors / zero skips in 106.25 seconds** through
`tools/kronos_test.py`. This is the earlier 253-case selection plus 17 composition
isolation cases and 51 frozen Intraday Browser/UX cases. It covers:

| Scope | Passed |
| --- | ---: |
| Theta workflow, Browser, HTTP restart and new composition isolation | 88 |
| Shared Browser server, views and route isolation | 133 |
| Intraday review workflow and frozen Browser/UX | 62 |
| Consumed Instrument active derivative and semantic contracts | 38 |
| Total | 321 |

The passing report is
`output/theta-te01-concurrency-43b/actual-impact-qualified.xml`, SHA-256
`0e9bd988e5454085e0d16b6cc99770e8aebe750140e81bbe6168d5a862473bac`.
The standalone 17-case report is `isolation-qualified.xml`. Earlier failed
iterations remain retained, including `actual-impact-final.xml` (**320 passes /
1 harness failure**, not a passing final qualification). The harness initially
rejected legitimate legacy unavailable responses; its final correction asserts
the exact Reports missing-calendar response rather than weakening product
source or granting invented calendar authority. All 14 changed Python files
parse; diff checks, protected-source comparison, production import-boundary and
literal secret scans pass. No secret values were read or printed.

**FACT:** The preceding 15-file snapshot and 253-test report remain historical
pre-repair evidence. The current checkpoint has 16 changed source/document/test
files, including the new Theta-local isolation test, and a separately retained
manifest. It is not a final-candidate freeze. No commit, push, deployment,
production load, Provider acquisition or trading action occurred. The existing
target/methodology owner decision is unchanged; no Swing or Intraday approval
hold is added. Full Stage-2 comparison follows actual engineering convergence,
and a product EA review becomes necessary only if its owned behavior changes.

## TE 01 Swing style chart intake

**OPERATIONAL_AUTHORITY:** The Sponsor's later TE-01 order opens only the
composite chart-intake slice in the retained isolated candidate. TE-02 Question
Pack work is not started. Production on 8947, its checkout and stores, shared
Swing/Intraday behavior, Provider and broker operations remain outside scope.

The generic global upload form is replaced by five commodity cards and one
shared GLOBAL_MACRO card. Every card has a focusable Cmd+V/Ctrl+V paste target,
PNG/JPEG Choose File fallback, exact-original preview, missing/ready state,
accepted identity/integrity details and explicit Replace Chart action. The five
commodity cards retain reference/MCX 1D, 4H and 1H guidance. Macro lists its eight
supporting panels but creates no sixth forecast subject or Question-blocking
rule. The displayed Question counts mean actual selected current packs, not
assumed generation eligibility.

**FACT:** The reuse investigation inspected current Swing
`browser/views.py::_chart_upload_script`, native card rendering,
`application/swing_native_review.py::upload_chart/active_chart`,
`swing/v1/evidence_store.py::retain_native_upload`, and the native Browser
clipboard/serial-intake tests. The reused patterns are focus-local role binding,
raw original file intake, serialized requests, pending/duplicate feedback,
file fallback through the same path, retained original previews and immutable
revision lineage. A Theta-local adapter preserves the narrower existing PNG/JPEG
and 16 MiB boundary. It imports no Swing analysis, enum, requirement, Question,
readiness, lifecycle or persistence schema. Swing's broader WEBP/25 MiB action
and analytical validation are not repurposed.

Only two existing Theta production files change for this slice:
`browser/theta_routes.py` and `theta/workflow.py`. The new
`browser/theta_charts.py` holds Theta-local controls/script/styles; the new
`tests/unit/theta/test_chart_intake.py` qualifies the slice. This interface and
engineering record are updated. The previously coordinated shared composition
seam and Intraday test-label correction are unchanged in this slice. No new
actual shared behavior impact requires another EA coordination request.

The first focused run retained **139 passes and one test-fixture failure** in
`output/theta-te01-chart-intake/theta-first.xml`. The legacy COPPER fixture used
the display label rather than the existing canonical subject. Its correction
does not change product mappings. Four further cases cover current replay,
corrupt-revision replacement rejection, pre-decode pixel bounds and overlapping
bound replacements.

**RESEARCH_RESULT:** Final actual-impact qualification passed **380 tests / zero
failures / zero errors / zero skips in 114.07 seconds** through the protected
`tools/kronos_test.py` runner. The retained report is
`output/theta-te01-chart-intake/actual-impact-qualified.xml`. The selection is
the preceding 321-case actual-impact suite plus 56 new chart-intake cases and
three existing Swing clipboard/serial-card checks. Source ownership totals are
Theta 144, shared Browser 133, Intraday 62, Instrument 38 and Swing reuse 3.

The new cases qualify all six role bindings, PNG/JPEG exact-byte previews,
acceptance identity/time/SHA, role-local replacement and original/history
retention, stale cycle/revision rejection, file fallback, focused clipboard
handlers and serial pending/error behavior, invalid images/types/sizes, pixel
bounds, restart restoration, legacy record compatibility, no mtime/orphan
fallback, existing five-subject Question binding, Macro nonblocking behavior,
selected corruption rejection and overlapping replacements. The real shared
HTTP handler rejects foreign-origin uploads. A forbidden Provider factory
records zero calls in the disposable HTTP qualification. These results are
automated mechanics, not a Sponsor's natural clipboard acceptance or production
runtime commissioning.

The six-file slice manifest and full 18-file retained candidate snapshot are
`output/theta-te01-chart-intake/source-checkpoint-manifest.json`. The earlier
16-file snapshot and reports remain untouched as historical evidence. No commit,
branch, push, publication or production load is made by this slice.

**FACT:** Chart receipt time is not independently verified TradingView time or
market evidence. No OCR or chart interpretation occurs. MACRO inclusion/blocking
policy and cycle rollover remain TE-02 owner work, not an implicit TE-01 rule.
Synthetic automated qualification does not establish Sponsor's natural
TradingView clipboard acceptance, production commissioning or forecast quality.

## TE 01A Sponsor navigation and view separation

**OPERATIONAL_AUTHORITY:** Sponsor TE-01A authorizes one isolated navigation and
presentation slice. OUTLOOK is the default at `/theta-earners`; NEW ANALYSIS is
secondary at `/theta-earners/new-analysis`. TE-02 remains not started. No
production mutation, publication, Provider operation or trading is authorized.

OUTLOOK shows only current accepted forecast values, with range/confidence
visually primary, expiry date secondary and compact local analysis time/status.
Exact original aware times remain in HTML time metadata and retained evidence.
The empty state is one NO CURRENT THETA ANALYSIS AVAILABLE message and START NEW
ANALYSIS link. Partial accepted selections do not reintroduce a superseded
commodity forecast. Detail retains its analytical content and gains BACK TO
OUTLOOK navigation.

NEW ANALYSIS retains all six TE-01 chart roles, counts, original previews,
Replace Chart and existing Question/Answer controls. Normal pages no longer
render outbox/inbox or temporary paths, and long workflow prose is removed.
The existing Browser tab styles are reused through Theta-local composition;
shared server/views, Swing and Intraday remain unchanged.

**FACT:** The qualified card-renderer source and paste-script bytes are unchanged.
Their SHA-256 identities are respectively
`c11653ac3fbe21e8998162956dc9e3fc4f73d0611db39f2e19754924b1cc2a71` and
`140bf11966235bf650b56329132464aa7b8fb755d80ec3113fb8a9d954379e2a`.
Theta workflow, store, contracts and Question transport remain byte-identical to
the preceding qualified snapshot. Tests move their page assertions to NEW
ANALYSIS without weakening chart-domain checks. The refresh link changes only
its presentation destination, not upload behavior.

The Sponsor-frozen subsequent transport destinations are recorded in the
interface contract: outbound
`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`
and inbound
`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/CHATGPT ANSWERS`.
No production path switch occurs. The inspection runtime continues using an
explicit disposable store/inbox/outbox. Its synthetic fixture is labelled by a
compact banner across OUTLOOK, NEW ANALYSIS and detail; it is not real market or
Analyst evidence. Earlier sandbox evidence remains retained separately.

**RESEARCH_RESULT:** The first protected Theta run passed **157 tests / zero
failures / zero errors / zero skips in 31.04 seconds**. The report is
`output/theta-te01a-view-separation/theta-first.xml`. Thirteen added cases cover
view selection, clean empty state, five exact synthetic E1/E2 forecasts, local
timestamp/exact metadata, partial/noncurrent/corrupt states, detail/return links,
path exclusion, observational navigation, guarded route ownership and immutable
card/script/storage source. Final affected regression and runtime evidence are
retained in the same directory after qualification.

**RESEARCH_RESULT:** Final actual-impact qualification passed **393 tests / zero
failures / zero errors / zero skips in 115.48 seconds**. The retained report is
`output/theta-te01a-view-separation/actual-impact-qualified.xml`. This is the
preceding 380-case selection plus 13 navigation/presentation cases: Theta 157,
shared Browser 133, Intraday 62, Instrument 38 and Swing reuse 3. All prior
56-case chart-intake qualification and existing Swing clipboard/serial-card
checks remain passing. Card/paste-script/storage source identity checks pass.

The exact eight-file slice and full 19-file candidate are retained in
`output/theta-te01a-view-separation/source-checkpoint-manifest.json`; the
preceding TE-01 source snapshot remains unchanged as historical evidence.
The inspection runtime on 8948 is disposable, with synthetic accepted five-by-two
forecasts, no commissioned owner adapter, zero Provider calls and chart-only
mutation admission. Question/Answer mutations remain blocked in that preview.
Source qualification is not Sponsor visual acceptance or production loading.
