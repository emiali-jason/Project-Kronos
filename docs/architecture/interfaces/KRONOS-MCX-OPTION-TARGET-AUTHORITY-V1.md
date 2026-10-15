# MCX option target authority — TE-03A

Status: Sponsor-authorized isolated engineering candidate, 12 October 2026.
Final Chief Architect domain dispositions are retained separately against the
candidate manifest. This document grants no production publication or runtime
activation. The direct TE-03A continuation order supplies the bounded authority.

## Ownership and consumed publications

DOMAIN-001 Instrument owns `KRONOS-MCX-OPTION-SERIES-PUBLICATION-V1 / 1.0.0`:
exact option-series identity, family, canonical subject, underlying future and
its expiry, quotation units, settlement-reference meaning and exchange-source
provenance. `instrument/option_series.py` loads the exact pinned publication.
It neither calls a Provider nor selects active futures.

DOMAIN-008 Market owns `KRONOS-MCX-OPTION-EXPIRY-PUBLICATION-V1 / 1.0.0`:
option dates, exchange rules, option session endpoints, coverage and calendar
lineage. `market/option_expiry.py` consumes the exact Instrument publication and
the existing 2026 MCX date calendar. It does not invoke the futures expiry
cutoff selector. `market/option_authority.py` composes the two publications via
an explicit current record, without selecting Theta's horizons.

Theta's `OwnerOptionAuthority.resolve` applies only the Sponsor's product rule:
sort eligible owner records by parsed endpoint; return the first two as E1/E2.
The name is retained from the earlier candidate; it is a thin consumer of the
shared publication class, not an additional Instrument or Market fact owner.

## Publication integrity, admission and currentness

The checked-in `2026.2.0` publications are a successor to retained `2026.1.0`
bytes. `current-2026.1.0.json` preserves the prior composition. `current.json`
pins explicit publication filenames, identities, versions and raw SHA-256s.
There is no scanning, mtime, latest-file, symbol or token authority. Each read
rejects path traversal, symlinks, nonregular artifacts and oversized files.
Sources are retained original official MCX PDFs, with exact hashes, circular
identities, retrieval times and effective scope. The Market publication also
pins the retained NIST DST source; NIST supplies DST dates only.

The authority descriptor has `identity`, `version` and `sha256`; the last is
the canonical hash of the exact current composition. Its version is the
Instrument publication version. Every target also binds both domain pins and
the current descriptor. A changed domain publication changes the descriptor
and requires fresh review. The resolver reloads pinned sources and the current
base calendar on every admission; an already loaded object is not a fallback
after source corruption or supersession.

`OptionAuthorityReview` is an explicitly supplied trusted commissioning
dependency. It binds both exact publication references and the current hash,
with separate `APPROVED` Instrument and Market dispositions and a public review
reference. It must be constructed from the authentic retained CA review.
It is not cryptographic authentication of a reviewer. Arbitrary strings in
the predecessor `owner_reviews` field confer no admission. An absent or
incorrectly bound review prevents genuine Question commissioning.

This is a bounded offline publication, not a live MCX amendment monitor.
New exchange amendments require a reviewed successor and explicit pointer
change. Calendar/source mismatch fails closed. It cannot prove absence of a
subsequent exchange amendment without a newly qualified publication.

## Coverage and source semantics

Instrument rows cover August through November 2026 for GOLDM and SILVERM;
COPPER, CRUDEOIL and NATURALGAS additionally cover December 2026. The successor
contains 23 explicit series; no resolver branch hardcodes October/November.
The publication becomes available at the retained evidence boundary on
12 October 2026. Earlier rows are historical coverage, not permission to
backdate commissioning before the source boundary.

GOLDM uses explicit exchange option dates and underlying-month relationships.
Its December option requires a January 2027 future endpoint unsupported by the
retained calendar; it is not fabricated. SILVERM's retained launch tables end
in November 2026. Monthly September/October options map to the same November
future as the bi-monthly November option. No one-option-per-future restriction
is imposed.

COPPER and bi-monthly SILVERM use three business days before the first day of
the underlying's three-business-day tender period. Monthly SILVERM uses its
fourth-last-business-day rule and Friday/day-before-holiday adjustment.
CRUDEOIL and NATURALGAS use two business days before the exactly listed future
expiry. Official futures tables establish the energy dates. No nearest future,
continuous series or automatic extrapolation establishes a relationship.

All five option specifications define the terminal reference as the **daily
settlement price of the exact underlying futures contract on the option expiry
date**. `OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE` retains that meaning.
It does not use futures-expiry DDR, LTP, an OHLC close, spot or an international
reference price. This slice acquires no terminal settlement values.

Units: GOLDM INR per 10 grams; SILVERM and COPPER INR per kilogram; CRUDEOIL INR
per barrel; NATURALGAS INR per MMBtu. These are quotation units, not lot sizes.

## Option endpoints and rollover

Endpoints are timezone-aware Asia/Kolkata values. Under the retained option
specification and DST evidence, covered October sessions end 23:30, covered
November/December sessions 23:55. The option publication is additive; the
existing futures base calendar and its November clocks are not rewritten.
Copper's futures-expiry 17:00 cutoff is never used for an option endpoint.

Eligibility is strictly `commissioning_time < option_endpoint`. At the exact
endpoint and afterwards, the expired series is excluded. A valid E1/E2 pair
requires two remaining applicable series. COPPER/CRUDEOIL/NATURALGAS can roll
from October/November to November/December. GOLDM/SILVERM fail closed after
their October endpoints because only one supported future option expiry
remains. December/2027 coverage is never guessed to manufacture E2.

## Theta and TE-04A consumption

`ThetaTargetAuthorityAdapter` is read-only and explicitly supplied through the
existing `authority_provider` seam. It returns the existing `AuthorityBundle`
and exact `ExpiryTarget` shape for TE-02. A missing methodology raises
`THETA_METHODOLOGY_UNAVAILABLE` separately from missing review or target data.
Default Browser/runtime composition is not changed by this slice.

`v3_inputs` supplies the existing V3 target-authority descriptor, exact target
fields and validity. `price_unit` comes from the Instrument publication.
`MCXA-<hash>` addresses `target_record`: the complete public series, option
session, domain references and currentness reference. `MCXE-<hash>` addresses
the ordered source-provenance tuple. Both satisfy V3's existing 100-character
identity grammar. These are reproducible public content references, not
Provider IDs or a new persistence platform. The owner publications and source
bytes must be retained for their resolution. No TE-04A change is required.

Historical Questions remain immutable. New target authority creates new
commissioned input identity; it does not reinterpret historical evidence.
V3 schema compatibility is qualified independently of runtime V3 rollout.

## Review routing and exclusions

No separately commissioned current Instrument owner is established.
No separately commissioned current Market/calendar owner is established.
Per the Sponsor order, **Kronos CA 2** reviews both domains independently
against the final candidate bytes. An engineering test review is always
explicitly synthetic and is not owner approval.

No existing futures selection/session code changes; no Swing/Intraday method
changes; NATGAS policy remains unchanged. No Provider acquisition, credentials,
broker activity, production operations, TE-04B intake or TE-05 assessment.
