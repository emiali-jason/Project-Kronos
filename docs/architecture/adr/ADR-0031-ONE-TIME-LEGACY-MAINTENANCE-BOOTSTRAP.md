# ADR-0031 — One-time legacy maintenance bootstrap and sealed launcher delivery

Date: 2026-09-08. Status: **Direct Sponsor-authorized engineering candidate; publication, installation and runtime acceptance pending.** This record does not claim independent architectural or production approval by Engineering.

## Context and authority

The Sponsor's “SPH Legacy Bootstrap Engineering — One-Time Migration Coordinator + Installable Launcher Package Qualification” explicitly authorizes this bounded implementation and qualification. SPH-001/002/003 is published in `dc964704937921a46dad8c125fc490ff4f46078a`. Legacy PID 39393 loaded `0dd6a74d3da25e52d0bd82326a30647f5111adce` and cannot publish the ordinary SPH handoff. The published raw launcher bundle lacked a complete resource seal. Neither limitation permits weakening [ADR-0030](ADR-0030-CONTROLLED-MAINTENANCE-PROVIDER-CONNECTION-GOVERNANCE.md).

The existing launcher continues to refuse a normal controlled restart of a legacy backend. This candidate adds an explicitly named migration authority, never an old-process-generated maintenance proof. Normal SPH authentication, request attribution, notification and restoration contracts remain unchanged. ADR-010 and ADR-0016 retain their existing scope.

## Separate migration contract

`KRONOS_LEGACY_BOOTSTRAP_V1` binds the expected legacy PID, frozen revision, runtime identity, startup timestamp, non-secret configuration identity, exact repository, exact listener, replacement published revision, installed corrected executable hash and old private-control-file digest. Only the proven legacy source revision is eligible. The future Sponsor-reviewed plan supplies the exact process/deployment values; this engineering turn does not issue a production plan.

A distinct coordinator process generates a fresh migration identity and private proof, reserves a private fixed deployment directory, and signs closed prepared/shutdown-authorized/stopped/consumed records. The old shutdown token is read only for the existing private shutdown POST and is never serialized into the migration contract or passed to the replacement. Provider credentials/capabilities are not read or transferred. The child environment is allow-listed.

The lifecycle is prepare → validate → immediate precondition recheck → durable exclusive shutdown authorization → one old shutdown POST → verify old PID gone and port free → stopped record → corrected launcher bootstrap mode → exclusive consumption before application composition → existing SPH-003 guard. Preparation failure never invokes shutdown. Failed stop/start, expired context or unknown outcome does not retry, kill, clear the record or fall back to unguarded startup.

Each transition uses exclusive creation, no-follow access and durability synchronization. Paths must be absolute and free of symlink ancestors/traversal. The migration directory must be owned by the current account with mode 0700; records are mode 0600. Proof validation rejects wrong identities, malformed records, concurrent replay, stale/future times and mixed ordinary/migration protocols. The existing 45-second handoff bound is reused (15-second shutdown plus 30-second startup). It bounds acceptance, not a guarantee that startup will succeed: if the deadline expires after legacy shutdown, remain stopped and seek a new explicit recovery decision. Never manufacture a fresh generation automatically.

The consumed marker is permanent for this deployment and is written before any replacement application composition. An incomplete or failed reservation also blocks automatic reissuance. No cleanup/reset command is provided. After successful migration, ordinary restarts use SPH-003; this legacy path is unusable with its retained marker. Future removal of the implementation can be separately reviewed. Retention/purge must never remove the marker while the legacy capability remains shipped.

## Legacy quiescence and notification truth

Read-only status checks establish the exact frozen runtime, listener owner, authentication/analysis state and active Discovery V1/V2/historical operation identities. The instrument-master status is inspected but does not expose a complete in-flight task registry. Browser control activity, background transport and Swing monitoring quiescence cannot be established atomically by the legacy process. These remain unknown, never false. Known active operations reject shutdown. The check is a snapshot, not a lock against a concurrent external actor.

Prepared evidence explicitly carries `LEGACY_SHUTDOWN_SIDE_EFFECT_RISK` and the Sponsor's `EXPECTED_LEGACY_BOOTSTRAP_NOTIFICATION_SIDE_EFFECT` policy. An ordinary disconnect alert emitted by old code is preserved and classified separately. No old event is rewritten or suppressed retroactively. This exception does not mute subsequent unexpected incidents and does not classify a legacy limitation as failure of post-migration SPH-002.

## Guarded replacement boundary

The corrected C launcher accepts migration mode only with a structurally complete migration environment, refuses any already listening backend, and never issues the legacy shutdown itself. Python validates and consumes the separate context using frozen startup source evidence before composing application capabilities. It passes the accepted migration identity into the existing shared maintenance guard.

The Provider factory is not invoked, authentication/restoration is prohibited, and the existing guard blocks Swing reconciliation/monitoring and Intraday operations. No automatic Browser opening, END MAINTENANCE, Provider connection, Refresh, Discovery or research-window acceptance occurs. Read-only status verification checks new PID, exact loaded revision, clean source, configuration, guard identity, disconnected Provider, disabled operation controls and inactive live shadow. Physical request/evidence inertness additionally requires the future before/after production inventories; status alone is not a proof of zero requests or writes.

## Package and installation

[Launcher packaging and migration procedure](../../engineering/SPH-LEGACY-BOOTSTRAP-DEPLOYMENT.md) defines the distinct signed artifact, source/build/resource identities, strict verification, reproducibility measurements, atomic replacement and rollback. Ad-hoc local signing is not Developer ID notarization and grants no distribution trust beyond the approved local package. Existing signature requirements are not relaxed.

## Preserved scope and gates

No Intraday methodology, admission, research, schema, Review, Risk, PAPER/LIVE or broker source is changed. WO-06H remains blocked, live shadow inactive, month clock not started and WO-06 open until separately authorized runtime acceptance. No installation, production stop/restart, Provider operation, staging, commit or push is authorized by this engineering record.
