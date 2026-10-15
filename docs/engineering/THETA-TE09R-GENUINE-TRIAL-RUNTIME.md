# Theta TE-09R — isolated genuine-trial operational composition

**Status:** Sponsor-authorized bounded operational engineering candidate. Final
qualification is recorded in `output/theta-te09r-closure/`. Not production
publication, a genuine research cycle, or runtime acceptance.
**Authority:** Sponsor TE-09R order, 13 October 2026; ADR-0066, ADR-0067 and the
retained CA-reviewed TE-03A publication remain unchanged.

## Baseline and scope

The complete candidate is retained working-tree bytes plus detached HEAD
`37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3`, not HEAD alone. Local develop is
`943e29a8aa140ec99946986514e9429f2bb06e01`, with merge base
`4c32492228eb871079b2634d5384466d8a9078a2` and 351/2 divergent commits. Remote
develop was observed at `d44b191289da3e6c05b034310267f04fdd084a2f`, five commits
after candidate HEAD. No fetch/ref update, merge, rebase, reset or publication.

TE-09R adds an opt-in operational composition and launcher. It does not change
the producer, contracts, intake, evaluator, store primitives, target selection,
methodology publications, Browser shell or approved Outlook/Detail/New Analysis.

## Runtime and filesystem boundary

Future genuine endpoint: `http://127.0.0.1:8970/theta-earners`.
Future durable root:
`/Users/imranali/Documents/Project-KRONOS/.theta-te01-v1/output/theta-te09b-genuine-trial/`.

- `evidence/`: genuine Theta immutable evidence and current selections.
- `support/home/`: process-local default Browser support/configuration state.
- `support/tmp/`: process-local temporary files.
- `theta-operational.json`: exact operational ownership; not analytical approval.
- `support/operational-<sha256>.sb`: immutable generated kernel-policy bytes.

`tools/theta_trial.py` validates exact genuine paths/port, owned private
directories and no symlink components before startup. macOS kernel isolation is
mandatory and proved by controlled file/network denial before KRONOS imports.
No credential/session environment is inherited; only non-secret process basics.
The child binds Python default-home resolution before application imports,
without reassigning HOME. Browser defaults therefore remain inside support state.
It does not import the test isolation bootstrap or test fixtures.

Kernel policy denies production stores, both retained preview stores, credentials,
other Review Pack paths, external networking and protected runtime connections.
Writes are confined to the isolated root and the exact Question outbox. The
Answer inbox is read-only. Existing no-follow directory primitives attempt mkdir
on existing ancestors; exact-name file-write-create permission alone permits
that behavior without permitting arbitrary child/data/deletion writes there.

The frozen Sponsor directories remain:

- `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/KRONOS QUESTIONS`
- `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners/CHATGPT ANSWERS`

Question publication retains existing no-clobber, fsync/readback and deterministic
identity behavior. Only the selected batch's exact `<TEB-id>_ANSWERS.json` is read;
no inbox scan/latest-file logic. Existing artifacts are never rewritten/deleted.
TE-09R rehearsals substitute disposable directories, never these genuine folders.

## Explicit genuine service admission

`kronos.theta.operational.compose` uses real UTC time and
`qualification_mode=False` in both operational and production-shaped rehearsal
paths. It verifies the exact retained CA review SHA-256
`4c297cde5c09b7c96b57707137ad21c14c0ae94091a9f8b785f9f0194d06dca0`, fixed domain
publication references and current canonical hash
`bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d`.
It independently admits the exact published research/assessment methodologies
and all ten current target inputs before publishing operational ownership.

The unchanged services are V3QuestionProducer, CombinedAnswerIntake,
ThetaAssessmentEngine and ThetaSponsorWorkflow. No runtime flag supplies target
or methodology authority. The default production runtime remains unenrolled.

Only the existing Theta GET/evidence routes and three POST routes are exposed:
`/theta-earners/chart`, `/theta-earners/question`, `/theta-earners/import`.
Shared exact Host/Origin, body limits and maintenance/concurrency admission remain
in place. Unrelated routes/methods and Provider controls fail closed. The isolated
application has a throwing Provider factory and no unrelated lifecycle pulse.

## Six-original admission procedure — future TE-09B only

1. Obtain Sponsor confirmation: “I confirm these six selected TradingView
   composites are the charts I intend to use for this genuine Theta cycle.”
2. Read/verify the six exact selected blob identities in the retained Sponsor
   chart sandbox without changing its selection or originals.
3. Prepare `support/originals-manifest.json` in the approved trial root. This
   operational file contains only `originals`, mapping each exact role to
   `path`, `sha256` and `media_type`. It contains no receipt, cycle, Question,
   Answer, approval flag or fixture clock.
4. Each genuine locator must be the exact hash-named blob under the retained
   sandbox's `populated/evidence/blobs/`. Source paths are admitted read-only as
   six literal files plus traversal directories; other sandbox evidence stays
   denied. No directory discovery or historical selection transfer occurs.
5. A later authorized launch may explicitly supply `--originals-manifest` and
   `--sponsor-confirmed-originals`. These are operational chart-intent inputs,
   not authority to run TE-09B without a Sponsor order.
6. Bounded stable no-follow reads verify original hashes/media and reject
   symlinks, hardlinks, corruption and extra metadata. All six payloads are
   prevalidated before intake. Existing governed chart intake creates fresh
   truthful receipts with `INTAKE_RECEIPT_NOT_CHART_TIME`; it does not invent
   visible market timestamps or copy qualification receipts.
7. An identical admission retry reuses selected exact originals and timestamps.
   Conflicting existing originals fail closed; deliberate later replacement
   remains the existing card-local governed workflow.

Example manifest entry shape (all six roles required):

```json
{"originals":{"GOLDM":{"path":"<exact retained blob path>","sha256":"<64 hex>","media_type":"image/png"}}}
```

No genuine manifest, real chart transfer or genuine runtime is created in TE-09R.
No Question generation/import happens merely on startup or file appearance.

## Synthetic separation and qualification

Genuine mode is restricted to the exact approved durable root/frozen directories.
Rehearsal launch paths must be disposable, not the genuine root. Ownership binds
mode, paths, candidate and genuine authority descriptors. Unowned populated
stores, copied rehearsal ownership, qualification selections and receipts fail
startup; they are never adopted by inferred directory order or mtime.

The rehearsal uses real authorities and nonqualification mechanics but explicitly
synthetic image pixels/research. Its runtime banner and images/PDF charts say
SYNTHETIC — NOT FOR GENUINE FORECASTING. Transport `synthetic=false` is deliberate
proof of the genuine producer branch, not a claim that controlled test content is
genuine. This evidence remains only in disposable rehearsal/closure artifacts.
Foreign Answers cannot satisfy the isolated store's exact commissioned bindings.
This is prevention of accidental foreign evidence consumption, not independent
certification that arbitrary Analyst prose or chart pixels are truthful.

`tools/theta_trial_rehearsal.py` is a stdlib/Pillow supervisor with no KRONOS
imports. It launches/stops the actual guarded child, uses exact manual HTTP
actions and verifies bytes/receipts/assessments, five Detail projections, inert
GET, real-process restart and replay. Disposable surrogate Review Pack and
credential paths prove OS read/write exception geometry. macOS prohibits nested
sandbox-exec; focused service/HTTP tests run separately inside the existing
tools/kronos_test.py guard. Neither boundary is disabled.

## Preserved boundaries and next operation

Ports 8947, 8948 and 8968 are rejected by the launcher and remain untouched.
No shared source is modified, no trading/Provider/broker/Astra API authority is
created, and the genuine root remains absent. Trial evidence must be retained
after a future authorized genuine run; stopping its process is not evidence
deletion. TE-09B requires separate Sponsor authorization and current chart/MCX
authority checks at commissioning. TE-08/TE-10 are not started.
