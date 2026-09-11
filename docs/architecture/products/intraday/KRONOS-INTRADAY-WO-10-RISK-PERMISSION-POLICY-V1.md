# WO-10 Risk permission and sizing

## Current authority — ADR-0042

Status: Approved bounded engineering by direct Sponsor / EA authorization, 2026-09-11.

Historical/superseded prospectively. This permission policy remains only as prior decision evidence. New WO10 records follow the advisory policy and cannot create Risk permission, veto or maximum_permitted_lots. Historical WO14 meaning is not changed.

See [ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) and [advisory Risk policy](KRONOS-INTRADAY-WO-10-ADVISORY-RISK-POLICY-V1.md).

## Preserved predecessor text

**Status:** Approved engineering policy; ADR-0039; version 1.0.0.

No broker margin, funds, buying power, SPAN, collateral or execution capital is
queried, retained as permission, or used in sizing. No default capital, percentage
or lots is supplied. Required current configuration: INR, monetary per-trade Risk
limit, aggregate Risk limit and existing open Risk, source identity, effective
and expiry timestamps. Optional product Risk limit requires existing product Risk
and exact product binding. Optional product/global lot caps apply only if configured.

Risk per lot = absolute mapped Entry minus mapped Stop, times lot size, times
contract multiplier. Reuse the historical factual monetary arithmetic without
reinterpreting old WO14 records. Remaining aggregate/product capacity is bounded
below by zero. Floor minimum applicable monetary capacity / Risk per lot, then
apply configured lot caps. Known zero permitted lots is REJECTED; invalid geometry
or missing/stale/inconsistent inputs is UNAVAILABLE. Positive maximum reduced
below primary per-trade lots by a secondary cap is CONSTRAINED; otherwise APPROVED.
Risk cannot alter contract, readiness, direction, Entry, Stop, Target or invalidation.
