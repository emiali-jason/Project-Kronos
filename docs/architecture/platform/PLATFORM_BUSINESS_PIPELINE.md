# KRONOS Platform Business Pipeline
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Define the approved sequence of business responsibility across KRONOS Platform domains.

This is a semantic business flow. It does not replace the runtime information paths in DATA_FLOW or the engine responsibilities in ENGINE_OWNERSHIP.

## Approved Business Flow

**Instrument → Observation → Validation → Risk → Execution → Portfolio**

## Business Questions

| Domain | Answers |
| --- | --- |
| Instrument | What is it? |
| Observation | What happened? |
| Validation | What does it mean? |
| Risk | Is it allowed? |
| Execution | Do it. |
| Portfolio | What do I own now? |

## Flow Rules

1. Each domain answers only its approved business question.
2. Each answer is published as an owned semantic contract.
3. A downstream domain consumes the upstream contract without recreating its meaning.
4. Risk evaluates permission without creating business judgment or execution timing.
5. Execution acts only on approved upstream judgment and risk permission.
6. Portfolio records the resulting owned state without changing the completed execution decision.
7. Platform domains may support the flow but do not insert business judgment into it.
8. Audit may observe the flow read-only but must not participate in it.

## Existing KRONOS Alignment

- KR-370 direction and BUY READY / SELL READY remain the current approved business-judgment ownership within Validation.
- KR-380A remains the current entry Execution Context Provider within the approved Execution Context boundary.
- KR-380 remains the sole current entry Execution Context consumer and owns final execution timing and BUY NOW / SELL NOW.
- KR-390 retains ownership of the objective KRONOS model trade within the Portfolio responsibility.
- BUY NOW and SELL NOW are not broker orders.

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [Domain Dependency Matrix](DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](DOMAIN_OWNERSHIP_MATRIX.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
