# BK-001 — *Trading Option Greeks*

**Status:** Draft Research  
**Author:** Dan Passarelli  
**Review status:** Practical extraction completed and accepted  
**Rights boundary:** External book; no PDF or copied passage is stored here.

## Observation

The source treats an option position as simultaneous exposure to direction, changing directional sensitivity, time, and implied volatility. A correct directional opinion can still produce a loss when the selected contract carries unsuitable exposures.

## Evidence

- Delta is a changing directional sensitivity, not a constant or exact probability.
- Gamma describes changing delta and can concentrate near ATM as expiry approaches.
- Positive theta in short-option positions commonly accompanies negative gamma.
- Vega, skew, term structure, events, and direction-volatility interaction affect option value.
- Position Greeks provide an aggregate view; leg-level exposure remains necessary when strikes or expiries reprice differently.
- At-expiry payoff diagrams do not describe the complete pre-expiry risk path.
- Liquidity, spreads, model limitations, and realistic exits are part of position risk.

## Possible Interpretation

Future Options research should study whole-position exposure and its evolution rather than select a strike from one Greek or distance measure. This is a research direction, not strike logic.

## Open Questions

- How well do model Greeks explain actual MCX option P&L during large moves and thin markets?
- How should gamma/theta, skew, term structure, and events be studied across the intended holding horizons?
- Which risk observations remain stable under current contract specifications and market microstructure?

## Not Retained

- Delta as an exact expiry probability.
- Any universal moneyness preference.
- Any strike, expiry, IV, Greek, premium, or loss threshold.
- Any architecture or implementation implication.

The detailed local extraction remains source material and is not copied into this summary.
