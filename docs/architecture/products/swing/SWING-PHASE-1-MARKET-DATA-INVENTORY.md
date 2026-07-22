# Swing Phase 1 — Market Data Inventory

**Status:** Approved

**Owner:** Chief Architect

**Version:** 1.0

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Architecture Impact:** Documentation only

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Purpose

Define the authoritative inventory of market information that KRONOS Swing may acquire from Kite during Phase 1 — Market Data Foundation.

This inventory classifies information only. It does not approve a retrieval operation, endpoint, Engineering Design Document, Engineering Package, persistence model, streaming model, or implementation sequence.

## 2. Scope

Phase 1 asks whether KRONOS can reliably obtain the market information required by the approved Swing scope while preserving Provider, Configuration, Instrument, Observation, and Market boundaries.

This document evaluates authenticated read-only access, instrument reference information, historical OHLCV and Open Interest, mandatory current quote facts, provider acquisition metadata, market-session information where an authoritative source exists, existing approved analysis/reference/execution relationships, and factual provenance and completeness metadata.

It does not expand approved Swing relationships. MCX Metals remains the currently supported model. Planned models or configuration scaffolding do not become supported merely by appearing in this inventory.

## 3. Architectural Principles

1. Availability from Kite does not equal permission for KRONOS Phase 1.
2. Provider acquisition does not create canonical business meaning.
3. Instrument Master rows are provider reference records, not automatically canonical instruments.
4. Provider instrument tokens are not permanent KRONOS identities.
5. Missing data and zero are different states.
6. HTTP or API success does not prove dataset completeness.
7. Missing quote entries must remain explicit.
8. Partial historical responses must remain explicit.
9. Provider availability is not Market availability.
10. Missing data must not be used to infer exchange closure.
11. Current OHLC snapshots are not completed historical candles.
12. Historical OI and current OI must remain distinct.
13. Continuous futures data must not automatically be described as adjusted or canonical continuous history.
14. Options rows present in the Kite instrument dump must not enter the approved Phase 1 universe.
15. No dataset may create Business Judgment, Risk Approval, Execution authority, Orders, or Positions.
16. Phase 1 acquisition is read-only.
17. No persistence model is authorized by this inventory.
18. No streaming model is authorized by this inventory.
19. No retrieval sequence is authorized by this inventory.

Provider acquires and normalizes external data. Instrument owns canonical identity. Observation owns factual market observations. Market owns market-session and schedule meaning. Configuration owns runtime configuration. Reuse does not transfer ownership.

## 4. Classification Definitions

| Classification | Definition |
| --- | --- |
| Mandatory | Required to make the approved Phase 1 boundary attributable, identity-safe, factually scoped, or operationally distinguishable from failure. Classification does not authorize retrieval. |
| Optional | May improve Phase 1 factual coverage or diagnostics but is not required for the minimum foundation. |
| Conditional | Permitted only when an approved scope, authoritative source, consumer, provider capability, or contract establishes the need. |
| Future Phase | Not required or authorized for Phase 1. Availability from Kite creates no permission. |

Every named dataset below has exactly one classification. Entries sharing a row share the stated classification and rationale.

## 5. Dataset Inventory

### A. Market Information

| Dataset Name | Description | Primary Purpose | Expected Source | Future Canonical Owner | Classification | Phase | Dependencies | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Instrument Master | Provider reference rows for available instruments. | Supply reference material for canonical mapping. | Kite instrument reference data. | Provider raw; Instrument canonical. | Mandatory | Phase 1 | Provider → Instrument contract. | Rows are not canonical instruments; Options rows are excluded. |
| Provider instrument token | Provider-scoped retrieval identifier. | Address Kite requests and map provider records. | Kite Instrument Master. | Provider technical; Instrument mapping meaning. | Mandatory | Phase 1 | Instrument Identity and reference-support contracts. | Never a permanent KRONOS identity. |
| Exchange token | Exchange-scoped reference identifier where supplied. | Trace provider/exchange records. | Kite Instrument Master. | Provider | Optional | Phase 1 | Provider reference capability. | Cannot replace canonical identity. |
| Trading symbol; exchange; segment; instrument type; instrument name or underlying reference | Provider reference fields used to reconcile and classify approved instruments. | Support canonical mapping and approved-universe filtering. | Kite Instrument Master. | Instrument after acceptance. | Mandatory | Phase 1 | Instrument Identity Contract. | Provider vocabulary must not leak unreviewed; exchange does not establish OPEN/CLOSED. |
| Expiry | Provider-recorded expiry for expiring instruments. | Preserve futures lifecycle identity. | Kite Instrument Master. | Instrument | Mandatory | Phase 1 | Instrument Lifecycle decision or contract. | Does not define rollover. |
| Lot size; tick size | Provider instrument reference values. | Preserve non-execution reference metadata. | Kite Instrument Master. | Instrument | Optional | Phase 1 | Instrument Identity Contract. | Not used for risk, sizing, price validation, or orders. |
| Instrument lifecycle state | Canonical active, expired, or historical identity status. | Preserve identity across expiry and token changes. | Instrument interpretation of approved references. | Instrument | Mandatory | Phase 1 | Instrument Lifecycle decision or contract. | Provider supports but does not own the meaning. |
| Historical timestamp; open; high; low; close; volume | One historical OHLCV observation and its time. | Publish attributable historical facts. | Kite historical data. | Observation | Mandatory | Phase 1 | Canonical Instrument Identity; Provider → Observation and Market Facts contracts. | Timestamp provenance is explicit; zero and missing volume differ. |
| Historical Open Interest | OI attached to historical observations where supported. | Preserve derivatives interest facts. | Kite historical data where available. | Observation | Mandatory | Phase 1 | OI availability semantics and Market Facts Contract. | Distinct from current OI and interpretation. |
| Continuous historical futures data | Provider-produced continuous futures history where supported. | Evaluate continuity coverage. | Kite historical data where available. | Observation facts; Instrument identity association. | Conditional | Phase 1 if approved | Instrument Lifecycle and continuous-data decisions. | Not adjusted, canonical, or rollover-safe by default. |
| Requested historical range; received historical range; partial historical response; missing historical intervals | Requested and actual time coverage plus explicit partiality and gaps. | Prevent false completeness. | Provider request/result and Observation acceptance. | Provider technical; Observation factual scope. | Mandatory | Phase 1 | Acquisition and Market Facts contracts. | API success does not clear partiality; gaps do not imply closure. |
| Last traded price; current OHLC snapshot; current Open Interest; OI day high and low; traded volume; last trade quantity; average traded price; last trade timestamp; exchange timestamp | Current factual snapshot fields. | Provide current non-streaming factual market information. | Kite quote capability. | Observation | Mandatory | Phase 1 | Provider → Observation quote contract. | Current Quote is factual market information and forms part of the Phase 1 Market Data Foundation. Its inclusion authorizes acquisition only and does not authorize trading logic, decision making, validation, or execution. Current OHLC is not a completed candle; historical/current OI differ; average traded price is not VWAP. |
| Full quote snapshot | Approved provider-neutral subset of a full quote. | Consolidate current facts when a consumer is approved. | Kite full quote. | Observation | Conditional | Phase 1 if approved | Explicit quote-field contract. | Raw quote payload and SDK object stay inside Provider. |
| Aggregate buy quantity; aggregate sell quantity; circuit limits | Provider-reported current quote fields. | Preserve optional venue facts where justified. | Kite full quote. | Observation for accepted facts. | Conditional | Phase 1 if approved | Explicit field definitions and consumer. | No imbalance scoring, execution validation, or judgment. |
| Bid market depth; ask market depth; depth price; depth quantity; depth order count | Market-depth records. | Future microstructure observation. | Kite quote/streaming capability. | Observation | Future Phase | Future | Market-depth contract and approved use. | Not justified by approved Phase 1 Swing architecture. |
| WebSocket quote data; WebSocket OI; WebSocket timestamps; subscription metadata; stream availability metadata | Streaming content and lifecycle metadata. | Future live-data acquisition. | Kite streaming service. | Provider acquisition; Observation accepted facts. | Future Phase | Future | Streaming architecture and contracts. | No streaming model or subscription is authorized; stream availability is not Market availability. |
| Trading session calendar; trading days; holidays; special sessions; market open and close times | Authoritative Market Schedule definitions. | Distinguish scheduled sessions from acquisition failure. | Approved authoritative calendar; Kite suitability unresolved. | Market | Mandatory | Phase 1 | Market Schedule Contract and approved source. | Market Schedule provides factual operating context required to correctly interpret market-data availability. It is market metadata, not business judgment. Must not be inferred from data presence/absence or Provider state. |
| Explicit exchange availability | Approved OPEN/CLOSED meaning. | Present explicitly known exchange state. | Approved source under EAIC-001. | Market | Conditional | Phase 1 if required | EAIC-001 and approved source. | Missing/stale data, Provider state, and execution state are prohibited inputs. |
| Active contract; expired contract; provider-token changes; futures expiry; historical identity preservation | Canonical futures lifecycle identity and historical traceability. | Keep facts attributable across expiry and provider changes. | Instrument using approved reference material. | Instrument | Mandatory | Phase 1 | Instrument Lifecycle decision or contract. | Does not imply execution permission or rollover. |
| Replacement contract; continuous futures limitations | Explicit successor relationship or provider continuity limitation where approved. | Support lifecycle/continuity review. | Instrument and Provider capability records. | Instrument relationship; Provider supplies limitations. | Conditional | Phase 1 if approved | Instrument Lifecycle/continuous-data decision. | No automatic replacement, rollover, adjustment, or canonical series. |
| Splits; dividends; bonuses; mergers; symbol changes | Corporate-action or identity-change information. | Future cash-history and identity context. | Approved corporate-action/reference source. | Observation facts; Instrument identity effects. | Future Phase | Future | Corporate-action and lifecycle architecture. | Not required by current approved Swing futures scope. |
| Analysis instruments; reference instruments; execution instruments | Canonical roles under existing approved Swing relationships. | Preserve analysis/reference/execution distinctions. | Instrument Identity Contract. | Instrument | Mandatory | Phase 1 | ADL-001 and PP-007. | No new relationship or execution permission. |
| Reference-market futures | Approved futures providing reference context. | Obtain existing required reference-market information. | Kite if supported; otherwise unresolved source. | Instrument identity; Observation facts. | Mandatory | Phase 1 | Existing ADL-001 relationships and acquisition contracts. | Kite coverage for approved COMEX/NYMEX references is not established; no substitute may be invented. |
| Index references | Approved benchmark identities/data when an existing model is activated. | Support approved benchmark relationships. | Kite if supported and separately approved. | Instrument identity; Observation facts. | Conditional | Phase 1 if model activated | Existing approved relationship and contracts. | Does not activate NSE Swing or create a benchmark relationship. |
| Freshness; source attribution; timestamp provenance; completeness; partiality; missing values; unsupported fields; provider limitations; zero versus missing; request success versus dataset completeness | Factual quality and provenance dimensions without scoring or judgment. | State exactly what was observed, from where, when, and with what limits. | Provider metadata accepted by Observation. | Observation for factual semantics; Provider for technical inputs. | Mandatory | Phase 1 | Acquisition and Market Facts contracts. | No quality/confidence score, validation judgment, or suitability-for-trading judgment. |

Instrument Master `last_price`, when supplied by Kite, is auxiliary provider metadata and is not classified as an independent architectural dataset. It is not part of Canonical Instrument Identity, it is not Current Quote, and it must never replace Observation-owned market state.

### B. Operational Information

| Dataset Name | Description | Primary Purpose | Expected Source | Future Canonical Owner | Classification | Phase | Dependencies | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Authentication profile probe | One authenticated read-only technical probe whose profile payload is discarded. | Confirm Provider connectivity. | Kite `profile()` through EP-004. | Provider | Mandatory | Phase 1 | Runtime configuration; externally acquired token. | Already implemented. Mandatory as capability, not as a published account dataset. |
| Account identity | Personal or provider account identifiers. | Account administration only. | Kite profile. | Unresolved; not a Market Fact. | Future Phase | Future | Separate account/security architecture. | Not required for market information and remains discarded under EP-004. |
| Account entitlements; enabled exchanges; enabled products | Provider permissions that might explain access limitations. | Diagnose approved data-access limitations if necessary. | Kite account/provider metadata where available. | Provider | Conditional | Phase 1 if approved | Provider capability contract and named consumer. | Does not establish approved universe or Market availability. |
| Enabled order types | Provider order permissions. | Order administration. | Kite profile metadata where available. | Execution if ever relevant. | Future Phase | Future | Separate order architecture. | Orders are excluded. |
| Provider identity; provider capability; provider availability | Provider source, supported technical surface, and technical availability. | Attribute source and distinguish technical support/failure. | Provider integration boundary. | Provider | Mandatory | Phase 1 | Provider Integration Contract. | Capability is not permission; availability is not Market availability or completeness. |
| API response status; error category; rate-limit or throttling metadata | Stable provider-neutral technical acquisition outcomes. | Explain failure, unsupported requests, and throttling safely. | Provider adapter. | Provider | Mandatory | Phase 1 | Provider acquisition contract. | No raw SDK exceptions/messages; does not authorize retry design. |
| API version or compatibility metadata | Compatibility facts required for safe provider review. | Support controlled provider/SDK compatibility. | Provider adapter and dependency record. | Provider | Optional | Phase 1 | Provider Integration Contract. | No SDK object exposure. |
| Request time; receipt time | KRONOS request and response receipt times. | Acquisition provenance and latency boundary. | Provider. | Provider | Mandatory | Phase 1 | Provider acquisition contract. | Neither is an exchange or observation timestamp. |
| Requested dataset scope; received dataset scope | Requested and actual instruments, fields, intervals, and range. | State acquisition intent and coverage. | Provider request/result. | Provider technical; Observation accepted scope. | Mandatory | Phase 1 | Provider → Observation contract. | Must remain distinct. |
| Missing-instrument result; unsupported-data result; partial-result status | Explicit non-success and incomplete-result states. | Prevent empty/partial data from appearing complete. | Provider acquisition result. | Provider technical; Observation factual acceptance where applicable. | Mandatory | Phase 1 | Provider capability and acquisition contracts. | Unsupported, unavailable, missing, and partial are distinct. |
| Source attribution | Provider and source context attached to acquired information. | Preserve provenance. | Provider acquisition boundary. | Provider supplies; Observation preserves. | Mandatory | Phase 1 | Provider → Observation and Market Facts contracts. | Does not transfer fact ownership to Provider. |
| Raw provider payload | Unmodified SDK/provider response object or structure. | Adapter-local decoding only. | Kite SDK. | Provider internal only. | Conditional | Phase 1 internal only | Approved adapter implementation. | May exist transiently but never becomes a contract, persisted dataset, or cross-domain object. |

**Kite completeness review across both inventories**

| Review Item | Disposition | Inventory Treatment |
| --- | --- | --- |
| Trading Halts | Not Available from Kite | Not available from Kite. Therefore not classified. |
| Circuit Limits | Included | Conditional current-quote field; no execution-validation or judgment authority. |
| Freeze Quantities | Not Available from Kite | Not available from Kite. Therefore not classified. |
| Tick Size | Included | Optional non-execution Instrument reference metadata. |
| Lot Size | Included | Optional non-execution Instrument reference metadata. |
| Instrument Status | Not Available from Kite | Not available from Kite. Therefore not classified. Canonical lifecycle state remains Instrument-owned. |
| Exchange Segment Metadata | Included | Mandatory Instrument reference fields; they do not establish Market availability. |
| Provider Rate-Limit Metadata | Included | Mandatory documented limits and provider-neutral throttling outcomes; no dynamic quota dataset is assumed. |
| API Version Metadata | Included | Optional Provider compatibility metadata. |
| Retrieval Timestamp | Included | Mandatory KRONOS request and receipt timestamps; neither is an exchange or observation timestamp. |
| Request Correlation Identifier | Not Available from Kite | Not available from Kite. Therefore not classified. |
| Response Latency Metadata | Not Available from Kite | Not available from Kite. Therefore not classified. |

## 6. Phase 1 Mandatory Inventory

Mandatory information is limited to the minimum reliable read-only foundation:

- the existing authentication profile probe as an internal connectivity capability;
- provider identity, capability, availability, acquisition outcome, redacted errors, and throttling status;
- requested/received scope, acquisition timing, partial results, missing instruments, unsupported data, and source attribution;
- approved Instrument Master reference data and provider-to-canonical mapping inputs;
- canonical identity, futures expiry/lifecycle identity, token-change handling, and historical identity preservation;
- approved analysis, reference, and execution instrument roles;
- historical timestamp, OHLCV, and historical OI facts;
- Current Quote factual market information;
- Market Schedule factual operating context from an approved authoritative source;
- requested/received historical ranges, partial responses, and missing intervals; and
- factual freshness, timestamp provenance, completeness, missing values, limitations, and zero-versus-missing semantics.

Omitting these would make identity, source, observation scope, partiality, or failure ambiguous. Mandatory classification still does not authorize retrieval.

## 7. Optional Phase 1 Inventory

Optional information may improve factual coverage but is not required for the minimum foundation:

- exchange token;
- lot size and tick size as non-execution reference metadata;
- provider/API compatibility metadata.

Optional omission must not be represented as Phase 1 failure. Provider average traded price must never be called VWAP.

## 8. Conditional Inventory

Conditional information requires a separately approved trigger:

- account entitlements and enabled exchange/product access when necessary to explain an approved Provider limitation;
- continuous futures data and replacement relationships after lifecycle/continuity decisions;
- full quote, aggregate quantities, and circuit limits after field and consumer approval;
- raw provider payload only transiently inside Provider;
- explicit exchange availability only from an approved source; and
- index references only when their existing approved model is activated.

Kite availability alone does not activate Conditional information.

## 9. Future-Phase Inventory

Future Phase information is not authorized for Phase 1:

- account identity and order permissions;
- market depth;
- WebSocket data and streaming lifecycle metadata;
- corporate actions and symbol-change workflows; and
- any Options, judgment, ranking, execution, order, position, or automated-trading information.

Future classification creates no roadmap commitment.

## 10. Explicit Exclusions

This inventory does not include or introduce:

- TradingView;
- indicators, EMA, RSI, CPR, ATR, or VWAP;
- signal generation, strategy logic, BUY/SELL logic, BUY READY/SELL READY, or BUY NOW/SELL NOW;
- scoring, confidence, ranking, or Validation judgment;
- execution, orders, positions, or portfolio automation;
- Options-specific information;
- data-quality scoring or suitability-for-trading judgment;
- persistence, databases, replay, scheduling, retries, or streaming;
- login, request-token exchange, token persistence, or refresh;
- raw Kite payloads, SDK objects, or SDK exceptions in cross-domain contracts; or
- new instrument or reference-market relationships.

## 11. Constraints

### Ownership

- Configuration owns runtime configuration, secrets, and configuration validation.
- Provider owns Kite integration, provider-specific acquisition, provider capability, provider availability, and technical acquisition results.
- Instrument owns canonical identity, classification, approved analysis/reference/execution relationships, lifecycle identity, and provider-to-canonical mapping meaning.
- Observation owns authoritative Market Facts, OHLCV, OI, accepted quote facts, and factual freshness/completeness semantics.
- Market owns Market Schedule, authoritative session meaning, and explicit Market availability.

Provider does not own Instrument Identity, Market Facts, Market Schedule, or Business Judgment. Observation answers what happened, not what it means.

### Availability and completeness

- Provider availability and Market availability are separate.
- Missing candles, quote entries, stale data, Provider connectivity/failure, and execution state cannot establish Market Schedule or OPEN/CLOSED.
- Missing and zero are separate.
- Requested and received scope are separate.
- API success and dataset completeness are separate.

### Read-only and provider isolation

- Phase 1 is read-only.
- Kite SDK objects, raw payloads, exception text, and provider-private semantics remain inside Provider.
- Provider-neutral contracts carry only approved information needed by named consumers.
- This inventory authorizes no retries, scheduling, persistence, streaming, generic Provider framework, or retrieval sequence.

### Instrument lifecycle

- Provider tokens are not canonical identifiers.
- Options rows cannot enter the Phase 1 universe.
- Expired identities and observations remain attributable.
- No rollover strategy, replacement policy, adjusted series, or canonical continuous-history method is defined.

## 12. Outstanding Questions

1. What exact approved Swing instrument universe is in Phase 1?
2. Are any planned models included beyond currently supported MCX Metals?
3. Can Kite supply the approved COMEX/NYMEX reference information, or is another Provider/source decision required?
4. Which historical intervals and lookback ranges are mandatory?
5. What factual rule identifies a completed interval without importing TradingView behavior?
6. How is unavailable historical OI represented for unsupported instruments or intervals?
7. Is continuous futures retrieval required, and which limitations must be preserved?
8. Which provider-neutral Current Quote fields belong to the Mandatory core contract, and which remain Conditional?
9. Does an approved authoritative market-calendar source exist?
10. Is Kite accepted as authoritative for any Market Schedule or EAIC-001 meaning?
11. Which provider-neutral reference fields are required without leaking Kite vocabulary?
12. What minimum provenance/completeness semantics must Observation approve before publication as Market Facts?
13. Must Phase 1 detect provider-token reuse, disappearance, or replacement without authorizing persistence?
14. Who owns future corporate-action normalization distinct from the underlying facts?

Unresolved answers remain architecture dependencies. Engineering must not infer them.

## 13. Recommended Follow-on Contracts

This inventory recommends, but does not create or approve:

1. Configuration → Provider Runtime Configuration Contract.
2. Instrument Identity Contract.
3. Provider → Instrument Reference-Support Contract.
4. Provider → Observation Acquisition Contract.
5. Market Facts Contract.
6. Market Schedule Contract.
7. Instrument Lifecycle Contract or ADR.

Each future contract must identify its producer, approved consumer, semantic scope, missing/unsupported behavior, and relationship to approved ownership.

## 14. Approval Effect

Approval applies only to the inventory, classifications, ownership interpretation, and recorded questions. It does not:

- authorize a Kite retrieval operation beyond EP-004;
- create an EDD, Engineering Package, or EP number;
- approve a follow-on contract or cross-domain dependency;
- authorize implementation or retrieval sequencing;
- activate Optional or Conditional information automatically;
- authorize persistence, retries, scheduling, streaming, or runtime changes; or
- expand approved Swing markets, instruments, products, or relationships.

## 15. Document Status

This document is **Approved** and is the canonical architecture document for KRONOS Swing — Phase 1 Market Data Foundation.

Approval does not independently authorize implementation. This document does not modify EP-004, approved Platform domains, engine ownership, data flow, or the canonical roadmap.

## Related Approved Authority

- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [KRONOS Platform Overview](../../platform/PLATFORM_OVERVIEW.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Provider Domain](../../platform/domains/provider/ARCHITECTURE.md)
- [Configuration Domain](../../platform/domains/configuration/ARCHITECTURE.md)
- [Instrument Domain](../../platform/domains/instrument/ARCHITECTURE.md)
- [Observation Domain](../../platform/domains/observation/ARCHITECTURE.md)
- [Market Domain](../../platform/domains/market/ARCHITECTURE.md)
- [EAIC-001 — Exchange Availability Interface Contract](../../interfaces/EAIC-001-Exchange-Availability-Interface-Contract.md)
- [ADL-001 — Futures Model Architecture](../../ADL-001-Futures-Model.md)
- [ADR-006 — Execution Context Provider Architecture](../../adr/ADR-006-Execution-Context-Provider-Architecture.md)
- [PP-007 — Execution Semantics Across Markets](../../principles/PP-007-Execution-Semantics-Across-Markets.md)
- [EP-004 — Minimum Read-Only Kite Connectivity](../../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md)
