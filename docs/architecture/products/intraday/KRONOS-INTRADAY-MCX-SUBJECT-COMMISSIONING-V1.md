# KRONOS Intraday — MCX Subject Commissioning V1

Status: production implementation contract. This publication admits qualified
MCX analytical subjects to Probables V2; it creates no Entry Timing, Trade,
Risk, PAPER/LIVE, execution, or broker authority.

## Governed state

The immutable `KRONOS-INTRADAY-MCX-SUBJECT-COMMISSIONING-REGISTRY-V1 / 1.0.0`
binds the accepted continuous-history and family-expiry research evidence.
Its initial publication is
`INTRADAY-MCX-COMMISSIONING-PUBLICATION-45260CF10CBB4FA9E8355351A9DD9EF22FA840617F6A8154B88FF1F328343818`.

| Canonical subject | State |
|---|---|
| `MCX-SUBJECT-GOLDM` | `COMMISSIONED` |
| `MCX-SUBJECT-SILVERM` | `COMMISSIONED` |
| `MCX-SUBJECT-COPPER` | `COMMISSIONED` |
| `MCX-SUBJECT-CRUDE` | `COMMISSIONED` |
| `MCX-SUBJECT-NATGAS` | `HELD` — `MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED` |

An unknown MCX subject fails closed. Commissioning is evidence-bound and is
not inferred from family-level qualification.

## Successor methodology

Prospective runs bind `KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2 / 2.1.0`.
The payload checksum is
`32012713c2b43212bea6af3bace0fbd2491176cb0a1cb7aaf88f8de77c1e8932`
and the publication is
`INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-32012713C2B43212BEA6AF3BACE0FBD2491176CB0A1CB7AAF88F8DE77C1E8932`.
Version 2.1.0 changes only MCX subject admission and prospective exact-contract
retention. NSE predicates, the four phases, completed-evidence rules, conflict
semantics, and NIFTY rules remain identical to 2.0.0. Historical 2.0.0 runs
remain valid and replay by their original publication and checksum.

MCX NIFTY applicability is `NOT_APPLICABLE`; this is a complete valid state.

## Expiry-safe evidence

Already-acquired, governed completed 1D, 1H, 15M, and 5M MCX candles are
retained prospectively under their exact actual derivative contract. Retention
performs no duplicate Provider read and preserves subject, contract, Provider
record identity (never token), active binding, DOMAIN-008 session/calendar,
timeframe, source and completion boundaries, OHLCV, operation provenance, and
integrity.

Storage is append-only, atomic, immutable, and explicit-identity reload only.
Conflicts and corruption fail closed. Continuous analytical views concatenate
explicit exact-contract segments without back adjustment, retain roll
boundaries, do not label rolls as market gaps, require no current Instrument
Master for old history, and are non-executable.

PDH, PDL, previous close, CPR, Classic Pivots, gap/open relationships, and
prior-session 1H context remain contract-local. If required evidence crosses
different actual contracts, that relationship is unavailable; the retention
or continuous-view layer never creates a synthetic cross-contract reference.
