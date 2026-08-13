# KRONOS V1 Evidence Retention Policy Candidate

- **Policy identity:** `KRONOS-V1-EVIDENCE-RETENTION-POLICY-CANDIDATE`
- **Status:** Candidate
- **Applies to:** KRONOS Swing V1 evidence and validation records
- **Pruning authority:** Manual and explicit only

## Governing Principle

Retention is determined by evidentiary value and lifecycle state, not by one
universal number of days. Retention never grants analytical, TradingView,
Readiness, trade-construction, ranking, or execution authority.

## Retention Classes

### Permanent

- architecture decisions;
- frozen policies;
- MA/CA approvals;
- production baselines;
- milestone validation summaries; and
- explicitly designated reference or audit cases.

### Long-Lived Local

- V0/V1 comparison datasets;
- validation cohorts; and
- evidence needed to reproduce architecture or policy decisions.

Long-lived local evidence must retain observation boundary, policy identity,
provenance, completeness state, and protection from routine cleanup.

### Temporary Local

- routine daily analysis snapshots;
- intermediate calculations;
- diagnostics; and
- routine completed-run evidence not promoted to another retention class.

Temporary does not mean automatically deletable. Pruning remains manual.

### TradingView Evidence

TradingView evidence is retained while validation is unresolved or while an
open LIVE/PAPER thesis depends on it. After validation or thesis closure, the
structured extracted evidence is preserved. An original screenshot becomes
permanent only when explicitly designated as a reference or audit case.

### Google Drive

Google Drive is reserved for compact governance and validation summaries. It
is not bulk storage for raw market datasets or routine screenshots.

## Safety Rule

Nothing supporting any of the following may be automatically pruned:

- an open LIVE trade;
- an open PAPER trade;
- unresolved validation;
- a current architecture or policy decision; or
- a frozen reference case.

Slice 3 creates no deletion job, expiry timer, cleanup scheduler, or automatic
pruning authority.

## Current Storage Audit

| Evidence | Current location | Durability | Git state |
|---|---|---|---|
| Exact same-98 shadow snapshot | `/private/tmp/kronos-shadow-AhOrdC/swing-v1-shadow-snapshot.json` | Host-local temporary path; currently reconstructable but not durable repository storage | Outside Git |
| Same-98 in-memory production result | Immutable `SwingDailyDataset` and V0/V1 comparison objects | Process-only | Not persisted |
| ETERNAL tie reference case | `tests/fixtures/swing/v1/ETERNAL_2026-08-11.json` | Repository-local explicit validation fixture | Git-eligible; uncommitted in this implementation phase |
| Slice-1/2 contracts and tests | `src/kronos/swing/v1/`, `tests/unit/swing/v1/` | Repository-local | Git-eligible; no commit authorized |
| Validation screenshot placeholders | `assets/validation/entries/`, `exits/`, `observations/` | Repository-local placeholders only | `.gitkeep` files tracked |
| Actual validation screenshots | `~/Library/Application Support/KRONOS/evidence/swing-v1/runs/<boundary-date>/<run-hash>/<instrument>/tradingview/` | Durable, run-scoped, atomic append-only revisions | Outside Git |

The preserved same-98 snapshot is 1,786,906 bytes (approximately 1.7 MiB).
No Swing V1 implementation writes raw market datasets or screenshots to Google
Drive. Repository validation guidance permits large screenshots to remain
outside Git and requires stable references when retained.

## Slice-3 Persistence Decision

The bounded runtime root is deterministic and outside Git, Google Drive, and
`/private/tmp`. Each manifest binds run identity, canonical instrument,
observation boundary, chart template/version, required timeframes, probable
assessment identities, retention class, and manual-pruning authority. Uploaded
bytes are preserved unchanged, named by slot/revision, integrity-addressed with
SHA-256, and written atomically. A separate structured-evidence document is
created for later manual or approved extraction.

Before automatic lifecycle handling is proposed, architecture must still approve:

1. retention-class transitions;
2. open LIVE/PAPER and unresolved-validation protection checks;
3. screenshot redaction and sensitive-material controls; and
4. explicit, auditable pruning authorization.
