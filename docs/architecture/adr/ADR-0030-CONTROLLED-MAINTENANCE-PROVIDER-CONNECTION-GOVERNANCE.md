# ADR-0030 — Controlled maintenance and Provider connection governance

**Status:** Sponsor-authorized bounded engineering decision; candidate review/publication/runtime acceptance pending.
**Decision owner:** Sponsor / Engineering Architect, direct SPH-001/002/003 authorization, 8 September 2026.
**Scope:** Shared Platform, with bounded Swing notification/restoration integration.
**References:** ADR-010 Provider Authentication; ADR-0016 Paper Observation Track; SPH-001/002 register; WO-06D/06H incident reconciliation.
**Runtime authority:** NONE in this engineering work order.

## Decision

Implement the existing SPH-001 and SPH-002 requirements and the Sponsor-approved SPH-003 controlled-maintenance guard once at the shared boundary. Preserve original ADR-010 authentication/principal-binding policy and ADR-0016 normal restoration. This adds explicit maintenance admission and expected-disconnect cause handling; it does not supersede either ADR wholesale.

The journal and maintenance handoff live in `kronos.common` as shared process infrastructure. Provider runtime receives the guard by composition; it does not read environment variables or own OS persistence. The existing Provider architecture boundary remains unchanged.

### SPH-001

An immutable PROVIDER_CONNECTION_AUDIT_V1 request is retained before dispatch: random connection_request_id, server_receipt_at, exact route, Provider identity, process PID/startup timestamp, frozen process runtime reference, loaded source revision/state, trigger and validated surface where available. Result records separately retain admission (ACCEPTED, REJECTED, ALREADY_CONNECTED), dispatch (UNFINISHED) and completion (SUCCESS, FAILURE, UNFINISHED). Each result binds the immutable request digest. Missing completion remains UNFINISHED after restoration; no success is inferred from an accepted request.

Normal HTTP requests remain LOCAL_HTTP_UNATTRIBUTED even with an accepted loopback Origin or signed HEADER/SETTINGS reference. References attest only a rendered process/control context. SPONSOR_EXPLICIT and OTHER_ESTABLISHED_GOVERNED_TRIGGER are supported vocabulary, but this implementation does not invent a human authenticator or mint either classification. Explicit direct application calls use SHARED_PROVIDER_API / UNATTRIBUTED_API; unaudited direct shared-runtime login is rejected before Provider dispatch.

No credentials, access tokens, payloads, cookies, authorization headers, arbitrary bodies or raw exceptions are persisted. The journal is append-only with integrity hashes, exclusive publication and conflict rejection. Disk failure prevents dispatch. It is request/attempt accounting, not a physical Provider transport counter; absent physical counts remain NOT_ESTABLISHED.

### SPH-003

The process-owned restart control validates its PID/private proof. The launcher supplies a fresh cryptographically random maintenance generation. Before shutdown, the process publishes an immutable HMAC-authenticated handoff bound to its PID/runtime identity. The launcher passes the generation, predecessor PID and private proof to the replacement process through a transient environment; startup consumes/removes those inputs and exclusively claims the handoff once. The proof itself is not persisted in the audit journal. Wrong proof, parent, generation, replay, symlink, malformed or stale/future handoff fails closed before application composition.

Handoff validity is bounded to 45 seconds, matching the existing launcher maximum 15-second stop wait plus 30-second readiness wait. There is no retry or fallback to unguarded startup on rejection. Controlled restart also rejects while authentication, analysis or a monitoring test is already running; it does not attempt to make an in-flight Provider request disappear. Normal startup without a handoff remains disconnected and creates no authentication attempt. The new process never restores an expired access capability.

During maintenance, shared authentication/lease use and Browser operational POST dispatch are blocked. Pending authentication cannot publish a usable capability or trigger restoration after maintenance begins; its request retains UNFINISHED. Persisted Swing tracks remain readable. Startup skips operational restoration and pending notification delivery; it does not subscribe, reconcile history, acquire observations, or run Intraday work.

END MAINTENANCE is a separate process-bound action and immutable exit record. It performs no Provider operation. Only a subsequent attributable explicit connect request can establish a new valid capability and resume existing restoration. Exit cannot release a process already shutting down. There is no automatic exit/connect chain, timer or queued authentication.

### SPH-002

A successful explicit transport close under the validated shutdown generation carries its expected-maintenance cause. Monitoring consumers still receive DISCONNECTED and preserve interruption truth. Only the corresponding ordinary disconnect alert is suppressed for both Browser and Telegram; a bounded shared disconnect record retains the cause. Normal socket-close acknowledgement is delivered once on the explicit close path, regardless of callback thread. Abnormal close/error/reconnect events remain ordinary alertable incidents. Failed explicit close is not classified as successful planned shutdown. No blanket muting is introduced.

## Preservation

No changes to WO-06H Cohort A/B, Assessment, EOD/outcomes or schemas; methodology 2.2.0, Narrow CPR, Opening, candidate selection, Review, Risk, PAPER/LIVE and broker authority remain unchanged. Paper Track observation arithmetic and persisted identities remain unchanged. No purge, Excel, live-shadow activation or WO-07 work.

## Deployment gate

The repository launcher executable is rebuilt from tools/macos/kronos_launcher.c. Engineering does not install it over /Applications/KRONOS.app or execute it. Source publication, installed-launcher update and a new controlled runtime acceptance require separate Sponsor authority. An older launcher cannot perform the new generation-bound shutdown and must fail safely rather than bypass it. The new launcher checks the live backend protocol before sending shutdown, and refuses a pre-SPH backend without stopping it. Initial deployment from PID 39393 therefore needs a separately approved bootstrap procedure; engineering does not attempt that transition. A process-owned Sponsor Exit also establishes its local expected-maintenance cause, without manufacturing a restart handoff. WO-06 remains OPEN; live-shadow clock remains NOT_STARTED.

## Qualification

Focused tests exercise request/result correlation, immutable/idempotent storage, secret exclusion, signed surface context, stale/foreign/replayed handoff rejection, maintenance entry/exit, pending callbacks, inert startup, retained monitoring interruption, deterministic Browser/Telegram suppression, abnormal-close alerts and explicit later connection. Existing Provider, Browser, Swing, launcher and Intraday suites supply non-regression coverage. All engineering execution uses fake Providers and isolated evidence; production restart and acquisition are prohibited.
