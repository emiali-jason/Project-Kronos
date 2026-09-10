# ADR-0032 - Intraday Chart Analyst correspondence source

**Status:** Sponsor-approved bounded product decision; engineering candidate, publication pending.
**Date:** 2026-09-10
**Decision owner / approval:** Sponsor / EA, explicit WO-07E independent observed chart source decision.
**Scope:** Intraday Review V2 transport and import only.

## Decision

KRONOS CHART ANALYST, operated through the existing Sponsor-assisted workflow,
is the independent visual observer. Immutable chart upload is followed by one
Question PDF, an independently completed Answer and exact governed-inbox import.
A second visual producer or a pre-Answer observation receipt is not required.
No OCR, alternate model, automated visual extraction or empirical call is added.

The versioned correspondence header carries independent panel observations.
Machine-owned envelope/slot bindings are separate from nullable observed facts.
Expected endpoints, calendar, canonical identity and intended contracts must
never populate an observed field. Unobservable precise timing remains unproven;
this decision does not relax the strict completed-panel comparator.

Import validates the Answer schema, exact pack/cycle/chart/candidate identity,
governed visual relationships, independent panel correspondence, required
question content and producer currentness before retaining observations. The
existing immutable receipt store is reused; current Answer publication follows
successful receipt and Answer retention. Historical receipts and pre-header
Answers retain their original identities and bytes. No upload, GET, restoration
or currentization fabricates a receipt from machine data.

NSE uses four native panels. MCX uses the same mechanism for eight panels;
native contract correspondence remains strict. NYMEX/COMEX remains supporting
visual context only and NOT_INDEPENDENTLY_ESTABLISHED. This grants no research,
Promotion, Risk, PAPER/LIVE, execution or broker authority.

## Supersession and preservation

This decision supersedes only the separate observation-producer prerequisite in
[WO-07B](../products/intraday/KRONOS-INTRADAY-WO-07B-CHART-INPUT-CORRESPONDENCE.md)
and the subsequent proposed upload-time producer work order. Historical wording
is preserved with this successor reference. It does not supersede
[ADR-0018](ADR-0018-DOMAIN-001-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-V1.md),
DOMAIN-001/008 or the published MCX asymmetric model. Identity publication 1.5.0,
FB02/FB03, analytical question meanings and methodology 2.2.0 are unchanged.

## Qualification and publication boundary

Constructed, isolated Answers must prove fresh ADANIGREEN, BANKNIFTY and the
five MCX families without injecting observation receipts. Wrong identities,
endpoints, scopes and bindings fail closed. Currentness, failure recovery,
idempotence, retained integrity and legacy compatibility require qualification.
The real Sponsor/Analyst workflow remains a post-publication operational check.
No production operations, staging, commit or push are authorized by engineering.

See the [engineering contract](../products/intraday/KRONOS-INTRADAY-WO-07E-ANALYST-CORRESPONDENCE.md).
