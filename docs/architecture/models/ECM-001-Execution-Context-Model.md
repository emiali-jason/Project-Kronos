# ECM-001 — Execution Context Model

**Status:** Approved

## 1. Purpose

Define the behavioral model for the Execution Context under the ownership model approved by [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md) and the public interface established by [ECIC-001](../interfaces/ECIC-001-Execution-Context-Interface-Contract.md).

This document defines lifecycle and behavioral constraints only. It does not define an Execution Context payload, introduce interface fields, or change execution ownership.

## 2. Scope

This model applies to the behavior of every Execution Context produced through ECIC-001, independent of market, product, provider implementation, or execution consumer.

It covers:

- the lifecycle of an Execution Context;
- the boundary of an execution evaluation cycle;
- production, publication, consumption, and cycle closure behavior;
- determinism, immutability, consumer isolation, and contract-version behavior;
- production failure and the prohibition of degraded-state behavior at an architectural level.

Existing execution ownership remains defined by [Engine Ownership](../ENGINE_OWNERSHIP.md) and [Data Flow](../DATA_FLOW.md).

## 3. Architectural Principles

1. An Execution Context communicates market-specific and product-specific qualification without authorizing execution.
2. Exactly one Execution Context Provider produces each Execution Context.
3. Execution Context communication occurs only through ECIC-001.
4. A published Execution Context is immutable for its execution evaluation cycle.
5. Consumers interpret only standardized context behavior, never provider implementation details.
6. Qualification is distinct from execution authorization and does not create BUY READY, SELL READY, BUY NOW, or SELL NOW.
7. Execution Context behavior is market-neutral even when provider evaluation is market-specific.
8. No lifecycle rule in this model changes the repository-defined responsibilities of KR-370, KR-380, or any other engine.

These principles apply [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md) without redefining its ownership boundary.

## 4. Execution Lifecycle

An Execution Context follows this behavioral lifecycle:

1. **Cycle initiation.** A cycle begins when KR-380A evaluates the latest eligible confirmed market state for KR-380.
2. **Provider evaluation.** KR-380A evaluates only authoritative inputs permitted by its governing architecture and within the same permitted confirmed-data boundary.
3. **Production outcome.** KR-380A produces either one complete and valid Execution Context or an explicit unavailable/failure outcome permitted by the public contract.
4. **Publication and cycle closure.** KR-380A publishes the immutable Execution Context or explicit unavailable/failure outcome through the applicable public-contract mechanism. That publication closes the cycle.
5. **Consumer evaluation.** KR-380 evaluates a valid published context through ECIC-001 under its existing repository-defined responsibility. An unavailable/failure outcome does not create an inferred context.
6. **Next evaluation.** A new eligible evaluation point begins a new cycle and requires a new production outcome.

The lifecycle does not prescribe a chart timeframe, event source, scheduling mechanism, or implementation sequence.

## 5. Execution Evaluation Cycle

An execution evaluation cycle is one deterministic evaluation point beginning when KR-380A evaluates the latest eligible confirmed market state for KR-380 and ending when KR-380A publishes the production outcome.

Within a cycle:

- KR-380A is responsible for the entry Execution Context;
- all inputs comply with the same permitted confirmed-data boundary;
- intrabar or partially confirmed inputs are prohibited unless separately approved by product architecture;
- KR-380A publishes either one immutable Execution Context or one explicit unavailable/failure outcome permitted by the public contract;
- publication closes the cycle;
- consumers do not refresh, supplement, or reinterpret the context from provider internals;
- previously published context is never mutated or retroactively replaced;
- a new eligible evaluation point begins a new cycle.

This behavioral boundary does not introduce a cycle identifier, payload field, or payload representation.

## 6. Execution Context Behavioral Model

The behavioral sequence is:

```text
New eligible confirmed evaluation point
  -> KR-380A begins one deterministic cycle
      -> Complete and valid context produced
          -> Immutable context published
              -> Cycle closed
                  -> KR-380 evaluates under existing ownership
      -> Context cannot be completely and validly produced
          -> Explicit unavailable/failure outcome published
              -> Cycle closed
                  -> KR-380 does not infer context
```

The labels in this sequence describe lifecycle behavior. They are not payload fields, required values, or a state enumeration.

Qualification behavior is provider-owned interpretation of whether provider-specific execution prerequisites are satisfied. Qualification does not determine direction, readiness, or execution authorization.

Consumers may continue to use other public dependencies authorized by existing repository architecture. Consumer isolation means that Execution Context itself is obtained only through ECIC-001; it does not replace unrelated public contracts.

## 7. Producer Responsibilities

Producer responsibilities are defined only by [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md).

For this behavioral model, the provider:

- evaluates market-specific and product-specific execution prerequisites;
- produces one standardized Execution Context for an evaluation cycle;
- reports execution qualification behavior without authorizing execution;
- publishes through the Execution Context Contract;
- does not generate BUY READY, SELL READY, BUY NOW, or SELL NOW.

This section does not add to or reinterpret ADR-006.

## 8. Consumer Responsibilities

Consumer responsibilities are defined only by [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md).

For this behavioral model, a consumer:

- receives Execution Context through the standardized contract;
- does not inspect or reproduce provider-specific interpretation;
- applies the context only within its existing repository-defined execution responsibility;
- does not mutate the published context;
- does not infer a context when production failed.

This section does not identify new consumers or change any execution engine responsibility.

Under ADR-006, KR-380 is the sole currently authorized consumer of the entry Execution Context. The generic consumer behavior in this section does not authorize additional consumers.

## 9. Determinism Requirements

Execution Context behavior shall be deterministic.

- Identical authoritative inputs evaluated under the same governing provider rules and contract version produce identical context behavior.
- Input ordering, provider selection, evaluation boundaries, and qualification behavior must not depend on nondeterministic side effects.
- All inputs in a cycle must comply with the same permitted confirmed-data boundary.
- Intrabar or partially confirmed inputs are prohibited unless separately approved by product architecture.
- Publication must not change the result produced by provider evaluation.
- Production failure must be explicit and repeatable under identical failure conditions.
- A published context must remain immutable and must never be retroactively replaced.
- Provider evaluation must not use lookahead or future-confirmed values; [ADL-003](../ADL-003-Execution-Context-Adapters.md) governs only the adapter-local source-access boundary through which permitted inputs are obtained.

This section defines behavioral determinism, not payload representation or test thresholds.

## 10. Consumer Isolation

Consumers shall remain isolated from provider implementation.

- Consumers receive Execution Context only through ECIC-001.
- Consumers do not access provider-private data, calculations, routing, thresholds, or market rules.
- Consumers do not reach through a provider to its source data.
- Consumers do not reconstruct missing or failed context from unrelated data.
- Adding or replacing a provider does not change the meaning of consumer execution states.
- Existing non-context public dependencies remain governed by their current repository contracts.

## 11. Contract Versioning Strategy

Contract versioning behavior follows ECIC-001 while leaving all payload representation to ECPC-001.

- Every Execution Context must conform to exactly one approved ECPC-001 contract version.
- KR-380A must not publish a contract version that it cannot completely produce.
- KR-380 must not interpret an unsupported contract version.
- An unsupported contract version produces context unavailability rather than best-effort parsing, coercion, or inference.
- Multiple contract versions may coexist only during an explicitly approved migration window.
- Supported-version policy and migration windows must be explicitly governed and must not be dynamically inferred.
- A version transition cannot mutate or retroactively replace an already published context.

This section defines behavior only. It introduces no version field, schema, encoding, or payload representation. ECPC-001 retains ownership of version representation in the payload.

## 12. Failure and Degraded-State Semantics

Production failure and context unavailability are behavioral concerns, not execution decisions.

### Production failure

- A provider that cannot produce an Execution Context reports failure explicitly through the product-architecture mechanism required by ECIC-001.
- No Execution Context is inferred from absence, partial provider output, cached provider internals, or consumer-side fallback logic.
- Consumers apply existing product behavior for an unavailable context; this model does not define a new execution outcome.

### Degraded state

- The current architecture does not permit a degraded Execution Context.
- KR-380A must produce either one complete and valid Execution Context or an unavailable/failure outcome.
- Partial, stale, substituted, incomplete, or degraded contexts must not be published as valid Execution Context.
- KR-380 must not interpret unavailable, partial, stale, substituted, incomplete, or degraded information as valid context.
- Any future degraded-context model requires a separate approved architectural decision.

These rules define behavior only and introduce no degraded-state field, value, schema, or payload representation.

## 13. Relationship to ECIC-001

[ECIC-001](../interfaces/ECIC-001-Execution-Context-Interface-Contract.md) defines the public communication contract. ECM-001 defines behavioral expectations for the context communicated through that contract.

ECM-001 does not define fields, types, serialization, payload structure, or consumer identity. ECIC-001 assigns payload-definition governance to [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md); this model defines behavior only and leaves payload definition exclusively to ECPC-001.

## 14. Relationship to ADR-006

[ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md) defines the approved provider architecture and preserves existing execution-engine ownership. ECM-001 describes the lifecycle behavior of the context produced under that architecture.

ECM-001 does not broaden provider responsibility, identify new consumers, or modify execution ownership.

## 15. Relationship to ADL-003

[ADL-003](../ADL-003-Execution-Context-Adapters.md) establishes the narrow adapter/data-access architecture, source-isolation rules, and adapter boundaries. It does not define Execution Context readiness, lifecycle, unavailable behavior, or other behavioral semantics.

ECM-001 exclusively governs Execution Context lifecycle and unavailable behavior. It remains compatible with ADL-003's narrow adapter, source-isolation, and adapter-boundary constraints without broadening adapter access or permitting duplicated intelligence.

ADR-006 defines KR-380A as the current concrete Execution Context Provider for entry execution authorization and KR-380 as the sole currently authorized consumer of that entry Execution Context. KR-390A remains outside the current entry Execution Context boundary because it serves post-entry trade management through KR-390. This model does not extend ECIC-001 behavior to KR-390A.

## 16. Extension Points

Future approved architecture may define:

- provider selection and routing behavior;
- explicitly governed supported-version sets and migration windows;
- product-specific unavailable/failure reporting mechanisms permitted by ECIC-001;
- a degraded-context model through a separate approved architectural decision;
- onboarding behavior for additional markets or products;
- additional consumers through a separate approved architecture decision.

Each extension must preserve PP-007, ADR-006, ECIC-001, ADL-003, and existing execution ownership as applicable. Material changes require the repository’s architecture-governance process.

## 17. Out of Scope

This model does not define or change:

- Execution Context payload fields, names, types, values, or serialization;
- a payload state enumeration;
- a cycle identifier field or representation;
- contract-version field representation;
- provider implementation, market rules, routing, thresholds, or data sources;
- KR-370, KR-380, KR-390, KR-400, or KR-705 responsibilities;
- BUY READY, SELL READY, BUY NOW, or SELL NOW semantics;
- decision direction, readiness, trigger logic, trade management, alerts, or presentation;
- failure-handling outcomes owned by product architecture;
- implementation sequencing, migration code, or regression tests;
- approval of ECPC-001 or any other architecture document.
