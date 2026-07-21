# PLATFORM-000 — KRONOS Platform Constitution
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Establish the constitutional decisions that govern KRONOS Platform domains, responsibilities, dependencies, communication, human workflow, and architectural change.

This constitution preserves the approved responsibilities of KR-370, KR-380, the Execution Context Provider architecture, PP-007, ENGINE_OWNERSHIP, and DATA_FLOW.

## CA-013 — Domain Identity

Each domain has one stable identifier, one name, and one explicit architectural boundary.

A domain groups semantically related responsibilities. Domain identity does not merge existing engine responsibilities, permit duplicate ownership, or allow one domain to reinterpret another domain's published meaning.

The approved domains are:

- DOMAIN-001 — Instrument
- DOMAIN-002 — Observation
- DOMAIN-003 — Validation
- DOMAIN-004 — Execution
- DOMAIN-005 — Portfolio
- DOMAIN-006 — Provider
- DOMAIN-007 — Risk
- DOMAIN-008 — Market
- DOMAIN-009 — Event
- DOMAIN-010 — Configuration
- DOMAIN-011 — Audit

## CA-014 — Responsibility Classes

KRONOS Platform responsibilities are divided into three classes:

- Business responsibilities: Instrument, Observation, Validation, Risk, Execution, and Portfolio.
- Platform responsibilities: Provider, Market, Event, and Configuration.
- Oversight responsibility: Audit.

Business domains answer the approved business questions in PLATFORM_BUSINESS_PIPELINE. Platform domains support business operation without acquiring business judgment. Audit observes all domains read-only and does not participate in business decisions.

## CA-015 — Contract-Based Dependencies

A domain may depend on another domain only through an explicitly published and consumed semantic contract.

Consumers depend on the contract's meaning, not on the producer's internal reasoning or implementation. A dependency does not transfer ownership from producer to consumer.

Allowed business dependencies are recorded in DOMAIN_DEPENDENCY_MATRIX. Any new dependency requires Chief Architect approval and an architectural decision.

## CA-016 — Single Semantic Ownership

Every platform responsibility and every published semantic meaning has exactly one owning domain.

A consumer may use an owned meaning but must not recreate, reinterpret, supplement, or replace it. Multiple current engines may contribute facts within their existing ENGINE_OWNERSHIP boundaries, but the same platform semantic responsibility must not be assigned to multiple domains.

DOMAIN_OWNERSHIP_MATRIX is the authoritative platform-level ownership map.

## CA-017 — Domain Communication (Platform Only)

The mechanism by which domains communicate is a platform responsibility and is not business logic.

Business domains declare semantic dependencies and exchange only approved contracts. They do not own communication mechanisms and do not depend on a particular transport, storage model, or runtime technology.

Platform support must not alter contract meaning, create business judgment, or introduce a second path around an approved dependency.

## CA-018 — Human Workflow Independence

Completion of a domain responsibility must not depend on an undocumented manual interpretation or hidden human handoff.

Human review, presentation, approval, and action may consume platform outputs where explicitly authorized, but they do not silently replace domain ownership or contract completion.

Current BUY NOW and SELL NOW remain confirmed KR-380 execution-timing states and are not broker orders. Human or broker action remains outside the current execution contract unless separately approved.

## CA-019 — Architecture Freeze

Version 1.0 of the following approved documents is frozen after approval:

- PLATFORM-000 — KRONOS Platform Constitution
- PLATFORM_OVERVIEW
- PLATFORM_BUSINESS_PIPELINE
- DOMAIN_DEPENDENCY_MATRIX
- DOMAIN_OWNERSHIP_MATRIX
- DOMAIN-001 through DOMAIN-011 architecture documents

A frozen responsibility, dependency, ownership assignment, or constitutional decision may change only through a new Architecture Decision Record approved by the Chief Architect. Engineering, implementation convenience, or an undocumented workflow must not alter frozen architecture.

## Existing Authority Preserved

- KR-370 retains direction and BUY READY / SELL READY ownership.
- KR-380 retains final execution timing and BUY NOW / SELL NOW ownership.
- KR-380 remains the sole currently authorized consumer of the entry Execution Context.
- Execution Context Providers do not own direction, readiness, final execution authorization, BUY NOW, SELL NOW, or trade management.
- Execution semantics remain market-neutral under PP-007.
- Existing engine ownership and information flow remain governed by ENGINE_OWNERSHIP and DATA_FLOW.

## Related Approved Documents

- [KRONOS Platform Governance](../../product/PLATFORM_GOVERNANCE.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [ADR-006 — Execution Context Provider Architecture](../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-003 — Execution Context Adapters](../ADL-003-Execution-Context-Adapters.md)
