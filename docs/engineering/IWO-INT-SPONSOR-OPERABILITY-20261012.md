# IWO-INT — Sponsor operability and selective monitoring

Status: R3 engineering candidate; R1 and R2 received CHANGES_REQUIRED and remain preserved. Independent exact-byte and EA-Intraday review, publication, runtime transition and production acceptance are separate pending gates.
Owner: EA-Intraday. Sponsor: Imran. Date: 12 October 2026.
Base: `90fcb8165aa894a96dda354b02cb16db4c882f3f`.

This implements the consolidated Sponsor order IWO-INT-20261012-SPONSOR-OPERABILITY-AND-MONITORING. ADR-0064 and the experimental PAPER interface freeze methodology and the passive observer boundary. ADR-0052 preserves WO13 event and transport authority; ADR-0054 preserves PAPER Position / Observation / LIVE distinctions. ADR-0060 and IWO-06A preserve historical research restoration. No approved ADR, method, criterion, threshold, readiness gate or notification policy is rewritten.

## Actual SAIL finding

Finding: OTHER_EXACT_FINDING — lawful retained watch with unavailable passive delivery; incomplete readiness-notification monitoring projection. This is neither proof of an active observer nor an authorized autonomous-activation defect.

The later ordinary Analysis retained SAIL SHORT 4/5, READY_FOUR, I2 outstanding. The complete path is:

1. WO08 retains the experimental assessment and exact completed source evidence.
2. WO09 retains validated readiness and its current pointer, then notifies committed source subscribers after source guards are released.
3. WO13 derives the commissioned READY_FOUR transition and retains its stable semantic notification identity. The natural event was delivered by the existing Telegram transport.
4. The experimental coordinator retains its watch/binding after readiness publication. It calls `observe_existing` on the shared hub; it never opens an ordinary transport owner, connects a socket or reconciles subscriptions.
5. An existing applied subscription is required. Captured global state was IDLE, with zero sessions, owners and subscriptions; experimental attached observers were zero and the exact failure was `SHARED_MONITORING_EXISTING_SUBSCRIPTION_REQUIRED`.
6. Consequently there was no active selective observer or promised live tick delivery. A retained `WatchState.ACTIVE` describes eligibility, not transport attachment. The Settings PASS at 13:25 IST was a separate completed one-shot price test, not evidence of continuing watch delivery.
7. Existing notification indicators resolved only WO11 lifecycle owners. Readiness events have no WO11 owner, so the generic UNAVAILABLE badge omitted the selective-watch reason.

The candidate adds a read-only projection on the existing coordinator. It validates exact readiness, pointer, session/source, watch binding, expiry, watch state and actual passive registration. It returns ACTIVE only when the required existing registration is active; INACTIVE for non-applicability, supersession or lawful session expiry; UNAVAILABLE for missing subscription/observer, interruption, missing source authority or invalid binding. Source/session unavailability is explicitly not converted to inactivity. Per-binding attachment failure is presentation evidence only. No GET activates, restores, mutates or acquires anything.

`watch_started_at` remains the governed watch timestamp; it is not invented socket-start evidence. No aggregate “active watches” count is invented: ordinary owners, positions and passive criteria are distinct populations. The authoritative shared-hub runtime status remains available unchanged.

WebSocket observations remain advisory. Only separately authorized ordinary Analysis can reassess completed evidence, satisfy I2/I3, produce 5/5, retain first-five or promote readiness. No watch/hint/WO12 event becomes notification or Telegram authority.

## Sponsor presentation

Machine Review presents Analysed / Considered / Ready / Now and separate Not Admitted / Unavailable counts. The primary table contains current considered opportunities with Security, Direction, Score, Status, Waiting for, Monitoring and immutable Assessment Price. Remaining rows remain accessible with counts by actual retained exclusion reason and exact codes under Technical details. All 98 rows remain accountable; the current considered population is not replaced by all 98 in WO12.

The row disclosure names I1 Direction Support, I2 Follow-through, I3 Path Clearance, I4 Structural Quality and I5 Extension. I2 describes the two consecutive completed 5-minute candles and direction-specific strict conditions. I3 describes the complete finite retained level population and exact path endpoints. Only retained advisory levels are displayed; they do not masquerade as completed-candle confirmation. Full source/criterion/readiness JSON, method identity and machine codes remain secondary evidence.

Dashboard retains the exact source/session-validated counts and adds the corresponding securities, directions, waiting criteria and monitoring projection. Swing's dashboard rendering remains independent. NSE names remove only recognized identity prefixes for presentation; exact MCX contract identity remains operationally visible.

Notifications display the same security, readiness and waiting language. Existing stored notification details, event identity, transition, deduplication, dispatch intent and historical Telegram receipts are unchanged. Future Telegram text uses monitoring observed at dispatch, including truthful unavailability when dispatch precedes watch attachment. Browser reads show the current projection. No replay is sent.

Reports explicitly describe simulated one-lot PAPER positions, non-exposure observations and disabled Live trading; exact authority codes remain in Technical details. Settings separates Kite connection, the last live-price test, Telegram, Chart Analyst and calendar coverage. A completed Settings PASS does not claim current watch delivery. Local read-only and no-broker-order authority remain explicit, with machine capability identifiers retained secondarily.

## Readable identity and history

The original symbol extraction used the suffix after the last hyphen. `NSE-EQ-BAJAJ-AUTO` consequently produced `AUTO-20261012-123043`. The full machine identity also binds canonical subject and origin provenance, so this presentation ambiguity did not establish cross-security association or machine collision.

New origins preserve the complete symbol after a recognized namespace and encode internal hyphens as underscores, compatible with the existing compact ID grammar: `BAJAJ_AUTO-YYYYMMDD-HHMMSS`. Existing origins, including AUTO, keep their exact ID and machine identity. The two origin-validation consumers deterministically recognize the original suffix form when validating existing evidence; they do not rewrite or trust arbitrary IDs. Origin time, reset rules, admission and one-lot authority are unchanged. New same-session origins still require the existing governed terminal/reset evidence.

## Genuine IWO-06 chronology retained

The initial Analysis was `INTRADAY-PROBABLES-V2-RUN-B45AD432DDD65204E08008A4BCADDBF13F2CD3F1301B1475D252C4CC7F2DE2A0`, boundary 2026-10-12T07:00:43.223000Z: 98 population, 5 considered (4 LONG / 1 SHORT), 92 not admitted and 1 unavailable; no natural 4/5.

The later Analysis was `INTRADAY-PROBABLES-V2-RUN-30F34B74A589CE4785E92E6BC9AFC1ED8232D5F7C03481AA88156B6AFB250841`, boundary 2026-10-12T07:40:54.526000Z: 98 population, 11 SHORT considered, 86 not admitted and 1 unavailable; natural SAIL 4/5 and retained watch, WO13 event and real Telegram delivery.

The SAIL binding is `WO09_EXPERIMENTAL_WATCH_BINDING_V1-383be72906c821796dc1af4de5e7021fc643e891652519fe5b86bcce7ec9b495`; its retained I2 advisory level is 172.84. The notification-centre identity is `d2d5eb607441307c7f623d72a612c31f5e34aee9c6d37edcc18246cdcd6c0573`. Natural event chronology includes created 07:42:07.083387Z, Telegram ATTEMPTING 07:42:07.184805Z and SENT 07:42:12.301379Z. Candidate work does not replay, edit, replace or backfill these records.

## Actual impact and qualification

Source scope is the Intraday watch projection, origin presentation/compatibility validation, context-specific Sponsor presentation helpers, read-model consumers and bounded shared Browser/composition seams. Shared changes are explicitly covered by the Sponsor C6 order and protected regressions. No Swing analytical/lifecycle behavior, Provider operation authority, shared transport action semantics, runtime recovery gate or launcher binary is changed. R2 adds inert retained-lease and registration evidence in the existing Provider/shared-monitoring owners; this is an actual shared implementation seam. Fresh EA-Intraday, PCP, shared-runtime/Swing and Provider-impact engineering review is required for the exact R2 bytes.

Qualification runs through `tools/kronos_test.py`: inherited kernel isolation denies production evidence, credentials, external network and production port 8947. Intercepted transport is never real Telegram or Provider. Intermediate isolation refusals, stale wording assertions and fixture corrections remain in the evidence directory. The initial overbroad suite was deliberately interrupted after 691 passes and three Settings presentation failures; it is not represented as a completed pass. Those failures led to restoring machine capability/calendar codes under Technical details.

The historical restoration rehearsal uses the 280-file checksum-verified prior IWO-06A authority snapshot, copied into this work order's output. A fresh child compiles exact candidate sources under the canonical logical filenames required by the unchanged legacy marshal digest, then runs the actual historical startup restoration validators. It passed. No compatibility document was created or altered, no arbitrary digest exception was introduced, and no expired collection authority was revived. Actual loaded release identity remains a production-acceptance gate.

Final qualification, rehearsal, changed-path hashes and review disposition are recorded in the work order evidence package. This engineering record does not self-approve, claim publication, production acceptance, IWO-06 resumption, or WO12 EOD completion. Root coordination owns the external Living Master and 12 October Daily Observation updates after the corresponding gates. IWO-06 remains active; EOD remains pending governed terminal evidence. Trading actions: zero. LIVE broker authority: NONE. NATGAS: HELD.

### Preserved R1 qualification disposition

The bounded affected/protected suite completed with **556 passed, 1 skipped** in 437.58 seconds (`qualification-bounded-2.xml`). The skip is the separately exercised production-copy restoration case. After the final monitoring-authority, polling revision and rehearsal-fixture corrections, the final focused suite completed with **95 passed** in 99.57 seconds (`qualification-final-2.xml`), including that exact-source fresh-child restoration. Its child completed with **1 passed, 15 deselected** in 18.58 seconds; `production-copy-loaded-source.json` binds the loaded candidate source hashes. These overlapping suites are not additive coverage counts. The bounded run precedes the final localized changes; the final suite exercises those changes and affected shared Browser/Swing notification consumers.

The final production-shaped offline rehearsal contains 98 source-derived rows: 11 considered, 80 not admitted and 7 unavailable (two indices and five MCX contracts in this NSE source fixture), with eight NOW and two READY opportunities. This synthetic fixture is explicitly distinct from the two genuine retained runs above. It exercises I2 and I3 readiness, 3/5 non-readiness, all three monitoring states, existing-owner passive attachment, missing existing subscription, two intercepted Telegram messages with deduplication, PAPER Reports and Settings. Exact-contract MCX, empty/populated/history and criterion disclosures are separately qualified. Rehearsal counters report zero real Telegram, zero Provider acquisition and unchanged historical source bytes.

All failed attempts and corrections remain available. In addition to initial isolation and stale-label corrections, the rehearsal corrected duplicate fixture member identities, invalid session subject identities, a source recipe that actually admitted 91 rows, and a purported 3/5 recipe that actually scored 2/5. A prior final restoration attempt correctly failed its source-stability guard because engineering edited source concurrently; the final run froze source and passed that guard. No failed or interrupted run is represented as passed.

Rendered HTML artifacts and structural/content assertions are retained for review. An attempted local-file visual preview was rejected by the browser policy, which also prohibited a workaround. No alternate rendering route was used and no screenshot-based visual acceptance is claimed. Independent review and production UI acceptance must account for this limitation.


### R2 corrections from independent review

R1's passing tests did not establish the real read boundary. IWO-INT-IR-01 identified that monitoring projection entered `_source` / `_machine_source` and rebuilt readiness; IWO-INT-IR-02 identified missing/contradictory authority classified as inactive; the EA-Swing/shared reviewer identified that registration `.active` synchronizes the canonical Provider lease and can revoke all shared leases. R1 remains CHANGES_REQUIRED and is not releaseable.

R2 compares retained Probables/WO08/Native/origin/first-five and exact contract source identities through `retained_monitoring_source`; the status path does not enter readiness evaluators or the operational publication source check. Existing immutable store validation remains in place. A missing WO09 pointer or durable watch is UNAVAILABLE; a self-valid pointer must bind subject, readiness identity and readiness integrity. A proven successor/non-current pointer or a present inactive watch is INACTIVE. The pointer is checked again before reporting attachment.

The Provider owner now offers `ReadOnlyProviderLease.read_only_active`, based only on exact retained lease membership, retained lifecycle/capability, governed deadline and known clock/expiry. It does not synchronize, invoke Provider status, acquire, release or revoke leases. Existing operation-time `.active` is untouched and continues strict revalidation. This follows the existing ADR-0050 inert status boundary and ADR-010 ownership; the new Boolean is presentation evidence, never operation authority. The shared registration's inert accessor combines that evidence with the exact hub registration, applied subscriptions, transport callback state and passive session-generation fence. Unknown capability implementations fail closed. The experimental runtime-status observer count also uses this inert accessor.

Regression uses an actual SharedAuthenticatedProviderRuntime and ReadOnlyProviderLease over a fake underlying Provider, with existing shared-hub ownership and passive attachment. Actual Dashboard, Machine Review, WO09 and notification GET routes trap readiness evaluation, Provider session_status, synchronization and lease revocation; retained source files, owner/subscription state and shared lease state must stay unchanged. A separate explicit action-time check proves that `.active` still discovers Provider expiry and revokes authority. Missing pointer/watch, self-valid contradictory pointer, actual successor, inactive watch, retained lease expiry/unavailability/release/revocation and transport-generation loss are covered.

The first R2 affected run retained 71 passes and one fixture timeout on a full 98-row HTTP response. The second retained 121 passes and two fixture failures: an old status fake lacked the new inert property, and post-server-teardown watch inactivity was incorrectly expected to remain unavailability. These were corrected in fixtures/assertions without weakening the read-side traps. Final R2 results and exact source/hash proof are recorded in the R2 package.

### Preserved R2 qualification disposition

The final affected/protected suite completed with **648 passed, 1 skipped** in 482.26 seconds (`R2/qualification-final.xml`). The sole skip explicitly delegates the exact production-copy case to the fresh canonical-filename child, which completed with **1 passed, 15 deselected** in 19.71 seconds. The strengthened read-boundary/runtime suite completed with **95 passed** in 138.79 seconds (`R2/qualification-read-boundary.xml`). Counts overlap and are not additive. Production source was unchanged across both final runs; the second run qualifies the additional expired/unavailable HTTP coverage and runtime-status fixture correction. The child loaded-source manifest is rechecked against final source before packaging.

The strengthened rehearsal records **22 actual HTTP GETs**, an actual shared Provider lease, zero Provider status/synchronization/revocation calls on reads, and preserved lease/owner/subscription/source state across normal, expired and unavailable retained authority. It retains the same 98-row synthetic accounting and zero real acquisition/delivery. Existing action-time expiry checks still revoke the lease when explicitly exercised after read qualification.

The supplementary runtime-status run initially retained 31 passes and two failures because its historical fake registrations exposed only the operational `active` attribute. Its fixture now exposes the inert property, and the complete runtime suite passes within the 95-test final run. This failed attempt remains in `R2/qualification-runtime.*`. Final scope is 24 paths, including the five newly required shared implementation/test seams. All R1 package/review bytes and intermediate R2 evidence are preserved. At R2 packaging, independent exact-byte and applicable owner reviews remained pending. Their subsequent R2 dispositions and R3 correction are recorded below; visual acceptance remains unverified for the recorded browser-policy reason.


### R3 retained Native source correction

Independent R2 probing demonstrated that replacing the exact current Native source companion with `{}` still allowed ACTIVE, despite corruption of semantic/selection dependencies already failing closed. R2's Native record integrity and current binding checks were insufficient because they omitted the source companion owner validation. R2 is therefore CHANGES_REQUIRED; its package, reviews and reviewer-owned probes remain preserved. Its separate shared/Provider engineering approval does not override this source-authority finding.

R3 invokes the existing Native owner's `load_decision_source` read validator on each retained monitoring source check. It cross-binds the freshly read companion to the assessment's embedded exact source document, and the Native decision to the retained run, probable result and semantic identity/integrity. The existing validator checks the selected source, candle-role references and retained target manifest; R3 does not select a new cycle, evaluate readiness, create authority or invoke Provider operations. No other product source dependency or methodology is changed.

The complete98 production-shaped rehearsal retains the real shared Provider lease, lawful ordinary owner and passive observer while testing corrupt (`{}`), missing, and valid-but-wrong Native companion files. Each probe must report UNAVAILABLE, and Dashboard, Machine Review and notification-status GETs must remain inert. Restoring the exact fixture bytes must restore the prior ACTIVE observation without creating or reconnecting any owner. Provider/readiness traps, file inventories and hub/lease snapshots remain enabled. Together with normal/expired/unavailable lease cases, the rehearsal now performs 31 actual HTTP GETs. All test corruption and restoration occurs only in disposable fixture stores.

The R3 delta from R2 is confined to the retained-source validator, this engineering record, the rehearsal regression and focused original first-five provenance tests. Total baseline scope remains 24 paths. All production source is frozen for final Native-owner, read-boundary, affected/protected and historical-child qualification. Fresh exact-byte and applicable owner review remain required; no previous approval transfers to R3 bytes.


The final R2 report also explicitly requires equivalent original first-five provenance checks. R3 preserves the original publication validator's comparisons: the first-five claim's original WO08 assessment must remain loadable, match its retained document, belong to its retained run, and bind the same origin. These comparisons do not reassess readiness. Focused tests cover intact provenance, missing/wrong original assessment, missing original run membership and missing retained first-five claim. The earlier R3 protected run began before this final bounded addition; it is retained as intermediate evidence. The final complete qualification runs separately under `R3/final/` on stable source including this addition.

### Final R3 qualification disposition

The complete final suite on frozen R3 production source completed with **724 passed, 1 skipped** in 572.93 seconds (`R3/final/qualification-final.xml`). The sole skip delegates the exact production-copy case to the canonical-filename fresh child, which completed with **1 passed, 15 deselected** in 19.80 seconds. The final suite includes the 31-GET real-lease rehearsal, the Native source corruption/missing/wrong-valid probes, all five original first-five provenance cases, and the affected Browser, shared monitoring, Provider, Swing protection and historical restoration cases. All loaded child source hashes are rechecked against final source before packaging.

Direct Native-owner / WO08–WO09 integration qualification passed **80 tests** in 16.73 seconds. Focused Sponsor/first-five qualification passed **27 tests** in 7.33 seconds. Earlier R3 read-boundary and protected runs passed 24 and 717 tests respectively; those are explicitly intermediate because they began before the final first-five addition. Counts overlap and are not additive. No R3 failed test attempt is omitted or relabeled; the final complete suite has zero failures or errors.

The final rehearsal reports 31 HTTP GETs; Native companion failure cases `corrupt`, `missing` and `wrong_valid_source`; zero Provider status/synchronization/revocation calls; preserved historical source bytes and lease/owner state; and the unchanged 98=11+80+7 synthetic accounting with eight NOW/two READY and two intercepted messages. Real Provider acquisition and real Telegram remain zero. R1/R2 packages and review bytes remain preserved. R3 is a new exact candidate requiring renewed independent and applicable owner review, not an approval, release or production acceptance.
