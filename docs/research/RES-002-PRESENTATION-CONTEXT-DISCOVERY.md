# RES-002 — Presentation Context Discovery

**Document ID:** RES-002<br>
**Title:** Presentation Context Discovery<br>
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
**Repository Location:** `docs/research/RES-002-PRESENTATION-CONTEXT-DISCOVERY.md`<br>
**Workflow Stage:** Repository Publication<br>
**Architecture Authority:** None<br>
**Engineering Authority:** None<br>
**Implementation Authority:** None<br>
**Runtime Authority:** None<br>
**Repository Status:** Published

---

## Authority Notice

This document contains exploratory, non-authoritative Discovery findings.

It does not approve Presentation Context Architecture, establish a context, assign ownership, define a role or workflow, authorize commands, create Security policy, or authorize Engineering, implementation, runtime behavior, persistence, deployment, or GUI development.

Repository authority remains vested exclusively in approved and canonical repository documents.

---

## 1. Executive Summary

A Presentation Context is provisionally discoverable as a governed human-consumption envelope that identifies:

- why information is being presented;
- for whom it is being presented;
- which authoritative information is eligible for composition;
- which externally governed visibility classifications constrain that consumption;
- what presentation-local review and display state may exist;
- which interactions have already been made available through separately governed authority and command boundaries.

A Presentation Context is not:

- a screen;
- a role;
- a product;
- a workflow;
- a domain;
- a source of authority.

A Context may compose information from multiple authoritative owners. It does not own that information or derive new business or engineering meaning from its combination.

A Context may hold presentation-local:

- display state;
- selection;
- focus;
- expansion;
- comparison;
- mode;
- temporary review state.

Such state must not alter platform meaning or complete a domain responsibility.

Repository evidence most strongly supports:

- a trader-facing candidate context;
- a future Administration Console candidate context.

An Engineering Console candidate is partially supported by Developer Mode, engineering observability, and future-Presentation evidence.

Research, Validation, and Operations contexts are not currently established by approved repository authority.

No generic context identity, access model, Security model, Projection contract, or command model is approved.

---

## 2. Repository Review

### 2.1 Governing programme authority

This Discovery is governed by:

- GOV-003 — Human Interaction Architecture Programme Charter, Version 1.0;
- CAR-005 — Architecture Programme Governance Authorization, Version 1.0;
- DOC-001 — Document Identification, Classification & Metadata Standard, Version 1.1.

These authorities preserve Discovery as Draft and non-authoritative. They do not authorize Presentation Context Architecture or any context implementation.

### 2.2 Discovery source relationship

Presentation Discovery supplies prior exploratory source meaning for this document.

Because no Human Interaction Discovery artefacts are currently published, that source remains an unapproved working source rather than repository authority.

All retained conclusions in this document remain subordinate to approved repository evidence.

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

The repository establishes:

- contract-based consumption;
- single semantic ownership;
- no implicit authority;
- no hidden human completion;
- no unapproved dependency cycles;
- read-only Audit;
- ADR-controlled change.

### 2.4 Context-related engineering evidence

Applicable evidence includes:

- EDD-002 GUI Readiness for a future Administration Console;
- EDD-003 GUI Readiness for a future Administration Console;
- EDD-005 classifications for safe, prohibited, and security-dependent future Presentation information;
- EAP-003 and EAP-004 qualification, provenance, currentness, security, and ownership boundaries.

EDD-005 explicitly identifies role, purpose, environment, sensitivity, and Audit authority as possible future visibility constraints.

### 2.5 Trader-facing evidence

ENGINE_OWNERSHIP and DATA_FLOW establish:

- KR-705 trader-facing display;
- Trader and Developer presentation modes;
- public-output consumption;
- presentation-only diagnostics;
- KR-710 deterministic blocker evidence;
- KR-711 concise trader wording.

These establish evidence for different human-consumption purposes and explanation depths without changing underlying meaning.

### 2.6 Research evidence

Research remains evidence and inquiry, not approved Architecture or a Platform domain.

Draft research-first material cannot establish a Research Workbench, candidate-presentation boundary, or human-decision workflow.

### 2.7 Security limitation

Security Architecture remains incomplete. No approved role taxonomy, access-control model, cross-context visibility policy, or identity model exists.

### 2.8 Terminology limitation

“Context” is used elsewhere in KRONOS for meanings such as Provider Context and Execution Context. A Presentation Context must not absorb or reinterpret those existing concepts.

### 2.9 Repository limitations

The repository does not define:

- a generic Presentation Context;
- context identity;
- context lifecycle;
- cross-context access;
- generic Context ownership;
- Context commands;
- Context persistence;
- generic composition contracts.

These matters remain unresolved.

---

## 3. Discovery Scope

This Discovery investigates:

- what constitutes a Presentation Context;
- the properties that may distinguish one Context from another;
- candidate Contexts supported by repository evidence;
- Context responsibilities and exclusions;
- Context state;
- explainability;
- security and visibility;
- boundaries with domains, products, Engineering, Research, and humans.

It does not define:

- screens;
- layouts;
- navigation;
- workflows;
- user journeys;
- access-control implementation;
- command handling;
- projection fields;
- APIs;
- persistence;
- runtime behavior;
- technology.

---

## 4. Definition of Presentation Context

### 4.1 Provisional definition

A Presentation Context is a governed, purpose-bounded human-interaction envelope within which information made available through authorized repository boundaries may be composed and presented under explicit scope, visibility, qualification, and non-authority constraints.

### 4.2 Candidate identifying properties

A Context may be identified by a combination of:

- human-consumption purpose;
- intended audience;
- eligible authoritative information;
- source-owner preservation;
- product scope where applicable;
- Provider scope where applicable;
- environment;
- externally governed Security classification;
- evidence and Audit visibility;
- currentness and qualification requirements;
- permitted presentation-local state;
- interactions already authorized by separately governed boundaries;
- explicit prohibitions on inference, orchestration, and authority.

These are Discovery properties, not an approved identity model.

### 4.3 Context versus Screen

A screen is a possible visual representation.

A Context remains conceptually meaningful without defining a visual layout and may eventually be represented in more than one way.

This document defines no screen.

### 4.4 Context versus Role

A role is an authority or visibility attribute.

Role may constrain access to a Context, but role alone does not establish:

- purpose;
- product scope;
- Provider scope;
- eligible information;
- explanation depth;
- permitted interaction.

No role model is approved.

### 4.5 Context versus Product

A product owns its approved product meanings, universe, eligibility, evidence requirements, and decision semantics.

A Context may be product-scoped, but it does not become the product or acquire product ownership.

### 4.6 Context versus Workflow

A workflow represents progression through activities or authoritative state.

A Context governs human consumption and presentation-local review. It must not advance business processing or become a hidden process controller.

### 4.7 Context versus Domain

A domain owns authoritative semantic meaning.

A Context consumes information derived from domain or product authority. It does not become a domain.

### 4.8 One human and multiple Contexts

One human may in principle require access to more than one human-consumption purpose.

A Context is not identical to a person. Actual access, role separation, and privilege boundaries remain unresolved pending Security Architecture.

### 4.9 One Context and multiple domains

One Context may consume information from multiple authoritative domains or product authorities.

Every source owner and qualification must remain distinct. Composition must not create a new semantic owner.

### 4.10 Information ownership

A Context owns no authoritative information.

It may own only presentation-local state and composition permitted by upstream governance.

### 4.11 Command ownership

No generic command authority is approved.

A Context may expose only interactions made available through separately governed authority and command boundaries.

The authoritative owner remains responsible for:

- command meaning;
- eligibility;
- acceptance;
- rejection;
- execution;
- outcome;
- Audit consequences.

### 4.12 Workflow ownership

A Context owns no business, engineering, validation, research, execution, or governance workflow.

Temporary presentation review state must not be treated as domain completion.

---

## 5. Candidate Context Analysis

| Candidate | Repository evidence | Discovery assessment |
|---|---|---|
| Engineering Console | KR-705 Developer Mode; KR-710 deterministic evidence; non-sensitive engineering observability; EDD-005 future-Presentation status classifications. | Partially justified as a candidate purpose. No approved named Context, user population, complete projection boundary, or authority exists. |
| Research Workbench | Research library and Draft research-first material. | Not currently justified. Research is evidence governance, not an approved runtime domain or human-consumption Context. |
| Validation Workbench | Validation owns Business Judgment; KR-370 publishes decisions and blockers. | Not currently justified as a distinct Context. Human review cannot complete or replace Validation. |
| Trader Workstation | KR-705 trader-facing display; Trader Mode; KR-711 trader wording; DATA_FLOW trader-facing endpoint. | Strongly justified as a candidate family. The name, Context boundary, security classification, and complete information set remain unapproved. |
| Operations Console | Non-sensitive observability and boundary statuses. | Not currently justified as a named Context. Operations ownership, users, authority, and command boundaries are absent. |
| Administration Console | ADR-007, ADR-008, EDD-002, and EDD-003 explicitly identify a future consumer of read-only GUI Readiness. | Strongly justified as a narrowly bounded candidate. Existing evidence grants no operational authority. |

A Context is not justified merely because information exists. It requires a distinct human-consumption purpose and a governed information boundary.

---

## 6. Context Dimensions

| Dimension | Repository support | Discovery finding |
|---|---|---|
| Audience | Trader, Developer Mode, future Administration Console. | Retained. Audience may affect explanation depth, not semantic meaning. |
| Role | EDD-005 identifies role-dependent visibility; Audit authority remains distinct. | Retained as a candidate visibility constraint. No role model is approved. |
| Purpose | Trader explanation, administration readiness, diagnostics, Audit review. | Retained as a constitutive candidate dimension. |
| Product | Product consumption must be explicit; KR-705 is product-facing. | Retained where applicable. Product scope does not alter upstream meaning. |
| Provider | Provider identity and Provider-scoped capability or entitlement information. | Retained where the information is legitimately Provider-scoped. |
| Environment | EAP-003, EDD-004, and EDD-005 preserve environment-specific authority and security constraints. | Retained. |
| Security classification | Explicit throughout EAP-003 and EDD-005. | Retained as an externally governed constraint. |
| Authority | Eligibility, authority, receipt, validation, admission, and interpretation are separated. | Retained as qualification that a Context must represent accurately. |
| Sensitivity | EDD-005 distinguishes safe, prohibited, and conditional information. | Retained. |
| Evidence visibility | EDD-002 through EDD-005 and KR-710. | Retained. |
| Audit visibility | Audit is read-only and publishes Audit Trail meaning for review. | Retained subject to Audit and Security authority. |
| Currentness | Provider snapshots and GUI Readiness include currentness and supersession. | Retained. |
| Explainability | KR-710 and KR-711 establish audience-specific explanation evidence. | Retained where an authoritative explanation contract exists. |
| Qualification | Evidence sufficiency, readiness, indeterminacy, rejection, and limitations recur throughout the repository. | Retained. |

A Context boundary may be indicated when a change in purpose, eligible information, product or Provider scope, environment, sensitivity, evidence visibility, or authority qualification changes what may safely be presented.

A visual change alone does not establish a new Context.

---

## 7. Context Responsibilities

A Presentation Context may provisionally own only presentation-local responsibilities, including:

- its declared human-consumption purpose;
- composition permitted by upstream governance;
- preservation of source-owner visibility;
- preservation of qualification visibility;
- presentation-local selection;
- presentation-local focus;
- presentation-local expansion;
- presentation-local comparison configuration;
- presentation mode;
- temporary review state;
- choice among explanation depths already made available for the applicable audience;
- explicit representation of missingness, uncertainty, currentness, and limitations;
- conformance to externally governed visibility classifications;
- exposure only of interactions already authorized through separately governed authority and command boundaries.

A Context does not determine Security policy, grant access, establish authority, or authorize commands.

Composition means arranging independently owned information for comprehension. It does not mean fusing information into a new conclusion.

---

## 8. Context Non-Responsibilities

A Context does not own:

- Provider semantics or acquisition;
- Instrument identity or interpretation;
- Market schedules or Market Facts;
- Validation or Business Judgment;
- research evidence acceptance or conclusions;
- product eligibility, ranking, or decision semantics;
- Risk Approval;
- execution timing, execution action, or orders;
- Portfolio state;
- Configuration or credentials;
- Event meaning;
- Audit Trail meaning;
- engineering calculations or status determination;
- Security policy or visibility classification;
- business or engineering workflow;
- command meaning or execution;
- persistence;
- orchestration;
- governance approval.

### 8.1 Prohibited responsibilities

A Context must never:

- infer business meaning from technical status;
- infer availability from missing or stale information;
- treat visibility as authority;
- treat review as Validation;
- treat temporary acknowledgement as approval;
- recalculate upstream results;
- suppress material qualification or uncertainty;
- create semantic feedback into an authoritative domain;
- use local state as platform truth;
- represent redacted information as a negative source fact;
- expose information contrary to governed classification;
- expose an interaction that has not been separately authorized.

---

## 9. Context Boundaries

### 9.1 Upstream boundary

A Context consumes only:

- separately governed presentation-safe information;
- approved read-only projections;
- existing public outputs explicitly authorized for Presentation.

A Context must not:

- inspect producer internals;
- use transitive dependencies to access upstream sources;
- consume raw Provider or engineering content merely because it exists;
- bypass product-consumption contracts.

### 9.2 Downstream boundary

The normal downstream party is a human.

Human comprehension, review, or discretionary action does not transfer authority to the Context.

### 9.3 Domain boundary

No Context may become an authoritative upstream dependency of:

- Instrument;
- Observation;
- Validation;
- Risk;
- Execution;
- Portfolio;
- Audit.

### 9.4 External boundary

Providers, exchanges, brokers, research sources, and licensed datasets remain behind their authoritative platform boundaries.

A Context does not integrate with or control them directly.

### 9.5 Interaction boundary

A Context may expose an interaction only when a separately governed authority and command boundary has already made that interaction available.

The Context does not:

- create command meaning;
- decide command eligibility;
- accept or reject commands;
- execute commands;
- own command results.

### 9.6 Security boundary

A Context conforms to externally governed visibility classifications.

It does not:

- classify information;
- grant access;
- enforce Security policy as an architectural owner;
- infer privilege from audience or purpose;
- transfer visibility between Contexts.

### 9.7 Prohibited boundaries

The following are prohibited:

- semantic feedback into domain determinations;
- observability controlling engineering decisions;
- review state completing a domain activity;
- direct domain mutation without an authorized contract;
- hidden command execution;
- hidden human approval;
- cross-context privilege inheritance;
- unrestricted evidence sharing between Contexts.

---

## 10. Human Interaction Principles

### 10.1 Governed consumption

Human interaction begins with information made available through an authorized boundary, not with an accessible internal representation.

### 10.2 Semantic transparency

A Context must preserve what a status means and, where material, what it does not mean.

### 10.3 Ownership visibility

Composed information must remain attributable to its authoritative owner.

### 10.4 Provenance visibility

Relevant provenance or governed provenance availability should remain visible where required for trust, explanation, or review.

### 10.5 Audience-bounded explainability

Explanation depth may differ by Context. The underlying rule, status, and result may not.

### 10.6 Currentness visibility

Current, stale, superseded, unavailable, and indeterminate information must remain distinguishable.

### 10.7 Qualification visibility

Eligibility, authority, receipt, validation, admission, interpretation, readiness, and execution must not be collapsed.

### 10.8 Explicit uncertainty

Missingness and ambiguity must not become convenient answers.

### 10.9 No hidden orchestration

Human interaction must not become an undocumented dependency or business-process controller.

### 10.10 No hidden authority

Display, selection, focus, expansion, comparison, mode, temporary acknowledgement, or review does not imply permission, approval, or execution.

---

## 11. Explainability Discovery

### 11.1 Repository-supported explainability

Repository evidence supports exposing, where applicable:

- semantic owner;
- status;
- qualification;
- currentness;
- supersession;
- non-sensitive provenance reference;
- evidence class;
- evidence completeness;
- limitations;
- indeterminacy;
- deterministic blocker evidence;
- concise audience-appropriate explanation.

KR-710 establishes detailed deterministic blocker evidence. KR-711 establishes concise trader wording without recalculating or reprioritizing the blocker.

### 11.2 Universal explainability remains unresolved

The proposition that every significant visible fact should expose:

- owner;
- provenance;
- qualification;
- currentness;
- evidence availability;
- limitations;
- permitted actions;

is strongly supported as a future proposal, but not yet established as a universal requirement.

The repository does not define:

- significant fact;
- mandatory versus on-demand attributes;
- security-safe provenance depth;
- applicability across every domain;
- generic redaction semantics;
- a generic permitted-action contract.

### 11.3 Permitted actions

Where information could reasonably be interpreted as actionable, a future architecture may need to expose whether any interaction is available.

The Context must not create that permission. It may expose only what a separately governed authority has established.

---

## 12. Context State Discovery

### 12.1 Presentation-local display state

Display state may be local when it changes only how already-governed information is presented.

### 12.2 Selection state

Selection may identify which governed item is currently under human attention.

It must not create product eligibility, priority, ranking, or approval.

### 12.3 Focus state

Focus may identify the information currently emphasized for presentation.

It must not change semantic importance or source authority.

### 12.4 Expansion state

Expansion may control whether already-eligible detail is currently exposed.

It must remain subject to the same externally governed visibility classification.

### 12.5 Comparison state

Comparison state may record which governed items have been selected for side-by-side human review.

It must not create an unowned ranking, judgment, or recommendation.

### 12.6 Mode state

Mode may select among already-authorized explanation or diagnostic depths, such as trader-facing versus developer-facing information.

Mode must not alter the underlying result.

### 12.7 Temporary review state

Temporary review state may indicate:

- viewed;
- selected;
- focused;
- expanded;
- compared;
- temporarily acknowledged.

It must not mean:

- validated;
- approved;
- accepted;
- admitted;
- executed;
- audited;
- completed.

### 12.8 State that is never presentation-local

The following are never presentation-local:

- domain facts;
- canonical identity;
- Business Judgment;
- product eligibility;
- Risk Approval;
- execution state;
- Provider capability or entitlement;
- Security classification;
- role or access authority;
- provenance meaning;
- currentness meaning;
- command acceptance or outcome;
- Audit Trail;
- research conclusion status;
- authoritative approval.

If review state must influence a domain or become durable evidence, its owner and contract must be established outside the Context.

---

## 13. Security Discovery

### 13.1 Information that may vary by Context

Subject to future Security Architecture:

- whether information is visible;
- explanation depth;
- identifier detail;
- provenance detail;
- evidence availability;
- reconstruction availability;
- rejection detail;
- replay or duplicate detail;
- lineage and supersession detail;
- precise time visibility;
- licensing and retention detail;
- diagnostics;
- Audit scope.

### 13.2 Information that must not vary semantically

Contexts must not disagree about:

- the authoritative fact or decision;
- its owner;
- the meaning of its status;
- its currentness;
- its qualification;
- whether it is indeterminate;
- its material limitations;
- whether authority exists.

A Context may omit or redact information when externally governed classification requires it. It must not replace redaction with a false semantic value.

### 13.3 Future Security Architecture requirement

Future Security Architecture is required before Contexts expose:

- credentials, secrets, tokens, or authentication material;
- raw Provider content;
- raw account or personal identity;
- detailed Provider, dataset, partition, snapshot, submission, or authority identifiers;
- detailed rejection and replay evidence;
- lineage and supersession relationships;
- retained-evidence references;
- precise times;
- restricted licensed information;
- exploit-relevant diagnostics;
- detailed reconstruction material;
- cross-context Audit evidence;
- commands or authoritative approvals.

---

## 14. Architectural Risks

| Risk | Consequence | Discovery control |
|---|---|---|
| Context becomes workflow | Human activity silently completes platform work. | Preserve domain completion independently. |
| Context becomes business logic | Composition creates recommendations or decisions. | Prohibit semantic inference. |
| Context becomes engineering | Diagnostics are recalculated or used for control. | Consume engineering-owned information only. |
| Hidden authority | A visible state appears to grant permission. | Preserve explicit authority qualification. |
| Hidden orchestration | Review or display activity triggers ungoverned action. | Expose only separately authorized interactions. |
| Duplicated ownership | Context becomes a second semantic owner. | Preserve source ownership. |
| Presentation inference | Missingness or composition creates meaning. | Preserve explicit uncertainty. |
| Security leakage | Sensitive information crosses Context boundaries. | Conform to external classifications. |
| Security ownership leakage | Context becomes responsible for determining policy. | Keep Security policy external. |
| Context ambiguity | Context is confused with screen, role, product, or domain. | Preserve conceptual distinctions. |
| Explainability failure | Humans cannot distinguish result, basis, and limitation. | Carry governed explanation and qualification. |
| Cross-context contradiction | Different Contexts present different semantic meaning. | Preserve semantic invariance. |
| Redaction ambiguity | Hidden information appears negative or absent at source. | Represent withholding explicitly. |
| Candidate inflation | Every concern becomes a separate Context. | Require a distinct evidence-supported purpose. |
| Local state leakage | Temporary review state becomes authoritative. | Keep local state non-authoritative. |

---

## 15. Recommendations for Presentation Projection Discovery

A subsequent Discovery should investigate:

1. the architectural concept of a Presentation Projection;
2. the relationship between authoritative contracts and projections;
3. whether projections are always required or only required for information not already presentation-safe;
4. source-owner preservation;
5. provenance, currentness, qualification, limitation, and evidence requirements;
6. semantic invariance across Contexts;
7. safe omission, redaction, and unavailable-state treatment;
8. audience-specific explanation depth;
9. Provider- and product-scoped projections;
10. composition without semantic fusion;
11. Projection eligibility and Security constraints;
12. actionable information and separately governed command boundaries;
13. prohibited Projection content;
14. candidate ownership locations without assigning ownership;
15. potential impacts on frozen ownership, dependencies, and DATA_FLOW.

No Projection owner, dependency, contract, or platform capability should be established during Discovery.

---

## Discovery Conclusion

Presentation Context is supported as a provisional human-consumption boundary rather than a screen, role, product, workflow, or domain.

It may hold only bounded presentation-local review and display state. It conforms to externally governed visibility classification, exposes only separately authorized interactions, and owns no business, engineering, Security, command, or governance meaning.

No Context Architecture is approved by this document.

---
