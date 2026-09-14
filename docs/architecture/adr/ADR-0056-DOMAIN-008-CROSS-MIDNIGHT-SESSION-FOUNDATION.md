# ADR-0056 — DOMAIN-008 Cross-Midnight Session Foundation

## Metadata

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
- **Date:** 2026-09-14
- **Decision Owner / Required Approver:** Chief Architect / DOMAIN-008
- **Proposed By:** Swing Engineering Architect, prepared by Codex
- **Repository Approval:** Approved — Proposal 3
- **Scope:** Platform Market contract and bounded consumer compatibility
- **Work order:** WO-SWING-03A-CONTRACT
- **Current revision:** Proposal 3 — WO-SWING-03A-CONTRACT-REV02
- **Inspected baseline:** `9068edb3cff204f6f1584cf723b4c3607ba1963f`

Approval transcription: the historical proposal/review narrative below is retained
for provenance. Proposal 3 was approved by Chief Architect / DOMAIN-008 on
2026-09-14. The Sponsor has since deferred WO-SWING-03A-ENG as a future
capability. The approved contract remains available for future implementation,
but V2 has not been commissioned, published as a production capability or loaded.
The safely archived partial implementation was removed from the active worktree.
This disposition does not change the approved semantics.

## Context and source authority

WO-SWING-NEXT-03 demonstrated a representation limitation, not a proven real
MCX trading failure. Same-local-date guards reject a synthetic 23:00 to 01:00
next-day session. Publication parsing, ownership lookup, grouping, family
profiles and persistence also encode same-date assumptions; removing three
constructor guards alone cannot close the boundary.

This proposal transcribes and specifies Section 0.7 of the
[Swing Living Architecture](https://docs.google.com/document/d/1hqXZMqR7q_N1-7uC4ApAcDvGh9WywmH_COksMmSUkXY/edit),
read on 2026-09-14. At Proposal 1 that source was **PROPOSED — NOT FROZEN**,
with independent design review reported there. That historical source status did
not constitute approval. The repository's later Proposal 3 approval is authoritative.

No existing approved ADR was found covering explicit offset-0/1 publication,
cross-midnight ownership resolution and version-safe consumers together.
[ADR-0028](ADR-0028-DOMAIN-008-MCX-CROSS-SCHEDULE-COMPATIBILITY.md) concerns
directional family-expiry specialization, not general schedule equivalence or
cross-midnight commissioning.

## Current-production closure — WO-SWING-03B

- Current NSE and all five Swing MCX family schedules close on trading date D.
- Existing manifest V3/V1 remains current production authority.
- Current production windows inspected: 1,327.
- D+1 windows found: 0.
- Isolated unchanged-HEAD verification: 231 passed.
- No current production record requires V2.
- Synthetic D 23:00 to D+1 01:00 remains a deferred successor capability.
- Intraday source was restored byte-identically to HEAD.
- The partial implementation is preserved at `/Users/imranali/Documents/Project-KRONOS/output/swing-deferred/WO-SWING-03A-2026-09-14`.

Reactivation requires an authoritative D+1 schedule or new explicit Sponsor
instruction. ADR-0056 is not rejected, withdrawn or superseded.

## Approved decision — Proposal 3

1. DOMAIN-008 exclusively owns the publication, resolution and validation of
   trading-date/session ownership. Products consume its result; they must not
   recreate civil-date-minus-one heuristics.
2. Add the explicit V2 publication and resolved schedule contracts in the
   [proposed interface](../interfaces/KRONOS-MARKET-CROSS-MIDNIGHT-SESSION-V2.md).
   The exact identifiers, strict fields, integrity rules, bounded result states
   and failure reasons in that document are part of this approval request.
3. Legacy V1 syntax, constructor dispatch, serialization, IDs, hashes and
   restoration remain intact. No default offset is added to V1 payloads and no
   global schedule constant is replaced. Unsupported successors fail closed.
4. Successor windows carry explicit `open`, `open_day_offset`, `close` and
   `close_day_offset`; offsets are integer 0 or 1, with the first opening on 0.
   Later windows may open on 1. Never infer an offset from clock ordering.
5. Resolve endpoints in the governed timezone; validate chronology and elapsed
   intervals in UTC. Activity remains half-open `[open, close)`. Ownership of
   a session envelope includes its gaps but does not declare those gaps open.
6. Distinguish exact bound-owner lookup, unbound timestamp resolution and
   retained completed-evidence lookup. Missing coverage is not a non-trading
   declaration. Conflicting envelopes or windows cannot be first-match resolved.
7. Preserve Provider DAY trading-date labels, governed week membership, exact
   family-specific expiry cutoffs and existing before/at/after-cutoff semantics.
   An overnight session does not extend expiry or authorize a rollover.
8. Adapt only demonstrated date/serialization assumptions in affected consumers
   after approval. Preserve Swing 1W/1D/4H/1H methodology, prior completed 1H,
   exact common-boundary RS and SUPPORTING_CONTEXT_ONLY / NON-VETO authority.
9. Preserve ADR-0028 directional provenance and protected Intraday restoration.
   Successor syntax is not an equivalence certificate, capability waiver or
   permission to restore an incompatible research epoch.
10. Contract versions have exact JSON string/runtime str literals. Calendar,
    normalized/shared schedule and MCX profile successors use string "2";
    resolver request/result use string "1"; compatibility schema/policy use
    string "2.0.0". Source publication versions remain exact opaque strings.
11. Stable schedule identity hashes only immutable authoritative facts, ordered
    windows and immutable provenance. Exclude as_of, availability, freshness
    and integrity projection status. Resolver request/result and containing
    evidence integrity remain explicitly observation-specific; do not conflate
    these with schedule identity. Exact canonical maps and golden vectors are
    normative parts of the proposed interface.
12. Resolver requests/results are closed, mode-discriminated schemas. Future
    reminder lookup is schedule-only, never completed/current market evidence.
    Retained 1H evidence requires its actual governed end <= as_of, exact owner
    and window anchor; DAY labels and 4H completeness retain separate authority.
13. V2 adjacency requires explicit exact predecessor/successor bindings in an
    immutable successor manifest V4. Verify digests, scope, lineage, coverage
    ordering and ownership conflicts at load, request and restoration boundaries.
    Preserve V3 manifests and V1 paths. This is a proposed format only, not a
    production manifest migration or authority to change exchange hours.

## Authority and exclusions

This is a Market Schedule proposal, not an EAIC-001 presentation-state change.
EAIC-001 OPEN/CLOSED remains presentation-only; it is not the authority used to
alter analytical decisions or alerts. Existing consumers use governed schedule
boundaries under their own unchanged contracts.

No production calendar, exchange hour, threshold, duration ceiling, universal
24-hour-market model, general DST commissioning, universe, Provider DAY label
convention or new market is authorized. Offsets outside 0/1 are out of scope.

No Native Discovery, KR-370, Review/Visual V2/V3, Layer-2/Readiness, Step-31,
Risk, Sponsor decision, entry timing, lifecycle, Pine or broker authority changes.
Intraday 15M/5M admission, cutoffs, research acceptance and product-specific holds
are untouched. Qualifying the five Swing MCX families does not commission a held
Intraday family. No evidence backfill, runtime action or production retrieval.

## Alternatives considered

- Remove date guards only: rejected; publication and ownership remain incorrect.
- Infer overnight from clock order: rejected; ambiguous and alters legacy meaning.
- Add only a closes-next-day boolean: rejected; cannot express a later window
  opening after midnight.
- Replace runtime concepts or bump global constants: rejected; unnecessary
  historical-identity and shared-consumer risk.
- Infer sessions from Kite candles: rejected; violates DOMAIN-008 authority.

## Consequences, risks and approval decisions

At proposal stage the Chief Architect was asked to ratify the exact successor
versions and strict wire forms, envelope ownership through gaps, conservative
coverage-edge behavior, failure taxonomy and narrowly versioned family/
compatibility projections. Proposal 3 additionally requested approval of the
exact closed resolver wire forms, timestamp canonicalization, stable-vs-
observational identity separation, explicit manifest V4 adjacency, deterministic
validation precedence and in-memory-only failure diagnostics. Proposal 3 was
subsequently approved as recorded above; commissioning remains deferred.

Calendar publication and application release are separate gates. There is no
assertion that currently published MCX hours require an overnight window. A new
official source would be required before any production session amendment.

Shared schedule code can affect Intraday capability hashes even without changing
methodology. Exact restoration must still pass; otherwise a separately approved
compatibility or material-successor operation is required. This ADR is no such
operation. No approved decision is superseded while this document is Proposed.

## Implementation and acceptance

The [consumer map and acceptance plan](../products/swing/WO-SWING-03A-CONTRACT-CONSUMERS-AND-ACCEPTANCE.md)
is part of this proposal. It identifies required changes versus compatibility
qualification, exact acceptance cases, likely files and stop gates. No runtime
or test implementation is included in this work order.

Existing verification evidence: WO-SWING-NEXT-02 reported 311 isolated tests;
NEXT-03 reported 229 foundation tests and seven diagnostic probes, three of
which reproduced rejection rather than cross-midnight support. These were not
rerun as implementation acceptance for this documentation-only amendment.

## Historical decisions and related authority

- [PLATFORM-000](../platform/PLATFORM-000-CONSTITUTION.md), CA-015/016/019.
- [DOMAIN-008 Architecture](../platform/domains/market/ARCHITECTURE.md) and
  [Engineering](../platform/domains/market/ENGINEERING.md).
- [EAIC-001](../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md).
- [ADR-0017](ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md).
- [ADR-0028](ADR-0028-DOMAIN-008-MCX-CROSS-SCHEDULE-COMPATIBILITY.md).
- [ADR-0048](ADR-0048-WO06H-SAME-EPOCH-COMPATIBILITY-RESTORATION.md).

Following Proposal 3 approval, indexes/domain documentation may describe V2 as
approved architecture while also recording its uncommissioned status.
Do not rewrite historical ADRs, V1 policy documents or accepted evidence.

## Proposal 2 — EA finding disposition

| EA finding | Proposal 1 gap | Proposal 2 exact response / proposed interface section |
| --- | --- | --- |
| 1 — Version types | Version table did not distinguish numeric 2 from string "2" | §1 enumerates each discriminator/type/literal and exact source-version/binding rules; §8 names legacy source-contract fields separately |
| 2 — Resolver contract | Modes/outcomes lacked closed request/result shapes | §6 supplies required/forbidden/null fields, owner tuple, as_of/future/retained rules and complete returned facts; §9 supplies exact outcomes |
| 3 — Stable identity | Full normalized schedule hash included observational projection | §5.2 replaces that proposed formula with immutable S; §12 proves identical identity across different as_of projections |
| 4 — Hash determinism | Maps/encoding/provenance and expected outputs incomplete | §5 specifies C/H, exact W/S/Q/R/K maps, timestamp/string/enum/null/array rules, prefixes and lowercase hex; §12 supplies seven complete golden vectors |
| 5 — Failure taxonomy | Suffix-only diagnostics, incomplete precedence/storage | §9 gives full codes, outcomes, typed outer exceptions, precedence and in-memory-only diagnostics; V1 paths/strings unchanged |
| 6 — Adjacency proof | Retained adjacent entry was underspecified | §11 defines immutable manifest V4 edges, exact binding lookup, lineage/effective ordering, digests/conflicts and load/request/restore phases |
| 7 — Acceptance | Original cases lacked revised wire/hash/adjacency checks | Consumer plan §4.1 adds V/Q/H/C/D cases; every original A/O/F/M/R/S/P/I case is retained |

These changes supersede only Proposal 1 text inside this unapproved package.
They do not supersede any approved decision, source publication or evidence.

### Revision record

| Date | Revision | Change | Approval |
| --- | --- | --- | --- |
| 2026-09-14 | Proposal 1 | Exact 03A contract and bounded implementation plan | Pending Chief Architect |
| 2026-09-14 | Proposal 2 | REV01 exact versions/resolver/hashes/failures/adjacency and additive acceptance | Pending Chief Architect — NOT APPROVED |
| 2026-09-14 | Proposal 3 | REV02 maps retained query/start inequality to MARKET_SESSION_INTERVAL_INVALID / INVALID / COMPLETION, with null trusted projections and completion false; Q07 extended, all other Proposal 2 decisions/vectors preserved | Approved by Chief Architect / DOMAIN-008 on 2026-09-14 |
