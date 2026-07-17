# ECPC-001 — Execution Context Payload Contract

**Status:** Approved

**Version:** 2.0

## 1. Purpose

Define governance for the structure, contents, evolution, and validation of the Execution Context payload assigned to ECPC-001 by [ECIC-001](ECIC-001-Execution-Context-Interface-Contract.md).

This contract defines conceptual payload elements and payload-validation obligations only. It does not define field names, concrete data types, enumerated values, encodings, serialization, or implementation-specific schemas. It creates no implementation authority.

## 2. Scope

ECPC-001 governs current and future architectural decisions about:

- payload schema boundaries;
- required and optional payload elements;
- semantic definitions and representations;
- schema versioning and compatibility;
- unavailable/failure boundaries and the prohibition of degraded payloads;
- producer and consumer validation obligations for the payload contract.

Execution behavior remains governed by [ECM-001](../models/ECM-001-Execution-Context-Model.md). Communication behavior remains governed by ECIC-001.

## 3. Authority and Status

ECIC-001 assigns payload-definition governance to ECPC-001.

ECPC-001 is Approved as conceptual payload-governance architecture. Its approval scope is limited as follows:

- no concrete payload field or implementation-specific representation is defined by this document;
- Engineering shall not infer a schema from examples, current implementation, provider internals, or conceptual descriptions;
- the conceptual decisions recorded here are authoritative within this contract scope.

Approval of ECPC-001 covers only the content explicitly recorded at that time. It does not approve unspecified fields or representations.

## 4. Payload Ownership Boundary

ECPC-001 is the repository location for Execution Context payload-schema decisions.

This ownership is limited to payload definition. ECPC-001 does not own:

- provider responsibilities;
- consumer responsibilities;
- execution direction, readiness, timing, or authorization;
- evaluation lifecycle behavior;
- market-specific qualification rules;
- trade management, alerts, or presentation.

Those responsibilities remain with their existing governing documents and repository-defined owners.

## 5. Approved Constraints Inherited from ECIC-001

The following approved interface constraints govern future payload decisions:

1. Execution Context communication remains market-neutral.
2. Each Execution Context has exactly one provider.
3. A published Execution Context is immutable during its execution evaluation cycle.
4. Every Execution Context identifies the contract version under which it was produced; Section 7 defines the payload representation as the single ECPC-001 payload contract-version identifier required by the current contract.
5. Provider output is deterministic for identical inputs.
6. Consumers do not depend on provider-specific implementation details.
7. Missing context is not inferred by consumers.

These constraints do not approve a field name, data type, allowed value, encoding, or representation.

## 6. Schema Decision Governance

Every future concrete payload field or representation proposed under the conceptual requirements in this contract must be recorded and reviewed before approval. Its architecture record must identify:

- semantic purpose;
- governing source and responsibility boundary;
- required or optional status;
- data type and representation;
- permitted values or constraints;
- absence, invalidity, and failure behavior;
- immutability and evaluation-cycle behavior;
- contract version introduction and compatibility impact;
- producer validation and consumer validation expectations;
- migration and regression-validation requirements.

A payload element must not duplicate provider internals, transfer execution ownership, or expose raw data merely for consumer convenience.

## 7. Payload Contract Decisions

The following conceptual payload requirements are defined by this contract and are authoritative within its conceptual scope.

### Contract-version identification

Every Execution Context payload contains exactly one required payload contract-version identifier.

- The identifier represents the approved ECPC-001 payload contract version under which the payload was produced and satisfies ECIC-001's contract-version identification requirement.
- The current contract defines no second or independent payload-schema version identifier.
- A missing, invalid, or unsupported identifier makes the payload invalid and results in context unavailability through the public contract.
- The identifier is immutable with the rest of the published payload.
- This conceptual requirement defines no field name, concrete data type, value syntax, encoding, or serialization.

### Execution qualification representation

Every Execution Context payload contains one required, complete, market-neutral execution-qualification representation.

- The representation communicates the complete set of standardized qualification assertions required by the approved provider contract for that evaluation point.
- Each assertion represents only whether its corresponding provider-evaluated prerequisite is satisfied or not satisfied.
- The representation does not establish direction, BUY READY, SELL READY, execution timing, execution authorization, BUY NOW, SELL NOW, or trade-management state.
- Unavailable/failure is not a qualification assertion or a valid qualification representation.
- No optional payload element is approved by this contract.
- These conceptual semantics define no field name, concrete data type, enumerated value, encoding, serialization, or implementation-specific schema.

### Unavailable/failure boundary

Unavailable/failure is represented outside the Execution Context payload through the public-contract mechanism required by ECIC-001 and governed behaviorally by ECM-001.

- An unavailable/failure outcome is not an Execution Context payload.
- KR-380A must not publish a partial payload, failure payload, cached substitute, or last-known payload as a valid Execution Context.
- KR-380 must not infer or reconstruct an Execution Context from the absence of a valid payload.

### Degraded and evaluation-cycle representation

- Degraded Execution Context payloads are prohibited.
- Partial, stale, substituted, incomplete, or degraded payloads are invalid.
- The payload contains no evaluation-cycle identifier or evaluation-cycle representation.
- Evaluation-cycle initiation and closure remain behavioral concerns governed by ECM-001.
- A published payload is immutable and must never be mutated or retroactively replaced.

## 8. Versioning and Compatibility Governance

Any approved payload-schema change must:

- identify the contract version affected;
- classify backward-compatibility impact;
- identify affected producers and consumers without changing their ownership;
- specify migration and fallback policy through approved architecture;
- preserve already published contexts for active evaluation cycles;
- include deterministic validation and regression requirements;
- update related interface and model references where necessary.

The current contract uses the single required ECPC-001 payload contract-version identifier defined in Section 7. No separate payload-schema version identifier exists. Multiple ECPC-001 contract versions may coexist only during an explicitly approved migration window governed consistently with ECM-001.

## 9. Failure and Missing-Information Governance

Payload schema must not cause consumers to infer missing context.

- Inability to produce a complete and valid Execution Context produces an unavailable/failure outcome outside the payload through the public contract.
- A missing or invalid required conceptual element invalidates the entire payload.
- An unsupported ECPC-001 contract version invalidates the entire payload and produces context unavailability rather than best-effort parsing.
- No optional payload element is currently approved.
- Degraded payloads are prohibited and have no valid representation.
- Invalid, unsupported, partial, stale, substituted, incomplete, or degraded payloads must not be interpreted as Execution Context.

## 10. Producer and Consumer Payload Obligations

### KR-380A producer obligations

Before publishing an Execution Context payload, KR-380A must validate that:

- the payload contains exactly one valid ECPC-001 payload contract-version identifier;
- KR-380A completely supports and can completely produce that contract version;
- the complete standardized execution-qualification representation is present and conforms to the approved contract version;
- the payload is complete, deterministic, immutable, and free of partial, stale, substituted, incomplete, or degraded content;
- the payload exposes neither provider-private implementation details nor raw data outside the approved payload contract;
- no payload element establishes direction, READY, execution timing, execution authorization, NOW, or trade-management state.

If any producer validation fails, KR-380A must not publish an Execution Context payload and must report unavailable/failure outside the payload through the public contract.

### KR-380 consumer obligations

Before consuming an Execution Context payload, KR-380 must validate that:

- exactly one ECPC-001 payload contract-version identifier is present, valid, and supported;
- the complete standardized execution-qualification representation is present and conforms to that contract version;
- the entire payload satisfies the approved payload contract and is not partial, stale, substituted, incomplete, or degraded;
- no required conceptual element is missing or invalid.

If any consumer validation fails, KR-380 must reject the entire payload and treat context as unavailable. KR-380 must not apply best-effort parsing, coerce an unsupported version, infer missing context, inspect provider internals, mutate the payload, or reinterpret qualification as direction, READY, execution authorization, or NOW.

Producer and consumer validation must preserve payload immutability, deterministic conformance, and backward-compatibility and migration requirements where applicable.

Validation evidence does not approve architecture by itself.

## 11. Relationships

- [ECIC-001](ECIC-001-Execution-Context-Interface-Contract.md) owns the payload-neutral communication interface and assigns payload-definition governance to ECPC-001.
- [ECM-001](../models/ECM-001-Execution-Context-Model.md) is Approved, owns Execution Context behavior, and does not define payload schema.
- [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md) is Approved and defines provider and consumer ownership without defining payload schema.
- [ADL-003](../ADL-003-Execution-Context-Adapters.md) remains the approved narrow-adapter architecture.
- [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md) requires market-neutral execution semantics.

## 12. Out of Scope

This contract does not define or approve:

- payload field names, concrete data types, enumerated values, encodings, serialization, or implementation-specific schemas;
- provider selection or market routing;
- market-specific qualification rules or thresholds;
- execution evaluation-cycle behavior;
- KR-370, KR-380, KR-390, KR-400, or KR-705 responsibilities;
- BUY READY, SELL READY, BUY NOW, or SELL NOW semantics;
- execution, trade-management, alert, or presentation logic;
- implementation sequencing or code changes;
- approval of any other architecture document.

## 13. Version 1 Implementation Schema — Superseded Before Implementation

**Version 1 Status:** Superseded Before Implementation

Version 1 was superseded before implementation because it could not satisfy all approved consumer responsibilities while preserving provider/consumer separation. Its technical content is retained unchanged below as a superseded contract record.

This section records the concrete Pine implementation schema defined for Version 1. It is a narrowly scoped exception to, and supersedes for Version 1 only, earlier statements in this document that limit ECPC-001 to conceptual governance or state that it defines no field names, concrete data types, permitted values, or implementation-specific schema. Those limitations continue to apply to every field and representation not defined in this section and to any future contract version unless separately approved.

Version 1 contains exactly these three public fields:

| Concept | Pine Identifier | Pine Type | Permitted Values |
|---|---|---|---|
| Execution Context Version | `outExecContextVersion` | `string` | `"1.0"` |
| Execution Context Available | `outExecContextAvailable` | `bool` | `true`, `false` |
| Execution Context Qualified | `outExecContextQualified` | `bool` | `true`, `false` |

The following rules govern the Version 1 public contract:

- `outExecContextVersion` must always equal `"1.0"`.
- `outExecContextAvailable = true` means the provider produced a complete and valid Execution Context.
- `outExecContextAvailable = false` means no valid Execution Context exists.
- When `outExecContextAvailable = false`, the consumer must not read, interpret, or act on `outExecContextQualified`.
- When `outExecContextAvailable = false`, Execution Context processing must stop and execution must not proceed.
- When `outExecContextAvailable = true`, `outExecContextQualified` is authoritative.
- The consumer must not reconstruct qualification from provider internals, timeframe states, market-specific conditions, or any other signals.
- `outExecContextAvailable` is part of the public Version 1 contract and is the authoritative mechanism by which a provider indicates whether a valid Execution Context payload exists. When `outExecContextAvailable = false`, no valid Execution Context payload exists and consumers shall terminate processing without interpreting qualification.

The Version 1 public schema explicitly excludes:

- Daily, 4H, and 1H states;
- acceptance;
- compression;
- momentum;
- breakout;
- blockers or reasons;
- MCX- or NSE-specific states;
- diagnostics and debug fields.

### Versioning Policy

Version 1 defines the complete public Execution Context contract.

Additional public fields shall only be introduced through a new approved contract version (for example, Version 2.0).

The semantics of Version 1 shall remain backward compatible for all Version 1 consumers.

## 14. Version 2 Public Contract

Version 2 is the active approved Execution Context implementation contract. It supersedes Version 1 for future implementation while preserving Version 1 as a superseded-before-implementation contract record.

### Conceptual public contract

Version 2 contains the smallest conceptual public contract required to preserve approved provider and consumer responsibilities:

| Concept | Contract meaning |
|---|---|
| Contract version identification | Identifies the approved Execution Context contract version under which the public contract was produced. |
| Execution Context availability | Indicates whether one complete and valid Execution Context payload exists. |
| Execution Context Outcome | Communicates one authoritative provider-owned Execution Context result: `PENDING`, `QUALIFIED`, `EXTENDED`, or `FAILED`. |
| Ordered Execution Context blockers | Communicates an ordered sequence of zero to three authoritative, market-neutral blocker classifications. |

The contract shall not expose timeframe, exchange, indicator, market-specific, provider-internal, diagnostic, debug, or implementation-specific state.

### Execution Context Outcome semantics

- `PENDING` means a complete and valid Execution Context exists, but provider-owned execution-context prerequisites are not yet satisfied and the context is neither `EXTENDED` nor `FAILED`.
- `QUALIFIED` means a complete and valid Execution Context exists and all provider-owned execution-context prerequisites are satisfied.
- `EXTENDED` means a complete and valid Execution Context exists and the provider has authoritatively classified the current context as extended for the evaluation cycle.
- `FAILED` means a complete and valid Execution Context exists and the provider has authoritatively classified the current context as failed for the evaluation cycle.

The Execution Context Outcome is authoritative for Execution Context only. It shall not authorize trade execution. Final execution authorization remains the responsibility of KR-380 after evaluating its own responsibilities and upstream contracts.

When Execution Context availability is false, no valid Execution Context payload exists. The consumer shall stop Execution Context processing, shall not interpret the Execution Context Outcome, and shall not proceed with execution.

### Ordered blocker contract

KR-380A owns selection and priority ordering of Execution Context blockers. The ordered blocker contract shall:

- contain no more than the three highest-priority blockers;
- use a stable market-neutral taxonomy;
- expose no provider-internal conditions or calculations;
- expose no timeframe, exchange, indicator, threshold, diagnostic, debug, or implementation-specific state;
- remain immutable for the evaluation cycle;
- permit KR-380 to consume and publish blocker information without reconstructing provider logic.

A `QUALIFIED` outcome carries no Execution Context blocker. `PENDING`, `EXTENDED`, and `FAILED` carry at least one authoritative Execution Context blocker.

An unavailable public-contract outcome may carry ordered availability blockers in the public contract envelope. Those blockers explain unavailability only; they do not constitute or permit inference of a valid Execution Context payload or Execution Context Outcome.

### Minimum market-neutral blocker taxonomy

Version 2 defines the following complete public blocker taxonomy:

| Code | Classification | Meaning |
|---:|---|---|
| 0 | No blocker | No blocker is present in this slot. |
| 1 | Required data pending | Required provider input data is not available for a valid context. |
| 2 | Eligible execution context pending | A valid context cannot yet be produced for the current evaluation point. |
| 3 | Directional alignment pending | Provider-owned alignment is pending without exposing market-specific internals. |
| 4 | Price acceptance pending | Provider-owned price acceptance is pending. |
| 5 | Expansion pending | Provider-owned expansion or release condition is pending. |
| 6 | Momentum pending | Provider-owned momentum confirmation is pending. |
| 7 | Confidence pending | Provider-owned confidence confirmation is pending. |
| 8 | Opportunity pending | Provider-owned opportunity confirmation is pending. |
| 9 | Execution confirmation pending | Provider-owned final execution-context confirmation is pending. |
| 10 | Price extended | Provider has classified the context as extended. |
| 11 | Execution setup failed | Provider has classified the context as failed. |

The taxonomy is market-neutral and shall not expose timeframe, exchange, indicator, threshold, provider-internal, diagnostic, or debug detail.

### Concrete Pine schema

Version 2 contains exactly these public Pine fields:

| Concept | Pine Identifier | Pine Type | Permitted Values |
|---|---|---|---|
| Execution Context Version | `outExecContextVersion` | `string` | `"2.0"` |
| Execution Context Available | `outExecContextAvailable` | `bool` | `true`, `false` |
| Execution Context Outcome | `outExecContextOutcome` | `int` | `0`, `1`, `2`, `3`, `4` |
| Execution Context Blocker 1 | `outExecContextBlocker1` | `int` | `0` through `11` |
| Execution Context Blocker 2 | `outExecContextBlocker2` | `int` | `0` through `11` |
| Execution Context Blocker 3 | `outExecContextBlocker3` | `int` | `0` through `11` |

Execution Context Outcome values are:

| Value | Outcome |
|---:|---|
| 0 | No valid outcome |
| 1 | `PENDING` |
| 2 | `QUALIFIED` |
| 3 | `EXTENDED` |
| 4 | `FAILED` |

Blocker slots are fixed-width, left-packed, ordered by provider priority, and use `0` as the no-blocker sentinel. Version 2 does not define a separate blocker-count field.

### Responsibility boundaries

KR-380A owns:

- provider-specific market and product interpretation;
- Execution Context availability;
- the authoritative Execution Context Outcome;
- selection and priority ordering of Execution Context blockers;
- translation of provider-internal conditions into approved market-neutral blocker classifications.

KR-380 owns:

- consuming KR-370 direction and BUY READY / SELL READY through their separate upstream contract;
- consuming the standardized Execution Context without reconstructing provider logic;
- final execution timing;
- mapping the authoritative Execution Context Outcome into its existing public execution states;
- final execution authorization and BUY NOW / SELL NOW;
- publishing its existing ordered execution blocker queue.

KR-380A shall not own or establish direction, BUY READY, SELL READY, final execution authorization, BUY NOW, SELL NOW, or trade management. KR-380 shall not inspect provider internals, reproduce provider interpretation, or derive a replacement Execution Context Outcome.

### KR-380 behavior mapping

| KR-370 input | Execution Context | KR-380 final timing | KR-380 public result |
|---|---|---|---|
| No BUY READY or SELL READY | Any available outcome | Any | `NO TRIGGER` |
| BUY READY or SELL READY | `PENDING` | Any | `FORMING` |
| BUY READY | `QUALIFIED` | Not final | `FORMING` |
| SELL READY | `QUALIFIED` | Not final | `FORMING` |
| BUY READY | `QUALIFIED` | Final | `BUY NOW` |
| SELL READY | `QUALIFIED` | Final | `SELL NOW` |
| BUY READY or SELL READY | `EXTENDED` | Not final | `FORMING` |
| BUY READY or SELL READY | `EXTENDED` | Final | `EXTENDED` |
| BUY READY or SELL READY | `FAILED` | Not final | `FORMING` |
| BUY READY or SELL READY | `FAILED` | Final | `FAILED` |
| Any | Unavailable | Any | Stop Execution Context processing; execution does not proceed. |

KR-380 retains direction-specific FORMING behavior through the separate KR-370 direction/readiness contract. The Execution Context neither supplies nor infers direction.

### Consumer boundary and dependent migration

KR-380 remains the sole authorized consumer of the entry Execution Context. Version 2 does not authorize KR-390A, KR-390, KR-705, or any other component to consume the entry Execution Context.

The existing execution-chart readiness dependency used outside KR-380 requires a separately approved migration outside the entry Execution Context contract:

- KR-390A remains responsible for its narrow post-entry context eligibility under ADL-003;
- KR-390 consumes the applicable KR-390A post-entry public contract;
- KR-705 consumes authorized KR-380 or KR-390 presentation outputs rather than the entry Execution Context.

This migration shall not broaden ECPC-001's consumer boundary or make trade-management and presentation components entry Execution Context consumers.

### Provider validation rules

KR-380A shall validate the Version 2 public contract before publication:

- `outExecContextVersion` must equal `"2.0"`.
- The published contract must be deterministic and immutable for the evaluation cycle.
- When `outExecContextAvailable = false`, `outExecContextOutcome` must be `0`, and blocker slots may contain only `0`, `1`, or `2`.
- When `outExecContextAvailable = true`, `outExecContextOutcome` must be `1`, `2`, `3`, or `4`.
- When `outExecContextOutcome = 2`, all blocker slots must be `0`.
- When `outExecContextOutcome = 1`, at least one blocker slot must contain a non-zero blocker, and no blocker slot may contain `10` or `11`.
- When `outExecContextOutcome = 3`, `outExecContextBlocker1` must be `10`.
- When `outExecContextOutcome = 4`, `outExecContextBlocker1` must be `11`.
- Non-zero blockers must be left-packed, ordered by provider priority, unique, and within the approved taxonomy.
- The provider must not publish timeframe, exchange, indicator, threshold, provider-internal, diagnostic, or debug detail through the public contract.

### Consumer validation rules

KR-380 shall validate the Version 2 public contract before consumption:

- Unsupported or invalid contract versions shall be rejected as unavailable.
- Invalid outcome or blocker combinations shall be rejected as unavailable.
- When `outExecContextAvailable = false`, KR-380 shall stop Execution Context processing, shall not interpret `outExecContextOutcome`, and shall not proceed with execution.
- When `outExecContextAvailable = true`, KR-380 shall treat `outExecContextOutcome` and ordered blockers as authoritative for Execution Context.
- KR-380 shall not reconstruct, supplement, reorder, or replace provider-owned Execution Context outcome or provider-owned blocker priority.
- KR-380 may combine separate KR-370 readiness blockers with provider-owned Execution Context blockers only for its own existing ordered execution blocker queue.
- `BUY NOW` and `SELL NOW` require a `QUALIFIED` Execution Context outcome, corresponding KR-370 READY state, and KR-380 final timing.
- `PENDING` maps to `FORMING` while KR-370 READY is present.
- `EXTENDED` and `FAILED` remain non-final until KR-380 final timing permits the corresponding public final state.
- The Execution Context Outcome shall never authorize trade execution by itself.

### Migration boundary for KR-390A, KR-390, and KR-705

The dependent readiness migration is approved as follows:

- KR-380 remains the sole authorized consumer of the entry Execution Context.
- KR-390A remains responsible for post-entry context eligibility under ADL-003 and shall not consume the entry Execution Context.
- KR-390 consumes KR-390A post-entry readiness and KR-380 confirmed execution outputs, not the entry Execution Context.
- KR-705 consumes KR-380 and KR-390 presentation outputs, not the entry Execution Context.
- Existing shared execution-chart readiness outputs may be removed only when KR-390A, KR-390, and KR-705 have migrated to the approved public outputs in the same reviewed implementation change.

### Version 2 governance

Version 2 is required because Version 1 cannot preserve the approved `PENDING`, `EXTENDED`, `FAILED`, and ordered-blocker responsibilities without consumer-side reconstruction of provider logic.

Version 1 is Superseded Before Implementation. Version 2 is the active contract for implementation.
