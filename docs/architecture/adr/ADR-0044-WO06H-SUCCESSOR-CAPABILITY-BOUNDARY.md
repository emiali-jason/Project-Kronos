# ADR-0044 — WO-06H per-epoch capability authority

**Status:** Approved bounded engineering by direct Sponsor / EA order, 11 September 2026. Publication and production commissioning require separate authorization.
**Owner:** Intraday WO-06H epoch compatibility.
**Authority:** Sponsor order c2662e31-36d2-434f-98f2-a807683b001f, SHA-256 `fa2e862e8000200310eccb9f7693bfa224d218e1bb6efc9f16b989843c723264`.
**Supersedes:** [ADR-0043](ADR-0043-WO06H-SUCCESSOR-ACCEPTANCE-EPOCHS.md) only for the successor cross-epoch capability-equality condition. Existing epoch, window, accounting, maintenance and immutable persistence semantics remain authoritative.

## Two separate decisions

Same-epoch restoration requires exact configuration and complete frozen capability-map equality. Epoch A under B remains incompatible, even if an approved A→B transition exists. Epoch B under B may restore; B under C may not. The transition is never a compatibility allowlist, revision exception or transitive restoration relation.

Successor commissioning after `ACCEPTANCE_MATERIAL_CHANGE` expects a different composed capability boundary. It independently validates retained predecessor A and the currently loaded clean process B, then requires a content-addressed immutable bridge binding A, B, the exact reviewed diagnosis and Sponsor authorization. The successor freezes B; its future restoration remains strict. Each B→C transition needs its own reviewed bridge and authorization.

## Current material change

The pre-WO-10 acceptance and published WO-10 capabilities differ in Discovery, WO-05A and WO-05B declarations. `WO_05A_TRUSTED_TIME_ADMISSION` hashes both `operation.execute` and `admit_analysis_time`. Native publication before Probables commit changed the composed transaction's failure semantics, while the reviewed Trusted-Time admission implementation remained unchanged. Thus requiring predecessor/current equality of that composite declaration prevents the authorized new epoch; removing that cross-epoch comparison does not establish compatibility of the predecessor.

The calculation digest remains frozen across this bounded transition. Methodology 2.2.0 and Narrow CPR publication must match. The diagnosis and bridge must explicitly record unchanged Trusted-Time admission semantics, methodology, Narrow CPR and WO-06H calculation. These semantic claims derive from trusted Sponsor/EA review of the immutable report, not from digest inequality or localhost attribution.

## Exact transition evidence

The [updated interface](../interfaces/KRONOS-WO06H-SUCCESSOR-EPOCH-V1.md) defines the bridge and additive authorization binding. The complete old/new capability delta is recomputed, including version changes, additions and removals; each changed entry retains both exact declarations. Unchanged entries retain their exact declarations. Capability identity hashes the complete sorted map and configuration, while the bridge additionally binds the entire current runtime proof, including revision, PID, startup and manifest. The authorizing document references the bridge and diagnosis, with its existing request, predecessor, process proof, expiry and Sponsor evidence reference.

Current startup/manifest integrity is revalidated from the server-owned frozen objects. Repository/remote equality and diagnosed-commit ancestry still gate commissioning. No caller-supplied proof or approval flag is accepted through HTTP. Trusted local enrollment remains separate from commissioning and is not performed during engineering.

Historical authorization envelopes remain readable without byte migration. New commissioning requires the bridge. When a bridge-bound epoch is restored/read, its retained bridge is revalidated against that epoch's frozen proof, not against another runtime as a restoration exception. Corrupt or detached bridge/authorization/diagnosis evidence fails closed.

## Qualification and preservation

An isolated fixture retains the exact historical and WO-10 capability declarations from reviewed evidence, but constructs synthetic runtime identities and research records in temporary stores. It represents all three changed declarations and the original dates/counts 34/66/0. It proves A restoration under B rejects; successor B is allowed with exact authority; B starts at zero with a new actual-boundary window; historical bytes remain unchanged. The earlier positive fixture changed only Discovery and omitted this production mismatch.

Negative cases cover wrong predecessor/current proof, incorrect changed/unchanged sets, missing/nonmaterial diagnosis, missing authorization/bridge, corrupt records, dirty or mismatched runtime, calculation/policy changes and A→B→C without cross-epoch fallback. Kernel isolation denies production stores and port 8947. WO-10 analysis, Risk, navigation, Provider, research arithmetic and normal maintenance dispatch remain unchanged.
