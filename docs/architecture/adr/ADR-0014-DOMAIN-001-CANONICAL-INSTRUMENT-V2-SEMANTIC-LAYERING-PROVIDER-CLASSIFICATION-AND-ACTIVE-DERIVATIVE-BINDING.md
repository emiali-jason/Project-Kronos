# ADR-0014 — DOMAIN-001 Canonical Instrument V2 Semantic Layering, Provider Classification, and Active Derivative Binding Architecture

## Metadata

- **ADR Number:** ADR-0014
- **Status:** APPROVED
- **Date:** 2026-08-22
- **Decision Owner / Approved By:** Chief Architect
- **Decision Scope:** Platform / DOMAIN-001 / DOMAIN-006
- **Repository Approval:** Approved for publication
- **Engineering Status:** Not started; implementation is decomposed into separately bounded WO-P1 through WO-P5
- **Runtime Authority:** NONE
- **Provider Acquisition Authority:** NONE
- **Broker Authority:** NONE
- **Trading / Risk / Entry Authority:** NONE

## Context

`KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1` successfully represents the
existing RELIANCE cash equity but does not provide sufficient production
semantics for the complete governed 98-member Intraday Native universe.

The unresolved set contains:

- 90 Sponsor-approved NSE cash equities;
- NIFTY and BANKNIFTY as persistent NSE index analytical subjects; and
- GOLDM, SILVERM, COPPER, NATGAS, and CRUDE as persistent MCX analytical
  subjects whose Provider representations are expiry-specific futures.

Provider vocabulary must not become canonical vocabulary automatically.
Persistent analytical subjects must not be collapsed into expiring Provider
contracts, and Provider presence must not become an implicit active-contract
selection policy.

This decision extends the approved product-neutral separation established by
[ADR-009](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md),
[EAIC-002](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md),
[DOMAIN-001](../platform/domains/instrument/ARCHITECTURE.md), and
[DOMAIN-006](../platform/domains/provider/ARCHITECTURE.md).

## Decision

### 1. Immutable Provider Instrument Master snapshot

The architecture authorizes the contract identity
`KRONOS-PROVIDER-INSTRUMENT-SNAPSHOT-V1`.

It is a DOMAIN-006-owned, complete, immutable representation of the factual
records returned by one separately authorized Provider Instrument Master
operation. Product-filtered acquisition is prohibited. The snapshot has no
canonical Instrument authority and does not establish product membership or
eligibility.

A bounded commissioning manifest may separately identify Provider records
relevant to one canonical commissioning programme. It does not reduce the
Provider snapshot, redefine acquisition scope, or replace EAIC-002 record
granularity and submission authority.

### 2. DOMAIN-006 ownership

DOMAIN-006 owns:

- Provider acquisition;
- Provider record identity;
- Provider vocabulary;
- Provider token;
- source boundary;
- snapshot provenance; and
- snapshot integrity.

DOMAIN-001 may consume eligible Provider facts through the approved boundary
without taking ownership of the Provider snapshot, record, vocabulary, token,
or provenance.

### 3. Provider classification mapping

The architecture authorizes the DOMAIN-001-owned, versioned contract
`PROVIDER_INSTRUMENT_CLASSIFICATION_MAPPING_V1`.

Canonical classification is distinct from Provider classification. Each
mapping is explicit, effective-dated, attributable, deterministically sealed,
and fail closed. Unknown Provider vocabulary is unavailable. Fuzzy matching,
runtime string inference, and automatic adoption of Provider enum strings as
canonical meaning are prohibited.

The initial explicit mapping families may include:

| Provider representation | Permitted canonical interpretation |
| --- | --- |
| Kite `NSE / EQ` | NSE cash equity |
| Kite `INDICES / EQ` | NSE index, only for an explicitly governed index subject |
| Kite `MCX / FUT` | Expiry-specific MCX derivative contract |

The MCX mapping does not map an expiry-specific future directly onto a
persistent commodity analytical subject.

### 4. Canonical Instrument Catalogue V2

The architecture authorizes
`KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2` as the successor semantic model.

`KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1` publications `1.0.0` and `1.0.1`
remain immutable for historical integrity and replay. V2 does not rewrite or
silently reinterpret V1 records.

Initial V2 commissioning is bounded to:

- 91 NSE cash equities;
- two persistent NSE index analytical subjects;
- five persistent MCX analytical subjects; and
- only the supporting derivative-contract records required for those
  subjects.

V2 is not an authority to import the complete Indian security master into the
canonical catalogue.

### 5. NSE cash equities

An NSE cash equity may remain a directly canonical listed Instrument. An
artificial analytical-subject wrapper is not required.

RELIANCE remains a canonical listed NSE cash equity and must retain its
observable V1 meaning through any V2 compatibility path.

Sponsor membership establishes the requirement to review a subject; it does
not establish every canonical market fact. Cash-instrument lot geometry may be
published only when supported by the governed source hierarchy. Derivative
lot geometry must not be inferred for a cash equity.

### 6. NIFTY

NIFTY is a persistent canonical NSE `INDEX` analytical subject.

NIFTY is not a NIFTY futures contract, a NIFTY option contract, or execution
eligibility. Provider vocabulary such as `NIFTY 50` and `INDICES / EQ`
requires an explicit governed mapping under
`PROVIDER_INSTRUMENT_CLASSIFICATION_MAPPING_V1`.

### 7. BANKNIFTY

BANKNIFTY is a persistent canonical NSE `INDEX` analytical subject.

BANKNIFTY is not a BANKNIFTY futures contract, a BANKNIFTY option contract, or
execution eligibility. Provider vocabulary such as `NIFTY BANK` and
`INDICES / EQ` requires an explicit governed mapping.

### 8. Persistent MCX analytical subjects

The following are persistent canonical analytical subjects:

- GOLDM;
- SILVERM;
- COPPER;
- NATGAS; and
- CRUDE.

Their canonical identities survive listed-contract expiry. No fictional
perpetual future or perpetual listed Instrument may be created to represent
them.

### 9. Derivative contracts

An expiry-specific future is a distinct canonical derivative-contract record.
Where established through governed sources, the record may preserve:

- canonical contract identity;
- parent analytical-subject identity;
- exchange and canonical Instrument type;
- expiry;
- effective-dated contract geometry;
- Provider mapping identity;
- effective validity;
- provenance; and
- integrity.

A Provider token does not create or preserve canonical contract identity.

### 10. Active derivative contract binding

The architecture authorizes the DOMAIN-001-owned contract
`ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1`.

It binds one persistent analytical subject to one exact governed derivative
contract for a bounded runtime interval and preserves:

- `effective_from`;
- `effective_through`;
- contract expiry;
- governed Provider reference;
- source and provenance; and
- deterministic integrity.

The binding records an already-governed selection. It does not select the
contract.

### 11. Contract-selection deferral

No automatic selection authority exists for:

- front month;
- nearest expiry;
- highest volume;
- highest open interest;
- most liquid contract; or
- same calendar month.

Without a current valid binding, contract-specific availability is
`ACTIVE_CONTRACT_BINDING_UNAVAILABLE`.

A later implementation may provide a typed resolver, binding store,
effective-dated lookup, roll segmentation, and an unavailable state without
implementing a selection heuristic.

### 12. Provider-token boundary

Provider token is a DOMAIN-006 operational and factual identifier. It may
support Provider access and governed audit evidence. If operationally
persisted, it remains a typed Provider-owned reference and must be replaceable
without changing canonical identity.

Provider token must never define:

- canonical subject identity;
- canonical semantic identity;
- classification-mapping identity;
- product-universe identity; or
- canonical catalogue identity.

Canonical publications should prefer governed Provider record identity and
symbol references. No product may access a private Provider token map.

### 13. Current runtime reconciliation

Later, separately authorized implementation work may reconcile:

- `ProviderInstrumentAssertion`;
- `ProviderInstrumentBinding`;
- `RuntimeInstrument`; and
- `RuntimeInstrumentRegistry`

with V2.

That reconciliation must introduce no canonical token leakage, transfer no
DOMAIN-006 ownership, create no second Provider context, expose no private
token map to a product, retain fail-closed behavior, and preserve Swing
observable behavior. This ADR publication performs no runtime change.

### 14. Effective-dated geometry

Mutable execution geometry, including tick size, lot size, and other governed
contract geometry, is effective-dated.

Historical facts remain immutable. A Provider-only mismatch fails closed and
requires investigation. An authoritatively corroborated change requires a new
DOMAIN-001 fact segment or governed publication. Historical geometry is never
rewritten.

### 15. Source hierarchy

Canonical publication uses the following source hierarchy:

```text
authoritative exchange or security facts
        +
Sponsor-governed canonical subject requirement
        +
immutable DOMAIN-006 Provider evidence
        +
DOMAIN-001 normalization and interpretation
        ↓
canonical publication
```

Sponsor requirement may establish the need for a subject but not every market
fact. Provider presence establishes Provider facts but not canonical meaning.

### 16. Runtime model

The conceptual runtime model is:

```text
DOMAIN-006 Provider snapshot
        ↓
eligible Provider → Instrument submissions
        ↓
DOMAIN-001 Catalogue V2
        + Classification Mapping V1
        + Provider Mapping Directives
        + Active Derivative Binding where required
        ↓
validated runtime resolution
        ↓
RuntimeInstrument / RuntimeAnalyticalSubject
        ↓
product universe resolution
```

By semantic kind:

- NSE cash equity: a direct canonical-to-Provider binding may suffice;
- NSE index: persistent analytical subject plus explicit classification
  mapping; and
- MCX: persistent analytical subject plus active derivative-contract binding
  for contract-specific operations.

All semantic kinds need not fit one destructive flat runtime shape.
Compatibility adapters are permitted in later bounded implementation work.

### 17. Failure semantics

V2 shall preserve, at minimum, these fail-closed outcomes:

- `CANONICAL_SUBJECT_UNAVAILABLE`;
- `CLASSIFICATION_MAPPING_UNAVAILABLE`;
- `PROVIDER_ASSERTION_UNAVAILABLE`;
- `PROVIDER_BINDING_UNAVAILABLE`;
- `ACTIVE_CONTRACT_BINDING_UNAVAILABLE`;
- `CANONICAL_GEOMETRY_MISMATCH`;
- `CANONICAL_CLASSIFICATION_CONFLICT`;
- `SOURCE_STALE`;
- `PUBLICATION_STALE`; and
- `INTEGRITY_INVALID`.

Fallback identity, fallback contract, Provider-wins mutation, and implicit
classification normalization are prohibited.

### 18. Intraday Native universe

`KRONOS-INTRADAY-NATIVE-UNIVERSE-V1 / 1.0.0` remains unchanged. Intraday owns
product membership. DOMAIN-001 owns canonical meaning and runtime resolution.

Native analytical membership is not execution eligibility.

### 19. Future COMEX and NYMEX reference subjects

A future Track-C path is approved for:

- COMEX Gold;
- COMEX Silver;
- COMEX Copper;
- NYMEX Natural Gas; and
- NYMEX Crude Oil.

They remain reference subjects outside the Native 98. This decision grants no
reference-market trading consequence.

### 20. Implementation decomposition

Implementation is decomposed into independently bounded packages:

| Work order | Bounded responsibility |
| --- | --- |
| PLATFORM WO-P1 | DOMAIN-006 Provider Instrument Master acquisition and immutable Provider snapshot |
| PLATFORM WO-P2 | DOMAIN-001 classification mapping and V2 semantic contracts |
| PLATFORM WO-P3 | DOMAIN-001 publication for the 90 missing NSE equities, NIFTY, BANKNIFTY, and RELIANCE compatibility |
| PLATFORM WO-P4 | DOMAIN-001 persistent MCX subjects, derivative-contract model, and active-binding machinery |
| PLATFORM WO-P5 | Intraday 98-member canonical reconciliation |

WO-P1 through WO-P5 must remain independently reviewable implementation
packages. This ADR does not begin any package.

## Authority Not Granted

This ADR grants no authority for:

- automatic authentication or re-authentication;
- automatic contract selection;
- front-month or liquidity-based selection;
- trading predicates;
- Readiness consequences;
- Trade Construction policy;
- Risk consequences;
- Entry consequences;
- broker mutation or execution;
- Pine authority;
- Chart Analyst numerical authority;
- Swing/Intraday product-state coupling;
- Provider endpoint invocation;
- live Provider acquisition;
- Provider snapshot persistence;
- runtime implementation; or
- implementation of WO-P1 through WO-P5 without a separate bounded work
  order.

## Rationale

V2 is required because the flat V1 record shape cannot safely represent all
of the following without changing V1 meaning:

- canonical classification that differs from Provider vocabulary;
- persistent analytical subjects;
- expiry-specific derivative contracts;
- effective-dated geometry; and
- explicit active derivative bindings that remain separate from selection.

The decision preserves Provider, Instrument, and Product ownership while
allowing the already-governed Intraday membership to resolve through shared
Platform contracts.

## Alternatives Considered

- **Extend the flat V1 record until it carries every new semantic kind:**
  rejected because it would materially reinterpret immutable V1 history.
- **Acquire or persist only the 98 product-relevant Provider rows:** rejected
  because ADR-009 prohibits product-filtered acquisition.
- **Treat the current MCX Provider future as the persistent subject:** rejected
  because contract expiry would change canonical subject identity.
- **Select the active contract automatically:** deferred because no front-month,
  nearest-expiry, volume, OI, liquidity, or calendar-month policy is approved.

## Consequences

- DOMAIN-001 gains an approved semantic architecture capable of representing
  directly listed cash equities, persistent index and commodity subjects, and
  expiry-specific derivative contracts without identity collapse.
- DOMAIN-006 retains ownership of Provider acquisition, Provider facts,
  tokens, snapshots, and provenance.
- Contract-specific MCX operations remain unavailable until an effective
  governed active binding exists.
- V1 history remains immutable while V2 becomes the successor semantic model
  after separately governed commissioning.
- The Intraday Native universe remains unchanged.

## Shared Regression Rule

Every later WO-P1 through WO-P5 Platform implementation must declare:

- shared files changed;
- cross-product contracts affected; and
- compatibility and migration impact.

Relevant regression must include, as applicable:

- Provider / DOMAIN-006;
- DOMAIN-001;
- Intraday;
- Swing; and
- Browser/runtime.

Swing observable methodology and behavior must remain unchanged unless
separately authorized. RELIANCE V1 compatibility, restart/replay behavior,
classification mismatches, unknown Provider vocabulary, effective-dated
geometry, missing/expired active bindings, integrity, and secret/token leakage
must receive focused proof where affected.

## Risks

- A compatibility adapter could accidentally preserve the flat V1 shape by
  collapsing analytical subjects into Provider contracts.
- Provider vocabulary could be treated as canonical through convenience
  comparisons.
- A resolver could become an unauthorized selection heuristic.
- Provider tokens could leak into canonical identity or product-visible state.
- Geometry changes could overwrite historical facts.

All such conditions must fail closed or prevent publication.

## Affected Products

- Intraday: canonical resolution of the existing 98-member Native universe.
- Swing: no methodology or observable behavior change is authorized.
- Future reference-market Track C: architecture path only.

## Affected Interfaces

- EAIC-002 remains the sole Provider → Instrument submission boundary.
- Later bounded work may add versioned V2 semantic, mapping, and binding
  contracts without rewriting EAIC-002 or V1 history.

## Implementation Implications

Implementation requires separate WO-P1 through WO-P5 authority. Each work
order must preserve ownership, migration compatibility, fail-closed behavior,
and the shared regression rule defined here.

## Validation Requirements

This documentation publication requires:

- required-decision content verification;
- repository-relative link verification;
- `git diff --check`;
- bounded secret scanning; and
- confirmation that no production or runtime file changed.

Runtime regression is not required for this documentation-only publication.

## Validation Evidence

Publication-candidate evidence is returned by the ADR publication work order.

## Supersedes

None. This ADR adds the V2 semantic architecture and preserves V1 history.

## Superseded By

None.

## Related ADRs

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [ADR-010 — Provider Authentication Shared Platform Capability](../platform/domains/provider/ADR-010-PROVIDER-AUTHENTICATION-SHARED-PLATFORM-CAPABILITY.md)

## Related Documents

- [DOMAIN-001 — Instrument](../platform/domains/instrument/ARCHITECTURE.md)
- [DOMAIN-006 — Provider](../platform/domains/provider/ARCHITECTURE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
- [Intraday Native Universe V1](../products/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md)
- [Intraday DOMAIN-001 prerequisite manifest](../products/intraday/KRONOS-INTRADAY-DOMAIN-001-PREREQUISITE-MANIFEST-V1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-22 | 1.0 | Codex Engineering Support | Published the Chief Architect-ratified DOMAIN-001 Canonical Instrument V2 architecture | APPROVED |
