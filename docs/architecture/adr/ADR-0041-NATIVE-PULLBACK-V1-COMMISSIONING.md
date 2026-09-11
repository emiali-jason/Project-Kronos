# ADR-0041 — Native PULLBACK V1 commissioning

Status: Approved for bounded engineering by direct Sponsor / EA order, 2026-09-11.
Authority: Native Structural Selection Policy V1 PULLBACK-only commissioning and final WO-10 successor correction.
Predecessor: [ADR-0040](ADR-0040-NATIVE-STRUCTURAL-AUTHORITY-AND-INTRADAY-NAVIGATION.md), preserved as the earlier no-selector decision.

This decision supersedes ADR-0040's empty production selector registry for prospective PULLBACK only. It does not commission BREAKOUT, change WO-09's five criteria, or grant runtime/production operation authority.

## Commissioned policy

`KRONOS-INTRADAY-NATIVE-STRUCTURAL-SELECTION-POLICY / 1.0.0` is Native-owned under `KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2`. Canonical JSON of `native_pullback_policy.RULES` determines its SHA-256 checksum. Positive output is `PULLBACK`; otherwise `NOT_ESTABLISHED` with ordered reasons. BREAKOUT is `NOT_COMMISSIONED_V1`; its construction engine is preserved.

Only owner-validated, completed, same-subject/session 15M payloads at the exact analysis boundary are eligible. Local HIGH/LOW requires strict inequality against both immediate neighbours; confirmation is the right neighbour's completion. The existing strict immediate-neighbour predicate is applied to the governed historical-payload type.

LONG uses L0 → H1 → L2 → Q: H1 > L0, L2 > L0; Q is the first completed candle strictly after L2 confirmation whose close exceeds the immediately preceding HIGH. Any completed LOW at or below L0 before/through Q invalidates that cycle. SHORT is the exact mirror. Select the most recent qualification completion; distinct cycles tied at that time are ambiguous and unavailable. No ATR, Fibonacci, retracement percentage, volume, reward/risk, distance or bar-count selector is introduced.

Cycle identity seals subject, direction, session, three pivot identities, qualification candle, boundary and policy version. The decision also binds Probables result/run, semantic identity/integrity, exact roles, source envelope, target manifest and MCX contract/roll.

## Typed target authority

The five classes are setup-native impulse, PDH/PDL, Classic R1–R4/S1–S4, existing governed session extremes and existing governed 15M barriers. Rows retain applicability, availability, exact reference, price, forward status, inclusion and reason. Prior-session references retain original session/date. Derived pivots refer to the prior-session fact and formula field, never a fabricated candle identity.

This order creates no new session-extreme or barrier selector. Where no existing governed producer establishes these optional sources, rows explicitly report NOT_APPLICABLE / NOT_ESTABLISHED. A required class missing complete authority is INCOMPLETE, never an implicit empty complete population.

Manifest states are COMPLETE_WITH_TARGETS, COMPLETE_NO_APPLICABLE_FORWARD_CONSTRAINTS and INCOMPLETE. Existing WO-13 geometry and nearest-forward target rules remain authoritative. A non-forward setup-native target fails without substituting another cycle or impulse.

## Publication and consumption

`NativePullbackPublication` is inert on construction. The new runtime composition captures a prospective commissioning boundary and retains it on the first new publication. Selection runs only on new Native publications at/after that boundary, before exposing the Probables population. Startup and historical restore never select. Source/decision records and semantic bindings are immutable; a run manifest closes the companion population. Missing/invalid mapped sources retain explicit negative decisions. Unmapped members have no semantic authority and cannot enter WO-09/WO-10.

`NativeStructuralLoader` loads the exact binding named by WO-09 machine identities. It verifies owner sources and the already-selected cycle without searching alternatives. Negative results persist unavailable construction before geometry/acquisition. The adapter carries the true structural cycle separately from semantic lineage; WO-13 exact-cycle validation remains intact.

MCX uses the owner-encoded active binding named by the original fact bundle, with exact contract, roll, session and snapshot. No later binding substitution is allowed. International references are never Native inputs. NATGAS remains HELD.

## Market composition and independent monetary inputs

The lazy WO-10 source uses the current governed Refresh master identity (or MCX's exact active-binding snapshot), sealed DOMAIN-001 catalogue/directives and DOMAIN-008 session. It requests the existing quote lease only after explicit construction. Startup/page reads perform no acquisition. Missing/stale master, binding or calendar fails closed.

Risk budgets/open-risk totals and MCX monetary economics remain independent authority inputs with explicit typed loader ports. No default budget, zero open-risk claim, broker-margin assumption or multiplier inferred from lot size is permitted. Without commissioned source records, Risk permission / MCX monetary construction remains unavailable. Isolated positive qualification supplies explicit fixture authority; it does not commission absent production configuration.

## Preservation

Primary tabs remain Opportunities, Review, Trade Candidates, Active, Closed. Current 5/5 readiness stays visible when construction is unavailable; exact Native details are secondary. Historical routes/contracts/records remain intact. Options, broker execution, a new WO-11 position lifecycle and production operations remain outside scope. No current historical candidate is retrospectively classified.
