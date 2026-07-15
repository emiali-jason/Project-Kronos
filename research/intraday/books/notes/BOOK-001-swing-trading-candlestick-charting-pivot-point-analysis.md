# Intraday Research Note

## Metadata

- Research ID: BOOK-001
- Source Type: Booklet
- Title: *Swing Trading Using Candlestick Charting with Pivot Point Analysis*
- Author: John L. Person
- Published Date: 2002
- Citation: John L. Person, *Swing Trading Using Candlestick Charting with Pivot Point Analysis* (2002), 16 pages
- Date Collected: 2026-07-15
- Source Artefact Status: External copyrighted PDF inspected; not copied into Git
- Source Manifest: [BOOK-001](../source-manifests/BOOK-001-source-manifest.md)
- Review Status: STRUCTURED
- Evidence Strength: ★★☆☆☆ practitioner booklet using selected retrospective examples
- Tags: #PivotPoints #Candlesticks #Execution #DecisionMaking #Confirmation #Validation #PatternRecognition #Risk

## Source Summary

Person introduces classic pivot-point calculations, selected Japanese candlestick formations, and a “multiple verification” approach that combines levels, patterns, trend context, and sometimes moving averages. The booklet uses futures examples across daily, weekly, monthly, hourly, and shorter time frames to argue that calculated levels can help frame possible support, resistance, targets, and trading plans.

The work is educational rather than empirical. Its demonstrations are selected historical charts where the calculated level or named candlestick pattern appears close to a subsequent turning point. The author repeatedly acknowledges that chart analysis is not exact, but the booklet does not disclose a complete sample, unsuccessful cases, selection method, costs, or reproducible performance study.

## Verified Facts

- The PDF identifies John L. Person as author and displays a 2002 copyright.
- The document is a 16-page booklet organized around pivot points, multiple verification, candlestick charting, and combined examples.
- The stated pivot formula is based on the prior period's high, low, and close, with derived support and resistance levels.
- The booklet contains examples from sugar, silver, U.S. Treasury bonds, the Dollar Index, Dow futures, and S&P futures.
- These are facts about the document and its calculations, not verification of predictive value.

## Observed Behaviour

- The booklet selects chart examples after the full outcome is visible.
- Several examples emphasize unusually close matches between a calculated level and a historical high or low.
- The author combines pivot levels with gaps, double bottoms, candlestick patterns, moving averages, and chart formations.
- Counterexamples are acknowledged generally, but no complete failure inventory is supplied.
- Numerical risk, entry, stop, and target illustrations are embedded in specific historical contracts and price scales.

## Speaker Interpretation

For this written source, “speaker” means the author's interpretation.

- Prior-period pivot calculations are interpreted as potential future support, resistance, breakout, or range levels.
- Candlestick formations are interpreted as warnings of reversal, continuation, indecision, or momentum change.
- Agreement among pivot levels, candlesticks, chart formations, fundamentals, and other indicators is interpreted as increasing forecast confidence.
- Longer-time-frame pivot calculations are interpreted as capable of producing larger market reactions.
- A precomputed level is interpreted as useful for planning even when the exact market reaction remains uncertain.

## Personal Opinion

- The strongest research value is the separation between a pre-session reference level and later observed price behaviour.
- “Multiple verification” is not automatically independent confirmation. Pivot levels, candlesticks, moving averages, gaps, and chart patterns frequently reuse the same OHLC history.
- Near-matches in selected charts cannot establish accuracy without an explicit tolerance, denominator, comparison baseline, and all eligible examples.
- The booklet's acknowledgement that analysis is not exact is important, but does not resolve selection bias or live-execution ambiguity.

## Main Claims

### Claim 1 — Pivot calculations identify useful future reference levels

- Claim: Prior-period high, low, and close can produce support and resistance levels useful for the next period.
- Evidence presented: Selected historical futures charts and numerical examples.
- Evidence type: personal experience; anecdotal case examples
- Scope and limitations: No population test, error distribution, or benchmark against ordinary prior highs, lows, or volatility bands.

### Claim 2 — Multiple techniques improve signal reliability

- Claim: Agreement among several technical techniques improves the chance of an accurate forecast.
- Evidence presented: Chart examples combining pivot points with gaps, patterns, and candlesticks.
- Evidence type: practitioner interpretation
- Scope and limitations: Shared underlying data may make the signals dependent rather than independently confirmatory.

### Claim 3 — Candlestick formations identify reversals or continuation

- Claim: Named candle formations convey changes in market control, indecision, reversal risk, or continuation.
- Evidence presented: Pattern definitions and selected charts.
- Evidence type: traditional practitioner framework; anecdotal
- Scope and limitations: Pattern definitions, context, confirmation, and tolerance require precise prospective specification.

### Claim 4 — Combining pivot levels and candlesticks improves planning

- Claim: A calculated level plus a recognized candle pattern provides a stronger basis for entry, risk, and exit planning.
- Evidence presented: Historical examples where both appear near a turning point.
- Evidence type: anecdotal case study
- Scope and limitations: Failed combinations and real-time observability are not recorded.

### Claim 5 — Longer calculation periods produce larger reactions

- Claim: Weekly or monthly pivot levels tend to generate larger reactions than shorter-period levels.
- Evidence presented: Author experience and examples.
- Evidence type: unsupported practitioner generalization
- Scope and limitations: Reaction magnitude, volatility adjustment, and selection criteria are undefined.

## Claims Requiring Validation

| Claim | Classification | Research treatment |
| --- | --- | --- |
| Pivot levels forecast future support and resistance better than simple reference levels. | NEEDS VALIDATION | Require a complete event set, exact tolerance, baseline, costs, and out-of-sample testing. |
| Several price-derived techniques provide independent confirmation. | NOT ESTABLISHED | Trace each input and transformation before assigning informational independence. |
| Named candlestick patterns have stable directional implications. | NEEDS VALIDATION | Define pattern, context, horizon, invalidation, and all failures before testing. |
| Longer-time-frame pivots cause larger reactions. | UNSUPPORTED CAUSAL CLAIM | Test association after normalizing for volatility and market regime; do not infer causality. |

## Market Topics

- Market structure: futures examples only; no exchange mechanics analysis.
- Opening process: prior-period levels may be available before the session, but opening-auction mechanics are not discussed.
- Market regime: trend and reversal context are used informally; no regime model is defined.
- Risk: examples include planned stops and bounded loss, but parameters are contract-specific.
- Execution: entry after pattern confirmation and exits near calculated levels.
- Position management: stop movement and target liquidation appear in examples.
- Liquidity, VWAP, news processing, and relative strength: not substantively addressed.

## Observable Research Questions

- Can every candidate pivot interaction be recorded prospectively with a fixed tolerance and horizon?
- Do pivot-derived levels add information beyond prior high, low, close, range, gap, and volatility?
- Does a candlestick condition add incremental information after accounting for the same underlying OHLC data?
- How often are named patterns recognizable only after later bars complete the narrative?
- What failure and transaction-cost distributions accompany the selected successful examples?

## Potential KRONOS Relevance

- Information Hierarchy: prior-session levels are known before later session behaviour.
- Confirmation Philosophy: useful case study in shared-data confirmation.
- Opening Process: possible distinction between pre-session context and observed opening response.
- Execution Philosophy: prospective recognition and actionability must be separated from retrospective appearance.
- Validation Framework: complete event capture and failure preservation are essential.

## Extracted Principles

No new extracted principle is created. The source may illustrate existing records:

- [EP-004 — Shared Data Is Not Independent Confirmation](../../extracted-principles/EP-004-shared-data-is-not-independent-confirmation.md)
- [EP-005 — Retrospective Visibility Does Not Prove Live Executability](../../extracted-principles/EP-005-retrospective-visibility-does-not-prove-live-executability.md)
- [EP-010 — Lifecycle Provenance Is Needed to Attribute Failure](../../extracted-principles/EP-010-lifecycle-provenance-is-needed-to-attribute-failure.md)

## Architecture Candidates

No new candidate is created or approved.

- [AC-004](../../architecture-candidates/AC-004-confirmation-meaningful-information.md) — multiple price-derived techniques may not be independent.
- [AC-005](../../architecture-candidates/AC-005-historical-appearance-not-live-executability.md) — evidence is presented retrospectively.
- [AC-010](../../architecture-candidates/AC-010-validation-preserves-decision-lifecycle.md) — a valid test must retain pre-session level, observed pattern, decision, execution, and outcome.

## Non-Architectural Content

- Pivot formulas and support/resistance levels.
- Candlestick definitions and named patterns.
- Moving-average periods, gaps, chart formations, and time-frame settings.
- Entry, stop, target, and trade-management examples.

These are preserved for traceability only. No formula, pattern, threshold, stop, target, or trading rule is recommended.

## Key Statements — Paraphrased

- Pivot levels are framed as advance reference points rather than certain predictions.
- A trading plan should be prepared before the market reaches a potential level.
- No individual chart technique is treated as infallible.
- The author prefers agreement among several analytical techniques.
- Candles describe the relationship among open, high, low, and close.
- Pattern meaning depends on location within an existing trend.
- Historical examples can look unusually precise while the method remains inexact.
- Risk planning is presented as necessary even when several techniques agree.

## Final Research Assessment

- Source credibility: Identifiable experienced practitioner booklet.
- Source quality: MODERATE provenance; LOW validation strength.
- Architectural usefulness: Moderate for confirmation and validation questions, low for direct design authority.
- Evidence quality: Low; selected examples without systematic testing.
- Main contribution: Makes precomputed reference levels and multi-technique confirmation explicit research objects.
- Main limitation: Selection bias, shared data, undefined tolerances, and no complete performance record.

## Related Research

- [YT-008 — Master Class on CPR](../../youtube/notes/YT-008-master-class-on-cpr.md)
- [BOOK-003 — Martin Pring on Market Momentum](BOOK-003-martin-pring-on-market-momentum.md)
- Topics: [Decision Making](../../topics/decision-making/README.md), [Execution](../../topics/execution/README.md), [Opening Auction](../../topics/opening-auction/README.md), [Market Regime](../../topics/market-regime/README.md)
