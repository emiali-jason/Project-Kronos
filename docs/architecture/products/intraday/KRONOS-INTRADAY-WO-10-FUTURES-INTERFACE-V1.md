# WO-10 Futures interface V1

## Current authority — ADR-0042

Status: Approved bounded engineering by direct Sponsor / EA authorization, 2026-09-11.

The current Native loader, publication and construction action are implemented under ADR-0041. ADR-0042 resolves the former monetary blocker by making Risk advisory. Current records are policy 1.1.0; old 1.0.0 remains readable only as history. `assess_risk` emits Risk fact + advisory, never permission. `preview_risk(comparison_identity, lots)` reads retained facts and returns a non-persisted projection. Browser POST `/control/intraday-futures/risk-preview` accepts only comparison_identity/lots. Selection retains its own evaluated advisory. No Browser-supplied prices, reference amounts or calculated Risk are authoritative. Individual contract/market/WO09/Native hard gates remain unchanged.

See [ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) and [advisory Risk policy](KRONOS-INTRADAY-WO-10-ADVISORY-RISK-POLICY-V1.md).

## Preserved predecessor text

**Status:** Approved engineering contract under ADR-0039.

`IntradayFuturesApplication.evaluate` accepts an exact-current WO09-derived adapter,
existing governed structural evidence and target population, a complete daily
Provider master, exact canonical runtime underlying or MCX active binding/economics,
DOMAIN-008 session source, a read-only Provider capability and optional configured
Risk evidence. A caller must supply one explicit operation identity. It does not
manufacture source structure or a 5/5 candidate. The operational guard must affirm
lawful operation; absent guards fail closed.

`adapt_wo09` binds exact handoff/readiness/current-pointer integrity, subject,
direction, session, analysis boundary, WO07F, machine and visual lineage. Setup
source must belong to retained WO09 machine evidence. Existing WO13 construction
engines accept precisely this new adapter or their original historical type.

Eight separate immutable result families are canonical plan, market snapshot,
Future expression, Risk fact, Risk permission, comparison, Sponsor selection and
selected-trade handoff. Additional operation, contract, opportunity, OI baseline
and current-pointer records retain audit and research lineage. All envelopes use
canonical sorted JSON, decimal strings, aware UTC timestamps, content hashes,
programme/version, policy/version/checksum and effective authority boundary.

New root: `prospective-v2-wo10-futures`. Append-only records and atomic pointers
never overwrite historical selections. One opportunity identity per exact WO09
handoff/readiness defines the denominator; later quote comparisons link to it.
A failed or interrupted request cannot retry itself. New request identity is
required for explicitly commissioned reacquisition. Foreign and corrupt records
fail closed. No opaque Provider handle or credential is serialized.

Browser GET `/intraday/futures` projects stored numbers and current decision state.
POST `/control/intraday-futures/selection` accepts exactly comparison_identity,
choice, lots and action_identity. Choice is SELECTED_FUTURE or NONE. It has no
geometry, pricing, Risk, sizing, options, activation or broker calculation path.
Full structural construction/acquisition is an explicit application operation;
Browser never accepts prices or Risk calculations from its own projection.

## Engineering integration gate — BLOCKED

The typed construction, quote, Risk, selection and Browser projection foundation
is implemented and tested with isolated governed fixtures. This is not a completed
production Sponsor journey and is not a deployment or runtime acceptance claim.

The retained production WO09 source does not currently supply a machine-produced,
exact-current WO09-bound WO13 pullback/breakout structural evidence object and
its complete target constraint population. Existing historical WO13 Browser
controls parse caller-supplied geometry; they are not a retained structural fact
producer. Search evidence: the only production-tree definitions of
`create_wo13_pullback_geometry_evidence` and
`create_wo13_breakout_geometry_evidence` are the contracts themselves. Swing's
structural producers are outside this Intraday authority and cannot substitute.

Therefore the new Browser exposes persisted comparison/selection only. No Sponsor
construction button or production acquisition controller is commissioned. A
production source loader must first bind lawful setup/structure, target population,
current WO09 handoff, instrument/master/economics, configured Risk and session
facts, then commission the one attributed acquisition through existing Provider
capability. `evaluate` is a typed application seam, not proof that such a source
loader already exists. The optional master callback is an integration seam; its
physical request bound still requires qualification of the production adapter.
No production structural facts, Risk budgets or Provider inputs were fabricated.

Smallest completion prerequisite: establish the authoritative retained structural
producer/loader contract, then wire and qualify the Sponsor construction action
using those exact current facts. If existing retained machine evidence can provide
all structural roles, that adapter may reuse it; otherwise Sponsor/EA must settle
the missing structural source authority. Until that is established, overall WO10
engineering candidate status remains BLOCKED despite passing component tests.

Interrupted selection persistence fails closed: a retained selection without its
selected-trade handoff is reported INCOMPLETE on replay, never repaired implicitly
or reported as a completed handoff. Read-only restoration never recreates current
quote authority. File and directory synchronization precede successful persistence.

Returned typed quote facts are retained as QUOTE_RECEIVED acquisition evidence
before post-request currentness/timeout checks. This factual receipt grants no
current snapshot, Risk or selection authority. A superseded request cannot
publish a comparison, but its returned facts are not erased. Process-local
selection eligibility is granted only after the completion record is durable;
a completion-write failure leaves no executable authority.

## Successor correction — ADR-0040

**Status:** Approved bounded engineering, Sponsor / EA 2026-09-11.

The predecessor integration-gate description above is retained as history. The
successor adds `construct_current(handoff_identity, request_identity)`, an exact
Native selection contract/loader and immutable unavailable results. Browser POST
`/control/intraday-futures/construction` accepts exactly those two identifiers.
It accepts no setup, geometry, source prices, target population, master or Risk
configuration. The existing `evaluate` numerical foundation remains an internal
composition seam, not a Browser authority source.

The runtime composes `NativeStructuralLoader` with an empty approved-policy
registry. It can preserve and display structural unavailability without changing
WO-09. No existing Native policy selects the roles required for positive
production construction. A new Native algorithm is explicitly prohibited in this
correction. The positive isolated path uses clearly test-only Native policy
fixtures, exact source identities and a supplied current market-authority adapter.
Production positive commissioning remains a separate, explicit prerequisite.

The complete consumer sequence is exact WO-09 handoff/current pointer → Native
selection/source loader → new WO-09 construction adapter → unchanged WO-13
geometry → canonical plan → configured acquisition inputs → bounded full quote
→ Future expression → Risk → comparison → Sponsor choice → non-position handoff.
Current input revalidation includes master, underlying, MCX active binding and
economics, Risk configuration, session and expiry. If the current market input
adapter is missing, the identity-only path returns unavailable before acquisition.
The runtime does not invent that source adapter or any Risk budget.

One request identity cannot retry an interrupted construction. The construction
lock and acquisition lock are separate; immutable request and result records
preserve failure and exact Native-selection/target-population lineage. Returned
quote facts survive a failed currentness check. No stale result grants selection.
GETs can display a 5/5 candidate with missing structure even before an operation
has retained a failure; this is explicitly a read-only availability projection,
not a newly manufactured plan. Explicit construction persists the unavailable
plan and outcome when a lawful exact-current handoff exists.

Sponsor routes are `/intraday`, `/intraday/review`, `/intraday/trade-candidates`,
`/intraday/active`, `/intraday/closed`; historical WO routes remain. Trade Candidates
also displays snapshot/Risk failure and selection state within the same journey.
