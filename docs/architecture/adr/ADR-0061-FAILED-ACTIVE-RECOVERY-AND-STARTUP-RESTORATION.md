# ADR-0061 — FAILED_ACTIVE recovery and startup restoration

**Status:** Sponsor/EA-authorized bounded engineering; final exact-byte independent,
PCP, EA-Swing and EA-Intraday reviews pending. Release, enrollment, installation
and runtime transition are not authorized by this document.

**Decision provenance:** Sponsor-reported CA recovery, drain/successor-health and
server-result decisions in order `705e27f8-ed46-45f6-8efd-5d7918f891fe`; expanded
engineering in `05d4975f-d5de-43e6-bba9-a2b9bc10586f`; explicit Native preparation
authority decision in `9dfa0c55-5669-4b8c-bf77-bdfe002699e4`.

## Context

An acceptance-incompatible predecessor can lawfully remain FAILED_ACTIVE. Its
incomplete startup must not be confused with evidence that it cannot be retired
safely. Conversely, draining a predecessor does not prove that its successor has
restored required product evidence. ADR-0050 and ADR-0059 retain their separate
health, admission, drain, checkpoint and one-use handoff responsibilities.

Native Review also had only one durable preparation record. Losing that record
could leave the same governed evidence as never preparing Review. Neither an
uninitialized NOT_PREPARED projection nor FileNotFoundError proves either history.

## Recovery permission and safety

Recovery is an explicit, non-default FAILED_ACTIVE_RECOVERY_REPLACEMENT operation.
It requires exact Sponsor authorization bound to predecessor PID/revision/control,
incident, successor revision, package, capability, relation, original window,
validity and one-use attempt. Reserve durably before shutdown dispatch; ambiguous
or repeated use is denied. An environment mode or shutdown token is insufficient.

Complete predecessor restoration health is not required. Exact incident admission,
required durable continuity, disconnected/absent Provider, all-writer accounting,
generation fencing, counted drain, final writes, notification checkpoint, zero-owner
proof, signed V2 handoff, predecessor exit and listener absence remain required.
Missing or corrupt continuity denies recovery. Sampled worker IDLE/COMPLETE is not
durable continuity authority. No fallback kill, alternate launcher or second start.

Successor restoration is the operational health boundary. Existing normal READY
replacement and the 120-second successor readiness deadline remain unchanged.
The original WO06H window remains end-exclusive, without restamping or extension.

## Owner restoration and canonical composition

The Browser retains bounded outcomes at its existing restoration call sites and
exposes an immutable in-process result. It does not reexecute restoration to
manufacture proof. Canonical composition supplies actual Swing outcomes, the WO11
lifecycle owner and the already-prepared WO17 restoration result to startup
completion. Missing required inputs fail closed.

Before submitting success to unchanged connection governance, complete_startup
checks required WO06H, Swing, WO11 and WO17 outcomes, Provider absence and transport
absence. WO11 constructor restoration failure cannot be masked by worker status.
WO17 CORRUPT/failure cannot be masked by an empty position projection. Contractual
NOT_YET_RUN empty estates and deferred disconnected monitoring remain lawful.
Required failure prohibits READY and a successful startup maintenance-exit receipt.

## Native legacy authority decision

No preparation witness plus no positive governed preparation/applicability lineage
is APPLICABILITY_NOT_ESTABLISHED. That state does not itself block startup. It is
not RESTORED, PREPARATION_CONFIRMED or EVIDENCE_COMPLETE. Existing evidence stays
unchanged, and no historical preparation time or witness is reconstructed.

Positive evidence must follow actual dependency contracts. A downstream product
name alone is insufficient: newer receipt-based Review may not depend on the old
Native complete-run preparation record. Where exact governed lineage does require
that record, missing or corrupt requirements block restoration and startup.

## Prospective Native preparation witness

Future successful preparation publishes an immutable exact-run completion witness
through existing evidence-store primitives. It binds preparation schema, source and
requirement identities, publication identity, integrity and completion time under
the owner's existing clock contract. It does not add analytical conclusions.

Required durable preparation precedes completion-witness publication. A failed or
partial preparation cannot publish a valid completion witness. Retry must validate
the exact retained prospective publication state; it cannot backfill legacy history
or overwrite conflicting immutable evidence. Restore never creates witnesses.

Witness corruption, wrong-run binding, incompatible multiplicity, missing required
evidence or changed required evidence fail closed. Valid applicable restoration
permits startup only subject to all other startup gates. Shared startup consumes
the Native owner's explicit applicability/restoration result rather than inferring
it from missing files or presentation status.

## Boundaries and release

No analytical methodology, Provider authority, trading authority, NSE/MCX policy,
shared persistence platform, route or HTTP schema change is commissioned. GET
projections remain inert. This decision adds no production compatibility relation
or acceptance, and does not modify the retained epoch/window.

The final candidate must qualify actual frozen bytes, recompute the successor
capability and prepare any required exact direct-relation update for review.
Independent approval and final owner reviews precede a separate Sponsor release
decision. Candidate qualification is not production recovery acceptance.
