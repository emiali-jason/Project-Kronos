# WO-07D — Sponsor current Review workspace

Status: Engineering candidate; Sponsor/EA publication review pending.
Authority: Sponsor-frozen WO-07D work order, 09 September 2026.
Owner: Intraday. Baseline: 10546460f372b0c08cf249594ff6c501cea7193f.

## Workspace and presentation

The existing WO-07B1 current producer/pointer decision remains authoritative.
No Review loaded offers explicit LOAD FRESH REVIEW. Producer advancement labels
REVIEW NON-CURRENT and suppresses superseded cards and all current bulk controls.
An empty current population stays empty; no historical fallback or automatic
Review creation occurs. Existing historical evidence remains immutable.

The page prioritizes current state, active count, latest Opportunities count and
primary action. Full run identities remain under header disclosures. Cards retain
exact Sponsor identity (including M&M), explicit LONG/SHORT, phase, boundary,
chart/Question/Answer states and existing collapsed V2 LINEAGE. Internal names,
methodology identity and full hashes remain available inside that disclosure.
Question ABSENT is presented as NOT CREATED; TRANSPORT_READY as READY. NOT_IMPORTED
is EXPECTED only with a retained transport; otherwise NOT REQUESTED. Receipt is
not represented as visual or temporal validation. Unknown typed states remain
visible rather than being mapped to success. Existing bounded inbox results keep
member rejection reasons, counts and partial-import outcomes visible.

There is one top bulk strip with chart-ready, Question-ready, Answer-imported,
Answer-rejected and reconciliation-eligible counts. Existing batch endpoints and
currentness guards are unchanged. An individual imported Answer has a disabled
ANSWER IMPORTED control. Exact deterministic Question and expected Answer
filenames remain in a compact disclosure. No inbox discovery, import, GC or
currentization is performed by page rendering.

## Responsive layout

Review-only styles use four columns at viewport widths of at least 1480px,
three from 1200px, two at intermediate widths and one at 760px or below. The
1536/1280/390 qualification targets expect 4/3/1 columns respectively. Grid
align-items:start preserves independent card heights and deterministic DOM/tab
order. Long identities wrap; controls retain at least 36px height. Workflow
navigation wraps on desktop and scrolls horizontally within its own narrow
container on mobile, without page overflow. Shared Browser/Swing source and
styles are unchanged.

## Exact retained chart preview

GET /intraday/review/v2/chart-preview requires exactly one each of run, cycle
and revision; it accepts no path, arbitrary filename, fuzzy selection or fallback.
The Intraday-owned reader uses the existing Review store codecs and integrity
validation with bounded descriptor-based no-follow reads. It reuses the governed
Answer-inbox ancestor containment primitive without changing that primitive.
Every ancestor and final file must remain an exact regular/directory object,
with metadata stable across the read. Symlinks, traversal, malformed identities,
missing/tampered files and foreign/currentness mismatches fail closed with a
bounded response. The existing workspace/producer locks cover currentness,
current chart identity, payload validation and final currentness recheck.

The response is the existing immutable PNG/JPEG payload with its governed media
type. Length/hash and the existing image validation must pass. Shared response
headers already supply no-store, nosniff, CSP and frame denial. No file path or
raw exception is returned. No chart copy, image manipulation, external fetch or
new evidence is created. An old link cannot follow a replacement revision or
load a superseded workspace.

A lazy compact thumbnail opens the exact original in a separate read-only tab.
Natural aspect ratio is retained: NSE 1D/1H/15M/5M and MCX reference/native
1D/4H/15M/5M composites are not split, annotated or regenerated. Qualification
images are explicitly synthetic fixtures, not Sponsor market evidence.

## MCX and preserved authority

Native and reference selectors retain their exact governed options. Missing
options explicitly explain unavailable governed contract/reference context at
the Review boundary. No option, roll or membership relationship is fabricated.
Existing metadata, chart-replacement and V2 Question/Answer engines are reused.
No USDINR semantics, question wording/schema, temporal observability, currentness,
methodology 2.2.0, Narrow CPR or 09:30 rule changes. No WO-07E reliability claim,
WO-07F reconciliation, WO-09 ledger/outcome/Statistics or downstream trading
consequence is introduced. There are no Swing improvements or new handover issues.

## Qualification and production boundary

Route, current-workspace and state-matrix tests use temporary stores under
published Test Isolation Hardening. Browser fixtures are exported by that same
runner. A separate Browser rendering sandbox denies every protected production
root and all TCP traffic; only temporary Unix profile IPC is permitted. All HTTP
responses are fulfilled in memory from fixture files. No production server,
Provider, Review control or real artifact folder is used by visual checks.

The evidence pack records focused, affected and full active-suite results,
exact paths/diff/SHA-256, desktop/mobile images, layout measurements and before/
after production hashes. Full regression runs after byte freeze; a later byte
change requires new final qualification. Publication and runtime activation are
separate Sponsor gates. WO-07E/F, WO-09 and WO-10 onward remain untouched.
