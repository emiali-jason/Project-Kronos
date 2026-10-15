# ADR-0066 — Theta prospective information set and retrieval times

**Document Status:** Approved for narrowly bounded TE-02 engineering; candidate
only. Publication and production runtime acceptance are not granted.

## Metadata

- **ADR Number:** ADR-0066
- **Title:** Theta prospective information set and retrieval times
- **Status:** APPROVED for bounded engineering
- **Date:** 2026-10-11
- **Decision Owner:** Chief Architect / Sponsor
- **Proposed By:** Codex, identifying the TE-02 temporal-contract conflict
- **Reviewers:** Chief Architect / Sponsor
- **Approved By:** Sponsor / CA, explicit “AUTHORIZE OPTION 1” instruction
- **Decision Scope:** Theta Question/Answer temporal interface only
- **Authority Level:** Sponsor / Chief Architect
- **Repository Approval:** Authorized decision recorded in this isolated candidate;
  repository publication not performed
- **Engineering Status:** Implemented in isolated TE-02 candidate; qualification
  evidence is recorded separately

## Context

The [retained Theta V1 contract](../interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md)
rejects sources accessed after an Answer's information cutoff. TE-02 instead
requires prospective Question commissioning, frozen T0, and unrestricted later
Astra-Ultra investigation. Requiring later retrieval to precede frozen T0 would
reject legitimate contemporaneously available evidence; advancing T0 would
permit hindsight. Codex escalated this conflict rather than silently changing
the contract. Sponsor / CA explicitly approved the correction below.

## Decision

New TE-02 Questions and their Answer templates use schema version `2.0.0`
under the existing schema identities. Historical `1.0.0` behavior is retained.

1. Freeze `information_cutoff` at Question `created_at`. Identical recommissioning
   reuses the exact Question, original T0, PDF and transport; it does not advance T0.
2. A prospective Answer preserves that exact Question cutoff. Its `analyzed_at`
   records actual completion, at/after commissioning and no later than intake.
3. Each prospective source separately records `published_at`, `available_at`
   and `accessed_at`. Availability must be legitimately supported and at/before
   T0. Known publication must also be at/before T0. Publication may remain unknown
   (`null`); availability may not be guessed from unknown publication.
4. Later retrieval is allowed: `available_at <= accessed_at <= analyzed_at`.
   Retrieval after T0 is not itself grounds for rejection. First publication or
   availability after T0 is grounds for rejection/exclusion from forecast evidence.
5. Source times and their supporting evidence remain external Analyst assertions.
   KRONOS checks structure and ordering; it does not claim independent verification
   of publication, historical page versions, authorship or source truth.
6. Historical Questions, Answers, receipts, raw bytes and validation semantics
   are not rewritten or reinterpreted. No version coercion or silent repair occurs.

## Rationale

The distinction prevents retrospective information leakage without imposing an
Intraday response-speed limit on prospective research. Separate timestamps retain
the actual research chronology and the admissible forecast information set.

## Alternatives Considered

- Retain retrieval-at/before-T0 for all versions: incompatible with TE-02's
  prospective manual research mandate.
- Move T0 to Analyst completion: violates the prospective information boundary.
- Defer to TE-04/TE-05: offered to Sponsor, who authorized this narrow correction
  in TE-02 instead.

## Consequences

New templates add source `available_at` and prefill immutable `information_cutoff`.
Legacy templates and Answers retain their original field set and cutoff rules.
This does not redesign Answer import UX, add NOT_EVALUABLE machine semantics,
change range/enum contracts, select targets or introduce a research Provider.

## Risks

False source timestamps or post-T0 updates remain analytical provenance risks.
Checksum and timestamp acceptance do not prove truth or calibration. Astra must
exclude later updates and report uncertainty honestly. Genuine target authority
and methodology remain NOT_ESTABLISHED pending their own commissioning.

## Affected Products

Theta Earners only. Swing, Intraday, Provider and broker authority are unchanged.

## Affected Interfaces

`KRONOS-THETA-QUESTION-V1` and `KRONOS-THETA-ANSWER-V1`, prospective version
`2.0.0` only. Historical version `1.0.0` remains supported without reinterpretation.

## Implementation Implications

Version-paired validation and deterministic templates are required. The approved
TE-02 Question workflow binds exact chart revisions, cycle, targets and Macro
alongside frozen T0. No production activation follows from this decision.

## Validation Requirements

Accept pre-T0 information retrieved after T0; reject post-T0 availability and
known publication; reject altered Question T0 or false future retrieval; retain
legacy rejection behavior and historical bytes; prove idempotent recommissioning.

## Validation Evidence

[TE-02 engineering record](../../engineering/THETA-TE02-QUESTION-PACK-CANDIDATE.md)
and protected `tests/unit/theta/test_question_packs.py`.

## Supersedes

Only the prospective application of the retained V1 source-retrieval cutoff.
No approved historical ADR or historical Answer is superseded or rewritten.

## Superseded By

None.

## Related ADRs

[ADR-0030](ADR-0030-CONTROLLED-MAINTENANCE-PROVIDER-CONNECTION-GOVERNANCE.md):
existing shared admission remains intact; no Provider authority is added.

## Related Documents

[Theta interface](../interfaces/KRONOS-THETA-EXTERNAL-RESEARCH-V1.md),
[TE-02 engineering record](../../engineering/THETA-TE02-QUESTION-PACK-CANDIDATE.md).

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-10-11 | 1 | Codex | Records exact Sponsor/CA Option 1 authorization and version-aware compatibility | Approved bounded engineering; no publication/runtime acceptance |
