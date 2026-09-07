# WO-03 / WO-03A — NSE-first operating scope reconciliation

**Status:** Proposed — documentation/presentation clarification candidate for Sponsor/EA review.
**Date:** 2026-09-07.
**Examined revision:** `60d9232127bd4bf6207fa0248f9dff21b92ba58c` on `develop`.
**Publication / runtime activation:** NONE in this work order.

## Decision and implementation boundary

The immediate improvement programme uses `NSE_FIRST_OPERATING_VIEW`: governed
members whose published market family is `NSE_EQUITY` or `NSE_INDEX`. The
verified result is 91 equities plus NIFTY and BANKNIFTY. Membership remains 98.
The five MCX subjects are deferred from this improvement focus, not removed
from KRONOS or declared unavailable.

This is a documentation/presentation clarification, not commissioning a new
93-member producer contract. Existing immutable membership, reconciliation,
per-member factual states and separate Probables diagnostics support the
required distinctions and read-only focus accounting. No new selector service,
Provider capability, analytical engine or shared Platform change is needed to
express this improvement view.

**Runtime limitation is explicit:** `IntradayNativeDiscoveryService.execute`
still iterates the complete governed reconciliation. Its runtime-evaluable
member IDs are prerequisite overrides, not an operating-view selector. This
candidate does not make the next Refresh NSE-only. No historical run is claimed
to have executed under the new focus. A later decision to activate producer
filtering would need an explicit, version-bound run policy and accounting for
members outside that policy; filtering or resealing the existing reconciliation
as a 93-member universe is not a valid shortcut. No such activation is asserted
by this reconciliation.

## Authority and chronology

Controlling scope: the Sponsor's WO-03 / WO-03A reconciliation instruction and
final 6 September improvement programme. The published
[Current Authority Manifest](KRONOS-INTRADAY-CURRENT-AUTHORITY-MANIFEST-V1.json),
entries `03-membership`, `03a-canonical-identity`, `03a-availability` and
`03a-execution-eligibility`, already preserve this separation. WO-01 and WO-02
remain closed; WO-02 factual/temporal validation does not grant admission or
execution authority.

Repository sources read:

- [Native Universe V1](KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md) and its sealed `1.0.0` publication.
- Sealed Canonical/Runtime Reconciliation V1 `1.0.0`; every member joined by its exact membership identity.
- DOMAIN-001 Catalogue V2 `1.2.0` for canonical identity/type verification; reconciliation's historical catalogue binding remains `1.1.0`.
- [Native Discovery V0](KRONOS-INTRADAY-NATIVE-DISCOVERY-V0-CONTRACT.md), [WO-05 runtime](KRONOS-INTRADAY-WO-05-NATIVE-DISCOVERY-RUNTIME.md), and current Discovery / Probables V2 implementations.
- [ADR-0014](../../adr/ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md), DOMAIN-001, DOMAIN-006 and DOMAIN-008 architecture.

External history read without editing:

- [Living Master](https://docs.google.com/document/d/1o5sv4Yukldeqe32bRObgEorKl3PhUwhqV8ZwowpTxmU/edit), including the final 6 September improvement register and WO-02 closure.
- [Programme Master Tracker](https://docs.google.com/document/d/1OpAMKyWE-Fwlh55vO_vMUzDHl1z_9tkdfaJClsI0Kt8/edit).
- [Work Order Diary](https://docs.google.com/document/d/1VDiVB7ttFZM88pZD7vX06b2IOMA_fPa1jG0C1wKeguc/edit).

The Tracker/Diary and early WO-03/WO-05 descriptions of five unavailable MCX
members are historical commissioning observations. They are not permanent
availability policy. The retained September run below proves why the old
93-available/5-unavailable split must not be copied into current accounting.

## Verified membership

Universe: `KRONOS-INTRADAY-NATIVE-UNIVERSE-V1 / 1.0.0`.

All 98 membership identities join the sealed reconciliation in publication
order. All 98 reconciled canonical identities are unique and exist with the
expected semantic kind in the inspected catalogue. No canonical identity is
constructed from a display label or Provider symbol. In particular, RELIANCE's
canonical identity remains `RELIANCE`; `BAJAJ_AUTO` maps to `NSE-EQ-BAJAJ-AUTO`.
The equity with Sponsor label `MCX` is `NSE-EQ-MCX`, not an MCX-market subject.

### Exact 91 NSE equities

| Sponsor label | Governed canonical identity |
| --- | --- |
| ADANIENT | `NSE-EQ-ADANIENT` |
| ADANIGREEN | `NSE-EQ-ADANIGREEN` |
| ADANIPORTS | `NSE-EQ-ADANIPORTS` |
| ALKEM | `NSE-EQ-ALKEM` |
| APOLLOHOSP | `NSE-EQ-APOLLOHOSP` |
| ASIANPAINT | `NSE-EQ-ASIANPAINT` |
| AXISBANK | `NSE-EQ-AXISBANK` |
| BAJAJFINSV | `NSE-EQ-BAJAJFINSV` |
| BAJAJ_AUTO | `NSE-EQ-BAJAJ-AUTO` |
| BAJFINANCE | `NSE-EQ-BAJFINANCE` |
| BDL | `NSE-EQ-BDL` |
| BEL | `NSE-EQ-BEL` |
| BHARATFORG | `NSE-EQ-BHARATFORG` |
| BHARTIARTL | `NSE-EQ-BHARTIARTL` |
| BHEL | `NSE-EQ-BHEL` |
| BPCL | `NSE-EQ-BPCL` |
| BSE | `NSE-EQ-BSE` |
| CANBK | `NSE-EQ-CANBK` |
| CDSL | `NSE-EQ-CDSL` |
| CIPLA | `NSE-EQ-CIPLA` |
| COALINDIA | `NSE-EQ-COALINDIA` |
| COFORGE | `NSE-EQ-COFORGE` |
| CONCOR | `NSE-EQ-CONCOR` |
| CUMMINSIND | `NSE-EQ-CUMMINSIND` |
| DIVISLAB | `NSE-EQ-DIVISLAB` |
| DIXON | `NSE-EQ-DIXON` |
| DRREDDY | `NSE-EQ-DRREDDY` |
| EICHERMOT | `NSE-EQ-EICHERMOT` |
| ETERNAL | `NSE-EQ-ETERNAL` |
| FEDERALBNK | `NSE-EQ-FEDERALBNK` |
| HAL | `NSE-EQ-HAL` |
| HCLTECH | `NSE-EQ-HCLTECH` |
| HDFCAMC | `NSE-EQ-HDFCAMC` |
| HDFCBANK | `NSE-EQ-HDFCBANK` |
| HDFCLIFE | `NSE-EQ-HDFCLIFE` |
| HEROMOTOCO | `NSE-EQ-HEROMOTOCO` |
| HINDALCO | `NSE-EQ-HINDALCO` |
| HINDPETRO | `NSE-EQ-HINDPETRO` |
| HINDUNILVR | `NSE-EQ-HINDUNILVR` |
| ICICIBANK | `NSE-EQ-ICICIBANK` |
| IDEA | `NSE-EQ-IDEA` |
| INDHOTEL | `NSE-EQ-INDHOTEL` |
| INDIANB | `NSE-EQ-INDIANB` |
| INDIGO | `NSE-EQ-INDIGO` |
| INFY | `NSE-EQ-INFY` |
| IOC | `NSE-EQ-IOC` |
| ITC | `NSE-EQ-ITC` |
| JIOFIN | `NSE-EQ-JIOFIN` |
| JUBLFOOD | `NSE-EQ-JUBLFOOD` |
| KAYNES | `NSE-EQ-KAYNES` |
| KOTAKBANK | `NSE-EQ-KOTAKBANK` |
| LICI | `NSE-EQ-LICI` |
| LT | `NSE-EQ-LT` |
| LUPIN | `NSE-EQ-LUPIN` |
| M&M | `NSE-EQ-M&M` |
| MARUTI | `NSE-EQ-MARUTI` |
| MAXHEALTH | `NSE-EQ-MAXHEALTH` |
| MAZDOCK | `NSE-EQ-MAZDOCK` |
| MCX | `NSE-EQ-MCX` |
| MOTHERSON | `NSE-EQ-MOTHERSON` |
| MUTHOOTFIN | `NSE-EQ-MUTHOOTFIN` |
| NAUKRI | `NSE-EQ-NAUKRI` |
| NTPC | `NSE-EQ-NTPC` |
| PAYTM | `NSE-EQ-PAYTM` |
| PERSISTENT | `NSE-EQ-PERSISTENT` |
| PNB | `NSE-EQ-PNB` |
| POLICYBZR | `NSE-EQ-POLICYBZR` |
| POWERGRID | `NSE-EQ-POWERGRID` |
| POWERINDIA | `NSE-EQ-POWERINDIA` |
| RBLBANK | `NSE-EQ-RBLBANK` |
| RECLTD | `NSE-EQ-RECLTD` |
| RELIANCE | `RELIANCE` |
| RVNL | `NSE-EQ-RVNL` |
| SAIL | `NSE-EQ-SAIL` |
| SBICARD | `NSE-EQ-SBICARD` |
| SBIN | `NSE-EQ-SBIN` |
| SHRIRAMFIN | `NSE-EQ-SHRIRAMFIN` |
| SRF | `NSE-EQ-SRF` |
| SUNPHARMA | `NSE-EQ-SUNPHARMA` |
| TATAPOWER | `NSE-EQ-TATAPOWER` |
| TATASTEEL | `NSE-EQ-TATASTEEL` |
| TCS | `NSE-EQ-TCS` |
| TECHM | `NSE-EQ-TECHM` |
| TITAN | `NSE-EQ-TITAN` |
| TMPV | `NSE-EQ-TMPV` |
| TRENT | `NSE-EQ-TRENT` |
| UPL | `NSE-EQ-UPL` |
| VBL | `NSE-EQ-VBL` |
| VEDL | `NSE-EQ-VEDL` |
| WIPRO | `NSE-EQ-WIPRO` |
| YESBANK | `NSE-EQ-YESBANK` |

### Indices and preserved MCX subjects

| Sponsor label | Governed canonical identity | Immediate improvement view |
| --- | --- | --- |
| NIFTY | `NSE-INDEX-NIFTY` | Included; analytical index only |
| BANKNIFTY | `NSE-INDEX-BANKNIFTY` | Included; analytical index only |
| GOLDM | `MCX-SUBJECT-GOLDM` | Deferred; governed membership retained |
| SILVERM | `MCX-SUBJECT-SILVERM` | Deferred; governed membership retained |
| COPPER | `MCX-SUBJECT-COPPER` | Deferred; governed membership retained |
| NATGAS | `MCX-SUBJECT-NATGAS` | Deferred; governed membership retained |
| CRUDE | `MCX-SUBJECT-CRUDE` | Deferred; governed membership retained |

No MCX contract, active derivative binding, native visual relationship,
continuous reference context, paired Question/Answer contract or historical
revision is altered. Reference-market series do not become native members.

## Semantic boundaries

| Concept | Authority / meaning | Does not establish |
| --- | --- | --- |
| Canonical existence | DOMAIN-001 exact published listed instrument or analytical subject | Intraday membership |
| Product membership | Effective Intraday Native Universe publication | Provider availability, admission or tradability |
| Operating focus | Published member market family, selected for the Sponsor improvement programme | New universe, available data or opportunity list |
| Provider availability | DOMAIN-006 factual binding/capability; explicit canonical reconciliation | Membership or active derivative selection policy |
| Market-data availability | Exact run/session/source facts, completed evidence and typed failures; DOMAIN-008 session authority | Analytical sufficiency or admission |
| Analytical eligibility / evaluated population | Sufficient governed evidence under the bound methodology, counted by that stage | Admission |
| Admission / rejection | Governed WO-06 successor methodology and retained member result | Readiness or execution |
| Probables | Current governed analytical candidates, bound to their producer run | Trade Construction, Risk, Entry or broker permission |
| Derivative / F&O eligibility | Separate downstream governed eligibility and contract authority | Implied by cash equity/index membership |
| Trade expression | Separately governed downstream instrument/contract choice | Automatically determined by analytical subject or Provider string |
| Execution eligibility | Separate downstream authority; Discovery retains `NOT_ESTABLISHED` | Granted anywhere in this WO |

NIFTY and BANKNIFTY remain analytical index subjects. Neither index membership
nor analysis creates futures/options eligibility. NSE equity analytical
membership does not require F&O eligibility or an available derivative contract.
No current exchange F&O list is substituted for the governed analytical list.
No lawful trade expression is decided here.

## Focus and Discovery accounting

The conceptual operating chain is:

`governed membership → NSE-first focus → factual availability → evaluated population → admission/rejection → Probables`.

Focus selection uses membership/family only. It must occur independently of
availability. For an offline focus projection of an existing run, join the
selected membership identities to that exact run's member identities and verify
canonical identity and source-run lineage. Never substitute another run's
results, infer results for missing members, or relabel the original run's scope.
Such a projection describes the selected portion of retained evidence; it is
not a newly executed operating run or a new current pointer.

Reuse the existing vocabulary:

| Required quantity | Existing source / interpretation |
| --- | --- |
| Governed membership | `len(publication.members)`; reconciled identity coverage must agree |
| Operating-view count | Count governed `NSE_EQUITY` / `NSE_INDEX` members; independent of result availability |
| Available factual population | Discovery `FACTUALLY_EVALUABLE`; pre-acquisition reconciliation consumability is a separate prerequisite observation |
| Unavailable factual population | Discovery `PREREQUISITE_UNAVAILABLE` and `OTHER_GOVERNED_UNAVAILABLE`, preserving their reasons |
| Failed factual population | Discovery `FACTUAL_FAILURE`, preserving the member and failure reason |
| Not acquired | No generic new state is invented; a prerequisite-unavailable path is not acquired, and a missing run/result is unavailable evidence, not an assumed zero |
| Evaluated population | Stage-specific: Discovery V0 `accounting.evaluated` does not count factual acquisition; Probables V2 `diagnostics.evaluable_count` counts methodology-evaluable results |
| Admitted | Probables V2 `LONG_PROBABLE` + `SHORT_PROBABLE` / `total_probables` |
| Not admitted | Probables V2 `NOT_ADMITTED` / `not_admitted_count`; excludes `UNAVAILABLE` |

A synthetic failure in one NSE/index member leaves 93 focus members: 92
factually available and one factual failure. A missing prerequisite likewise
preserves the member and denominator; it is unavailable, not an admission
rejection. Provider failure never shrinks the universe. Counts from different
stages must not be combined into one denominator equation. Conflicting results
are already represented within methodology accounting, not added again.

The first meaningful opportunity selection is WO-06 admission methodology.
The 93-subject focus is not an opportunity list. No ranking, Top-N, direction,
CPR, volume or VWAP predicate participates in focus selection.

## Retained run read-only reconciliation

Inspected current Probables pointer and exact immutable lineage on 7 September:

- Probables: `INTRADAY-PROBABLES-V2-RUN-8DC2835D0D7A53490F8ABA536B74706858E47F49FDCFB51156DD08D17CF6D372`.
- Source Discovery: `INTRADAY-DISCOVERY-RUN-a8ac322b3465ad9936ee06dd0a0bb62afd01fbc6673d6d4390710a8c3e04c226`.
- Analysis boundary: `2026-09-04T13:47:57+00:00`.

| Quantity | Original complete run | NSE/index portion, audit projection only |
| --- | ---: | ---: |
| Member coverage | 98 | 93 |
| Discovery factually evaluable | 98 | 93 |
| Discovery prerequisite / other unavailable | 0 / 0 | 0 / 0 |
| Discovery factual failures | 0 | 0 |
| Discovery admission evaluated / candidates | 0 / 0 | 0 / 0 |
| Probables V2 evaluable | 97 | 93 |
| Probables V2 unavailable | 1 | 0 |
| Admitted Probables | 9 | 8 |
| Long / short | 3 / 6 | 3 / 5 |
| Not admitted | 88 | 85 |

The focus subset's eight admitted equities are BDL, EICHERMOT, MAXHEALTH, NTPC,
SRF, TATAPOWER, TITAN and TMPV. The original nine-member Probables/Review
population, including CRUDE, is preserved. Eight is an audit subset count, not
a replacement current candidate population. Current runtime/Provider health is
not inferred from this historical analysis boundary.

## Capacity and historical preservation

No `93` capacity rule is introduced. The family predicate has no limit, slice,
Top-N or whitelist of exactly 93 IDs. Membership additions require their own
successor governed publications and canonical evidence.

The legacy Native Universe V1 codec contains `EXPECTED_NATIVE_MEMBER_COUNT = 98`
and rejects different-size V1 publications/resolutions. This existing schema
restriction is disclosed: arbitrary larger publications are not claimed to load
through that codec unchanged. It must not be changed to 93 or advertised as
permanent system capacity. Existing successor-reconciliation tests demonstrate
99-member Discovery accounting; future membership commissioning still needs a
compatible governed universe publication/codec and explicit runtime binding.
No end-to-end 99-member producer activation is claimed here.

Historical 98-member runs retain their identities, denominators, evidence,
universe version and applicable policy. Read-only audit filtering does not
rewrite or persist them. Before/after hashes of all 70,749 files in the inspected
production Intraday evidence root matched during reconciliation. All checks and
new fixture writes use isolated test/output locations; no runtime restart or
currentization is performed.

## Bounded Browser clarification identified

Current `/intraday` `Universe` is sourced from the presented run's
`starting_population`; its cards and Equity/Index versus MCX groups project
retained Probables. It is not a Sponsor improvement-focus selector. The generic
label can obscure that distinction.

The bounded presentation correction is to label that value **Run population**
and display a separate note: **Improvement focus: NSE equities and indices;
MCX improvement deferred. Retained run evidence remains unchanged.** If a focus
count is shown, derive it from governed member families and label it separately
from run availability and admission. Do not hide CRUDE or alter existing cards,
current Review population, selection, ranking or results.

This document identifies that correction as requested by WO-03 section Q.
Browser implementation/desktop/mobile acceptance is not claimed by this
clarification candidate. No Browser or shared route file is changed.

## Qualification and programme gate

Validation on the examined source: 217 membership/identity/Provider-boundary
tests passed; 55 Discovery/application/Probables V2 tests passed; the final
changed runtime test module passed all 10 tests, including two new focus cases.
There are 274 distinct passing tests across these selections. An initial new
test used the execution wrapper instead of its `.run`; that fixture error was
corrected before the final module run. No production defect was inferred from it.
The production read-only audit also verified all 98 canonical identities and
all 93 focus members, and preserved the original run bytes.

A full repository suite was not rerun for this documentation/test-only change:
production Python and Browser source are unchanged. WO-02's 5,211-test full-suite
PASS remains prior qualification, not a fresh WO-03 result. No Browser acceptance
is claimed.

Qualification covers exact commissioned membership/canonical semantics,
non-destructive family selection, unavailable/failure denominator preservation,
98-member historical restoration, 99-member successor accounting, downstream
execution separation and separate Discovery/Probables populations. New bounded
fixture coverage projects a complete synthetic run with one failed NSE member;
it performs no real Provider operation.

No Opening/CPR/1H/15M/5M/NIFTY-context/Probables policy, assessment price/time,
Review/Answer, Readiness, Trade Construction, Risk, Entry, PAPER/LIVE or broker
behavior changes. VWAP remains Sponsor research hypothesis only for WO-06.
No publication approval is asserted by this proposed document.

WO-01 CLOSED; WO-02 CLOSED; WO-03/03A clarification candidate pending EA review.
WO-04 NOT STARTED / NEXT; Statistics HELD; WO-10 revalidation HELD; WO-18 HELD;
BR2 CLOSED_WITH_SPONSOR_INPUT_PENDING; autonomous broker execution NONE.
Complete WO-01 through WO-09, then stop for Sponsor check; WO-10 requires
explicit Sponsor approval.
