# ADP-001E — Observation Domain Architecture

**Status:** Approved

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Owner:** Chief Architect

**Prepared By:** Codex Engineering Team

**Approved By:** Chief Architect

**Classification:** Architecture Documentation Package

**Architecture Impact:** Approved canonical Observation Domain architecture

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Status and Governance

This document is approved canonical architecture. It does not authorize factual-data acquisition, Observation creation, publication, runtime communication, an interface, an Engineering Design Document, an Engineering Package, or any implementation change.

The following labels govern this document:

- **Approved base** identifies architecture already approved in ADP-001A, ADP-001B, ADP-001C, ADP-001D, or another approved repository document.
- **Chief Architect-approved direction** identifies architectural direction approved through the Chief Architect's final review and incorporated into this canonical architecture.
- **Deferred** identifies a capability or detail excluded from this document.

The Chief Architect approved the architecture, and Engineering Architect verification passed. ADP-001E is approved canonical architecture. No ADR, implementation, runtime contract, follow-on capability, or engineering work is authorized.

## 2. Purpose

Define the KRONOS Swing Observation Domain architecture for owning and preserving factual market state that is authoritative within KRONOS's governed factual architecture, attributable, and temporally meaningful without introducing business interpretation, Validation judgment, or trading meaning.

ADP-001E elaborates the approved Observation ownership boundary. It does not amend the Platform Constitution, domain ownership, domain dependencies, engine ownership, data flow, ADP-001A through ADP-001D, or any approved interface.

## 3. Architectural Problem

Approved architecture assigns external information and Provider meaning to Provider, canonical identity to Instrument, Market Schedule and session meaning to Market, Market Facts to Observation, and Business Judgment to Validation.

Availability, acquisition success, normalization, admissibility, and approved subject attribution are each insufficient to create a governed Observation. KRONOS therefore requires an explicit Observation architecture that defines factual authority without:

- converting Provider information automatically into factual state that is authoritative within KRONOS's governed factual architecture;
- allowing factual state to create or alter canonical identity;
- transferring Market Schedule or session meaning into Observation;
- treating factual acceptance as Validation judgment;
- presenting factual state that is authoritative within KRONOS's governed factual architecture as infallible external truth;
- concealing uncertainty, ambiguity, missingness, partiality, correction, or supersession; or
- introducing implementation, transport, persistence, or processing design.

### Central architectural question

> What is a governed factual Observation in KRONOS, and what architectural responsibilities are required to preserve factual market state without introducing interpretation, validation, or trading meaning?

ADP-001E defines a governed Observation as an Observation-owned factual assertion with an approved attributable subject, explicit temporal meaning, preserved provenance and lineage, and explicit factual limits. Observation authority establishes a factual record that is authoritative only within KRONOS's governed factual architecture; it does not guarantee absolute external truth, exchange authority, Provider infallibility, objective correctness beyond represented provenance and known factual limits, evidence quality, or fitness for action.

## 4. Scope

This document covers only:

- Observation Domain purpose, authority, ownership, and non-ownership;
- the architectural definition and essential characteristics of a governed Observation;
- factual state that is authoritative within KRONOS's governed factual architecture;
- Observation acceptance as an architectural concept;
- approved subject attribution;
- fact-versus-interpretation boundaries;
- bounded derived factual Observations;
- architectural Observation taxonomy;
- temporal semantics;
- provenance and factual lineage;
- conceptual lifecycle;
- correction and supersession;
- availability, missingness, partiality, and completeness;
- relationships with Provider, Instrument, Market, and future Validation;
- architectural invariants and prohibitions;
- conceptual, technology-independent models;
- conformance with ADP-001A through ADP-001D;
- confirmation that no unresolved architectural question blocks canonical approval; and
- deferred capabilities.

This document applies only within KRONOS Swing Phase 1 — Market Data Foundation and does not expand the approved information inventory, instrument universe, market model, product boundary, or domain dependency matrix.

## 5. Out of Scope

This document does not define, authorize, or recommend:

- APIs, interfaces, schemas, fields, payloads, file formats, or serialization;
- databases, tables, persistence, repositories, retention, or storage models;
- events, queues, streams, polling, transport, publication mechanisms, or synchronization;
- adapters, services, modules, classes, runtime components, or runtime state machines;
- timestamps formats, clocks, synchronization, lateness thresholds, sequence algorithms, or event-time processing;
- retrieval, Kite integration, Provider → Observation runtime communication, or acquisition sequencing;
- candle, quote, depth, or Open Interest structures or construction;
- correction-processing, temporal-ordering, aggregation, or derivation algorithms;
- formulas, indicators, thresholds, scores, ranking, confidence, or opportunity logic;
- Validation logic, evidence judgment, evidence sufficiency, or suitability for trading;
- strategy, BUY/SELL logic, BUY READY, SELL READY, BUY NOW, SELL NOW, execution, orders, positions, or automated trading;
- TradingView or Pine Script;
- Options capability or any expansion of approved Swing scope;
- an ADR, an EDD, an Engineering Package, tests, or runtime code; or
- ADP-001F or any follow-on architecture capability.

## 6. Governing Direction

**Chief Architect-approved direction:**

> Observation is the exclusive architectural authority for governed factual market state. It preserves what was observed, about what approved attributable subject, for what temporal context, from what provenance, and with what factual limits. It does not decide what the fact means, whether it is useful as evidence, or what action should follow.

ADP-001E also preserves the approved ADP-001D principle:

> Facts do not possess identity. They are attributed to identity.

These directions require the following separation:

- Provider owns external information and Provider meaning.
- Instrument owns canonical Instrument identity and Instrument meaning.
- Market owns Market Schedule, session definitions, and authoritative market-context meaning.
- Observation owns factual market state that is authoritative within KRONOS's governed factual architecture.
- Validation owns Business Judgment and may later govern evidentiary judgment under separately approved architecture.

This document shall never convert these separate authorities into shared ownership.

## 7. Terminology

| Term | Architectural meaning in this document |
| --- | --- |
| Observation | An Observation-owned factual assertion that is authoritative within KRONOS's governed factual architecture. It carries no business, evidentiary, or trading judgment. |
| Market Fact | Factual market state owned by Observation and authoritative within KRONOS's governed factual architecture that answers what happened, was reported, was available, was absent, or was revised. |
| Factual State | A factual assertion about a defined subject and temporal context, preserved with applicable provenance and known limits. |
| Candidate Observation | Candidate factual information available for possible Observation participation that has not been accepted and is not owned by Observation. It may concern any approved attributable subject within the Phase 1 subject scope. |
| Admissibility | Satisfaction of approved architectural eligibility conditions. Admissibility does not imply correctness, acceptance, ownership, publication, validation, or fitness for use. |
| Observation Acceptance | Observation's exclusive semantic architectural decision to accept candidate factual information as a governed Observation. Acceptance produces Observation ownership of the accepted factual record but is not itself that ownership state. This document defines no acceptance mechanism. |
| Observation Ownership | The resulting architectural state in which Observation owns the accepted factual record and its factual meaning within KRONOS's governed factual architecture. |
| Observation Authority | Observation's exclusive architectural responsibility to assign and govern factual meaning that is authoritative within KRONOS's governed factual architecture. It is not a claim of absolute external truth, exchange authority, Provider infallibility, or objective correctness beyond represented provenance and known factual limits. |
| Approved Attributable Subject | An approved subject owned by the domain architecturally responsible for its meaning. Phase 1 subjects may be an approved canonical Instrument, an approved Market subject, an approved exchange or session subject already established under Market architecture, or a defined Observation factual availability or completeness scope. |
| Derived Factual Observation | A factual result that passes every governed-input, determinism, reproducibility, lineage, temporal-coherence, visible-derivation, semantic-preservation, non-judgment, no-policy, and factual-purpose test defined by this architecture. |
| Observation Class | An architectural category that distinguishes factual semantics, temporal meaning, ownership, lifecycle, or governance. It is not a runtime type. |
| Observation Provenance | Observation's preserved explanation of factual source, origin, relevant acquisition context, temporal context, and known limits without acquiring Provider ownership. |
| Factual Lineage | The explainable relationship from a governed Observation to its source factual information, attributed subject, prior Observations, corrections, or supersession context. |
| Temporal Context | The architectural meaning of when a fact occurred, applied, was reported, was received, was accepted, or was revised. |
| Market-Effective Time | When the represented fact occurred or became effective in the market. |
| Represented Interval | The period summarized or described by an Interval Observation. |
| Source-Report Time | When the external source represented that it reported or published the fact. |
| KRONOS Receipt Time | When KRONOS received candidate factual information. It is not automatically market-effective or acceptance time. |
| KRONOS Factual-Acceptance Time | When Observation made the architectural acceptance decision from which ownership of the accepted factual record resulted. |
| Observation Lifecycle | The conceptual factual-governance conditions through which candidate information may become, remain, or relate to an accepted Observation. It is not a runtime state machine. |
| Current-State Observation | The accepted Observation that is presently applicable for a defined subject, factual category, and temporal context under approved Observation semantics. Current describes applicability, not freshness, receipt recency, publication status, or fitness for use. |
| Historical | An accepted factual record retained within Observation authority. Historical does not imply invalid, superseded, or obsolete. |
| Correction | An explicit relationship in which a later accepted Observation states that an earlier factual assertion contained a factual defect and addresses that defect while preserving the original Observation, relationship, provenance, temporal context, and lineage. |
| Supersession | An explicit relationship in which a later accepted Observation replaces the earlier Observation's present applicability for a defined context without necessarily asserting that the earlier Observation was defective, while preserving the earlier Observation, relationship, provenance, temporal context, and lineage. |
| Absence | A factual assertion that something defined was not present within an established scope. Absence shall not be inferred solely from acquisition failure. |
| Availability | An accepted factual assertion about whether defined information was available within an explicit Observation factual scope. Provider availability and Market availability remain separate meanings and ownership. |
| Missingness | The factual condition that expected information is not present within a defined scope, without treating it as zero or proving absence. |
| Partiality | The factual condition that only part of a defined scope is present or represented. |
| Provider Technical Acquisition Completeness | Provider-owned meaning concerning whether a requested Provider operation completed and technically delivered what that operation represented, including expected response structure or segments, reported partial or complete delivery, failure or success, and capability support. |
| Observation Factual-Scope Completeness | Observation-owned factual meaning, only after acceptance, concerning whether an accepted factual record or Observation set represents an explicit scope defined by attributable subject, factual category, temporal context, expected factual coverage, and known limits. |
| Uncertainty | A known limit on a factual assertion or its context that remains explicit rather than being converted into certainty. |
| Ambiguity | More than one possible factual meaning or attribution, or the absence of one determinate meaning, preserved without silent resolution. |

Terminology in this document is architectural, semantic, implementation-neutral, and free of runtime representation.

## 8. Definition of a Governed Observation

**Chief Architect-approved definition:**

> A governed Observation is a factual assertion owned by the Observation domain and authoritative within KRONOS's governed factual architecture, attributable to an approved subject, associated with explicit temporal meaning and preserved provenance, and represented with any known limits, uncertainty, ambiguity, completeness state, correction, or supersession context—without assigning business, evidentiary, or trading meaning.

“Authoritative” means authoritative only within KRONOS's governed factual architecture. It shall never imply:

- infallible real-world truth;
- exchange authority;
- Provider infallibility;
- objective correctness beyond represented provenance and known factual limits;
- independent verification of an external source;
- evidentiary reliability;
- suitability for trading;
- Validation acceptance;
- statistical correctness; or
- business significance.

A governed Observation requires:

1. a factual assertion;
2. attribution to an approved subject;
3. explicit temporal meaning;
4. preserved provenance and factual lineage;
5. an architectural acceptance decision, after which the accepted factual record is owned by Observation;
6. preserved factual limits; and
7. absence of interpretation.

The definition shall never be reduced to “market data with a timestamp.”

## 9. Observation Domain Purpose

Observation exists to own and preserve attributable, temporally meaningful factual market state that is authoritative within KRONOS's governed factual architecture without introducing business interpretation, Validation judgment, or trading meaning.

Observation answers:

> What factually happened, was reported, was available, was absent, or was revised?

Observation shall never answer:

- What Instrument is this?
- Why did this happen?
- Is it bullish or bearish?
- Is the fact useful evidence?
- Is the fact reliable enough to trade?
- Is there an opportunity?
- What should the trader do?
- Should execution occur?

## 10. Domain Ownership

The approved ownership boundary remains:

| Domain | Exclusive ownership relevant to ADP-001E |
| --- | --- |
| Provider | External information, Provider meaning, Provider identifiers, Provider records, Provider capability, Provider availability, Provider-specific technical meaning, acquisition outcomes, and source-origin semantics. |
| Instrument | Canonical Instrument identity, classification, lifecycle, relationships, Provider mapping semantics, identity resolution, identity invariants, and Instrument meaning. |
| Market | Market Schedule, trading-day and holiday meaning, session definitions, authoritative market-open and market-closed semantics, exchange-availability meaning, and temporal market context. |
| Observation | Market Facts and factual market-state records that are authoritative within KRONOS's governed factual architecture; Observation semantics; factual attribution; temporal factual meaning; factual lineage continuity; Observation provenance continuity; and accepted factual-state relationships. |
| Validation | Business Judgment. Future evidentiary quality, relevance, sufficiency, weighting, reliability for a defined use, and fitness-for-trading meaning require separately approved Validation architecture. |

Observation owns the architectural meaning of the acceptance decision and the resulting Observation ownership state, correction and supersession relationships, current and historical factual-state distinctions, factual-scope availability and completeness, and governed derived factual Observations where permitted.

No new domain, shared ownership, or responsibility transfer is created.

## 11. Explicit Non-Ownership

Observation shall never own or redefine:

- external Provider information, Provider meaning, Provider capability, or Provider availability;
- canonical Instrument identity, classification, lifecycle, relationships, or Provider mapping semantics;
- Market Schedule, sessions, holidays, trading-day meaning, exchange availability, or Market status semantics;
- Validation judgment, evidence quality, hypothesis relevance, evidence sufficiency, confidence, or fitness for trading;
- direction, readiness, risk permission, execution timing, orders, positions, or model-trade state;
- transport, persistence, runtime configuration, Platform Events, or Audit Trail meaning; or
- source-engine responsibilities preserved by ENGINE_OWNERSHIP.

Observation ownership of a factual assertion shall never transfer ownership of the assertion's subject, source, schedule context, or downstream interpretation.

## 12. Authoritative Factual State

Authoritative factual state is the factual record owned by Observation and authoritative only within KRONOS's governed factual architecture.

Within an explicit accepted Observation factual scope, it may state what:

- was reported or measured;
- was present or absent within a defined scope;
- was available, unavailable, missing, partial, unsupported, or incomplete;
- occurred at a point in time or across an interval;
- was current within a defined context;
- was retained historically;
- was corrected or superseded; or
- was deterministically derived within the governed factual boundary.

An Observation assertion about unsupported information shall describe only its accepted factual scope and shall never redefine Provider capability or Provider support.

Observation authority makes the assertion authoritative only within KRONOS's governed factual architecture. It shall preserve represented provenance, context, and known limits and shall never imply exchange authority, Provider infallibility, or objective correctness beyond what those represented meanings support.

Raw or normalized Provider information remains Provider-owned, may contain Provider vocabulary, gaps, errors, partiality, or technical limitations, and does not automatically become factual state that is authoritative within KRONOS's governed factual architecture.

## 13. Observation Authority

Observation Authority is an architectural responsibility, not a runtime service, component, engine, module, process, or algorithm.

Observation Authority shall:

- govern factual meaning that is authoritative within KRONOS's governed factual architecture;
- preserve the boundary between factual state and interpretation;
- preserve attribution to the approved subject;
- preserve temporal and provenance meaning;
- preserve known factual limits;
- govern factual lineage, correction, and supersession meaning; and
- preserve existing source-engine responsibilities without duplicating them.

Observation Authority shall never:

- validate an external source independently merely by accepting a fact;
- convert provenance into proof of correctness;
- assign evidence quality or business meaning;
- override another domain's semantic authority; or
- imply exchange authority, Provider infallibility, absolute external truth, or objective correctness beyond represented provenance and known factual limits.

## 14. Observation Acceptance

Availability, acquisition success, normalization, architectural admissibility, and approved subject attribution shall never create an Observation.

Observation exclusively owns the semantic authority to accept candidate factual information as a governed Observation. Observation ownership of the accepted factual record is the resulting architectural state.

The conceptual distinction is:

```text
Candidate Factual Information
        ↓
Architectural Acceptance Decision
        ↓
Observation-Owned Factual Record
```

This distinction is conceptual and semantic. It is not a runtime flow, state machine, algorithm, or implementation sequence.

Acceptance means only that:

- Observation decides that candidate factual information becomes a governed Observation;
- the resulting accepted factual record becomes owned by Observation;
- that record becomes authoritative within KRONOS's governed factual architecture;
- the candidate has an approved attributable subject;
- its semantic purpose is factual rather than interpretive;
- its temporal meaning is explicit;
- its provenance is preserved;
- its factual lineage is explainable;
- its uncertainty, ambiguity, and known limits are preserved;
- it contains no embedded Validation, business, or trading judgment; and
- no interpretation, Validation judgment, publication, or downstream use is implied.

Acceptance as an architectural decision shall remain distinct from Observation ownership as its resulting architectural state. Both shall remain distinct from correctness, completeness, publication, consumption, validation, and fitness for trading.

The acceptance mechanism, runtime criteria, runtime checks, representation, and processing remain deferred. This architecture defines only the minimum semantic conditions above and no mechanism, algorithm, schema, service, check, or state machine.

## 15. Approved Subject Attribution

Phase 1 Observation ownership is not limited to Instrument-scoped facts. Observation may own facts concerning:

- an approved canonical Instrument;
- an approved Market subject;
- an approved exchange or session subject where that subject already exists under Market architecture; or
- a defined Observation factual availability or completeness scope.

Instrument-specific factual information shall require attribution to an approved canonical Instrument identity under ADP-001D before Observation may make the acceptance decision that results in ownership of the accepted factual record.

Observation may own a factual availability or completeness assertion only when:

- it concerns an approved Observation factual scope;
- its subject and scope are explicit;
- it has passed Observation acceptance; and
- it does not redefine Provider or Market availability.

Provider capability and acquisition semantics remain Provider-owned, including Provider support, endpoint availability, request success or failure, technical payload completeness, Provider error meaning, and Provider acquisition outcomes.

Observation shall:

- preserve the subject attribution that applied to the factual assertion;
- preserve relevant effective identity or lifecycle context where approved architecture requires it;
- keep attribution distinct from subject ownership; and
- reject silent identity inference or ambiguity resolution.

Observation shall never create or own the subject identity.

No new subject identity, identity domain, dependency, or cross-domain contract is created by this document.

## 16. Fact Versus Interpretation

The conceptual semantic progression is:

```text
Candidate Factual Information
        ↓
Approved Subject Attribution
and Observation Eligibility
        ↓
Candidate Observation
        ↓
Architectural Acceptance Decision
        ↓
Observation-Owned Governed Observation
        ↓
Derived Factual Observation, where permitted
        ↓
Interpretation
        ↓
Validated Evidence
        ↓
Decision Support
```

The progression is conceptual, semantic, and technology-independent. It is not a runtime flow, state-machine implementation, transport sequence, persistence model, processing order, or implementation authorization.

Raw or normalized Provider information:

- retains Provider meaning;
- may preserve gaps, Provider vocabulary, partiality, errors, and technical limits;
- does not automatically become factual state that is authoritative within KRONOS's governed factual architecture; and
- is not an Observation merely because acquisition succeeded.

Attributed factual information:

- has an approved attributable subject;
- is eligible for Observation participation;
- has not necessarily been accepted and therefore is not necessarily owned by Observation; and
- is not necessarily correct, complete, accepted, or published.

A governed Observation:

- is owned by Observation;
- expresses factual state;
- preserves temporal and provenance meaning;
- preserves known limits; and
- assigns no business or evidentiary judgment.

Interpretation, validated evidence, and decision support remain outside Observation.

Candidate factual information concerning an approved Market subject, exchange subject, session subject, or Observation factual availability or completeness scope follows the same acceptance boundary without transferring Provider, Instrument, or Market ownership.

## 17. Derived Factual Observations

Derived factual Observations are permitted only when they pass every architectural test below:

1. **Governed-input test:** Every semantic input is a governed factual Observation or another explicitly approved factual input.
2. **Determinism test:** The same governed factual inputs produce the same result.
3. **Reproducibility test:** The result can be reconstructed from preserved inputs and derivation identity.
4. **Lineage test:** Source Observations and provenance remain traceable.
5. **Temporal-coherence test:** The temporal meaning of the result is explicit and consistent with its inputs.
6. **Visible-derivation test:** The result remains distinguishable from directly reported factual state.
7. **Semantic-preservation test:** The derivation introduces no new semantic claim beyond what is factually contained in its inputs.
8. **Non-judgment test:** The result assigns no quality, significance, strength, confidence, opportunity, evidence, or action meaning.
9. **No-policy test:** The result does not depend on a strategic threshold, preference, hypothesis, or trading rule.
10. **Factual-purpose test:** The result exists to describe factual state rather than support a conclusion or decision.

Failure of any test places the result outside Observation.

Conceptual examples may include:

- a factual arithmetic difference;
- a factual interval range;
- an approved factual aggregation; or
- a factual availability ratio.

These examples define no formula, algorithm, indicator, threshold, calculation engine, schema, or implementation.

Determinism alone shall never make a result a factual Observation. Semantic preservation is required in addition to deterministic derivation: a derived factual Observation shall never introduce new semantic meaning beyond its governed factual inputs. Semantic purpose also governs ownership.

The following remain outside Observation:

- bullish or bearish meaning;
- trend strength;
- momentum judgment;
- breakout quality;
- compression signals;
- opportunity scores;
- confidence;
- actionable status; and
- significance for trading.

## 18. Observation Taxonomy

The minimum architectural Observation classes are:

| Observation class | Architectural distinction |
| --- | --- |
| Point-in-Time Observation | A factual assertion associated with a particular market-effective moment. |
| Interval Observation | A factual assertion representing a defined interval. |
| Current-State Observation | The accepted Observation presently applicable for a defined subject, factual category, and temporal context under approved Observation semantics. |
| Historical Observation | A retained accepted factual record. |
| Derived Factual Observation | A factual result that passes every architectural test in Section 17. |
| Availability and Completeness Observation | An accepted factual assertion concerning an explicit Observation factual availability or completeness scope. |
| Correcting Observation | A later accepted factual Observation that states that an earlier factual assertion contained a factual defect and addresses that defect while preserving the original record and relationship. |
| Superseding Observation | A later accepted factual Observation that replaces an earlier Observation's present applicability for a defined context without necessarily asserting a factual defect. |

Provider-reported and exchange-reported are provenance distinctions, not primary Observation classes unless later approved architecture requires otherwise.

This taxonomy does not define candles, quotes, depth, Open Interest structures, payload shapes, runtime types, inheritance, or storage.

## 19. Point-in-Time Observations

A Point-in-Time Observation is a factual assertion whose meaning concerns a particular market-effective moment.

It shall preserve:

- the approved subject;
- the relevant market-effective meaning;
- source and receipt context where applicable;
- provenance and known limits; and
- correction or supersession lineage where applicable.

Point-in-time does not imply current, fresh, correct, complete, validated, or suitable for trading.

## 20. Interval Observations

An Interval Observation is a factual assertion whose meaning concerns a defined represented interval.

The represented interval is part of the Observation's meaning. An Interval Observation shall never imply:

- how the interval was constructed;
- that a Provider snapshot is a completed interval;
- that missing sub-intervals indicate Market closure;
- that the interval is complete merely because acquisition succeeded; or
- that the interval is useful evidence.

Dataset-specific interval and candle architecture remains deferred.

## 21. Current and Historical Observations

A Current-State Observation is the accepted Observation that is presently applicable for a defined subject, factual category, and temporal context under approved Observation semantics.

Current shall never imply:

- latest Provider receipt;
- low latency;
- freshness;
- correctness;
- completeness;
- Validation acceptance;
- tradability; or
- actionability.

Current describes applicability. It does not describe freshness, receipt recency, publication status, or fitness for use.

Current-state meaning shall preserve explainable:

- subject;
- factual category;
- temporal context;
- applicability relationship; and
- correction or supersession context.

A Historical Observation is a retained accepted factual record. Historical shall never imply invalid, superseded, obsolete, or unsuitable for factual lineage.

The selection, publication, and runtime mechanism remain deferred.

## 22. Availability and Completeness Observations

An Availability and Completeness Observation is an accepted factual assertion about a defined Observation factual scope and context.

It may state that information was:

- available;
- unavailable;
- missing;
- partial;
- unsupported; or
- incomplete.

It shall never:

- infer Market OPEN or CLOSED;
- equate unavailable with missing;
- equate missing with zero;
- equate unsupported with failed;
- equate acquisition success with completeness; or
- assign quality, reliability, or fitness-for-use judgment.

Provider technical acquisition completeness and Observation factual-scope completeness shall remain conceptually distinct.

Provider technical acquisition completeness is Provider-owned. It concerns whether:

- the requested Provider operation completed;
- the expected Provider response structure was returned;
- Provider response segments were received;
- the Provider reported partial or complete delivery;
- the acquisition operation failed or succeeded; or
- Provider capability supported the request.

Observation factual-scope completeness is Observation-owned only after acceptance. It concerns whether an accepted factual record or Observation set represents a defined factual scope.

That Observation factual scope shall explicitly identify:

- the attributable subject;
- the factual category;
- the temporal context;
- the expected factual coverage; and
- the known limits.

The governing distinction is:

> **Provider completeness:** Did the Provider technically deliver what its operation represented?
>
> **Observation completeness:** Does the accepted factual record represent the defined KRONOS factual scope?

Provider success shall never establish Observation completeness automatically.

## 23. Corrected and Superseding Observations

Correction and supersession are separate architectural relationships.

**Correction:** A later accepted Observation states that an earlier factual assertion contained a factual defect and addresses that defect while preserving the original Observation, relationship, provenance, temporal context, and lineage.

**Supersession:** A later accepted Observation replaces the earlier Observation's present applicability for a defined context without necessarily asserting that the earlier Observation was defective.

The governing distinction is:

> **Correction:** The earlier assertion was factually defective.
>
> **Supersession:** The earlier assertion is no longer presently applicable.

A correcting Observation may also supersede an earlier Observation, but the two relationships remain semantically distinct.

Correction and supersession shall:

- preserve the earlier Observation;
- preserve the explicit relationship;
- preserve provenance and factual lineage;
- preserve the temporal context of both assertions; and
- prohibit silent overwrite.

A source correction supplied by Provider may become candidate information for a correcting or superseding Observation. Provider shall never silently mutate an accepted Observation.

## 24. Temporal Semantics

Time is part of an Observation's meaning, not merely metadata.

A factual assertion without explainable temporal meaning shall not be considered a complete governed Observation.

The relevant architectural temporal concepts are:

| Temporal concept | Architectural meaning |
| --- | --- |
| Market-effective time | When the represented fact occurred or was effective in the market. |
| Represented interval | The period summarized or described by an Interval Observation. |
| Source-report time | When the external source represented that it reported or published the fact. |
| KRONOS receipt time | When KRONOS received the candidate factual information. |
| KRONOS factual-acceptance time | When Observation made the architectural acceptance decision from which ownership of the accepted factual record resulted. |
| Correction or supersession time | When a later Observation corrected an earlier factual defect or superseded an earlier Observation's present applicability. |

These temporal concepts may coincide, but they shall never be assumed identical. Ordering, late arrival, and revision context shall remain explainable.

This document defines no clocks, formats, thresholds, ordering algorithms, streaming semantics, or event-time processing.

Observation may reference Market-owned session and schedule context. Observation shall never define Market Schedule, define session meaning, infer Market closure from missing information, own exchange availability, or redefine Market temporal authority.

## 25. Provenance and Factual Lineage

Observation shall preserve factual lineage back to:

- source or Provider origin;
- relevant acquisition context;
- approved subject attribution;
- temporal context;
- source limitations;
- known uncertainty;
- known ambiguity; and
- correction and supersession relationships.

Provider retains ownership of Provider provenance meaning. Instrument retains canonical identity and mapping meaning. Market retains schedule and session meaning. Observation owns the accepted factual Observation, preserved factual attribution, temporal provenance, factual-lineage continuity, and approved correction or supersession relationships.

Observation shall never silently alter original provenance. Provenance may be supplemented, clarified, related to additional provenance, or corrected through an explicit subsequent factual record, while original lineage remains explainable.

Observation provenance shall remain distinguishable from Provider ownership. Observation attribution shall remain distinguishable from Instrument ownership.

## 26. Observation Lifecycle

The following lifecycle concepts are conceptual and do not define runtime states, transitions, events, commands, services, or implementation checks.

| Lifecycle concept | Architectural meaning |
| --- | --- |
| Candidate | Candidate factual information is available for possible Observation participation but has not been accepted and is not owned by Observation. |
| Admissible | The candidate satisfies approved architectural eligibility conditions. Admissible does not mean accepted, correct, complete, published, or validated. |
| Accepted | Observation has made the architectural acceptance decision. The accepted factual record is consequently owned by Observation and authoritative within KRONOS's governed factual architecture. |
| Current | The accepted Observation is presently applicable for a defined subject, factual category, and temporal context under approved Observation semantics. It does not imply latest Provider receipt, low latency, freshness, correctness, completeness, Validation acceptance, tradability, or actionability. |
| Historical | The Observation remains in the accepted factual record but is not current for the relevant context. |
| Superseded | A later accepted Observation replaces the earlier Observation's present applicability for a defined context without necessarily asserting that the earlier Observation was defective, while preserving the earlier record and relationship. |
| Corrected | A later accepted Observation states that an earlier factual assertion contained a factual defect and addresses that defect while preserving the original record, relationship, provenance, temporal context, and lineage. |
| Incomplete | The Observation explicitly represents a factual scope known to be incomplete. Incomplete does not automatically mean false or invalid. |
| Unavailable | Approved architecture factually establishes that defined information was unavailable from a relevant source or context. Unavailable is not zero and does not imply Market closure. |
| Rejected as Observation | Observation did not make the acceptance decision, so the candidate factual information did not become Observation-owned. This does not necessarily assert that Provider information was false. |

“Invalidated as a fact” is excluded as a canonical lifecycle concept unless separately approved architecture requires it, because it risks importing Validation judgment.

Observation acceptance authority is exclusively Observation-owned. Acceptance is the semantic architectural decision; ownership of the accepted factual record is the resulting architectural state. The acceptance mechanism remains deferred.

## 27. Availability, Missingness, Partiality, and Completeness

The following meanings shall remain distinct:

- zero;
- missing;
- absent;
- unavailable;
- unsupported;
- partial;
- incomplete;
- acquisition failure;
- Provider success; and
- Observation acceptance.

The following rules apply:

- missing is not zero;
- unavailable does not imply Market closure;
- Provider success does not establish Observation completeness;
- attribution admissibility does not establish factual acceptance;
- incomplete does not automatically mean invalid;
- absence shall not be inferred solely from acquisition failure; and
- current shall not establish freshness.

Provider owns technical acquisition completeness within Provider meaning. It answers whether the Provider technically delivered what its operation represented, including operation completion, expected response structure or segments, Provider-reported partial or complete delivery, failure or success, and capability support.

Observation owns factual-scope completeness only after Observation acceptance. It answers whether an accepted factual record or Observation set represents a defined KRONOS factual scope whose attributable subject, factual category, temporal context, expected factual coverage, and known limits are explicit.

Provider success shall never establish Observation completeness automatically.

## 28. Relationship with Provider

Provider may, within approved Provider authority:

- acquire external information;
- preserve Provider provenance;
- normalize Provider representation within approved boundaries;
- report Provider capability, availability, and acquisition outcomes;
- report Provider technical acquisition completeness; and
- supply source corrections.

Provider shall never:

- declare a KRONOS Observation authoritative;
- own Observation semantics;
- bypass required canonical attribution;
- convert acquisition success into factual acceptance; or
- silently mutate an accepted Observation.

Provider information may become candidate factual information only through separately approved architecture. This document does not create a Provider → Observation contract, runtime path, retrieval capability, or new domain dependency.

## 29. Relationship with Instrument

ADP-001E preserves ADP-001D:

- Instrument owns canonical identity.
- Observation owns factual state.
- Facts do not possess identity; they are attributed to identity.
- Attribution shall never transfer identity ownership.
- Observation may preserve the attribution and applicable lifecycle context.
- Observation shall never create, alter, resolve, or infer canonical Instrument identity.

Instrument-specific candidate factual information shall not be accepted, and therefore shall not become Observation-owned, without approved canonical attribution.

ADP-001E does not define the Instrument Identity Contract or alter the approved Instrument → Observation dependency.

## 30. Relationship with Market

Market owns:

- Market Schedule;
- trading-day and holiday meaning;
- session definitions;
- Market status semantics;
- exchange-availability meaning; and
- approved temporal market context.

Observation may reference approved Market-owned context, record factual events within that context, or record that a Market-owned state was reported. Observation shall never own, infer, or redefine the underlying Market meaning.

Observation may own an accepted fact concerning an approved Market subject or an approved exchange or session subject where that subject already exists under Market architecture. Ownership of that factual assertion shall never transfer Market ownership or redefine Provider availability, Market Schedule, session meaning, or Market availability.

Available, missing, stale, partial, or absent information shall never establish Market OPEN or CLOSED. EAIC-001 remains the approved presentation-facing Exchange Availability authority.

This document creates no Market → Observation contract and identifies no authoritative calendar source.

## 31. Future Relationship with Validation

Validation owns Business Judgment under approved Platform architecture.

A future Observation → Validation boundary may make available:

- governed factual records;
- attributable subject context;
- temporal meaning;
- provenance;
- known limits; and
- correction and supersession lineage.

Observation shall never provide:

- evidentiary strength;
- hypothesis relevance;
- confidence;
- fitness for trading;
- significance;
- reliability for a defined use;
- actionability; or
- forecast value.

This document does not design Validation, create an Observation → Validation contract, or authorize downstream influence. Existing ENGINE_OWNERSHIP boundaries remain unchanged.

## 32. Architectural Invariants

The following Chief Architect-approved invariants are normative within this approved canonical architecture:

1. Observation shall exclusively own factual market state that is authoritative within KRONOS's governed factual architecture.
2. Observation shall exclusively own the semantic authority to accept candidate factual information as a governed Observation.
3. Observation acceptance shall be the semantic architectural decision, and Observation ownership of the accepted factual record shall be the resulting architectural state.
4. Provider availability, acquisition success, normalization, architectural admissibility, and canonical attribution shall never establish Observation acceptance or ownership.
5. Every accepted Observation shall have an approved attributable subject, factual rather than interpretive semantic purpose, explicit temporal meaning, preserved provenance, explainable factual lineage, preserved uncertainty, ambiguity, and known limits, and no embedded Validation, business, or trading judgment.
6. Instrument-specific facts shall require approved canonical Instrument attribution.
7. Observation may own facts concerning an approved Market subject, an approved exchange or session subject already established under Market architecture, or a defined Observation factual availability or completeness scope without acquiring Market or Provider ownership.
8. Observation shall never create, alter, resolve, or infer canonical Instrument identity.
9. Missing and zero shall remain distinct factual states.
10. Unsupported, unavailable, missing, partial, and incomplete shall remain distinguishable.
11. Current shall describe present applicability for a defined subject, factual category, and temporal context.
12. Current shall never imply latest Provider receipt, low latency, freshness, correctness, completeness, Validation acceptance, tradability, or actionability.
13. Historical shall never imply invalid.
14. Correction shall mean that an earlier factual assertion was factually defective.
15. Supersession shall mean that an earlier Observation is no longer presently applicable for a defined context without necessarily asserting a factual defect.
16. Correction and supersession shall remain semantically distinct even when a correcting Observation also supersedes an earlier Observation.
17. Correction and supersession shall preserve the earlier Observation, explicit relationship, provenance, temporal context, and factual lineage.
18. Provider correction shall never silently mutate an accepted Observation.
19. A derived factual Observation shall pass every governed-input, determinism, reproducibility, lineage, temporal-coherence, visible-derivation, semantic-preservation, non-judgment, no-policy, and factual-purpose test.
20. Failure of any derived factual test shall place the result outside Observation.
21. Determinism alone shall never make a result a factual Observation.
22. Observation shall preserve known uncertainty.
23. Observation shall preserve unresolved ambiguity.
24. Observation shall never infer Market status from data presence, absence, or staleness.
25. Provider shall own technical acquisition completeness.
26. Observation shall own factual-scope completeness only after acceptance for an explicit subject, factual category, temporal context, expected factual coverage, and known limits.
27. Provider success shall never establish Observation completeness automatically.
28. Observation provenance shall remain distinguishable from Provider ownership.
29. Observation attribution shall remain distinguishable from Instrument ownership.
30. Factual acceptance shall remain distinguishable from Validation judgment.
31. Observation shall answer what happened, not what it means.
32. No Observation shall independently confer trading permission, direction, confidence, opportunity status, or execution authority.
33. Temporal concepts that coincide shall never be assumed semantically identical.
34. Observation acceptance shall remain distinct from publication or downstream consumption.
35. Observation authority shall never imply exchange authority, Provider infallibility, absolute external truth, or objective correctness beyond represented provenance and known factual limits.

These invariants define architectural meaning only and no implementation enforcement mechanism.

## 33. Explicit Prohibitions

Observation shall never:

- create canonical Instrument identity;
- resolve identity ambiguity;
- define Provider mappings;
- redefine Instrument lifecycle;
- own Market schedules;
- define Market sessions;
- infer exchange closure from missing or stale information;
- treat missing information as zero;
- treat partial information as complete;
- treat architectural admissibility as factual correctness;
- treat Provider success as Observation acceptance;
- treat Provider success as Observation completeness;
- represent Provider capability, endpoint availability, request outcome, technical payload completeness, Provider error meaning, or Provider acquisition outcome as Observation-owned Provider meaning;
- silently replace provenance;
- silently overwrite corrected facts;
- conceal correction or supersession;
- collapse correction and supersession into one meaning;
- erase factual lineage;
- assign bullish or bearish meaning;
- assign trend, momentum, market-acceptance judgment, strength, or weakness;
- assign evidence quality;
- assign opportunity or significance;
- validate a trading hypothesis;
- judge evidence sufficiency;
- score or rank opportunities;
- create indicators;
- create strategy signals;
- produce BUY READY, SELL READY, BUY NOW, or SELL NOW;
- authorize execution;
- own positions, orders, or trade management;
- represent interpretation as a factual Observation;
- treat a derived result that fails any Section 17 test as a factual Observation;
- treat current as proof of latest Provider receipt, low latency, freshness, correctness, completeness, Validation acceptance, tradability, or actionability; or
- treat factual state that is authoritative within KRONOS's governed factual architecture as proof of exchange authority, Provider infallibility, absolute external truth, or objective correctness beyond represented provenance and known factual limits.

Observation architecture shall never become a runtime contract, schema, persistence design, generic cross-domain framework, or indirect path around an approved dependency.

## 34. Conceptual Models

### Figure 1 — Domain ownership context

```text
Provider                              Market
External Information                 Schedules and Session Meaning
and Provider Meaning                         │
        │                                    │ approved subject or
        │                                    │ referenced context
        ▼                                    ▼
Instrument Attribution Boundary ───────► Observation
Canonical Instrument attribution       KRONOS-Governed Factual
                                       Market State
                                              │
                                              ▼
                                      Future Validation
                                      Evidentiary Judgment
                                      and Use
```

Figure 1 is conceptual, semantic, and technology-independent. It is not a runtime flow, transport design, schema, processing order, or implementation sequence.

### Figure 2 — Factual progression

```text
Candidate Factual Information
        ↓
Approved Subject Attribution
        ↓
Candidate Observation
        ↓
Architectural Acceptance Decision
        ↓
Observation-Owned Governed Observation
        ↓
Current / Historical / Correcting / Superseding
```

Figure 2 is conceptual, semantic, and technology-independent. It is not a runtime flow, transport design, schema, state-machine implementation, or implementation sequence.

### Figure 3 — Meaning separation

```text
Identity          → Instrument
Schedule Meaning  → Market
Provider Meaning  → Provider
Factual State     → Observation
Evidence Judgment → Validation
Trading Decision  → Downstream Decision Authority
```

Figure 3 is conceptual, semantic, and technology-independent. It is not a runtime flow, transport design, schema, processing order, or implementation sequence.

## 35. Architectural Traceability

The approved architecture and this document progress as follows:

- **ADP-001A defines what information may enter KRONOS and establishes key factual distinctions.**
- **ADP-001B defines canonical Instrument identity.**
- **ADP-001C governs when Provider information becomes eligible for Instrument interpretation.**
- **ADP-001D governs when factual information may be attributed to canonical Instrument identity and become eligible for Observation participation.**
- **ADP-001E defines Observation ownership and the architecture of governed factual state.**

ADP-001E shall never restate ADP-001A through ADP-001D as new decisions, weaken their exclusions, expand their approved scope, or transfer their ownership assignments.

## 36. Conformance with ADP-001A

This document conforms to ADP-001A by:

- limiting factual scope to the approved Phase 1 inventory;
- preserving Observation ownership of accepted OHLCV, Open Interest, Current Quote facts, provenance, and factual-scope completeness;
- preserving missing, zero, partial, unsupported, unavailable, and incomplete distinctions;
- keeping Provider availability separate from Market availability;
- keeping Current Quote distinct from completed historical intervals;
- keeping historical and current Open Interest distinct;
- authorizing no dataset retrieval, optional or conditional activation, persistence, retry, scheduling, or streaming;
- retaining Options, TradingView, interpretation, ranking, execution, order, and position exclusions; and
- leaving dataset-specific Observation models unresolved and deferred.

ADP-001E does not amend ADP-001A classifications, inventory, completion criteria, or outstanding questions.

## 37. Conformance with ADP-001B

This document conforms to ADP-001B by:

- preserving Economic Instrument, Listed Instrument, and Derivative Contract as Instrument-owned canonical identities;
- requiring approved canonical Instrument attribution for instrument-specific Observations;
- preserving effective identity and lifecycle context where applicable;
- keeping Provider Instrument References external and non-canonical;
- preserving historical attribution across Provider-reference and lifecycle change;
- allowing no factual state to create, alter, resolve, or infer identity;
- keeping Observation lifecycle distinct from Instrument Lifecycle and Provider Mapping State; and
- creating no mapping, successor, continuous-futures, or Options capability.

ADP-001E does not amend ADP-001B.

## 38. Conformance with ADP-001C

This document conforms to ADP-001C by:

- preserving Provider ownership of external information, Provider meaning, provenance, capability, availability, and acquisition outcomes;
- preserving the separation between physical movement, admissibility, and semantic authority;
- preventing Provider success from becoming Observation acceptance;
- preserving partiality, failure, unavailability, uncertainty, and ambiguity;
- keeping Provider provenance distinguishable from Observation provenance continuity;
- creating no Provider → Observation contract, retrieval authority, or runtime path; and
- preserving exclusive domain ownership.

ADP-001E does not amend ADP-001C.

## 39. Conformance with ADP-001D

This document conforms to ADP-001D by:

- preserving the principle that facts do not possess identity and are attributed to identity;
- preserving Instrument identity and Observation factual-state ownership;
- requiring approved attribution before Observation participation for instrument-specific facts;
- preserving attribution, provenance, temporal context, uncertainty, and ambiguity;
- keeping admissibility distinct from acceptance, ownership, publication, and validation;
- preventing the attribution boundary from creating an Observation;
- preserving attribution failure as distinct from factual acceptance; and
- creating no Instrument → Observation runtime communication or contract implementation.

ADP-001E elaborates the Observation side of the approved boundary without amending ADP-001D.

## 40. Dependencies

ADP-001E depends on:

- ADP-001A for approved factual categories, provenance requirements, inventory boundaries, and read-only restrictions;
- ADP-001B for canonical Instrument identity, lifecycle, mapping semantics, and historical attribution;
- ADP-001C for governed admissibility and preservation of Provider meaning;
- ADP-001D for canonical attribution eligibility and Instrument–Observation ownership separation;
- PLATFORM-000 for contract-based dependencies and single semantic ownership;
- DOMAIN-002 for Observation ownership;
- DOMAIN-001, DOMAIN-006, DOMAIN-008, and DOMAIN-003 for the preserved Instrument, Provider, Market, and Validation boundaries;
- the Domain Ownership Matrix and Domain Dependency Matrix;
- ENGINE_OWNERSHIP for preserved source-engine responsibilities;
- DATA_FLOW for existing current information paths; and
- EAIC-001 for explicit Exchange Availability meaning.

ADP-001E creates no new domain dependency. Observation continues to depend on Instrument through approved semantic meaning. Platform support from Provider or Market shall never create an unapproved business-domain dependency or transfer semantic ownership.

No runtime, transport, storage, Provider-specific implementation, Validation, or Engineering Package dependency is established.

## 41. Architectural Resolution Status

The Chief Architect has resolved all six architectural questions concerning Observation acceptance authority, Phase 1 subject scope, the derived factual boundary, correction and supersession, completeness ownership, and current-state authority. No unresolved architectural question blocks canonical approval.

These resolutions authorize no field, schema, API, payload, runtime state, algorithm, contract, implementation, or follow-on capability.

## 42. Deferred Capabilities

The following remain deferred:

- dataset-specific Observation models;
- historical candle architecture;
- Current Quote architecture;
- Open Interest architecture;
- continuous-futures factual architecture;
- market-depth architecture;
- retention;
- correction-processing mechanics;
- temporal-ordering mechanics;
- publication;
- APIs, schemas, fields, payloads, and persistence;
- synchronization and transport;
- derivation algorithms;
- Provider → Observation runtime communication;
- Observation → Validation contract;
- Validation architecture;
- Options capability;
- TradingView integration;
- execution, orders, positions, and automated trading; and
- any engineering implementation.

Deferral creates no roadmap sequence, implementation authority, or follow-on package.

## 43. ADR Determination

No ADR is required for ADP-001E.

An ADR shall be recommended if later review concludes that KRONOS must:

- create a separate Provenance domain;
- create a separate Temporal domain;
- move Market Schedule ownership into Observation;
- move factual acceptance into Validation;
- alter ADP-001D attribution authority;
- establish a mandatory platform-wide Observation model for every product;
- redefine canonical engine ownership; or
- introduce shared ownership across Provider, Instrument, Market, or Observation.

No ADR is created or authorized by this document.

## 44. Follow-on Architecture

This document does not select, number, create, recommend, or authorize a follow-on architecture package.

The Chief Architect may determine follow-on architecture only through separate authorization.

This section creates no sequence, roadmap commitment, contract, ADR, EDD, Engineering Package, acquisition authority, publication authority, or runtime authorization.

## 45. Approval Record

**Chief Architect Decision:** Approved

**Engineering Architect Verification:** Passed

**ADR Required:** No

**Canonical Status:** Approved canonical architecture

**Implementation Authorization:** None

**Next Authorized Capability:** None

**Review History:** Initial Draft prepared from Chief Architect direction after Engineering Architecture discovery review. The Chief Architect approved the architecture after the required documentation amendments, Engineering Architect verification passed, and repository metadata and indexes were updated for canonicalization.

ADP-001A, ADP-001B, ADP-001C, ADP-001D, ADP-001E, and the approved Platform architecture retain authority within their respective scopes. Approval of ADP-001E creates no implementation or follow-on authority.

## Related Approved Authority

- [ADP-001A — Swing Phase 1 Market Data Inventory](SWING-PHASE-1-MARKET-DATA-INVENTORY.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001C — Provider → Instrument Contract](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [ADP-001D — Instrument → Observation Contract](SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [KRONOS Platform Overview](../../platform/PLATFORM_OVERVIEW.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Provider Domain](../../platform/domains/provider/ARCHITECTURE.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [Observation Domain](../../platform/domains/observation/ARCHITECTURE.md)
- [Market Domain](../../platform/domains/market/ARCHITECTURE.md)
- [Validation Domain](../../platform/domains/validation/ARCHITECTURE.md)
- [EAIC-001 — Exchange Availability Interface Contract](../../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
