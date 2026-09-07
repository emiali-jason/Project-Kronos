# WO-05C — Loaded startup source and runtime identity

**Status:** Engineering candidate — Sponsor/EA publication review pending.

Authority: Sponsor WO-05C work order and bounded shared-launcher authorization.
This record implements the current WO-01 manifest's runtime-source proof item.
WO-05A and WO-05B remain unchanged analytical/operation authorities. WO-05D
retains controlled production acceptance and final WO-05 closure.

## Existing deficiency

The shared Python launcher imported application code before composition. Neither
its static package version nor the current checkout HEAD proved what the process
loaded. V2 operation provenance retained a PID label, which was not a durable
process-instance or loaded-build identity. Existing private restart tokens are
shutdown authority, not public source evidence, and must never be exported.

## Startup source boundary

The only changed shared production file is `tools/kronos_browser.py`. It creates
an Intraday-owned `StartupCapture` before application imports. The helper imports
only standard-library modules. It snapshots local KRONOS/tools Python source
bytes, source revision, branch, source state, UTC startup-boundary time, PID and
an independent random process nonce. It checks source blobs against the Git tree
before certifying clean source. A changed checkout during snapshot collection
fails closed to unavailable proof.

An instance-owned import finder compiles the captured bytes for the launcher's local
application imports, avoiding later checkout reads and stale bytecode. Namespace
packages contain no executable source and are handled separately. The launcher
retains the frozen source mapping for later local imports, so startup composition
and lazy imports cannot mix a newer checkout into the captured local modules.
The finder is removed if initial imports fail. Normal shared Provider and
Swing composition remain unchanged. No Provider calls are added.

The frozen startup evidence includes the source-snapshot digest and exact imported
module source digests. A checkout that advances A → B after capture cannot alter
those imported A bytes or change the evidence to B. A fresh process captures and
loads B. Preloaded application modules cannot be retroactively certified; this
includes test/embedded entry paths that loaded components before this launcher.

The proof scope is explicitly `LAUNCHER_STARTUP_IMPORTS`: local application Python
source loaded through that boundary. It is not a signed OS/process-memory
attestation or a dependency-lock/build-package certificate. Later imports of
modules in the captured source map use those same frozen bytes; newly installed
external modules are outside this proof. Bootstrap/standard library/third-party code is outside
the application-source proof. Python implementation/version is retained separately.
No source-file existence check substitutes for a loaded capability.

## Source and process semantics

- CLEAN_COMMIT: verified clean source snapshot and pinned startup imports; the
  exact loaded commit may be reported.
- DIRTY_WORKTREE: base revision remains visible, but exact-clean loaded commit
  is null. Captured/imported source digests identify the actual candidate bytes.
- REVISION_UNAVAILABLE: unavailable Git metadata, incomplete/preloaded import
  proof, or an inconsistent snapshot; no exact loaded commit is fabricated.

Branch/detached/unavailable state is explicit in status. An unrepresentable
branch name retains the known commit but reports branch state UNAVAILABLE,
never falsely DETACHED. The startup timestamp
means the captured application-loading boundary, not an invented OS birth time.
PID + timestamp + random nonce + content-addressed evidence identity distinguish
process instances, including PID reuse. An inherited foreign-process manifest
cannot label a child process as its parent. No mutable global runtime manifest
or cross-process latest pointer is introduced. The launcher holds one frozen
startup value; each process owns its own value.

## Composition and configuration

Intraday composition carries the startup evidence. The constructed V2 control
seals the runtime manifest using actual service/control instances and loaded
callable implementation digests. It represents current Discovery operation,
WO-05A admission, WO-05B accounting and the current V2 operational control.
Missing components or missing guard/counter wiring are not declared loaded.

Configuration identity is intentionally bounded to the existing non-secret
launcher controls: port and Browser-open choice, under a versioned allowlist.
The digest is deterministic. No credential object, environment dump, token,
cookie, keychain value, authorization header or arbitrary configuration mapping
is serialized. Other configuration and package-build identities are NOT_RETAINED.
No Configuration-domain policy or Provider configuration behavior changes.

## Read-only status and retention

The existing `/control/intraday-discovery/v2/status` API exposes a separate
`runtime_identity` object. It projects the frozen manifest and never reads Git
HEAD to reconstruct loaded identity. It does not change Browser layouts or
shared server/views. Normal operation provenance, historical accounting,
Discovery/Probables identities and market freshness retain their own meaning.

The manifest is versioned, canonically serialized and integrity-checked. It is
retained only in process memory; no new filesystem persistence or historical
runtime rewrite is introduced. Existing/embedded compositions without captured
startup evidence report NOT_RETAINED, not the current checkout revision.

`runtime_accepted` remains NOT_PROVEN. Loaded build proof does not certify fresh
market analysis, runtime operational acceptance or any trading authority.

## Qualification boundary

Deterministic fixtures cover clean/dirty/unavailable metadata, source advancement
before import, old/new process separation, PID reuse, immutable/canonical status,
configuration allowlisting, integrity/tamper rejection, actual/missing composed
capabilities, stale bytecode, namespace loading, and imported-before-capture
rejection. An isolated fresh interpreter checks the real launcher import boundary.
Existing launcher/Swing and WO-05A/WO-05B tests remain non-regression authorities.
Full repository regression is required before publication review.

No production restart, Refresh, live Probables, Question Pack, Answer import,
Provider/OpenAI/broker operation or production evidence mutation is authorized.
No WO-05D, WO-06, WO-10, WO-18, methodology or VWAP implementation is included.
