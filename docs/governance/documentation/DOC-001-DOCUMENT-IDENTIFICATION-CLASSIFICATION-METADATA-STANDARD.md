# Document Identification, Classification & Metadata Standard

**Document ID:** DOC-001
**Title:** Document Identification, Classification & Metadata Standard
**Version:** 1.1
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Governance Standard
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md`
**Documentation Authority:** Chief Architect Approved
**Implementation Authority:** None
**Runtime Authority:** None

---

# 1. Purpose

This document establishes the standard for identifying, classifying, naming, and describing controlled documentation within the Project KRONOS repository.

Its purpose is to ensure that every controlled document is uniquely identifiable, consistently classified, and governed throughout its lifecycle.

---

# 2. Objectives

This standard shall:

- establish a unique document identification system;
- define document families and prefixes;
- standardise document metadata;
- define document classifications;
- standardise lifecycle status values;
- establish repository naming conventions;
- eliminate identifier ambiguity;
- support long-term repository governance.

---

# 3. Scope

This standard applies to every controlled document maintained within the Project KRONOS repository, including but not limited to:

- governance documents;
- architecture documents;
- engineering standards;
- engineering packages;
- architecture decision records;
- platform principles;
- interface contracts;
- architecture models;
- validation documents;
- research documents;
- migration packages;
- review packages;
- Architecture Governance Programme artefacts;
- repository indexes.

Documents outside repository governance are not subject to this standard.

---

# 4. Document Identity

Every controlled document shall possess one unique Document ID.

A Document ID:

- uniquely identifies a controlled document;
- remains permanently assigned;
- shall never be reused;
- shall remain independent of file location;
- shall remain stable across document revisions.

Changing repository structure shall not change document identity.

---

# 5. Document Families

Controlled documents shall be organised into defined document families.

Current approved families include:

| Prefix | Document Family |
|---------|-----------------|
| GOV | Governance |
| DOC | Documentation Standards |
| IDX | Repository Index |
| CAR | Chief Architect Review |
| ADR | Architecture Decision Record |
| PP | Platform Principle |
| ADP | Product Architecture |
| ADL | Legacy Architecture Decision Log |
| EAIC | Architecture Interface Contract |
| ECIC | Execution Context Interface Contract |
| ECPC | Execution Context Payload Contract |
| ECM | Architecture Model |
| EAS | Engineering Architecture Standard |
| EAP | Engineering Architecture Package |
| EDD | Engineering Design Document |
| EP | Engineering Package |
| MIG | Migration Package |
| VAL | Validation *(reserved)* |
| RES | Research *(reserved)* |

Additional document families require Chief Architect approval.

## 5.1 Migration Packages

Migration Packages govern coordinated migration of approved repository architecture while preserving repository consistency.

They coordinate:

- migration planning;
- migration sequencing;
- migration validation;
- migration publication; and
- migration rollback planning.

Migration Packages are governance artefacts.

They are not architecture documents.

They are not Engineering Design Documents.

They do not authorize implementation.

Migration Packages:

- are initiated following approved architectural change;
- coordinate migration of canonical architecture;
- may reference ADRs, Domains, ADPs, EAPs, and EDDs;
- do not replace architectural authority; and
- do not supersede ADRs.

Migration Packages may govern migration planning, migration sequencing, migration validation, migration publication, and migration rollback planning.

Migration Packages do not authorize:

- implementation;
- runtime behaviour;
- endpoint invocation;
- persistence implementation;
- engineering work; or
- EDD execution.

The Chief Architect owns Migration Packages.

Migration Packages follow the existing repository lifecycle model:

- Draft;
- Approved; and
- Canonical.

They introduce no unique lifecycle.

ADLs are retained for historical and architectural traceability. ADLs are not automatically equivalent to ADRs. Future architectural decisions shall use the approved ADR family unless explicitly authorized otherwise. Migration of an ADL into an ADR requires a separate controlled decision. Existing ADL identifiers shall not change.

---

# 6. Identifier Allocation

Each Document ID shall:

- belong to exactly one document family;
- contain a unique numeric sequence within that family;
- never duplicate an existing identifier;
- never be reassigned to a different document.

Reserved identifiers shall remain reserved until released through governance.

Migration Package identifiers shall use the governed family prefix followed by a three-digit sequence:

- `MIG-001`;
- `MIG-002`; and
- subsequent identifiers in the same format.

---

# 7. Document Metadata

Every controlled document shall include the following metadata:

- Document ID
- Title
- Version
- Status
- Classification
- Owner
- Prepared By
- Review Authority
- Repository Location

Optional metadata may be added where appropriate but shall not replace required metadata.

## 7.1 Architecture Governance Programme Artefact Metadata

All existing mandatory metadata remains required for Architecture Governance Programme artefacts.

Architecture Governance Programme artefacts shall additionally record:

| Metadata | Requirement |
|---|---|
| Programme | The exact governed programme name or identity established by its specific authorization. Programme metadata shall not be populated before that authorization exists. |
| Programme Stage | The CAR-005 gate or activity to which the artefact belongs. This is distinct from DOC-001 Workflow Stage. |
| Classification | One approved DOC-001 primary classification. Discovery artefacts use `Architecture Discovery`. |
| Programme Authority | The approved governance record and bounded authority under which the artefact exists, or `None` where authority is absent. |
| Lifecycle Status | Recorded through the existing DOC-001 `Status` field. |
| Repository Status | Whether the governed version is `Not Published` or `Published` at its approved canonical repository location. |

The following rules apply:

- `Programme Stage` does not grant authority or alter Workflow Stage.
- `Programme Authority` shall cite authority and shall not infer authority from a programme name, folder, register entry, or prior stage.
- `Repository Status: Published` records repository presence only. It does not mean Approved, Canonical, or authorized.
- `Status: Draft` remains non-authoritative even when Repository Status is `Published`.
- Architecture Discovery shall always record `Status: Draft` and `Canonical Status: Draft`.
- Implementation Authority and Runtime Authority remain separate and shall be `None` unless an explicit future decision establishes otherwise.
- Conflicting metadata shall be resolved in favor of the governing authorization and the higher repository authority.

---

# 8. Document Classification

Every controlled document shall have one primary classification.

Approved classifications include:

- Constitution
- Governance Standard
- Documentation Standard
- Repository Index
- Architecture Standard
- Architecture Decision Record
- Legacy Architecture Decision Log
- Architecture Principle
- Product Architecture
- Architecture Model
- Interface Contract
- Engineering Architecture Standard
- Engineering Architecture Package
- Engineering Design Document
- Engineering Package
- Migration Package
- Validation Standard
- Validation Report
- Research Standard
- Research Report
- Architecture Discovery
- Review Package

A document shall have only one primary classification.

## 8.1 Architecture Governance Programme Documentation

An Architecture Governance Programme is a bounded, repository-governed coordination mechanism authorized under CAR-005. It coordinates controlled Discovery, Architecture, Engineering Design, Verification, Publication, and Programme Closure activity.

An Architecture Governance Programme:

- operates within Platform Governance;
- remains subordinate to PLATFORM-000 and approved Platform Architecture;
- may coordinate Product Architecture without acquiring product authority;
- permits Engineering Design only after architecture publication and separate Engineering Authorization;
- uses DOC-001 for document identity, classification, metadata, location, naming, lifecycle, and register governance;
- cannot transfer semantic ownership;
- cannot grant authority merely through programme membership; and
- requires each controlled artefact to complete its own lifecycle.

An Architecture Governance Programme is not:

- architecture;
- a document family;
- a repository location;
- a product;
- a domain;
- an engineering authority;
- an implementation authority; or
- a runtime authority.

## 8.2 Programme Artefact Categories

Programme artefact categories describe an artefact's role within a programme. They are not document families or primary classifications unless this standard separately identifies them as classifications.

| Artefact category | Documentation purpose | Governance boundary |
|---|---|---|
| Programme Charter | Records the separately approved programme purpose, scope, exclusions, owner, authorities, gates, required artefacts, and closure conditions. | Does not independently authorize the programme or any phase. |
| Discovery | Records evidence, observations, alternatives, risks, limitations, and recommendations. | Uses the `Architecture Discovery` classification and remains Draft and non-authoritative. |
| Architecture | Records proposed or approved architecture through an applicable existing architectural form. | Authority arises only from the artefact's own approval, not its programme association. |
| Engineering Design | Translates approved, published architecture through applicable existing Engineering governance. | Requires separate Engineering Authorization and cannot redefine architecture. |
| Verification | Records independent conformance, completeness, traceability, boundary, and lifecycle findings. | Verification produces evidence; it does not create architecture or implementation authority. |

Programme Closure shall be recorded through the applicable authorized governance or verification artefact. It does not require a new artefact category or document family.

## 8.3 Architecture Discovery Classification

Architecture Discovery is the primary classification for controlled exploratory findings produced during the Discovery phase of a separately authorized Architecture Governance Programme.

Architecture Discovery shall:

- have Lifecycle Status `Draft`;
- have Canonical Status `Draft`;
- remain exploratory and non-authoritative;
- identify its governing programme authorization;
- distinguish evidence, observation, inference, recommendation, and unresolved question;
- preserve approved architecture unchanged;
- create no domain, product, responsibility, ownership, dependency, interface, or authority;
- create no Engineering Design or implementation requirement;
- recommend architectural work or ADR preparation without approving it; and
- remain non-authoritative after Discovery Review.

Classification distinctions are:

| Classification or authority | Distinction from Architecture Discovery |
|---|---|
| Approved Architecture | Possesses architectural authority within its approved scope. Architecture Discovery never does. |
| Engineering Design | Translates approved architecture downstream. Architecture Discovery cannot perform that translation. |
| Architecture Decision Record | Records an architectural decision and becomes authoritative only after approval. Architecture Discovery may recommend an ADR but cannot replace one. |
| Chief Architect Review | Records governance, review, authorization, or disposition. Architecture Discovery cannot grant those outcomes. |

Adding the Architecture Discovery classification does not create a corresponding document family, prefix, number range, identifier, or repository path.

---

# 9. Governance State Vocabulary

Every controlled document shall distinguish Lifecycle Status, Workflow Stage, Register Disposition and Authorization State.

### 9.1 Lifecycle Status

Approved lifecycle status values are:

- Draft
- Approved
- Canonical
- Superseded
- Retired
- Deferred

Lifecycle Status describes the authority and maturity of an existing controlled document. Planned is not a lifecycle status for an existing document.

### 9.2 Workflow Stage

Approved workflow stages are:

- Draft Authorization
- Draft Preparation
- Engineering Verification
- Chief Architect Review
- Amendment Required
- Engineering Reverification
- Chief Architect Re-review
- Canonicalization
- Repository Publication
- None

Workflow Stage describes the current governance activity and does not itself grant document authority.

### 9.3 Register Disposition

Approved register dispositions are:

- Planned
- Reserved
- Unassigned Controlled Authority
- Cancelled
- None

Planned means identified for future consideration and does not authorize drafting. Reserved protects an identifier or intended responsibility and does not authorize creation. Unassigned Controlled Authority identifies an existing controlled authority awaiting governed identity allocation. Cancelled identifies a proposed entry that will not proceed. None applies where no special register disposition exists.

### 9.4 Authorization State

Approved authorization states are:

- None
- Draft Authorized
- Implementation Authorized
- Suspended
- Completed

Where relevant, Draft Authorization and Implementation Authorization shall be recorded independently. EDD approval or canonicalization does not authorize implementation. Draft Authorization is required before creating a specific EDD. Implementation Authorization requires a separate explicit decision.

### Engineering Design Document Lifecycle

Engineering Design Documents shall:

- require Chief Architect draft authorization;
- follow the controlled lifecycle defined by GOV-002;
- require Engineering Verification;
- require Chief Architect review;
- require approval and canonicalization;
- not authorize implementation merely by being approved or canonical; and
- require separate explicit implementation authorization unless a future canonical standard states otherwise.

---

# 10. Versioning

Controlled documents shall use semantic document versions.

Typical progression:

- 0.1 Draft
- 0.2 Draft
- 0.3 Draft
- 1.0 Approved
- 1.1 Minor Revision
- 2.0 Major Revision

Version history shall remain traceable.

Approved documents shall never revert to an earlier version.

---

# 11. Repository Naming Standards

Repository filenames shall:

- clearly describe document purpose;
- contain the Document ID where applicable;
- use uppercase document prefixes;
- use hyphen-separated words;
- avoid ambiguous abbreviations;
- remain stable after approval except through governance.

Example:

`EAS-002-REPOSITORY-ENGINEERING-STANDARDS.md`

`EDD-001-PROVIDER-ACCESS-AND-PROVIDER-CONTEXT-ENGINEERING-DESIGN.md`

## 11.1 Architecture Governance Programme Artefact Naming

Architecture Governance Programme artefact naming shall:

- use an identifier allocated from an approved document family;
- contain the assigned stable Document ID;
- describe the programme association and artefact purpose clearly;
- identify the artefact category or governed subject where useful;
- follow existing uppercase-prefix and hyphenated-filename rules;
- avoid unapproved abbreviations;
- avoid implying Approved or Canonical status in the filename;
- remain stable across ordinary version changes; and
- avoid treating the programme name as a document-family prefix.

This standard does not define:

- a programme-specific prefix;
- a programme-specific numbering sequence;
- reserved programme identifiers;
- programme acronyms; or
- filenames for any specific programme.

---

# 12. Repository Location

Repository location identifies the canonical storage location of a controlled document.

Repository location:

- shall be recorded in document metadata;
- may change through approved repository refactoring;
- shall not affect document identity.

Only one canonical repository location shall exist for each controlled document.

## 12.1 Architecture Governance Programme Artefact Locations

Future Architecture Governance Programme artefact locations shall:

- be approved before controlled publication;
- conform to the selected existing document family and artefact purpose;
- preserve one canonical location per controlled document;
- avoid duplicating an artefact merely to group it under a programme;
- preserve shared authorities at their existing owning locations;
- use links instead of copied authoritative content;
- remain stable after approval except through governed refactoring; and
- be recorded in both document metadata and the Document Register.

A programme name, programme stage, folder, or artefact category does not allocate a repository location.

This standard does not prescribe a generic programme directory. Any programme-specific hierarchy requires separate repository governance.

---

# 13. Identifier Governance

Document identifiers shall be allocated through repository governance.

Before assigning a new identifier:

- verify the identifier is unused;
- verify the document family is correct;
- verify the Document Register has been updated;
- verify no existing controlled document represents the same responsibility.

Duplicate identifiers are prohibited.

---

# 14. Document Register

Every controlled document shall be recorded in the Repository Document Register.

The register shall record:

- Document ID;
- Title;
- Classification;
- Status;
- Version;
- Repository Location;
- Owner.

No controlled document shall exist outside the register.

The register is the authoritative index of repository-controlled documentation.

## 14.1 Architecture Governance Programme Artefacts

Every controlled Architecture Governance Programme artefact shall have its own Document Register entry.

The existing register structure remains applicable:

- Document ID, Title, Classification, Status, Workflow Stage, Owner, Review Authority, and Repository Location use existing columns.
- Programme, Programme Stage, Programme Authority, and Repository Status may be recorded in `Remarks`.
- Architecture Discovery entries shall record Lifecycle Status `Draft` and Classification `Architecture Discovery`.
- A programme-level row shall not replace individual artefact rows.
- Planned or Reserved entries do not authorize drafting.
- Register inclusion does not authorize a programme, stage, document, architecture, engineering, implementation, or runtime activity.
- No controlled programme artefact may exist outside the register.

No Document Register schema change is required.

---

# 15. Metadata Governance

Required metadata shall appear at the beginning of every controlled document.

The standard metadata format shall include:

- Document ID
- Title
- Version
- Status
- Classification
- Owner
- Prepared By
- Review Authority
- Repository Location

Metadata shall accurately reflect the current governance state of the document.

Metadata shall be updated whenever the document lifecycle changes.

---

# 16. Ownership

Every controlled document shall have a clearly identified owner.

The owner is responsible for:

- maintaining document accuracy;
- initiating revisions;
- coordinating reviews;
- ensuring repository consistency;
- maintaining alignment with approved architecture.

Ownership shall remain unambiguous throughout the document lifecycle.

---

# 17. Traceability

Controlled documentation shall support complete traceability.

Documents shall reference related controlled documents where appropriate.

Traceability may include references to:

- Governance documents;
- applicable Constitutions and governance standards;
- Product Architecture;
- Architecture Decision Records;
- Platform Principles;
- Domain Architecture;
- EAS documents;
- the governing EAP;
- Engineering Standards;
- Interface Contracts;
- Validation documents;
- Review Packages.

An Engineering Design Document shall maintain backward traceability to applicable approved governance, architecture and engineering authority. Forward traceability to implementation, tests, validation and verification evidence shall be established progressively as those artifacts are created. The absence of future downstream artifacts shall not prevent EDD approval or canonicalization.

Traceability shall improve repository navigation without introducing unnecessary duplication.

## 17.1 Architecture Governance Programme Traceability

Architecture Governance Programme artefacts shall maintain traceability to:

- CAR-005;
- the specific programme authorization;
- the applicable programme stage;
- source evidence and predecessor artefacts;
- applicable Platform and Product Architecture;
- affected ADRs and contracts;
- separately authorized downstream artefacts;
- verification findings; and
- Programme Closure disposition.

Traceability does not promote a referenced Draft into authority.

---

# 18. Compliance

All controlled documents shall comply with:

- GOV-001 — Governance Constitution;
- GOV-002 — Governance Lifecycle;
- DOC-001 — Document Identification, Classification & Metadata Standard;
- approved repository standards.

Non-compliant documentation shall be corrected through the established governance process.

---

# 19. Exceptions

Exceptions to this standard require explicit approval from the Chief Architect.

Approved exceptions shall record:

- affected document;
- justification;
- approval authority;
- review requirements;
- expected retirement or review date where appropriate.

Exceptions shall remain traceable within the repository.

---

# 20. Relationship to Other Documents

This document supports and complements:

- GOV-001 — Governance Constitution;
- GOV-002 — Governance Lifecycle;
- IDX-001 — Repository Document Register;
- all controlled architecture documents;
- all engineering standards;
- all governance standards.

Future controlled documents shall conform to this standard unless an approved exception exists.

---

# 21. Review and Approval

This document shall follow the governance lifecycle defined in GOV-002.

Lifecycle:

Draft

↓

Engineering Verification

↓

Chief Architect Review

↓

Approved

↓

Canonical

## Canonical Approval

This document is approved as the canonical repository standard governing document identification, classification, metadata and Engineering Design Document recognition within Project KRONOS.

---

# End of Document
