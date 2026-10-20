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

## TradingView / Pine release-gate applicability

The TradingView compilation and representative-symbol gates above are applied to the affected functionality:

- TradingView compilation remains mandatory when a release changes Pine source or functionality genuinely dependent on executed Pine output.
- TradingView representative-symbol validation remains mandatory when affected functionality genuinely depends on TradingView or Pine behavior. Existing TradingView-dependent workflows retain their applicable validation requirements.
- Both gates are `NOT_APPLICABLE` for an exact release scope only when a documented, source-bound dependency audit and applicable owner review establish that the affected product requires neither TradingView charts nor executed Pine output and that retained TradingView/Pine functionality is unchanged.
- A shared repository, imported Python contract types, historical Pine-derived mathematical definitions or presentation of immutable visual-review history does not independently establish a runtime TradingView/Pine dependency.

Swing WO-08 Local Research qualifies under the completed
`KRONOS-SWING-TRADINGVIEW-DEPENDENCY-AUDIT-20261020` audit: its source chain is
Kite instrument/source data, governed completed candles and Market calendar/session
validation, same-run MTF facts, Native Discovery, committed publication, LOCAL-01
versioned deterministic Python methodology, LOCAL-02 integration, LOCAL-03 retained
recording, LOCAL-04 outcome measurement, WO-12 immutable records and Browser/Excel
reporting. This determination binds the unchanged 20-path Release B manifest
`8beb479071f22f0496e4df03e1f7503a9358b900e051442b8c7162063b5d5766` and patch
`7a20f8f0165609011b582d9ebf17bd5656cedc61bee801d5a37d77039d0f86cc`, with its
attributable EA-Swing and PCP combined-source approvals. For that scope,
`TRADINGVIEW_COMPILE = NOT_APPLICABLE` and
`TRADINGVIEW_REPRESENTATIVE_SYMBOL_TEST = NOT_APPLICABLE`.

Applicable verification instead covers exact Kite instrument/source lineage;
matching Native run, assessment and committed publication; completed
1W/1D/4H/1H facts, calendar/session identities and observation cutoffs; missing/stale
source rejection and final currentness; deterministic versioned results on
representative retained or synthetic NSE cases; immutable originals, no-lookahead
outcome measurement and preserved Review/K4/V2 and shared-runtime boundaries.
No fresh Provider acquisition or TradingView execution is implied.

Sponsor Imran approved this bounded applicability correction on 20 October 2026
under `KRONOS-SWING-RELEASE-POLICY-TV-APPLICABILITY-20261020` and expressly directed
that no additional Chief Architect approval is required for this correction.
No binding provision expressly requiring separate CA approval for this
release-policy clarification was identified; Draft governance proposals are not
promoted into approval requirements. This is a policy-applicability correction,
not an architecture, ownership, analytical or interface change. Any genuinely
applicable approved governance conflict must be reported rather than bypassed.
Every later `NOT_APPLICABLE` determination requires its own exact source-bound
evidence and applicable owner review; this finding and the historical one-release
exception do not automatically transfer to a changed composition.

All other Product Release Gates, release-type and tag controls remain mandatory.
Pine files, Chart Analyst contracts, accepted visual evidence, WO-07F and historical
records remain preserved. This subsection grants no publication, build,
installation, runtime, Provider, broker or trading authority.

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
