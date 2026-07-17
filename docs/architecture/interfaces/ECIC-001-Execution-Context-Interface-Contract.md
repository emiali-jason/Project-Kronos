# ECIC-001 — Execution Context Interface Contract

**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.0

---

# Purpose

Define the standard interface through which an Execution Context Provider communicates execution context to execution consumers.

This contract standardizes communication between components while remaining independent of market, product, and implementation.

This contract does not define execution logic or the structure of the Execution Context payload. Those are defined separately.

---

# Scope

This contract applies to all Execution Context Providers within KRONOS.

Examples include:

- NSE Equities
- NSE Futures
- MCX Futures
- Future supported products

---

# Producer

An Execution Context Provider is the sole producer of an Execution Context.

Each provider evaluates product-specific and market-specific execution prerequisites and produces a standardized Execution Context.

Providers shall not:

- Produce BUY READY
- Produce SELL READY
- Produce BUY NOW
- Produce SELL NOW

---

# Consumer

Execution consumers receive an Execution Context exclusively through this contract.

The identity and responsibilities of execution consumers are defined by the product architecture and are outside the scope of this contract.

---

# Contract Rules

The interface shall satisfy the following rules:

1. Single Producer

Each Execution Context is produced by exactly one Execution Context Provider.

---

2. Standardized Interface

All providers expose Execution Context through the same interface regardless of market or product.

---

3. Immutable During Evaluation

Once published for an execution evaluation cycle, an Execution Context shall not change during that evaluation.

A new evaluation requires a new Execution Context.

---

4. Versioned

Every Execution Context shall identify the contract version under which it was produced.

This enables backward compatibility and controlled evolution.

---

5. Deterministic

Given identical inputs, a provider shall produce an identical Execution Context.

---

6. Consumer Independence

Consumers shall depend only on this interface contract.

Consumers shall not depend on provider-specific implementation details.

---

# Failure Behaviour

If an Execution Context cannot be produced, the provider shall explicitly report failure through the mechanisms defined by the product architecture.

Consumers shall not infer missing context.

Failure handling semantics are outside the scope of this contract.

---

# Relationship to ECPC-001 and ECM-001

This contract defines the communication interface and remains payload-neutral.

The structure and contents of the Execution Context payload are governed exclusively by ECPC-001.

ECM-001 defines Execution Context behavior only and does not own the payload schema.

---

# Architectural Invariants

The following invariants shall always hold:

1. Exactly one producer exists for each Execution Context.

2. Consumers never interpret provider implementation.

3. Providers never authorize execution.

4. Consumers communicate only through this contract.

5. This contract remains market-neutral.

---

# Amendment History

| Date | Amendment | Status | Summary |
| --- | --- | --- | --- |
| 2026-07-17 | Amendment 1 | Approved | Reassigned payload-definition governance from ECM-001 to ECPC-001, clarified ECM-001 as behavior-only, and preserved ECIC-001's payload-neutral scope. |

---

# Related Documents

- PP-007 — Execution Semantics Across Markets
- ADR-006 — Execution Context Provider Architecture
- ECPC-001 — Execution Context Payload Contract
- ECM-001 — Execution Context Model
- ADL-003 — Execution Context Adapters
