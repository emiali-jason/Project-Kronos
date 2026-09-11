# KRONOS Intraday — WO-07F Governed Visual Reconciliation

**Status:** Engineering Candidate
**Baseline:** `184c5017a0fecb2bcebf23931b993ff148f43b82`
**Production activation:** Not authorized

## Product result

WO-07F gives the Sponsor a deterministic answer to one bounded question: does
the correspondence-qualified chart evidence confirm the current machine Review
thesis, qualify it with conditions, contradict it, leave it insufficiently
established, or fail an upstream reconciliation prerequisite?

The five outcomes are `CONFIRMED`, `CONDITIONAL`, `CONTRADICTED`,
`INSUFFICIENT`, and `NOT_RECONCILABLE`. They are analytical facts. They do not
create a trade, a direction, a price, Risk permission, or broker authority.

## Current Review behavior

`RECONCILE ALL READY REVIEWS` now calls the WO-07F application. It no longer
dispatches the V2 Review population directly into the later WO-10 engine. The
page reads restoration status and shows, for each current candidate:

- readiness;
- retained outcome;
- ordered reason codes;
- downstream WO-10 evaluation eligibility.

The control is explicit. GET/status/startup paths never evaluate or persist a
result. Batch processing is ordered and candidate-isolated.

## Current eight-case read-only qualification

The accepted 10 September 2026 Review population was evaluated directly from
its retained V2 Answer and chart-correspondence evidence without creating a
production 07F record.

| Candidate | Direction | Outcome | Decisive reasons |
| --- | --- | --- | --- |
| YESBANK | SHORT | `CONDITIONAL` | weak/mixed base; obstacle close; visibly extended |
| JUBLFOOD | SHORT | `CONDITIONAL` | mixed broader context; weak/mixed base; obstacle close |
| VEDL | SHORT | `CONDITIONAL` | mixed context; no clear base; obstacle close; visibly extended |
| NIFTY | LONG | `CONTRADICTED` | Q4 failed or returned through |
| NTPC | SHORT | `CONDITIONAL` | mixed/congested/weak progression; obstacle close |
| INDIGO | SHORT | `CONDITIONAL` | no clear base; obstacle close; visibly extended |
| MOTHERSON | SHORT | `CONDITIONAL` | mixed/congested/weak progression; obstacle close |
| LUPIN | SHORT | `CONDITIONAL` | mixed structure/setup; obstacle close; visibly extended |

The distribution is 0 confirmed, 7 conditional, 1 contradicted, 0 insufficient,
and 0 not reconcilable. This distribution is not tuned. The exact retained
evidence determines it.

## Preservation

WO-07E remains unchanged: Q1–Q10 and R/M/X meaning, Answer schemas, temporal
header 1.1.0, identity publication 1.7.0, 98/98 identity capability, strict
correspondence, single/batch transport, MCX family/contract separation, and all
historical evidence remain intact. NATGAS commissioning remains held.

WO-06H acceptance, live-shadow window, methodology 2.2.0, Narrow CPR, Opening,
Probables, Review, and all later execution authority remain unchanged. No
Provider, Refresh, Discovery, OpenAI, Review, Risk, PAPER/LIVE, or broker action
is part of engineering or qualification.

## Downstream handoff

Only `CONFIRMED` and `CONDITIONAL` can be handed to later WO-10 evaluation.
Conditions remain attached. WO-10 may reject either outcome under its own
policy. It cannot reinterpret `CONTRADICTED` or `NOT_RECONCILABLE` as eligible.
WO-07F does not implement or alter WO-10.
