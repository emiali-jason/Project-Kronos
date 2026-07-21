# KRONOS Domain Dependency Matrix
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Define the allowed semantic dependencies between KRONOS Platform domains.

A listed dependency authorizes consumption of an approved contract only. It does not authorize access to producer internals or transfer semantic ownership.

## Allowed Dependencies

| Domain | Depends On |
| --- | --- |
| Instrument | None |
| Observation | Instrument |
| Validation | Observation |
| Risk | Validation, Portfolio |
| Execution | Validation, Risk |
| Portfolio | Execution |
| Provider | None (Business) |
| Market | None (Business) |
| Event | None (Business) |
| Configuration | None (Business) |
| Audit | All domains (Read Only) |

## Dependency Rules

1. Dependencies are directional and contract-based.
2. A consumer may use only meanings published by the producer.
3. A consumer must not reconstruct, override, or supplement the producer's owned meaning.
4. Transitive dependency does not authorize direct access to an upstream domain.
5. Instrument begins the business pipeline and has no business-domain dependency.
6. Risk consumes the previously established Portfolio state together with current Validation judgment.
7. Execution consumes Validation judgment and Risk approval; it does not produce either.
8. Portfolio consumes completed Execution outcomes and publishes the resulting portfolio state for later decisions.
9. The Risk–Execution–Portfolio relationship is sequential across a business decision cycle and must not create circular authority.
10. Provider, Market, Event, and Configuration have no business judgment dependency. Their platform contracts may support domains without joining the business decision chain.
11. Audit may consume all published domain contracts read-only and must not become an upstream business dependency.
12. Any dependency not listed here requires an approved Architecture Decision Record.

## Existing KRONOS Alignment

- KR-370 remains upstream of KR-380 and owns direction and readiness.
- KR-380 consumes approved direction/readiness and Execution Context without reinterpreting either.
- KR-390 consumes confirmed KR-380 execution outcomes for objective model-trade state.
- Existing narrow adapter exceptions remain governed by ADL-003 and do not create new domain dependencies.

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Ownership Matrix](DOMAIN_OWNERSHIP_MATRIX.md)
- [ADL-003 — Execution Context Adapters](../ADL-003-Execution-Context-Adapters.md)
- [ADR-006 — Execution Context Provider Architecture](../adr/ADR-006-Execution-Context-Provider-Architecture.md)
