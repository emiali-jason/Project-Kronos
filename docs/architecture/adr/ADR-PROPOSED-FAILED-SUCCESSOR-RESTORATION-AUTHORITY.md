# Failed-successor restoration: native admission and child facts

Status: Proposed implementation record for CA exact-source review. The P01–P03 contract is approved by the explicit R3.3 order; this successor's implementation is not approved by this document.

Authority: `KRONOS-RECOVERY-R3.3` and `KRONOS-RECOVERY-R3.3-CONTINUE`. The approved P01–P03 contract has raw SHA-256 `909266eb79f31d7ebb5275fe799b7bc27711bd9e97b13dcd64982804f7b923ab`. Its historical proposed labels remain unchanged in the retained original. The approved R3.2 entry raw source-manifest hash is `28916aba8c1fda6ee592d056bff55aac40472bcfd8f78b48be9907ff9b71ba62`; its compact packet hash is `7db8adf266e16381501cb6fdd77efad1781e68df7cc40a04ab5f5c2243190998`.

## Problem and bounded decision

An exit code, absent receipt, stopped process, or consumed historical V2 claim does not establish that a failed successor never reached READY and completed cleanup. A later launcher must not create a new child while that uncertainty remains. The approved contract requires durable native admission under the existing installation OFD, actual child observations, positive settled-state evidence, and one explicit restoration reservation for an eligible incident.

The native launcher is the sole writer of admission-head transitions. The Python adapter validates selected inputs and returns proposals; it does not write the head. A child writes its own exclusive facts and the unchanged R3.1 consumer writes the exclusive restoration claim. None of those records authenticates Sponsor approval. Selection remains subject to the supervised Sponsor/operator procedure.

The native launcher requires an already initialized, consistent installation head after canonical-image, custody and source admission. This implementation provides no initializer, repair, migration, reset, automatic retry, or production activation command. Missing and uncertain history deny. Historical claims are not scanned into new incidents.

## Observed lifecycle

The original reservation records actual parent and known predecessor identities before shutdown. Shutdown dispatch intent precedes the effect. Retirement requires actual predecessor absence, listener absence and the existing handoff checks. The sole-fork intent is durable before fork. The native parent records the actual child's PID and kernel birth after fork, then opens its dispatch pipe. No future child runtime identity is predeclared.

The child retains its original StartupCapture, pinned evidence, adopted custody, and original absolute ValidationBudget. It validates native provenance, then uses the existing mutually exclusive ordinary/V2/legacy/restoration dispatch. Restoration still uses the actual approved R3.1 consumer and one permanent claim. R3.2 capture correspondence, source/Git and artifact correspondence, actual parent-bundle binding, pre/post-completion revalidation and UTC continuity remain in place.

Composition, completion-entry intent, actual READY/receipt, close-only release and same-owner UX10/WO-13/K5 activation are observed at their existing boundaries. Cleanup observations are recorded before acknowledgement/release. Existing owner methods provide the cleanup ledger, final owner proof, helper disposition, settled semantics and current notification checkpoint; no owner is recreated to fill missing evidence.

Only an actually reaped failed child, complete acknowledged cleanup, positively established pre-completion failure, actual V2 provenance, and validated settled continuity can produce `INCIDENT_OPEN`. Genuine READY is retained as `READY_OUTSIDE_PERMIT`. Ambiguous completion or unavailable continuity remains `UNRESOLVED` or leaves the reserved head blocked. An absent fact is not a successful negative observation.

An explicit later restoration selection is checked against the incident and current settled files. Its deterministic reservation identity binds installation, original attempt and incident, independently of the permit filename or ID. The native reservation is published and read back before the sole fork. Failure, interrupted publication, uncertain fork, claim failure, or subsequent startup failure does not replenish that allowance.

`READY_COMPLETE` requires actual child READY/receipt/release/activation facts plus matching native process, listener, control and runtime observations. Unknown child/helper outcomes retain custody under existing cleanup behavior. PACKAGE_VERIFY remains inert and precedes operational custody. Healthy ordinary reuse retains existing runtime checks and also requires consistent admitted history.

## Internal transport correction

Qualification exposed that `/runtime/status` uses valid JSON insertion order while the native helper envelope requires canonical JSON. Embedding that object directly caused the genuine READY message to be rejected. The native parent now carries the exact observed HTTP body as lowercase hexadecimal in `runtime_json_hex`. The helper retains canonical envelope validation, decodes strict UTF-8 JSON with duplicate-key, BOM and non-finite-value rejection, then performs the unchanged terminal identity/READY checks. It does not canonicalize or rewrite the server's observation to claim a different history. Failed validation is not retried by the readiness poll.

## Scope and limitations

Production edits are confined to the native launcher, legacy bootstrap adapter and browser entry. R3.1 schemas/consumer, release admission, runtime identity/state, native production bindings, server cleanup, and product owners are unchanged. Owning tests and this ADR/interface document are the only additional source paths.

Qualification uses disposable installation roots, anchor and harness ports. Authority/publication/signature records are synthetic. The native image is an actual disposable compiled executable with test-only canonical path/device/inode bindings. Its component entry invokes actual native admission, dispatch, monitoring and terminal functions; it substitutes a synthetic predecessor drain and does not qualify the production Dock entry or a full B→T→R rehearsal. The real predecessor is reaped by one concurrent fixture owner. Native parent and child waits, application outcomes and cooperative/forced test teardown are recorded separately.

No source approval, production build/signing/install, head activation, shutdown, R4 or R5 execution follows from these tests. R5 retains the full native B→T→R rehearsal. Separately approved initialization, real authority selection, production signature/publication and operational prerequisites remain deployment dependencies. The accompanying coverage register and exact-source packet, rather than this document alone, establish the implemented and tested scope.
