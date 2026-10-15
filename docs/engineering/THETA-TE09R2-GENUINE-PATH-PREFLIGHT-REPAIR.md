# Theta TE-09R2 — genuine-path preflight compatibility repair

**Status:** Sponsor-authorized bounded engineering repair candidate, 13 October
2026. No genuine commissioning, production publication or runtime acceptance.
**Authority:** Sponsor TE-09R2 order. ADR-0066/0067 and all target, methodology,
producer, intake, assessment and UX contracts remain unchanged.

## Reproduction and cause

The retained TE-09B policy reproduces exit 78: `PermissionError` from
`tools/theta_trial.py` preflight's `lstat`/no-symlink check against
`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK`. Its Review Pack
deny rule covered the shared ancestors of the two approved Sponsor directories.
The substitute-path TE-09R rehearsal did not exercise these real ancestors.
The blocked evidence under `output/theta-te09b-genuine-trial/support/` is preserved.

## Smallest platform-compatible repair

The policy now emits `file-read-metadata file-read-data` **literal-node**
exceptions for the required ancestors within Review Pack, which for genuine
operation are exactly:

- `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK`
- `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners`

No new subpath read exception, write exception, source-directory wildcard,
credential exception or runtime mode is introduced. Empty ancestor sets emit
no rule; an unfiltered allow operation must never be generated.

An empirical metadata-only policy passed `lstat` but macOS denied
`os.open(..., O_RDONLY | O_DIRECTORY | O_NOFOLLOW)` on both ancestor nodes.
The frozen descriptor-relative store traversal requires these directory opens.
The authorized fallback therefore adds exact-node data-read permission too.
This permits enumeration of the **two ancestor directory nodes** at OS level;
it is not claimed to be metadata-only. It does not permit opening/read data
from their unrelated children. Application path allowlisting and no-follow
traversal still forbid discovery-based authority and foreign inputs. Existing
runtime library/source reads remain necessary; this is not a claim that all
operating-system files are unreadable.

Question outbox write scope, governed no-clobber/fsync publication, read-only
Answer scope, exact expected-filename resolution, Host/Origin admission, path
normalization, no-symlink checks and protected paths/network policy are unchanged.
No store primitives or analytical/source contracts are modified.

## Qualification geometry

`tools/theta_trial_preflight_rehearsal.py` is a bounded stdlib supervisor, not
a collector, new product interface or genuine launcher mode. macOS forbids
nested sandbox-exec, so the OS proof runs separately from the protected pytest
entry point.

1. Run the exact genuine launcher preflight and operational `TrialPaths.validate`
   read-only against actual frozen names under the repaired genuine policy.
2. Open the four exact nodes with no-follow directory descriptors. Do not read
   Sponsor Answer contents or write Sponsor evidence.
3. Prove real SWING/Intraday/Support Charts, Keychains, production, 8948 and 8968
   roots remain denied. Query actual Answer/Question write access without writes.
4. Use the identical policy grammar with disposable Review Pack replacements
   for actual read/write/delete/rename, exact-byte no-clobber publication,
   expected-Answer symlink and foreign-filename attacks.
5. Reject all four same-named symlink directory components under kernel isolation
   using disposable controls; never replace an actual Sponsor ancestor.
6. Start the existing operational child under the genuine-path policy with an
   empty disposable root/inbox/outbox. A test-only exact disposable-outbox write
   exception permits the unchanged path admission; genuine policy rules remain
   present unchanged. No originals manifest, chart transfer, Question operation
   or Answer import is supplied. Real-clock/nonqualification authority and
   methodology admission must succeed. Repeated GET is inert after empty-store
   initialization. Stop the child and retain zero-call shutdown evidence.
7. Check protected directory inventories and blocked-root hashes remain exact.

Focused pytest additionally proves exact exception scope, no unfiltered rule,
normalized/frozen paths and four symlink ancestry rejections. Existing TE-09R,
Theta/Browser isolation and relevant shared admission/maintenance regressions
run through `tools/kronos_test.py`, with production denial unchanged.

## Operation boundary

No enduring 8970 process is launched. Ports 8947/8948/8968 remain untouched.
TE-09B remains blocked historical truth; this repair does not recast it as
success. A separately authorized retry must recheck current-time gates and use
the repaired launcher. **Do not start TE-09B automatically.**

Final exact-source hashes and qualification evidence are retained under
`output/theta-te09r2-closure/`.
