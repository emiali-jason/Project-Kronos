# EX-001 — MCX Options Mechanics

**Status:** Draft Research  
**Sources:** [MCX Options overview](https://www.mcxindia.com/options); [MCX exercise-mechanism FAQ](https://www.mcxindia.com/gu/faq/changes-in-options-exercise-mechanism)  
**Source type:** Exchange material  
**Review status:** Reviewed for expiry-mechanics cross-check

## Observation

MCX commodity options are options on commodity futures. Expiry can create a futures position rather than ending with only a cash premium outcome.

## Evidence

- MCX states that exercised commodity options devolve into the corresponding futures contract and that devolved futures open at the strike price.
- For applicable contracts launched from February 2022 onward, ITM options are exercised automatically unless the long holder gives contrary instruction.
- OTM options expire worthless under the stated mechanism.
- Exercised contracts are assigned to short positions within the series through the exchange mechanism.
- MCX advises users to consult current contract specifications and circulars.

## Possible Interpretation

Expiry research must include the resulting futures exposure, margin, broker handling, position limits, and delivery timeline. These mechanics are risk inputs, not trading rules.

## Open Questions

- Which current specification and circular governs each studied contract and expiry?
- What broker deadlines and margin policies apply before exchange expiry?
- How are contrary instructions, square-off, devolvement, and delivery handled operationally?

## Not Retained

No exchange mechanic is converted into a strategy, recommendation, or product design. Current exchange publications take precedence over this paraphrase.
