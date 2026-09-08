# SPH legacy bootstrap — package qualification and future deployment procedure

This is an engineering candidate under ADR-0031. **Do not execute the installation or migration steps without a separate Sponsor deployment authorization.** No current production plan/proof is created by qualification.

## Package creation and identities

`tools/macos/package_launcher.py` builds into an exclusive output directory outside the repository. Inputs are the exact C source, repository Info.plist, repository PNG/ICNS resources and the package procedure itself. The existing tracked raw executable remains unchanged: it is a recorded previous-source artifact, not the new deployable package. Build the candidate directly from C; do not install the old unsealed tracked bundle.

Compiler: `/usr/bin/clang -Wall -Wextra -Werror -O2 -mmacosx-version-min=13.0`. The procedure records compiler version, current source revision/state, source SHA-256, previous tracked binary SHA-256, newly built binary SHA-256, signed binary SHA-256, procedure SHA-256 and exact file/mode/hash manifest. A dirty engineering checkout is explicitly `DIRTY_WORKTREE`, never a qualified clean runtime revision. After source publication, bind the installation plan to that actual published revision and the reviewed source/resource/procedure hashes; regenerate/verify the artifact if any build input changes.

Bundle structure: `KRONOS.app/Contents/Info.plist`, `MacOS/KRONOS`, `Resources/KRONOS.icns`, `Resources/KRONOS.png`, `_CodeSignature/CodeResources`. Info.plist uses executable KRONOS, APPL, `com.project-kronos.browser-v1`, icon KRONOS. Repository icon bytes differ from the previously installed app; their exact new resource hashes are explicit package inputs, not silently described as unchanged installed resources.

Directories/executable use 0755; regular resources 0644. The local account owns the bundle. Set content/permissions first, then sign the complete outer bundle using `/usr/bin/codesign --force --sign - --timestamp=none KRONOS.app`. Ad-hoc identity, no entitlements requested, resources sealed. Strict verification is `/usr/bin/codesign --verify --strict --verbose=2 KRONOS.app`; no flags weakening verification are permitted.

The signed executable is tested with only `KRONOS_LAUNCH_MODE=PACKAGE_VERIFY`; it returns `KRONOS_LAUNCHER_PACKAGE_V1_OK` before filesystem discovery, sockets, Python, Browser or runtime actions. This proves isolated execution of the signed binary. It does not claim LaunchServices/Gatekeeper/notarized distribution acceptance or perform a production startup.

The external `manifest.json` records the signed manifest identity and archive SHA-256. The ZIP uses sorted entries, fixed timestamps, fixed permissions and no compression ambiguity. Two independent builds measure binary/bundle/archive equality. Do not infer deterministic signing from the procedure: publish the measured equality results and compiler/toolchain used. A package manifest is not its own authority; Sponsor-approved hashes must be supplied independently at deployment.

## Installation — future separate authorization

1. Recheck the clean published repository and exact installed runtime. Inventory production evidence and retain installed bundle identity/signature. Do not use an updated filesystem HEAD as proof of the legacy loaded revision.
2. Verify the approved archive hash, safely stage its known app contents, verify each manifest entry and strict code signature. Use the separately approved bundle identity. No arbitrary archive path extraction is part of this implementation.
3. Verify `/Applications/KRONOS.app` against its independently recorded current identity/signature. Retain a byte-identical, strictly verified rollback app/archive outside the destination before modifying the installed app. Existing installed resources must be retained exactly in rollback.
4. `package_launcher.install(...)` prepares a verified sibling staging directory on the destination filesystem. It uses macOS `renamex_np(RENAME_SWAP)` to atomically exchange the two full app directories, rechecks installed identity/signature, and retains both rollback and exchanged original. The runtime is not stopped. No executable or Browser is launched.
5. Verification failure before exchange leaves installed bytes unchanged. Post-exchange validation failure exchanges the exact original directory back and re-verifies it. If the operating system refuses rollback itself, preserve both directories and report an explicit installation failure; never start/restart a runtime to compensate. Concurrent external modifications require stopping the procedure and reconciling identities.
6. Final ownership must be the current account (UID verified), bundle directories/executable 0755, resources 0644. Retain the rollback app and its original package identity until the separately approved post-migration review.

Engineering tests exercise this using temporary app copies only. Real installation remains zero.

## Future migration plan and sequence

`tools/kronos_legacy_bootstrap.py --plan <approved-json>` without `--execute` performs no HTTP or production operation. The future execution plan has exactly `binding`, `launcher`, `bundle_identity`, `authorization_reference`; binding is the ADR-0031 closed LegacyBinding record. It contains no shutdown token or Provider credentials. The reviewed replacement revision must contain this candidate and be clean/published. The installed launcher field identifies the verified corrected app; its executable hash is part of the binding.

After installation is separately authorized and verified, migration may be independently authorized via `--execute`. The coordinator rechecks repository/unique launcher discovery, private control-file digest, exact frozen old runtime/listener and observable operation states. It creates and validates the one-use context in the fixed private runtime `legacy-bootstrap-v1` directory **before** allowing the existing token-bound legacy shutdown request. No normal SPH handoff is forged.

On one successful shutdown, old PID must disappear and port 8947 become free within the existing bound. The coordinator marks stopped, re-verifies the installed package, and invokes its bootstrap mode with an allow-listed environment and fresh migration proof only. The replacement validates clean frozen source/repository/process identity and chronology, consumes the migration once, then composes under the existing maintenance guard. The launcher returns without opening the Browser. No kill fallback, retry, reissue or automatic exit exists.

Read-only post-start status must establish the exact new listener/PID/runtime/configuration, consumed migration and ACTIVE maintenance guard. Provider must be disconnected and controls non-operational. Verify evidence inventories at distinct boundaries: before legacy shutdown, after old PID stopped, and after guarded replacement startup. Retain/classify old disconnect/monitoring effects separately from new-process writes. Preserve concurrent unattributed additions. A status-only success is not final zero-write acceptance.

Stop after guarded replacement proof. END MAINTENANCE is a separate explicit action and creates no Provider calls. Provider connection is another separately attributable action. WO-06H runtime/window acceptance can only follow its own gate; this coordinator never invokes it.

## Recovery and decommissioning

Before shutdown, failed preparation leaves the old runtime untouched. After shutdown, failed/expired startup remains stopped; no automatic retry. The permanent reservation/consumed marker is not purgeable operational research evidence. Retain it to render this deployment's bootstrap path unusable. Subsequent normal restarts must use SPH-003, with its own process-owned handoff and controlled-notification semantics. Removing the one-time code later requires a separate source review; do not remove the marker while it remains shipped.

Qualification must include focused migration/package cases, existing SPH/Provider/Browser/Swing/UX10/launcher tests, WO-06H/runtime/Intraday preservation, complete active repository suite, syntax, strict C build, signing, changed-scope secret scan and baseline evidence hashes. Engineering reports record actual counts and artifacts rather than declaring runtime acceptance.
