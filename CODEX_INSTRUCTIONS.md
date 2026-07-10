# Project KRONOS Codex Instructions

**Status:** Operational policy for AI-assisted changes
**Date:** 2026-07-10

These instructions govern Codex work in Project KRONOS. They are intentionally short and defer volatile engine status to the canonical documents.

## Read Before Changing Code

Before implementation, read the relevant canonical docs:

- [Engine Status](docs/ENGINE_STATUS.md)
- [Engine Ownership](docs/architecture/ENGINE_OWNERSHIP.md)
- [Architecture Overview](docs/architecture/OVERVIEW.md)
- [Data Flow](docs/architecture/DATA_FLOW.md)
- [Testing Protocol](docs/validation/TESTING.md)
- [Architecture Decision Logs](docs/architecture/ADL-001-Futures-Model.md)

Use [Coding Standards](docs/CodingStandards.md) if a coding-style question is not answered by the current source.

## Architecture Rules

- One engine, one responsibility.
- Preserve frozen contracts.
- Use public outputs between engines wherever possible.
- Adapter exceptions must be narrow, documented, and justified by a missing formal public fact.
- No backward dependency from lower layers into higher layers.
- No changes to frozen logic without explicit bug-fix scope or a declared version change.
- KR-370 owns decision and readiness.
- KR-380 owns execution timing.
- KR-390 owns objective model-trade management.
- KR-400 owns BUY NOW / SELL NOW alert events.
- KR-705 owns trader-facing display only.

## Pine Safety Rules

- TradingView is the final Pine compiler and runtime authority.
- Run `git diff --check` before finishing.
- Confirm symbol and timeframe safety for every market-data change.
- Never allow `UNKNOWN` or an empty placeholder into `request.security()`.
- Keep stateful functions such as `ta.rma`, `ta.ema`, `ta.sma`, `ta.highest`, and `ta.lowest` executing consistently on every bar.
- Use confirmed-bar gates for actionable states, model-trade starts, exits, and alert events.
- Keep boolean assignments on one line whenever practical and Pine-compatible.

## Metadata and Documentation Rules

- Keep comments and metadata truthful.
- Do not invent release versions, build numbers, validation claims, or supported models.
- Product metadata remains unresolved unless an authoritative release decision exists.
- Preserve existing historical decision records unless the task explicitly allows an additive note.
- Documentation should link to canonical registries rather than duplicate volatile tables.

## Completion Report

Every implementation summary should state:

- changed files;
- assumptions;
- compile/runtime risks;
- validation performed;
- validation still required.

For documentation-only tasks, explicitly confirm that Pine code was not modified.
