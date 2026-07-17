# PP-007 — Execution Semantics Across Markets

**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.0

---

# Purpose

Establish a single execution model for all KRONOS products and markets.

Execution semantics shall remain identical regardless of instrument or exchange. Market-specific behaviour shall be encapsulated within dedicated Execution Context Providers.

---

# Principle

Execution authorization has identical meaning across all supported markets.

Examples include, but are not limited to:

- NSE Equities
- NSE Futures
- MCX Futures
- US Equities
- Future supported products

The meaning of execution states shall never vary by market.

---

# Architectural Rule

Market-specific interpretation shall never exist inside execution authorization components.

Execution authorization consumes standardized execution context produced by the appropriate Execution Context Provider.

---

# Responsibilities

Execution Context Provider

Responsible for:

- Market interpretation
- Product interpretation
- Timing interpretation
- Qualification of execution context

KR-380

Responsible for:

- Consuming standardized execution context
- Consuming BUY READY / SELL READY from KR-370
- Determining execution authorization
- Producing BUY NOW / SELL NOW

---

# Benefits

This principle provides:

- Market neutrality
- Deterministic execution
- Single execution engine
- Independent market onboarding
- Reduced architectural coupling

---

# Exceptions

Any deviation from identical execution semantics requires an approved Architecture Decision Record (ADR).

No implementation may introduce market-specific execution semantics without an approved ADR.

---

# Related Documents

- ADR-006 — Execution Context Provider Architecture
- ECIC-001 — Execution Context Interface Contract
- ECM-001 — Execution Context Model
