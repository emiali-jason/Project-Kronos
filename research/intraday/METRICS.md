# Research Library Metrics

Snapshot date: 2026-07-15

These are repository-governance metrics, not trading-performance metrics.

| Metric | Count |
| --- | ---: |
| YouTube research notes | 8 |
| Book research notes | 4 |
| Academic-paper research notes | 0 |
| Exchange-material research notes | 0 |
| Institutional-practice research notes | 0 |
| Extracted principles | 10 |
| Architecture candidates | 10 |
| Validation queue items | 2 |
| Validated candidates | 0 |
| Rejected candidates | 0 |
| Accepted principles | 0 |
| Consensus records | 10 |
| Source evidence profiles | 12 |
| EP support profiles | 10 |
| EP convergence assessments | 10 |

## Sources by Type

Only indexed research notes are counted. Playlist registers and transcript or source manifests are traceability artefacts, not separate research sources.

| Source type | Count |
| --- | ---: |
| YouTube | 8 |
| Book | 2 |
| Booklet | 1 |
| Magazine article | 1 |
| Academic paper | 0 |
| Exchange material | 0 |
| Institutional practice | 0 |
| **Total** | **12** |

## Evidence Profile Coverage

| Profile status | Count |
| --- | ---: |
| ASSESSED | 7 |
| PROVISIONAL | 5 |
| Missing source profiles | 0 |
| **Total source profiles** | **12** |

The five provisional YouTube profiles describe only the evidence currently reviewed in the repository. Zero-level dimensions do not judge unreviewed source content.

## Evidence Bases

Evidence-basis codes are non-ordinal and may overlap within one source.

| Evidence basis | Sources containing basis |
| --- | ---: |
| UNREVIEWED | 5 |
| PRACTITIONER | 7 |
| ANECDOTE | 7 |
| OPINION | 5 |
| MARKETING | 5 |
| MIXED | 1 |
| FORMAL_RULE | 0 |
| PEER_REVIEWED | 0 |
| ACADEMIC | 0 |
| INSTITUTIONAL | 0 |
| DOCUMENTED_CASE | 0 |

## Evidence Dimension Distribution

Dimensions are reported separately and must not be totalled or averaged.

| Dimension | Level 0 | Level 1 | Level 2 | Level 3 |
| --- | ---: | ---: | ---: | ---: |
| Provenance (`P`) | 0 | 0 | 8 | 4 |
| Method transparency (`M`) | 5 | 6 | 1 | 0 |
| Empirical support (`E`) | 5 | 7 | 0 | 0 |
| Independence (`I`) | 5 | 7 | 0 | 0 |
| Reproducibility (`R`) | 5 | 6 | 1 | 0 |
| Applicability (`A`) | 5 | 7 | 0 | 0 |
| Conflict transparency (`T`) | 6 | 6 | 0 | 0 |

## Extracted Principle Support Counts

| Principle | Books | Videos | Papers | Total supporting sources |
| --- | ---: | ---: | ---: | ---: |
| EP-001 | 2 | 2 | 0 | 4 |
| EP-002 | 1 | 2 | 0 | 3 |
| EP-003 | 1 | 2 | 0 | 3 |
| EP-004 | 2 | 3 | 0 | 5 |
| EP-005 | 2 | 3 | 0 | 5 |
| EP-006 | 2 | 3 | 0 | 5 |
| EP-007 | 1 | 3 | 0 | 4 |
| EP-008 | 1 | 2 | 0 | 3 |
| EP-009 | 1 | 2 | 0 | 3 |
| EP-010 | 4 | 3 | 0 | 7 |

Support counts are traceability counts, not evidence weights. Sources may share authors, events, claims, or underlying information.

## Architecture Candidate Support Counts

| Candidate | Supporting extracted principles | Count |
| --- | --- | ---: |
| AC-001 | EP-001 | 1 |
| AC-002 | EP-002 | 1 |
| AC-003 | EP-003 | 1 |
| AC-004 | EP-004 | 1 |
| AC-005 | EP-005 | 1 |
| AC-006 | EP-006 | 1 |
| AC-007 | EP-007 | 1 |
| AC-008 | EP-008 | 1 |
| AC-009 | EP-009 | 1 |
| AC-010 | EP-010 | 1 |

## Consensus Coverage

| Coverage metric | Value |
| --- | ---: |
| Existing extracted principles | 10 |
| Extracted principles with consensus records | 10 |
| Missing consensus records | 0 |
| Consensus coverage | 100% |

## Convergence Coverage

| Convergence level | Extracted principles |
| --- | ---: |
| C0 — Unmapped | 0 |
| C1 — Single-source signal | 0 |
| C2 — Repeated signal | 10 |
| C3 — Independent convergence | 0 |
| C4 — Triangulated convergence | 0 |
| C5 — Validated convergence | 0 |
| **Total assessed** | **10** |

All current EPs remain at `C2` because multiple sources support or illustrate them, but independence and direct validation are not established. Convergence is not an acceptance state.

## Counting Rules

- Count research sources by stable Research ID in [`INDEX.md`](INDEX.md); playlist references are not research notes.
- Count extracted principles by `EP-*` record in [`extracted-principles/`](extracted-principles/).
- Count architecture candidates by `AC-*` record in [`architecture-candidates/`](architecture-candidates/).
- Count queue items by `VQ-*` record in [`validation-queue/`](validation-queue/).
- Count accepted principles only from [`accepted-principles/INDEX.md`](accepted-principles/INDEX.md).
- Count supporting sources only from the explicit `Supporting Sources` section of each `EP-*` record.
- Count supporting extracted principles only from the explicit `Supporting Extracted Principles` section of each `AC-*` record.
- Count consensus coverage by matching one [`consensus/`](consensus/) record to every existing `EP-*` record.
- Count source evidence-profile coverage from [`evidence-profiles/SOURCES.md`](evidence-profiles/SOURCES.md).
- Count EP support-profile coverage from [`evidence-profiles/PRINCIPLES.md`](evidence-profiles/PRINCIPLES.md).
- Count convergence from the proposition-specific assignments in [`convergence/INDEX.md`](convergence/INDEX.md), not from source totals.
- Update this snapshot whenever indexed artefacts or lifecycle statuses change.
