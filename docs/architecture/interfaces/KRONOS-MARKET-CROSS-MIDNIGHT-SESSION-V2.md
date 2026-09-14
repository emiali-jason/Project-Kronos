# DOMAIN-008 — Explicit Session Offsets and Ownership V2

- **Status / architecture:** APPROVED — Proposal 3
- **Approver:** Chief Architect / DOMAIN-008
- **Approval date:** 2026-09-14
- **Approved revision:** Proposal 3
- **Commissioning status:** UNCOMMISSIONED
- **Engineering status:** DEFERRED FUTURE CAPABILITY
- **Current-production requirement:** NONE ESTABLISHED
- **Current NSE/MCX disposition:** SAME-DATE CONFIRMED
- **Cross-midnight successor capability:** DEFERRED
- **Partial implementation:** Safely archived and removed from the active worktree
- **Reactivation:** Requires an authoritative D+1 schedule or new explicit Sponsor instruction
- **Approval verdict:** WO-SWING-03A-ARCH-APPROVAL-02 = APPROVED
- **Revision:** Proposal 3 — WO-SWING-03A-CONTRACT-REV02
- **Owner / producer:** DOMAIN-008 / Chief Architect
- **Authority:** MARKET_SCHEDULE_ONLY
- **Governing ADR:** [ADR-0056](../adr/ADR-0056-DOMAIN-008-CROSS-MIDNIGHT-SESSION-FOUNDATION.md)

**Consumers:** version-aware Market adapters, Swing facts/scheduling/restoration,
and existing shared/Intraday persistence only within separately authorized scope.

All Proposal 3 requirements below are approved normative requirements under
WO-SWING-03A-ARCH-APPROVAL-02. Historical uses of “proposed” identify their
proposal origin, not a remaining approval gate. The Sponsor has deferred
WO-SWING-03A-ENG. This approved contract remains available for future
implementation but is not commissioned, published as a production capability or
runtime-loaded. Existing manifest V3/V1 remains production authority.

WO-SWING-03B inspected 1,327 current production windows and found zero D+1
windows. NSE and all five Swing MCX families are same-date; unchanged-HEAD
verification passed 231 tests. No current production record requires V2.
Synthetic D 23:00 to D+1 01:00 remains a deferred successor capability.
Intraday source was restored byte-identically to HEAD. The archived partial
implementation is at `/Users/imranali/Documents/Project-KRONOS/output/swing-deferred/WO-SWING-03A-2026-09-14`.

## 1. Exact version dispatch and types

Every identity/version literal in this section is a JSON **string** and a
runtime Python **str** (exact type, no numeric/boolean coercion). Backticks
containing quotes below denote the complete string value. Thus `"2"` is valid;
JSON `2`, `2.0`, `true`, `null` and runtime int/float/bool are invalid.

| Surface and exact fields | Exact proposed literals |
| --- | --- |
| Official publication: schema; contract_identity; contract_version | `"KRONOS-MARKET-CALENDAR-PUBLICATION-V2"`; `"KRONOS-MARKET-CALENDAR-V2"`; `"2"` |
| Normalized schedule: contract_identity; contract_version | `"KRONOS-MARKET-SCHEDULE-V2"`; `"2"` |
| Shared day schedule: schema_identity; contract_version | `"KRONOS-MARKET-SCHEDULE-V2"`; `"2"` |
| Resolver request: schema_identity; schema_version | `"KRONOS-MARKET-SESSION-RESOLUTION-REQUEST-V1"`; `"1"` |
| Resolver result: schema_identity; schema_version | `"KRONOS-MARKET-SESSION-RESOLUTION-V1"`; `"1"` |
| MCX family profile: contract_identity; contract_version | `"KRONOS-MCX-CONTRACT-FAMILY-SESSION-V2"`; `"2"` |
| Compatibility artifact: schema_identity; schema_version | `"KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V2"`; `"2.0.0"` |
| Compatibility artifact: policy_identity; policy_version | `"KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V2"`; `"2.0.0"` |
| Adjacent-publication manifest: schema | `"KRONOS-MARKET-CALENDAR-MANIFEST-V4"`; no separate version field |

Publication `calendar_version`, shared `source_version`, family profile
`publication_version`, and compatibility `base_schedule_version`,
`derived_schedule_version`, `base_publication_version`,
`derived_publication_version` are **opaque nonempty strings** copied exactly
from their bound source (for example `"TEST.2"`), not the number 2 and not
implicitly the literal `"2"`. Their value is source-specific; never parse
version numbers to select a publication. Contract-version pair fields in the
compatibility artifact are exactly `"1"` for the unchanged V1 schedule contract
or `"2"` for V2; each must match its explicit identity.

`publication_binding.contract_version` is also a string. Permitted complete
binding discriminators are:
- base V1: schema `"KRONOS-MARKET-CALENDAR-PUBLICATION-V1"`,
  contract_identity `"KRONOS-MARKET-CALENDAR-V1"`, contract_version `"1"`;
- base V2: schema `"KRONOS-MARKET-CALENDAR-PUBLICATION-V2"`,
  contract_identity `"KRONOS-MARKET-CALENDAR-V2"`, contract_version `"2"`.
For a derived MCX schedule the binding remains the **base calendar publication**;
its family-rule publication identity/version/digest remains separately bound
in the family profile and compatibility artifact. Do not invent a V2 official
family publication. Existing source rules remain unchanged.

Do not change any V1 constant, literal, serializer or exception. Dispatch on
complete discriminator tuples, not filenames, optional fields or civil dates.
Missing/wrongly typed discriminators fail shape validation; a correctly typed
but unsupported tuple fails version validation (§9). Proposal revision numbers
are not runtime schema versions.

The existing integrity-sealed V1 parser `parse_market_calendar_publication`
retains its exact V1 syntax. It cannot accept offsets or claim V2. A dedicated
official V2 parser projects validated facts into the two successor runtime
representations. Existing manifest V3 remains unchanged for V1-only operation;
V2 adjacency uses the proposed manifest V4 in §11. No production manifest or
publication is created by this order.

## 2. Strict official publication wire shape

The V2 top-level key set is exactly the existing official publication key set:
`schema`, `contract_identity`, `contract_version`, `calendar_identity`,
`calendar_version`, `market_identity`, `exchange`, `segment`, `timezone`,
`coverage_start`, `coverage_end`, `source_boundary`, `official_sources`,
`trading_dates`, `non_trading_dates`. Only the first three discriminators and
the trading-session window shape change. Existing source provenance and
coverage validation remain mandatory. Supported market scope remains NSE/MCX
and the existing governed timezone Asia/Kolkata; no new timezone commissioning.

`trading_dates` maps ISO trading-date labels to exactly:
`{"session_type": <existing nonempty type>, "windows": [<window>, ...]}`.
V2 always uses a nonempty ordered window array, even for a singleton; no compact
`session_type/open/close` alternative. Each window has exactly these four keys:

| Field | Exact proposed type / constraint |
| --- | --- |
| open | Local clock string `HH:MM:SS`, 00:00:00 through 23:59:59 |
| open_day_offset | JSON integer 0 or 1; booleans, floats, strings and null rejected |
| close | Same clock syntax as open |
| close_day_offset | JSON integer 0 or 1; same strict typing |

No implied defaults, timezone suffixes on local clocks, `24:00`, leap seconds,
duplicate JSON keys or unknown fields. Array position defines order starting at
1, not sorting by clock value. First window open_day_offset is 0; later windows
may open on 0 or 1. Each close is strictly after its open in resolved UTC time.

Synthetic representation only, not exchange hours:

```json
{"session_type":"SYNTHETIC_VALIDATION","windows":[
  {"open":"23:00:00","open_day_offset":0,"close":"01:00:00","close_day_offset":1}
]}
```

`non_trading_dates` retains its existing explicit date-to-reason mapping.
Coverage is a complete, disjoint partition of trading and declared non-trading
dates. An absent date is missing coverage, never an inferred holiday. Official
source identities/references, effective coverage and source boundary remain
required. The manifest retains exact file SHA-256 bindings; it must dispatch
each publication explicitly without changing existing manifest/source bytes.

## 3. Absolute resolution and publication validation

For trading date D, resolve each endpoint as D plus its published day offset,
at its published clock in the governed IANA timezone. Retain that local form,
the timezone, offset and owner D. Convert to UTC for all comparisons and elapsed
arithmetic. Reject a local time which is nonexistent or unresolved-ambiguous;
do not select a fold or repair a gap by guessing. No general DST-market feature
is commissioned.

Require positive UTC duration; increasing ordered windows; no window overlap;
and no session-envelope overlap among competing owners within the same market,
exchange, segment and applicable schedule lineage. Envelopes are
`[first_open, final_close)`. Adjacent endpoints are allowed. Non-overlapping
windows with overlapping envelopes from different owners are still conflicting.
Validate neighboring entries and effective publication boundaries, not only one
date at a time. Different unrelated exchanges/segments are not competing owners.
Exact governed family specialization is selected before resolving ownership;
base/derived schedules are not two interchangeable candidate owners.

Offsets bound endpoints to D or D+1. No arbitrary less-than-24-hours duration
threshold is added. Neither representability nor equal-clock 0-to-1 endpoints
commissions a continuous 24-hour market. Source rules remain the authority for
any actual duration or special session.

## 4. Runtime representations and successor serialization

Keep the two existing concepts: `MarketDaySchedule` with `MarketWindow`, and
normalized `MarketSchedule` with `MarketSessionWindow`. V1 constructors/adapters
and payloads keep their original guards and output. Use explicit V2 construction
paths/types as necessary; do not make V1 silently accept overnight semantics.

For shared day-schedule V2, the exact persisted keys are existing
`exchange`, `trading_date`, `session_id`, `timezone`, `status`, `windows`,
`source_identity`, `source_version`, `special_session`, `schema_identity`, plus
`contract_version` and `publication_binding`. Each window has `opens_at`,
`closes_at`, `open_day_offset`, `close_day_offset`; aware endpoint strings must
reproduce the source clock/offset resolution exactly. status is exactly the string TRADING or NON_TRADING; special_session is an
exact JSON boolean. Other scalars are nonempty strings. Declared non-trading
entries have windows=[]; no field is omitted.

For normalized schedule V2, all scalar fields are strings except explicitly
nullable summary endpoints; order/offsets are exact integers and windows and
provenance are arrays. No field is omitted. Retain the full `MarketSchedule` field set:
`contract_identity`, `contract_version`, `identity`, `market_identity`,
`exchange`, `trading_date`, `calendar_identity`, `calendar_version`,
`session_identity`, `session_type`, `session_open`, `session_close`, `timezone`,
`market_availability`, `as_of`, `source_identity`, `source_boundary`,
`freshness_status`, `integrity_status`, `provenance`, `windows`; add only
`publication_binding`. Each window has `identity`, `order`, `window_open`,
`window_close`, `open_day_offset`, `close_day_offset`. Singleton legacy-summary
open/close fields match that window; multi-window summary fields stay null.
market_availability is one of OPEN, CLOSED, PRE_OPEN, POST_CLOSE, UNAVAILABLE;
freshness_status is CURRENT, STALE or UNAVAILABLE; integrity_status is VALID or
INVALID. These are exact string enums retaining their existing meanings. Invalid/missing
authority does not produce a usable schedule.

In either V2 representation `publication_binding` has exactly:
`schema`, `contract_identity`, `contract_version`, `calendar_identity`,
`calendar_version`, `publication_sha256`. All are explicit strings and the SHA
is lowercase 64-character hexadecimal. This is the exact selected base calendar publication binding (also for a
family-derived schedule), never an alias to latest. Derived authority additionally
retains its exact family-rule source binding in provenance and compatibility.

Persisted local datetimes use ISO 8601 with explicit offset and seconds; dates
use ISO YYYY-MM-DD. On restoration validate local endpoints against the retained
publication, timezone and offsets, and independently compare UTC instants. A
timezone-data change producing different endpoints is a mismatch, not permission
to reinterpret history.

## 5. Deterministic identity and integrity contract

### 5.1 Canonical encoding C and digest H

For each explicitly named map below, C is UTF-8 encoding of
`json.dumps(map, ensure_ascii=True, sort_keys=True, separators=(",",":"), allow_nan=False)`
with **no final newline**. Keys are ASCII strings; no duplicate keys. String
values are preserved exactly, without trimming/case folding/Unicode normalization.
Numbers are exact integers only where specified (window order and day offsets);
booleans are JSON true/false, never integers. No floats. Enums serialize as their
exact uppercase string values; null as JSON null; tuples as ordered JSON arrays.
Arrays are not sorted by the serializer. Source window order and provenance order
are authoritative. Maps admit only the specified fields; no implicit defaults.

Dates are strings YYYY-MM-DD. Local source clocks are strings HH:MM:SS.
Resolved schedule/window endpoints and source boundaries are strings
YYYY-MM-DDTHH:MM:SS+05:30 in the governed Asia/Kolkata timezone. Source resolution
has whole-second precision; no Z, alternative offsets or fractional seconds in
those canonical fields. Equivalent instants must be converted before encoding.

Query instants, as_of, analysis_boundary and completed-interval endpoints use
UTC strings YYYY-MM-DDTHH:MM:SS.ffffff+00:00, **six fractional digits including
zeros**. Runtime input may be aware datetime; normalize to these canonical
strings before encoding. Wire input must already use its specified canonical
form. A naive datetime or precision-losing conversion is invalid.

H(map) is SHA-256(C(map)), **lowercase** 64 hexadecimal digits. Prefixes below
are concatenated *after* hashing and are not part of the digest input. The
`integrity_identity` digest map includes its object's prefixed primary identity.
All new hashes use this rule; existing V1 formulas/case remain untouched.

### 5.2 Stable schedule map S

S has exactly these keys (types defined by §1/§4):
`contract_identity, contract_version, market_identity, exchange, trading_date,
calendar_identity, calendar_version, session_identity, session_type, timezone,
source_identity, source_boundary, publication_binding, windows, provenance`.

- All scalars are strings; publication_binding is the exact six-string map in §4.
- windows is the ordered array of complete normalized window maps, including
  `identity, order, window_open, window_close, open_day_offset, close_day_offset`.
- provenance is an ordered array of nonempty immutable authoritative source
  reference strings; it **does participate**. It must not contain query times,
  request IDs, generated diagnostic prose or status. Derived provenance includes
  the exact family-rule publication identity, version and SHA as source facts.

`schedule.identity = "MARKET-SCHEDULE-V2-" + H(S)`.

Exclude `as_of, market_availability, freshness_status, integrity_status`,
presentation text and containing artifact metadata. Also exclude singleton
`session_open/session_close` (redundant, validated against windows) and
`identity` itself. A projection at a different as_of has the **same identity**
provided S is unchanged. Its observational status can differ and its separate
containing-evidence integrity can differ. A changed authoritative publication,
window or provenance creates a new identity, even with matching clocks.

### 5.3 Window map W

W has exactly:
`publication_binding, trading_date, session_identity, order, window_open,
window_close, open_day_offset, close_day_offset`.
All types/representations follow §5.1. Only order/offsets are integers. W has no
as_of, availability, own identity or separate provenance; provenance is bound
through publication_binding and owning schedule S.

`window.identity = "MARKET-WINDOW-V2-" + H(W)`.

Shared day-schedule projection retains its session_id and containing artifact
integrity; it creates **no additional schedule/window identity scheme**.
MCX family profiles likewise create no new primary ID field. Their existing
publication identity/version/digest and exact schedule binding are preserved.

### 5.4 Resolver maps Q and R

Q is the **entire admitted canonical request map in §6**, including mode-specific
required keys, and excluding nothing. Forbidden keys are absent, not null.
`request_identity = "MARKET-SESSION-REQUEST-V1-" + H(Q)`.
The request has no caller-provided identity field.

R is the entire exact result map in §6 **excluding only**
`resolution_identity` and `integrity_identity`.
It includes request_identity, as_of, query_instant, state/reason/phase, owner,
returned schedule/window, temporal_use, interval_completion_validated and
provenance. Resolver identity is deliberately observation/request-specific;
schedule identity is not.

`resolution_identity = "MARKET-SESSION-RESOLUTION-V1-" + H(R)`.
`integrity_identity = "INTEGRITY-MARKET-SESSION-RESOLUTION-V1-" +
H(R plus resolution_identity)`.
Here “plus” means adding that exact named key/value to the map, not concatenating
serialized documents. The integrity field itself is never hashed.

### 5.5 Compatibility map K and publication bytes

K is exactly the full typed field set in §8 minus only compatibility_identity
and integrity_identity. It includes provenance, all source/version bindings,
timestamps, booleans and the explicit null supersession field.

`compatibility_identity = "MARKET-SCHEDULE-COMPATIBILITY-V2-" + H(K)`.
`integrity_identity = "INTEGRITY-MARKET-SCHEDULE-COMPATIBILITY-V2-" +
H(K plus compatibility_identity)`.

The new V2 `*_serialized_schedule_sha256` fields hash C of the complete
versioned serialized schedule, **including** its stable identity and observation
projection fields. They certify those exact bytes/projections, not stable
schedule identity. V1 schedule/session digest fields retain their original
serialization definitions. For V2, base_session_sha256 hashes C of the previous shared day schedule and
derived_session_sha256 hashes C of the current derived shared day schedule.
The three new serialized_schedule digests instead hash complete normalized
base/derived/previous schedules. Consumers must not exchange these meanings.

V2 official publication files and manifest bindings use **raw exact file-byte
SHA-256**, lowercase hex without a prefix, not a hash of a reconstructed object.
Canonical writers use C with no final newline; readers retain and verify exact
bytes before parsing. `calendar_identity` and `session_identity` are assigned
source identities, not newly invented hash outputs. No new general integrity
field is added to the official publication. Golden vectors in §12 specify
complete canonical inputs and exact expected outputs; they are documentary
calculation checks, not production acceptance tests.

## 6. Exact DOMAIN-008 resolver request and result

### 6.1 Request Q: closed shapes

Every mode has these **required** keys:
`schema_identity, schema_version, mode, purpose, scope, manifest_binding,
publication_binding, schedule_selection, query_instant, as_of`.
Their values are:
- schema_identity/version: exact request literals in §1.
- mode: exactly `"BOUND_OWNER"`, `"UNBOUND_TIMESTAMP"`, or
  `"RETAINED_COMPLETED_EVIDENCE"`.
- purpose: exactly `"OBSERVATION_AS_OF"` or `"FUTURE_SCHEDULE"`.
- scope: exact object `{market_identity, exchange, segment, timezone}`, all
  nonempty strings matching the selected publication. timezone is
  `"Asia/Kolkata"`; no caller-invented scope alias.
- manifest_binding: exact `{schema, sha256}`, both strings. schema is the
  unchanged `"KRONOS-MARKET-CALENDAR-MANIFEST-V3"` for V1-only resolution, or
  `"KRONOS-MARKET-CALENDAR-MANIFEST-V4"` for explicit V2 resolution; sha256
  is verified lowercase 64-hex of the exact retained manifest bytes.
- publication_binding: exact §4 object, selected from that manifest.
- schedule_selection: exact closed discriminator object below; required even
  for base calendars. There is no implicit family context or caller-local default.
- query_instant/as_of: canonical UTC timestamp strings in §5.1; runtime aware
  datetime accepted only through lossless canonical conversion.

| Mode | Additional required keys | Forbidden keys/values |
| --- | --- | --- |
| BOUND_OWNER | owner | completed_interval; purpose may be either declared value |
| UNBOUND_TIMESTAMP | None | owner and completed_interval (including null) |
| RETAINED_COMPLETED_EVIDENCE | owner, completed_interval | purpose FUTURE_SCHEDULE |

schedule_selection is one of exactly:
- `{kind}` with kind="BASE_CALENDAR"; no other keys.
- `{kind, contract_family, contract_expiry, profile_contract_identity,
  profile_contract_version, family_publication_identity,
  family_publication_version, family_publication_sha256}` with kind="MCX_FAMILY".
  contract_family is one of GOLDM, SILVERM, COPPER, CRUDEOIL, NATURALGAS;
  contract_expiry is an exact ISO date string. profile_contract_identity/version
  are KRONOS-MCX-CONTRACT-FAMILY-SESSION-V2 / "2" for a V2 base, or the unchanged
  KRONOS-MCX-CONTRACT-FAMILY-SESSION-V1 / "1" for V1. Family publication identity/version are exact nonempty
  source strings; digest is lowercase 64-hex. Resolve that exact family-rule
  publication from manifest.mcx_contract_family_sessions, verifying its digest,
  source boundary, scope and expiry-effective rule. Wrong scope/binding is
  MARKET_SESSION_LINEAGE_MISMATCH, missing bytes MARKET_SESSION_SOURCE_UNAVAILABLE, unavailable exact applicable
  expiry rule MARKET_SESSION_EXPIRY_AUTHORITY_UNAVAILABLE. No instrument selection or alias guess.

scope names the base publication scope; MCX_FAMILY is lawful only for MCX /
MCX_NON_AGRI / FUTURES_NON_AGRI. Its derived profile segment remains MCX_FUTURES.
Family rule specialization is selected before ownership resolution; the returned
schedule/window is from that exact specialization, not an interchangeable base.
For retained historical resolution derive schedule facts for the requested owner
from the retained rule; current contract_eligible is not an ownership override.
This does not commission a family, extend expiry, select a rolling contract or
return an eligibility/entry decision. All window/cutoff rules stay governed.

owner is exactly `{trading_date, session_identity, publication_binding,
schedule_selection}`.
The first two are nonempty ISO date/string; publication_binding is the full §4
tuple including schema, contract identity/version, calendar identity/version and
digest. No field in Q or its nested objects may be null. No other keys, wildcard
owner, latest pointer, optional default, caller hash, requested status or raw
publication bytes are admitted. Bound owner publication_binding and schedule_selection must equal Q's selected
values. For every candidate date, resolve only the explicitly selected base or
family-derived session identity; do not substitute the current active contract.

completed_interval is exactly:
`{source_interval, source_start, source_end, window_identity}`.
source_interval is string `"60minute"`; endpoints are canonical UTC timestamp
strings; window_identity is the nonempty exact retained window identity. This
mode validates the temporal ownership/completion of a source 1H constituent;
it is **not** a general DAY/weekly resolver and does not validate OHLCV itself.
DAY consumers use BOUND_OWNER with their independently governed date label.
4H consumers validate source constituents and their own existing completeness
rules. No inference of a DAY label from timestamp containment.

### 6.2 Query/as_of and future reminder semantics

OBSERVATION_AS_OF requires query_instant <= as_of. The as_of value is explicitly
supplied by the calling governed run/event/replay; no hidden wall-clock read.
Selected sources must have source_boundary <= as_of and lawful coverage.
A historical replay uses its historical as_of with the exact retained sources.

FUTURE_SCHEDULE requires query_instant > as_of. Only BOUND_OWNER and
UNBOUND_TIMESTAMP may use it; all source/coverage/ownership checks still apply
as known at as_of. Result temporal_use is FUTURE_SCHEDULE and
interval_completion_validated is false. OWNED_ACTIVE then means only that the
**published window would contain the future query**, not that the market is
currently open or that any candle/tick exists.

For reminders, the caller asks this operation about exact candidate boundaries
using the same selected manifest. DOMAIN-008 enumerates candidate session/window
endpoints in increasing UTC order, starting with C-1/C at the source boundary and
then covered following dates; it returns/uses the least governed completed-hour
boundary strictly greater than the source boundary under the existing recurrence
rule. This is composition over these exact requests, not a fourth hidden resolver
mode or a new completion claim. At a closing endpoint use BOUND_OWNER, since
UNBOUND_TIMESTAMP activity excludes close. No lookahead outside verified coverage,
no Provider retrieval, and no fabricated completed bar. Query/as_of rules remain
enforced for every composed request.

RETAINED_COMPLETED_EVIDENCE additionally requires:
- query_instant == completed_interval.source_start;
- source_start < source_end <= as_of;
- source_start in the named active window of the exact bound owner and equal to
  window_open + n elapsed UTC hours for an exact nonnegative integer n;
- source_end == min(source_start + one elapsed UTC hour, that window close);
- no gap or owner crossing; source_boundary <= as_of (publication metadata is
  not itself a candle boundary).

For RETAINED_COMPLETED_EVIDENCE, failure of
`query_instant == completed_interval.source_start` is rejected with
reason_code=MARKET_SESSION_INTERVAL_INVALID, state=INVALID and phase=COMPLETION.
The result has owner=null, schedule=null, window=null and
interval_completion_validated=false; no trusted projection escapes. This mapping
applies even when the completed interval is otherwise correctly anchored,
contained, chronological and complete. Existing §9.2 validation precedence is
unchanged: an earlier failing phase still takes precedence; an isolated
query/start mismatch fails specifically at COMPLETION.

The result certifies these temporal predicates only; it does not manufacture
market observations or prove a supplied candle exists. Endpoints at close use
the bound owner, never rebind through unbound lookup of source_end.

### 6.3 Owner resolution

BOUND_OWNER validates the supplied exact tuple and returns BOUND_BEFORE_OPEN
before first open, OWNED_ACTIVE in a window, OWNED_GAP in the envelope's break,
or BOUND_COMPLETED at/after final close. It never substitutes query civil date.
Historical bound completion stays with its original owner after later sessions
open. The source family/expiry contract, not this mode, decides expiry eligibility.

UNBOUND_TIMESTAMP checks only query civil date C and C-1 under the 0/1 rule,
with §11's validated manifest adjacency and exact coverage. One unique envelope
gives OWNED_ACTIVE/OWNED_GAP; multiple envelopes give INVALID; none with both
dates authoritatively resolved gives NO_OWNER. Missing necessary coverage gives
UNAVAILABLE, including an unproven predecessor edge. A holiday C does not erase
a lawful C-1 tail. V1 same-day exclusion rules remain valid only in that exact
V1 lineage. Activity is [open, close); adjacent next-open ownership is distinct.

RETAINED_COMPLETED_EVIDENCE performs the exact bound and interval checks above.
On success its state is `"COMPLETED_EVIDENCE_BOUND"`, whether or not the whole
session has ended at as_of; no claim of BOUND_COMPLETED is inferred from merely
one completed hour.

### 6.4 Result: closed shape and null rules

Exact keys:
`schema_identity, schema_version, request_identity, query_instant, as_of,
temporal_use, state, reason_code, phase, owner, schedule, window,
interval_completion_validated, provenance, resolution_identity, integrity_identity`.

- schema_identity/version: exact result literals in §1.
- request_identity/resolution_identity/integrity_identity: §5 strings.
- query_instant/as_of: admitted request values, not newly sampled times.
- temporal_use: `"AS_OF_SCHEDULE"` for ordinary requests,
  `"FUTURE_SCHEDULE"` for future requests, `"RETAINED_COMPLETED_INTERVAL"`
  for retained-completion mode.
- state: one of the exact §9 state values; reason_code is null on success,
  otherwise the exact mapped code. phase is the exact §9 phase string.
- owner: exact §6.1 owner object; schedule: the complete normalized versioned
  schedule (§4 for V2, unchanged V1 serialization otherwise).
- window: the complete matching normalized window for OWNED_ACTIVE and
  COMPLETED_EVIDENCE_BOUND; null for gap/before/whole-session-completed states.
- owner/schedule/window are **all null** for NO_OWNER, UNAVAILABLE and INVALID.
  No partial trusted schedule escapes on failure.
- interval_completion_validated is boolean true **only** for successful
  COMPLETED_EVIDENCE_BOUND; false for every other state, including future.
- provenance: ordered array of exact inspected publication binding references,
  each base reference encoded as `calendar_identity + ":" + calendar_version + ":" +
  publication_sha256`; selected base first, then distinct adjacent base entries by
  trading-date coverage order, then the selected family-rule reference if any
  (publication_identity + ":" + publication_version + ":" + publication_sha256). Empty only if no publication was validated.
  No free-form exception or current-clock text. It participates in R's hashes.

Every result key is present, including null fields; there are no omitted optional
result fields. Schedule.as_of equals Q.as_of; availability is projected at as_of,
not at a future query. Future ownership state and current availability must not
be conflated. A wrong/malformed request rejected before admission raises the
bounded outer exception in §9 and produces **no result and no request identity**.
For an admitted request, validation failures return the exact failure result
above, with hashes of sanitized structured data only.

## 7. Completed evidence, expiry and scheduling preservation

1H binds its source start to an active owner/window. Completion uses the earlier
of start+1h (elapsed UTC) and that window's close, not the entire split-session
close. A source candle may not bridge a gap. 4H constituents group by exact
trading-date/session/window lineage and preserve the existing window anchor;
midnight alone is not a reset. Existing constituent completeness and remainder
labels remain. No 4H bucket spans a gap or another owner.

DAY timestamps retain the existing Provider trading-date label contract; they
are not unbound instants at midnight. Unknown label semantics are unavailable.
Daily completion waits for the labeled owner's final close. Weekly membership
uses those trading dates, not endpoint civil dates; Friday ending Saturday stays
in the Friday-owned governed week. Prior completed 1H remains available until a
new completed hour exists; no assumed 09:30 or Intraday 15M/5M rule.

Progression and next-completed-hour/reminder boundary lookup must include the
still-owning prior date and preserve current recurrence/deletion/recovery policy.
Do not change thresholds or reinterpret EAIC OPEN/CLOSED as reminder authority.

For MCX, separate expiry trading date from the authorized absolute cutoff. V2
family profiles retain existing fields plus the exact required field
publication_binding (the six-string base binding in §4); the expiry boundary need not have the same civil date as expiry, but
must equal the exact source-governed family boundary for that expiry owner.
Normal-session rules consume that owner's final close; COPPER's existing fixed
17:00 rule remains on its expiry date with no inferred offset. Missing fixed
cutoff coverage is unavailable, not replaced by generic session close.
Eligibility stays inclusive at the cutoff (`observed <= cutoff`) and ends
strictly after it; activity remains exclusive at close. Product cutoffs and
expiry eligibility are distinct. No rollover or active-contract selection changes.

## 8. Compatibility and shared recovery

ADR-0028 V1 artifacts remain byte-identical and restricted to their existing
contracts. The proposed V2 artifact is still a directional, family-specific
expiry-session specialization, never a global compatibility flag. It does not
certify equivalence of arbitrary calendar versions or research capabilities.

### 8.1 Exact closed V2 field map

The full serialized artifact has exactly these keys; K excludes only the two
primary/integrity output fields as specified in §5:

```text
compatibility_identity, contract_family, exchange, market_identity,
base_segment, derived_segment, timezone, trading_date, previous_trading_date,
analysis_boundary, current_session_identity, previous_session_identity,
base_session_identity, base_session_sha256, base_schedule_identity,
base_schedule_version, base_publication_identity, base_publication_version,
base_publication_sha256, base_source_boundary, derived_schedule_identity,
derived_schedule_version, derived_session_sha256, derived_publication_identity,
derived_publication_version, derived_publication_sha256, derived_source_boundary,
derivation_relationship, effective_from, effective_through, status,
superseded_by_identity, roll_continuity_authority, analytical_authority,
trading_authority, provenance, integrity_identity, policy_identity,
policy_version, schema_identity, schema_version,
base_schedule_contract_identity, base_schedule_contract_version,
derived_schedule_contract_identity, derived_schedule_contract_version,
previous_schedule_contract_identity, previous_schedule_contract_version,
base_serialized_schedule_sha256, derived_serialized_schedule_sha256,
previous_serialized_schedule_sha256
```

All fields are required. Except the exceptions below, all are nonempty strings:
- trading_date, previous_trading_date, effective_from, effective_through are
  canonical date strings; previous < trading and effective_from <= trading <=
  effective_through. The existing source-effective intersection remains required.
- analysis_boundary is canonical UTC with six fractional digits; source boundaries
  are canonical local timestamps (§5), each <= analysis_boundary.
- roll_continuity_authority, analytical_authority, trading_authority are exact
  JSON booleans **false** (runtime bool, not 0).
- provenance is a nonempty ordered string array; it participates in both hashes.
- superseded_by_identity is JSON null exactly when status="CURRENT"; for
  status="SUPERSEDED" it is a nonempty string naming the exact successor.
  No other null or omission is permitted.
- Every field ending _sha256 is lowercase 64-hex without a prefix.
- contract_family is GOLDM, SILVERM, COPPER, CRUDEOIL or NATURALGAS; exchange is
  MCX; market_identity is MCX_NON_AGRI; base_segment is FUTURES_NON_AGRI;
  derived_segment is MCX_FUTURES; timezone is Asia/Kolkata.
- derivation_relationship is exactly FAMILY_SPECIFIC_EXPIRY_SESSION_SPECIALIZATION.
  Schema and policy identities/versions are the exact strings in §1.
- Each of base/derived/previous_schedule_contract_identity and its version is
  exactly the pair KRONOS-MARKET-SCHEDULE-V1 / "1" or
  KRONOS-MARKET-SCHEDULE-V2 / "2", matching its retained normalized schedule.
  Unsupported/mixed unproved lineage is not silently accepted.

### 8.2 Preserve existing meanings, distinguish new hashes

Existing base_schedule_identity is the **source contract identity**, not the new
stable schedule hash: KRONOS-MARKET-CALENDAR-V1 or KRONOS-MARKET-CALENDAR-V2,
matching the base publication. derived_schedule_identity is the family-profile
source contract KRONOS-MCX-CONTRACT-FAMILY-SESSION-V1 or
KRONOS-MCX-CONTRACT-FAMILY-SESSION-V2, matching the exact profile. Associated
_schedule_version fields remain source publication versions, not contract
versions. The added _schedule_contract_* fields remove this legacy naming
ambiguity without changing V1 meaning.

base_session_identity names the base schedule for the current trading date.
The legacy base_session_sha256 binds the **previous** shared day schedule;
previous_session_identity also names that previous schedule. Preserve this
existing, potentially surprising meaning. derived_session_sha256 and
current_session_identity bind the current derived shared day schedule.
New base/derived/previous_serialized_schedule_sha256 fields bind the respective
complete normalized schedules, including their stable identities and observational
fields. No source/window/offset may be omitted from those payloads. V1 session
hashes use the existing V1 codec unchanged; V2 session hashes use §5.

The base publication fields name the official calendar; derived publication
fields name the unchanged official family-rule publication, not a fabricated
family calendar. A V2 family profile's publication_binding still names its base
calendar. All compatibility bindings are checked against these exact retained
objects, family, date, cutoff and source boundary before hashing/publishing.

Existing exact restoration, ADR-0048 compatibility restoration and separately
authorized material-successor commissioning remain distinct. Shared Intraday
serializers may gain explicit V2 dispatch only in authorized engineering; they
must restore V1 unchanged or reject unsupported V2. No accepted research record,
configuration, digest, pointer or epoch is rewritten. A changed capability proof
remains an operational review gate, not automatically approved by ADR-0056.

## 9. Exact failures, outcomes and diagnostic handling

### 9.1 States and complete reason mapping

The complete state enum is OWNED_ACTIVE, OWNED_GAP, BOUND_BEFORE_OPEN,
BOUND_COMPLETED, COMPLETED_EVIDENCE_BOUND, NO_OWNER, UNAVAILABLE, INVALID.
The first five are successful states with reason_code=null and phase=RESOLVED.
NO_OWNER is a normal negative lookup outcome, **not** an exception name. It has
reason_code=MARKET_SESSION_NO_CONTAINING_OWNER and phase=OWNERSHIP.
It requires complete validated C/C-1 coverage and no containing envelope.

The following table is the complete new reason enum; full strings are literal.
Rows are in deterministic precedence order within each phase.

| Phase | Exact reason_code | State if request admitted | Exact failing predicate |
| --- | --- | --- | --- |
| REQUEST_SHAPE | MARKET_SESSION_SHAPE_INVALID | INVALID | Missing/extra/duplicate key, wrong JSON/runtime type, malformed date/clock, noncanonical timestamp or enum |
| VERSION | MARKET_SESSION_VERSION_UNSUPPORTED | UNAVAILABLE | Well-typed discriminator tuple is not explicitly supported |
| REQUEST_TIME | MARKET_SESSION_QUERY_AFTER_AS_OF | INVALID | Ordinary/retained query > as_of |
| REQUEST_TIME | MARKET_SESSION_FUTURE_QUERY_REQUIRED | INVALID | FUTURE_SCHEDULE query <= as_of |
| SOURCE_INTEGRITY | MARKET_SESSION_INTEGRITY_MISMATCH | INVALID | Retained raw digest, recomputed identity or publication-resolved endpoint differs |
| SOURCE_INTEGRITY | MARKET_SESSION_SOURCE_UNAVAILABLE | UNAVAILABLE | Required source bytes absent or source_boundary > as_of |
| SOURCE_INTEGRITY | MARKET_SESSION_EXPIRY_AUTHORITY_UNAVAILABLE | UNAVAILABLE | Explicit MCX_FAMILY selection lacks exact applicable family expiry cutoff |
| ADJACENCY | MARKET_SESSION_ADJACENCY_INVALID | INVALID | Malformed/duplicate/branching/self edge, wrong relationship or coverage ordering |
| ADJACENCY | MARKET_SESSION_LINEAGE_MISMATCH | INVALID | Edge scope/calendar/schedule discriminator or exact referenced publication does not match |
| ADJACENCY | MARKET_SESSION_ADJACENCY_MISSING | UNAVAILABLE | Necessary adjacent edge or referenced manifest member absent |
| ENDPOINTS | MARKET_SESSION_OFFSET_INVALID | INVALID | Offset not exact integer 0/1, or first open offset != 0 |
| ENDPOINTS | MARKET_SESSION_LOCAL_TIME_UNRESOLVED | INVALID | Timezone unsupported, nonexistent/ambiguous local endpoint, or naive runtime datetime |
| CHRONOLOGY | MARKET_SESSION_CHRONOLOGY_INVALID | INVALID | Nonpositive UTC interval or source window ordering invalid |
| CHRONOLOGY | MARKET_SESSION_WINDOW_OVERLAP | INVALID | Two active windows overlap for competing owners or within one owner |
| OWNERSHIP | MARKET_SESSION_OWNER_CONFLICT | INVALID | Conflicting session envelopes/identities or overlapping publication ownership coverage |
| OWNERSHIP | MARKET_SESSION_OWNER_MISMATCH | INVALID | Supplied owner date/session/publication/window binding does not identify the retained owner |
| OWNERSHIP | MARKET_SESSION_COVERAGE_INCOMPLETE | UNAVAILABLE | Required date has neither valid trading entry nor explicit non-trading declaration |
| OWNERSHIP | MARKET_SESSION_NO_CONTAINING_OWNER | NO_OWNER | C/C-1 fully covered, neither envelope contains query; no inferred holiday |
| COMPLETION | MARKET_SESSION_INTERVAL_INVALID | INVALID | query_instant != completed_interval.source_start, retained interval wrong anchor/window, start >= end, end != governed constituent end, or bridges gap |
| COMPLETION | MARKET_SESSION_INTERVAL_NOT_COMPLETED | INVALID | Otherwise valid constituent end > as_of |
| CONSUMER_AUTHORITY | MARKET_SESSION_DAILY_LABEL_UNSUPPORTED | UNAVAILABLE | Provider DAY date-label authority not established |

The CONSUMER_AUTHORITY DAY reason is produced only at the existing DAY consumer
boundary using the same safe diagnostic shape, not by pretending the 1H-only
resolver accepts DAY requests. The family-expiry source reason is also available
when the explicit resolver schedule_selection cannot derive its governed schedule.
NO_OWNER is only emitted by UNBOUND_TIMESTAMP; a bound tuple purporting to own a
declared non-trading date is MARKET_SESSION_OWNER_MISMATCH, not an invented session.

### 9.2 Precedence and outer exceptions

Validation executes the phases above in table order, stopping at the first
failing phase. Shape/type dispatch precedes value-version dispatch. Within a
phase use row order, then canonical field path lexicographic order, then trading
date and source window ordinal; never file enumeration or hash-map iteration.
Offset fields are reserved for ENDPOINTS validation, and naive datetime/timezone
resolution for ENDPOINTS, not the generic shape row. This preserves their
specific diagnostics. Request required/forbidden fields are admitted before
temporal predicates; malformed requests never enter Q/R hashing. A source
which cannot be read cannot have its unseen contents diagnosed. Required source
availability is established before dependent digest/chronology checks; among
readable sources a verified mismatch takes precedence over an absent peer.
No later NO_OWNER/OPEN/CLOSED result may replace an earlier failure.
Coverage-overlap ownership validation in a manifest occurs in OWNERSHIP after
edge integrity and chronology; valid coverage is required before query resolution.

V2 public parser/constructor boundaries are ValueError (or a subclass), with
the following exact str(exception) outer code; a separate reason is not appended
to the string. Raw library errors are caught and sanitized.

| Boundary | Exact outer exception string on rejection |
| --- | --- |
| Official V2 publication parser | MARKET_CALENDAR_PUBLICATION_INVALID |
| V4 manifest parser/constructor | MARKET_CALENDAR_MANIFEST_INVALID |
| V2 shared/normalized schedule constructor | MARKET_SCHEDULE_INVALID |
| V2 window constructor | MARKET_SESSION_WINDOW_INVALID |
| V2 MCX family profile constructor | MCX_CONTRACT_FAMILY_SESSION_PROFILE_INVALID |
| V2 compatibility parser/constructor | MARKET_SCHEDULE_COMPATIBILITY_INVALID |
| Resolver request rejected before admission | MARKET_SESSION_RESOLUTION_REQUEST_INVALID |

An admitted resolver request returns INVALID/UNAVAILABLE/NO_OWNER instead of
throwing these expected validation exceptions. Failure of result self-integrity
raises ValueError("MARKET_SESSION_RESOLUTION_RESULT_INVALID") and returns no
trusted result. This is an invariant failure, not a fabricated schedule outcome.

All V1 functions retain **every existing exception class/string and dispatch
behavior exactly**, including their more specific existing source/digest/
unavailable errors. The V2 outer mapping does not replace V1 error paths.
Legacy non-prefixed internal ValueError behavior is likewise not rewritten.

### 9.3 Diagnostics and persistence

A rejected V2 parser/constructor/request exposes only this in-memory diagnostic
map: {outer_code, reason_code, phase, field_path}. All fields are strings except
field_path may be null for no attributable input path. Paths refer only to closed
schema keys and numeric array ordinals, never raw received values or filesystem
paths. Codes/phases are those above; no exception stack/provider token is part
of the contract. A result-integrity error uses reason_code
MARKET_SESSION_INTEGRITY_MISMATCH and phase SOURCE_INTEGRITY.

The resolver/parsers perform **no diagnostic persistence and no evidence writes**.
A successful result can be included by an explicitly versioned existing caller
in its normal evidence artifact, with exact Q, R and source bytes/bindings retained
for replay. Failure diagnostics are in-memory-only under this proposal; adding
durable failure records requires a separate approved storage contract. Do not
add logs, files, tables or lifecycle events merely to retain these diagnostics.

## 10. Approval and implementation gate

See [acceptance plan](../products/swing/WO-SWING-03A-CONTRACT-CONSUMERS-AND-ACCEPTANCE.md).
The exact Proposal 3 successor identifiers, fields and failure taxonomy above
were approved by Chief Architect / DOMAIN-008 on 2026-09-14. This contract adds no production schedule, API route,
retrieval, market hours, analytical predicate or execution authority.

## 11. Exact adjacent-publication manifest contract

### 11.1 Manifest V4 and exact relationship

The V4 root has exactly schema, publications, session_regimes,
subject_session_applicabilities, mcx_contract_family_sessions and
adjacent_publications. Existing collection item shapes remain unchanged:
publication references are exact {file, sha256}, repository-relative safe paths
under the configured calendar root, with raw lowercase 64-hex digest. No path
escape, absolute path, symlink escape or network retrieval. Existing V1-only
manifest V3 bytes and cardinality rules remain unchanged.

V4 publications may contain the multiple V2 coverage intervals needed for
explicit adjacency, plus unchanged V1 sources for other scopes. This relaxes
the old V3 two-publication cardinality **only for V4**, not the V1 parser.
Other collections retain existing validation and cardinality. V4 is an immutable
retained snapshot, not a directory scan or mutable "latest" lookup.

adjacent_publications is an ordered array (possibly empty), each element exactly:
{predecessor, successor, scope, calendar_identity, schedule_contract_identity,
schedule_contract_version}. predecessor and successor are the full six-field
publication_binding objects in §4. scope is the exact four-string map in §6.
calendar_identity must equal both references' calendar_identity;
schedule_contract_identity/version are exactly KRONOS-MARKET-SCHEDULE-V2 / "2".
Both endpoint references must be V2 publication discriminators from §1.

Each binding must resolve to exactly one publications member after its file
digest and parsed identity/version have been verified; matching by filename or
calendar name alone is forbidden. Each endpoint has at most one predecessor
and one successor in its exact scope/lineage. Reject duplicate edges, forks,
cycles, self-links or a fabricated binding/digest. Relation order is predecessor
coverage_start then successor coverage_start (ascending dates); not version sort.
There is no new adjacency identity: the exact relation is sealed by the retained
manifest raw-byte SHA in every request.

### 11.2 Lineage, dates, conflicts and proof requirement

An edge is lawful only if both parsed publications have identical market_identity,
exchange, segment, timezone and calendar_identity, matching the edge, and both
normalize to the stated V2 schedule contract. calendar_version values are opaque,
distinct strings, with exact digest bindings. They do not determine chronology.
predecessor.coverage_end + one calendar day == successor.coverage_start.
Coverage spans are the authoritative effective-date intervals for this relation.
The predecessor source_boundary must be <= successor source_boundary; both must
be <= request as_of when used. No extra effective-date field is inferred.

Within the selected scope/lineage, overlapping coverage intervals, competing
versions of an interval, or cross-publication envelope overlap are rejected,
not selected by load order or newest version. A historical replacement is a
different retained manifest; do not put competing versions into this active
lineage. Multiple disjoint scopes (including governed family specialization)
are not conflicts; their selection must already be bound, never guessed.
No V1↔V2 adjacency edge is authorized here. A required mixed edge fails version
validation; preserving V1 same-day behavior does not prove a V2 predecessor safe.

For an unbound query use C and C-1. If either date is outside the selected
publication, traverse the **declared edge** towards that date, using only exact
retained manifest members, until its partition entry is found. A missing needed
edge/member gives MARKET_SESSION_ADJACENCY_MISSING; unreadable referenced bytes
give MARKET_SESSION_SOURCE_UNAVAILABLE; missing date inside verified coverage
gives MARKET_SESSION_COVERAGE_INCOMPLETE. A declared non-trading entry is valid
coverage. No empty lookback is inferred at a year boundary or first retained date.
Bound-owner lookup does not rebind across an edge. For a trading owner D, its
conflict proof needs D-1 and also D+1 when the owner's final endpoint has day
offset 1. An endpoint exactly at D+1 00:00 cannot overlap an offset-0 D+1 opening,
so D+1 proof is not required in that one case. These are the only neighboring
dates needed under the 0/1 and first-open=0 rule. Missing required neighboring
proof is UNAVAILABLE, even when the queried owner's own windows are present.

### 11.3 Exact validation phase

At V4 load, before the publisher becomes usable: parse closed shapes/versions,
verify every referenced raw digest, verify relationship scope/lineage and
effective ordering, resolve UTC endpoints, then check window/envelope and
coverage ownership conflicts. Thus even a conflict not covering today's query
cannot hide in a successfully loaded manifest. Missing optional external history
is not invented; a missing edge is assessed when a query actually needs it.

At request resolution: verify the exact retained manifest/binding selection and
as_of admissibility, locate required C/C-1 or bound-owner entries, require any
needed adjacency proof, and only then resolve query ownership/completion.
At restoration: repeat load validation on retained bytes, recompute identities
and revalidate request as_of; never substitute today's manifest or corrected
calendar. Failure precedence and safe outcomes are exactly §9. No production
publication, manifest migration or historical rewrite is performed by this proposal.

## 12. Documentary golden identity vectors

All examples below are **synthetic hash inputs**, not official calendar facts,
not executable implementation and not proof of source admission. Repeated
hexadecimal source digests are explicit fixture values, not real file digests.
The NO_OWNER vector assumes prior coverage has already been checked; it tests
serialization of a result, not the correctness of its unseen source partition.
Compatibility vectors test the exact K map, not commissioning a GOLDM session.

Each canonical_input is complete for its named hash map, with no ellipsis,
implicit field or default. Apply §5 C/H and the indicated prefix; expected_identity
is the literal required output. R-integrity and K-integrity include the respective
primary identity and exclude their own integrity field.

The two complete stable_identity_projections intentionally differ in as_of and
market_availability. Project each onto exactly S's keys before hashing: **both
must yield the same expected S identity**. Hashing either entire projection is
incorrect for schedule identity (but appropriate for its separate serialized
schedule digest). No observation-specific schedule identity is authorized.

```json
{
  "vectors": [
    {
      "name": "W-window",
      "canonical_input": {
        "publication_binding": {
          "schema": "KRONOS-MARKET-CALENDAR-PUBLICATION-V2",
          "contract_identity": "KRONOS-MARKET-CALENDAR-V2",
          "contract_version": "2",
          "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
          "calendar_version": "TEST.2",
          "publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "trading_date": "2026-09-14",
        "session_identity": "SYNTHETIC-MCX-2026-09-14",
        "order": 1,
        "window_open": "2026-09-14T23:00:00+05:30",
        "window_close": "2026-09-15T01:00:00+05:30",
        "open_day_offset": 0,
        "close_day_offset": 1
      },
      "expected_identity": "MARKET-WINDOW-V2-4dd542a6e51b89f695ff748378911300ec6636f14e09f10b9351164ebc3067e2"
    },
    {
      "name": "S-stable-schedule",
      "canonical_input": {
        "contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "contract_version": "2",
        "market_identity": "MCX_NON_AGRI",
        "exchange": "MCX",
        "trading_date": "2026-09-14",
        "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
        "calendar_version": "TEST.2",
        "session_identity": "SYNTHETIC-MCX-2026-09-14",
        "session_type": "SYNTHETIC_VALIDATION",
        "timezone": "Asia/Kolkata",
        "source_identity": "KRONOS-MARKET-CALENDAR-V2",
        "source_boundary": "2026-09-01T00:00:00+05:30",
        "publication_binding": {
          "schema": "KRONOS-MARKET-CALENDAR-PUBLICATION-V2",
          "contract_identity": "KRONOS-MARKET-CALENDAR-V2",
          "contract_version": "2",
          "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
          "calendar_version": "TEST.2",
          "publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "windows": [
          {
            "order": 1,
            "window_open": "2026-09-14T23:00:00+05:30",
            "window_close": "2026-09-15T01:00:00+05:30",
            "open_day_offset": 0,
            "close_day_offset": 1,
            "identity": "MARKET-WINDOW-V2-4dd542a6e51b89f695ff748378911300ec6636f14e09f10b9351164ebc3067e2"
          }
        ],
        "provenance": [
          "SYNTHETIC-MCX-CALENDAR:TEST.2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ]
      },
      "expected_identity": "MARKET-SCHEDULE-V2-e42a00a7f7e1f9a5c999ffe732a02bb2732b70253975c6e932bd5f3753c77c0a"
    },
    {
      "name": "Q-resolver-request",
      "canonical_input": {
        "schema_identity": "KRONOS-MARKET-SESSION-RESOLUTION-REQUEST-V1",
        "schema_version": "1",
        "mode": "UNBOUND_TIMESTAMP",
        "purpose": "OBSERVATION_AS_OF",
        "scope": {
          "market_identity": "MCX_NON_AGRI",
          "exchange": "MCX",
          "segment": "FUTURES_NON_AGRI",
          "timezone": "Asia/Kolkata"
        },
        "manifest_binding": {
          "schema": "KRONOS-MARKET-CALENDAR-MANIFEST-V4",
          "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        },
        "publication_binding": {
          "schema": "KRONOS-MARKET-CALENDAR-PUBLICATION-V2",
          "contract_identity": "KRONOS-MARKET-CALENDAR-V2",
          "contract_version": "2",
          "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
          "calendar_version": "TEST.2",
          "publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "query_instant": "2026-09-14T16:00:00.000000+00:00",
        "as_of": "2026-09-14T16:00:00.000000+00:00",
        "schedule_selection": {
          "kind": "BASE_CALENDAR"
        }
      },
      "expected_identity": "MARKET-SESSION-REQUEST-V1-4edc22e0eb817f5fa564ddea683425631a47c83dbb7cc6614a61e7ef8ad83f74"
    },
    {
      "name": "R-resolver-result",
      "canonical_input": {
        "schema_identity": "KRONOS-MARKET-SESSION-RESOLUTION-V1",
        "schema_version": "1",
        "request_identity": "MARKET-SESSION-REQUEST-V1-4edc22e0eb817f5fa564ddea683425631a47c83dbb7cc6614a61e7ef8ad83f74",
        "query_instant": "2026-09-14T16:00:00.000000+00:00",
        "as_of": "2026-09-14T16:00:00.000000+00:00",
        "temporal_use": "AS_OF_SCHEDULE",
        "state": "NO_OWNER",
        "reason_code": "MARKET_SESSION_NO_CONTAINING_OWNER",
        "phase": "OWNERSHIP",
        "owner": null,
        "schedule": null,
        "window": null,
        "interval_completion_validated": false,
        "provenance": [
          "SYNTHETIC-MCX-CALENDAR:TEST.2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ]
      },
      "expected_identity": "MARKET-SESSION-RESOLUTION-V1-590f77cfa3622120d68e210e83b5c85ffa626dcdf4a56adedfaeca64f731b836"
    },
    {
      "name": "R-integrity",
      "canonical_input": {
        "schema_identity": "KRONOS-MARKET-SESSION-RESOLUTION-V1",
        "schema_version": "1",
        "request_identity": "MARKET-SESSION-REQUEST-V1-4edc22e0eb817f5fa564ddea683425631a47c83dbb7cc6614a61e7ef8ad83f74",
        "query_instant": "2026-09-14T16:00:00.000000+00:00",
        "as_of": "2026-09-14T16:00:00.000000+00:00",
        "temporal_use": "AS_OF_SCHEDULE",
        "state": "NO_OWNER",
        "reason_code": "MARKET_SESSION_NO_CONTAINING_OWNER",
        "phase": "OWNERSHIP",
        "owner": null,
        "schedule": null,
        "window": null,
        "interval_completion_validated": false,
        "provenance": [
          "SYNTHETIC-MCX-CALENDAR:TEST.2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ],
        "resolution_identity": "MARKET-SESSION-RESOLUTION-V1-590f77cfa3622120d68e210e83b5c85ffa626dcdf4a56adedfaeca64f731b836"
      },
      "expected_identity": "INTEGRITY-MARKET-SESSION-RESOLUTION-V1-affe2b64605ea667cd96bcede5abef78146f0015e11716f815a86f0aa7871bb1"
    },
    {
      "name": "K-compatibility",
      "canonical_input": {
        "contract_family": "GOLDM",
        "exchange": "MCX",
        "market_identity": "MCX_NON_AGRI",
        "base_segment": "FUTURES_NON_AGRI",
        "derived_segment": "MCX_FUTURES",
        "timezone": "Asia/Kolkata",
        "trading_date": "2026-09-14",
        "previous_trading_date": "2026-09-13",
        "analysis_boundary": "2026-09-14T16:00:00.000000+00:00",
        "current_session_identity": "SYNTHETIC-GOLDM-2026-09-14",
        "previous_session_identity": "SYNTHETIC-MCX-2026-09-13",
        "base_session_identity": "SYNTHETIC-MCX-2026-09-14",
        "base_session_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "base_schedule_identity": "KRONOS-MARKET-CALENDAR-V2",
        "base_schedule_version": "TEST.2",
        "base_publication_identity": "SYNTHETIC-MCX-CALENDAR",
        "base_publication_version": "TEST.2",
        "base_publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "base_source_boundary": "2026-09-01T00:00:00+05:30",
        "derived_schedule_identity": "KRONOS-MCX-CONTRACT-FAMILY-SESSION-V2",
        "derived_schedule_version": "FAMILY.TEST.1",
        "derived_session_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "derived_publication_identity": "SYNTHETIC-MCX-FAMILY-RULES",
        "derived_publication_version": "FAMILY.TEST.1",
        "derived_publication_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "derived_source_boundary": "2026-09-01T00:00:00+05:30",
        "derivation_relationship": "FAMILY_SPECIFIC_EXPIRY_SESSION_SPECIALIZATION",
        "effective_from": "2026-09-01",
        "effective_through": "2026-09-30",
        "status": "CURRENT",
        "superseded_by_identity": null,
        "roll_continuity_authority": false,
        "analytical_authority": false,
        "trading_authority": false,
        "provenance": [
          "ADR-0028",
          "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
          "SYNTHETIC-FAMILY-RULE"
        ],
        "policy_identity": "KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V2",
        "policy_version": "2.0.0",
        "schema_identity": "KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V2",
        "schema_version": "2.0.0",
        "base_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "base_schedule_contract_version": "2",
        "derived_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "derived_schedule_contract_version": "2",
        "previous_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "previous_schedule_contract_version": "2",
        "base_serialized_schedule_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "derived_serialized_schedule_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
        "previous_serialized_schedule_sha256": "2222222222222222222222222222222222222222222222222222222222222222"
      },
      "expected_identity": "MARKET-SCHEDULE-COMPATIBILITY-V2-4ca74ed5dae7cd41c8dfe8d069e35477e8d7a8eb4935f13d9567d18443b02142"
    },
    {
      "name": "K-integrity",
      "canonical_input": {
        "contract_family": "GOLDM",
        "exchange": "MCX",
        "market_identity": "MCX_NON_AGRI",
        "base_segment": "FUTURES_NON_AGRI",
        "derived_segment": "MCX_FUTURES",
        "timezone": "Asia/Kolkata",
        "trading_date": "2026-09-14",
        "previous_trading_date": "2026-09-13",
        "analysis_boundary": "2026-09-14T16:00:00.000000+00:00",
        "current_session_identity": "SYNTHETIC-GOLDM-2026-09-14",
        "previous_session_identity": "SYNTHETIC-MCX-2026-09-13",
        "base_session_identity": "SYNTHETIC-MCX-2026-09-14",
        "base_session_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "base_schedule_identity": "KRONOS-MARKET-CALENDAR-V2",
        "base_schedule_version": "TEST.2",
        "base_publication_identity": "SYNTHETIC-MCX-CALENDAR",
        "base_publication_version": "TEST.2",
        "base_publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "base_source_boundary": "2026-09-01T00:00:00+05:30",
        "derived_schedule_identity": "KRONOS-MCX-CONTRACT-FAMILY-SESSION-V2",
        "derived_schedule_version": "FAMILY.TEST.1",
        "derived_session_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "derived_publication_identity": "SYNTHETIC-MCX-FAMILY-RULES",
        "derived_publication_version": "FAMILY.TEST.1",
        "derived_publication_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "derived_source_boundary": "2026-09-01T00:00:00+05:30",
        "derivation_relationship": "FAMILY_SPECIFIC_EXPIRY_SESSION_SPECIALIZATION",
        "effective_from": "2026-09-01",
        "effective_through": "2026-09-30",
        "status": "CURRENT",
        "superseded_by_identity": null,
        "roll_continuity_authority": false,
        "analytical_authority": false,
        "trading_authority": false,
        "provenance": [
          "ADR-0028",
          "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
          "SYNTHETIC-FAMILY-RULE"
        ],
        "policy_identity": "KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V2",
        "policy_version": "2.0.0",
        "schema_identity": "KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V2",
        "schema_version": "2.0.0",
        "base_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "base_schedule_contract_version": "2",
        "derived_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "derived_schedule_contract_version": "2",
        "previous_schedule_contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
        "previous_schedule_contract_version": "2",
        "base_serialized_schedule_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "derived_serialized_schedule_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
        "previous_serialized_schedule_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
        "compatibility_identity": "MARKET-SCHEDULE-COMPATIBILITY-V2-4ca74ed5dae7cd41c8dfe8d069e35477e8d7a8eb4935f13d9567d18443b02142"
      },
      "expected_identity": "INTEGRITY-MARKET-SCHEDULE-COMPATIBILITY-V2-c2a02af04937d618224a2c8fdb3fdbd4f4ca0c075a6ed9bf8b9be6c9e249b674"
    }
  ],
  "stable_identity_projections": [
    {
      "contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
      "contract_version": "2",
      "market_identity": "MCX_NON_AGRI",
      "exchange": "MCX",
      "trading_date": "2026-09-14",
      "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
      "calendar_version": "TEST.2",
      "session_identity": "SYNTHETIC-MCX-2026-09-14",
      "session_type": "SYNTHETIC_VALIDATION",
      "timezone": "Asia/Kolkata",
      "source_identity": "KRONOS-MARKET-CALENDAR-V2",
      "source_boundary": "2026-09-01T00:00:00+05:30",
      "publication_binding": {
        "schema": "KRONOS-MARKET-CALENDAR-PUBLICATION-V2",
        "contract_identity": "KRONOS-MARKET-CALENDAR-V2",
        "contract_version": "2",
        "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
        "calendar_version": "TEST.2",
        "publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      },
      "windows": [
        {
          "order": 1,
          "window_open": "2026-09-14T23:00:00+05:30",
          "window_close": "2026-09-15T01:00:00+05:30",
          "open_day_offset": 0,
          "close_day_offset": 1,
          "identity": "MARKET-WINDOW-V2-4dd542a6e51b89f695ff748378911300ec6636f14e09f10b9351164ebc3067e2"
        }
      ],
      "provenance": [
        "SYNTHETIC-MCX-CALENDAR:TEST.2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ],
      "identity": "MARKET-SCHEDULE-V2-e42a00a7f7e1f9a5c999ffe732a02bb2732b70253975c6e932bd5f3753c77c0a",
      "session_open": "2026-09-14T23:00:00+05:30",
      "session_close": "2026-09-15T01:00:00+05:30",
      "as_of": "2026-09-14T16:00:00.000000+00:00",
      "market_availability": "PRE_OPEN",
      "freshness_status": "CURRENT",
      "integrity_status": "VALID"
    },
    {
      "contract_identity": "KRONOS-MARKET-SCHEDULE-V2",
      "contract_version": "2",
      "market_identity": "MCX_NON_AGRI",
      "exchange": "MCX",
      "trading_date": "2026-09-14",
      "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
      "calendar_version": "TEST.2",
      "session_identity": "SYNTHETIC-MCX-2026-09-14",
      "session_type": "SYNTHETIC_VALIDATION",
      "timezone": "Asia/Kolkata",
      "source_identity": "KRONOS-MARKET-CALENDAR-V2",
      "source_boundary": "2026-09-01T00:00:00+05:30",
      "publication_binding": {
        "schema": "KRONOS-MARKET-CALENDAR-PUBLICATION-V2",
        "contract_identity": "KRONOS-MARKET-CALENDAR-V2",
        "contract_version": "2",
        "calendar_identity": "SYNTHETIC-MCX-CALENDAR",
        "calendar_version": "TEST.2",
        "publication_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      },
      "windows": [
        {
          "order": 1,
          "window_open": "2026-09-14T23:00:00+05:30",
          "window_close": "2026-09-15T01:00:00+05:30",
          "open_day_offset": 0,
          "close_day_offset": 1,
          "identity": "MARKET-WINDOW-V2-4dd542a6e51b89f695ff748378911300ec6636f14e09f10b9351164ebc3067e2"
        }
      ],
      "provenance": [
        "SYNTHETIC-MCX-CALENDAR:TEST.2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      ],
      "identity": "MARKET-SCHEDULE-V2-e42a00a7f7e1f9a5c999ffe732a02bb2732b70253975c6e932bd5f3753c77c0a",
      "session_open": "2026-09-14T23:00:00+05:30",
      "session_close": "2026-09-15T01:00:00+05:30",
      "as_of": "2026-09-14T18:00:00.000000+00:00",
      "market_availability": "OPEN",
      "freshness_status": "CURRENT",
      "integrity_status": "VALID"
    }
  ]
}
```
