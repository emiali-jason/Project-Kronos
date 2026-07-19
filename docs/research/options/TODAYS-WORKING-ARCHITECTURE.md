# Today's Working Architecture — Research Map Only

**Status:** Draft Research  
**Product Architecture Status:** Not approved  
**Runtime Authority:** None

The title is retained from the requested knowledge-base section. This document is not an Options product architecture. It records only how the current research material is organized and the approved platform boundary that research must not change.

## Approved-Boundary Snapshot

The authoritative repository currently records:

- KRONOS Core as the shared intelligence product;
- Cash and Futures as current execution modules;
- Options as a future execution module that is not implemented;
- the approved principle that the BUY/SELL signal does not change merely because the execution vehicle changes;
- current engine ownership, Execution Context, execution, model-trade, alert, and presentation boundaries in approved architecture documents.

This research directory does not assign Options to an engine, define an Options provider, add a consumer, alter KR-370/KR-380/KR-390 responsibilities, or modify any public contract.

## Current Research Organization

```text
External books, videos, exchange material, and user observations
  -> source-level evidence summaries
  -> evidence matrix and limitations
  -> candidate principles and research hypotheses
  -> rejected claims and open questions
  -> future validation evidence
  -> explicit promotion decision, if ever authorized
```

This is a documentation lifecycle, not a runtime data flow.

## Current Working View

1. Phase 1 collects and classifies evidence.
2. Contract mechanics from authoritative exchange material may be recorded as mechanics; they do not create trading decisions.
3. Practitioner examples generate hypotheses and rejected-claim checks; they do not create rules.
4. User working practices remain observations until reconstructed from account and market evidence.
5. Candidate capabilities remain discovery questions without ownership or interfaces.
6. Approved KRONOS architecture remains unchanged unless a later, explicitly authorized governance process promotes a proposal.

## Explicit Non-Architecture

This document contains no:

- Options engine or component topology;
- ownership assignment;
- interface or payload;
- decision, strike, entry, exit, adjustment, or risk rule;
- threshold or scoring model;
- code or implementation sequence;
- ADR or architectural approval.
