# KRONOS Versioning Policy

**Status:** Approved
**Date:** 2026-07-12

## Semantic Versioning

KRONOS uses Semantic Versioning in `MAJOR.MINOR.PATCH` form. Pre-1.0 versions represent active platform development.

- **MAJOR:** incompatible platform or contract changes.
- **MINOR:** new backward-compatible platform capabilities or architectural milestones.
- **PATCH:** backward-compatible corrections, documentation fixes, and narrowly scoped defects.

## Versioning Dimensions

| Dimension | Meaning |
|---|---|
| Platform version | The maturity of the broader KRONOS platform and its cross-product contracts. |
| Product version | The release version of a specific product, currently KRONOS Core. |
| Individual engine version | The contract and implementation maturity of one numbered engine. |
| Build number | A repository-wide sequential identifier for an approved product milestone. |
| Git commit | An immutable repository snapshot; it may represent work between releases. |
| Git tag | A named pointer to an approved release commit, using the release policy. |

Individual engine versions do not automatically force a product-version change. An engine change affects the product version only when its release impact meets the applicable Semantic Versioning definition and passes release governance.

## Build Numbering

- Build identifiers contain four digits and increase sequentially.
- The build number records repository-wide product milestones.
- It is independent from individual engine versions.
- Build numbers must not be changed casually or reused.

## Current Approved Metadata

| Field | Value |
|---|---|
| Platform | KRONOS |
| Product | KRONOS Core |
| Version | `0.6.0` |
| Build | `0005` |
| Codename | FOUNDATION |
| Status | Active Development |

## Codename Policy

Codenames represent broad development eras. FOUNDATION remains active until KRONOS Core reaches a validated production baseline.

A codename change requires an explicit architectural or release decision.
