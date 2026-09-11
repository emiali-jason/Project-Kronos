# ADR-0040 — Native structural authority and Intraday Sponsor navigation

**Status:** Approved for bounded engineering by Sponsor / EA, 2026-09-11.
**Authority:** WO-10 successor order and its explicit Native-selection clarification.
**Predecessor:** [ADR-0039](ADR-0039-INTRADAY-PROSPECTIVE-WO09-WO16-PROGRAMME-AUTHORITY.md), preserved.

## Decision

Native machine analysis owns setup classification, selected structural roles,
setup/cycle identity, exact candle/source references and target population with
explicit completeness. WO-10 consumes this authority; Browser, Chart Analyst and
WO-07F cannot supply or choose it. Directional Native facts do not establish a
PULLBACK or BREAKOUT selection. No new Native selection algorithm is authorized.

Positive construction requires an already-approved Native selection policy and
an exact retained selection record under that policy. The current production
approval registry is empty. A valid checksum alone never proves policy approval.
No current production source has been established as such a selection record.

Absent authority produces `TRADE_PLAN_UNAVAILABLE` with reason
`STRUCTURAL_CONSTRUCTION_AUTHORITY_NOT_ESTABLISHED`. A lawful 5/5 NOW readiness
record remains unchanged. No retrospective candle search, target shopping,
historical backfill or manufactured completeness is permitted.

## Prospective contract and consumption

`NATIVE_STRUCTURAL_SELECTION_V1 / 1.0.0` is a retention/consumption contract,
**not** a commissioned setup-selection policy. It binds programme, the producer's
policy identity/version/checksum, subject/direction, setup/cycle/boundary/session,
trading date, machine identity/integrity, source identities/integrities, exact
candle references and fields, instrument, MCX contract/roll, created time and
integrity. PULLBACK retains qualification HIGH and LOW, directional pullback
extreme and prior impulse extreme. BREAKOUT retains qualification HIGH and LOW,
original range identity and both range extremes. Roles are explicit; none is
selected by the adapter.

Target states are `COMPLETE_WITH_TARGETS`,
`COMPLETE_NO_APPLICABLE_FORWARD_TARGETS`, and `INCOMPLETE`. The first requires
nonempty targets, the second an explicitly empty population. INCOMPLETE cannot
construct. The existing geometry and target hierarchy are reused unchanged;
there is no implicit empty-to-complete default at this interface.

`NativeStructuralStore.retain` is a prospective producer seam that requires an
approved policy and the exact cycle. It is not called from current Native
analysis because no supported classifier exists. `NativeStructuralLoader.load`
resolves only immutable bindings from the handoff's exact machine identities,
then validates the approved policy, all handoff bindings, each exact source
integrity, selected candle completion/time/session/date, role price and MCX
lineage. Source loader adapters must be commissioned with the future Native
policy. The runtime's empty registry rejects unsupported records before any
source or Provider acquisition. Isolated policy fixtures are not production
approval and cannot populate this registry.

`construct_current(handoff_identity, request_identity)` is the bounded Sponsor
entry point. Browser supplies identities only. Unavailable results and request
lineage are immutable in `prospective-v2-wo10-futures`; GET/restoration creates
nothing. Native selections live separately under `native-structural-selection-v1`.
Rechecking exact WO-09 currentness protects structural loading, plan publication,
acquisition, comparison and selection. A missing/stale handoff cannot be repaired
by this operation. It does not create a new WO-09 evaluation or handoff.

## Sponsor navigation

The primary Intraday order is exactly OPPORTUNITIES, REVIEW, TRADE CANDIDATES,
ACTIVE, CLOSED. Opportunities includes persisted WO-09 readiness; a lawful current
5/5 NOW card links to Trade Candidates. Review owns the existing Chart Analyst
workflow. Trade Candidates owns prospective WO-10 and future WO-11 continuation,
including unavailable construction and retained Sponsor selection. Active and
Closed are real, inert destinations until the future lifecycle is commissioned.

WO-10 through WO-17 primary tabs are removed. Historical GET/status/deep links,
records, contracts and policies remain available. `/intraday/futures` remains an
alias of `/intraday/trade-candidates`. No Swing navigation is changed.

## Commissioning boundary and consequences

The fixture-qualified positive consumer path is not proof of production Native
selection or acquisition composition. The runtime wires the unavailable path.
Positive production composition remains blocked until Sponsor/EA separately
approves the Native selector, its complete target-source policy and exact
source adapter, then binds current instrument/master/MCX economics, configured
Risk and DOMAIN-008 session inputs to the acquisition seam. It must not choose
these retrospectively in WO-10. The new identity-only path requires current
market-authority revalidation for a positive comparison; absent inputs fail closed.

Future policy must specify supported setup classification, deterministic
qualification/resumption and governing-structure selection, range/move origin,
cycle identity, source population coverage and explicit completeness, completion
and session rules, and exact MCX lineage. Thresholds and selection rules remain
`NOT_ESTABLISHED`; this ADR invents none.

No new options, margin/funds, execution, position, PAPER/LIVE or broker authority.
NATGAS remains HELD. WO-06H clean-commit restoration is unchanged. Dirty-runtime
recovery, publication and production acceptance require separate authorizations.
