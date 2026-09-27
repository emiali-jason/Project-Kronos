# ADR-0059 — Generation-Bound Maintenance Admission and V2 Drain Handoff

**Document Status:** APPROVED — source publication; launcher installation and runtime acceptance separate

## R2 successor checkpoint and durability proof

The V2 handoff consumer returns an immutable startup context containing the
signed notification checkpoint state, pending count and digest with the
maintenance generation. One-use consumption and predecessor identity checks
remain at the handoff boundary. Application composition passes that context to
WO-13 before notification binding. Binding reconstructs and validates the
retained reference set and requires exact equality with the signed checkpoint
before attaching listeners, scheduling replay or declaring READY. A different
valid set fails startup; it is not treated as an empty or replaceable set.
Legacy/V1 startup does not fabricate a V2 checkpoint. The successor still has
the 120-second READY deadline.

At the fenced final-owner proof, WO-13 validates every retained `.pending` and
`.done` reference and syncs its reference directory and parent. This explicitly
certifies references created by the older direct-enqueue path. A directory-sync
failure after pending-to-done rename marks durability unproven for that process;
a readable `.done` file or zero pending count cannot override it. Failed
certification withholds the signed handoff. Pending replay references are
durable work to restore, not active workers and not an empty queue.

## Metadata

- **ADR Number:** ADR-0059
- **Date:** 2026-09-26
- **Decision owner and required approver:** Chief Architect
- **Proposed by:** KRONOS engineering for MWO-02
- **Scope:** Shared platform maintenance, Browser, Swing, Intraday and launcher
- **Repository approval:** APPROVED 2026-09-27, as reported by the Sponsor after independent Chief Architect and EA-Intraday review
- **Engineering status:** R2 exact 34-path source/test candidate qualified, 11,039 protected tests passed; source publication in this commit, launcher installation and runtime acceptance pending

## Context and approved decision

ADR-0030's sampled idle check does not atomically prevent work from starting after the sample. The approved V2 contract adds a process-local, generation-bound admission coordinator. The following prospective maintenance authority was approved for the qualified candidate on 2026-09-27, as reported by the Sponsor.

1. An authenticated shutdown claim atomically changes admission from OPEN to FENCED for one exact PID, loaded revision and maintenance generation. Browser mutations, direct application admissions, server-loop pulses, queues, timers and callbacks must obtain a counted ticket before entering their owner lock or scheduling work. A parent must transfer or fork a ticket to a child before returning. Ownership lasts through callbacks, cleanup and final durable writes.
2. A corrected predecessor may advertise DRAINABLE while explicitly supported, counted work is active. The authenticated maintenance claim atomically fences admissions, then a bounded condition-based drain waits for every accepted owner and active queue to finish. The launcher must not impose a pre-claim zero-owner requirement on this corrected-runtime path. Legacy predecessors retain their separate strict idle preflight. The coordinator lock is never held during domain locks, I/O, Provider calls or joins. Ticket completion releases domain locks before signaling the coordinator. Status GETs copy state and do not admit work or create pulses.
3. Finalization closes the relevant Swing, Intraday WO-11/WO-17, monitoring, notification, housekeeping, Provider/callback and durable-bulk owners before claiming zero. A nonterminal bulk batch prevents handoff unless its restart-safe checkpoint is independently proven. WO-13 notification references may remain durably pending when every reference is validated and its file and parent-directory publication boundaries are fsynced; this is not an empty queue or active worker. Invalid or interrupted reference publication prevents handoff. Unknown, stale, conflicting or missing owner facts cannot be interpreted as zero.
4. Only after zero-owner and zero-queue proof, cleanup and final writes may the predecessor publish one authenticated V2 handoff. It binds exact predecessor PID/revision, runtime identity and maintenance generation, eleven explicit zero active-owner/queue fields, a validated notification checkpoint state/count/digest, creation time and one-use claim. The checkpoint is signed and rechecked after final cleanup; a changed, missing or invalid checkpoint withholds the handoff. V1 handoffs remain historical and are never represented as V2 proof.
5. Stop/drain remains within the existing 15-second predecessor window, with at most 10 seconds for drain. The handoff age limit is 45 seconds; successor READY deadline is 120 seconds. No automatic retry, signal/kill fallback or timeout extension is authorized. Timeout, generation conflict, partial cleanup or failed handoff stays fenced and does not start a successor.
6. Deployment branches remain distinct: A requires independent absence of predecessor process, listener, control and usable handoff before one cold start; B requires separate authenticated legacy transition review and explicit unproven-drain risk acceptance; C requires the corrected predecessor's signed zero-owner V2 handoff and verified exit. An ordinary Dock click reuses a healthy exact-current backend.

## Preserved authority

The decision changes maintenance admission and attestation, not Swing or Intraday analytical decisions, Provider authentication authority, monitoring policy, ADR-0058 atomic bulk acceptance, historical V1 records or broker/trade authority. ADR-0030's existing maintenance governance and ADR-0050's truthful startup contract remain active except for the approved V2 drain-proof addition. ADR-0031's one-time legacy bootstrap is not a reusable approval for branch B.

## Risks and fail-closed disposition

A callback or final write not accounted for at fence time could invalidate zero-owner proof; missing owner coverage must block handoff. A timed-out or partly cleaned predecessor remains FAILED_FENCED pending separate recovery. A successor startup failure leaves the old generation retained and does not trigger a second start. No Provider capability or monitoring owner transfers to the successor.

## Review and validation evidence

- Complete proposed contract: `/private/tmp/mwo-02.1-contract/COMPLETE-MAINTENANCE-CONTRACT.md`.
- Original frozen 33-path manifest: `/private/tmp/mwo-02-4-qualification/final-source-test-architecture-manifest.json`, SHA-256 `d3bb54284d06baafbe31cf5efb89c4c9e8710b13451cefd251e6fe55e2c858fd`.
- Original-candidate full protected qualification only: 11,024 passed, zero failed/errors/skipped; JUnit SHA-256 `a9cc145f4c2c80baad53c94b44886383e709a528d49c5026877cdb6d12cebfab`.
- MWO-02.2/02.3 focused and isolated branch A/B/C rehearsals and MWO-02.4 contract review are retained in their respective `/private/tmp/mwo-02-*-qualification` directories.
- Independent Intraday owner disposition on R2: **APPROVED 2026-09-27**, as reported by the Sponsor. The original reviewer record was not supplied to this publication task; the implementation author's review is not represented as independent approval.
- R2 final protected qualification: 11,039 passed, zero failures/errors/skips, process exit 0; retained in `/private/tmp/mwo-02-5-r2-final-qualification/`.

## Recorded decision and approval provenance

- Chief Architect disposition: **APPROVED**, reported by the Sponsor on 2026-09-27.
- Independent EA-Intraday disposition on the notification/startup delta: **APPROVED**, reported by the Sponsor on 2026-09-27.
- Nonterminal durable-bulk rule: no handoff without a proven restart-safe checkpoint, as specified in Decision item 3.
- Reviewed ADR-0059 R2 SHA-256: `05864e38465c114909589360e202d822fd8d76fa2b3769e158e92a7bfce54cc6`.
- Original signed reviewer records were not supplied to this task. These provenance statements record the Sponsor's report and do not manufacture signatures.
- Source publication is distinct from launcher installation, governed runtime load and live acceptance.

## R2 reviewer focus

Review the launcher/server DRAINABLE claim, counted Provider and monitoring continuations, exact restoration ownership through final writes, and the signed notification replay checkpoint. R2 retains the 34-path candidate, changing 10 paths relative to R1. R2 candidate manifest SHA-256: `229f5bcf46b223457afb222606b47eadcab2c2f7363a23097f14274e14395138`. The original full-suite qualification and R1 focused results did not qualify these changed executable bytes. The final R2 run on exact reviewed bytes passed 11,039 tests with zero failures/errors/skips. The decision is **APPROVED**; runtime activation remains separately gated.
