# Theta TE-02 Astra-Ultra Question Pack candidate

**Status:** QUALIFIED isolated engineering candidate, 2026-10-11. Synthetic
Sponsor inspection only. No source publication, production deployment or runtime
acceptance is granted or performed. TE-03 is not started.

TE-02 supplies five independent portable commodity Questions and a convenience
combined transport, with exact original charts, fixed commissioning T0 and a
deep external research mandate. Genuine forecasting remains fail-closed because
authoritative E1/E2 and applicable methodology are not commissioned.

## Authority and boundary

The Sponsor's TE-02 order, including supplied sections 36–55, authorizes this
slice. The subsequent explicit “AUTHORIZE OPTION 1” instruction authorizes the
narrow version-aware temporal correction recorded in
[ADR-0066](../architecture/adr/ADR-0066-THETA-PROSPECTIVE-INFORMATION-SET-AND-RETRIEVAL-TIMES.md).
The [Theta interface](../architecture/interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md)
retains historical V1 and records the prospective successor separately.

No Astra API, Provider acquisition, broker action, trading rule, strategy/strike
recommendation, new target authority, Answer UX redesign, TE-03 or later slice is
implemented. No Git commit/push, production source publication, launcher deployment
or production store change occurred.

## Question and transport behavior

Each of GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS has a separate canonical
Question, template and PDF/ZIP. Each Question binds its exact analysis cycle,
commodity chart revision/SHA, shared Macro revision/SHA, exact E1/E2 target
dictionaries, methodology and Answer schema version. Macro supports the five
commodities; it is not a sixth forecast subject.

Prospective Question/Answer versions are `2.0.0` under retained schema identities.
T0 is frozen at commissioning. Each source has separate publication, supported
availability and actual retrieval times; pre-T0 information retrieved later is
allowed. First publication or availability after T0 is rejected. Historical
`1.0.0` behavior, original raw Answers, receipts and templates remain unchanged.
Only prospective temporal detail labels are corrected; no later Answer UX is added.

The mandate covers visible T1–T8 chart evidence, independent extensive global
research, commodity-specific fundamentals, events through each expiry,
bull/bear/base cases, counterevidence, chart/research reconciliation, source
discipline, independent E1/E2, useful interval sharpness and honest terminal
containment confidence. Copper receives the specified deeper investigation.
Intraperiod path risk is distinct from terminal containment and no-touch claims.
Research depth takes precedence over response speed. Sponsor manually takes the
pack to Astra-Ultra and manually returns the exact Answer.

Individual ZIPs contain PDF, canonical JSON, exact commodity/Macro originals,
governed blank template, instructions and checksum manifest. Combined ZIP stores
Macro once and preserves each canonical Question/template identity. An isolated
commodity failure yields explicit BLOCKED status and PARTIAL transport rather
than a complete cycle. Exact-input regeneration reuses the original T0/binaries;
revised charts, targets or methodology create new identities without historical
rewrite. Filename authority is deterministic, not directory order or mtime.

NEW ANALYSIS offers CREATE THETA QUESTION PACK, per-commodity status, QUESTION
PACK READY/PARTIAL and direct pack/PDF/template actions. OUTLOOK remains the default
reading view. The qualified intake script and card behavior are preserved. The
only card-text change replaces the stale TE-01 “no new Question gate” Macro
caption with the TE-02 required-input wording. The card hash test normalizes only
that explicit caption before checking the retained full-function hash; the script
and historical transport retain their exact prior SHA-256.

## Qualification evidence

The final actual-impact command ran through `tools/kronos_test.py`, with inherited
kernel denial of production evidence/Review Pack, external network and sensitive
process actions. It qualified the full Theta suite, Browser product isolation,
Browser server/views, protected Intraday paths, retained Swing chart paste/intake,
and Instrument identity/active-derivative paths:

```text
tests/unit/theta
tests/unit/browser/test_product_route_isolation.py
tests/unit/browser/test_intraday_review_workflow.py
tests/unit/browser/test_browser_server.py
tests/unit/browser/test_browser_views.py
tests/unit/browser/test_intraday_iwo_ux.py
tests/unit/browser/test_intraday_wo08_browser.py
tests/unit/instrument/test_active_derivative_selection.py
tests/unit/instrument/test_semantic_v2.py
tests/unit/browser/test_browser_native_review.py::test_swing_chart_paste_javascript_bounds_duplicate_and_failed_intake
tests/unit/browser/test_browser_native_review.py::test_swing_chart_paste_serializes_eight_targets_and_reports_each_result
tests/unit/browser/test_swing_review_intake_binding.py::test_eight_generated_review_cards_accept_serial_chart_posts_and_rerender
```

**Final result:** 428 passed, 0 failures, 0 errors, 0 skipped, 142.71 seconds.
The suite includes 35 new TE-02 cases. Artifact emission separately passed 1 test
in 2.32 seconds. Final JUnit:
`output/theta-te02-question-pack/actual-impact-closure.xml`.

| Required proof | Retained evidence |
| --- | --- |
| Correct commodity and shared Macro; not sixth forecast | Independent bindings and combined manifest tests |
| Exact cycle, revisions and original hashes | Independent Question and foreign-binding failure tests |
| Independent E1/E2 and genuine-authority absence | Exact two-slot templates; mandatory-input/default-owner fail-closed tests |
| Clearly synthetic targets | Explicit qualification mode; nonqualification rejects synthetic authority |
| Missing/corrupt/foreign chart fails closed | Per-commodity failure parameterization; mandatory Macro tests |
| Changed chart/Macro/targets/methodology | New identity/readiness tests, original bytes preserved |
| Historical Question and Answer unchanged | Immutable replay, restart and legacy temporal compatibility tests |
| PDF instructions and exact readable charts | Mandate/layout/determinism tests plus 30 rendered pages |
| Individual isolation and combined identities | Four-of-five PARTIAL tests and one shared Macro copy |
| Governed template and integrity manifests | Template pairing, populated validation, blank rejection, archive SHA validation |
| Deterministic/no-clobber/safe outbound | Reuse, conflict preflight, symlink rejection, frozen default-path and readback tests |
| No Astra/Provider/broker actions | Forbidden Provider fixture, protected tests and live preview counter = 0 |
| TE-01/TE-01A, OUTLOOK, Swing, Intraday | Retained regression paths and no protected source changes |
| Production 8947 untouched | Same PID 95115/listener before and after; preview kernel denies production paths/port |

`git diff --check` passed. No modifications exist in shared Browser server/views,
application, Provider, Swing, Intraday or Instrument implementation relative to
candidate HEAD. The retained product-route composition hash remains unchanged
from TE-01A; existing unrelated/staged candidate changes are preserved.

## PDF visual inspection

All five final PDFs are six pages: one A4 identity/target page, two landscape A3
full-original chart pages, and three A4 research/Answer-instruction pages. All
30 pages were rendered at 120 dpi with bundled Poppler and visually inspected.
Full-size chart, Macro and Answer pages were inspected alongside each commodity
contact sheet. An orphaned commodity heading found during the first inspection
was corrected and the final set rerendered.

The original embedded images remain 2400×1440 pixels and decoded pixel hashes
match the originals exactly. Transport image bytes preserve their original
SHA-256. Aspect ratio is preserved, with no crop, stretch, redraw, annotation or
panel split. Text-bounds checks found no out-of-page words. No clipping, overlap,
unreadable chart labels or internal absolute/temp paths remain in the inspected
set. The PDF skill supplied this render-and-inspect qualification; the write-page
skill guided the bounded local governance/engineering documentation.

Structural report: `output/theta-te02-question-pack/pdf-structural-qa.json`.
Synthetic final artifacts:
`output/pdf/theta-te02-synthetic-v2/theta-te01-qualification/`.
Earlier synthetic drafts remain separate, not silently overwritten or selected.

## Frozen outbound and Sponsor artifacts

The intended outbound remains:
`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`.

The candidate's normal writer uses retained no-follow descriptors, conflict
preflight, atomic/no-clobber individual files and readback verification. Tests and
the running preview use disposable outboxes. A separately bounded, one-time
static publisher placed exactly 16 new visibly SYNTHETIC inspection copies in the
frozen Sponsor outbox: five PDFs, five individual ZIPs, five templates and one
combined ZIP. It blocked network, credentials, production stores and all other
home-directory writes, and preflighted all names before copying. No existing
file was overwritten. SHA-256 readback matched all 16 originals.

Readback evidence: `output/theta-te02-question-pack/sponsor-outbound-readback.json`.
Those files belong to the retained synthetic qualification cycle. The live preview
has its own disposable synthetic cycle; the identities are not conflated.
The future CHATGPT ANSWERS path is instructions only; no new Answer intake
semantics or production inbound configuration is activated.

The representative GOLDM PDF and combined transport were requested in Codex's
file panel; the tool returned queued. Actual files and direct handoff links are
available regardless of panel visibility. A separate Chrome PDF tab has the
correct document title/URL, but automated PDF-viewer capture was blank; PDF visual
qualification relies on the completed Poppler renders, not that capture.

## Running isolated sandbox

- OUTLOOK: `http://127.0.0.1:8948/theta-earners`
- NEW ANALYSIS: `http://127.0.0.1:8948/theta-earners/new-analysis`
- PID: **8233**, retained for Sponsor visual inspection.
- Disposable root:
  `/private/var/folders/t6/y8wycddx2tv3swhcw_ccqjcw0000gn/T/kronos-test-theta-te02-preview.KrsPuT6bPZ`.
- Provider calls: **0**. Accepted Answers: **0**.
- Six synthetic composites, five current independent Questions, one complete
  convenience batch. No genuine ranges are presented in OUTLOOK.

The preview inherits kernel denial of production stores, credentials and network
except its 8948 loopback. Its application factory refuses Provider operations.
Only existing bounded chart/Question POSTs are admitted; Answer import and other
mutations are blocked. Shared Host/Origin and maintenance admission are preserved.
No scheduler, collector, lifecycle acquisition or notification loop runs.

The exact old disposable preview processes were stopped for this refresh; their
temporary stores are retained. Production PID **95115** on 8947 was not stopped,
restarted, queried for market data or modified.

Final HTTP smoke: `output/theta-te02-question-pack/preview-http-smoke.json`.
It verified six originals, five inline PDFs/templates, combined manifest,
independent identities, one shared Macro, empty unchanged OUTLOOK, foreign Origin
403, blocked mutations 405 and Provider count 0. Chrome's actual CREATE action
returned five READY states and reused the same batch identity/T0. Proof screenshot:
`output/theta-te02-question-pack/sponsor-new-analysis.png`.

## Remaining limitations and next boundary

Genuine exact E1/E2 option expiries, underlying/settlement identity and approving
methodology remain NOT_ESTABLISHED. Synthetic dates, charts and templates are
not genuine forecast authority, usefulness or calibration evidence. Analyst
source truth/authorship and actual pre-T0 availability are not independently
verified by KRONOS. Blank templates are structurally governed but deliberately
invalid as completed Answers. NOT_EVALUABLE machine Answer UX is not added.

Source checkpoint and actual changed-file manifest:
`output/theta-te02-question-pack/source-checkpoint-manifest.json`.
This records exact candidate bytes, not a Git commit or production release.

**Next:** TE-03 — authoritative E1/E2 target identity. **NOT STARTED BY THIS ORDER.**
