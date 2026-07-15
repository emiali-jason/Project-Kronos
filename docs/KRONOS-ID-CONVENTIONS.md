# KRONOS ID Conventions

## Purpose

Stable IDs make KRONOS evidence, decisions, validation, and implementation specifications traceable even when documents are reorganized or renamed. Documents should cite IDs in their metadata and cross-references rather than relying only on paths or filenames.

## Identifier Registry

| Prefix | Format | Responsibility |
| --- | --- | --- |
| `YT` | `YT-###` | YouTube research |
| `BOOK` | `BOOK-###` | Book research |
| `PAPER` | `PAPER-###` | Academic paper |
| `EXCH` | `EXCH-###` | Exchange publication |
| `INST` | `INST-###` | Institutional publication |
| `AC` | `AC-###` | Architecture candidate |
| `AD` | `AD-###` | Architecture decision |
| `VO` | `VO-###` | Validation observation |
| `EXP` | `EXP-###` | Validation experiment |
| `REP` | `REP-###` | Validation report |
| `SPEC` | `SPEC-###` | Implementation specification |

Numbers are zero-padded to at least three digits. Each prefix has an independent sequence; for example, `YT-007` and `AC-007` identify different artefact classes.

## Preserved Research Library Identifiers

The migrated Intraday Research Library already uses these stable identifiers. They remain permanent and must not be renumbered:

| Prefix | Format | Responsibility |
| --- | --- | --- |
| `EP` | `EP-###` | Extracted research principle |
| `VQ` | `VQ-###` | Research validation-queue item |

Existing architecture documents whose filenames use `ADL-###` also remain unchanged. `ADL-###` must not be silently converted to, or treated as equivalent to, the new `AD-###` architecture-decision class; any future mapping requires explicit architecture review.

## Permanence Rules

1. IDs are permanent.
2. IDs must not be renumbered after creation.
3. Filenames may change, but IDs must remain stable.
4. Documents should cross-reference IDs rather than depending only on filenames.
5. Deleted or rejected IDs must not be reused.

## Allocation and References

- Check the relevant index or register before assigning the next unused ID.
- Assign an ID once an artefact is first recorded, not when it is eventually accepted.
- Keep the original ID when an artefact is revised, moved, rejected, superseded, or archived.
- Give derived artefacts their own class-appropriate IDs and link them to their predecessors; an architecture decision does not inherit its candidate's `AC-###` ID.
- Write cross-references as both the stable ID and a relative Markdown link where a target document exists.
