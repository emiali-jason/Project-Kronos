# Theta TE-06A visual theme qualification

**Status:** QUALIFIED isolated presentation candidate, 2026-10-11. Sponsor visual
acceptance, source publication, deployment and production runtime acceptance are
separate gates. No next slice is started.

TE-06A applies the Sponsor-approved subdued purple and indigo direction to Theta
Earners while preserving the dark KRONOS shell. The five requested visual states
pass Chrome inspection and responsive checks. Analytical behavior and all retained
Question, Answer, chart and persistence contracts are unchanged.

## Authority and scope

The Sponsor's TE-06A order authorizes presentation-only work in
`.theta-te01-v1`. The retained [Theta interface](../architecture/interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md)
and [TE-02 candidate](THETA-TE02-QUESTION-PACK-CANDIDATE.md) remain the functional
baseline. [ADR-0066](../architecture/adr/ADR-0066-THETA-PROSPECTIVE-INFORMATION-SET-AND-RETRIEVAL-TIMES.md)
and historical temporal behavior are not changed.

No shared Browser source, Dashboard, Swing, Intraday, Provider, application,
analytical model, schema or store implementation is changed. No Git commit,
push, production publication, production restart or production store operation
is performed. Genuine target and methodology authority remains fail-closed.

## Visual changes

Theta's page renderer alone emits the local theme stylesheet and wrapper.
The active Theta sidebar item, product mark, tabs, drill-in arrows, borders,
primary actions and focus indication use restrained purple. The existing logo,
sidebar structure, header composition, font family and local read-only status
area remain intact. Green success/confidence and amber warning semantics are
preserved; semantic states are not recolored purple.

OUTLOOK retains the normal empty state and START NEW ANALYSIS action. Accepted
evidence retains fixed commodity order, exact decimal range/confidence strings,
exact expiry dates, currentness, timestamps and detail bindings. Confidence is
displayed in compact green pills. Narrow layouts label E1 and E2 separately and
preserve the analysis date/time break. No Trend column or market sparklines are
introduced.

Five original local inline SVG primitives decorate commodity names: bullion for
Gold Mini and Silver Mini, a coil for Copper, barrel/drop for Crude Oil and a flame
for Natural Gas. They are small, deterministic, aria-hidden and nonfocusable,
with no external image dependency or analytical meaning.

NEW ANALYSIS retains the exact qualified six-card renderer, intake bindings and
paste script. Local CSS restyles cards, focus, buttons, ready states, pack controls
and the shared Macro panel. Two desktop columns and one narrow column preserve
usable cards. Preview height increases from 220 to 340 pixels; aspect ratio and
object-fit contain remain intact, with exact original links unchanged. Detail
retains all identity, target, source, integrity, narrative and original chart
content with local theme accents.

## Changed file manifest

Only these five source, test and record files are changed by this slice:

| File | Change |
| --- | --- |
| `src/kronos/browser/theta_routes.py` | Local stylesheet/wrapper and decorative Outlook/detail marks |
| `src/kronos/browser/theta_theme.py` | New Theta-only CSS and original SVG primitives |
| `tests/unit/theta/test_visual_theme.py` | Eleven theme, isolation, exact-byte and read-only rendering cases |
| `tests/unit/theta/test_view_separation.py` | Two presentation assertions adapted to the decorative arrow markup |
| `docs/engineering/THETA-TE06A-VISUAL-THEME-CANDIDATE.md` | This bounded qualification record |

Earlier staged, unstaged and untracked candidate changes remain preserved.
Generated evidence is retained separately in `output/theta-te06a-visual-theme`.
The launcher and HTTP-check helpers are disposable qualification tools outside
the repository, not a new production surface.

## Functional qualification

The final command used the existing protected runner:

```text
tools/kronos_test.py tests/unit/theta tests/unit/browser/test_product_route_isolation.py -q --junitxml=output/theta-te06a-visual-theme/functional-regression.xml
```

**Result:** 208 passed, zero failures, errors or skips; console duration 56.80
seconds, JUnit duration 56.730 seconds. Eleven TE-06A cases supplement the retained
Theta/Browser suite. Routes, paste/upload/replacement, Question generation,
Outlook/detail navigation, integrity, restart, raw Answer bytes and persistence
remain passing. The protected runner denies production stores and external
Provider network access.

Exact-byte tests preserve the TE-02 hashes of product-route composition,
`theta_charts.py`, contracts, workflow, store, historical transport, prospective
pack transport and Question generation. The existing whole-card and paste-script
hash guards also pass. Shared Browser server/views and Swing/Intraday/application
source have no differences from candidate HEAD, so no broader shared-source
regression slice is required by TE-06A. `git diff --check` passes.

## Visual qualification

Chrome inspected empty OUTLOOK, populated five-commodity OUTLOOK, NEW ANALYSIS
with missing charts, NEW ANALYSIS with all six charts ready, and GOLDM detail.
All five states were checked at the normal 1920-pixel desktop width and at
1440, 1024, 760 and 390 pixels: 25 state/width checks, zero horizontal page or
range overflow and zero broken image assets. All six ready preview images load.
Keyboard focus on the exact-original link and focused paste controls retain a
visible two-pixel purple outline. Screenshots confirm readable values, clear
active tabs, preserved semantic colors and no clipping or overlap in the
inspected layouts. The temporary viewport override is reset before handoff.

A mobile date/time-spacing defect found during visual inspection was corrected,
and compact commodity marks improve intermediate-width legibility. Long labels
and their drill-in controls wrap within their own cell. Final screenshots and metrics use the
final qualified source bytes.

Evidence includes `browser-visual-qa.json`, `focus-qa.json`, five desktop state
screenshots, narrow screenshots and `preview-http-smoke.json`. The bounded HTTP
check verifies five views, six original charts, all three Theta POSTs blocked
with 405, unchanged disposable evidence and zero Provider calls.

## Running Sponsor preview

- OUTLOOK: `http://127.0.0.1:8948/theta-earners`
- NEW ANALYSIS: `http://127.0.0.1:8948/theta-earners/new-analysis`
- PID: **9279**, left running for Sponsor inspection.
- Synthetic fixture clock: `2026-10-11T13:00:00+00:00`.
- Five explicitly synthetic accepted Answers, six synthetic composites and five
  independent retained Questions; none is genuine forecast authority.
- All HTTP mutations are blocked. The existing controls are visible for design
  inspection, not operational intake during this preview.

The ephemeral launcher inherits kernel denial of production evidence/Review Pack,
credentials and all outbound network except 8948 loopback. Its Provider factory
refuses operations and its counter remains zero. No collector, acquisition,
notification or lifecycle loop runs. Preview-only empty/missing fixture URLs are
`/__theta_visual/outlook-empty` and `/__theta_visual/analysis-missing`; these exist
only in the disposable launcher, not candidate application routes.

The earlier 8948 preview processes were refreshed by exact PID only, retaining
their temporary stores. Production **8947 / PID 95115** remains the same listener,
untouched. No production process, source, session or store is read for application
data, modified, stopped or restarted.

## Acceptance and next boundary

All displayed ranges, dates, confidence and chart candles in this preview are
synthetic visual fixtures. They establish neither market facts nor calibrated
probability. The normal no-current-analysis projection remains intact. Sponsor
inspection grants no publication or runtime acceptance; a subsequent explicit
order is required for any next slice.
