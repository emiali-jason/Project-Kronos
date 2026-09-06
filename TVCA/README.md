# TVCA — isolated local core

TVCA is a first-class peer product inside Project-Kronos. WO-TVCA-01A,
implemented under the supplied AD-TVCA-007 approval, provides a headless local
core only. Source and tests are contained in this directory.

`TvcaCore(storage_root)` exposes `create`, `record_identity`, `seal` and
`restore`. Use the exported `IdentityChannel.ADAPTER_OBSERVED` or
`IdentityChannel.VISUALLY_OBSERVED` when recording an observation. Request UUIDs
and timezone-aware timestamps are explicit caller inputs; no credentials,
configuration files, clocks or external clients are loaded.

## Local states and identity

- `OPEN`: a local request may receive its two independent identity strings.
- `SEALED`: no further local revision may be appended. This does not establish
  verification, acquisition, analysis, completeness, readiness or authority.
  Sealing with neither observed identity is valid.

Expected, adapter-observed and visually-observed identity are independent.
Valid strings retain their exact contents. Equality and inequality cause no
reconciliation or trading consequence. Each observed channel can be populated
once; changing an occupied channel is rejected. Each successful transition
populates one absent channel or seals the request, never both.

`CoreRecord`, `RecordRef` and `CoreFailure` are immutable values. Failures are
raised through `TvcaCoreError.failure.code`; they are not persisted and there
is no `FAILED` lifecycle state. The seven codes are `INVALID_INPUT`,
`INVALID_TRANSITION`, `RECORD_NOT_FOUND`, `RECORD_CONFLICT`, `INTEGRITY_FAILURE`,
`STORAGE_ROOT_INVALID` and `STORAGE_IO_FAILURE`.

## Persistence and recovery

Supply an existing absolute directory that is not filesystem root and has no
symlink components. There is no default production location. Records are stored
as `records/<canonical-request-uuid>/<revision>.json`. Identity labels are never
path components. Tests use temporary directories.

JSON is canonical UTF-8, with sorted keys, compact separators, ASCII escaping,
no nonfinite numbers and no trailing newline. UTC timestamps have fixed
microsecond precision and `Z`. SHA-256 covers the complete record bytes without
including its own digest. A record's `.ref` binds request, revision and digest.
Restoration rejects unknown/missing fields, duplicate JSON keys, noncanonical
bytes, invalid transitions, broken chains and digest mismatches.

Publication writes and fsyncs a temporary sibling, creates an exclusive hard
link to the final slot, removes the temporary name and fsyncs directories.
This implementation requires a local filesystem supporting hard links and
directory fsync. There is no replacing-write fallback.

Identical operation replay with the original predecessor, input and timestamp
returns the existing record. Different content in that slot is a conflict.
An I/O failure can occur after publication: it does not prove nothing was
written. Retry the identical operation after storage recovers. Replay retries
the durability steps. Never substitute a new timestamp to resolve uncertainty.

`restore(ref)` restores exactly the requested revision and validates its
predecessors. There is no mutable current/latest pointer or modification-time
fallback. Historical replay returns historical state. Before mutation, the
stored request chain is checked for continuity and valid transitions; it never
selects a replacement predecessor. Abandoned `.tmp-*` artifacts are ignored,
not promoted or treated as recovery evidence.

**One process and one active writer instance per root only.** The lock is
instance-local. Multiple processes or simultaneous writer instances are not
supported. Path checks do not claim safety against hostile concurrent filesystem
mutation. Hashes establish integrity relative to retained references, not
authentication against an actor able to rewrite all records and references.

## Integration boundary

There is no Browser/runtime integration, TradingView/MCP, Pine, Chart Analyst,
Intraday/Swing consumer adapter or broker authority. No root package/build
configuration was changed. The core imports only its own modules and a bounded
set of Python standard-library modules.

## Run local tests

From the isolated worktree, using the existing Python environment read-only:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH=/Users/imranali/Documents/Project-KRONOS/.wo-tvca-01a/TVCA/src \
/Users/imranali/Documents/GitHub/Project-Kronos/.venv/bin/python -B -m pytest \
-p no:cacheprovider -v \
/Users/imranali/Documents/Project-KRONOS/.wo-tvca-01a/TVCA/tests
```

The boundary suite checks all source imports and exercises import, construction,
local lifecycle and restoration in a fresh process that rejects external-service
imports and network/process actions. That subprocess belongs to the test harness;
the product core does not launch processes.
