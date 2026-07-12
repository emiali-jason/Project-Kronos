# KRONOS Release Policy

**Status:** Approved
**Date:** 2026-07-12

## Product Release Gates

Every product release requires:

- TradingView compile confirmation;
- representative symbol validation;
- a clean `git diff --check` result;
- synchronized documentation;
- synchronized `ENGINE_STATUS.md`;
- synchronized `ENGINE_OWNERSHIP.md`;
- an updated `CHANGELOG.md`;
- recorded known limitations;
- no unresolved critical runtime defects.

## Release Types

### Patch Release

A patch release is a narrow, backward-compatible correction. It must not change architecture or break a public contract.

### Minor Release

A minor release delivers a backward-compatible capability or architectural milestone. Documentation and validation evidence are required.

### Major Release

A major release represents a production-level contract change or an incompatible platform change. It requires:

- formal architecture review;
- migration notes;
- documentation freeze;
- explicit approval before tagging.

## Git Tags

- Release tags use `vMAJOR.MINOR.PATCH`.
- Tag only after validation and documentation are complete.
- Creating or updating documentation does not by itself authorize a tag.
- This governance milestone must not be tagged unless separately instructed.
