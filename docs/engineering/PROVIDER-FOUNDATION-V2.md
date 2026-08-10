# Provider Foundation V2

## Status

**VALIDATED FOR READ-ONLY MARKET DATA**

Validation baseline: **2026-08-10**

Provider Foundation V2 supplies KRONOS products with secure, normalized,
read-only Zerodha Kite market data.

It does not expose account, position, streaming, order, or execution
capabilities to KRONOS product consumers.

## Responsibilities

Provider Foundation owns:

- Sponsor authentication;
- protected credential retrieval;
- Kite session establishment and principal verification;
- authenticated capability lifecycle and cleanup;
- Kite SDK isolation;
- Instrument Master retrieval;
- deterministic instrument resolution;
- Provider-private instrument identity;
- historical candle retrieval;
- Quote, LTP, and OHLC retrieval;
- Provider-response validation and normalization; and
- sanitized Provider failures.

Trading products such as Swing consume normalized Provider output. They must not
communicate with Kite directly.

## Sponsor Operation

### One-Time Provisioning

Use the **KRONOS — Provider Foundation V2 Setup** UI for initial setup or
credential replacement.

Implementation entry point:

`tools/provider_pilots/provider_foundation_v2_provisioning.py`

Provisioning:

1. creates the approved non-secret application configuration;
2. stores the Kite API key in Apple Keychain;
3. stores the Kite API secret in Apple Keychain;
4. stores the intended permanent Kite `user_id` in Apple Keychain; and
5. reports only sanitized READY or MISSING states.

The provisioning UI never displays an existing stored credential.

### Normal Daily Authentication

Normal Sponsor operation is:

```text
Open KRONOS
→ Kite status: DISCONNECTED
→ Connect to Kite
→ official Kite browser login
→ loopback callback
→ immediate session exchange
→ principal verification
→ authenticated read-only capability
→ CONNECTED
```

Normal Sponsor Terminal dependency: **NONE**.

Authentication implementation entry point:

`tools/provider_pilots/provider_foundation_v2_authentication.py`

Authentication logic remains UI-independent so the same Provider service can be
driven by the eventual KRONOS browser application.

## Configuration

Approved non-secret application configuration is stored at:

```text
~/Library/Application Support/Project-KRONOS/provider-authentication.json
```

The containing directory is created with mode `0700`. The configuration file is
written atomically with mode `0600`.

The file contains exactly these non-secret keys:

```text
KRONOS_PROVIDER
KRONOS_KITE_REDIRECT_URL
KRONOS_KITE_CREDENTIAL_REF
KRONOS_KITE_INTENDED_REGISTRATION_REF
KRONOS_PROVIDER_CONFIGURATION_REF
KRONOS_KITE_APPLICATION_REGISTRATION_REF
```

The strict loader rejects:

- missing or additional keys;
- non-string values;
- symlinks;
- non-regular files;
- oversized files;
- malformed JSON; and
- protected credential or token keys.

Normal GUI operation loads this durable configuration without Sponsor Terminal
exports.

Configuration implementation:

- `src/kronos/configuration/loader.py`
- `src/kronos/configuration/settings.py`

## Credential Security

Protected material remains in Apple Keychain.

Keychain account purposes are derived from approved non-secret references:

```text
api-key:<application-registration-reference>
api-secret:<credential-reference>
intended-principal:<intended-registration-reference>
```

Protected material includes:

- Kite API key;
- Kite API secret;
- intended permanent Kite principal;
- access/session token; and
- callback/request token material.

Security invariants:

- ordinary configuration contains no credentials or tokens;
- credentials and tokens are not accepted through command-line arguments;
- credentials and tokens are not logged or displayed;
- the callback `request_token` is held in memory only;
- `request_token` is exchanged immediately and then discarded;
- the API secret remains under `SecureCredentialSource` and `SecretLease`
  custody;
- the access token remains inside the private authenticated Kite client;
- the raw Kite SDK client is never returned to consumers; and
- authenticated Provider internals are never serialized or transferred between
  processes.

Apple Keychain implementation:

`src/kronos/configuration/apple_keychain.py`

## Authentication Lifecycle

`ProviderAuthenticationService` owns the authentication attempt and
authenticated-context lifecycle.

The lifecycle is:

1. load approved non-secret configuration;
2. retrieve protected API-key material;
3. create one loopback authentication attempt;
4. generate the official Kite login URL;
5. open the Sponsor’s default browser;
6. receive the loopback callback;
7. retain the callback token ephemerally;
8. retrieve the API secret through a one-use lease;
9. exchange the callback token for a session;
10. retrieve and verify the authenticated permanent Kite `user_id`;
11. establish a context only when principal binding is `MATCHED`;
12. issue one opaque read-only capability; and
13. perform local cleanup on success, cancellation, timeout, or failure.

A capability is usable only while its owning authenticated context remains
active. Expiry or cleanup makes subsequent operations fail closed.

Primary implementation:

- `src/kronos/provider/services/provider_authentication.py`
- `src/kronos/provider/kite/auth/kite_authentication.py`
- `src/kronos/provider/adapters/kite/authentication.py`
- `src/kronos/provider/adapters/kite/client.py`
- `src/kronos/provider/kite/adapter/kite_provider.py`

## Read-Only Capability

The application-facing contract is:

`AuthenticatedReadOnlyProviderCapability`

It exposes exactly:

```text
instruments
historical_data
quote
ltp
ohlc
```

It exposes no:

```text
raw Kite SDK client
API key
API secret
access token
request token
callback token
instrument token
place_order
modify_order
cancel_order
automated execution capability
```

Contract location:

`src/kronos/provider/contracts/provider_authentication.py`

## Instrument Master and Resolution

`KiteInstrumentProvider` retrieves and normalizes Kite Instrument Master
records.

Application-facing `InstrumentRecord` contains:

```text
provider
exchange
segment
trading_symbol
name
instrument_type
expiry
```

It does not contain the Kite instrument token.

The Provider retains the Kite instrument token privately and associates it with
the normalized immutable `InstrumentRecord`. Historical and live operations
resolve that private identity internally.

Resolution is deterministic and fails clearly when:

- no record matches;
- multiple records match;
- the request is invalid;
- Provider data is malformed; or
- the authenticated capability is unavailable.

For futures, resolution selects the nearest unexpired contract only when that
expiry is unique.

Implementation:

- `src/kronos/provider/contracts/instrument.py`
- `src/kronos/provider/kite/instruments/kite_instrument_provider.py`

## Market-Data Contracts

Provider-neutral market-data contracts are defined in:

`src/kronos/provider/contracts/market_data.py`

Historical candles contain:

```text
timestamp
open
high
low
close
volume
```

Live models are:

- `QuoteSnapshot`
- `LtpSnapshot`
- `OhlcSnapshot`
- `OhlcValues`

All timestamps and numeric structures are validated before publication.

Legitimate Kite-specific representations are normalized narrowly:

- Kite quote timestamps parsed by the SDK as exchange-local naive datetimes are
  assigned the `Asia/Kolkata` timezone;
- index quotes may legitimately publish `volume=None`;
- missing volume remains invalid for ordinary equity and futures quotes; and
- raw payloads, SDK objects, and instrument tokens never cross the adapter
  boundary.

Sanitized failure categories include:

```text
CAPABILITY_UNAVAILABLE
INSTRUMENT_NOT_RESOLVED
INVALID_REQUEST
MALFORMED_PROVIDER_DATA
PROVIDER_FAILURE
```

Raw Provider exceptions and payloads are not retained in published failures.

Market-data implementation:

- `src/kronos/provider/kite/marketdata/kite_market_data_provider.py`
- `src/kronos/provider/adapters/kite/authentication.py`
- `src/kronos/provider/adapters/kite/client.py`

## Development Proof Utilities

These utilities exercise the same UI-independent authentication service and
same-process read-only capability. They are validation tools, not alternate
authentication paths.

```text
tools/provider_pilots/provider_foundation_v2_provisioning.py
tools/provider_pilots/provider_foundation_v2_authentication.py
tools/provider_pilots/provider_foundation_v2_historical_proof.py
```

Supported bounded proof inputs include:

```text
--equity-symbols-csv <path>
--mcx-symbol <symbol>
--live-snapshot-proof
--quote-only-proof
```

Proof output is sanitized. It may contain public market values, candle counts,
and timestamps, but never credentials, tokens, raw Provider payloads, raw SDK
objects, or instrument tokens.

## Maintenance and Safe Extension

When adding a read-only Provider operation:

1. define or extend a provider-neutral contract;
2. keep Kite SDK calls inside the private Kite client;
3. normalize and validate the response inside the Provider adapter;
4. publish only immutable provider-neutral results;
5. map failures to sanitized Provider-owned categories;
6. prove expiry and cleanup behavior;
7. prove no Provider identity or token leaks;
8. add fake-only unit and boundary tests; and
9. perform a bounded real proof only after offline verification is green.

Do not add order methods to `AuthenticatedReadOnlyProviderCapability`.

Do not return the Kite SDK client or a generic request function.

Do not add the instrument token to `InstrumentRecord`.

Do not persist authenticated Provider internals to enable cross-process reuse.
Market-data work requiring a live capability must run in the same owning
process.

New instrument classes require explicit deterministic matching rules and tests
for no-match, ambiguity, malformed data, and expiry selection.

WebSocket streaming must remain a separate future capability rather than being
added implicitly to the snapshot interface.

## Verification

Final offline verification:

```text
Focused Provider V2 tests: 270 PASSED
Complete offline regression: 978 PASSED
Python compilation: PASS
Secret scan: PASS
Sensitive-material scan: PASS
git diff --check: PASS
```

Real historical validation:

```text
NSE equities:
91/91 resolution PASS
91/91 historical-data PASS
Interval: 60-minute
Period: 2026-08-04 through 2026-08-07

MCX:
GOLDM resolution/history PASS
SILVERM resolution/history PASS
COPPER resolution/history PASS

USDINR/CDS representative historical proof: PASS
```

Real live validation:

```text
NSE equities:
91/91 resolution PASS
91/91 Quote PASS

MCX Quote:
NATURALGAS PASS
CRUDEOIL PASS
GOLDM PASS
SILVERM PASS
COPPER PASS

Representative complete snapshots:
RELIANCE Quote/LTP/OHLC PASS
NIFTY 50 Quote/LTP/OHLC PASS
GOLDM Quote/LTP/OHLC PASS
```

Security evidence:

```text
Secrets exposed: NO
Raw Kite client exposed: NO
Instrument token exposed: NO
Order capability exposed: NO
Order operations executed: 0
```

## Deferred Scope

The following are not part of Provider Foundation V2:

- WebSocket streaming;
- account APIs;
- holdings and position APIs;
- order placement;
- order modification;
- order cancellation; and
- automated execution.

WebSocket streaming remains deferred until a concrete consumer requires it,
including Swing active-trade monitoring, Intraday, or Portfolio/Options
monitoring.
