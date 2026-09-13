# ADR-0054 — Intraday shared Portfolio and Reports

**Status:** Sponsor/EA authorized bounded engineering; Sponsor/EA candidate review pending. No publication/runtime/production authority in this candidate.

Extends ADR-0053 shared Journal integration without rewriting its historical
future-product statements. Prospective WO-15 Portfolio and WO-16 Reports adapt
the existing shared destinations and shell. They have separate versioned policies
and contracts, one source extraction adapter and one combined engineering gate.

WO-15 owns current entered one-lot PAPER exposure presentation only. WO-16 owns
filtered historical factual reporting/export only. Neither owns lifecycle,
monitoring, opportunity origin or research. WO-12 research remains exclusive.
Journal suppression and Notification dismissal cannot change either projection.

The existing shared Portfolio page has no action authority; no new Sponsor Exit
control is commissioned here. Shared Reports filtering/pagination/export writers
are extended for Intraday. Swing semantics remain unchanged. LIVE stays
uncommissioned, Observation stays non-exposure, NATGAS stays HELD.

Contracts:
- [WO-15 Portfolio](../interfaces/KRONOS-INTRADAY-WO15-PORTFOLIO-V1.md)
- [WO-16 Reports](../interfaces/KRONOS-INTRADAY-WO16-REPORTS-V1.md)

Both must independently pass before one combined candidate may proceed to
separate Sponsor/EA commit, publication and runtime gates. PERF/LAG-01 remains deferred.
