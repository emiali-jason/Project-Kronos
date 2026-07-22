# Project KRONOS Documentation Governance

**Status:** Draft
**Owner:** Chief Architect
**Lifecycle:** Draft → Approved → Superseded

## 1. Purpose

Project KRONOS values authoritative documentation over excessive documentation. Documentation must exist to reduce material project risk, preserve necessary authority, or make durable knowledge maintainable.

Every document must have a clear purpose, a single owner, and an explicit lifecycle or status. A document must not exist merely because a process can produce it.

This document governs when documentation should be created. It does not define how architecture is decided, how engineering is performed, how ADRs are governed, or how repository authority is assigned. Those matters remain governed by their existing authoritative documents.

## 2. Guiding Principles

- Documentation must exist only when it materially reduces project risk.
- Every document must have one authoritative purpose.
- Documents must not duplicate responsibilities or information already maintained elsewhere.
- Approved documents take precedence over Draft or Proposed documents within their approved scope.
- Documentation should remain lean, current, navigable, and maintainable.
- Links to an authoritative source should be preferred over copied content.
- Temporary knowledge may remain in working discussion until it requires durable repository authority.

## 3. Documentation Creation Rule

A new document should be created only when its absence would materially increase one or more of:

- architectural risk;
- engineering risk;
- operational risk;
- maintenance risk; or
- governance risk.

Before creating a document, the author must determine whether an existing authoritative document already owns the purpose. When it does, that document should be updated instead, subject to its status, ownership, and change controls.

Convenience, anticipated future use, or a desire for completeness is not sufficient justification for a new document.

## 4. Approved Documentation Types

KRONOS uses the following established major document classes:

| Document class | Authoritative purpose |
| --- | --- |
| Platform Constitution | Records constitutional platform authority and constraints. |
| Architecture Documents | Describe approved or proposed architectural boundaries and responsibilities. |
| Architecture Decision Records (ADRs) | Preserve material architecture decisions and their rationale. |
| Product Architecture | Defines product-level responsibilities and boundaries. |
| Engineering Design Documents (EDDs) | Describe a reviewable engineering design within approved authority. |
| Interface Contracts | Define authoritative boundaries between producers and consumers. |
| Validation Documentation | Records validation methods, evidence, scope, and results. |
| Repository Governance | Governs repository authority, records, and maintenance. |

This list does not change the authority, approval process, ownership, or lifecycle already defined for any class. New document classes must not be introduced merely to reorganize existing information.

## 5. Documentation Anti-Patterns

KRONOS should avoid documents created only to:

- duplicate information already owned by another document;
- record temporary discussions or unresolved chat history;
- satisfy process without reducing material risk;
- maintain personal notes in the authoritative repository;
- justify decisions already recorded in an authoritative source;
- restate another document under a different title; or
- preserve speculative future detail with no current owner or lifecycle.

## 6. Modification Rule

Existing authoritative documents should be updated instead of creating new documents whenever practical.

An update must respect the existing document's authority, ownership, lifecycle, approval requirements, and historical-preservation rules. A new document may be justified when the proposed content has a materially different authoritative purpose or when an established document class requires a separate record.

## 7. Closing Principle

If removing a document would not materially increase project risk, that document probably should not exist.
