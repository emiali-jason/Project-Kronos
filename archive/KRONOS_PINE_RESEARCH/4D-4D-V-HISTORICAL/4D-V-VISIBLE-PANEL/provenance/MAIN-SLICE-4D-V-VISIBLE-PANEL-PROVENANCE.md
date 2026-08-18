# KRONOS Swing V1 Main Slice 4D-V — Visible Panel Provenance

## Contract and authority

- Panel contract: `KRONOS-SWING-V1-PINE-VISIBLE-EVIDENCE-V1`
- Panel version: `1.0`
- Publisher role: `CANDIDATE / SHADOW_ONLY`
- Webhook path: paused and absent from both 4D-V candidates
- OpenAI extraction: not implemented
- Production authority: unchanged

## Analytical lineage

The MCX candidate derives from the closed 4B candidate with SHA-256
`59f35175ea0c666fbadef00e6861f42e3c75b858a66891e3908657fd4bb0245d`
The NSE candidate derives from the closed 4C candidate with
SHA-256
`f7a5098b6c406303686a110849ba93c2a505ffa3e9bd2d6ba77b038aa1639a43`
as its analytical source.

Sponsor compilation exposed invalid explicit return-type prefixes on three
projection helper declarations inherited by each candidate. Pine infers
function return types and accepts parameter type annotations, so only the
leading `string` tokens were removed. The same correction was applied to all
twelve 4D-V helper declarations per candidate. Tests prove that the inherited
analytical source differs from the closed parent only by those three syntax
tokens and that no analytical expression changed.

- MCX 4D-V candidate SHA-256:
  `e19f40903139272acc51abdb7bc87007fee53daf8f5e3f93f4ad8254d5e4d1cd`
- NSE 4D-V candidate SHA-256:
  `a351e0fe7adc9b01e35023a124b7e41582790159d28f8c2ea350d2791ec4a52b`

The appended code performs table presentation only. It contains no new
indicator, threshold, market-data request, setup rule, Readiness rule, alert,
webhook dependency or OpenAI dependency.

## Geometry

Each chart renders one fixed two-column, 37-row table at top-right. It has two
stable sections and never removes a row dynamically. Required subordinate
facts are grouped into fixed `LABEL=VALUE` sequences so the full contract can
fit without hiding mandatory fields. The existing KR-705 workstation is moved
to bottom-right by presentation-only positioning to prevent direct overlap.

The visible panel uses `size.tiny`, matching a compact transport surface rather
than a discretionary dashboard. Readability in the Sponsor's normal four-chart
layout is not claimed by automated tests and requires TradingView validation.

## Explicit unresolved presentation

No new rule or tolerance was created. Fields lacking an existing deterministic
source are explicit `UNAVAILABLE`, including range high/low, SMA interaction,
SMA200 slope, bounded reference support/resistance and barrier price.

Known-truth MCX and NSE fixtures preserve product, instrument, timeframe,
boundary, Candidate role, all 14 domain rows and each product extension for the
future separately authorized 4E transcription comparison.
