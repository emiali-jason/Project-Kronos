# KRONOS Intraday V1 — WO-06H Historical Qualification Reconstruction

**Status:** WO-06H engineering review candidate

**Owner:** KRONOS Intraday

**Authority:** Sponsor/EA WO-06H
**Production Discovery/Probables authority:** NONE

## Purpose and governance boundary

WO-06H establishes a separate, research-only reconstruction contract for asking
what factual qualification evidence for the *current* governed Intraday subject
set would have looked like at an earlier completed session and observation
boundary. It does not backdate the universe publication, claim that the product
was operational historically, or create a historical production Discovery run.

Production remains fail-closed: a production Discovery observation boundary
before `universe.valid_from` returns `PUBLICATION_STALE`. WO-06H adds no stale
override, validity bypass, production-candidate state, Probable, Promotion,
Trade Construction, Risk, Entry Timing, execution eligibility, Sponsor position,
broker state, or notification authority.

## Contract identities

All WO-06H contract versions are `0.1.0`:

| Contract | Identity |
|---|---|
| Reconstruction | `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-RECONSTRUCTION-V0` |
| Historical factual bundle | `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-FACT-BUNDLE-V0` |
| Current-membership research subject set | `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-SUBJECT-SET-V0` |
| Corpus eligibility | `KRONOS-INTRADAY-HISTORICAL-CORPUS-ELIGIBILITY-V0` |
| Separate later outcome evidence | `KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OUTCOME-V0` |

Reconstruction identity binds the research contract, current universe identity,
subject-set identity, exact historical session and observation boundary,
canonical reconciliation identity/version, factual bundle and source identities,
qualification contract, hypothesis versions, purpose
`QUALIFICATION_RESEARCH`, provenance, and integrity. It never reuses a
production Discovery run identity.

## Subject-set and historical identity semantics

The collection-driven subject set derives from
`KRONOS-INTRADAY-NATIVE-UNIVERSE-V1 / 1.0.0`; its current count is 98. Records
state `current_membership_used_for_research = true` and
`historical_operational_membership_claim = false`. Provider presence cannot
create membership. Future successor publications can produce different subject
sets without a fixed-98 assumption.

Each subject must resolve through an exact governed historical canonical and
Provider binding. Missing or ambiguous identity fails closed. There is no fuzzy
matching or current-symbol substitution. GOLDM, SILVERM, COPPER, NATGAS and
CRUDE additionally require an explicit historical derivative-contract identity.
No nearest-expiry, front-month, volume, liquidity or OI rule exists.

## Sessions, boundaries and facts

Historical sessions are explicit. `latest`, `newest`, `current`, rolling scans
and directory-order authority are prohibited. DOMAIN-008 supplies the target
schedule and governed previous trading schedule; calendar-day subtraction is
not authoritative.

An explicit governed observation-boundary identity and aware timestamp are
bound into every reconstruction. The model permits multiple exact boundaries
for future comparison without commissioning PRE-MARKET, EARLY SESSION,
MID SESSION, or any other new label. A real operation still requires EA/CA to
identify the governed qualification boundaries it may request; otherwise the
result is `QUALIFICATION_OBSERVATION_BOUNDARY_DECISION_REQUIRED`.

Historical fact bundles require completed 1D, 1H, 15M and 5M facts. Every
qualification input has `available_at <= observation_boundary`. A candle that
is present in today's database but was not complete at that boundary is
rejected. Previous H/L/C, PDH/PDL, Classic Pivots, CPR and Narrow CPR derive
from the DOMAIN-008 previous completed trading session.

`NARROW_CPR_KGS_V0` is unchanged:

```text
P      = (H + L + C) / 3
BC_RAW = (H + L) / 2
TC_RAW = (2 × P) - BC_RAW
NARROW = abs(P - BC_RAW) < 0.001 × C
```

It remains a deterministic factual research observation with no Probable or
direction consequence. Pre-session Narrow CPR availability is not evidence
that later 1H/15M/5M facts were available.

Later factual outcomes use a separate identity and require
`available_at > observation_boundary`. They may retain governed range expansion,
excursion, displacement, time-to-expansion or structural-continuation facts,
but never Entry, fill, quantity, P&L, realised R, Stop, Target or trade outcome.

## Evidence source classes and corpus binding

Reports must preserve three distinct source classes:

- `PRODUCTION_POST_ACTIVATION_DISCOVERY_EVIDENCE`;
- `HISTORICAL_QUALIFICATION_RECONSTRUCTION`; and
- `SYNTHETIC_TEST_FIXTURE`.

WO-06H assigns no relative evidentiary weight. Exact reconstructions may reach
`ELIGIBLE_FOR_EXPLICIT_BINDING_REVIEW` only after subject, session, boundary,
source and integrity checks pass. Automatic append to
`KRONOS-INTRADAY-QUALIFICATION-CORPUS-V0` is prohibited.

Persistence uses canonical serialization, explicit type and identity lookup,
atomic retention, idempotent identical writes, conflicting-duplicate rejection
and integrity verification. There is no latest-file lookup.

## Operational acquisition finding

The shared DOMAIN-006 read-only lease exposes historical candles, but the
published runtime has no dedicated Intraday research-only operation that accepts
an explicit session set and avoids production Discovery state. The existing
Intraday Discovery operation enforces production publication validity, as it
must. Real acquisition was therefore not attempted and the current result is:

`HISTORICAL_RESEARCH_OPERATIONAL_SEAM_REQUIRED`.

The smallest later seam is an Intraday-owned application operation that:

1. receives an exact subject-set identity, explicit DOMAIN-008 session and
   observation-boundary identities, explicit `{1D, 1H, 15M, 5M}` timeframes and
   a maximum request count;
2. receives one already-active shared DOMAIN-006 read-only lease through
   composition, with no authentication, retry, automatic expansion or second
   Provider context;
3. resolves exact historical canonical/Provider bindings, including explicit
   MCX contract identities, before any request;
4. returns only immutable WO-06H research artifacts and never calls production
   Discovery, Browser state or corpus append.

Any required shared Provider, Market, Browser, launcher or composition-file
change needs a separate bounded review. An initial 5–10-session NSE corpus is
only a future bootstrap proposal, not a sufficiency threshold or authorization.

## Current evidence and next boundary

Real historical acquisition performed: **NO**.
Historical sessions acquired: **0**.
Real historical observations retained: **0**.
Real evidence sufficiency: **INSUFFICIENT_EVIDENCE**.

Next is EA/CA review of the WO-06H contracts, the explicit observation-boundary
decision, and the bounded operational seam. Do not start WO-06 Part 3, perform
an unreviewed historical acquisition, or bind a reconstruction automatically.
