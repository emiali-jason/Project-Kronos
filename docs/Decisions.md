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

# Future Decisions

All significant architectural decisions should be recorded here before implementation.