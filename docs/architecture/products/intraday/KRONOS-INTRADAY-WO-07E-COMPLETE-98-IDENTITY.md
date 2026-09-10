# WO-07E complete current-universe visual identities

Status: Sponsor-authorized engineering candidate; not published or loaded.
Authority: [ADR-0034](../../adr/ADR-0034-INTRADAY-STABLE-MCX-VISUAL-FAMILY.md).

## Capability scope

Publication KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1 / 1.7.0 preserves all 95 relationships in 1.6.0 and adds eleven: NIFTY plus five native and five reference visual families. This gives 91 NSE equities + 2 indices + 5 paired MCX families = 98 visual identity capabilities. This denominator is not a commissioning count or proof of expiry from chart pixels.

| Native subject | Exact native label (MCX) | Exact supporting label | Reference venue |
|---|---|---|---|
| MCX-SUBJECT-CRUDE | Crude Oil Futures | Light Crude Oil Futures | NYMEX |
| MCX-SUBJECT-COPPER | Copper Futures | Copper Futures | COMEX |
| MCX-SUBJECT-GOLDM | Gold Mini Futures | Gold Futures | COMEX |
| MCX-SUBJECT-NATGAS | Natural Gas Futures | Natural Gas Futures | NYMEX |
| MCX-SUBJECT-SILVERM | Silver Mini Futures | Silver Futures | COMEX |

NIFTY resolves `Nifty 50 Index` to `NSE-INDEX-NIFTY`. BANKNIFTY retains `Nifty Bank Index` to `NSE-INDEX-BANKNIFTY`. The 91 exact equity relationships, M&M punctuation and CSV bytes are unchanged.

## Source and time

`data/instruments/KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1/1.7.0-source-evidence.json` retains the source manifest with original/copy hashes, visible labels, separate file/capture timestamps and panel roles. It contains historical pre-decision resolver observations as source audit context, not current successor results. Original PNGs remain in the isolated Sponsor source evidence output; they are not an unnecessary permanent raw Git archive.

Conservative new relationship effective starts (UTC):

- NIFTY: 2026-09-10T11:56:50.252121+00:00.
- NATGAS native/reference: 2026-09-10T11:56:57.829206+00:00.
- CRUDE native/reference: 2026-09-10T11:57:37.943045+00:00.
- COPPER native/reference: 2026-09-10T11:58:01.794521+00:00.
- GOLDM native/reference: 2026-09-10T11:58:25.539199+00:00.
- SILVERM native/reference: 2026-09-10T11:58:32.251415+00:00.

BANKNIFTY and equities retain their older intervals. Export-only equities still begin at 17:18:30.613955 IST. None of the later source evidence rewrites the 10 September 17:03 Review. A new Review after the applicable starts is required for successor authority.

## Preserved workflow and residual trust

KRONOS selects and retains the exact native contract and shows it in the Question PDF. Sponsor opens that contract. Chart Analyst reports only independently visible family/venue/role/timeframe/content and temporal evidence. No invisible expiry is requested; family is not expiry proof. The native exact contract and integrity-bound selection remain recorded separately in the bundle and imported evidence.

Same-family wrong-expiry pixels can be indistinguishable; Sponsor explicitly accepts chart-selection responsibility. This is not an accidental validation bypass. Wrong family, venue, role, timeframe, revision, machine metadata, binding, unreadable identity and known temporal contradictions remain rejected. Reference context is supporting-only and is never promoted to independent machine correspondence or trading authority.

Transport 1.4.0 retains one Sponsor Question PDF per generated successor, an internal template, and the same exact Answer inbox lookup. Historical PDFs/Answers stay distinct. Q1-Q10/R/M/X meanings, strict V2 schema, machine-selected anchor NOT_ESTABLISHED, and the temporal contradiction model are unchanged.

## Qualification interpretation

The five-family workflow cases are synthetic deterministic engineering fixtures, not new live observations or Analyst responses. NATGAS commissioning is enabled only by the existing isolated test fixture and remains HELD in production. Gold/Silver supplied images are identity sources; their incomplete paired layouts are not claimed as positive complete Answer composites.

Rollover tests use the governed machine selector and unchanged visual publication. CRUDE, COPPER, GOLDM and NATGAS obtain a different successor contract under current calendar coverage. SILVERM next-expiry selection remains unavailable beyond the 2026 calendar, while visual identity stays valid; no calendar expansion is fabricated.

No WO-07F reconciliation is added. Existing reconciliation handoff/restoration is exercised without creating reconciliation requests or trade authority. No production operation, staging, commit, push or runtime load is part of this candidate.
