# PROJECT KRONOS – ENGINEERING DECISIONS

This document records the major engineering and architectural decisions made during the development of PROJECT KRONOS.

It explains **why** decisions were made so they remain clear as the project evolves.

---

# Decision Log

---

## KD-001

**Date:** 2026-07-04

**Decision**

PROJECT KRONOS will use a modular engine architecture.

**Reason**

Each engine has a single responsibility, making the code easier to develop, test, maintain, and extend.

**Status**

Approved

---

## KD-002

**Date:** 2026-07-04

**Decision**

Development will occur on the `develop` branch.

Stable releases will be maintained on the `main` branch.

**Reason**

This protects the stable version while allowing active development.

**Status**

Approved

---

## KD-003

**Date:** 2026-07-04

**Decision**

One engine will be completed before starting the next engine.

**Reason**

Every engine should compile successfully before additional functionality is added.

**Status**

Approved

---

## KD-004

**Date:** 2026-07-04

**Decision**

KRONOS will operate as a Decision Support System (DSS) rather than an automated trading system.

**Reason**

The objective is to assist traders with transparent, explainable decisions while leaving execution under the trader's control.

**Status**

Approved

---

## KD-005

**Date:** 2026-07-04

**Decision**

Global market data will be used to guide local market analysis whenever applicable.

Examples:

- COMEX → MCX Metals
- NYMEX → MCX Energy

**Reason**

Global markets often establish the broader trend before local markets react.

**Status**

Approved

---

## KD-006

**Date:** 2026-07-04

**Decision**

The GitHub repository will contain complete project documentation alongside the source code.

**Reason**

Documentation should evolve together with the software to keep the project understandable and maintainable.

**Status**

Approved

---

## KD-007

**Date:** 2026-07-12

**Decision**

Adopt the Platform/Product identity:

- Platform = KRONOS.
- Current product = KRONOS Core.
- Historical product-specific filenames and runtime identifiers remain compatible until separately migrated.
- Product identity is broader than the current Cash and Futures execution modules.
- Product metadata changes require release-governance approval.

**Reason**

Separating platform identity, product identity, execution paths, and compatibility names allows KRONOS to evolve without breaking current Pine integrations or rewriting accurate project history.

**Status**

Approved

---

## KD-008

**Date:** 2026-07-13

**Decision**

KRONOS will separate local Daily trend foundation from the final consolidated multi-timeframe directional bias.

KR-300 remains the owner of Daily trend foundation. KR-341 owns the authoritative Weekly/Daily/4H directional bias for swing-trading decisions. KR-360 and KR-370 consume KR-341 where directional authority is required, while preserving their existing public contracts. KR-705 continues to display the public Decision output published by KR-370.

KR-341's swing contract treats Weekly Neutral as permissive, requires Confirmed Daily direction for READY permission, limits Developing Daily to WATCH support, and distinguishes Neutral from Conflicted evidence.

**Reason**

Live validation showed that an execution chart could display BUY READY or SELL READY while visible higher-timeframe context had not reached an equivalent consolidated decision. The audit confirmed this was an architectural gap: KR-370 was using KR-300 Daily direction directly because no dedicated multi-timeframe directional contract existed.

**Status**

Approved

---

# Future Decisions

All significant architectural decisions should be recorded here before implementation.

---

# Architecture Decision Linkage

The following Architecture Decision Logs extend this decision record. KD-001 through KD-006 remain preserved above.

| ADL | Decision | Relationship to existing decisions and assumptions |
|---|---|---|
| [ADL-001 - Futures Model Architecture](architecture/ADL-001-Futures-Model.md) | One Engine. Multiple Market Models. | Clarifies KD-001 and KD-005 by defining model-specific dependency profiles over common engines. Its 2026-07-10 amendment records current COMEX futures mappings and implementation status. |
| [ADL-002 - MCX Self-Contained Execution](architecture/ADL-002-MCX-Self-Contained-Execution.md) | The MCX execution chart must be self-contained. | Clarifies KD-005 and supersedes the old DD-004 assumption that the trader must depend on separate timeframe panels for execution understanding. |
| [ADL-003 - Execution Context Adapters](architecture/ADL-003-Execution-Context-Adapters.md) | Narrow adapters may bridge low-level data into execution engines. | Clarifies KD-001 by documenting a controlled exception to strict prior-public-output access without permitting duplicated intelligence stacks. |
| [ADL-004 - Model Trade Ownership](architecture/ADL-004-Model-Trade-Ownership.md) | KR-390 manages the objective KRONOS model trade independently of personal entry. | Clarifies KD-004: model analysis is not broker execution or personal-position tracking. |
| [ADL-005 - Alert Architecture](architecture/ADL-005-Alert-Architecture.md) | KR-400 owns confirmed BUY NOW and SELL NOW TradingView alert events. | Clarifies KD-004: actionable notifications do not convert KRONOS into an automated broker system. |

## Clarifications

### BUY NOW, SELL NOW, and Alerts

KD-004 remains in force. BUY NOW and SELL NOW are confirmed KR-380 execution-timing states, and KR-400 alerts are TradingView notifications. Neither state places a broker order or proves that the user entered a personal position.

### DD-004 Timeframe Assumption

The Engineering Manual's DD-004 assumption that Daily, 4H, and 1H should depend on separate future panel intelligence is superseded for the MCX execution workflow by ADL-002. Reference timeframes still provide distinct evidence, but KR-380A translates that evidence so the MCX 1H execution chart can explain its blockers without requiring separate chart inspection.
