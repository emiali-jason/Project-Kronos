# Intraday Product Architecture

**Status:** Living product architecture
**Owner:** KRONOS Intraday
**Authority:** Sponsor/EA/CA governed work orders

## Purpose

This directory indexes the governed Intraday product records. Source documents
retain their own authority and status; this index grants no additional trading,
Risk, execution, or broker authority.

## Current authority through WO-09

The [WO-01B Current Authority Manifest V1](KRONOS-INTRADAY-CURRENT-AUTHORITY-MANIFEST-V1.json)
is the **Approved WO-01C publication edition**, qualified against develop
`782e51e52ed621d03881f59f13412a21d41b4f14` on 2026-09-07. It records the accepted
WO-01A reconciliation and subsequent Sponsor WO-09 producer-advance decision.
Its own publication is established by its containing commit on origin/develop;
Git history supplies the exact SHA. An unpushed copy is not publication.
The dated Living Master closure records final publication and closure proof.
The baseline identifies inspected source, not the currently loaded runtime.

Its six independent dimensions are APPROVED_POLICY, IMPLEMENTED, PUBLISHED,
RUNTIME_ACCEPTED, OPERATIONALLY_PROVEN and EMPIRICALLY_QUALIFIED. Historical
statements remain visible with explicit successors. Classification counts may
overlap: an OPEN_CORRECTION can also be CONTRADICTORY or MISSING. Evidence
references distinguish repository code, retained operational evidence, Sponsor
decisions and research; engineering success does not imply predictive usefulness.

The WO-09 producer-advance rule is approved policy only: implementation,
publication, runtime acceptance and operational proof remain NO. WO-05/06/07
corrections remain open. WO-04 is skipped; WO-08 remains conditional/skipped.
BR2 remains CLOSED_WITH_SPONSOR_INPUT_PENDING. This manifest grants no runtime,
import, acquisition, trading or broker authority and is not consumed by runtime.

Validate from the repository root without loading production composition:

```sh
python3 tools/validate_intraday_authority_manifest.py
python3 -m pytest tests/unit/architecture/test_intraday_current_authority_manifest.py
```

The validator is a bounded executable schema for manifest version 1.0.0. It
requires all material capabilities, explicit statuses, evidence and owned open
corrections. Later approved reconciliations must revise the version and gates
explicitly; old decisions and evidence are not silently rewritten.

## Documents

- [Responsibilities](RESPONSIBILITIES.md)
- [Interfaces](INTERFACES.md)
- [Constraints](CONSTRAINTS.md)
- [Future](FUTURE.md)
- [Living Architecture Record V0.1](KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md)
- [Slice 3V Validation Contract V1](KRONOS-INTRADAY-SLICE-3V-FACTUAL-VISUAL-VALIDATION-CONTRACT-V1.md)
- [Native Universe V1](KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md)
- [Native Discovery V0 Contract](KRONOS-INTRADAY-NATIVE-DISCOVERY-V0-CONTRACT.md)
- [WO-05 Native Discovery Runtime](KRONOS-INTRADAY-WO-05-NATIVE-DISCOVERY-RUNTIME.md)
- [WO-05A Operational Invocation](KRONOS-INTRADAY-WO-05A-OPERATIONAL-INVOCATION.md)
- [WO-05B Bounded Operational Control](KRONOS-INTRADAY-WO-05B-BOUNDED-OPERATIONAL-CONTROL.md)
- [WO-06 Part-1 Qualification Foundation](KRONOS-INTRADAY-WO-06-PART-1-QUALIFICATION-FOUNDATION.md)
- [WO-06 Part-2 Probables Methodology Research](KRONOS-INTRADAY-WO-06-PART-2-PROBABLES-METHODOLOGY-RESEARCH.md)
- [WO-06 Part-3 V0 Probables Methodology](KRONOS-INTRADAY-WO-06-PART-3-V0-PROBABLES-METHODOLOGY.md)
- [WO-06E Phase-Aware Probables V2 Methodology](KRONOS-INTRADAY-WO-06E-PHASE-AWARE-PROBABLES-V2-METHODOLOGY.md)
- [WO-06E Probables V2 Canonical Payload](KRONOS-INTRADAY-WO-06E-PROBABLES-V2-METHODOLOGY-PAYLOAD.json)
- [WO-06H Historical Qualification Reconstruction](KRONOS-INTRADAY-WO-06H-HISTORICAL-QUALIFICATION-RECONSTRUCTION.md)
- [WO-06HA Historical Research Operational Seam](KRONOS-INTRADAY-WO-06HA-HISTORICAL-RESEARCH-OPERATIONAL-SEAM.md)
- [WO-07 Governed Native Review](KRONOS-INTRADAY-WO-07-GOVERNED-NATIVE-REVIEW-V1.md)
- [WO-07A Sponsor Review UX and Batch Transport](KRONOS-INTRADAY-WO-07A-SPONSOR-REVIEW-UX-AND-BATCH-TRANSPORT-V1.md)
- [WO-10 E/I/M Frozen Architecture V1](KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
- [Historical WO-10 Native + Visual Reconciliation V1](KRONOS-INTRADAY-WO-10-NATIVE-VISUAL-RECONCILIATION-V1.md)
- [WO-12 KR-370 Analytical Promotion V1 — historical](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md)
- [WO-12 KR-370 Analytical Promotion V2 — current](KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md)
- [WO-12 K5 Fact Foundation V1 — supporting WO-15 research](KRONOS-INTRADAY-WO12-K5-FACT-FOUNDATION-V1.md)
- [WO-13 Step-31 Trade Construction V1](KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md)
- [WO-13 Step-31 canonical policy payload](KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1.json)
- [WO-14 DOMAIN-007 Risk Observation V1](KRONOS-INTRADAY-WO-14-DOMAIN-007-RISK-OBSERVATION-V1.md)
- [WO-15 KR-380 Entry Timing V1](KRONOS-INTRADAY-WO-15-KR380-ENTRY-TIMING-V1.md)
- [WO-15 canonical timing policy](KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json)
- [WO-16 Sponsor Decision and Session-Bounded Lifecycle Admission V1](KRONOS-INTRADAY-WO-16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md)
- [WO-16 canonical decision/admission policy](KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json)
- [WO-17 Position Evidence and Active Lifecycle Monitoring V1](KRONOS-INTRADAY-WO-17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1.md)
- [WO-17 canonical position/lifecycle policy](KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-POLICY-V1.json)
- [WO-B Operational Readiness Review V1](KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1.md)
- [V2 Review Successor Seam](KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM-V1.md)
- [DOMAIN-001 Prerequisite Manifest](KRONOS-INTRADAY-DOMAIN-001-PREREQUISITE-MANIFEST-V1.md)
- [Machine-Fact Catalogue](KRONOS-INTRADAY-MACHINE-FACT-CATALOGUE.md)
- [Contract/State Ownership Registry](KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Deferred Decision Register](KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md)
- [Programme Roadmap](KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md)

## Current governed boundary

Intraday owns its 98-member Native analytical universe, factual product
composition, immutable V1 Probables methodology, frozen phase-aware V2
Probables methodology, later promotion/construction policy,
product state, and product projections. It consumes DOMAIN-001, DOMAIN-006, DOMAIN-008, and other
Platform capabilities through governed seams. Native membership is not
execution eligibility.

## Change control

Follow the [Intraday Shared-File Change Rule](../../../engineering/INTRADAY-SHARED-FILE-CHANGE-RULE.md).
