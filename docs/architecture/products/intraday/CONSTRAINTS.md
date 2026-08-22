# Intraday Constraints

**Status:** Living constraint record
**Owner:** KRONOS Intraday

## Approved Constraints

- Native universe is exactly 98 Sponsor subjects in publication 1.0.0.
- Native membership is not execution eligibility.
- Provider, Swing, canonical non-member, and reference-only identities cannot
  enlarge membership.
- Missing canonical/runtime evidence preserves membership and fails closed.
- 1D/1H/15m/5m structural authority uses completed governed candles.

## Compatibility Constraints

Preserve Swing behavior and product isolation. Prefer Intraday adapters and
product routes over repeated shared-file changes. No Pine or OpenAI authority is
implied by Intraday contracts.

## Governance Constraints

Membership changes require a new immutable, effective-dated publication. No
latest-file-wins semantics, silent substitution, Provider-driven identity,
trading predicate, Risk policy, or broker authority may be inferred.

## Governing ADRs

See the Living Architecture Record and Shared-File Change Rule.
