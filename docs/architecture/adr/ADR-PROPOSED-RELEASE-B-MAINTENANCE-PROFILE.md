# Ordinary Release B maintenance profile

Status: Settled design recorded for Sponsor-authorized isolated engineering.
CA exact-source review and publication of this record remain pending.
The proposed filename is preserved exactly as authorized for Slice 2.4.
Date: 25 October 2026. Owners: CA / PCP for platform contract; EA-Swing for UX.

## Scope and authority

This records the previously settled Step 1–4 contract, not a new architecture.
The bounded source ceiling is `1b7be60bd37ed5ed456e347c03ada9eef5a37b89e92b8f782662359f1117b328`.
The ordinary successor starts from Release B
`355922f92f7b826191ae86bd7bb0473349f3c1cc` and corrected Slice 2.3
`f3a9b1ef1ab3508b0b56813349fdc2b72af05387cf6ff1cb6fd755e0feb46332`.
Earlier ADRs, FAILED_ACTIVE attempts (including spent October 10), prospective
FAILED_FENCED R3 and original commissioning history are neither replaced nor reused.

## Retained settled contract


### Fixed source admission
One approved repository `emiali-jason/Project-Kronos`, exact origin `git@github.com:emiali-jason/Project-Kronos.git`, local branch `maintenance/release-b-swing-ux`, full remote ref `refs/heads/maintenance/release-b-swing-ux`. Require exact origin/merge/upstream tracking configuration, HEAD/tracking equality, direct authoritative advertisement of the exact full ref, and actual-launch-environment destination checks. Reject additional origin URLs, destination rewrites/overrides, unresolved destination configuration, alternate refs, cached remote authority and caller-selected policy. Preserve all root, clean index/worktree, scoped Python tracked-byte/roster, signature, canonical parent, pinned startup and final-currentness checks. Normal authentication and host-key verification remain effective. No transport is executed for this consolidation.

### Bounded installation applicability
Exact retained installation: `/Applications/KRONOS.app`, bundle ID `com.project-kronos.browser-v1`, repository `/Users/imranali/Documents/GitHub/Project-Kronos`, estate `/Users/imranali/Library/Application Support/KRONOS/runtime`; Release B base above; retained bundle `ed7a77729ff22aea43134b5dfc9dc2cb32e05204c4e66cd9188d8cf78b434a69`; executable `2b3a705f734d40779ef5fc5380fe2fc01179aa93b8b7c7687cfaf750e2909f2c`; history register `9a3afc9d017072d18e025b156fbaadc7f168f91891f5728c0d2d939e4d9ed266`.
The Sponsor-conveyed accepted CA historical reasoning/determination and PCP authoring-owner CONCUR are preserved for this retained installation and prospective FAILED_FENCED R3 boundary. PCP capacity remains AUTHORING_OWNER_ASSESSMENT, not independent review. Sponsor exact factual response: "No recollection." It is not technical never-enrollment evidence. Do not repeat the history investigation. Ordinary V1/V2, September bootstrap and earlier FAILED_ACTIVE records remain historical; October 10 is spent/non-reusable.
Use the existing exact-hash controlled-release approval arrangement: original readable CA decision and PCP attribution are retained as immutable release evidence; the later Sponsor-approved procedure identifies their exact hashes and exact target source/artifact pair. No automatic Markdown approval parser, new certificate system or R3 commissioning. This historical acceptance does not replace fresh installation checks, actual target source/artifact approval, runtime admission or explicit production authority. New actual artifact/anchor identities are populated only when observed under later authority.

### Installation lock and direct backend custody
The existing private runtime directory is the installation anchor. Validate its approved device/inode, owner and safe directory chain, not pathname alone. Nonblocking EX before decisive checks/effects; no automatic retries. The designated backend inherits the same held descriptor across exec, adopts it before StartupCapture and restores close-on-exec immediately before any helper. Validate custody while the kernel-identified canonical parent retains its original EX: correct inherited descriptor, nonblocking EX operation on that descriptor, independent-open conflict, and parent identity/liveness checks, under the source-enforced parent-retention invariant. Metadata/probe alone is not proof. Missing/substituted/reopened/early-closed custody denies.
Each process closes only its own reference; never LOCK_UN. Hold custody through unfinished startup/cleanup. Successful backend release requires completed canonical startup with durable startup completion and READY, no startup failure and no incomplete startup cleanup; returning from complete_startup() alone is insufficient. Parent retains its reference through monitor disposition. Parent loss before validation denies; loss during incomplete startup causes failure/cleanup under surviving custody. Process death closes descriptors but is not cleanup proof. Repository rename/replacement/second checkout cannot select another lock domain. Replacement of the approved installation anchor denies.
Future first R3 provisioning is offline-only and must enforce this same exclusion inside the sole first-write primitive before any estate write, proving complete backend absence while held. No production provisioning entry is authorized now; no execution of the uncorrected RecoveryStore.provision() is authorized. Its future companion source/test work is explicitly excluded from this maintenance implementation, not an automatic release prerequisite. Advisory exclusion covers approved canonical participants; it does not claim to constrain an arbitrary administrator/script.

### Existing CLI validators; bounded failure contract
Retain Git/SSH/codesign and direct remote verification. No library replacement, generic supervisor framework, universal descendant-reaping requirement or new recovery registry.
Approved maximum decision ceilings: one pre-transition aggregate 120 s from before initial validation, including repeated checks; each complete source gate 60 s capped by remainder; native signature/local revision 10 s capped; existing Python calls retain 10/20 s capped; post-retirement handoff verification 10 s capped by remaining freshness and any still-applicable stop deadline; successor READY remains 120 s from immediately before fork. Preserve predecessor drain/stop/freshness limits. Parent enforces its deadline independently; nested work receives only remaining time, with no reset and no late success. Use one explicit monotonic clock domain for passed absolute deadlines; any inability to establish that bound is denial, not a guessed clock conversion.
All native helper children close every admission-lock alias before helper work, callbacks, configuration processing, descendant creation or exec. Pre-close stalled children remain directly owned. Backend sets CLOEXEC before capture, and Python helper launches preserve close_fds=True, no admission pass_fds/preexec callback. Restrict helper environment to the validated transport/authentication context; no unrelated maintenance/control secrets. verify-v2 alone gets its exact required proof via its existing stdin interface. Pipe endpoints are role-specific and all unused ends close.
Native pipe reads/writes and waits become deadline-aware with bounded output, nonblocking I/O and EINTR-safe polling. Before predecessor effects: validation failure/expiry/ambiguity denies all transition effects and leaves predecessor untouched. After retirement: failed/expired handoff or final verification admits no successor, retry or fallback. Backend capture/source failure/expiry blocks consumption, further operational composition and READY. Record the exact phase and directly owned helper outcome.
MANDATORY CA WORDING: An unresolved-cleanup report does NOT discharge ownership. Retain required custody while owned startup/helper work can still act. No claim that process death, direct-child exit, group emptiness or snapshots prove complete descendant termination. Termination/reaping authority is limited to the exact directly owned validation helper; never predecessor/successor/unrelated process or a group fallback. Known surviving/unaccounted helpers remain cleanup-unresolved and confer no provisioning/retry/second-child permission.
Use bounded structured failure results captured in the existing controlled-attempt output/receipt. The current Boolean/alert-only results and discarded backend stderr do not supply this reporting. Absence of a retained failure result is unresolved, not success or zero ownership. No alert/workspace exec may close the last required custodian while work remains actionable. Normal synchronous CLI success keeps its existing ordinary-release meaning; it is not a new descendant-termination certificate.
Use only an entry-local StartupCapture adapter through the existing _git() seam. Preserve capture arguments/byte results/predicates, pinned imports and failure semantics. No global monkeypatch or runtime_identity.py change. If that seam cannot satisfy the contract in implementation, stop at the specific conflict.


## Implemented boundary and pending authority

Slices 2.1–2.3 implement the fixed source policy, installation custody and bounded
helpers in isolated source. Slice 2.3's corrected early-entry boundary includes
adoption, capture and pinned imports; unresolved failure retains existing custody.
Native/Python startup reporting leaves the shared output OFD nonblocking and never
restores stale flags. READY relinquishes the backend's own startup output reference.
No descendant-termination certificate, cleanup clearance or retry follows from a
report or direct-child exit. The eight platform files remain unchanged in Slice 2.4.

Slice 2.4 copies only the selected UX bytes, synchronizes the six documentation
paths and changes the source-policy marker/checksum. The optional FAILED-successor
projection is excluded. Exact qualification belongs to the candidate evidence
package; previous candidate counts are historical. Production anchor binding is
unpopulated/fail closed. No applicability record or operational authority is invented.

No implementation of the future R3 provisioning companion is included. It remains
required before any authorized first R3 provisioning and is not made a UX-release
implementation dependency. No current provisioning execution is authorized.

Independent exact-source review, release-policy reconciliation, fresh actual
source/artifact/applicability checks and separate Sponsor operational authorization
are required before production work. This record grants no publication, build,
installation, provisioning, maintenance, shutdown or runtime authority.
