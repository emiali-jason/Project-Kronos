# WO-07E — Evidence-supported NSE visual identity coverage

Status: Engineering candidate; Sponsor-authorized bounded correction under ADR-0018.
No deployment, production operation, staging or publication is implied.

## Authority and evidence

Current NSE scope is 91 equities and two indices. The existing visual publication
1.3.0 contains 13 equity labels and Nifty Bank Index. Immutable successor 1.5.0
retains those 14 relationships byte-for-byte as records and adds 35 relationships
supported by individually inspected, retained Sponsor TradingView chart headers.
The result is 48 equities plus BANKNIFTY; 44 instruments remain unavailable.
This is deliberately not a claim of complete visual-label coverage.

The companion `1.5.0-coverage.json` audits all 93 canonical instruments, lists
exact supported labels, intervals, source and manifest hashes, and states every
unavailable member. Its chart-source rows are an evidence index, not a runtime
alias fallback. The native universe/canonical catalogue remain authoritative for
membership and analytical identity. In particular RELIANCE retains canonical
identity `RELIANCE`, BAJAJ_AUTO resolves through its established canonical
`NSE-EQ-BAJAJ-AUTO`, and M&M remains `NSE-EQ-M&M`.

New labels were transcribed from the exact NSE chart headers. Reviewed company
names, Provider names, ticker syntax and general knowledge were not converted
into aliases. Each source manifest ties its immutable payload to a retained
Sponsor TradingView upload and subject. These Swing-owned chart bytes are read
as evidence only; Swing behavior and evidence are unchanged. No new chart corpus
or permanent raw-image archive is introduced into the repository.

For new relationships, the effective start is the latest of retained upload time,
canonical object's valid-from, and the source catalogue publication's effective
start. Existing relationships keep their original intervals and identities.
The open end uses the established publication convention. No record is
backdated merely to make the September Review pass.

ADANIGREEN's exact `Adani Green Energy Limited` is evidenced by a retained
2026-08-17 upload, before the 2026-09-09T15:40:05.435000+00:00 Review boundary.
M&M's exact `Mahindra & Mahindra Ltd.` is evidenced by a 2026-08-16 upload.
Their new intervals start at 2026-08-23T00:00:00+05:30, the applicable catalogue
publication boundary, and continue to the repository-standard open end.
`Nifty Bank Index` remains governed. `Nifty 50`, `NIFTY`, ticker-only `M&M` and
ungoverned spelling/punctuation variants remain unavailable. No source-qualified
NIFTY visual label was established by this audit.

## Composition and historical compatibility

Current Review and its chart-correspondence gate explicitly select 1.5.0.
There is no latest-file scan, catalogue-name lookup, fuzzy resolution or Provider
fallback. VisualIdentityResolver's exact, source-qualified, boundary-aware
algorithm is unchanged. Existing publications 1.0.0 through 1.4.0 are unchanged.

Already imported evidence retains its original publication version and integrity.
Historical revalidation selects that exact retained publication and verifies its
integrity before binding. This is an explicit replay-authority selection, not a
fallback for accepting a new unknown label. Missing/tampered historical authority
fails closed. Current operational imports continue to use the composed successor.
The current-Review adapter's policy, methodology, downstream states and request
construction are unchanged; no production WO-10 invocation is authorized.

## Exact submitted ADANIGREEN regression

The retained Answer SHA-256 is
`36ae790ed9b7287de9720b34d7549b4812074f8a9ed5714a5e6ba2a71093486e`.
An isolated copy of its governed Review/Probables/transport evidence is used;
production roots remain denied by the published test-isolation launcher.
The unchanged Answer passes batch envelope, Q1-Q10 schema and visual binding.
Its copied chart has no retained independent panel observations for 1D/1H/15M/5M.
The next governed result is `INTRADAY_CHART_CORRESPONDENCE_UNVERIFIABLE`, with
`PANEL_OBSERVATION_NOT_RETAINED` on all four panels. No synthetic observations
are added to this exact retained case to manufacture acceptance.

Separate, clearly synthetic fixtures test complete panel correspondence and
successful import/replay with the successor. They do not qualify the real chart.
This work does not change Question/Answer semantics, the chart gate, or FB02/FB03.

## Qualification and exclusions

Dedicated tests cover all 93 members, exact ADANIGREEN/M&M/BANKNIFTY labels,
unsupported NIFTY, unknown/foreign labels, case/punctuation, wrong source,
effective intervals, duplicate/conflicting/ambiguous relationships, integrity,
V1/V2 bindings, historical publication restoration and inert runtime composition.
Run dedicated, focused, affected and full regression through `tools/kronos_test.py`.
Freeze candidate bytes before final full regression; retain result logs and hash
manifests in isolated engineering output. No test reads production evidence.

MCX native contract publication 1.4.0 remains separate and unchanged. International
reference panels remain SUPPORTING_VISUAL_CONTEXT_ONLY /
NOT_INDEPENDENTLY_ESTABLISHED. No NSE-style MCX alias inference is introduced.

No Provider, Refresh/Discovery, Review/Question/Answer production operation,
Chart Analyst/OpenAI call, broker operation or runtime restart is permitted.
Historical rejection evidence is preserved. Concurrent runtime writes must be
inventoried separately without assigning an unsupported initiating actor.
FB01 and WO-07F remain outside this correction.
