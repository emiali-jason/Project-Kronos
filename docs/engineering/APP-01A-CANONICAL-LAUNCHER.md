# APP-01A — canonical operational launcher and historical execution containment

Status: Sponsor-authorized engineering candidate; source publication and installed-package replacement require separate authority. No runtime restart is part of this candidate.

## Operational entry boundary

Only the resolved executable `/Applications/KRONOS.app/Contents/MacOS/KRONOS` may enter operational launcher code. The C launcher obtains the actual executable image path through `_NSGetExecutablePath`, resolves that path and the fixed canonical executable, and requires both to equal the canonical literal. A canonical bundle path that is itself redirected outside the location fails. A Finder alias or symlink to the real canonical app introduces no alternative executable authority; an alias/symlink to a noncanonical executable fails.

Before HOME/repository discovery, backend connections, control-file reads, shutdown, migration or startup, the canonical bundle must pass strict/deep codesign verification and the designated identifier requirement `com.project-kronos.browser-v1`. Failed resolution, missing canonical executable, broken seal, wrong identifier or failed verification returns failure without calling operational code. This is local sealed-code verification, not a claim of Developer ID notarization. Release-specific approved hashes remain independently checked by the governed package/deployment procedure; an owner deliberately re-signing modified source does not acquire Sponsor release approval.

The legacy migration coordinator additionally rejects every launcher argument except the absolute canonical bundle before package verification or migration preparation; existing no-symlink checks and separately approved bundle/executable hashes remain in force. No basename, Spotlight, newest-file or alternate-package fallback exists.

The existing `KRONOS_LAUNCH_MODE=PACKAGE_VERIFY` branch prints its fixed package marker and returns immediately. It has no filesystem discovery, socket, control, Python/runtime or Browser path. It is an inert build probe, not an environment-variable grant to start an alternate operational app. There is no environment variable overriding the canonical path. Isolated tests substitute literal paths only in disposable compiled harnesses whose main validates and exits; those harnesses are not deployable operational launchers.

## Preserved historical executables

A source change cannot alter an already-built historical executable. APP-01A therefore also applies a separate macOS filesystem containment boundary to the exact inventoried noncanonical executable inodes: prepend the ACL entry `everyone deny execute` at index zero. This denies direct execution and aliases/hardlinks resolving to the protected inode, while retaining file contents, normal mode bits, resource seals, repository templates and rollback identities. `/Applications/KRONOS.app` is excluded.

The operational evidence pack records each absolute bundle/executable path, precondition SHA-256, inode/device, POSIX mode, prior ACL, applied ACL, timestamp, and effective execute-access result. On this host the inventory comprises 18 existing bundles: one canonical and 17 noncanonical. All 17 receive execution denial; none is deleted, renamed, re-signed or byte-edited. The exchanged installer original remains rollback evidence. LaunchServices de-registration from APP-01 remains supplementary hygiene, not the execution boundary.

This containment persists on the protected inodes across application registration changes. It is not protection against the file owner or an administrator intentionally removing an ACL, replacing the inode or copying bytes while stripping security metadata. Such restoration/copy/install activity must be treated as an explicit deployment change: inventory and reapply containment to retained noncanonical executable copies before making them available. No daemon, auto-repair, purge or broad permission reset is introduced. No claim is made that read-accessible historical machine code is cryptographically incapable of repackaging by its owner.

Reversal is separately authorized restoration work. Verify exact file identity and the recorded ACL, then remove only the recorded execute-deny entry. Do not use `chmod -N`, clear unrelated ACLs or enable all historical copies. If an artifact must become the installed canonical app, use the governed independently verified installation and rollback procedure; do not launch it from its evidence location.

## Qualification and preservation

Tests cover canonical resolved identity and signature, repository/output/qualification/rollback/installer copies, aliases to both valid and invalid destinations, symlinked canonical destinations, missing canonical app, resource tampering, wrong bundle identifier, unsigned executable, actual noncanonical C main, rejected environment override, inert build probe, and kernel ACL denial/reversal with identical bytes and POSIX modes. Existing isolated package tests continue building from the preserved repository resources without executing the historical template.

All automated repository tests run through `tools/kronos_test.py`, which denies real production stores, the installed app and operational network endpoints. No test starts PID 84667, calls a real Provider, or performs a production Review/Refresh operation. Isolated fixtures alone are compiled/signed/tampered/executed. Full regression and exact source hashes are recorded in the candidate evidence pack.

No Intraday/Swing analytical logic, WO-06H acceptance/window, methodology, Narrow CPR, visual question/Answer protocol, trading authority or current installed bundle is changed. Historical ACLs provide current containment; the new source guard becomes an operational defense only after separate publication and installation. Source-template and package resources remain available for lawful build and recovery.
