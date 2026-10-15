# Theta combined Astra Answer intake — TE-04B

**Status:** Sponsor-authorized isolated engineering candidate, 12 October 2026.
**Owner:** EA-Theta Earners. No production publication or runtime activation.
**Authority:** Sponsor TE-04B order and supplied sections 33–49.

## Frozen dependencies and scope

Consumes the qualified TE-04A Question/Answer 3.0.0, combined Answer 1.0.0 and
Question batch transport 2.0.0 without modifying their schema or validators.
TE-03A remains frozen under CA review `KRONOS-CA-TE03A-20261012`, canonical
current hash `bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d`.
Genuine methodology remains NOT_ESTABLISHED. Synthetic rehearsal is not genuine
commissioning, methodology approval or evidence of forecast quality.

No TE-05 assessment, Browser Import button, Outlook publication, Detail redesign,
watcher, scheduling, network/Provider call, broker operation or shared coordinator.
V1/V2 readers, original records, selection behavior and runtime composition remain
unchanged. V3 uses separate product-local record families within ThetaStore.

## Application operation and trusted upstream seams

`CombinedAnswerIntake(workflow, current_authorities=...)` provides:

- `import_combined_astra_answer(question_batch_id)` — explicit local intake;
- `restore_import(attempt_id)` — exact committed graph restoration/read;
- `accepted_evidence(receipt_id)` — original package/child bytes and receipt.

The sole expected inbox filename is `<question_batch_id>_ANSWERS.json`, where
the ID is an exact retained `TEB-<64 lowercase hex>` identity. No caller-supplied
file path, directory enumeration, mtime priority or commodity-name discovery.
The inherited default inbox is the Sponsor-frozen
`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/CHATGPT ANSWERS`.
Tests supply only isolated disposable paths; this slice does not access the real
inbox, production evidence or Sponsor sandbox.

`retain_question_batch(batch, questions)` retains exact producer-supplied V3
Questions and their batch after contract and original chart/revision/cycle graph
verification. It does not construct/upgrade/commission Questions or select them.
`select_question_batch(batch_id)` is an explicit trusted upstream selection seam,
not an import side effect or Sponsor UI. It verifies current chart and owner
bindings and uses existing atomic selection/history with separate V3 keys.
Neither method is exposed to Analyst input. Structural retention cannot confer
owner or methodology authority. Actual V3 producer/runtime orchestration remains
separately gated; no genuine producer is commissioned here.

`current_authorities(subject, now)` must be a read-only trusted projection of
the applicable methodology and target-authority descriptors. There is no default
inference from the historical Question. Missing/unavailable/mismatched owner
projection makes evidence noncurrent. It neither acquires nor enrolls authority.

## Safe snapshot and raw representation

Read through no-follow directory/file descriptors; reject traversal, symlinked
components, nonregular files, hardlinks, empty/oversized input and unstable reads.
Two bounded reads and before/after/named-file identity/stat comparison detect
observed in-progress writes/replacement. Stat times are stability checks only,
never discovery, recency or analytical authority. Frozen TE-04A limits apply.

The entire original file is stored and read back before parsing/canonicalization.
Bounded malformed inputs remain original rejection evidence, never accepted
analysis. Oversized/unreadable inputs produce a bounded operation rejection, not
a claim that all inaccessible bytes were retained. Sponsor files are never moved,
rewritten or deleted.

The frozen bounded parser supplies exact UTF-8 child-value bytes, raw SHA-256,
canonical SHA-256 and end-exclusive byte offsets. Each valid-wrapper child raw
span is retained, including rejected children as rejection evidence. Canonical
package SHA exists for parseable JSON; malformed JSON has no invented canonical
hash. Source truth, Analyst authorship and secrecy of arbitrary free text are
not independently certified by structural acceptance.

No local reader can prove that a writer will not modify a valid complete snapshot
in the future. Sponsor should finish the file before invoking import (atomic
rename into the expected filename is suitable). Later changed bytes are a new
attempt, never silently substituted for a retained original.

## Validation, receipts and evidence commit

The unchanged V3 validator rejects invalid wrapper identity/topology globally.
With a valid wrapper, child structural/semantic failure is commodity-local.
Typed V3 reasons are preserved without raw-value echo or exception traces.

An immutable import intent fixes the truthful receipt time and exact batch/raw
hash. Whole original, child spans, acceptance receipts, immutable identity claims
and bounded rejection records precede the final import commit. Only that final
commit completes acceptance. No receipt is exposed as accepted without its
complete integrity-valid origin graph. Failed sibling *validation* permits
independent valid acceptance; interrupted *storage* does not fabricate a completed
package. Prepared but uncommitted artifacts are not accepted evidence.

Each content-addressed receipt binds package/attempt/batch/Question/subject/Answer,
whole raw and canonical hashes, child raw and canonical hashes, offsets, Question
hash, complete chart/Macro/methodology/target bindings, T0, acceptance time and
validation contract/version. These are KRONOS integrity facts, not an Astra
self-hash. Original bytes and receipt timestamps are never regenerated on read.

Retained primitives provide cross-process locking, no-clobber publication,
no-follow paths, fsync and readback. V3 records do not enter legacy `accepted` or
analytical/outcome namespaces. Immutable import commits and rejection records are
history; no directory-order fallback or latest-file current selection exists.

## Replay, conflict and recovery

Exact package replay validates the retained graph at its ORIGINAL receipt time,
returns REPLAY, and never changes selection, timestamps or T0. An identical child
in another valid package reuses its original receipt and original package offsets.
The new package retains its own complete original bytes and parser-derived spans.

Same package identity with different raw bytes fails closed, even if canonical
JSON is equal. Same Answer identity with different bytes/bindings is child-local
conflict. One Question's accepted Answer cannot be silently replaced by another
Answer identity, preserving the retained single-acceptance-per-Question pattern.
Correcting a rejected package requires a new package identity; four valid children
may replay while a previously rejected fifth child is newly accepted. Older
commodity Answers never fill rejected slots in a new package.

Interrupted intent without a final commit is typed INCOMPLETE; restart/replay does
not repair it by inference. Corrupt/missing raw bytes, receipt, identity claim or
rejection dependency fails restoration closed. A crash after the durable commit
but before acknowledgement can be recognized as exact replay with its original
timestamp. Earlier intact imports remain intact. No automatic cleanup/recovery
or deletion policy is introduced.

## Versioned application result

`KRONOS-THETA-COMBINED-INTAKE-V1 / 1.0.0` returns:

- `question_batch_id`, `answer_package_id`, `attempt_id`;
- `package_status`: COMPLETE / PARTIAL / REJECTED / REPLAY;
- `original_package_status`, retaining the original outcome on exact replay;
- bounded `reason` or null;
- exactly five `children`, each with `status`, `reason`, `question_id`,
  `answer_id`, `receipt_id`, and `currentness`.

Child status: ACCEPTED / REJECTED / REPLAY / STALE. Currentness is separate:
CURRENT / HISTORICAL / STALE / SUPERSEDED. STALE status denotes structurally
accepted but noncurrent evidence; the receipt remains available. Exact replay
uses REPLAY status alongside its honest currentness, never resurrecting it.
Five structurally valid accepted/replayed children are COMPLETE (all already
accepted may be REPLAY); 1–4 are PARTIAL; zero or invalid wrapper is REJECTED.
COMPLETE is evidence completeness, not currentness, quality or trading permission.

Currentness requires explicit selected Question identity plus exact current
cycle/charts/owner descriptors and unexpired targets/authority. Import and GET
never write selection. No newer inbox file can promote old evidence. Result
objects expose no internal filesystem paths or trading consequences.
