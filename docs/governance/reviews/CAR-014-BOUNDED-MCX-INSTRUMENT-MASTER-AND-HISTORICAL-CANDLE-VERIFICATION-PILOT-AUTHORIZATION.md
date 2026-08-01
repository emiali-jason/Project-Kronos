# CAR-014 — Bounded MCX Instrument Master and Historical Candle Verification Pilot Authorization

**Document ID:** CAR-014
**Title:** Bounded MCX Instrument Master and Historical Candle Verification Pilot Authorization
**Version:** 1.0
**Status:** Approved
**Canonical Status:** Canonical
**Classification:** Review Package
**Owner:** Chief Architect
**Prepared By:** Engineering Architect
**Review Authority:** Chief Architect
**Repository Location:** `docs/governance/reviews/CAR-014-BOUNDED-MCX-INSTRUMENT-MASTER-AND-HISTORICAL-CANDLE-VERIFICATION-PILOT-AUTHORIZATION.md`
**Workflow Stage:** Repository Publication
**Decision:** APPROVE WITH CONDITIONS
**Implementation Authorization:** Authorized with Constraints — CAR-014 pilot-only implementation
**Runtime Authority:** None — deferred to CAR-014 Version 1.1
**Provider Endpoint Authority:** None — deferred to CAR-014 Version 1.1
**Credential-Use Authority:** None — deferred to CAR-014 Version 1.1
**Token-Generation Authority:** Withheld
**Repository:** `emiali-jason/Project-Kronos`
**Authoritative Branch:** `develop`
**Implementation Baseline:** `14948c6f872c28b01401909364f13b53286326be`

---

# 1. Purpose

This Chief Architect decision authorizes implementation publication and offline verification of one isolated pilot-local utility for a future bounded MCX Instrument Master and historical-candle verification attempt.

Version 1.0 authorizes no live use. Possession, publication, import, launch or successful offline testing of the pilot code does not authorize credentials, SDK client construction for live use, Provider communication, Instrument Master invocation or historical-data invocation.

The pilot is not the production Provider implementation, Provider Catalogue, Instrument interpretation, Observation, Market Facts, Validation, product GUI or trading system.

# 2. Governing Basis

CAR-014 is bounded by:

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md);
- [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md);
- [EDD-004 — Provider Instrument Master Acquisition Engineering Design](../../engineering/edd/EDD-004-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-ENGINEERING-DESIGN.md);
- [CAR-011 Version 1.1 — consumed Kite profile pilot outcome](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md);
- [CAR-012 — CAR-011 transport-boundary clarification](CAR-012-CAR-011-PROFILE-OPERATION-AND-TRANSPORT-BOUNDARY-CLARIFICATION.md);
- [DOC-001 — Document Identification, Classification & Metadata Standard](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md); and
- [Document Register](../../indexes/DOCUMENT-REGISTER.md).

This pilot-specific implementation authority does not amend or activate production architecture or EDD-004 implementation. Historical-candle verification is a separately bounded pilot concern and creates no architecture, persistence, downstream publication or product authority.

# 3. Decision

> **APPROVE WITH CONDITIONS**

Version 1.0 authorizes only:

1. this CAR-014 Version 1.0 record;
2. its single Document Register entry;
3. one pilot-local headless engine;
4. one pilot-local standard-library tkinter GUI;
5. one fake-only offline test file;
6. offline verification of the hard activation gate, combined one-attempt boundary, deterministic selection, sanitized evidence and prohibited surface; and
7. one combined code-and-documentation commit and push after Engineering Architect review.

No authority shall be inferred beyond those grants.

# 4. Three-Stage Lifecycle

## 4.1 Version 1.0 — Implementation Publication

Version 1.0 authorizes implementation publication and offline verification only.

It grants no credential use, live runtime, Provider endpoint, SDK client construction for live use, Instrument Master call or historical-data call.

## 4.2 Version 1.1 — Live Activation Authority

Version 1.1 is absent and separately required before any live operation. It must freeze:

- the implementation commit SHA;
- local non-production environment identifier;
- authority expiry;
- frozen execution date;
- exact historical start;
- exact historical end;
- timezone;
- credential-use boundary;
- one combined attempt authority;
- exact endpoint grants;
- runtime grant;
- interval `5minute`;
- `continuous=False`; and
- `oi=False`.

Version 1.1 publication, a fresh preflight and a new explicit Sponsor execution instruction are all mandatory. No one condition implies another.

## 4.3 Version 1.2 — Sanitized Outcome

Version 1.2 is reserved exclusively for the sanitized result and consumed-authority state. It creates no renewed or second-attempt authority.

# 5. Hard Activation Gate

Before SDK construction, the engine shall require one immutable `LiveActivationContext` that proves:

1. `car_id` is exactly `CAR-014`;
2. `car_version` is exactly `1.1`;
3. authority is unexpired;
4. implementation SHA is present;
5. environment identifier is present;
6. frozen execution date is present;
7. historical start and end are present and form a completed 60-minute window;
8. timezone is present;
9. start precedes end;
10. interval is exactly `5minute`;
11. `continuous` is exactly `False`;
12. `oi` is exactly `False`;
13. the supplied execution plan exactly equals the frozen activation plan; and
14. execution has not already started in the process.

Any invalid or absent context shall produce only:

`LIVE_EXECUTION_NOT_AUTHORIZED_CAR_014_VERSION_1_1_REQUIRED`

The invalid path invokes no SDK factory, constructs no SDK client and reaches no Provider method.

# 6. Combined Authority-Consumption Boundary

CAR-014 uses one combined attempt. After valid activation, local credential validation and final Sponsor confirmation, the engine shall mark execution started and authority consumed before SDK construction and before Stage 1.

The process-lifetime state shall never reset. There is no second Stage 1, independent Stage 2, corrected-token attempt, retry, automatic repeat, re-probe or relaunch authority.

SDK construction failure, credential rejection, Stage 1 failure, absent selection, ambiguity, transport failure or Stage 2 failure consumes the entire authority once execution begins.

Sanitized evidence shall separately record whether each stage was initiated and completed and whether CAR-014 authority was consumed.

# 7. Pilot-Local SDK Boundary

The private adapter may reach only:

- one future `instruments("MCX")` operation;
- one future `historical_data(...)` operation after deterministic Stage 1 success; and
- one local HTTP-session close where construction occurred.

The raw SDK object remains private. The adapter exposes no generic request method, mutation, token lifecycle, alternate endpoint or raw response. The GUI never receives the adapter, SDK object, numeric instrument token, Instrument Master rows or candle rows.

# 8. Stage 1 — MCX Instrument Master Verification

When separately activated, Stage 1 shall invoke `instruments("MCX")` exactly once with no retry or endpoint loop. Records remain transient and are inspected only for the minimum fields required by the closed selection expectation.

The exact Provider futures classification is `FUT`. An otherwise qualifying record with any other instrument type produces `FUTURES_CLASSIFICATION_UNRESOLVED` and blocks Stage 2. No alternative meaning may be inferred.

A record qualifies only when:

1. normalized exchange is exactly `MCX`;
2. normalized name or underlying is exactly `GOLD`;
3. normalized instrument type is exactly `FUT`;
4. segment, when present, does not conflict with MCX futures;
5. the trading symbol conforms to the closed standard-GOLD futures form;
6. expiry is present, parseable and strictly later than the frozen execution date;
7. the token is present and integer-compatible; and
8. no field conflicts with standard GOLD classification.

`GOLDM`, `GOLDGUINEA`, `GOLDPETAL`, options, continuous instruments, expired contracts and ambiguous records are excluded. Fuzzy and substring matching are prohibited.

Qualifying records are sorted by expiry, normalized trading symbol and finally the numeric token as an internal tie-break only. Conflicting duplicates, public-fact ambiguity and records that differ only by token block Stage 2.

The numeric token exists only as a transient internal reference for Stage 2 and shall never enter evidence, representation, serialization, GUI output, logs or exceptions. The complete Instrument Master response is discarded after bounded analysis.

# 9. Stage 1 Sanitized Evidence

Stage 1 evidence is limited to:

- initiated and completed flags;
- controlled outcome category;
- total and qualifying record counts;
- required-field presence matrix;
- expected futures value and whether exact `FUT` was observed;
- expiry and token representation types;
- selected exchange, public trading symbol, expiry and instrument type;
- deterministic-selection result;
- ambiguity category;
- payload-discard confirmation; and
- `numeric-token-retained-in-evidence: false`.

It contains no numeric token, raw row, complete response, credential, SDK object or raw exception.

# 10. Stage 2 — Historical Candle Verification

Stage 2 is reachable only in the same consumed attempt after one valid deterministic Stage 1 selection. Its one future operation is exactly bounded by the frozen token, start, end, timezone and flags:

- interval `5minute`;
- `continuous=False`; and
- `oi=False`.

It shall invoke historical data exactly once with no retry or endpoint loop. Bounded in-memory inspection may verify OHLCV structure, timestamps, ordering, duplicates, spacing, missingness and value types. No OHLCV numeric value or complete candle row may be retained.

The raw candle response and transient token reference are discarded before outcome presentation.

# 11. Stage 2 Sanitized Evidence

Stage 2 evidence is limited to:

- initiated and completed flags;
- controlled outcome category;
- requested interval, historical bounds, timezone, continuous and OI flags;
- row count;
- key-presence and value-type matrices;
- first and last returned timestamps;
- timezone or offset observation;
- chronological-order result;
- duplicate-timestamp count;
- interval-spacing result;
- null and missing-value counts; and
- raw-payload-discard confirmation.

Type evidence such as `open: int`, `high: float` and `volume: int` is permitted. Numeric OHLCV values are prohibited from evidence, serialization, representation, GUI output, logs and exceptions.

# 12. GUI Boundary

Direct Version 1.0 launch is inspection-only. Credential fields and Run remain disabled, no Provider factory or SDK object is constructed, and the GUI displays:

`LIVE EXECUTION NOT AUTHORIZED — CAR-014 VERSION 1.1 REQUIRED`

A future Version 1.1 launch procedure may supply only a non-secret activation context. The GUI may then accept a masked Kite API key and existing access token locally. It shall request no other authentication material or browser interaction.

After final confirmation, the GUI disables Run and credential controls, clears and hides credential widgets before Stage 1, invokes the engine once, displays sanitized evidence only and exposes only acknowledgement and close. Rejecting confirmation, empty validation and Cancel perform no Provider activity and consume no authority.

# 13. Iteration, Cleanup and Persistence

One bounded iteration over Instrument Master records, one bounded iteration over candle rows and deterministic in-memory sorting are permitted. No iteration may invoke an endpoint.

Retry loops, endpoint loops, polling, scheduling, automatic repeat, automatic re-probe and automatic relaunch are prohibited.

Local adapter cleanup is attempted exactly once where construction occurred. Cleanup invokes no Provider endpoint or token invalidation, and failure is sanitized.

No file, database, cache, environment file, payload, token, candle, record, snapshot, Instrument, Observation, Market Fact or Validation output is created or persisted.

# 14. Explicitly Withheld Authority

Version 1.0 authorizes no:

- credentials or authentication material;
- live SDK client construction;
- Provider or network communication;
- Instrument Master or historical-data call;
- profile, quote, LTP, OHLC snapshot, streaming or account endpoint;
- token generation, exchange, refresh, invalidation or termination;
- order, trade, holding, position, funds, margin or GTT operation;
- Provider mutation;
- retry, second attempt or independent Stage 2;
- production Provider implementation or product GUI;
- Provider Catalogue, persistence or downstream contract activity;
- Instrument interpretation, Observation, Market Facts or Validation creation; or
- trading, Risk, Execution or Portfolio activity.

# 15. Offline Verification

All Version 1.0 tests shall use fakes and mocks only. They shall prove activation rejection before factory invocation; consumption before construction; one call per stage; no retry; deterministic exact-GOLD and exact-`FUT` selection; transient token and payload treatment; OHLCV value exclusion; sanitized failures; GUI inspection-only behavior; no unapproved endpoint; no persistence; and no network activity.

Test success is implementation evidence only. It creates no Version 1.1 authority.

# 16. Publication and Future Activation

After Engineering Architect review, Version 1.0 permits one combined code-and-documentation commit and push containing only the five authorized files.

Publication shall end with CAR-014 Version 1.1 absent, no live operation performed and no credential accessed. Engineering shall then stop and await a separate Version 1.1 activation work order.

## Related Authority

- [ADR-009 — Provider-Bounded Instrument Master Acquisition Architecture](../../architecture/platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)
- [Provider Domain Architecture](../../architecture/platform/domains/provider/ARCHITECTURE.md)
- [EDD-004 — Provider Instrument Master Acquisition Engineering Design](../../engineering/edd/EDD-004-PROVIDER-INSTRUMENT-MASTER-ACQUISITION-ENGINEERING-DESIGN.md)
- [CAR-011 Version 1.1](CAR-011-KITE-PROFILE-VERIFICATION-PILOT-AUTHORIZATION-DECISION.md)
- [CAR-012](CAR-012-CAR-011-PROFILE-OPERATION-AND-TRANSPORT-BOUNDARY-CLARIFICATION.md)
- [DOC-001](../documentation/DOC-001-DOCUMENT-IDENTIFICATION-CLASSIFICATION-METADATA-STANDARD.md)
- [Document Register](../../indexes/DOCUMENT-REGISTER.md)

# End of Document
