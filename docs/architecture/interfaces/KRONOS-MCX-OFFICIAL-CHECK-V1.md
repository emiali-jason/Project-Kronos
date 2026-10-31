# KRONOS MCX Official Check V1

Status: S3.03 exact-source candidate for CA review. This is a non-authoritative check-and-stage
interface. It does not publish, approve, activate, install, or trade.

## Boundary

`McxOfficialCheckEngine` owns one dormant, single-flight checker for the five
supported MCX option families: GOLDM, SILVERM, COPPER, CRUDEOIL and NATURALGAS.
It checks the five fixed official product pages and the Trading & Surveillance
circular index, follows only bounded HTTPS redirects on `www.mcxindia.com` or
`classic.mcxindia.com`, and downloads documents only below `/docs/`. Product
discovery retains links from the intended family section (or an explicitly
family-labelled unsectioned link); it does not assign every PDF on a mixed
product page to that family. Circular discovery includes both family-labelled
records and potentially governing market-wide launch calendars, expiry/trading
calendars, session/timing records, holidays and amendments even when the title
contains no family name.

Transport is dependency-injected. Every request carries the fixed connect/read,
redirect, and size bounds. A page must be complete HTML. A circular scan must
carry explicit page number/count/item-count/next-page observations and complete
inclusive circular ranges whose union has no gap. The response's recorded
request URL must exactly equal the request issued by the checker. A document must be a
bounded `application/pdf` payload with a PDF header and terminal envelope.
Failure of any required page, range, redirect, or document makes that attempt
FAILED; it can never produce CURRENT.

`OfficialHttpsTransport` performs one verified-TLS HTTPS GET per call with
identity encoding, bounded connect/read timeout, capped body read and explicit
connection closure. It performs no hidden redirect, retry or browser operation.
The engine validates and follows each permitted Location itself, counting every
actual exchange and response byte against the same original whole-check scope.
Timeouts are capped by that scope's remaining duration. Every real-transport
response, including redirect/denial bodies, is retained privately by exact hash;
a failed immutable receipt records its requests, response objects and incomplete
disposition. No failed response becomes active publication evidence.

Official evidence captured 28 October 2026 shows Sitefinity product sections
and sibling `item-link-*` contract accordions. The parser associates those links
with the preceding exact family section and excludes separate Mini sections
for full-size energy families. Browser-rendered DOM evidence is labelled as
such; it is not represented as raw HTTP response evidence.

The direct client currently receives Akamai HTTP 403 for all six source URLs.
Chrome can render the official circular table, whose `href="#"`/`data-page`
controls and date filters do not establish a verified HTTP continuation or
complete range. No official API endpoint/response contract has been verified.
The current transport therefore marks that circular source incomplete even if
HTML becomes reachable; it does not fabricate page/range facts. An operational
successful live whole check remains unavailable until this exact source
interface can be observed and qualified. This limitation is an explicit FAILED
checker outcome and cannot be hidden by a synthetic test success.

One check is bounded as a whole, not merely per request: at most 64 requests,
48 distinct document requests, 100 MiB of response bytes, 10 circular-index
pages and 45 seconds are allowed by the V1 defaults. Exhaustion, contradictory
pagination, a repeated page or uncertain completeness fails closed. Receipts
retain the complete discovery inputs, response identities, redirect lists,
page/range facts, link classifications and observed resource totals. These
classifications establish potential relevance only; they are not semantic or
publication approval.

The duration limit establishes one original monotonic deadline when the attempt
starts. The checker reobserves that same deadline after candidate validation,
after immutable-receipt persistence, after mutable-status persistence and
immediately before accepting success. An observation at or after the deadline
is `MCX_CHECK_DEADLINE_EXPIRED`; phases do not receive renewed limits. A late
attempt cannot update last-success or the last accepted receipt. Objects and an
immutable receipt already committed by the attempt remain untouched, and the
terminal FAILED status links any such receipt as `attempt_receipt_sha256` for
audit. A blocked write is not claimed interrupted: its existing durable-write
and worker ownership remain observable until the operation actually returns.
This whole-check deadline is separate from the shutdown `ValidationBudget`.

Circular continuation is a separate constrained interface. Every next-page URL
must remain on an approved MCX host, use the exact all-circulars index path and
carry only the expected `page=N` pagination form for the immediately following
page. A product URL or another approved page cannot serve as circular
pagination, even when its supplied page/range metadata looks consistent.

Discovery establishes only that bytes are potentially relevant. The checker
does not infer contract dates, option-to-future mapping, holidays, session
endpoints, publication approval, or Sponsor approval from a document.

## Immutable stage and receipts

The store root is an absolute private directory. Symlinked components and
group/world permissions are denied. Exact payloads are retained as mode-0600
`objects/<sha256>` files. Identical bytes are deduplicated; every successful
check still receives a distinct immutable canonical-JSON receipt containing
source/final URLs, retrieval time, size, hash, circular range, and the explicit
`semantic_mapping_approved: false` statement. Earlier objects remain when a URL
changes.

Every object, receipt and atomic document uses an explicit complete-write loop.
Zero-length, invalid and short writes are not acknowledged. The checker verifies
the exact bytes through a no-follow file descriptor after file `fsync` and
directory `fsync`; atomic documents are also verified before and after replace.
Configuration and status are canonical JSON written through a private temporary
file, `fsync`, atomic replace, and directory `fsync`. Partial or uncertain bytes
remain retained and unresolved; they are never labelled as successful objects,
receipts or status. On a later explicit activation, regular private temporary
files are removed; a symlink or non-regular recovery artifact denies activation.
The engine never writes tracked publications, `current.json`, official source
directories, review records, or static production pins.

Each immutable receipt binds the exact active Instrument reference, Market
reference and current-pointer digest used for comparison. It also retains enough
page, pagination, circular-range and classified-link evidence to audit why the
attempt called discovery complete. Identical payload objects remain deduplicated,
but no source URL, family classification or check history is discarded.

The exact HTML bytes of every product and circular-index response are themselves
retained as private immutable objects. Each observation binds its response hash
to that retained-object hash and labels it `DISCOVERY_PAGE`. The receipt can be
audited later with `retained_discovery_pages()` without a network refetch;
missing, changed, malformed or corrupt receipt/object evidence denies readback.
Discovery-page objects are logically separate from the PDF/source-document set
compared with active Instrument authority. A changed HTML page creates retained
history and a new receipt but cannot, by itself, manufacture UPDATE AVAILABLE.

## Status semantics

Checker health and active-authority health are separate:

- **CURRENT**: the complete check succeeded inside its original whole-check
  deadline and every retained document hash is already present in the active
  approved Instrument source roster.
- **UPDATE AVAILABLE**: the complete check retained at least one new exact byte
  object, but there is no mechanically complete reader-validated candidate.
- **AWAITING REVIEW**: a separately supplied staged candidate was loaded by the
  existing `OwnerOptionAuthority` Instrument/Market readers. This says the
  candidate is structurally valid; it does not approve or activate it.
- **FAILED**: a required source, transport, range, validation, or durable-write
  operation failed. The last successful check is retained separately.

A downloaded PDF alone never produces AWAITING REVIEW. The active authority is
never replaced by a staged candidate.

For each family, coverage reports E1/E2, approved complete-roster count, eligible
count, authority health, and the first instant at which fewer than two eligible
expiries or governing authority/calendar coverage remains. The boundary is
derived from the complete approved roster and the governing authority end, not
from displayed E2 alone. Warnings are NONE, 30 DAYS, 14 DAYS, 7 DAYS, or
UNAVAILABLE. The approved S3.01 roster yields the shared earliest boundary
CRUDEOIL at 2026-11-17T23:55:00+05:30.

## Lifecycle and cleanup

Construction performs no network request, scheduling, or filesystem write.
Canonical composition registers the same dormant checker in `_StartupCleanup`
before binding or activation side effects, binds the actual server maintenance
coordinator and exact adopted `AdmissionCustody`, then retains that object.
`activate_from_canonical()` requires the same actual custody instance after
the existing `release_ready()` has returned, its descriptor observed closed,
cleanup not started, genuine READY/INACTIVE governance, a live listener and
the matching durable startup receipt. It validates that receipt's actual bytes
and original budget before and after activation. No release receipt is
fabricated: admission currently proves close-only release through its actual
object/descriptor state, while the digest binds those observations and the
existing READY receipt. The existing library `ActivationEvidence` seam remains
available for isolated embedding tests; canonical startup does not use it.

DAILY is the default frequency; EVERY THREE DAYS and WEEKLY are supported. Check
now and scheduled checks use one ownership slot and one worker generation. The
runner must return the exact started `Thread`; the checker retains its handle and
identity. Callback completion, a zero counter or an event alone is not worker
termination. Cleanup joins and observes that exact thread within the original
deadline. A late observation cannot be reported as timely, and runner launch
failure retains unknown ownership rather than guessing that no descendant exists. A
maintenance coordinator, when bound before activation, admits the worker under
the existing HOUSEKEEPING class. New work is denied after drain, close, runner
activation failure, or maintenance fencing.

Automatic checking on/off and frequency are private atomic preferences restored
on activation. Off suppresses scheduled checks but leaves Check now available.
First/overdue work is due only after canonical activation. Restart due time is
derived from retained last-attempt UTC plus frequency, rather than the restart
time; repeated restarts cannot keep postponing a check. The existing server
pulse invokes `trigger_scheduled()` and shares the same single-flight slot with
manual POST work. No new scheduler thread or pre-READY timer is created.

Canonical activation retains UX10, WO-13 and K5 ordering after custody release,
then activates the checker and submits any due work. The new cleanup slot is
closed once using the caller's original absolute cleanup deadline. Startup
failure reuses the exact original custody budget when that deadline applies;
governed shutdown uses its existing passed absolute deadline. The slot proves
the actual returned worker/durable-work outcome before domain final proof.
Unknown launch or unfinished write/operation remains unresolved.

The failure latch is checked again at the actual callback-entry boundary, before
maintenance activation or checking. A callback queued by a runner that then
fails performs no source check when it later enters. Runner transition failures,
including `KeyboardInterrupt` and cancellation derived directly from
`BaseException`, latch failure and propagate the exact original exception object;
they are never converted to a successful return or swallowed. Unknown launch
ownership remains unresolved, while already committed objects and receipts are
not rolled back.

Activation and configuration changes reserve an entered lifecycle operation
before any clock or filesystem side effect. Drain/close fences unentered work and
waits for entered operations within the same cleanup budget, so close cannot
report completion while a reserved operation may still write. Filesystem and
network blocking remain outside the execution-state lock. The activation try
boundary includes store recovery, durable configuration, clock evaluation and
final state publication; any exception preserves its original type/message while
permanently fencing later work. A close race cancels activation before ACTIVE can
be published.

Cleanup takes the existing `ValidationBudget` object and waits only to its
original absolute monotonic deadline. It never renews the deadline. A live owned
worker, unfinished durable write, or unknown write ownership returns UNRESOLVED.
The inherited budget uses its exact `observed >= deadline` expiry rule for both
thread-termination observation and final cleanup acknowledgement. After all
terminal ownership checks, cleanup checks the same budget once more immediately
before reporting CLOSED. Completion observed exactly at, or later than, expiry
therefore remains UNRESOLVED; no retry or replacement budget is created.
Application cleanup disposition is therefore distinct from fixture/process
teardown. Cleanup reports entered operations, exact worker identity and observed
termination disposition as separate evidence.

## Settings integration and remaining gates

The Market Calendar card exposes on/off, frequency, Check now, pending/running,
last attempt/success, next scheduled check, sanitized failure, checker state and
separate five-family approved E1/E2/coverage warnings. Updates and staged data
remain distinct from approved active authority. The protected same-origin POST
routes are `/settings/mcx-check/configure` (exact enabled/frequency form) and
`/settings/mcx-check/now` (empty body). Existing Browser admission/mutation fences
apply. GET `/settings` and `/settings/mcx-check/status` perform no check,
transport or persistence. Existing Settings polling observes state changes.

Qualification retains exact official browser DOM and denied direct-transport
responses separately from synthetic HTTP/lifecycle fixtures. No successful live
whole check, external warning delivery or automatic authority activation is
claimed. Full applicable regression remains S3.06. Authoritative publication and
activation continue through the existing Instrument, Market/Calendar, CA,
release and Sponsor process.
