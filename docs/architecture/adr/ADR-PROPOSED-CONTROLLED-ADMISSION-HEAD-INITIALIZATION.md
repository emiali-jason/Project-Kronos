# Controlled admission-head preparation and persistent admission

Status: Bounded engineering authorized by `KRONOS-S3.04 — IMPLEMENT PREPARE-ONLY INITIALIZATION AND PERSISTENT ADMISSION FENCE`; exact candidate source and operational release remain pending independent CA review.

Contract: revised packet SHA-256 `613937140f201a220808b41aa87cae58f1d945c90e54497d1a1a8507fc0680ae`; contract document SHA-256 `6ccc16ac12fa7184856dd4883387e2a79e8f93a9a7a2563dca0dba6ee9e548ad`. This ADR records that bounded implementation direction, not an implementation approval, human appointment or permission to operate the installation.

## Decision and preserved history

The ordinary native gate still requires initialized admitted history. Add one explicit native `ADMISSION_HEAD_INITIALIZATION` route after actual canonical-image, exclusive-custody and source admission. Python returns read-only proposals and final input revalidation; it never writes the head or an initialization completion disposition. Existing head/phase, permit/reservation and permanent one-use claim schemas remain unchanged. This supplements the existing [restoration implementation record](ADR-PROPOSED-FAILED-SUCCESSOR-RESTORATION-AUTHORITY.md), [ADR-0059](ADR-0059-GENERATION-BOUND-MAINTENANCE-ADMISSION-AND-V2-DRAIN-HANDOFF.md) and the [amended interface](../interfaces/KRONOS-FAILED-SUCCESSOR-RESTORATION-AUTHORITY-V1.md). Historical ADRs are preserved.

Preparation never admits itself. A final success receipt, deleting a blocker or rename cannot prove its own timely fsync completion after process death. A physically complete, parseable head can therefore remain unresolved. The live writer may report only `PREPARED_PENDING_EXACT_ADMISSION_REVIEW`; acknowledgement delivery is not durable completion or admission.

Both production policy defaults are empty: native `approved_initialization_disposition = NULL`, Python R3.1 `INITIALIZATION_DISPOSITION = None`. Every operational reader requires the same exact canonical initialization disposition embedded by a separately approved source/artifact successor. No environment/caller policy, operator instruction alone, local receipt, new invocation or renewed budget can clear this fence. Direct R3.1 pre/post-claim head checks use the shared Python predicate; native independently validates the descriptor, evidence and entire current lineage and synchronizes current required evidence under actual custody. Native/Python result digests must agree. Python stays read-only. Later denial never removes an already-created claim.

A separate resolution may adjudicate the original completion time. It cannot waive required records, current durability, actual custody, helper uncertainty, cleanup, retirement or mode-specific checks. Exact current native file/directory fsync/readback and actual ownership remain necessary before effects. Original late/unproved completion stays late/unproved after separate lineage admission.

## Publication and deadlines

Under the same actual existing anchor OFD and original 120-second absolute pretransition deadline, exclusively create the private journal only on positive absence. Retain the original source/helper ceilings. Publish attempt, head-1 intent, full activation phase and current head, in that order, with complete writes, file fsync, checked close, directory fsync and exact readback. No overwrite/unlink/retry. Existing empty, partial, inconsistent or initialized journal roots deny another preparation.

After publication, perform `initialization-recheck`: validate the same selected inputs/source/artifact, original attempt/deadline and unchanged head/phase, under the same native parent and budget. Recheck actual eligibility/custody and original deadline before acknowledgement. The recheck writes nothing and neither prepares a second attempt nor returns operational admission proof. Late/unknown blocking I/O remains owned; no claim of interruption or timely cleanup is made.

## Existing Release B

`EXISTING_RELEASE_B` is observational enrollment of one specifically authorized existing process, not retirement or cold absence. Require genuine existing capture/loaded-source evidence, actual kernel identity, control/listener correspondence and existing successful release facts. The implementation accepts the existing native capture/success/release format; it never creates historical StartupEvidence or hashes PID/revision as a substitute. No new endpoint is added. If retained B cannot supply this supported evidence, enrollment remains denied. No production inspection or evidence acquisition follows from engineering authority.

An admitted genesis may bind that process distinctly as `enrolled_predecessor`. Only the first exact GOVERNED_REPLACEMENT can use it. Different/disappeared B, missing evidence, cold/legacy/recovery substitutions deny. Existing authenticated fencing, counted drain, genuine signed V2, actual retirement/exit, one fork and READY/receipt/release/activation checks remain required; initialization certifies none of those future events.

## Two separately controlled releases

1. **Preparatory release:** final independently approved source/artifact pair with no admitted descriptor. Separately authorized installation and initialization may prepare evidence; normal admission remains denied. This engineering packet supplies no such artifact or permission.
2. **Admission-pinned T/R releases:** after actual evidence and attributable separate decisions, embed identical exact disposition bytes in the native and Python readers in isolated successors. Obtain exact-source qualification on those final bytes, final combined qualification and actual artifact approval. The original preparation identity, deadline, artifacts and uncertainty remain unchanged. The disposition binds historical preparation bytes, not its own containing future artifact, avoiding a hash cycle.

Earlier default-null engineering qualification and disposable synthetic pin controls do not qualify later real pin changes. Changed pins alter source, Git/tree/capture and launcher artifacts; every final identity must be recomputed and reviewed. S3.03 remains OPEN_EXTERNAL_ACCESS_BLOCKED and may still change final source. No future hashes are guessed.

## Qualification boundaries

Use the unchanged mandatory isolated harness and actual native/head readers, R3.1 consumer, custody and budgets. Disposable path/signature/publication/authority seams remain explicit. Fault injection performs real prefix/short/zero writes, fsync/close errors, actual crashes/death and original-clock expiry. New invocations and independent lock probes observe actual exclusion. Separately compiled pinned controls preserve the original unresolved attempt. Genuine disposable child capture/READY facts qualify the supported enrollment format, not retained production B. Application/helper outcomes precede separate fixture/harness teardown. Full applicable regression, release/sign/install, production initialization and runtime transition remain separately gated.

PRODUCTION_AUTHORITY=NO. SHUTDOWN_GO=NO.
