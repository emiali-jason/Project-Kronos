# KRONOS Swing V1 — Slice A Pine Evidence Contract

- **Status:** Implemented under the approved Pine-first Engineering Slice A authorization
- **Contract:** `KRONOS-SWING-V1-PINE-EVIDENCE-V1`
- **Version:** `1.1`
- **Products:** `MCX` and `NSE`, explicitly separated
- **Routine mandatory OpenAI calls:** `0`
- **Pine publication:** Not authorized in Slice A

## Ownership

The frozen Layer-2 question set retains explicit responsibility boundaries:

- Pine owns 14 deterministic evidence domains: chart instrument identity,
  chart timeframe identity, price structure, visible swings,
  range/consolidation, breakout/breakdown, SMA20, SMA50, SMA200, candle
  acceptance, Volume context, reference levels, barriers and Pine display.
- Browser owns `CHART_TEMPLATE_IDENTITY`.
- KRONOS owns `CONTRADICTIONS` and all final reconciliation and decision
  authority.

Pine does not calculate Browser template identity or contradictions. Slice A
does not implement Readiness, Trade Construction, ranking, transport,
persistence or final-authority decisions.

## Envelope and product isolation

The immutable envelope contains contract and deterministic event identities,
producer source identity and SHA-256, canonical analysis/execution identity,
declared timeframe roles, completed/developing/unknown observation boundary,
sequence number, integrity and provenance. Stream identity is derived from
product, publisher role, Pine identity/build/source hash, canonical instrument
and chart timeframe. Version 1.1 adds explicit Production/Candidate role,
evidence-contract identity/version, declared compatibility class and
product-scoped publisher-registry reference. Compatibility is never inferred.

MCX preserves MCX futures analysis, COMEX/NYMEX reference identity,
reference-timeframe states, commodity workstation semantics, readiness
reference context and already-authoritative NOW/trigger evidence. It cannot
carry NSE extension fields.

NSE preserves cash analysis, futures-to-underlying provenance, sector and
parent indexes, sector/broad-market context, relative alignment, reference
completeness and NSE readiness context. NOW is explicitly
`NOT_APPLICABLE / NOT_IN_NSE_V1`. It cannot carry COMEX/NYMEX extension fields.

## Boundary, availability and integrity

Observation boundary is one of `COMPLETED`, `DEVELOPING` or `UNKNOWN`, with
bar open/close, evaluation time, declared timeframe, confirmed flag and
source-period identity. A completed boundary must be confirmed and evaluated
at or after bar close. A developing boundary must be unconfirmed and evaluated
before bar close.

Every Pine-owned evidence item has a question identity, availability
(`AVAILABLE`, `UNAVAILABLE`, `NOT_APPLICABLE`), state, scalar value or values,
source engine and fields, derivation (`DIRECT`, `EXPOSURE`, `DERIVED`),
integrity (`VALID`, `DEGRADED`, `INCOMPLETE`, `INVALID`), boundary state and
provenance.

Validation reports explicit codes for wrong product, Pine identity,
version/build or source hash; missing fields; unsupported contract version;
invalid timeframe or boundary; invalid product fields; invalid evidence or
event identity; wrong publisher role, contract, compatibility or registry; and
payload-budget breach.

## Pine evolution and registry authority

MCX and NSE each have an independent immutable `ApprovedPineRegistry` model.
Entries preserve product, publisher role, exact Pine identity/version/build and
SHA-256, evidence contract, explicit compatibility class, approval status and
timing, supersession/rollback lineage, validation reference and active-authority
state. Registry authority is established only by this local registry; webhook
traffic never activates or promotes a publisher.

Compatibility classes are:

- `IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE`;
- `NEW_EVIDENCE_ADDITION`;
- `EXISTING_EVIDENCE_SEMANTIC_CHANGE`; and
- `BREAKING_CONTRACT_CHANGE`.

Candidate entries are structurally prohibited from active authority. A
validated Candidate can be promoted only through the explicit registry
promotion operation, which creates a new Production entry and preserves the
Candidate entry unchanged. Rollback is an explicit independent product-scoped
operation and reactivates only the declared rollback parent. Historical
evidence retains its original publisher role and event identity.

The collision-safe retention key includes product, role, Pine identity/build /
source hash, canonical instrument, timeframe and complete bar-boundary
identity. Production and Candidate evidence for the same market state are
therefore retained independently. Only an approved active Production entry can
produce the authoritative Layer-2 handoff used by downstream KRONOS; Candidate,
unknown and inactive Production evidence are denied that handoff.

## Canonical identity and serialization

Canonical serialization is sorted, compact UTF-8 JSON with UTC timestamps,
no non-finite numbers and stable enum values. Event identity is SHA-256 over
the evidence identity tuple plus a digest of evidence and the applicable
product extension. Arrival time is not part of analytical identity. Identical
canonical evidence produces the same event ID; changed evidence produces a
different ID.

## Fixture and payload budget

Canonical deterministic fixtures cover MCX and NSE completed, developing and
invalid events; product extensions; unavailable, not-applicable and partial
evidence; and wrong-product semantics.

Measured canonical fixture sizes:

| Fixture | Bytes |
| --- | ---: |
| MCX Candidate valid completed | 8,606 |
| MCX Candidate developing | 8,624 |
| MCX Candidate partial/incomplete | 8,604 |
| NSE Candidate valid completed | 8,706 |
| NSE Candidate developing | 8,722 |
| NSE Candidate partial/incomplete | 8,693 |
| MCX Production completed | 8,585 |
| NSE Production completed | 8,861 |

The internal payload maximum is **16,384 bytes**. The largest fixture leaves
7,523 bytes of internal headroom. TradingView currently documents a 40,960
character maximum for Pine `alert()` / `alert_message`, also applied to the
webhook request body; the largest fixture therefore has 32,099 characters of
nominal platform headroom. This external ceiling is a validation reference,
not a license to expand the internal budget.

Source: [TradingView alert name and message size limits](https://www.tradingview.com/support/solutions/43000773947-alert-name-and-message-size-limits/).

## Existing Layer-2 compatibility

Validated Pine envelopes map to a provider-neutral `PineLayer2EvidenceHandoff`
carrying the 14 Pine-owned facts, question-set identity and explicit Browser /
KRONOS ownership. This establishes the later ingress seam only.

The existing `ChartEvidenceProvider`, manual provider, OpenAI adapter,
clipboard intake, image hashing, Layer-2 reconciliation, barriers, Clear Air
and Readiness are retained unchanged. No provider is invoked in Slice A, and
normal mandatory OpenAI usage remains zero.
