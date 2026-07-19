# Architecture Questions

**Status:** Draft Research / Future Backlog  
**Active Phase:** Phase 1 only

These questions are reserved for a future explicitly authorized Architecture Discovery phase. They are not proposals and must not be answered by silently inferring architecture.

## Product Boundary

1. How should a future Options execution module relate to the approved KRONOS Core directional contract?
2. Which option-specific concerns are execution-vehicle concerns, and which—if any—would require separately approved evidence changes upstream?
3. What belongs in future KRONOS Options rather than Discovery, Intraday, Swing, Portfolio, Execution, or Engineering?
4. Does the current approved classification of Options as a future execution module remain sufficient after evidence review?

## Information and Behavior

5. Should Greeks, volatility, option-chain state, liquidity, expiry, and settlement be first-class concepts, derived context, or external evidence?
6. How should leg-level and position-level exposure coexist without losing lifecycle history?
7. How should rolls, adjustments, hedges, and directional futures positions preserve intent and attribution?
8. How should missing, stale, reconstructed, or conflicting option data be represented?
9. How should expiry regimes and futures devolvement affect a future product boundary?

## Relationship to Approved Architecture

10. Would a future Options capability require a new Execution Context Provider, and what approved decision would authorize it?
11. Which existing approved interfaces can remain unchanged, and which missing contracts would require formal proposals?
12. How would deterministic explainability apply to nonlinear and multi-leg positions without embedding unvalidated trade logic?
13. How would model-trade concepts relate to options positions without redefining approved KR-390 ownership?
14. Which questions are already answered or constrained by approved platform governance, product architecture, ADRs, ADLs, and interfaces?

## Evidence and Promotion

15. What minimum validation evidence is required before proposing ownership or interfaces?
16. Which source claims have survived independent, product-specific testing?
17. What evidence would justify an Architecture Candidate rather than continued research?
18. Which approved artifact types would be required for any later promotion?

No answer in Phase 1 may create de facto architecture.
