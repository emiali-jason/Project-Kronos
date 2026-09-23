# ADR-0058 — Swing V3 Durable Bulk Answer Import

**Status:** Approved  
**Date:** 2026-09-22  
**Owner:** EA-SWING / Sponsor  
**Decision authority:** ADR-SWING-BULK-IMPORT-01 Sponsor architecture seal

## Context

The Swing V3 Browser previously kept an Answer upload HTTP request open while
extracting the PDF, validating all subjects, committing accepted evidence and
running every candidate's downstream analytical handoff. An eight-candidate
Answer therefore appeared to process for several minutes with only a transient
`PROCESSING` label. Refresh lost that transient presentation, and runtime
restart did not own or resume the unfinished batch as one durable unit.

The immutable Review evidence store already owns request publications,
multi-subject acceptance commits, receipts and downstream attempts. That
authority remains correct and is not replaced by this decision.

## Decision

The Swing application layer owns the durable bulk-import lifecycle through
`SwingBulkImportOwner` and `SwingBulkImportStore` in
`src/kronos/application/swing_bulk_import.py`.

The store authority is:

`~/Library/Application Support/KRONOS/runtime/swing-bulk-import-v1`

Custom isolated Browser compositions use an explicitly supplied temporary root.
These records are runtime/work-control state. They are never accepted analytical
evidence and never reside in immutable evidence or human-facing Review Pack
directories.

The Browser may receive the existing upload action, call durable admission,
return a `303 See Other` acknowledgement carrying the deterministic batch
identity, and query/render the retained status resource. It owns no queue,
worker, acceptance ordering or retry policy.

## Identity and admission

The batch identity is the SHA-256 digest of the canonical tuple:

1. `KRONOS-SWING-V3-BULK-ANSWER-IMPORT-V1`
2. contract version `1.0`
3. exact Review request identity
4. exact Question Pack identity
5. uploaded Answer PDF SHA-256

Admission retains, before acknowledgement, an immutable Answer copy and an
integrity-protected record containing the exact current mutation fence. The
request/Pack pointer is create-once. An identical submission resolves the
existing batch. Different bytes for the same request/Pack fail with
`REVIEW_ANSWER_IDENTITY_CONFLICT` and cannot replace staged or accepted data.

PDF extraction is retained once as immutable runtime-control material. A restart
uses that exact extracted payload and does not repeat extraction.

## State model

Batch states are:

`ADMITTED`, `VALIDATING`, `VALIDATION_FAILED`, `ACCEPTING`, `ACCEPTED`,
`DOWNSTREAM_RUNNING`, `COMPLETED`, `COMPLETED_WITH_FAILURE`, `FAILED`.

Candidate states are:

`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.

Every state change appends a timestamped transition. The retained timing map
covers admission, extraction, validation, atomic acceptance, each candidate and
batch completion. Failures retain bounded governed reason codes and never
incoming payloads, credentials or filesystem locations in Browser output.

## Acceptance and downstream execution

The existing `NativeReviewIntakeWorkflow` remains the evidence authority.
Extraction occurs once. All subject and binding validation completes before the
existing atomic multi-subject acceptance commit becomes visible. No candidate
is shown as accepted while the batch is admitted or validating.

The canonical Browser runtime starts one tracked application worker. It scans
durable incomplete batches, takes a nonblocking advisory lease for one batch and
processes candidates serially. Candidate work identities are deterministic over
the batch, immutable acceptance commit and receipt. Existing immutable
downstream attempts and output restoration provide effectively-once evidence
outcomes across an internal retry.

At startup, `ADMITTED`, `VALIDATING`, `ACCEPTING`, `ACCEPTED` and
`DOWNSTREAM_RUNNING` batches resume from their retained boundary. Completed
candidates are never repeated. A downstream failure remains visible and does
not undo the atomic acceptance or successful siblings. Only the explicit
application retry API may queue that failed candidate again; refresh and startup
do not retry it automatically.

## Browser contract

The Review page displays the durable batch identity, batch state and each
candidate state. The status resource is
`/swing/v1/bulk-import-status?batch=<identity>`. It excludes staged paths,
Answer digests and mutation fences. Refresh reconstructs the same presentation
from retained runtime-control state. Status and Review GETs remain
observational.

## Preservation and boundaries

- The acceptance commit, receipts, structured evidence, V2 promotions and
  downstream attempts remain under their existing owners and schemas.
- Historical Review Pack PDFs are never removed, rotated or replaced by the
  bulk owner.
- `UNATTRIBUTED_PRESENTATION_COPY_REMOVAL` remains an accepted open limitation;
  this decision does not attribute or repair the earlier losses.
- The valid `HARD_GATED` V2 presentation correction remains separate and
  unchanged in authority.
- No Step-31, Trade Window, Sponsor decision, Position, Paper Observation,
  Ignore, Provider or broker authority is added.
- MCX Step-31 remains not commissioned.

## Consequences

The HTTP upload action becomes bounded by durable admission instead of total
downstream time. Candidate progress survives refresh and canonical restart.
The runtime-control store adds a small retained work graph, one tracked worker
and lease files. Any corrupt control record fails closed; it is not inferred or
repaired from loose evidence.

## Validation

Qualification must use isolated stores and cover deterministic admission,
identical and conflicting submissions, extraction once, atomic eight-subject
acceptance, candidate progress, refresh recovery, restart at every incomplete
boundary, single-flight ownership, governed failure/retry, zero duplicate
evidence, protected Swing/Intraday behavior and complete Review Pack
preservation.

