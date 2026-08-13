# KRONOS Swing V1 Slice 4 — AI Chart Analyst Boundary

- **Status:** Implemented under the current Slice-4 engineering instruction
- **V0:** frozen and unchanged by Slice 4
- **Question set:** `SWING-V1-CHART-QUESTION-SET-V1`
- **Structured schema:** `KRONOS-SWING-V1-CHART-EVIDENCE-V1`
- **Decision authority:** KRONOS only

## Boundary

`ChartEvidenceProvider` accepts one retained original TradingView image plus
its run, canonical instrument, timeframe, completed observation boundary,
template identity, request timestamp, image hash and minimum Layer-1 factual
context. It returns one strict `ChartEvidenceResponse` containing identity
checks, structure, SMA20/50/200 observations, candle acceptance, qualitative
Volume context, visible reference levels and barriers, Pine transcription,
contradiction codes and explicit undeterminable questions.

The provider response cannot represent Readiness, trade viability, Entry,
Stop, Target, R:R, rank or lifecycle disposition. The manual Sponsor-reviewed
provider and OpenAI Responses vision adapter implement the same contract.

## Failure and authority

OpenAI model, timeout, retries and enablement remain adapter configuration. A
timeout, refusal, incomplete response, invalid schema, binding conflict or
undeterminable critical field is a typed failure. Application orchestration
retains the failure against the exact image hashes and returns candidate
Readiness `CONTEXT_INCOMPLETE`. It does not proceed to Trade Construction.

Successful observations are normalized into the preserved provider-neutral
Layer-2 contract. Existing deterministic reconciliation, correlated barrier
grouping, Options-OI `UNAVAILABLE`, Clear-Air synthesis and candidate Readiness
then run unchanged. The original chart observation and Layer-1 fact remain
separate; a conflict is not silently resolved in favour of the model.

## Retention and external content

Evidence remains local at
`~/Library/Application Support/KRONOS/evidence/swing-v1`. The retained result
includes provider, model, question-set, request time, run, instrument,
timeframe, boundary, image SHA-256, schema and complete structured response.
Routine raw charts are not stored in Google Drive.

The external provider receives the original chart and the minimum question and
thesis context needed to interpret it. Kite tokens, OpenAI credentials,
portfolio state, positions and order data are never added to the request body.
Credentials are not persisted in source, evidence metadata or request-count
audit records.

## Browser credential configuration

The local loopback Browser exposes a masked, write-only OpenAI API-key field.
Submission replaces the protected `api-key:CHART-ANALYST-API-KEY-PRIMARY`
item under the existing Apple Keychain secure-credential boundary. The stored
value is never read back to Presentation. Browser-visible status is restricted
to `CONNECTED`, `NOT CONFIGURED` and `CONNECTION FAILED`.

`Test Connection` performs one bounded Responses vision request using a
synthetic solid-colour image and strict capability-only schema. It sends no
TradingView chart, instrument, timeframe, frozen question set, Layer-1 fact or
Readiness input; it invokes no Swing workflow and retains no response or
evidence. A capability-test failure exposes only the sanitized connection
status.

## Validation boundary

Unit and regression tests use mock transports and frozen structured responses;
no external call occurs. The named NAUKRI, TITAN, POWERGRID, HINDUNILVR,
ADANIENT, NTPC and YESBANK cases are registered against one frozen question-set
identity. Manual-versus-live-AI field agreement and repeated-run consistency
remain blocked until Sponsor-reviewed frozen images and explicit live-provider
access are supplied; production authority must not be inferred from mocks.
