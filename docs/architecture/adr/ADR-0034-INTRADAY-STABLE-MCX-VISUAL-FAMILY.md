# ADR-0034 — Intraday stable MCX visual family and separate exact contract authority

Status: Sponsor-approved bounded decision; engineering candidate, publication pending.
Decision source: Sponsor FINAL MCX VISUAL IDENTITY AUTHORITY CORRECTION, 10 September 2026, and subsequent direct engineering authorization.
Scope: WO-07E identity completion only. No production, commissioning, reconciliation, trading or broker activation.

## Decision

DOMAIN-001 retains exact case/punctuation-sensitive visual relationships. Successor 1.7.0 adds three explicit contexts: TRADINGVIEW_MCX_NATIVE_FAMILY, TRADINGVIEW_NYMEX_REFERENCE_FAMILY and TRADINGVIEW_COMEX_REFERENCE_FAMILY. Contexts encode role and venue so identical Copper/Natural Gas labels do not collide across native and reference subjects. General NSE visual context remains unchanged.

Native relationships resolve to stable MCX-SUBJECT identities, never to a permanently selected expiry. Native panel venue, role, timeframe, content and temporal validation remain required. Exact machine active binding, derivative contract, expiry, calendar eligibility, Review boundary and image/revision association remain separate and unchanged.

Sponsor must open the exact contract printed by KRONOS. Same-family different-expiry pixels may be indistinguishable. This is an explicitly accepted single-Sponsor operating assumption, not independent visual expiry proof. Wrong machine metadata still rejects. No fuzzy alias, Provider-name fallback or month-code inference exists.

Reference relationships resolve exact visible family/venue to existing reference analytical subjects. References remain SUPPORTING_VISUAL_CONTEXT_ONLY and NOT_INDEPENDENTLY_ESTABLISHED; no independent reference market source or continuous-series constituent membership is asserted.

## History and transition

This supersedes the Intraday requirement that every prospective native family label resolve to the exact expiry contract; ADR-0018 exact relationship, integrity, effective-date and replay principles otherwise remain intact. No historical publication is changed. NSE 1.6.0 and its source CSV are byte-preserved; 1.7.0 preserves all 95 relationships and adds NIFTY plus ten MCX native/reference relationships.

New source relationships start at each retained chart file timestamp, never at the earlier 17:03 Review. The new MCX family gate uses the Review analysis boundary, not later chart receipt, for relationship availability. A later upload cannot backdate family authority.

MCX transport 1.4.0 adds family-authority instructions and a distinct immutable pack-transports-family pointer. Previous transport namespaces and files remain readable. Legacy transport imports keep the exact-contract resolver; successor imports use explicitly composed 1.7.0. Imported native resolution context records family authority; native correspondence is classified FAMILY_VISUAL_MACHINE_TEMPORAL_CORRESPONDENCE, avoiding a claim of independent expiry proof. Machine exact-contract fields remain retained.

## Rollover and limits

Rollover changes the governed active derivative binding, not the stable visual relationship. Machine calendar/eligibility failures remain failures. The current 2026 calendar does not authorize the next SILVERM contract expiring in 2027; this engineering does not extend calendar authority. NATGAS remains HELD for production commissioning, although its stable visual identity capability is qualified in isolation.

## Qualification

Require exact 91-equity preservation, both indices, all ten family/venue relationships, effective-boundary and tamper rejection, four existing-calendar successor rollovers plus fail-closed Silver future-calendar coverage, and five-family constructed V2 intake/import/restoration with adverse cases. These tests do not represent empirical Chart Analyst performance. WO-07F is not implemented or started.
