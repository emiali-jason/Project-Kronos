# EAP-004 — Instrument Interpretation and Canonical Identity Establishment Engineering Architecture

**Document ID:** EAP-004
**Title:** Instrument Interpretation and Canonical Identity Establishment Engineering Architecture
**Version:** 2.0
**Status:** Approved
**Canonical Status:** Approved Canonical Engineering Architecture
**Classification:** Engineering Architecture Package
**Owner:** Engineering Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Approved By:** Chief Architect
**Repository Location:** `docs/engineering/eap/EAP-004-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT.md`
**Workflow Stage:** Repository Publication
**Governing Architecture:** ADR-009 Version 1.0; DOMAIN-001 Instrument Domain; ADP-001J Version 1.0
**Governing Interface:** EAIC-002 Version 0.1
**Governing Migration:** MIG-001 Version 0.1
**Upstream EAP:** EAP-003 Version 2.0
**Downstream EAP:** EAP-005 Version 1.1
**Activation State:** Inactive — Pending RC-03 Repository Synchronization and RC-04 Activation Governance
**EDD-004 Drafting Authorization:** None
**Implementation Authorization:** None
**Runtime Authority:** None
**Instrument Interpretation Authority:** None
**Persistence Authority:** None

---

# 1. Purpose

EAP-004 translates the approved product-neutral Instrument interpretation and canonical identity architecture into implementation-neutral engineering contracts.

It begins only after EAP-003 has established `ACCEPTED_FOR_INTERPRETATION` under EAIC-002. It defines:

1. Interpretation Processing Status;
2. Interpretation Outcome;
3. Canonical Identity Decision; and
4. Provider Mapping Status

as four independent Instrument-owned dimensions.

EAP-004 also defines engineering contracts for identity-layer semantic sufficiency, identity continuity, Provider mapping and cross-Provider reconciliation evidence, Instrument Identity Contract publication, and Canonical Instrument Catalogue publication.

It terminates before EAP-005 factual attribution evaluation and before any product-consumption decision.

# 2. Migration Effect

Version 2.0 replaces the product-coupled interpretation model in EAP-004 Version 1.0.

The migration:

- replaces ADP-001C Architectural Admissibility with EAIC-002 Interpretation Admission;
- removes current-product universe membership as an interpretation or canonical identity prerequisite;
- replaces the former determinate/indeterminate outcome tree with the four independent canonical dimensions;
- makes Provider Mapping Status explicitly independent from Canonical Identity Decision;
- preserves Instrument-owned cross-Provider reconciliation;
- establishes the Canonical Instrument Catalogue as product-neutral and distinct from the Provider Catalogue;
- preserves product-specific universes solely for later explicit product consumption; and
- grants no implementation, runtime, persistence, product, or EDD-004 authority.

ADP-001C and ADP-001H remain historical predecessor traceability only.

# 3. Governing Authority

EAP-004 is subordinate to:

- PLATFORM-000 — KRONOS Platform Constitution;
- ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture;
- MIG-001 — ADR-009 Coordinated Architecture Migration Package;
- EAIC-002 — Provider → Instrument Submission Contract;
- DOMAIN-001 — Instrument Domain Architecture;
- DOMAIN-006 — Provider Domain Architecture;
- ADP-001B — Instrument Identity Architecture;
- ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture;
- ADP-001D — Instrument → Observation Contract;
- the Domain Ownership Matrix;
- the Domain Dependency Matrix;
- DATA_FLOW;
- EAP-003 Version 2.0;
- EAS-001 through EAS-007; and
- applicable approved Instrument relationship, lifecycle, security, and governance authorities.

Product documents govern product eligibility and consumption only. They do not create, broaden, narrow, or replace canonical Instrument meaning.

# 4. Scope

EAP-004 defines engineering architecture for:

- Interpretation Admission consumption;
- Interpretation Processing Status;
- Instrument interpretation activity and Interpretation Outcome;
- Canonical Identity Decision;
- Provider Mapping Status;
- Economic Instrument, Listed Instrument, and Derivative Contract identity layers;
- identity-layer semantic sufficiency;
- existing identity reuse and new canonical identity establishment;
- Provider identity-scope preservation;
- canonical identity continuity;
- Provider mapping and cross-Provider reconciliation evidence;
- ambiguity, unsupported meaning, insufficiency, non-establishment, and deferral;
- Instrument Identity Contract publication eligibility;
- Canonical Instrument Catalogue publication eligibility;
- product-neutrality and downstream restrictions;
- provenance, evidence, security, and observability; and
- engineering verification.

# 5. Explicit Exclusions

EAP-004 does not define or authorize:

- Provider acquisition, Provider Catalogue mutation, Submission Eligibility, EAIC-002 delivery, or contract validation;
- parsing, matching, ranking, scoring, fuzzy logic, normalization, enrichment, deduplication, repair, algorithms, thresholds, or automated resolution;
- runtime sequencing, service workflows, APIs, schemas, payloads, transport, persistence, caches, databases, repositories, queues, or deployment;
- a new Instrument lifecycle state or relationship type;
- mapping-effective-time mechanics or lifecycle-transition behavior not already governed;
- product universe membership, Product Eligibility, product consumption, strategy, or execution selection;
- Observation formation, factual attribution, Market Facts, Validation, Risk, Execution, Portfolio, Event, or Audit meaning;
- implementation, production code, or runtime behavior; or
- EDD-004 drafting.

# 6. Ownership and Dependency Direction

| Engineering meaning | Semantic owner |
| --- | --- |
| Provider Records, Provider dispositions, and Provider provenance | Provider |
| EAIC-002 receipt, validation, and Interpretation Admission | Instrument boundary |
| Instrument interpretation and all four dimensions | Instrument |
| Canonical Instrument identity and identity layers | Instrument |
| Provider mapping and cross-Provider reconciliation | Instrument |
| Instrument relationships and governed lifecycle meaning | Instrument |
| Instrument Identity Contract and Canonical Instrument Catalogue | Instrument |
| Product universe, Product Eligibility, and product consumption | Each product, outside EAP-004 |
| Factual attribution and governed Observation | Observation, outside EAP-004 |

The engineering dependency direction is:

```text
EAP-003 ACCEPTED_FOR_INTERPRETATION
                    ↓
Interpretation Processing Status
                    ↓
Interpretation Outcome
                    ↓
Canonical Identity Decision
                    ↓
Provider Mapping Status
                    ↓
Instrument Identity Contract and
Canonical Instrument Catalogue publication
                    ↓
EAP-005 factual attribution boundary
```

The ordering does not require synchronous completion and shall not collapse the four dimensions into one workflow status.

# 7. Interpretation Input Contract

The input contract shall consume only:

- one EAIC-002 Submission Unit with `ACCEPTED_FOR_INTERPRETATION`;
- its immutable Provider, dataset, partition, snapshot, record, and unit identity associations;
- preserved Provider assertions and Provider vocabulary;
- Provider and acquisition provenance;
- submission, receipt, validation, and admission evidence;
- retained missingness, limitations, ambiguity, duplicate, and inconsistency evidence;
- safe content or immutable content reference; and
- applicable approved Instrument context.

The input contract shall not contain raw Provider payloads, SDK objects, credentials, transport-private state, Provider-created canonical meaning, product eligibility, Observation facts, or business judgment.

Instrument shall preserve Provider-owned identity scopes and shall not globalize Provider Catalogue Partition Identity, Provider Snapshot Identity, Provider Record Identity, or Submission Unit identity.

# 8. Interpretation Processing Status Contract

Exactly one processing status shall exist:

- `NOT_STARTED`;
- `PENDING`; or
- `COMPLETED`.

`NOT_STARTED` means Instrument interpretation has not begun.

`PENDING` means the bounded interpretation activity began but has not completed.

`COMPLETED` means the bounded interpretation activity completed.

Technical receipt, contract validation, and `ACCEPTED_FOR_INTERPRETATION` shall not themselves cause `PENDING` or `COMPLETED`.

Processing status establishes no Interpretation Outcome, canonical identity, Provider mapping, product eligibility, or Instrument lifecycle.

# 9. Interpretation Outcome Contract

When processing status is `COMPLETED`, exactly one mutually exclusive outcome shall exist:

| Outcome | Instrument-owned engineering meaning |
| --- | --- |
| `INTERPRETED` | A bounded supported Instrument semantic interpretation was established. |
| `UNINTERPRETED` | Processing completed without sufficient semantic interpretation. |
| `AMBIGUOUS` | More than one materially valid Instrument interpretation remains. |
| `UNSUPPORTED` | Current canonical Instrument architecture does not support interpretation of the submitted Provider assertion. |

An Interpretation Outcome shall not alter Provider information, Provider dispositions, Submission Eligibility, Provider availability, product membership, or business judgment.

Provider `AMBIGUOUS` evidence is not automatically Instrument `AMBIGUOUS`. Unrecognized Provider vocabulary is not automatically `UNSUPPORTED`.

# 10. Canonical Identity Decision Contract

Exactly one decision shall exist:

- `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED`; or
- `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

`NOT_EVALUATED` preserves that the bounded identity evaluation has not begun or remains deferred. It may coexist with `NOT_STARTED`, `PENDING`, or a completed `INTERPRETED` outcome before identity evaluation.

`CANONICAL_IDENTITY_ESTABLISHED` requires:

- processing status `COMPLETED`;
- Interpretation Outcome `INTERPRETED`;
- sufficient approved Instrument-owned identity evidence;
- no unresolved ambiguity preventing one identity decision; and
- an Instrument-owned decision to reuse an existing identity or establish a new identity.

Once identity evaluation is completed, `UNINTERPRETED`, `AMBIGUOUS`, or `UNSUPPORTED` requires `CANONICAL_IDENTITY_NOT_ESTABLISHED`.

`CANONICAL_IDENTITY_NOT_ESTABLISHED` preserves the applicable reason, creates no identity, does not imply Instrument non-existence, does not alter Provider meaning, and does not create product exclusion. It is not an Interpretation Outcome.

# 11. Provider Mapping Status Contract

Exactly one mapping status shall exist:

- `NOT_EVALUATED`;
- `MAPPING_PENDING`;
- `MAPPED`;
- `NOT_MAPPED`;
- `MAPPING_AMBIGUOUS`; or
- `MAPPING_UNSUPPORTED`.

Provider Mapping Status is independent from Canonical Identity Decision.

- a canonical Instrument may exist without a current Provider mapping;
- `MAPPED` requires a canonical identity target;
- `MAPPING_PENDING` may coexist with `CANONICAL_IDENTITY_ESTABLISHED`;
- `NOT_MAPPED` does not invalidate canonical identity;
- `MAPPING_AMBIGUOUS` preserves unresolved alternatives;
- `MAPPING_UNSUPPORTED` preserves current mapping-architecture limits;
- Provider mapping shall not create canonical identity; and
- one Provider mapping shall not establish another Provider’s mapping.

Cross-Provider reconciliation remains Instrument-owned. It shall preserve each Provider’s evidence and provenance separately, prohibit silent Provider preference, and establish no equivalence without sufficient approved Instrument evidence.

# 12. Dimension Coexistence and Terminal Meaning

The following coexistence is expressly permitted:

- `NOT_STARTED` with identity `NOT_EVALUATED` and mapping `NOT_EVALUATED`;
- `PENDING` with identity `NOT_EVALUATED` and mapping `NOT_EVALUATED`;
- `COMPLETED` and `INTERPRETED` while identity remains `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with mapping `NOT_EVALUATED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_PENDING`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `NOT_MAPPED`;
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_AMBIGUOUS`; and
- `CANONICAL_IDENTITY_ESTABLISHED` with `MAPPING_UNSUPPORTED`.

A terminal value is terminal only for the identified bounded evaluation. It does not create a permanent prohibition, Instrument lifecycle state, Provider disposition, product-eligibility state, or runtime reassessment authority.

# 13. Identity-Layer Semantic Sufficiency

Canonical identity shall preserve three distinct layers:

## 13.1 Economic Instrument

Sufficiency requires approved meaning for the economic subject, instrument class, distinction from existing Economic Instruments, continuity, provenance, and absence of unresolved ambiguity or conflict.

## 13.2 Listed Instrument

Sufficiency requires one approved Economic Instrument association, venue or listing context, distinction from other Listed Instruments, applicable relationship and continuity meaning, provenance, and absence of unresolved ambiguity or conflict.

## 13.3 Derivative Contract

Sufficiency requires one approved Listed Instrument association, underlying relationship, contract category, contract-expiry identity meaning, distinction from every other contract, applicable role context, provenance, and absence of unresolved ambiguity or conflict.

These are semantic categories, not fields, parsing rules, algorithms, scores, or thresholds.

Sufficiency shall not be established by product membership, Provider vocabulary, token presence, symbol presence, row order, price behavior, product demand, or implementation convenience.

# 14. Existing Identity Reuse and New Identity Establishment

An existing canonical identity shall be reused when approved semantic continuity is established. Provider reference, symbol, snapshot, row, or token change alone shall not create a new identity.

A new identity may be established only when positive semantic sufficiency exists for the applicable layer and the new identity remains distinguishable from existing identities.

Provider record presence, Submission Eligibility, Interpretation Admission, or `INTERPRETED` alone shall not establish canonical identity.

Provider record addition, absence, change, token reuse, or symbol change remains evidence for Instrument evaluation and shall not mutate canonical or historical identity automatically.

# 15. Instrument Identity Contract

An Instrument Identity Contract may be published only when:

- Canonical Identity Decision is `CANONICAL_IDENTITY_ESTABLISHED`;
- the applicable identity-layer meaning and continuity are established;
- required evidence and provenance are attributable;
- unresolved ambiguity does not invalidate the bounded identity decision;
- security and sensitive-data exclusions are satisfied; and
- separately required publication authority exists.

The contract may publish approved canonical identity, classification, relationships, continuity, and applicable Provider mapping meaning through Instrument-owned semantics.

It shall not publish raw Provider payloads, SDK representations, credentials, transport-private state, Provider dispositions as Instrument meaning, or product eligibility.

# 16. Canonical Instrument Catalogue Contract

The Canonical Instrument Catalogue is a product-neutral Instrument-owned publication of approved:

- canonical Instrument identities;
- canonical classifications;
- canonical relationships;
- governed lifecycle meaning;
- identity continuity;
- Provider mappings; and
- traceable evidence associations.

It is distinct from Provider Catalogue, Provider Snapshots, Provider Records, Provider dispositions, EAIC-002 units and envelopes, product universes, product eligibility lists, Observation stores, and trading-eligibility lists.

It may contain canonical Instruments consumed by zero, one, or multiple products and mapped to zero, one, or multiple Providers.

Products shall not write canonical identity, classification, relationship, lifecycle, or Provider mapping meaning into the catalogue.

This engineering contract defines publication meaning only. It grants no Persistence Authority and defines no physical catalogue implementation.

# 17. Deferral, Ambiguity, and Unsupported Meaning

Contract rejection remains an EAP-003 result and shall not become an Interpretation Outcome.

Canonical identity deferral is represented only by `NOT_EVALUATED`.

Provider mapping deferral is represented only by `NOT_EVALUATED` or `MAPPING_PENDING` according to the bounded stage.

Insufficient identity evidence shall remain explicit, preserve its reason and evidence, establish no identity, and never be converted into a convenient canonical result.

Cross-Provider reconciliation deferral shall preserve separate Provider evidence, mappings, ambiguity, and conflict without inventing equivalence or lifecycle meaning.

# 18. Product and Downstream Separation

Canonical identity is independent from Provider mapping, Provider availability, snapshot currentness, product membership, Product Eligibility, Observation availability, Validation result, Risk Approval, execution status, and current product consumption.

Swing, Intraday, and future products may consume canonical Instruments only through separately approved product-consumption boundaries.

A product shall not:

- alter canonical identity, classification, relationships, lifecycle, or Provider mappings;
- filter Provider acquisition or delete Provider evidence;
- consume Provider Catalogue records, EAIC-002 units, or envelopes directly;
- turn product exclusion into identity non-establishment; or
- activate another product.

EAP-004 output may enter EAP-005 only through the approved Instrument Identity Contract and associated safe provenance. EAP-004 creates no factual attribution or Observation ownership.

# 19. Provenance, Security, Observability, and Auditability

Engineering evidence shall preserve:

- EAIC-002 contract version and immutable input associations;
- admission evidence;
- status, outcome, identity-decision, and mapping-status evidence;
- semantic sufficiency and identity continuity evidence;
- Provider mapping and cross-Provider reconciliation evidence;
- deferral, ambiguity, unsupported, insufficiency, and non-establishment reasons;
- Instrument Identity Contract or Canonical Instrument Catalogue publication evidence where separately authorized; and
- distinct Provider acquisition, EAIC-002 submission, Instrument interpretation, identity, and mapping provenance.

Credentials, tokens, authorization headers, raw Provider payloads, SDK objects, exceptions, and private transport state shall not become Instrument evidence, identity, mapping, logs, errors, or Audit evidence.

Observability may expose only non-sensitive dimension values, reason classifications, evidence completeness, identity-layer category, publication eligibility, and boundary conformance.

Audit owns the Audit Trail only and does not acquire Instrument or Provider meaning.

# 20. Mandatory Engineering Invariants

1. Instrument interpretation begins only after EAIC-002 `ACCEPTED_FOR_INTERPRETATION`.
2. Contract rejection never becomes an Interpretation Outcome.
3. The four Instrument dimensions remain independent and retain exact cardinality.
4. Processing status does not establish an Interpretation Outcome.
5. `INTERPRETED` does not by itself establish canonical identity.
6. Canonical identity does not by itself establish Provider mapping.
7. Provider mapping does not create canonical identity.
8. Product membership does not participate in interpretation, identity, or mapping.
9. Provider-owned identity scopes remain bounded and never become canonical identity automatically.
10. Provider information remains Provider-owned throughout interpretation.
11. Instrument does not silently repair, select, merge, or discard Provider evidence.
12. Canonical identity remains product-neutral.
13. Cross-Provider reconciliation remains Instrument-owned and preserves separate provenance.
14. Provider Snapshot currentness and record change do not create Instrument lifecycle.
15. Canonical Instrument Catalogue remains distinct from Provider Catalogue and product universes.
16. Instrument publication creates no product eligibility, Observation acceptance, Validation, Risk, Execution, Portfolio, or trading authority.
17. EAP-004 remains implementation-neutral and inactive.
18. No persistence, runtime interpretation, or implementation authority is granted.
19. EDD-004 remains unauthorized.

# 21. Engineering Verification

Engineering Verification shall confirm:

- traceability to ADR-009, MIG-001, EAIC-002, DOMAIN-001, ADP-001J, EAP-003 Version 2.0, and ADP-001D;
- complete removal of active ADP-001C and product-universe identity prerequisites;
- exact four-dimension values, cardinality, ordering, permitted coexistence, and non-implications;
- product-neutral identity-layer sufficiency;
- canonical identity and Provider mapping independence;
- Provider identity-scope and provenance preservation;
- Instrument-owned cross-Provider reconciliation;
- Canonical Instrument Catalogue separation;
- absence of product eligibility, Observation, Validation, Risk, Execution, Portfolio, Event, or Audit meaning;
- security, observability, and Audit safety;
- authority separation and inactive state;
- metadata, register, links, and repository path consistency; and
- absence of implementation, persistence, runtime, or EDD-004 authority.

# 22. Publication Record

Version 2.0 is the approved canonical engineering replacement for EAP-004 Version 1.0 under RC-02 — Engineering Architecture Publication.

Publication establishes engineering architecture only. RC-03 Repository Synchronization and RC-04 Activation Governance remain subsequent and separate. EDD-004 drafting remains prohibited until explicitly authorized after those stages.

# 23. Related Approved Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../architecture/migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../architecture/interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Instrument Domain Architecture](../../architecture/platform/domains/instrument/ARCHITECTURE.md)
- [ADP-001J — Instrument Interpretation and Canonical Identity](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md)
- [ADP-001D — Instrument → Observation Contract](../../architecture/products/swing/SWING-PHASE-1-INSTRUMENT-OBSERVATION-CONTRACT.md)
- [EAP-003 — Submission Validation and Interpretation Admission](EAP-003-PROVIDER-TO-INSTRUMENT-ARCHITECTURAL-ADMISSIBILITY.md)
- [EAP-005 — Instrument-to-Observation Attribution Eligibility](EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
