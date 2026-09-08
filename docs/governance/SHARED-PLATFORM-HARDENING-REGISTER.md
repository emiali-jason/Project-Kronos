# Shared Platform Hardening Register

**Status:** Sponsor-approved requirements; implementation deferred.
**Decision:** WO-06D Activation Reconciliation, 7 September 2026.
**Implementation gate:** After the Intraday improvement programme / Sponsor Check; shared engineering authorization required. Not part of WO-06D.

## SPH-001 — Provider connection attribution

New authentication remains explicit-action only. ADR-010 governs authentication; existing authenticated WebSocket transport recovery is separate. No automatic KRONOS `/provider/connect` caller was found. The historical activation initiator is NOT_ESTABLISHED / NOT_RECOVERABLE_FROM_RETAINED_EVIDENCE and CLOSED AS HISTORICAL ATTRIBUTION GAP. Do not assign an actor without evidence.

Future connection requests must retain a connection request identity, server receipt timestamp, runtime/process identity, frozen runtime revision, Provider identity, route, trigger classification and initiating surface where actually established, accepted/rejected/already-connected state, and correlated asynchronous success/failure/unfinished result. Unknown callers remain LOCAL_HTTP_UNATTRIBUTED. Host, Origin or client address never proves SPONSOR_EXPLICIT.

Exclude credentials, tokens, Provider payloads, cookies, authorization headers, arbitrary bodies, raw secret configuration and raw exceptions. Audit records do not grant authentication authority. Implement once at the shared boundary; preserve product ownership and asynchronous connection behavior. Candidate seams are Browser dispatch, application connection/result callbacks and immutable startup-context wiring. No source implementation is authorized by this register.

## SPH-002 — Expected maintenance disconnect notification

Approved Sponsor policy: SUPPRESS_EXPECTED_MAINTENANCE_ALERT. A validated, process-owned deliberate shutdown/restart must not emit the ordinary high-priority unexpected-outage notification solely because it disconnects transport. Preserve disconnect evidence, monitoring interruption, position/lifecycle truth and restoration evidence. Do not suppress unexpected Provider disconnect, network/socket failure, unplanned process loss, failed reconnect, authentication failure or any genuine connectivity incident. Blanket muting is prohibited.

This policy concerns delivery classification; it does not change ADR-0016 restoration. Seven existing Swing files remain genuine evidence of the controlled activation sequence, without established trading-state consequence. No deletion, rewriting or quarantine. Implementation deferred until shared/Swing hardening after Intraday.

## Retention dependency

Operational/analytical generated evidence is temporary under the Sponsor personal-retention policy: current month plus five calendar days. Previous-month purge is conditional on final monthly Excel being finalized, reconciled and integrity verified. Final monthly Excel, GitHub source/tests/governance and Living Master/programme governance are permanent. Purge engine is not authorized by WO-06D.

## Sponsor production-inertness classification — 8 September 2026

WO-06D initiated zero Intraday production operations, Refreshes, Provider/OpenAI/broker operations, or runtime restarts after accepted activation. Baseline evidence files modified: zero. Concurrent/unattributed Swing additions are present and are not attributed to WO-06D without evidence.

| Retained category | Files |
| --- | ---: |
| Previously accepted activation additions | 7 |
| Additional historical interruption additions discovered | 2 |
| Further additions during the WO-06D engineering window | 6 |

Actor/initiating cause for the additional writes: NOT_ESTABLISHED. Sponsor disposition: PRESERVE + CARRY TO SWING/SHARED HARDENING. This resolves the WO-06D production-inertness classification; it does not claim that the running platform produced no files. Preserve every file. No deletion, attribution, WO-06C reopening or Swing redesign is authorized inside WO-06D. Shared investigation/implementation remains deferred under SPH-001/SPH-002 and the existing post-Intraday gate.

## SPH-001/002/003 engineering gate — direct Sponsor override, 8 September 2026

**Status:** Bounded engineering authorized; candidate review/publication/runtime acceptance pending.

The direct Sponsor SPH authorization supersedes the prior deferred implementation gate for these exact requirements. Historical dispositions above remain retained. No automatic authentication authority is granted and no historical actor is newly attributed.

SPH-003 adds validated process-owned maintenance generation/handoff, startup guards and explicit exit. It is the shared enforcement prerequisite accompanying SPH-001 attribution and SPH-002 expected-maintenance notification suppression; it is not a separate product implementation. [ADR-0030](../architecture/adr/ADR-0030-CONTROLLED-MAINTENANCE-PROVIDER-CONNECTION-GOVERNANCE.md) records the bounded design and deployment gates.

Engineering must remain offline. Staging, commit, push, installed-launcher update, production restart, Provider operations and WO-06H runtime retry are not authorized by this entry. WO-06H remains published with runtime acceptance blocked, live shadow inactive and month clock not started. Retain all baseline files and classify concurrent Swing additions separately without actor attribution.
