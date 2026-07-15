# KRONOS Intraday Research Library

## Purpose

This directory is an evidence-organising knowledge base for a possible future KRONOS Intraday Architecture Lab. It collects source material, separates source claims from analysis, and preserves questions that may later deserve independent review and validation.

It is not an implementation workspace. Research stored here must not be treated as approved trading logic.

## Hard Boundaries

- This library is separate from the KRONOS Swing production architecture.
- Nothing here may modify, override, or silently influence KRONOS Swing production behaviour.
- This library is separate from any future KRONOS Intraday implementation.
- No research note may directly alter architecture, code, configuration, validation criteria, or operating policy.
- Sources create hypotheses, not truth.
- Indicators, patterns, parameters, thresholds, entries, exits, stops, targets, TradingView instructions, and Pine Script are non-architectural content. They may be preserved only for traceability and must not be recommended here.
- An architecture candidate is a review object, not an architectural decision.
- Architecture Decision Records are created only after an actual decision has been independently reviewed, validated, and approved. This library currently contains no ADRs.

## Governing Flow

```text
Source
  -> Research Note
  -> Extracted Principle
  -> Architecture Candidate
  -> Architecture Review
  -> Validation
  -> Accepted Principle
```

No stage may be skipped. In particular, a source or research note cannot become an architecture candidate or accepted principle directly. See the binding [Research Lifecycle](governance/research-lifecycle.md).

## Evidence-Driven Review

1. **Collect** the source and record provenance without filling unavailable fields by inference.
2. **Structure** the source into verified facts, observed behaviour, speaker interpretation, personal opinion, claims, evidence types, assumptions, and open questions.
3. **Extract** source-faithful propositions without endorsing them.
4. **Review** a technology-neutral, parameter-free architecture candidate derived from an extracted principle.
5. **Validate** the candidate independently through the validation queue using evidence not limited to the originating source.
6. **Accept** only the exact reviewed and validated principle through explicit approval. Acceptance does not authorise implementation.

Source credibility and architectural usefulness are evaluated separately. A credible source may have no KRONOS relevance, while a useful hypothesis may still have weak evidence and require extensive validation.

Evidence is described through independent profile dimensions rather than a composite score. Convergence records proposition-specific agreement and independence separately from source quality, validation, and acceptance.

## Evidence Vocabulary

- **Source claim:** A statement made by the source. Recording it does not endorse it.
- **Observation:** A directly inspectable occurrence in source material or validation data. It should state its scope and provenance.
- **Interpretation:** A reviewer-created explanation of what a claim or observation may mean. It must be labelled and may be wrong.
- **Evidence profile:** Separate provenance, method, empirical, independence, reproducibility, applicability, and conflict-transparency metadata. Dimensions are never combined into a score.
- **Convergence:** A C0–C5 proposition-specific record of repeated, independent, triangulated, or validated support. It is not acceptance.
- **Extracted principle:** A source-faithful proposition recorded between a research note and architecture candidate. Extraction is not endorsement.
- **Accepted principle:** A principle accepted only after architecture review, independent validation, and explicit approval. Research notes cannot create accepted principles.

## Status Lifecycle

```text
COLLECTED
  -> STRUCTURED
  -> ARCHITECTURE REVIEW
  -> VALIDATION REQUIRED
  -> ACCEPTED
  -> REJECTED
```

| Status | Meaning |
| --- | --- |
| `COLLECTED` | Provenance and available source artefacts are recorded. |
| `STRUCTURED` | Claims, evidence, concepts, assumptions, and questions have been separated. |
| `ARCHITECTURE REVIEW` | A candidate is being assessed for relevance; it is not approved. |
| `VALIDATION REQUIRED` | The candidate has a defined validation need and remains unapproved. |
| `ACCEPTED` | Independent review, validation, and explicit approval are complete. |
| `REJECTED` | The concept has been rejected with reasons retained for institutional memory. |

`ACCEPTED` does not mean implemented. Implementation authority and production change control remain outside this research library.

## Library Map

- [`INDEX.md`](INDEX.md): master source register.
- [`METRICS.md`](METRICS.md): repository-governance metrics.
- [`governance/`](governance/): binding research constitution.
- [`templates/`](templates/): research-note and candidate templates.
- [`topics/`](topics/): cross-source topic graph.
- [`evidence-profiles/`](evidence-profiles/): multidimensional source and EP support metadata.
- [`extracted-principles/`](extracted-principles/): source-faithful propositions awaiting architectural translation or rejection.
- [`consensus/`](consensus/): source-agreement, conflict, and unresolved-question records for existing extracted principles.
- [`convergence/`](convergence/): C0–C5 convergence assignments for existing extracted principles.
- [`architecture-candidates/`](architecture-candidates/): unapproved candidate principles.
- [`validation-queue/`](validation-queue/): candidate validation intake and status.
- [`accepted-principles/`](accepted-principles/): explicitly approved principles; currently empty.
- [`youtube/`](youtube/): YouTube notes and transcript artefacts.
- [`books/`](books/): book research.
- [`academic-papers/`](academic-papers/): academic research.
- [`exchange-material/`](exchange-material/): exchange and venue material.
- [`market-microstructure/`](market-microstructure/): market-mechanics research.
- [`institutional-practice/`](institutional-practice/): documented institutional practices.
- [`validation-observations/`](validation-observations/): validation records and observations.
- [`rejected-concepts/`](rejected-concepts/): rejected concepts and rationale.

## Governance

The files in [`governance/`](governance/) define the research lifecycle, multidimensional evidence profile, convergence model, source-quality review, architecture-review gate, and validation policy. They are the constitution of this library and must be updated intentionally when governance changes.

## Naming and Stable IDs

Use sortable filenames such as `YT-001-video-title-slug.md`. When source rights permit transcript storage, transcript artefacts use `-transcript-raw.txt` and `-transcript-clean.txt`. Otherwise use `-transcript-source.md` and, when useful, `-transcript-digest.md`. The Research ID is the stable identifier and must not change when a file is renamed.

## Transcript Handling

- Preserve retrieved raw caption text separately from any cleaned copy only when the source licence, ownership, or user-provided status permits storing the full text.
- For third-party sources that cannot be reproduced in full, preserve a source manifest, caption availability, language, provenance, quality limitations, and a non-substitutive research digest instead.
- Label manual versus auto-generated captions when known.
- Cleaning may remove duplicated caption overlap, music markers, and unnecessary timestamp clutter, but must not rewrite meaning or silently correct factual claims.
- Useful timestamps belong in the corresponding research note.
- Codex-generated summaries and interpretations must never be presented as transcript text.
- If a transcript cannot be retrieved, record it as unavailable; do not reconstruct it from the title or description.
