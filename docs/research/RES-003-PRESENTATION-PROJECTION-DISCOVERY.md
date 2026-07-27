# RES-003 — Presentation Projection Discovery

**Document ID:** RES-003<br>
**Title:** Presentation Projection Discovery<br>
**Version:** 0.1 Draft<br>
**Programme:** Human Interaction Architecture Programme<br>
**Programme Authority:** GOV-003<br>
**Programme Stage:** Discovery<br>
**Classification:** Architecture Discovery<br>
**Status:** Draft<br>
**Canonical Status:** Draft<br>
**Owner:** Chief Architect<br>
**Prepared By:** Product Master Architect (Human Interaction)<br>
**Review Authority:** Chief Architect<br>
**Repository Location:** `docs/research/RES-003-PRESENTATION-PROJECTION-DISCOVERY.md`<br>
**Workflow Stage:** Repository Publication<br>
**Architecture Authority:** None<br>
**Engineering Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published

---

## Authority Notice

This document contains exploratory, non-authoritative Discovery findings.

It does not approve Presentation Projection Architecture, establish Projection ownership, create a Platform capability, define a contract, authorize Security policy, or authorize Engineering, implementation, runtime behavior, persistence, deployment, or GUI development.

Repository authority remains vested exclusively in approved and canonical repository documents.

---

## 1. Executive Summary

Repository evidence supports a Presentation Projection as a provisional concept: a bounded, read-only, non-authoritative representation of already-established meaning prepared for a defined human-consumption purpose.

A Projection may be needed because an authoritative contract or record may contain:

- information unsuitable for human presentation;
- sensitive or licensed material;
- internal engineering detail;
- distinctions that must remain explicit;
- evidence whose visibility depends on role, purpose, environment, sensitivity, or Audit authority;
- information that could be misleading without qualification.

A Projection may select, carry, qualify, and safely omit information.

It cannot:

- create meaning;
- reinterpret meaning;
- correct authoritative meaning;
- rank;
- approve;
- execute;
- grant authority.

The repository does not support an absolute rule that every human-facing consumer must use a separately named Projection. KR-705 directly consumes explicitly public engine outputs and EAIC-001 Exchange Availability.

A separate Projection is justified where a source is not already presentation-safe or where bounded selection, qualification, security compliance, or Context-specific exposure is required.

Projection ownership remains unresolved.

---

## 2. Repository Review

### 2.1 Governing programme authority

This Discovery is governed by:

- GOV-003 — Human Interaction Architecture Programme Charter, Version 1.0;
- CAR-005 — Architecture Programme Governance Authorization, Version 1.0;
- DOC-001 — Document Identification, Classification & Metadata Standard, Version 1.1.

These authorities permit exploratory Discovery but do not authorize Projection Architecture, ownership, publication, Engineering, or implementation.

### 2.2 Discovery source relationship

Presentation Discovery and Presentation Context Discovery provide prior exploratory source material.

They are non-authoritative and not currently published repository artefacts.

Their findings are used only where consistent with approved repository evidence.

### 2.3 Platform authority

Applicable approved evidence includes:

- PLATFORM-000 — KRONOS Platform Constitution;
- Platform Overview;
- Platform Business Pipeline;
- Domain Ownership Matrix;
- Domain Dependency Matrix;
- DOMAIN-001 through DOMAIN-011;
- DATA_FLOW;
- ENGINE_OWNERSHIP;
- applicable approved Architecture Decision Records and legacy Architecture Decision Logs.

These authorities establish:

- contract-based consumption;
- single semantic ownership;
- no implicit authority;
- no internal access through transitive dependency;
- no hidden human completion;
- no duplicate semantic ownership.

No approved ownership or dependency matrix contains a generic Presentation Projection responsibility.

### 2.4 Explicit Projection evidence

The repository contains two approved explicit Projection precedents.

#### Provider Capability GUI Readiness

EDD-002 defines an optional, read-only, Provider-neutral Projection derived from a Capability Assessment Record.

It:

- contains no new authority;
- preserves currentness, limitations, and provenance;
- excludes credentials, entitlement, acquisition authority, controls, and business-readiness meaning;
- is intended for a future separately authorized Administration Console.

#### Provider Entitlement GUI Readiness

EDD-003 defines an optional, read-only Projection derived from a non-sensitive Entitlement Assessment Record.

It:

- creates no new meaning or authority;
- preserves currentness and supersession;
- excludes raw identity, authentication material, operational authority, execution permission, and business readiness;
- is withheld when unsafe or incomplete.

### 2.5 Future-Presentation classification evidence

EDD-005 classifies engineering outputs into:

- safe for future Presentation;
- prohibited;
- requiring future Security Architecture.

Safe candidates include non-sensitive:

- receipt status;
- compatibility and conformance;
- duplicate, replay, ordering, concurrency, and stale classifications;
- validation status;
- admission disposition;
- approved rejection classification;
- logical-response status;
- safe time meaning;
- provenance completeness;
- evidence completeness;
- reconstruction availability.

EDD-005 explicitly grants no Presentation Authority and defines no GUI, workflow, API, payload, access-control mechanism, or runtime behavior.

### 2.6 Direct-consumption evidence

KR-705 consumes public outputs from upstream engines and adapters. It does not require every input to be placed inside a separately named Projection.

Therefore:

> The repository supports Presentation Projections but does not establish them as the exclusive human-consumption path.

### 2.7 Explainability evidence

KR-710 owns deterministic blocker evidence.

KR-711 owns concise trader wording derived only from KR-710.

KR-705 displays those outputs.

This establishes that a Projection may carry an approved explanation without acquiring explanation ownership.

### 2.8 Repository limitations

The repository contains no approved generic definition of:

- Presentation Projection;
- Projection ownership;
- Projection dependency;
- Projection producer;
- Projection publisher;
- Projection lifecycle;
- Projection composition;
- Projection Security policy.

These matters remain unresolved.

---

## 3. Discovery Scope

This Discovery investigates:

- what a Presentation Projection may be;
- why it may exist;
- problems it may solve;
- source, eligibility, consumer, and Presentation boundaries;
- candidate responsibilities and exclusions;
- composition;
- lifecycle evidence;
- candidate ownership locations;
- risks.

It does not define:

- Projection fields;
- schemas;
- payloads;
- APIs;
- transport;
- persistence;
- caching;
- runtime publication;
- final ownership;
- a Platform capability;
- a generic contract;
- GUI representation.

---

## 4. Definition of Presentation Projection

### 4.1 Provisional definition

A Presentation Projection is a bounded, read-only, non-authoritative representation of already-established information, made suitable for an explicitly governed human-consumption purpose while preserving source meaning, source ownership, qualification, currentness, provenance, limitations, and authority boundaries.

### 4.2 Problem solved

A Projection separates:

- what an authoritative source knows;
- what may safely be exposed;
- what a human-consumption Context needs;
- what must remain hidden or qualified.

This can prevent Presentation from:

- inspecting source internals;
- independently interpreting records;
- treating technical visibility as permission to display everything;
- exposing sensitive information;
- collapsing important semantic distinctions.

### 4.3 Direct consumption is not universally prohibited

The repository does not support the conclusion that Presentation can never consume domain, product, or engine meaning directly.

Direct consumption is supported where:

- the output is explicitly public;
- the consumer is authorized;
- the output is already human-consumption-safe;
- no sensitive or misleading internal meaning is exposed;
- ownership and qualification are preserved.

KR-705 is the canonical current precedent.

### 4.4 When a separate Projection is justified

A separate Projection may be justified where:

- only part of a record is safe;
- sensitive information must be omitted;
- the source contract is not human-consumption-ready;
- currentness or limitations must accompany the value;
- explanation depth differs by Context;
- the source contains implementation or Provider-private detail;
- direct exposure could imply authority that does not exist;
- composition requires explicit source preservation.

### 4.5 Projection versus authoritative contract

An authoritative contract carries meaning owned by its source.

A Projection represents permitted portions without acquiring that ownership.

### 4.6 Projection versus Presentation Context

A Context identifies the human-consumption purpose and applicable constraints.

A Projection is information eligible for consumption within such a Context.

### 4.7 Projection versus Presentation

Presentation renders and supports human interaction.

A Projection contains no visual or interaction design.

### 4.8 Projection versus explanation

KR-710 and KR-711 establish explanation and wording.

A Projection may carry those outputs but does not invent or reprioritize them.

### 4.9 Projection versus Security policy

Security determines permissible exposure.

A Projection conforms to that determination. It does not classify information or grant access.

### 4.10 Projection versus implementation representation

A Projection does not imply:

- API;
- payload;
- schema;
- message;
- transport;
- database;
- cache;
- runtime object.

### 4.11 Projection versus workflow

A Projection does not advance activity or complete a domain responsibility.

### 4.12 Projection versus authority

Visibility of a Projection does not grant:

- eligibility;
- permission;
- approval;
- operational control;
- execution;
- governance authority.

---

## 5. Projection Responsibilities

The repository supports the following as candidate Projection requirements. It does not assign their final owner.

### 5.1 Bounded representation

A Projection may represent only meaning already established by an authoritative source.

It must not extend the source’s semantic scope.

### 5.2 Safe selection

A Projection may select a human-consumption-safe subset from an authoritative record or contract.

EDD-002 and EDD-003 demonstrate positive allow-lists and explicit prohibited-content lists.

### 5.3 Semantic preservation

A Projection must preserve distinctions such as:

- capability versus entitlement;
- eligibility versus authority;
- receipt versus validation;
- validation versus admission;
- admission versus interpretation;
- current versus stale;
- stale versus superseded;
- unavailable versus negative;
- indeterminate versus rejected.

### 5.4 Qualification carriage

A Projection may carry source-established:

- status;
- classification;
- evidence completeness;
- currentness;
- supersession;
- limitations;
- safe reason classification;
- non-sensitive provenance reference;
- safe time meaning.

The Projection does not own these meanings.

### 5.5 Security conformance

A Projection must conform to externally governed:

- Security classification;
- sensitivity;
- licensing;
- purpose;
- environment;
- role;
- Audit authority.

The Projection does not determine those constraints.

### 5.6 Safe omission

A Projection may omit information that is prohibited or unavailable for the applicable Context.

Omission must not be converted into:

- a false negative;
- an unsupported conclusion;
- a fabricated default;
- an assertion that the source lacks the information.

### 5.7 Explanation carriage

A Projection may carry:

- approved reason classifications;
- KR-710 deterministic evidence;
- KR-711 approved trader wording;
- source-owned limitation descriptions.

It may not generate or reprioritize explanation.

### 5.8 Composition

Projection composition is supported only as a provisional possibility.

Any composition must preserve:

- every contributing source;
- every source owner;
- each source’s qualification;
- each source’s provenance;
- each source’s currentness;
- product and Provider scope.

Composition must not create a new conclusion or shared semantic owner.

---

## 6. Projection Non-Responsibilities

A Projection does not own:

- Provider meaning;
- Instrument interpretation or identity;
- Market Facts;
- Business Judgment;
- research conclusions;
- product eligibility or ranking;
- Risk Approval;
- execution timing or orders;
- Portfolio state;
- Audit Trail meaning;
- engineering status determination;
- Security classification policy;
- access authority;
- provenance;
- currentness;
- explanation semantics;
- persistence;
- retention;
- workflow;
- orchestration;
- rendering;
- interaction.

### 6.1 Meaning

A Projection owns no authoritative meaning. It represents meaning owned elsewhere.

### 6.2 Security

A Projection does not own Security. It conforms to externally governed classification and visibility authority.

### 6.3 Authority

A Projection owns no operational or governance authority.

Projection eligibility and visibility confer no permission to act.

### 6.4 Explainability

A Projection does not own explanation semantics.

It may carry an approved explanation or evidence contract.

### 6.5 Currentness

A Projection does not determine currentness.

It carries or reflects currentness established by the authoritative source.

### 6.6 Provenance

A Projection does not create provenance.

It preserves attributable provenance or a governed provenance reference.

### 6.7 Prohibited behavior

A Projection must never:

- calculate missing business meaning;
- reinterpret rejection;
- convert technical success into downstream success;
- hide uncertainty required for correct interpretation;
- turn restricted evidence into unrestricted content;
- initiate an operation;
- act as an orchestration or feedback channel;
- grant command authority;
- replace its authoritative source.

---

## 7. Projection Boundaries

### 7.1 Source boundary

A Projection begins only after authoritative meaning exists.

It cannot repair, complete, or substitute for source determination.

The source remains authoritative if the Projection is:

- absent;
- withheld;
- stale;
- superseded;
- unavailable.

### 7.2 Eligibility boundary

A source being valid does not automatically make it safe for human presentation.

EDD-005 establishes that evidence safe for a downstream engineering boundary is not automatically safe for Presentation.

### 7.3 Security boundary

Projection eligibility depends on external classification.

Information may be:

- generally safe;
- prohibited;
- conditionally visible under future Security Architecture.

The Projection does not decide which class applies.

### 7.4 Consumer boundary

Explicit consumers evidenced by the repository include:

- a future Administration Console for GUI Readiness;
- KR-705 for approved public outputs;
- future Presentation consumers for EDD-005-safe statuses, subject to separate authority.

No generic consumer dependency is approved.

### 7.5 Producer boundary

Explicit producer evidence includes:

- Provider capability record projection;
- Provider entitlement record projection.

EDD-005 identifies source outputs that may support a future Projection but does not establish a Projection producer.

### 7.6 Composition boundary

A composite Projection must not:

- obscure sources;
- collapse distinct status meanings;
- create cross-domain authority;
- use one owner’s provenance for another source;
- use one owner’s currentness for another source;
- become product ranking or recommendation.

### 7.7 Context boundary

A Projection may be eligible for one human-consumption Context and unavailable to another due to externally governed visibility constraints.

This must not change the underlying semantic meaning.

### 7.8 Presentation boundary

A Projection ends before:

- rendering;
- visual representation;
- display state;
- selection;
- focus;
- expansion;
- comparison state;
- mode;
- temporary review state;
- interaction exposure.

### 7.9 External boundary

A Projection must not directly expose:

- credentials;
- secrets;
- tokens;
- authentication material;
- raw Provider payloads;
- SDK objects;
- restricted licensed content;
- internal Security controls;
- exploit-relevant detail;
- unrestricted evidence;
- implementation internals.

---

## 8. Projection Lifecycle

The repository does not define a generic Presentation Projection lifecycle.

EDD-002 and EDD-003 provide evidence for lifecycle concerns inherited from their source records.

### 8.1 Supported conceptual sequence

1. Authoritative source meaning is established.
2. The source is assessed against externally governed Projection eligibility.
3. A safe Projection may be made available.
4. An unsafe or incomplete Projection is withheld.
5. An authorized consumer may consume the Projection.
6. Source currentness, staleness, supersession, or indeterminacy remains visible.
7. A later Projection may reflect a later authoritative source state.

This sequence is Discovery evidence, not an approved state machine.

### 8.2 Lifecycle constraints

- A Projection does not create source currentness.
- A Projection must not appear current when its source is stale or superseded.
- Failure to form a Projection does not invalidate the source.
- Withholding a Projection does not mean the source fact is false.
- Supersession must remain non-destructive.
- No Projection persistence or retention lifecycle is established.
- No runtime generation mechanism is implied.
- No decision is made about whether a Projection is generated once, repeatedly, or conceptually at a boundary.

---

## 9. Candidate Ownership Analysis

No candidate is selected.

### 9.1 Authoritative producer or domain capability

**Supporting evidence:**

- EDD-002 and EDD-003 identify Provider record projections.
- The producer is close to source meaning, limitations, and currentness.

**Unresolved concern:**

- Producer-side ownership could cause domains to acquire Human Interaction and audience responsibilities.

### 9.2 Human Interaction capability

**Supporting evidence:**

- Projection exists for human consumption.
- KR-705 performs bounded display.
- KR-711 performs trader-facing translation.

**Unresolved concern:**

- Human Interaction formation could acquire source interpretation, Security classification, or duplicate semantic meaning.

### 9.3 Platform-support capability

**Supporting evidence:**

- PLATFORM-000 assigns communication mechanisms to Platform and requires semantic neutrality.
- A common Projection concern might support consistency across domains.

**Unresolved concern:**

- Projection is not currently an approved Platform responsibility.
- Establishing it as such could change frozen Architecture and require an approved decision.

### 9.4 Contract-specific Projection responsibility

**Supporting evidence:**

- GUI Readiness is attached to specific Provider capability and entitlement contracts.

**Unresolved concern:**

- Contract-specific treatment may create inconsistent rules or duplicate cross-cutting concerns.

### 9.5 Composite or shared ownership

**Supporting pressure:**

- Multi-source human composition may appear to require shared responsibility.

**Unresolved concern:**

- Shared semantic ownership conflicts with PLATFORM-000 and the Domain Ownership Matrix.

It must not be assumed.

### 9.6 Unresolved ownership questions

Later Architecture would need to distinguish:

1. who owns authoritative source meaning;
2. who determines Projection eligibility;
3. who forms the Projection;
4. who publishes it;
5. who consumes it;
6. who governs Security classification.

These responsibilities need not belong to the same authority, but no arrangement may create duplicate semantic ownership.

---

## 10. Architectural Risks

| Risk | Consequence | Discovery control |
|---|---|---|
| Projection becomes business logic | Selection or composition creates a new decision. | Prohibit semantic inference. |
| Projection becomes Presentation | Projection defines display or interaction behavior. | End Projection at the information boundary. |
| Projection becomes API design | Discovery defines fields, schemas, or transport. | Keep representation conceptual. |
| Projection becomes persistence | Currentness becomes a storage model. | Preserve source lifecycle without selecting persistence. |
| Projection becomes orchestration | Projection availability initiates activity. | Preserve terminal, non-feedback consumption. |
| Ownership leakage | Projection becomes owner of represented facts. | Preserve source ownership. |
| Authority leakage | Visibility is interpreted as permission. | Carry explicit qualification where material. |
| Security ownership leakage | Projection determines who may see information. | Keep classification external. |
| Explainability invention | Projection generates unsupported reasons. | Carry only approved explanations. |
| Currentness invention | Projection calculates freshness without source authority. | Carry source-established currentness. |
| Provenance distortion | Provenance becomes a new conclusion. | Preserve provenance as attribution. |
| Semantic collapse | Distinct statuses become one simplified result. | Preserve exact source distinctions. |
| False absence | Withheld information appears false at source. | Represent withholding explicitly. |
| Projection proliferation | Consumers create divergent meanings. | Future governance should examine consistency. |
| Mandatory-Projection overreach | Already-safe public outputs are needlessly wrapped or re-owned. | Preserve direct consumption where authorized. |
| Direct-consumption overreach | Presentation accesses rich source internals. | Require Projection where the source is not already presentation-safe. |
| Draft treated as Architecture | Provisional Projection concepts become implementation assumptions. | Preserve Draft status and separate Architecture Authorization. |

---

## 11. Recommendations

Before any Architecture selects Projection ownership or establishes a generic capability, future governed work should:

1. decide whether a Presentation Projection is:
   - mandatory for all human consumption;
   - mandatory only for sources that are not already presentation-safe;
   - one of several authorized consumption boundaries;
2. distinguish:
   - authoritative producer;
   - Projection-eligibility authority;
   - Projection former;
   - Projection publisher;
   - human-consumption Context;
3. establish semantic-preservation invariants;
4. investigate mandatory qualification attributes without defining schemas;
5. investigate redaction, withholding, indeterminacy, and false-absence treatment;
6. determine when multi-source composition requires a separately governed Projection;
7. determine how approved explanation enters a Projection without transferring ownership;
8. require future Security Architecture for conditionally sensitive information;
9. assess impacts on:
   - PLATFORM-000;
   - Domain Ownership Matrix;
   - Domain Dependency Matrix;
   - DATA_FLOW;
   - Product Architecture;
   - ENGINE_OWNERSHIP;
10. preserve existing direct KR-705 consumption unless later approved Architecture changes it;
11. require an approved architectural decision if Projection becomes a new Platform responsibility, dependency, or ownership assignment.

No final ownership conclusion is supported during Discovery.

---

## Discovery Conclusion

The repository supports Presentation Projection as a useful provisional concept but not as an approved generic capability.

Projection is supported where authoritative information requires bounded, non-authoritative, human-consumption-safe representation. It is not proven necessary for every public output.

Projection does not own meaning, Security, authority, explainability, currentness, or provenance. It may carry those meanings only as established elsewhere.

The repository does not decide whether Projection belongs to an authoritative producer, Human Interaction, Platform support, or a contract-specific boundary.

This document grants no Architecture or downstream authority.

---
