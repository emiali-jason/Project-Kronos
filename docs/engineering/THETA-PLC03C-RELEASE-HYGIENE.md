# PLC-03C — release hygiene replacement

**Status:** Sponsor-authorized bounded engineering; unpublished replacement.
No publication, canonical source activation, installation or runtime authority.

## Preserved failure and source lineage

PLC-03B commit `c9a169e9fa57cfc53aeb1a5cff37d08f495c8d5d` and tree
`276a75ca803bb12206d05cf7d844115687b0fd93` remain historical failure evidence,
not publication authority. This replacement worktree starts at approved base
`8a3b2baadb186ab840bba2f05c945ec594490a8c`; it must not publish the failed
commit as an ancestor. Original PLC-02 qualification/approval is historical,
not automatic approval of the replacement source.

## Exact evidence transport, not a whitespace exception

The NIST original SHA-256 remains
`25cf0d761b6383d096622600fa27dbce89c986437a06e753375eaf7b105ccdf6`.
Its 90,882 bytes are retained unchanged as the sole `nist-dst-2026.html` member
of `data/market_calendars/mcx_option_expiries/sources/nist-dst-2026.zip`.
The failed commit and original source archive also retain the exact original.
The ZIP reuses KRONOS's fixed-timestamp, exact-member transport pattern; no Git
attributes, whitespace configuration or diagnostic suppression exempts evidence.

The two existing Market publications, current pointers, source URI, logical
filename, retrieval time, source hash, domain review and all analytical facts
remain byte-identical. The source filename remains the original evidence's
logical identity, not a renamed publication or a claim that ZIP bytes are HTML.

`read_dst_source` first supports the existing raw layout using `read_exact`.
Only actual raw absence permits the explicit NIST package representation.
An existing corrupt, inaccessible, symlink or nonregular raw artifact cannot be
masked by a valid package. The package itself is opened through the existing
no-follow/path/bounded reader. Its sole regular, unencrypted member must have the
exact expected name and size bound. CRC/decompression and the original pinned
SHA-256 must pass before any content is used. No extraction, cache, repair,
network operation, path discovery, mtime selection or disk write occurs.

This is representation-only engineering under PLC-03C, not new exchange,
methodology or source authority. A package cannot make altered source bytes
authoritative. Old raw layouts and both retained publication versions remain
supported. Admission still revalidates source bytes every time.

## Formatting and complete-release gate

Only the ten diagnosed formatting issues in the eight identified documentation
and test files are corrected: two trailing-space lines and eight EOF blank-line
findings. Contract text, test ASTs and test behavior are preserved. The before/after
manifest records exact hashes. Separate registry/changelog notes synchronize
the replacement release state without changing engine or product versions.

The complete replacement tree, including additions and the binary package, must
pass `git diff --cached --check` against the approved base using a disposable
qualification index. The real release index is not inferred from a tracked-only
diff. A nonzero result stops qualification; no follow-on commit command is chained.

## Qualification and renewed review

Qualify raw/package target equivalence, original bytes, immutable provenance,
malformed archives, path protection, corruption after load and inert reads.
Run retained Theta plus affected Instrument/Market, Browser and product boundary
regressions under the protected kernel harness. No source publication follows.

Freeze complete replacement source and hashes once qualification converges.
Actual renewed Swing/Intraday dispositions must bind that exact freeze.
Unavailable review remains explicitly pending; earlier PLC-02 approval is not
substituted. Production 8947 and Sponsor sandbox 8948 remain untouched.
