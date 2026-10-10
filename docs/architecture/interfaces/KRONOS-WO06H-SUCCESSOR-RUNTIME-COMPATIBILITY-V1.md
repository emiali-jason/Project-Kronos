# WO-06H successor-runtime compatibility V1

**Status:** Bounded engineering contract under ADR-0060; candidate and owner review pending; production enrollment not authorized.
**Schema:** KRONOS-WO06H-SUCCESSOR-RUNTIME-COMPATIBILITY/1.0.0
**Owner:** EA-Intraday / WO-06H, Chief Architect, EA-Swing/shared runtime.

The existing epoch envelope (`policy`, `kind`, `body`, `identity`, `integrity`) is reused unchanged. Kind is `successor_compatibility`; identity prefix is `WO06H-SUCCESSOR_COMPATIBILITY-`. Canonical JSON content hashes bind the entire relation. Historical `compatibility` records continue through the original validator without schema migration.

Exact body keys:

| Key | Rule |
| --- | --- |
| schema | Exact relation schema above |
| epoch / acceptance / window | Exact original bound identities |
| start / end | Exact original retained window strings |
| source_capabilities / target_capabilities | Complete sorted declaration lists, exact identity/version/implementation_digest, no duplicates/additions/removals |
| source_aggregate / target_aggregate | Independently recomputed WO06H-CAPABILITY identities over complete maps and configuration |
| configuration | Exact original and actual successor configuration identity |
| reviewed_changes | Exact sorted nonempty complete difference; no omitted/unreviewed/extra changes |
| semantic_assessment | Exactly identity and sha256 |
| adr | Exactly identity ADR-0060-WO06H-SUCCESSOR-RUNTIME-COMPATIBILITY, version1.0.0 |
| direction | SOURCE_TO_TARGET |
| non_transitive | Boolean true |
| evidence_package | Exactly identity and sha256 |
| owner_approvals | Ordered complete EA-INTRADAY-WO06H, CHIEF-ARCHITECT, EA-SWING-SHARED-RUNTIME, SPONSOR rows |

Each change row has exactly `identity`, `predecessor`, `successor`, `source_delta_sha256`, `digest_change_reason`, `semantic_impact`, `owning_tests_sha256`, `protected_tests_sha256`, `failure_behavior`. Full old/new declarations retain both versions and digests. Evidence hashes are lowercase SHA256; explanations are nonempty and non-wildcard.

Each approval row has exactly `owner`, `disposition`, `identity`, `sha256`; disposition is APPROVED or PENDING. Restoration requires every row APPROVED. Only the offline draft binding check permits PENDING. Its success is not operational authority. Trusted enrollment and human approval remain external to hash validation.

The source proof is derived from the bound immutable epoch; target proof is derived from the actual runtime. Source and target maps are never supplied as replacements for those proofs. Frozen research calculation cannot change. Unknown relation version, direction, declaration shape, delta, configuration, ADR or missing evidence/approval rejects.

Selection does not traverse relations. It reads only exact source/target/epoch matches and rejects more than one. No pre-correction target, parent chaining, reverse interpretation or transitive inference is allowed. Current original-window time validation is mandatory.

No HTTP enrollment or new runtime surface is introduced. The existing legacy restoration endpoint retains its legacy semantics. Automatic startup restoration invokes the new selector only after equality and legacy checks fail. Current status and active-epoch checks use the same selector; existing startup health and maintenance exit remain externally owned and unchanged.

Failures include SHADOW_SUCCESSOR_COMPATIBILITY_{INCOMPLETE,VERSION_INVALID,DIRECTION_INVALID,BINDING_INVALID,ADR_INVALID,EVIDENCE_INVALID,APPROVAL_INVALID,MAP_INVALID,DELTA_INVALID,NOT_APPROVED,AMBIGUOUS}; expired/inactive window is SHADOW_RESTORATION_WINDOW_NOT_ACTIVE. Existing document integrity/path/storage failures propagate; no skip, repair or fallback is added.
