# WO-07B1 — Fresh Review workspace and producer currentness

Status: Engineering candidate; Sponsor/EA publication review pending.
Authority: Sponsor-frozen WO-07B1 work order and explicit workspace decision.
Owner: Intraday. Trading, Provider and broker authority: none.

## Source and working population

Opportunities/Probables owns current analytical truth. Load Fresh Review is an
explicit Sponsor operation binding the existing immutable Review cycles and
active pointer to one exact current producer generation. Run, result, candidate,
direction, phase, boundary, methodology and source lineage are inherited without
recalculation. There is no filename ordering, historical fallback, automatic
loading, population merge, old chart copying or direction carry-forward.

The operational state is NO_REVIEW_LOADED, CURRENT_REVIEW_LOADED or
REVIEW_NON_CURRENT. Existing detailed currentness vocabulary remains available.
Advancing the producer immediately makes the old workspace non-current. Its
cards and Question/Answer bulk controls disappear from the active projection;
Load Fresh Review is offered instead. No history UI is introduced. A lawful
zero-admission producer can explicitly establish an empty current workspace.

## Publication and concurrency

Preparation retains exact immutable handoffs/cycles. The existing atomic Review
pointer is replaced only after full preparation and a final producer comparison.
A preparation or pointer-write failure leaves the previous truthful pointer;
retained partial immutable components may be reused on explicit retry. Identical
loading reuses the same generation. Conflicting bytes fail closed.

Review applications sharing a store root share workspace serialization. Producer
stores sharing a root share their existing publication lock. In the governed
single-backend process, final workspace publication, chart persistence, Question
Pack creation and each new Answer member commit serialize against producer
publication. Currentness is reloaded inside the guarded boundary. This does not
introduce a multi-process distributed writer protocol or authorize additional
backends. No lock record, new store or startup control file is created.

## Question and Answer boundaries

New Question Packs and charts require the exact current loaded workspace.
NSE and paired MCX paths use the same producer-generation requirement while
retaining their separate existing Question/Answer contracts and visual checks.
Normal Answer acceptance validates exact retained transport, pack, cycle, chart,
candidate and visual evidence, then rechecks producer currentness before each
new member persistence. An identical already-imported Answer is a read-only
idempotent replay even after divergence/replacement. Conflicting replay rejects;
no pointer, revision, evidence or analytical consequence is created by replay.
The inbox file is never deleted because of stale Review state.

Batch start requires currentness. Producer advancement between members rejects
remaining new members with INTRADAY_REVIEW_NOT_CURRENT while preserving earlier
members. The return explicitly identifies PARTIAL_PRODUCER_ADVANCED, including
advancement at the final return boundary. Independent invalid members remain
separately rejected. There is no batch currentization or WO-09 analytics.

## Restoration and historical evidence

Restart follows the existing explicit pointers and validates immutable lineage.
Missing pointer means no loaded workspace; tampered/foreign pointer evidence
fails closed. A stale pointer remains historical and does not auto-currentize.
New loading only replaces the active Review pointer: old cycles, charts, packs,
Answers, direction, provenance and evidence bytes remain untouched. No garbage
collection or retention-policy change is invoked by loading or projection.

## Preservation and qualification

WO-07B chart correspondence, DOMAIN-001 visual identity, DOMAIN-008 sessions,
methodology 2.2.0, Opening behavior, Probables admission, live-shadow semantics,
Review reconciliation, Risk and PAPER/LIVE authority are preserved. Q1–Q10,
paired questions, Answer schemas, PDF presentation and Chart Analyst semantics
are outside this change. WO-07C/D/E/F and WO-09 remain unstarted; there is no
monthly Excel, outcome research, scoring, purge or trading-authority addition.

All tests run through tools/kronos_test.py against temporary stores under the
published isolation guard. Deterministic tests cover state restoration, exact
nine-to-eight replacement, population growth, both directions, empty generation,
idempotency, failures, producer races, same-store concurrency, stale packs/imports,
partial batch restoration and historical byte preservation. The external WO-07B1
evidence pack records focused/affected/full results, frozen hashes, static and
secret checks, before/after production inventories and concurrent additions.
Engineering grants no staging, commit, push, restart or production operation.
