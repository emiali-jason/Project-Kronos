# Swing Native Discovery availability V2

**Status:** Approved for this bounded Phase C correction by Sponsor, 2026-09-22.
**Authority:** Consolidated Phase C availability correction and live requalification.
**Scope:** Prospective Native Discovery results only. Historical V1/V0 records and hashes retain their original meanings.

## Evidence completeness and setup eligibility

A completed Native assessment may be ineligible without being unavailable. An affirmative, fully evidenced NSE weekly opposition blocks fresh Probable admission and yields `NO_CURRENT_OPPORTUNITY` with `NSE_WEEKLY_OPPOSING_BLOCKS_FRESH_PROBABLE`. A completed MCX four-hour structural failure yields `NO_CURRENT_OPPORTUNITY` with `FOUR_HOUR_CLOSE_THROUGH_RADIUS2_BASIS`. Neither is a missing-data condition. The constituent weekly, daily, four-hour and one-hour reason codes remain visible, including any independent limitation. An independently missing mandatory fact takes precedence over a negative assessment and remains `UNAVAILABLE`; the weekly veto still remains explicit and still prohibits Probable.

An NSE foundation with fewer than 205 completed governed weeks remains `UNAVAILABLE` and carries `NOT_ELIGIBLE_INSUFFICIENT_WEEKLY_HISTORY` and the exact retained completed/required counts. The 200-week SMA and five-week comparison remain mandatory. Missing confirmed radius-two pivots after bounded completed-history derivation remain `UNAVAILABLE` with exact pivot counts and `DAILY_REQUIRED_FACTS_UNAVAILABLE` or `FOUR_HOUR_REQUIRED_PIVOTS_UNAVAILABLE`. Neither condition may become a valid negative merely by renaming the status.

Prospective Daily and four-hour structural measurements use up to the latest 60 completed, exactly bound bars. Pivot confirmation still requires both trailing bars of radius two, strict unique extremes and two confirmed highs and lows. The 60-bar bound is fixed for the affected factual timeframes across the entire universe, independent of direction, score, or resulting classification. It never stitches contracts, admits future bars, changes moving-average periods, or changes market-calendar completion.

The reference lookup maps only Swing `BANK NIFTY` to the calendar applicability subject `BANKNIFTY` at that boundary. The published Swing instrument identity and reference-fact identity remain `BANK NIFTY`. It does not alter the calendar, NIFTY mapping, session rules or Intraday consumers.

## Version and historical dispatch

Prospective native run schema `KRONOS-NATIVE-MTF-DISCOVERY-RUN-V2`, policy `SWING-V1-KRONOS-NATIVE-MTF-DISCOVERY-V1` version `1` are separate from historical schema `KRONOS-NATIVE-MTF-DISCOVERY-RUN-V1`, policy `SWING-V1-KRONOS-NATIVE-MTF-DISCOVERY-V0` version `0`. The exact schema/policy tuple is required for load and publication validation. Unknown, partial and mixed tuples fail closed. Historical V1 bytes, result hashes and readers are unchanged. The new assessment remains discovery-only, with no readiness, trade, Risk, Sponsor or execution authority.
