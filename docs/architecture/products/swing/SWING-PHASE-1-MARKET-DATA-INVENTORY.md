# Swing Phase 1 — Market Data Inventory

**Document ID:** ADP-001A
**Title:** Swing Phase 1 — Market Data Inventory
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Not stated
**Classification:** Architecture Documentation Package

**Owner:** Chief Architect

**Prepared By:** Engineering Architect

**Approved By:** Chief Architect
**Review Authority:** Not stated
**Repository Location:** `docs/architecture/products/swing/SWING-PHASE-1-MARKET-DATA-INVENTORY.md`

**Product:** KRONOS Swing

**Phase:** Phase 1 — Market Data Foundation

**Architecture Impact:** Approved Swing product-consumption inventory aligned with the canonical Provider → EAIC-002 → Instrument architecture

**Engineering Impact:** None

**Runtime Impact:** None

## 1. Purpose

Define the authoritative inventory of market information that KRONOS Swing may require and consume during Phase 1 — Market Data Foundation.

This inventory classifies Swing product-consumption requirements only. It does not constrain Provider acquisition to the Swing product universe and does not approve a dataset, capability, Dataset Permission, Acquisition Authority, retrieval operation, endpoint, Engineering Design Document, Engineering Package, persistence model, streaming model, runtime authority, or implementation sequence.

## 2. Scope

Phase 1 asks whether Swing can consume approved canonical and factual information required by its product scope while preserving Provider, Configuration, Instrument, Observation, Market, Validation, Risk, Execution, and product boundaries.

This document evaluates authenticated read-only access, instrument reference information, historical OHLCV and Open Interest, mandatory current quote facts, provider acquisition metadata, market-session information where an authoritative source exists, existing approved analysis/reference/execution relationships, and factual provenance and completeness metadata.

It does not expand approved Swing relationships. MCX Metals remains the currently supported model. Planned models or configuration scaffolding do not become supported merely by appearing in this inventory. Product membership and Product Eligibility remain independent from Provider acquisition and canonical Instrument identity.

## 3. Architectural Principles

1. Availability from a Provider does not equal permission, authority, or Swing Product Eligibility.
2. Provider acquisition remains Provider-owned and does not create canonical Instrument or product meaning.
3. Provider Instrument Master records remain Provider-owned and are not canonical Instruments.
4. Provider-native identifiers, instrument tokens, exchange tokens, symbols, and row positions are not permanent KRONOS identities.
5. Missing data and zero are different states.
6. HTTP or API success does not prove dataset completeness.
7. Missing quote entries must remain explicit.
8. Partial historical responses must remain explicit.
9. Provider availability is not Market availability.
10. Missing data must not be used to infer exchange closure.
11. Current OHLC snapshots are not completed historical candles.
12. Historical OI and current OI must remain distinct.
13. Continuous futures data must not automatically be described as adjusted or canonical continuous history.
14. Options rows returned within an authorized Instrument Master acquisition remain preserved Provider records but must not enter the approved Swing Phase 1 product universe unless separately authorized.
15. No dataset may create Business Judgment, Risk Approval, Execution authority, Orders, or Positions.
16. This inventory defines no read or write acquisition authority.
17. No persistence model is authorized by this inventory.
18. No streaming model is authorized by this inventory.
19. No retrieval sequence is authorized by this inventory.

Provider owns acquisition, Provider Catalogue, Provider-and-Dataset Catalogue Partitions, Provider Snapshot Identity, Provider Snapshots, Provider Record Identity, Provider Records, Provider dispositions, Submission Eligibility, Requested Acquisition Scope, Received Acquisition Scope, acquisition outcomes, Provider Context, Provider Capability, Provider Entitlement, and Provider provenance. Instrument owns EAIC-002 technical receipt and contract validation, Interpretation Admission, interpretation, canonical identity, canonical classification, Provider mapping, Provider Mapping Status, cross-Provider reconciliation, relationships, lifecycle semantics, Instrument Identity Contract publication, and Canonical Instrument Catalogue publication. Swing and other products are downstream consumers that own only their respective product universes, Product Eligibility, consumption, and product meanings. Observation owns factual market observations. Market owns market-session and schedule meaning. Configuration owns runtime configuration. Reuse and dependency do not transfer ownership.

For Instrument Master only, EAIC-002 is the sole Provider → Instrument architectural boundary. Provider shall not populate Instrument directly. Products and Observation shall not consume Provider Catalogue internals or EAIC-002 envelopes.

## 4. Classification Definitions

| Classification | Definition |
| --- | --- |
| Mandatory | Required by the approved Swing Phase 1 consumption boundary to remain attributable, identity-safe, factually scoped, or operationally distinguishable from failure. Classification does not authorize acquisition or retrieval. |
| Optional | May improve Swing Phase 1 factual coverage or diagnostics but is not required for the minimum product-consumption foundation. |
| Conditional | May be consumed only when an approved product scope, authoritative source, consumer, Provider capability, Dataset Permission, Acquisition Authority, engineering design, runtime authority, and applicable contract establish the need. |
| Future Phase | Not required or authorized for Phase 1. Availability from Kite creates no permission. |

Every named dataset below has exactly one classification. Entries sharing a row share the stated classification and rationale.

## 5. Dataset Inventory

### A. Market Information

| Dataset Name | Description | Swing Consumption Purpose | Expected Source | Semantic Owner(s) | Classification | Phase | Dependencies | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Instrument Master | Provider-owned reference records describing instruments exposed by one approved Provider operation. | Support later Instrument interpretation and canonical outputs consumed by Swing; not a direct product input. | Kite instrument reference data. | Provider owns acquisition, Catalogue and records; Instrument owns interpretation, identity and mapping. | Mandatory | Phase 1 | ADR-009 and EAIC-002 for Instrument Master only. | Complete returned records remain preserved within the Provider Catalogue independently of Swing membership; Options rows are not discarded merely because Swing does not consume them. |
| Provider instrument token | Provider-scoped retrieval identifier. | Preserve attributable Provider reference evidence for Instrument-owned mapping. | Kite Instrument Master. | Provider owns the identifier; Instrument owns mapping meaning and status. | Mandatory | Phase 1 | EAIC-002 and Instrument-owned mapping architecture. | Never a permanent KRONOS identity and never establishes cross-Provider equivalence. |
| Exchange token | Exchange-scoped reference identifier where supplied. | Trace provider/exchange records. | Kite Instrument Master. | Provider | Optional | Phase 1 | Provider reference capability. | Cannot replace canonical identity. |
| Trading symbol; exchange; segment; instrument type; instrument name or underlying reference | Provider-owned reference fields that may support Instrument interpretation, classification, mapping and reconciliation. | Support canonical Instrument outputs later consumed explicitly by Swing. | Kite Instrument Master. | Provider owns supplied fields; Instrument owns canonical interpretation, classification, mapping and reconciliation. | Mandatory | Phase 1 | EAIC-002, Instrument Identity Contract and Canonical Instrument Catalogue. | Provider vocabulary must not become canonical by implication; exchange does not establish OPEN/CLOSED or product membership. |
| Expiry | Provider-recorded expiry assertion for expiring instruments. | Support Instrument-owned lifecycle and identity interpretation. | Kite Instrument Master. | Provider owns its assertion; Instrument owns lifecycle and canonical identity meaning. | Mandatory | Phase 1 | EAIC-002 and Instrument Lifecycle architecture. | Does not define rollover or product eligibility. |
| Lot size; tick size | Provider instrument reference values. | Preserve non-execution reference evidence where explicitly consumed. | Kite Instrument Master. | Provider owns supplied values; any accepted canonical meaning requires Instrument authority. | Optional | Phase 1 | EAIC-002 and approved Instrument publication. | Not used by this inventory for risk, sizing, price validation, or orders. |
| Instrument lifecycle state | Canonical active, expired, or historical identity status. | Preserve identity across expiry and token changes. | Instrument interpretation of approved references. | Instrument | Mandatory | Phase 1 | Instrument Lifecycle decision or contract. | Provider supports but does not own the meaning. |
| Historical timestamp; open; high; low; close; volume | One historical OHLCV observation and its time. | Consume attributable historical facts after separately governed acquisition and Observation establishment. | Kite historical data where separately authorized. | Observation | Mandatory | Phase 1 | Separate historical-data capability, permission, acquisition, design, runtime and contract authority; Instrument attribution. | Outside ADR-009 and EAIC-002; timestamp provenance is explicit; zero and missing volume differ. |
| Historical Open Interest | OI attached to historical observations where supported. | Consume derivatives interest facts after separately governed acquisition and Observation establishment. | Kite historical data where separately authorized. | Observation | Mandatory | Phase 1 | Separate Futures OI and historical-data authorities plus Market Facts contract. | Outside ADR-009 and EAIC-002; distinct from current OI and interpretation. |
| Continuous historical futures data | Provider-produced continuous futures history where supported. | Evaluate continuity coverage. | Kite historical data where available. | Observation facts; Instrument identity association. | Conditional | Phase 1 if approved | Instrument Lifecycle and continuous-data decisions. | Not adjusted, canonical, or rollover-safe by default. |
| Requested historical range; received historical range; partial historical response; missing historical intervals | Requested and actual time coverage plus explicit partiality and gaps. | Prevent false completeness in separately authorized historical-data consumption. | Provider request/result and Observation acceptance. | Provider owns acquisition scope and outcomes; Observation owns accepted factual scope. | Mandatory | Phase 1 | Separate historical-data authorities and applicable contract. | Outside ADR-009 and EAIC-002; API success does not clear partiality; gaps do not imply closure. |
| Last traded price; current OHLC snapshot; current Open Interest; OI day high and low; traded volume; last trade quantity; average traded price; last trade timestamp; exchange timestamp | Current factual snapshot fields. | Consume current non-streaming factual market information after separately governed acquisition and Observation establishment. | Kite quote capability where separately authorized. | Observation | Mandatory | Phase 1 | Separate Quote and Futures OI capability, permission, acquisition, design, runtime and contract authority; Instrument attribution. | Outside ADR-009 and EAIC-002. Inclusion is a Swing requirement, not acquisition authority. Current OHLC is not a completed candle; historical/current OI differ; average traded price is not VWAP. |
| Full quote snapshot | Approved provider-neutral subset of a full quote. | Consolidate current facts when a consumer is approved. | Kite full quote. | Observation | Conditional | Phase 1 if approved | Explicit quote-field contract. | Raw quote payload and SDK object stay inside Provider. |
| Aggregate buy quantity; aggregate sell quantity; circuit limits | Provider-reported current quote fields. | Preserve optional venue facts where justified. | Kite full quote. | Observation for accepted facts. | Conditional | Phase 1 if approved | Explicit field definitions and consumer. | No imbalance scoring, execution validation, or judgment. |
| Bid market depth; ask market depth; depth price; depth quantity; depth order count | Market-depth records. | Future microstructure observation. | Kite quote/streaming capability. | Observation | Future Phase | Future | Market-depth contract and approved use. | Not justified by approved Phase 1 Swing architecture. |
| WebSocket quote data; WebSocket OI; WebSocket timestamps; subscription metadata; stream availability metadata | Streaming content and lifecycle metadata. | Future live-data acquisition. | Kite streaming service. | Provider acquisition; Observation accepted facts. | Future Phase | Future | Streaming architecture and contracts. | No streaming model or subscription is authorized; stream availability is not Market availability. |
| Trading session calendar; trading days; holidays; special sessions; market open and close times | Authoritative Market Schedule definitions. | Distinguish scheduled sessions from acquisition failure. | Approved authoritative calendar; Kite suitability unresolved. | Market | Mandatory | Phase 1 | Market Schedule Contract and approved source. | Market Schedule provides factual operating context required to correctly interpret market-data availability. It is market metadata, not business judgment. Must not be inferred from data presence/absence or Provider state. |
| Explicit exchange availability | Approved OPEN/CLOSED meaning. | Present explicitly known exchange state. | Approved source under EAIC-001. | Market | Conditional | Phase 1 if required | EAIC-001 and approved source. | Missing/stale data, Provider state, and execution state are prohibited inputs. |
| Active contract; expired contract; provider-token changes; futures expiry; historical identity preservation | Canonical futures lifecycle identity and historical traceability. | Keep facts attributable across expiry and provider changes. | Instrument using approved reference material. | Instrument | Mandatory | Phase 1 | Instrument Lifecycle decision or contract. | Does not imply execution permission or rollover. |
| Replacement contract; continuous futures limitations | Explicit successor relationship or provider continuity limitation where approved. | Support lifecycle/continuity review. | Instrument and Provider capability records. | Instrument relationship; Provider supplies limitations. | Conditional | Phase 1 if approved | Instrument Lifecycle/continuous-data decision. | No automatic replacement, rollover, adjustment, or canonical series. |
| Splits; dividends; bonuses; mergers; symbol changes | Corporate-action or identity-change information. | Future cash-history and identity context. | Approved corporate-action/reference source. | Observation facts; Instrument identity effects. | Future Phase | Future | Corporate-action and lifecycle architecture. | Not required by current approved Swing futures scope. |
| Analysis instruments; reference instruments; execution instruments | Instrument-owned canonical roles under existing approved Swing relationships. | Consume approved roles without recreating Instrument meaning. | Instrument Identity Contract and Canonical Instrument Catalogue. | Instrument owns roles; Swing owns product-universe membership and consumption. | Mandatory | Phase 1 | Explicit product-consumption boundary, ADL-001 and PP-007. | No new relationship, mapping, identity or execution permission. |
| Reference-market futures | Approved futures providing reference context. | Obtain existing required reference-market information. | Kite if supported; otherwise unresolved source. | Instrument identity; Observation facts. | Mandatory | Phase 1 | Existing ADL-001 relationships and acquisition contracts. | Kite coverage for approved COMEX/NYMEX references is not established; no substitute may be invented. |
| Index references | Approved benchmark identities/data when an existing model is activated. | Support approved benchmark relationships. | Kite if supported and separately approved. | Instrument identity; Observation facts. | Conditional | Phase 1 if model activated | Existing approved relationship and contracts. | Does not activate NSE Swing or create a benchmark relationship. |
| Freshness; source attribution; timestamp provenance; completeness; partiality; missing values; unsupported fields; provider limitations; zero versus missing; request success versus dataset completeness | Factual quality and provenance dimensions without scoring or judgment. | State exactly what was observed, from where, when, and with what limits. | Separately governed Provider evidence and Observation establishment. | Provider owns technical acquisition evidence; Observation owns factual semantics. | Mandatory | Phase 1 | Dataset-specific authorities, Instrument attribution and Market Facts contracts. | No direct Observation dependency on Provider internals; no quality/confidence score, validation judgment, or suitability-for-trading judgment. |

Instrument Master `last_price`, when supplied by Kite, is auxiliary provider metadata and is not classified as an independent architectural dataset. It is not part of Canonical Instrument Identity, it is not Current Quote, and it must never replace Observation-owned market state.

### Instrument Master and Dataset Authority Boundary

ADR-009 and EAIC-002 govern Instrument Master only. They do not govern or authorize Futures OI, Options OI, quotes, historical data, streaming, market depth, option-chain data, or any similar Provider dataset.

Each excluded dataset requires its own separately approved:

- Provider Capability;
- Dataset Permission;
- Acquisition Authority;
- engineering design;
- runtime authority; and
- applicable contract dependency.

The classifications in this inventory express Swing consumption requirements and priorities only. They shall not be interpreted as any of those authorities.

Provider acquisition shall not be filtered by Swing membership, Swing Product Eligibility, current product demand, or canonical identity before acquisition. Within one separately authorized Instrument Master operation, Provider shall preserve the complete returned dataset subject only to ADR-009 record-representation and security restrictions. Non-Swing records, including Options records, shall not be discarded merely because Swing does not consume them.

### B. Operational Information

| Dataset Name | Description | Swing Consumption Purpose | Expected Source | Semantic Owner(s) | Classification | Phase | Dependencies | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Authentication profile probe | One authenticated read-only technical probe whose profile payload is discarded. | Confirm Provider connectivity. | Kite `profile()` through EP-004. | Provider | Mandatory | Phase 1 | Runtime configuration; externally acquired token. | Already implemented. Mandatory as capability, not as a published account dataset. |
| Account identity | Personal or provider account identifiers. | Account administration only. | Kite profile. | Unresolved; not a Market Fact. | Future Phase | Future | Separate account/security architecture. | Not required for market information and remains discarded under EP-004. |
| Account entitlements; enabled exchanges; enabled products | Provider-reported account entitlement evidence that might explain bounded access context. | Consume a separately approved Provider entitlement output if required. | Kite account/provider metadata where available. | Provider | Conditional | Phase 1 if approved | ADR-008, EDD-003 and a named product-consumption boundary. | Does not establish Provider Capability, Dataset Permission, Acquisition Authority, product membership, or Market availability. |
| Enabled order types | Provider-reported Order-Type Entitlement evidence. | No Phase 1 market-information requirement. | Kite profile metadata where available. | Provider owns entitlement evidence; later execution meaning remains separately governed. | Future Phase | Future | ADR-008 and separate execution architecture if ever relevant. | Does not authorize orders or execution. |
| Provider identity; Provider Capability; Provider Operational Availability | Provider source, supported technical surface, and technical operational availability. | Attribute source and distinguish technical support or failure. | Provider integration boundary. | Provider | Mandatory | Phase 1 | EDD-001, ADR-007 and approved Provider contracts. | Provider Capability is not Provider Entitlement, Dataset Permission, Acquisition Authority, or usability; Provider Operational Availability is not Market availability or completeness. |
| API response status; error category; rate-limit or throttling metadata | Stable provider-neutral technical acquisition outcomes. | Explain failure, unsupported requests, and throttling safely. | Provider adapter. | Provider | Mandatory | Phase 1 | Provider acquisition contract. | No raw SDK exceptions/messages; does not authorize retry design. |
| API version or compatibility metadata | Compatibility facts required for safe provider review. | Support controlled provider/SDK compatibility. | Provider adapter and dependency record. | Provider | Optional | Phase 1 | Provider Integration Contract. | No SDK object exposure. |
| Request time; receipt time | KRONOS request and response receipt times. | Acquisition provenance and latency boundary. | Provider. | Provider | Mandatory | Phase 1 | Provider acquisition contract. | Neither is an exchange or observation timestamp. |
| Requested dataset scope; received dataset scope | Requested and actual instruments, fields, intervals, and range. | State acquisition intent and coverage for a separately authorized dataset. | Provider request/result. | Provider owns acquisition scope; Observation owns only separately accepted factual scope. | Mandatory | Phase 1 | Dataset-specific authority and applicable governed contract. | Must remain distinct; creates no direct Observation access to Provider internals. |
| Missing-instrument result; unsupported-data result; partial-result status | Explicit non-success and incomplete-result states. | Prevent empty/partial data from appearing complete. | Provider acquisition result. | Provider technical; Observation factual acceptance where applicable. | Mandatory | Phase 1 | Provider capability and acquisition contracts. | Unsupported, unavailable, missing, and partial are distinct. |
| Source attribution | Provider and source context attached to acquired information. | Preserve provenance through separately governed boundaries. | Provider acquisition boundary. | Provider owns acquisition provenance; downstream domains preserve attributable references without ownership transfer. | Mandatory | Phase 1 | Dataset-specific contract, Instrument attribution where applicable, and Market Facts contract. | Does not create a direct Observation dependency on Provider or transfer fact ownership to Provider. |
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
- approved Instrument Master support through Provider-owned acquisition and EAIC-002, without direct Swing consumption of Provider records;
- Instrument-owned canonical identity, Provider mapping, futures expiry/lifecycle identity, token-change interpretation, historical identity preservation, and Canonical Instrument Catalogue publication;
- explicit Swing consumption of approved analysis, reference, and execution Instrument roles;
- historical timestamp, OHLCV, and historical OI facts;
- Current Quote factual market information;
- Market Schedule factual operating context from an approved authoritative source;
- requested/received historical ranges, partial responses, and missing intervals; and
- factual freshness, timestamp provenance, completeness, missing values, limitations, and zero-versus-missing semantics.

Omitting these would make product consumption, identity attribution, source, observation scope, partiality, or failure ambiguous. Mandatory classification still does not authorize acquisition, retrieval, runtime operation, or a cross-domain dependency.

## 7. Optional Phase 1 Inventory

Optional information may improve factual coverage but is not required for the minimum foundation:

- exchange token;
- lot size and tick size as non-execution reference metadata;
- provider/API compatibility metadata.

Optional omission must not be represented as Phase 1 failure. Provider average traded price must never be called VWAP.

## 8. Conditional Inventory

Conditional information requires a separately approved trigger:

- Provider-reported entitlement outputs when separately approved for a named product-consumption need;
- continuous futures data and replacement relationships after lifecycle/continuity decisions;
- full quote, aggregate quantities, and circuit limits after field and consumer approval;
- raw provider payload only transiently inside Provider;
- explicit exchange availability only from an approved source; and
- index references only when their existing approved model is activated.

Provider availability alone does not activate Conditional information.

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
- Provider owns Provider integration, Provider Context, Provider Capability, Provider Entitlement, dataset acquisition, Provider Catalogue, Provider-and-Dataset Catalogue Partitions, Provider Snapshot Identity, Provider Snapshots, Provider Record Identity, Provider Records, dispositions, Submission Eligibility, Requested Acquisition Scope, Received Acquisition Scope, acquisition outcomes, Provider provenance, Provider Operational Availability, and technical acquisition results.
- Instrument owns EAIC-002 technical receipt and contract validation, Interpretation Admission, interpretation, canonical identity, classification, approved analysis/reference/execution relationships, lifecycle identity, Provider mapping, Provider Mapping Status, cross-Provider reconciliation, Instrument Identity Contract publication, and Canonical Instrument Catalogue publication.
- Swing owns only its product universe, Product Eligibility, explicit consumption, evidence requirements, validation requirements, decision semantics, and risk interpretation.
- Observation owns authoritative Market Facts, OHLCV, OI, accepted quote facts, and factual freshness/completeness semantics.
- Market owns Market Schedule, authoritative session meaning, and explicit Market availability.

Provider does not own Instrument Identity, Provider mapping, product membership, Market Facts, Market Schedule, or Business Judgment. Instrument does not own Provider acquisition, Provider Catalogue, Provider records, dispositions, Submission Eligibility, or product membership. Products do not perform acquisition, Instrument interpretation, canonical identity establishment, Provider mapping, cross-Provider reconciliation, or Observation establishment. Observation answers what happened, not what it means.

### Direction and governed boundaries

- Provider → EAIC-002 → Instrument is a platform-support and contract path for Instrument Master only, not a business-pipeline stage.
- EAIC-002 is the sole Provider → Instrument boundary for that dataset.
- Provider shall not populate Instrument directly, and Instrument shall not access or mutate Provider Catalogue internals.
- Products consume only approved canonical Instrument outputs through separately approved explicit product-consumption contracts.
- Observation consumes canonical Instrument identity through the separately governed Instrument-to-Observation attribution boundary.
- Products and Observation shall not consume Provider Catalogue records, Provider Snapshots, Provider Records, Submission Eligibility, or EAIC-002 envelopes directly.
- The canonical business pipeline remains Instrument → Observation → Validation → Risk → Execution → Portfolio.

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
- This inventory authorizes no Provider operation, endpoint invocation, retries, scheduling, persistence, streaming, generic Provider framework, or retrieval sequence.

### Instrument lifecycle

- Provider tokens are not canonical identifiers.
- Options rows returned within an authorized Instrument Master acquisition remain Provider-owned records but cannot enter the Swing Phase 1 product universe without separate product authority.
- Expired identities and observations remain attributable.
- No rollover strategy, replacement policy, adjusted series, or canonical continuous-history method is defined.

## 12. Resolved and Outstanding Architecture Dependencies

The coordinated migration resolves the following former questions:

1. ADP-001I governs the approved Swing Phase 1 product universe.
2. Planned products and models do not enter that universe merely because Provider records or configuration exist.
3. ADR-009 governs Provider-bounded Instrument Master acquisition independently of product membership.
4. EAIC-002 is the sole Provider → Instrument boundary for Instrument Master.
5. Instrument owns interpretation, canonical identity, Provider mapping, cross-Provider reconciliation, and Canonical Instrument Catalogue publication.
6. Swing is a downstream consumer and does not perform acquisition, interpretation, canonical identity establishment, or mapping.

The following matters remain separately governed or unresolved:

1. approved Provider capability, Dataset Permission, Acquisition Authority, engineering design, runtime authority, and contract dependency for historical data, Futures OI, quotes, streaming, market depth, and every other dataset outside Instrument Master;
2. mandatory historical intervals and lookback ranges;
3. factual completed-interval meaning without importing TradingView behavior;
4. unavailable historical OI representation for unsupported instruments or intervals;
5. continuous-futures requirements and limitations;
6. provider-neutral Current Quote field contracts;
7. authoritative Market Schedule source and any EAIC-001 source authority;
8. minimum Observation provenance and completeness semantics;
9. Provider-token reuse, disappearance, or replacement treatment within Instrument-owned interpretation and mapping; and
10. future corporate-action fact and identity-effect boundaries.

Engineering shall not infer unresolved answers or reuse ADR-009 or EAIC-002 as authority for excluded datasets.

## 13. Governing and Future Contract Boundaries

The following boundaries already govern:

1. EAIC-002 governs Provider → Instrument submission for Instrument Master only.
2. The Instrument Identity Contract and Canonical Instrument Catalogue publish Instrument-owned canonical meaning.
3. The approved Instrument-to-Observation attribution boundary governs canonical identity attribution without transferring Instrument ownership.

The following require separate approval where applicable:

1. explicit Swing product-consumption contract;
2. dataset-specific Provider support and acquisition contracts for every dataset outside Instrument Master;
3. Market Facts Contract;
4. Market Schedule Contract; and
5. further Instrument Lifecycle architecture where unresolved.

This inventory creates, approves, activates, or implements none of those future boundaries.

## 14. Approval Effect

Approval applies only to the inventory, classifications, ownership interpretation, and recorded questions. It does not:

- authorize any Provider retrieval operation or endpoint invocation;
- create an EDD, Engineering Package, or EP number;
- approve a follow-on contract or cross-domain dependency;
- authorize implementation or retrieval sequencing;
- activate Optional or Conditional information automatically;
- authorize persistence, retries, scheduling, streaming, or runtime changes; or
- expand approved Swing markets, instruments, products, or relationships.

Approval does not activate ADR-009 or EAIC-002 and does not authorize EDD-004.

## 15. Document Status

This document is **Approved** architecture for KRONOS Swing — Phase 1 Market Data Foundation. Its metadata and the Document Register continue to record Canonical Status as Not stated.

Approval does not independently authorize implementation. WP-B6 aligns this document with ADR-009, MIG-001, EAIC-002, the migrated Provider and Instrument domains, the Domain Ownership Matrix, the Domain Dependency Matrix, DATA_FLOW, ADP-001B, ADP-001J, ADP-001I, and the supersession of ADP-001C. ADR-009 Version 1.0, DOMAIN-006 Provider Domain Architecture, and EAIC-002 Version 0.1 supersede ADP-001H, which remains historical predecessor traceability only. No runtime, implementation, activation, or EDD-004 authority is introduced.

## Related Approved Authority

- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [ADR-007 — Provider Capability Assessment Architecture](../../platform/domains/provider/ADR-007-PROVIDER-CAPABILITY-ASSESSMENT-ARCHITECTURE.md)
- [ADR-008 — Provider Entitlement Assessment Architecture](../../platform/domains/provider/ADR-008-PROVIDER-ENTITLEMENT-ASSESSMENT-ARCHITECTURE.md)
- [MIG-001 — ADR-009 Coordinated Architecture Migration Package](../../migrations/MIG-001-ADR-009-COORDINATED-ARCHITECTURE-MIGRATION-PACKAGE.md)
- [EAIC-002 — Provider → Instrument Submission Contract](../../interfaces/EAIC-002-PROVIDER-TO-INSTRUMENT-SUBMISSION-CONTRACT.md)
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
- [ADP-001H — Superseded Provider Instrument Master Acquisition predecessor (historical traceability only)](SWING-PHASE-1-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-CAPABILITY-AND-CONTRACT.md)
- [ADP-001B — KRONOS Swing Instrument Identity Architecture](SWING-PHASE-1-INSTRUMENT-IDENTITY-ARCHITECTURE.md)
- [ADP-001J — Instrument Interpretation and Canonical Identity Establishment Architecture](SWING-PHASE-1-INSTRUMENT-INTERPRETATION-AND-CANONICAL-IDENTITY-ESTABLISHMENT-ARCHITECTURE.md)
- [ADP-001I — Swing Phase 1 Approved Instrument Universe and Reference Semantics Architecture](SWING-PHASE-1-APPROVED-INSTRUMENT-UNIVERSE-AND-REFERENCE-SEMANTICS-ARCHITECTURE.md)
- [ADP-001C — Superseded Provider → Instrument Contract (historical predecessor)](SWING-PHASE-1-PROVIDER-INSTRUMENT-CONTRACT.md)
- [EP-004 — Minimum Read-Only Kite Connectivity](../../../engineering/ep/EP-004-MINIMUM-READ-ONLY-KITE-CONNECTIVITY.md)
