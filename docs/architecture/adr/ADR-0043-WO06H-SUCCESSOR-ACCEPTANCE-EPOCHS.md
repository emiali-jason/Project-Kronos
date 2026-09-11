# ADR-0043 — WO-06H successor acceptance epochs

**Status:** Approved for bounded engineering by direct Sponsor / EA order, 11 September 2026. Publication and runtime commissioning remain separately gated.
**Owner:** Intraday research acceptance infrastructure; Shared Browser owns maintenance/quiescence admission only.
**Authority:** Sponsor order 907614a9-c881-43f0-8b70-8f6222bc9bb0, SHA-256 `04fb645926d99d38ff693d237e60268e27c1da2dd1ac496b04293971847ee7dc`.

## Decision and previous authority

Extend the [WO-06H product contract](../products/intraday/KRONOS-INTRADAY-WO-06H-LIVE-SHADOW.md) with explicit immutable acceptance epochs. This supersedes its single-window restriction only at a separately authorized successor commissioning boundary. Preserve [ADR-0030](ADR-0030-CONTROLLED-MAINTENANCE-PROVIDER-CONNECTION-GOVERNANCE.md): ordinary operational POSTs remain blocked in maintenance; exit and Provider connection remain separate actions. [ADR-0042](ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) and Native/WO-10 semantics are unchanged.

Policy/schema identity is `KRONOS-WO06H-ACCEPTANCE-EPOCH/1.0.0`. An epoch binds one immutable acceptance, one immutable calendar-month research window, exact runtime proof, methodology/CPR identity, material-change diagnosis, predecessor and commissioning request. A content-addressed immutable transition binds the epoch, previous transition and retained Sponsor authorization. `CURRENT.json` is its atomically replaced, integrity-checked projection. It is the sole successor current authority; file age and directory ordering are never selectors.

The historical singleton is a deterministic initial epoch derived from its exact original acceptance and `INITIAL_ONE_MONTH` window. Read-only mapping writes nothing. First successor preparation retains this derived epoch and a `LEGACY.json` anchor without changing any historical artifact. This also preserves a usable historical root if unpublished preparation stops partway. Subsequent current epochs require the pointer and its complete exact chain; missing/corrupt current authority never falls back to legacy.

Immutable documents use no-follow directory IO, fsynced temporary files and exclusive hard-link publication. Commissioning serializes with the service lock and a filesystem lock. Acceptance, window and epoch must exist and validate before the pointer commit. Interrupted unpublished preparation remains evidence; a later request cannot reuse its earlier effective start. Investigation and separate authority are required after such a failure. No automatic repair or retry is implemented. Pointer publication is the commit point; a response failure after that point is reconciled through exact-request idempotency.

## Historical and prospective research

The original planned start/end remain unchanged even after supersession. Predecessor/successor and `superseded_at` are derived from immutable transitions. Legacy observations map by their original window/acceptance; they are never rewritten. Prospective observation fields `epoch` and `acceptance` are additive to the existing observation schema and must agree with `window`. Epoch-scoped accounting and ledger reads default to current. Status exposes all historical epochs individually and explicitly named `all_epoch_counts`; these do not replace current counts.

The successor starts at the actual acceptance instant and ends under the existing next-calendar-month rule. Its A/B/EOD counts begin at zero. No observations, Assessments, EOD outcomes or backfill are created by acceptance. All historical cohort and numerical semantics remain unchanged. A material change in calculation or Trusted-Time capability is rejected by this bounded commissioning contract.

## Maintenance commissioning boundary

See the [successor interface](../interfaces/KRONOS-WO06H-SUCCESSOR-EPOCH-V1.md). `COMMISSION_SUCCESSOR_EPOCH` is a distinct same-origin Browser control. Its small request names pre-enrolled immutable authorization; it cannot supply approval flags, runtime proof, diagnosis or timestamps. Server-owned active maintenance, idle Sponsor/analysis/Provider controls, clean exact runtime proof and clean synchronized repository are mandatory. An already-compatible current epoch rejects new commissioning. An exact duplicate request returns the same epoch; a different authorization or reused request rejects.

Authorization and diagnosis enrollment is a separate trusted local Sponsor/EA evidence step, not an HTTP feature or an automatic startup behavior. Integrity hashes are not human signatures: possession of arbitrary JSON is not Sponsor authority. The deployment operator must retain only specifically approved documents through the governed local evidence process. This engineering order neither enrolls production documents nor authorizes commissioning. Restoration binds the current epoch to compatible process capabilities without creating authority records.

## Current material-change evidence

The established diagnosis concerns published `7159439ea68c07819a5f23d8eb9c4538c02eb54c`: Native publication transaction semantics around Probables publication changed. Trusted-Time admission, methodology 2.2.0, Narrow CPR and WO-06H calculation remained unchanged. The retained compatibility report SHA-256 is `df52231199aa88419aa5d770d56dfc252896b184561a976b89c6c2d74923313d`. Any future enrollment must bind that reviewed report, the exact predecessor proof and the newly loaded engineering revision/proof. The diagnosed commit must be an ancestor of the exact synchronized authorized revision; ancestry does not itself prove compatibility.

The preserved historical boundary is `2026-09-08T20:29:02.829905+05:30` through `2026-10-08T20:29:02.829905+05:30`, A/B/EOD 34/66/0. Qualification uses independently constructed isolated fixtures, not production evidence. No new epoch is commissioned on PID 54410 under this engineering order.

## Capability and scope

Loaded capability `WO_06H_ACCEPTANCE_EPOCH/1.0.0` declares the new infrastructure separately from the frozen `WO_06H_LIVE_SHADOW` calculation digest. It does not allowlist changed code as compatible. The successor acceptance must bind the newly loaded capability set. No WO-10 analytical source, selector, Provider, broker, launcher, Risk or navigation change is required. No maintenance exit, Provider restoration, production collection, retention/purge or Excel authority is added.
