# ADR-0039 — Intraday Prospective WO09–WO16 Programme Authority

**Status:** APPROVED for bounded engineering by Sponsor / EA, 2026-09-11.
**Programme:** KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2 / 1.0.0.
**Runtime and publication:** Separately authorized; this candidate grants neither.

The Sponsor final Futures-only WO-10 engineering order supersedes the earlier
options/margin preflight prospectively. WO-10 is construction, Futures expression,
Risk-only sizing, executability facts and Sponsor selection. It has no broker,
activation, position, fill, PAPER/LIVE, P&L or margin authority. Options are
NOT_COMMISSIONED_V1 and NATGAS remains HELD.

## Semantic epochs and ownership

| Prospective owner | Responsibility |
| --- | --- |
| WO-09 | Governed Promotion & Active Readiness; existing current authority |
| WO-10 | Futures Trade Construction, Risk & Sponsor Selection |
| WO-11 | Position / Paper Observation / Lifecycle; future work |
| WO-12 | Opportunity Data & Research Ledger, real XLSX, quantitative analysis; future work |
| WO-13 | Notifications; future work |
| WO-14 | Trading Journal; future work |
| WO-15 | Portfolio; future work |
| WO-16 | Reports; future work |

The effective boundary is the first explicitly commissioned prospective WO-10
operation under this programme and policy, recorded as
ADR-0039:EXPLICIT_PROSPECTIVE_WO10_OPERATION together with each operation timestamp.
It is not a backdated activation or a migration of prior records.
Every prospective record binds programme/version, policy/version/checksum and
this authority boundary. New prospective current pointers are authoritative only
inside their own epoch. Historical pointers remain readable and are never repointed.

## Predecessor disposition

ADR-0019/0020 old WO-10 E/I/M and WO-11 collation become HISTORICAL_ONLY and
RETIRED_PROSPECTIVE_AUTHORITY. Old WO-12 promotion remains historical under
ADR-0038. ADR-0022 old WO-13 records remain historical; its pullback/breakout,
target constraint and arithmetic engines are ADAPTED_INTO_NEW_WO10 through the
explicit WO09 adapter. No old handoff is fabricated. ADR-0023 old WO-14 records
remain advisory historical facts; the monetary formula is reused by a new
Risk permission owner. ADR-0025 old WO-15 timing and ADR-0027 old WO-17 lifecycle
may be adapted into future WO-11. ADR-0026 old WO-16 Sponsor records stay historical;
prospective expression/quantity selection belongs exclusively to WO-10.

These decisions retire conflicting prospective ownership only. All predecessor
ADRs, schemas, policies, records, namespaces and evidence bytes retain their
historical meaning. The operational Browser blocks mutating historical controls
under the successor programme; historical GET projections remain available.
No dual prospective decision owner is permitted. Swing authority is unchanged.

## Construction and Risk boundary

Only exact-current integrity-valid WO-09 5/5 BUY_NOW/SELL_NOW enters WO-10.
Canonical setup geometry precedes contract selection. No Stop repair, target
shopping, minimum R:R, options or margin API is permitted. Risk Permission is a
new APPROVED/CONSTRAINED/REJECTED/UNAVAILABLE record and never changes geometry.
Sponsor selects whole lots within the permitted maximum or NONE. Only a selected
Future creates a selected-trade handoff; neither selection nor handoff activates it.

## Implementation and qualification

The product specification and interface define the bounded frozen rules. Tests
must use the kernel-isolated repository launcher. Existing running production
composition and all retained evidence remain untouched during engineering.
