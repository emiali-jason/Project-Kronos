# EAIC-001 — Exchange Availability Interface Contract

**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.0

---

# Purpose

Define the public presentation-facing interface for explicit Exchange Availability in KRONOS.

This contract allows presentation components to determine whether an exchange is explicitly open or closed without inferring market status from market-data availability, stale bars, readiness failures, Execution Context availability, or the absence of newly confirmed candles.

---

# Scope

This contract applies only to public Exchange Availability presentation.

It does not define:

- execution logic;
- execution authorization;
- execution readiness;
- market-data readiness;
- Execution Context validity;
- market-data retrieval rules;
- exchange session calendars;
- holiday logic;
- fallback heuristics.

---

# Owning Producer

Version 1 designates:

**KR-200 — Market Identification Engine**

as the sole producer of the Exchange Availability Interface.

Future ownership changes require repository approval.

KR-200 may publish Exchange Availability only when exchange status is explicitly known through an approved repository-backed source.

KR-200 shall not infer Exchange Availability from:

- missing market data;
- stale market data;
- unchanged bars;
- elapsed time;
- trading volume;
- Execution Context;
- downstream execution readiness;
- execution failures.

---

# Implementation Note

This contract defines the public Exchange Availability interface only. Publication of OPEN and CLOSED requires an independently approved authoritative Exchange Availability source. Until such a source exists, producers shall not publish Exchange Availability values.

---

# Consumers

Presentation components may consume this interface.

Initial consumer:

- KR-705 — Engine Status Panel

Consumers shall use this interface for presentation only.

Consumers shall not use Exchange Availability to alter:

- KR-370 decisions;
- KR-380 execution timing;
- KR-380A Execution Context production;
- ECPC payloads;
- alerts;
- trade management;
- market-data readiness.

---

# Public Contract

Version 1 exposes exactly two canonical public values.

| Public Value | Meaning |
|--------------|---------|
| `OPEN` | Exchange is explicitly known to be open. |
| `CLOSED` | Exchange is explicitly known to be closed. |

No additional Exchange Availability values are defined by Version 1.

---

# Contract Rules

1. `OPEN` and `CLOSED` are mutually exclusive.

2. A published Exchange Availability state shall contain exactly one valid public value.

3. If Exchange Availability cannot be explicitly determined, the producer shall not publish a valid Exchange Availability state.

4. Consumers shall not infer `CLOSED` from unavailable market data.

5. Consumers shall not infer `OPEN` from available market data.

6. Consumers shall not infer Exchange Availability from ECPC, KR-370, KR-380, KR-390, or KR-705 state.

7. This interface is presentation-facing only.

---

# Failure Behaviour

If Exchange Availability cannot be explicitly determined, the interface shall be considered unavailable.

Unavailable Exchange Availability is **not** a third Exchange Availability state.

When unavailable:

- KR-705 may continue rendering existing generic presentation wording.
- KR-705 shall not render session-specific wording such as:
  - Market Open
  - Market Closed
  - Next Session

without a valid Exchange Availability value.

---

# Presentation Guidance

Presentation wording remains owned by KR-705.

Suggested mappings:

| Interface Value | Example Presentation |
|-----------------|----------------------|
| `OPEN` | Market Open |
| `CLOSED` | Market Closed or Next Session |

Presentation wording may evolve without changing this interface contract.

---

# Relationship to ECPC V2

EAIC-001 does not modify ECPC V2.

Exchange Availability does not determine Execution Context validity.

A closed exchange does not invalidate the most recent confirmed Execution Context.

---

# Relationship to KR-370 and KR-380

EAIC-001 does not modify KR-370 or KR-380.

Exchange Availability shall not alter:

- BUY READY
- SELL READY
- BUY NOW
- SELL NOW
- FAILED
- EXTENDED
- FORMING

or any execution readiness, qualification, or execution behaviour.

---

# Architectural Invariants

1. KR-200 is the sole producer of Exchange Availability.

2. KR-705 shall render Exchange Availability only from this public interface.

3. KR-705 shall not calculate, infer, reconstruct, or predict Exchange Availability.

4. Exchange Availability shall not be used as execution readiness.

5. Exchange Availability shall not be used as Execution Context validity.

6. Exchange Availability and Market Data Availability are independent architectural concepts and shall never be substituted for one another.

7. Version 1 exposes only the canonical public values `OPEN` and `CLOSED`.

---

# Related Documents

- ENGINE_OWNERSHIP.md
- DATA_FLOW.md
- ECPC-001 — Execution Context Payload Contract
- ADR-006 — Execution Context Provider Architecture
- ECM-001 — Execution Context Model
