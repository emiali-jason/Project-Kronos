# PP-007 — Execution Semantics Across Markets

**Document ID:** PP-007
**Title:** Execution Semantics Across Markets
**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.1

**Canonical Status:** Not stated
**Classification:** Architecture Principle
**Prepared By:** Not stated
**Review Authority:** Not stated
**Repository Location:** `docs/architecture/principles/PP-007-Execution-Semantics-Across-Markets.md`

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
- Consuming an exact current, Risk-permitted downstream path derived from KR-370 analytical BUY NOW / SELL NOW and immutable Step-31 geometry
- Determining execution authorization
- Producing LONG_ENTRY_TRIGGERED / SHORT_ENTRY_TRIGGERED Entry Outcomes

KR-370 analytical BUY NOW / SELL NOW is a DOMAIN-003 analytical-promotion
classification and has no execution authority. KR-380 remains the sole owner of
final entry timing. Historical KR-380 BUY NOW / SELL NOW retains its original
meaning only under the historical Entry Outcome Version 1 contract.

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
- ADR-0011 — KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics
- ECIC-001 — Execution Context Interface Contract
- ECM-001 — Execution Context Model
