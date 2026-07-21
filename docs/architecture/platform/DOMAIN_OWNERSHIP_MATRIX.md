# KRONOS Domain Ownership Matrix
Status: Approved
Owner: Chief Architect
Version: 1.0

## Purpose

Assign each platform-level semantic responsibility to exactly one KRONOS domain.

## Single Ownership Matrix

| Responsibility | Owner |
| --- | --- |
| Instrument Identity | Instrument |
| Market Facts | Observation |
| Business Judgment | Validation |
| Risk Approval | Risk |
| Orders | Execution |
| Positions | Portfolio |
| Provider Integration | Provider |
| Market Schedule | Market |
| Runtime Configuration | Configuration |
| Platform Events | Event |
| Audit Trail | Audit |

## Ownership Rules

1. Each listed responsibility has exactly one owning domain.
2. Ownership includes the authoritative semantic meaning of the responsibility.
3. Consumers may use an owned contract but must not recreate its meaning.
4. Platform support does not acquire ownership of the business information it carries.
5. Audit ownership is limited to the Audit Trail and does not include the responsibilities being observed.
6. New responsibilities require an explicit owner before approval or implementation.
7. Reassignment of a listed responsibility requires an approved Architecture Decision Record.

## Existing KRONOS Alignment

- KR-200 retains its approved engine responsibilities. Its instrument-identity responsibility aligns to Instrument; its approved Exchange Availability production aligns to Market.
- Existing evidence engines retain their individual ENGINE_OWNERSHIP boundaries while their published market facts align to Observation.
- Business Judgment is a domain-level responsibility and does not merge the distinct KR-360 confidence and KR-370 decision engine responsibilities.
- KR-370 remains the engine owner of direction and BUY READY / SELL READY within Business Judgment.
- KR-380 remains the engine owner of final execution timing and BUY NOW / SELL NOW within Execution.
- The Orders assignment reserves order semantics to Execution; the current KRONOS execution contract does not place broker orders.
- KR-390 remains the owner of the objective KRONOS model trade within Portfolio. No personal broker-position ownership is introduced.
- KR-400 retains confirmed alert-event ownership within Event.
- Provider Integration does not redefine the separate Execution Context Provider role approved by ADR-006.

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](DOMAIN_DEPENDENCY_MATRIX.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
