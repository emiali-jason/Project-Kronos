# CAR-005 — Architecture Programme Governance Authorization

**Document ID:** CAR-005
**Title:** Architecture Programme Governance Authorization
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** KRONOS Repository Publication Team
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-005-ARCHITECTURE-PROGRAMME-GOVERNANCE-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Governance Authority:** Chief Architect Approved
**Decision:** AUTHORIZE WITH CONSTRAINTS
**Decision Date:** 2026-07-27
**Authoritative Branch:** `develop`
**Implementation Authority:** None
**Runtime Authority:** None

---

# 1. Executive Summary

KRONOS shall support multiple repository-governed Architecture Governance Programmes under a common governance mechanism.

An Architecture Governance Programme is a bounded coordination and assurance structure. It is not architecture, a domain, a product, an engineering authority, or an implementation authority. Authority continues to reside only in separately approved repository documents.

The programme lifecycle requires explicit governance gates. Architecture must be approved and published before dependent Engineering Design begins, and every controlled artefact must cross its own review, approval, publication, and freeze gates.

**Decision: AUTHORIZE WITH CONSTRAINTS.**

This decision authorizes no specific programme. Human Interaction Architecture, HIAP, GAD, GAA, GED, GPV, implementation, runtime, and programme-document publication remain unauthorized.

# 2. Repository Review

The review was performed against the current `develop` branch as the sole authoritative repository source.

Reviewed authorities included:

- [PLATFORM-000 — KRONOS Platform Constitution](../../architecture/platform/PLATFORM-000-CONSTITUTION.md);
- [KRONOS Platform Architecture Overview](../../architecture/platform/PLATFORM_OVERVIEW.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md);
- [Document Register](../../indexes/DOCUMENT-REGISTER.md);
- [CAR-001 — Governance Foundation Review](CAR-001-GOVERNANCE-FOUNDATION-REVIEW.md);
- [CAR-002 — Governance Foundation Closure Review](CAR-002-GOVERNANCE-FOUNDATION-CLOSURE-REVIEW.md);
- [CAR-003 — RC-04 Architecture Activation and Engineering Authorization Decision](CAR-003-RC-04-ARCHITECTURE-ACTIVATION-AND-ENGINEERING-AUTHORIZATION-DECISION.md);
- [CAR-004 — EDD-005 Draft Authorization Decision](CAR-004-EDD-005-DRAFT-AUTHORIZATION-DECISION.md);
- [ADR Index](../../architecture/adr/README.md);
- [Platform Architecture Index](../../architecture/platform/ARCHITECTURE_INDEX.md);
- the approved Engineering Architecture Standards; and
- repository documentation governance.

The review established:

- PLATFORM-000 requires single semantic ownership, contract-based dependencies, human-workflow independence, and ADR-controlled changes to frozen architecture.
- Approved Platform Governance recognizes an evidence-before-architecture progression.
- DOC-001 governs document families, identity, metadata, repository location, lifecycle state, and Document Register integration.
- CAR-003 uses the term “Architecture Programme” but does not define a reusable, multi-programme governance mechanism.
- CAR-004 confirms that downstream activity requires specific authorization and that authority does not propagate implicitly.
- CAR-001, CAR-002, the Architecture Governance document, and ADR Governance remain Draft and are not treated as approved authority.
- No approved repository document previously established a general Architecture Governance Programme mechanism.

Two existing navigation inconsistencies were observed:

- the ADR Index describes ADR-009 as inactive pending activation, while CAR-003 and the Document Register establish it as active Operational Architecture; and
- the Platform Architecture Index does not list ADR-009 with the approved Provider ADRs.

These inconsistencies do not prevent this decision, do not conflict with its scope, and are not resolved by CAR-005.

# 3. Governance Objective

CAR-005 authorizes KRONOS to organize suitable architectural initiatives as separately authorized Architecture Governance Programmes.

The mechanism provides:

- bounded programme scope;
- explicit programme ownership and review authority;
- separation of discovery, architecture, engineering, and implementation;
- controlled governance gates;
- repository traceability;
- preservation of existing ownership and dependencies;
- independent verification; and
- governed closure.

CAR-005 does not approve the subject matter, findings, architecture, engineering, or implementation of any individual programme.

# 4. Architecture Governance Programme Definition

An **Architecture Governance Programme** is a time-bounded, repository-governed coordination structure for investigating and resolving a material architectural concern that may require multiple related decisions, contracts, architecture records, and downstream Engineering Designs.

An Architecture Governance Programme:

- coordinates related governance activity;
- defines the concern, scope, boundaries, affected authorities, dependencies, risks, and required decisions;
- preserves traceability between discovery evidence, architecture, and downstream engineering;
- provides governance gates and a closure determination;
- may span Platform and Product Architecture where separately authorized; and
- may coordinate multiple controlled documents without becoming their semantic owner.

An Architecture Governance Programme is not:

- a new governance layer above the Platform Constitution;
- an architectural domain;
- a product;
- an Architecture Decision Record;
- a document family;
- a repository folder;
- an Engineering Programme;
- a runtime component;
- an implementation plan; or
- an independent source of semantic authority.

Only approved programme artefacts possess authority within their recorded scopes.

# 5. Governance Principles

Every Architecture Governance Programme shall preserve these principles:

1. **Specific authorization**
   Each programme requires a separate Chief Architect authorization defining its purpose, scope, owner, affected authority, exclusions, and permitted starting phase.

2. **No implied programme authority**
   CAR-005 authorizes the governance mechanism only. It authorizes no named programme.

3. **Single semantic ownership**
   A programme may examine ownership but cannot acquire, duplicate, or transfer it.

4. **Authority separation**
   Discovery, architecture, engineering, verification, approval, publication, implementation, and runtime authority remain independent.

5. **Evidence is not authority**
   Findings, observations, alternatives, prototypes, and recommendations do not become architecture automatically.

6. **Architecture before engineering**
   Engineering Design may derive only from approved, repository-published architecture and separately granted Engineering Authorization.

7. **No automatic promotion**
   Completion of one programme phase or governance gate does not authorize the next.

8. **Repository authority**
   Chat history, meetings, working notes, and programme labels are not authoritative.

9. **Controlled architectural change**
   Any change to frozen Platform or Product Architecture requires the applicable approved architectural decision process, including a new ADR where required.

10. **No implementation implication**
    Programme completion, architecture approval, engineering completion, verification, or publication does not authorize implementation or runtime activity.

# 6. Discovery Governance

Discovery is the exploratory phase of a separately authorized Architecture Governance Programme.

Discovery may:

- gather evidence and provenance;
- document observations and open questions;
- identify affected architecture, ownership, contracts, products, and dependencies;
- compare alternatives;
- identify risks and unresolved authority;
- test whether an architectural change is necessary; and
- recommend that ADRs or other architecture records be prepared.

Discovery shall:

- produce Draft, non-authoritative findings;
- distinguish evidence, inference, recommendation, and unresolved question;
- preserve existing architecture as authoritative;
- avoid assigning new ownership or dependencies;
- avoid engineering or implementation design; and
- record conflicts rather than resolving them by assumption.

Discovery Review determines only whether:

- the authorized investigation is sufficiently complete;
- its findings and limitations are reviewable;
- unresolved matters are explicit; and
- Architecture Authorization may be considered.

Discovery Review does not approve Discovery recommendations as architecture.

Within an Architecture Governance Programme, Architecture preparation may begin only after Discovery Review and explicit Architecture Authorization. This rule applies prospectively to Architecture Governance Programmes and does not replace the existing standalone ADR process.

# 7. Lifecycle Governance

Every Architecture Governance Programme shall use the following programme-governance model:

```text
Programme Authorization
        ↓
Discovery
        ↓
Discovery Review
        ↓
Architecture Authorization
        ↓
Architecture
        ↓
Architecture Review
        ↓
Architecture Publication
        ↓
Engineering Authorization
        ↓
Engineering Design
        ↓
Engineering Verification
        ↓
Engineering Publication
        ↓
Programme Closure
```

The governance gates have the following meanings:

1. **Programme Authorization** permits only the bounded programme activity stated in its decision.
2. **Discovery** produces exploratory, non-authoritative findings.
3. **Discovery Review** assesses investigative sufficiency without approving architecture.
4. **Architecture Authorization** is required before Architecture preparation begins.
5. **Architecture** produces proposed architecture through existing approved architectural mechanisms.
6. **Architecture Review** applies the required independent review and approval authority.
7. **Architecture Publication** publishes approved architecture before dependent Engineering Design may begin.
8. **Engineering Authorization** separately authorizes bounded Engineering Design.
9. **Engineering Design** translates published architecture without redefining it.
10. **Engineering Verification** verifies completeness, conformance, boundaries, ownership, and traceability without approving architecture or authorizing implementation.
11. **Engineering Publication** publishes only independently approved engineering artefacts.
12. **Programme Closure** records completion, deferral, rejection, supersession, or remaining authorized work and grants no further authority.

These are programme-governance gates, not additions to the DOC-001 Workflow Stage vocabulary.

Programme governance does not replace controlled-document governance. Every controlled artefact follows its own DOC-001-compliant authorization, review, approval, canonicalization, publication, amendment, supersession, and retirement requirements.

An Architecture Governance Programme may be stopped, rejected, deferred, or returned for amendment at any applicable gate.

# 8. Repository Governance Requirements

Every future Architecture Governance Programme shall require:

- an explicit programme authorization;
- use of approved document families;
- compliant DOC-001 metadata;
- an approved repository location for every controlled artefact;
- Document Register integration;
- unique and stable document identities;
- explicit owners and review authorities;
- lifecycle and authorization states recorded independently;
- backward and forward traceability;
- preserved review and supersession history;
- valid repository navigation; and
- a controlled closure record.

CAR-005 does not:

- create a document family;
- allocate a prefix;
- allocate an identifier for any programme artefact;
- define a repository path for any programme artefact;
- reserve programme documents;
- amend DOC-001; or
- authorize publication of future programme artefacts.

A future programme shall use existing approved document families where suitable. Any additional family, identifier policy, or location requires separate DOC-001-governed approval.

Repository folders, indexes, and programme names shall not confer authority.

# 9. Relationship to Existing Governance

## 9.1 Platform Architecture

Architecture Governance Programmes remain subordinate to PLATFORM-000, the Platform Overview, ownership and dependency matrices, approved ADRs, and canonical contracts. Changes to frozen Platform Architecture require a separately approved ADR.

## 9.2 Product Architecture

An Architecture Governance Programme may investigate or propose Product Architecture only within separately authorized scope. It cannot silently establish a product, product owner, product dependency, GUI responsibility, or consumer authority.

## 9.3 Engineering

Engineering remains downstream of approved architecture. EAS, EAP, EDD, and Engineering Verification governance remain unchanged. Programme authorization does not authorize an EAP, EDD, module, implementation, or runtime activity.

## 9.4 Repository Governance

DOC-001 continues to govern document identity, family, metadata, location, status, and Document Register integration. CAR-005 adds no competing lifecycle vocabulary.

## 9.5 Existing CAR Authority

CAR-003 remains limited to its recorded architecture activation and EDD-004 authority. CAR-004 remains limited to EDD-005. Neither becomes general authority for a named Architecture Governance Programme.

## 9.6 Research and Discovery

Existing research areas remain evidence repositories. Their contents are not promoted into architecture merely because an Architecture Governance Programme references them.

# 10. Risks

| Risk | Required control |
|---|---|
| Programme name becomes de facto authority | Require explicit artefact-level approval and status. |
| Discovery findings become architecture | Preserve Draft classification and separate Architecture Authorization. |
| Programme lifecycle bypasses document governance | Treat it as a governance overlay with document-level gates. |
| Engineering begins from unpublished architecture | Require Architecture Review and Architecture Publication first. |
| Programme creates shadow ownership | Preserve PLATFORM-000 and ownership-matrix authority. |
| Cross-programme duplication | Require scope, ownership, dependency, and register review. |
| Document proliferation | Apply the documentation-creation necessity test. |
| Programme authorization implies implementation | Record Implementation Authority and Runtime Authority independently as `None`. |
| Human Interaction is treated as approved | Explicitly prohibit Human Interaction Architecture, HIAP, GAD, GAA, GED, GPV, and GUI authority. |
| Programme never formally closes | Require an explicit Programme Closure disposition. |
| Indexes misrepresent current authority | Validate navigation against canonical decisions during future publication. |

# 11. Resolution

## AUTHORIZE WITH CONSTRAINTS

KRONOS is authorized to support multiple repository-governed Architecture Governance Programmes following the governance mechanism defined by CAR-005.

The authorized mechanism:

- permits separately authorized programmes to coordinate Discovery, Architecture, Engineering Design, Verification, Publication, and Programme Closure;
- requires independent authorization for every programme;
- treats Discovery as exploratory and non-authoritative;
- requires Architecture to derive from reviewed Discovery without being predetermined by it;
- requires Architecture Review and Architecture Publication before dependent Engineering Design;
- requires separate Engineering Authorization;
- requires Engineering Verification before Engineering Publication;
- preserves existing Platform, Product, domain, contract, and Engineering authority; and
- grants no implementation or runtime authority.

This resolution does not authorize:

- Human Interaction Architecture;
- a Human Interaction Architecture Governance Programme;
- HIAP;
- GAD;
- GAA;
- GED;
- GPV;
- GUI architecture or design;
- any other named programme;
- any programme document;
- any architecture change;
- Engineering Design;
- implementation;
- runtime activity; or
- publication of a programme artefact.

# 12. Recommendations

1. Require a separate resolution before initiating any named Architecture Governance Programme.
2. For any future Human Interaction initiative, authorize Discovery only in its first programme decision.
3. Before creating controlled programme artefacts, determine their existing DOC-001 families, metadata, locations, and Document Register treatment.
4. Define programme-specific scope, exclusions, owners, affected authorities, Discovery questions, evidence requirements, and gate criteria in the programme authorization.
5. Reconcile the ADR-009 navigation inconsistencies through separate repository-maintenance governance.
6. Preserve Implementation Authority and Runtime Authority as `None` until separately and explicitly granted.

# End of Document
