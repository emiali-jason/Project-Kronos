# Swing post-closure improvements — 12 October 2026

Status: Sponsor-authorized isolated engineering candidate; exact-byte reviews
and release remain separate gates. This record does not reopen Swing methodology.

Authority: KRONOS-SWING-OPS-IMPROVEMENTS-20261012, Slice 1, and
INTERIM-WO-SWING-UX-01. The historical interim record remains unchanged; the
Sponsor's later programme order supplies this bounded implementation authority.

## Baseline and ownership

The clean published and loaded base is
`d44b191289da3e6c05b034310267f04fdd084a2f`. It retains the accepted final Swing
release and subsequent canonical runtime/Intraday changes, including the three
12 October Intraday commits. Their shared Browser/Provider/monitoring changes
are inherited, not replaced by older files.

This candidate modifies only the Swing `_native_opportunity_card` presentation
and its presentation CSS in the shared Browser views file. The narrow action
wrapping rule is contained by the existing Swing-only `.swing-card-list` ancestor. The
existing exact run/instrument/assessment matchers, type guards, contradictory
V2 checks, Review action availability, trade-window links and owning projections
remain unchanged. Browser and EA-Intraday exact-byte review are required for
this shared-file change. Historical approvals do not transfer.

## Slice 1 presentation

The first view shows instrument/direction, current display stage, Discovery
status, currentness, the existing governed Review/KR-370/V2 status, outstanding
conditions from the existing bound explanation (or explicit retained reasons
where numeric explanation is unavailable), and compact Chart/Question Pack/
Answer states. Stage is navigation, not a newly calculated lifecycle outcome.

The native collapsed `details` element labelled **WHY BLOCKED / ANALYSIS
DETAILS** retains methodology, phase, observation boundary, timeframe evidence,
original result, K1–K5/confirmation detail, watch/progression detail and existing
provenance/navigation. Root/continuity warnings, unavailable/error states and
MCX production holds remain visible. All existing detailed analysis links remain.

The change creates no new card population: only current PROBABLE cards are
rendered by the existing opportunity page. FORMING/WATCH, NO_CURRENT_OPPORTUNITY
and UNAVAILABLE continue through the existing counts/empty-state presentation.
It introduces no checked lifecycle stages or new READY/admission authority.

## Qualification and acceptance boundaries

Owning regressions cover NSE and all five MCX families separately, both
directions, incomplete and accepted/stale/rejected intake, unavailable criteria,
contradictory confirmation, actual typed V2 outcomes, stale run/assessment input,
unchanged Discovery population, visible governed numeric facts, long identifiers
and collapsed accessible disclosure. Affected existing suites cover Browser,
Swing, MCX, Review/publication, Portfolio/Reports and current Intraday changes.
All tests use `tools/kronos_test.py` and production-store/network denial.

Offline 1440×900 and 390×844 rendering uses a labelled fixture with JavaScript
disabled, network interception and kernel TCP denial. Native keyboard disclosure,
horizontal bounds and screenshots qualify engineering layout only; they do not
establish genuine deployed visual acceptance. Initial fixture and renderer
failures remain historical evidence outside the source candidate.

Exact invocations, logs, JUnits, source continuity, manifests, reconstruction,
screenshots and review dispositions are in the extraction-verified packet.
No full regression is represented as passed by this record. The combined
programme regression decision is retained after all implemented slices and
applicable impact review; previous full-run results do not qualify changed bytes.

## Sequential gates and deferred work

Slice 2 measurement must not begin until Slice 1's owning/affected qualification
and applicable exact-byte review gates pass. It must remain diagnostic, retain
UNKNOWN for unobservable model/visual phases and change no Analyst instruction,
pack, Answer schema or decision. Instrumentation alone proves no speedup.

Slice 3 optimization remains gated by genuine measured evidence. No parallel
assessment or new Analyst architecture is implemented here. The original
13-minute operation is not rerun for timing. Daily constituent rejection
observability remains deferred. WO-12 operational/import/UPDATE evidence,
MCX certification, current V2 attribution and Intraday work are separate.

The Answer provenance investigation is separate: extracted host Answer data
serialized in the original recorded working format matches the Analyst's
working-JSON hash. PDF size/hash transformation attribution remains unresolved;
this is not a claim of PDF byte equivalence or a new intake authority.

No publication, build, installation, runtime load, Provider operation, market
acquisition, Review submission, research UPDATE, position/admission or broker
operation is authorized by this candidate. Release and genuine acceptance
require separate Sponsor authorization.


## Slice 1 R2 — bounded successor, 13 October 2026

Status: isolated successor for renewed exact-byte review; not deployed.
The rejected predecessor packet and PCP PASS / EA-Intraday CHANGES REQUIRED
remain historical evidence against their original identities.

R2 corrects only the two reviewed presentation findings. Fallback Pending
requirements includes retained confirmation reasons only for the existing
projector's PENDING or UNAVAILABLE states. The owner maps governed WITHHELD
to those labels; ESTABLISHED and asset-class exemption are not blockers.
Affirmative reasons remain unchanged in governed details. No confirmation
calculation, enum, criterion, evidence, currentness or readiness rule changes.

The new narrow action wrapping rule is scoped through `.swing-card-list`.
Intraday's shared classes and existing styles are unchanged. Qualification
compares computed styles against the authoritative base at desktop and narrow
widths using the actual legacy Intraday card producer, plus a shared-class
non-Swing surface, and checks Swing wrapping, native keyboard/focus/disclosure,
long identifiers and unavailable evidence. These are isolated engineering
fixtures and establish no genuine production visual acceptance.

Owning tests reproduce affirmative NSE/MCX confirmation inversion before the
fix, retain non-established/unavailable confirmation blockers and asset-class
exemption, and preserve all five MCX production holds. Renewed Browser and
EA-Intraday reviews bind only to the frozen R2 successor. Slice 2 remains gated
by both reviews; Reports UX is excluded. A fresh scope-based regression
decision follows qualification/reviews; no full-run result is implied here.


## Final S1 + S2 + S4 composition / source authority — 13 October 2026

Status: Sponsor-authorized composition/authority engineering; exact-byte final
reviews, regression-impact decision and release authorization remain separate.
The frozen S1/S2/S4 packets are preserved. This appendix is an explicitly
authorized composition reconciliation, not a rewrite of those checkpoints.

The canonical shared base is d44b191289da3e6c05b034310267f04fdd084a2f.
S1/S4 views.py changes compose independently; S2's three original file bytes
remain exact and it remains a disabled-by-default, explicitly invoked external
measurement sidecar. No runtime, startup, Browser, Provider or automatic Analyst
hook is added. The complete candidate is ten paths: eight slice paths after
the views.py overlap, plus the exact-path verifier correction and owning tests.

ResearchReleaseVerifier attests the declared complete published release delta:
clean requested/startup-loaded Git HEAD, original manifest bytes/hash, one
commit trailer, exact base-to-release path set and committed/on-disk equality,
then final identity recheck. Separate S2 checksum evidence cannot remove its
changed path from that same committed release. Its original roots allowance
intentionally permits src/tests/docs and only tools/kronos_browser.py.
PCP's early source-grounded disposition requires the smallest formal exact-path
extension: tools/swing_chart_analyst_measurement.py only. Every other unlisted
tools path still rejects; traversal, noncanonical, absolute, symlink, changed
byte/scope/trailer/hash and loaded-revision guards remain unchanged.

This extension grants source attestation, not execution or research capture
authority. S2 retains a separate exact three-file external-tool manifest and
requires future explicit authorized invocation. It is not a required production
dependency. No arbitrary tool command gains authority from checksum validation.
No Question/Answer contract, method, comparison or timing semantics change.

The last Swing cumulative manifest (72 paths,
2dec304cb41f600433c690672fc27a45a5cb0052fe10908cbe153dd90dfd5a34)
is valid at c777c68296f00e304e58149053608415c7b99af7 only. Current d44 is
17 separately published shared-runtime/Intraday commits later; eight original
rows differ and its full original-7fad delta is243 paths, including three
other tools excluded by WO12. Do not relabel that old manifest as current.
Use the freshly verified published d44 as the final direct base; bind the exact
ten-path successor delta with one new WO12-Source-Manifest-SHA256 trailer.
The complete all-file composition manifest and retained base/history map
supply cumulative provenance without granting old operational tools a new
exception. The original commissioning receipt, active pointer and research
history remain unchanged; they do not attest the successor and are not rebound
or automatically recommissioned. Existing commission conflict/empty-store
guards remain exact. Future release verifies successor source independently.

Preserve the artifact-provenance limitation: Analyst-returned PDF45142 bytes
(8293231b4eeec77c79b28c8e43032f79956a7badbc357e8053195f8497efd104)
and host-accepted PDF70111 bytes
(7a23a26b16d431019964ae550151b568f6fc7787c5ecb0675c7b8a5c00f0ad9e)
share an Answer identity. Extracted host data matches working JSON
b87ea0211b55aba1106361a3a48d69bddf3cd0d38442e92518fd7eff1fc78313.
No content alteration is demonstrated, PDF byte equivalence is unestablished,
and the transformation boundary is unresolved. Measurement does not depend on
assuming equivalence; future genuine acceptance must retain actual byte hashes.

Final owning/affected checks and fresh PCP source-authority/Browser and
EA-Intraday shared-impact reviews must bind the actual final packet. No full
protected regression is authorized by this composition order. If impact
requires one, prepare its single-run order and wait for Sponsor authorization.
No publication/build/install/load or genuine visual acceptance is completed.
Slice3 remains DEFERRED — GENUINE MEASURED EXECUTION REQUIRED; its only trigger
is a naturally reached, separately authorized genuine Analyst execution with
S2 available, without changing the workflow for timing. Unknown phases remain
UNKNOWN. Operational attribution, official NSE import/UPDATE, MCX22-item live
certification and genuine PAPER/LIVE/broker evidence remain separate.
