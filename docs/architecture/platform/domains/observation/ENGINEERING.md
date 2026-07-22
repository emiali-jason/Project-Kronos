# Observation Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-002 — Observation into one primary Observation engineering component while preserving existing evidence-engine ownership.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-002 — Observation](ARCHITECTURE.md).

## Engineering Responsibility

Realize the approved Market Facts responsibility and make observed facts available to Validation without deciding what they mean.

## Responsibilities

- Consume the approved Instrument Identity Contract.
- Preserve factual production by existing market-data and evidence owners.
- Preserve the distinction between observed evidence and evidence approved for downstream influence.
- Publish only the approved Market Facts Contract.

## Explicit Non-Responsibilities

- Instrument Identity, Business Judgment, confidence ownership, direction, BUY READY / SELL READY, Risk Approval, execution timing, BUY NOW / SELL NOW, orders, positions, provider integration, Market Schedule, Runtime Configuration, or audit conclusions.
- Recreating the responsibilities of source evidence engines inside a second implementation path.

## Consumed Approved Contracts

- Instrument Identity Contract.

## Published Approved Contracts

- Market Facts Contract.

## Allowed Dependencies

- Business-domain dependencies: Instrument only.

## Prohibited Dependencies

- Direct business-domain dependencies on Validation, Risk, Execution, or Portfolio.
- Access to Instrument internals rather than the Instrument Identity Contract.
- Any direct dependency justified only by a transitive path.

## Existing KR Engine Alignment

- Existing market-data, indicator, structure, and evidence engines retain their individual ENGINE_OWNERSHIP responsibilities.
- KES remains an unnumbered synthesis boundary and does not acquire evidence generation, confidence, decision, execution, trade-management, alert, or presentation ownership.
- KR-360 confidence and KR-370 decision remain outside Observation and align to Validation.

## Existing Implementation Alignment

- Current market-data and evidence sections are present in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`, including KR-260B, KR-260, KR-270, KR-271, KR-275, KR-280, and KR-300 through KR-350 evidence owners.
- The source is monolithic; no independently packaged Observation component exists.

## Open Engineering Questions

- Which current public evidence outputs form the approved Market Facts Contract without broadening their existing influence?
- Which evidence outputs remain observational only and therefore must not be wired into Validation in this release?
