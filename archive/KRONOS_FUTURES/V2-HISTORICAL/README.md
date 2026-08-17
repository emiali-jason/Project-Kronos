# KRONOS FUTURES V2 Historical Lineage

Status: **PRESERVED / NON-PRODUCTION**

This directory preserves the governed historical lineage that led to the current KRONOS MCX Production Pine. It is archival evidence only and must not be used as the active Production source.

## Preserved checkpoints

| Checkpoint | Role | Source SHA-256 |
| --- | --- | --- |
| V2-SR1 | Historical sponsor-review checkpoint | `d9165711814913f29560b4f0f65ad28c16509c0bab5bfa9ecd05dc115f868f40` |
| V2-SR2 | Approved, frozen validation checkpoint promoted into the Production lineage | `d3048aa6d0f6f3a97585a4cc35d36d5839352d91ec8ff05d5989a495d341d54a` |

The current Production source is `KRONOS_FUTURES/source/KRONOS_FUTURES.pine`, SHA-256 `85ccc53181607b8c82d40dc230cd1025f99be1e876d1d8278119ade32eed9bf8`. The V2-SR2 checkpoint is its approved analytical baseline. Promotion changed Production identity and retired the comparison presentation; the governed records identify no analytical-logic or threshold change.

## Archive layout

- `V2-SR1/` preserves its checkpoint records, source roles, and screenshot manifest.
- `V2-SR2/` preserves the approved frozen source, checkpoint records, and Package D validation screenshots.
- `redundant-loose-copies/` preserves two former top-level working copies that were proven byte-identical to governed sources.
- `filesystem-metadata/` isolates non-source macOS metadata formerly present in the loose working directories. The files were renamed `DS_STORE.bin` so their non-source role is explicit and the disposition is reviewable.

## Duplicate disposition

| Archived loose copy | Duplicate of | Disposition |
| --- | --- | --- |
| `redundant-loose-copies/KRONOS_FUTURES_V2.pine` | Current MCX Production, SHA-256 `85ccc53181607b8c82d40dc230cd1025f99be1e876d1d8278119ade32eed9bf8` | Retained as a labeled redundant historical copy; not authoritative |
| `redundant-loose-copies/KRONOS_FUTURES_V2_CANDIDATE.pine` | V2-SR2 approved frozen source and tracked V2-SR2 forensic source, SHA-256 `d3048aa6d0f6f3a97585a4cc35d36d5839352d91ec8ff05d5989a495d341d54a` | Retained as a labeled redundant historical copy; not authoritative |

Checkpoint content and checksum manifests are preserved without substantive changes. Any embedded absolute paths or former relative paths are historical record values, not current repository locations.

Current architecture and Production remain outside this archive. Future work must not treat any file here as implementation authority.
