# ADR-0042 — WO-10 advisory Risk and final Futures composition

Status: Approved for bounded engineering by direct Sponsor / EA authorization, 2026-09-11.

This decision implements the final WO-10 successor order and direct authorization to replace Risk-permission gates with advisory Risk. It supersedes permission/sizing statements in [ADR-0039](ADR-0039-INTRADAY-PROSPECTIVE-WO09-WO16-PROGRAMME-AUTHORITY.md), [ADR-0040](ADR-0040-NATIVE-STRUCTURAL-AUTHORITY-AND-INTRADAY-NAVIGATION.md) and the independent monetary-input blocker in [ADR-0041](ADR-0041-NATIVE-PULLBACK-V1-COMMISSIONING.md) only prospectively. Those earlier decisions and all historical records remain intact. Native PULLBACK policy 1.0.0 is unchanged; BREAKOUT remains uncommissioned.

## Authority

WO-10 owns Futures construction, monetary facts, optional Risk reference, warnings and Sponsor selection. It has no Risk permission/veto, broker margin, buying-power, funds, execution, position or lifecycle authority. WO-09 remains exactly five criteria. Options remain NOT_COMMISSIONED_V1. Exact contract/roll, subject, direction, geometry, integrity, session, currentness, fresh market evidence and factual executability remain independent hard gates. NATGAS remains HELD.

The prospective programme remains KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2 / 1.0.0. The WO10 Futures policy becomes 1.1.0, with a new checksum and logical effective boundary ADR-0042:EXPLICIT_PROSPECTIVE_WO10_ADVISORY_OPERATION. No runtime activation timestamp is invented. Old 1.0.0 envelopes can be read and integrity-checked but never restore current 1.1.0 authority or create new permission records.

## Advisory monetary contract

Risk/reward per lot use exact mapped Future geometry and authoritative contract lot/multiplier only. NSE equity/index Futures use the current exact NFO contract lot and INR-per-underlying-unit quotation convention. MCX lot/tick alone do not prove monetary scaling. Existing typed, sealed Wo14InstrumentEconomics may supply exact contract/roll-bound economics; missing/stale/inconsistent monetary economics produce RISK_FACT_UNAVAILABLE without blocking an otherwise valid contract. Foreign contract economics remain a binding violation. Missing monetary data never licenses invented quotation units, contract units or tick values.

Sponsor may optionally supply a sealed INR Risk reference with source identity, effective time and expiry. It is not a budget cap. No default amount, percentage, lot count, open-risk zero or margin assumption exists. A zero explicit reference has reference-lots zero; percentage difference is undefined and remains unavailable, with a reason. Negative/nonfinite/boolean amounts are invalid.

risk_reference_lots = floor(reference / risk_per_lot). Sponsor may select any positive whole lots. Selected Risk = risk_per_lot × selected lots; difference = selected Risk − reference; percentage = difference/reference × 100 for a nonzero reference. States are WITHIN_REFERENCE, ABOVE_REFERENCE, REFERENCE_NOT_CONFIGURED and RISK_FACT_UNAVAILABLE; QUANTITY_NOT_SELECTED distinguishes a pre-choice display. Stale, invalid or superseded references do not become trade vetoes. Risk magnitude never disables SELECT FUTURE.

## Composition and UX

New Native publication → exact structural decision → exact-current WO-09 5/5 → existing geometry/typed targets → Future contract/snapshot/basis expression → advisory facts → Trade Candidates → Sponsor selection → immutable non-position handoff. Current 5/5 with NOT_ESTABLISHED remains visible as TRADE PLAN UNAVAILABLE. No historical backfill, setup search or target shopping.

The five primary destinations remain OPPORTUNITIES, REVIEW, TRADE CANDIDATES, ACTIVE, CLOSED. Historical WO routes remain accessible without restoring old tabs. ACTIVE/CLOSED are inert until prospective WO-11 is separately commissioned. Swing is unchanged.

Quantity preview is a read-only backend projection, not Browser arithmetic authority. ABOVE RISK REFERENCE includes prominent red styling plus explicit text, per-lot Risk, reference, selected lots/Risk, exact INR excess and percentage excess. The warning never disables selection. Selection retains the exact advisory facts and their source/currentness, with no maximum_permitted_lots field. The forward handoff distinguishes selected quantity from any later activated/executed quantity.

## Qualification and operating boundary

Deterministic tests cover LONG/SHORT publication-to-selection, no-reference/above-reference selection, MCX available/unavailable economics, product isolation, exact calculations, no hidden permission gates, read-only previews, historical envelopes, currentness, persistence and the five-tab UX. Full repository qualification uses the kernel-isolated launcher. Engineering creates no production Native/WO09/WO10/Provider/Review/Risk/selection/handoff or broker operation. Publication and runtime load need separate Sponsor authorization.
