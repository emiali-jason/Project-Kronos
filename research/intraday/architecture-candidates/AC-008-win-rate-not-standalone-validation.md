# AC-008 — Win Rate Is Not a Standalone Validation Measure

> Unapproved research candidate. Not an architecture decision, metric specification, or performance threshold.

## Candidate Metadata

- Candidate ID: AC-008
- Originating Research IDs: YT-006; YT-007
- Extracted Principle: [EP-008](../extracted-principles/EP-008-win-rate-alone-is-an-incomplete-performance-description.md)
- Created Date: 2026-07-15
- Lifecycle Status: ARCHITECTURE REVIEW

## Underlying Problem

Win rate omits the magnitude, sequence, costs, risk, and context of outcomes and can therefore misrepresent performance.

## Proposed Principle

The future Validation Framework should not assess a method using win rate alone. Relevant review dimensions may include:

- payoff distribution
- loss magnitude
- gain magnitude
- execution costs
- risk-adjusted performance
- behavioural compliance
- performance by market state
- stability through time

No metric, formula, weighting, or threshold is proposed.

## Research Traceability

| Research ID | Contribution | Evidence type | Limitation |
| --- | --- | --- | --- |
| YT-006 | Questions hit-rate assumptions and stresses outcome management. | Personal experience; conceptual explanation | No reproducible performance data. |
| YT-007 | Uses a low-win-rate fund anecdote to illustrate dependence on outcome magnitude. | Anecdotal | The fund and results are unverified. |

## Validation Required

- Review quantitative validation literature.
- Establish which dimensions are necessary for the future framework without selecting measures now.
- Examine interactions with market state and compliance.

## Review Outcome

- Status: ARCHITECTURE REVIEW
- Acceptance: Not granted
