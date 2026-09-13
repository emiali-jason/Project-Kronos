# ADR-0050 — Clean startup and shared runtime state

**Status:** Sponsor/EA authorized bounded RUNTIME-01 engineering; candidate pending qualification/review. Publication, installation and runtime transition require separate authority.

## Context and root causes

APP-01A verifies the resolved installed executable and its strict signature. It does not qualify its discovered Git checkout. The previous Python launcher retained truthful DIRTY_WORKTREE proof, but proceeded to consume handoff, create runtime control and compose the production server. The protected WO-06H validator correctly rejected that proof. A clean unpublished checkout also lacked a release-admission gate.

WO-06H bind_runtime already invokes exact restoration and, for a current managed epoch, the exact retained compatibility lookup. There is no need to create new acceptance or to call the manual restoration endpoint for an already-restored clean startup. The prior maintenance contract intentionally required a separate manual exit. Its Boolean process authority is sound; Browser HTML injected the exit control only through the Swing-oriented _html helper, while product responses could bypass it. Existing page polling compared Provider, analysis and projection signatures, not maintenance, leaving already-rendered controls stale.

The old /status live_monitoring field describes an explicit diagnostic test, not shared WebSocket transport. REST authentication, hub registrations and observed WebSocket connection state already have distinct owners. Diagnostics lacked one inert aggregate status surface. Switching pages must not be interpreted as evidence of reconnection. Kite authentication errors remain a separate diagnosis.

## Decision

This prospectively supersedes ADR-0030's manual-only maintenance-exit requirement for a verified canonical startup only. The explicit legacy manual exit and exact compatible restoration endpoints remain available and retain their original authority. No protected WO-06H callable, digest policy or research calculation is changed.

The canonical launcher invokes a read-only source preflight before touching the old runtime. It requires the discovered root, develop, clean index/worktree including untracked files under existing Git ignore policy, HEAD equal to origin/develop and a direct origin/develop advertisement, and exact scoped Python bytes including detection of ignored or assume-unchanged Python changes. There is no revision allowlist, cleaning, stash or fallback. Unreachable publication authority fails SOURCE_PROOF_UNAVAILABLE.

The launcher uses one fork whose canonical parent remains alive until readiness; the Python process independently verifies that kernel-reported parent image is the exact canonical executable with strict bundle signature. No environment flag grants production authority. The backend rechecks publication and genuine pinned startup proof before consuming maintenance or creating runtime control. Direct script main is therefore denied. Library construction remains an isolated test/embedding API, not an attestation that an arbitrary Python caller is production-authorized. The threat boundary does not claim protection against the account owner rewriting executable code.

Cold and replacement canonical composition begin held in process maintenance. After existing restoration, startup checks accepted authority where a window exists, restoration failure, Swing V3 restoration error, absence of unexpected Provider capability and absence of unexpected transport. Success writes one RUNTIME_STARTUP_MAINTENANCE_EXIT_V1 record and marks READY / INACTIVE. Failure stays BLOCKED / FAILED_ACTIVE. Launcher readiness requires runtime_ready=true. There is no restart retry or kill fallback.

Disconnected Provider is a lawful successful startup. Persisted monitoring owners stay suspended; existing explicit-authentication restoration owns resubscription and interruption evidence. Startup does not authenticate or reconstruct missed observations. Registry state and last transport interruption are exposed independently of factual tick continuity. Status never starts or repairs owners.

All HTML response paths receive the same process-owned maintenance projection. Existing status polling updates its control; pageshow/focus/visibility restoration obtains an inert /runtime/status snapshot. No new timer is introduced. INACTIVE removes the visible exit label/control even when Provider is disconnected. Cached handoff generation alone is never maintenance authority.

## Contract and boundaries

KRONOS-RUNTIME-01 / 1.0.0 policy and deterministic checksum are published in KRONOS-RUNTIME-STATE/1.0.0 at GET /runtime/status. The existing /status gains runtime_ready and the same maintenance object. KRONOS-SHARED-MONITORING-STATUS/1.0.0 includes session/owner/subscription registry counts, exact instrument scopes, latest factual observation provenance and continuity flags, and last observed transport interruption. Registry ownership is not confirmed exchange subscription acknowledgement or lifecycle continuity authority.

The existing maintenance Boolean and generation are retained; ACTIVE, FAILED_ACTIVE and INACTIVE are derived from that authority plus startup result. No artificial ENTERING/EXITING durable schema is needed for the existing synchronous process operations. Startup failure codes are bounded and do not expose credentials or arbitrary exception strings.

Swing decision, risk, timing, lifecycle, research and owner semantics are unchanged. Intraday WO-06H/07F/09/10/11/12 and NATGAS HELD are unchanged. WO-12 GET/startup remains inert. The acceptance epoch 1.2.0 digest and live-shadow calculation digest must remain byte-identical. This is not WO-13, performance optimization, authentication repair or production acceptance.

## Deployment consequence

The preserved installed launcher still contains its previous double-fork behavior and cannot satisfy the new parent gate. A separately authorized canonical rebuild/install is required before loading this candidate. No historical bundle or ACL is modified in engineering. The running pinned source remains its published WO-12 revision until that separate deployment.

## Inert Provider projection qualification

An operational Provider capability getter may synchronize session state, revoke expired leases or acquire a consumer lease. RUNTIME-01 therefore adds a separate Provider-owned read_only_status snapshot and injects it into the Browser compositor. It reports retained lifecycle, known expiry and retained lease count without calling the Provider, refreshing authentication, acquiring/revoking leases or changing shared Provider semantics. Expired observations are projected truthfully without mutating the retained runtime; operational use continues to revalidate normally.
