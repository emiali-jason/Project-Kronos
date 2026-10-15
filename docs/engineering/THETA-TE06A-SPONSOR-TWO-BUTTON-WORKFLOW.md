# Theta TE-06A — Sponsor two-button workflow candidate

**Status:** Sponsor-authorized isolated engineering candidate, 12 October 2026.
**Owner:** EA-Theta Earners.
**Production/runtime status:** Not deployed or accepted. Production 8947 and the
retained Sponsor sandbox 8948 remain outside this candidate.

## Scope

TE-06A adds one thin `ThetaSponsorWorkflow` application composition and projects
it on `NEW ANALYSIS` as exactly two primary workflow actions:

1. `CREATE THETA QUESTION PACK`
2. `IMPORT ASTRA ANSWERS`

It reuses, without redefining, the TE-04C `V3QuestionProducer`, its TE-04B
`CombinedAnswerIntake`, and the TE-05C `ThetaAssessmentEngine`. The Browser still
uses TE-01/TE-01R chart intake. TE-03A target authority and the exact TE-05B
methodology publication remain explicitly injected dependencies. No default
production enrollment is introduced.

## Create action

The page binds a digest of all six selected chart revisions and exact public
methodology/target inputs. A stale page cannot commission a pack after any of
those inputs changes. The producer then performs the existing full admission,
five independent Question creation, exact PDF/JSON/template/schema/original-chart
transport, no-clobber publication and final currentness check.

The existing default outbox remains the frozen Sponsor directory:

`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`

The combined V3 transport remains one ZIP with five original commodity charts,
one standalone shared Macro original, five self-contained PDFs, one combined
Answer template, its Question-bound schema, generated producer instructions and
the integrity manifest. Identical inputs reuse exact Question identities and T0;
changed inputs produce the existing governed successors.

## Import and assessment action

The import button is bound to the exact current selected `TEB-…` batch. A stale
or noncurrent batch fails before local Answer intake. TE-04B alone resolves the
exact `<batch>_ANSWERS.json`, snapshots original bytes, validates wrapper and five
children independently, commits receipts/rejections, and handles replay/conflict
and currentness. There is no directory watcher or filename discovery.

Only children with a retained receipt, `ACCEPTED`/`REPLAY` status and `CURRENT`
currentness are passed by Answer identity to TE-05C. The Browser application does
not pass raw evidence or policy. E1 and E2 `DOCUMENTED`, `LIMITED` or
`NOT_EVALUABLE` results are shown separately from Answer acceptance. An assessment
exception produces a bounded `NOT_EVALUABLE` operation projection and does not
roll back the already committed TE-04B acceptance.

## Operation status and safety

The coordinator adds no research/evidence store and no runtime coordinator. It
uses a narrow nonblocking in-process button gate in addition to the shared Browser
same-origin/Host, request-size and maintenance/shutdown admission. Underlying
cross-process Theta transactions and immutable/idempotent services remain the
source of evidence safety.

Completed Browser operation results are sealed in the product-local Theta store
and addressed by deterministic `TSO-…` identity. Exact pointers are added to the
existing atomic selection document. Refresh/restart reads only those pointers;
there is no mtime, directory order, scanning, automatic import, reassessment or
new T0. A crash after underlying Answer acceptance but before presentation commit
leaves acceptance intact; an explicit retry becomes TE-04B replay and can publish
the missing presentation record.

## Boundaries

The page retains the subdued-purple visual system, OUTLOOK remains the default,
and chart paste/file replacement remains unchanged. Historical V1/V2 readers and
evidence bytes are unchanged. There is no TE-06B Outlook population, Detail
redesign, outcome research, Provider/Kite access, Astra API, broker/order action,
strategy/strike/lot advice, production deployment, watcher, poller or scheduler.

## Qualification

Focused unit and actual HTTP tests cover complete and 4/5 partial intake,
independent assessment, assessment failure after acceptance, wrapper rejection,
replay, immutable conflict, stale page/batch, chart succession, deterministic
restart restoration, concurrent-button rejection, exact ZIP download, exact two
primary actions, same-origin rejection and zero Provider construction. Final
actual-impact regression and disposable Chrome rehearsal evidence are retained in
`output/theta-te06a-closure/`.
