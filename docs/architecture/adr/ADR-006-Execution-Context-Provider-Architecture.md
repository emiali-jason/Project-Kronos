# ADR-006 — Execution Context Provider Architecture

**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.0

---

# Context

KRONOS supports multiple products and markets.

Examples include:

- NSE Equities
- NSE Futures
- MCX Futures
- Future supported markets

Execution authorization should remain market-independent while allowing each market to express its own execution requirements.

Without a standard execution context, market-specific execution logic becomes tightly coupled to downstream execution components.

---

# Decision

Introduce an **Execution Context Provider** for each supported product or market.

The Execution Context Provider is responsible for evaluating market-specific execution prerequisites and producing a standardized Execution Context.

For entry execution authorization, KR-380A is the current concrete Execution Context Provider. KR-380 is the sole currently authorized consumer of the entry Execution Context.

KR-370 remains upstream of entry execution authorization. It owns direction and BUY READY / SELL READY and does not consume the Execution Context produced by KR-380A.

KR-380 consumes KR-370 direction/readiness together with the standardized Execution Context produced by KR-380A. KR-380 retains ownership of final execution timing and the production of BUY NOW / SELL NOW.

Additional consumers require a separate approved architecture decision. This ADR does not authorize them.

Execution Context consumers shall not interpret market-specific rules directly.

---

# Architecture

```
          Product and public intelligence logic
                   │                   │
                   ▼                   ▼
              KR-370              KR-380A
       Direction and readiness    Execution Context Provider
       BUY READY / SELL READY     Entry Execution Context
                   │                   │
                   └─────────┬─────────┘
                             ▼
                           KR-380
                  Final execution timing
                     BUY NOW / SELL NOW
```

KR-370 direction/readiness and the KR-380A Execution Context are separate inputs to KR-380. The KR-380A Execution Context does not flow to KR-370.

---

# Responsibilities

## Execution Context Provider

Responsible for:

- Market-specific interpretation
- Product-specific interpretation
- Producing a standardized Execution Context
- Reporting execution qualification state

For the current entry execution architecture, KR-380A fulfills this provider responsibility through the narrow adapter scope approved by ADL-003.

The provider shall never:

- Own or establish trade direction
- Own BUY READY / SELL READY
- Generate BUY READY
- Generate SELL READY
- Own BUY NOW / SELL NOW
- Generate BUY NOW
- Generate SELL NOW
- Own or perform trade management

---

## KR-370

KR-370 owns direction and readiness, including BUY READY / SELL READY.

KR-370 is upstream of entry execution authorization. It does not consume the Execution Context produced by KR-380A and does not own final execution timing or BUY NOW / SELL NOW.

---

## KR-380

KR-380 is the sole currently authorized consumer of the entry Execution Context produced by KR-380A.

KR-380 consumes KR-370 direction/readiness as a separate upstream input. It retains ownership of final execution timing and produces BUY NOW / SELL NOW according to its existing repository-defined responsibilities.

KR-380 shall not reinterpret market-specific provider rules, infer direction, or create BUY READY / SELL READY.

---

## Consumer Boundary

This ADR authorizes no entry Execution Context consumer other than KR-380. Any additional consumer requires a separate approved architecture decision.

---

## KR-390A Boundary

KR-390A is outside this ADR's current entry Execution Context boundary. It serves post-entry trade management through KR-390 under ADL-003 and the existing repository-defined ownership model.

The existing KR-380A context-readiness dependency used for KR-390A gating remains governed by ADL-003 and does not make KR-390A a consumer of the standardized entry Execution Context under this ADR.

This ADR does not convert KR-390A into an entry Execution Context Provider or consumer and does not modify KR-390 or KR-390A responsibilities.

---

## Execution Ownership

Execution engines remain responsible for execution decisions according to their existing repository-defined ownership.

This ADR does not modify execution engine responsibilities.

---

# Architectural Invariants

The following invariants shall always hold:

1. Execution Context Providers shall never own direction, own or produce BUY READY / SELL READY, authorize trades, own or produce BUY NOW / SELL NOW, or own trade management.

2. Execution engines shall never contain market-specific execution logic.

3. Communication between providers and consumers shall occur only through ECIC-001, with payload governance assigned to ECPC-001.

4. New markets shall be introduced by creating new providers rather than modifying execution engines.

5. Execution Context shall remain deterministic.

6. KR-380 is the sole currently authorized consumer of the entry Execution Context.

7. Additional consumers require a separate approved architecture decision.

8. KR-390A and post-entry trade management remain outside this ADR's current entry Execution Context boundary.

---

# Relationship to ECIC-001 and ECPC-001

ECIC-001 defines the payload-neutral public interface through which an Execution Context Provider communicates with an authorized consumer.

ECPC-001 is the payload-governance contract for the structure and contents of the Execution Context. This ADR does not define payload fields, types, values, encodings, or representations.

---

# Relationship to ADL-003

This ADR extends the Execution Context Adapter architecture defined by ADL-003.

ADL-003 establishes the adapter concept and approves KR-380A as the narrow Execution Context Adapter serving KR-380. Under this ADR, KR-380A is the current concrete Execution Context Provider for entry execution authorization while retaining ADL-003's narrow scope and prohibitions.

ADL-003 also establishes KR-390A as the Trade Management Execution Adapter serving KR-390. KR-390A remains outside this ADR's current entry Execution Context boundary; its existing context-readiness gating dependency does not make it an entry Execution Context consumer under this ADR.

ADR-006 standardizes provider responsibilities and the contract through which execution context is exchanged.

If any conflict exists between ADR-006 and ADL-003, the conflict shall be resolved through an explicit repository update rather than implementation.

---

# Consequences

Benefits include:

- Reduced coupling
- Simplified onboarding of new markets
- Stable execution engines
- Clear separation of market interpretation from execution authorization
- Improved testability

---

# Related Documents

- PP-007 — Execution Semantics Across Markets
- ECIC-001 — Execution Context Interface Contract
- ECPC-001 — Execution Context Payload Contract
- ECM-001 — Execution Context Model
- ADL-003 — Execution Context Adapters
