# Document Identification, Classification & Metadata Standard

**Document ID:** DOC-001
**Title:** Document Identification, Classification & Metadata Standard
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Governance Standard
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md`

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
- Review Package

A document shall have only one primary classification.

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

---

# 12. Repository Location

Repository location identifies the canonical storage location of a controlled document.

Repository location:

- shall be recorded in document metadata;
- may change through approved repository refactoring;
- shall not affect document identity.

Only one canonical repository location shall exist for each controlled document.

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
