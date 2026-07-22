# Instrument Engineering Component
Status: Draft
Owner: Chief Architect

## Purpose

Translate DOMAIN-001 — Instrument into one primary Instrument engineering component while preserving approved Instrument Identity ownership and existing KR engine boundaries.

## Platform Domain Trace

- Exactly one domain: [DOMAIN-001 — Instrument](ARCHITECTURE.md).

## Engineering Responsibility

Realize the approved Instrument Identity responsibility without creating Market Facts, Business Judgment, or any downstream business meaning.

## Responsibilities

- Preserve canonical instrument, market identity, classification, and approved analysis/reference/execution relationships.
- Preserve the approved identity, mapping, classification, relationship, and routing responsibilities of KR-200, KR-250, KR-251, KR-252, and KR-260A.
- Publish only the approved Instrument Identity Contract.
- Keep distributed engine responsibilities distinct within the component alignment.

## Explicit Non-Responsibilities

- Market Facts, Business Judgment, Risk Approval, execution timing, orders, positions, provider integration, Market Schedule, Platform Events, Runtime Configuration, or Audit Trail.
- Reinterpreting KR-370 direction/readiness or KR-380 execution states.
- Merging or reassigning existing KR engine ownership.

## Consumed Approved Contracts

- None from another business domain.

## Published Approved Contracts

- Instrument Identity Contract.

## Allowed Dependencies

- Business-domain dependencies: None.
- Platform-supplied values may support identification only without owning or altering Instrument Identity.

## Prohibited Dependencies

- Any business-domain dependency.
- Direct access to another component’s internals or any transitive dependency treated as direct authority.

## Existing KR Engine Alignment

- KR-200: market and instrument identity portion of its approved ownership.
- KR-250: asset-to-reference mapping and dependency profile.
- KR-251: market-model classification and approved instrument semantics.
- KR-252: approved instrument relationships.
- KR-260A: approved symbol routing and analysis/execution selection.

## Existing Implementation Alignment

- Relevant KR-200, KR-250, KR-251, KR-252, and KR-260A sections exist in `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`.
- No independently packaged Instrument component exists; this Draft does not create one or prescribe code structure.

## Open Engineering Questions

- Which existing public outputs collectively satisfy the approved Instrument Identity Contract?
- How should a future implementation preserve one component boundary while retaining each engine’s exclusive ownership?
