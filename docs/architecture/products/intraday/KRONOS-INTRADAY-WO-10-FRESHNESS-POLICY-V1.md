# WO-10 market and decision freshness

**Status:** Approved engineering policy; WO10_MARKET_AND_DECISION_FRESHNESS_V1.

WO09 NOW: current same session and at most 300 seconds since first_five_of_five_at.
Plan: current same WO09 identity/session and at most 300 seconds since construction.
Quotes and their BBO/depth: exchange timestamps at most 30 seconds old at completion;
future timestamps are rejected. Cross-leg skew at most five seconds. OI and Sponsor
selection: 30 seconds from completed snapshot. No unsupported subsecond Provider
precision is asserted. Complete instrument master must be acquired on the same
trading date. DOMAIN-008 session must be OPEN at acquisition and selection; expiry
must be later than trading date. Store UTC; evaluate session in Asia/Kolkata.

Supersession, stale Risk configuration and expired decision windows fail closed.
Restoration reads history and selections without acquisition, recalculation or
new handoffs. Restored quotes cannot regain executable authority. Reacquisition
requires a new explicit request and immutable comparison.
