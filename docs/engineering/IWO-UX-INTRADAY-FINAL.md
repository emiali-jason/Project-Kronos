# IWO-UX final Intraday presentation

Status: Sponsor-authorized engineering candidate; exact-byte review, release and
read-only production acceptance are separate gates.
Owner: EA-Intraday; Browser/shared composition impact reviewed separately.
Baseline: fe9e2398a5952d95bdaa792d088ee02ca6997376.
Authority: Sponsor IWO-UX-INTRADAY-FINAL-SPONSOR-UX, 11 October 2026;
ADR-0062, ADR-0064 and existing WO08/WO09/experimental PAPER interfaces.

## Frozen two-requirement scope

UX-01 uses one compact Machine Review title, a method/PAPER line and a table of
current admitted assessments. Each row exposes direction, I1–I5, score, WO09
state, exact MCX contract where present, retained watch/missing criterion,
first-five and Assessment Price. Keyboard-accessible native details retain
criterion reasons, actual values, method/source evidence, governance and
historical Question/Answer/WO07F viewing. Non-admitted, stale and unverified
assessments remain secondary. Missing currentness authority never makes them
current. Typography changes are scoped to `.machine-review` and its containing
header; Swing and global CSS are unchanged.

Assessment Price comes only from the exact retained Probables admission
companion, matched to the displayed run/result/subject/session/direction. Its
observation time, source and authority remain inspectable. It is not experimental
P, a quote fallback, Entry, or a replacement for the immutable original
opportunity price across subsequent admissions. Missing price remains explicitly
unavailable. The persisted WO08 analytical document is not modified.

UX-02 counts exact persisted WO09 BUY_NOW/SELL_NOW as READY_FIVE / 5/5 NOW,
and BUY_READY/SELL_READY as READY_FOUR / 4/5 READY. This read-only Browser
projection reuses existing producer read scopes and DOMAIN008 session checks.
It verifies the current WO09 pointer, Probables run/result, complete WO08
membership/integrity, Native binding and exact current MCX contract/roll. Source
scopes cover the aggregate; WO09 pointers are compared again before return.
It does not call the analytical evaluator or publish/update any authority.

An empty configured owning WO09 store is authoritative zero, labeled
NO_CURRENT_READINESS. Missing composition, missing required authority or corrupt
source evidence is unavailable (em dashes), never a fabricated zero. Historical,
closed-session, superseded and stale-pointer readiness does not count. A retained
MCX HARD_GATE/READINESS_UNAVAILABLE with neither contract nor roll claim is
non-countable and not shown as current; it does not erase a valid NSE count.
Missing authority for a claimed contract remains unavailable. No clock
TTL is invented. The summary describes readiness classifications, not handoff
or Entry eligibility; commissioned first-five/handoff freshness remains a
separate downstream check. VIEW INTRADAY retains `/intraday` navigation.

WATCHING_DASHBOARD_METRIC = DEFERRED_NOT_AUTHORITATIVE.
Existing Browser watch facts are retained bindings/hints, not a clean current
active-delivery count. They stay explicitly labeled retained evidence in Review;
no lifecycle reconstruction, new subscription or new count authority is added.

## Composition and actual impacts

`KronosBrowserServer` and `create_browser_server` gain one optional final
`intraday_dashboard_summary` supplier, default absent. Missing supplier renders
Intraday summary unavailable; Swing sources/counts/markup are unchanged.
Canonical `tools/kronos_browser.py` supplies the existing WO09 store and existing
publication-boundary dependencies. No construction invokes the supplier.

`IntradayWo09Projection` optionally attaches this operational summary to its
Browser-only status document. The default is `None`, preserving retained
pointer-only projection semantics. `IntradayWo08Projection.status_document`
additively exposes retained admission-price fields. Persisted schemas, readiness
policy, source stores, public producer contracts and mutations are unchanged.
These additive Browser/composition API effects require PCP impact disposition;
there is no Swing behavior change requiring an EA-Swing behavioral redesign.

## Qualification and visual evidence

The mandatory `tools/kronos_test.py` harness denies production roots and external
networking at the kernel boundary. Qualification protects Dashboard, Review,
WO08/WO09, selective-watch projection, historical evidence, navigation,
currentness, canonical composition and Swing presentation. Tests include a
complete real persisted source graph with actual owner locks and DOMAIN008
calendar: NOW=1 in its open session, NOW=0 in a later open session, unchanged
source bytes. Negative tests distinguish empty from missing/corrupt authority.

`tests/unit/browser/test_intraday_iwo_ux.py::test_write_visual_rehearsals` is the
reusable disposable HTML writer. Set `IWO_UX_VISUAL_OUTPUT` to an evidence folder
and run it through the governed harness. It emits empty, populated, expanded
criterion, expanded history and zero/nonzero/unavailable Dashboard pages.
Native details need no script. Browser screenshots must block network and app
polling in these standalone rehearsals. A–G and I are exercised; H is
inapplicable because WATCHING is deferred. These fixtures create no production
opportunities. Exact commands, failed runs, final JUnit results, screenshots and
candidate hashes are retained in the work-order evidence directory.

No Provider calls, Analysis, research publication, notifications, PAPER/trading
actions, runtime transition, commit or push is performed by this engineering
candidate. Final closure and INTRADAY_V1_UX freeze follow release acceptance.
