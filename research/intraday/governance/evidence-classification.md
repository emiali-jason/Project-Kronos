# Multidimensional Evidence Profile

## Purpose

An evidence profile records distinct properties of the evidence currently available in the research library. It replaces the former star-based evidence score.

The profile is not a truth score, ranking, weighted total, or architecture gate. Dimensions must remain separate because strong provenance cannot compensate for weak method, repeated claims cannot compensate for missing independence, and direct applicability cannot compensate for unreproducible evidence.

## Profile Schema

Use this compact form in research metadata:

```text
Basis=<one or more basis codes>; P<n> M<n> E<n> I<n> R<n> A<n> T<n>; Status=<status>
```

Example:

```text
Basis=PRACTITIONER; P2 M1 E1 I1 R1 A1 T1; Status=ASSESSED
```

Every compact profile must link to a profile record containing its rationale. No arithmetic total, average, colour, grade, or replacement star score may be derived from the dimensions.

## Evidence-Basis Codes

Evidence basis is categorical and non-ordinal. Use multiple codes when necessary.

- `FORMAL_RULE`: exchange, regulator, or venue rule with identifiable scope and effective date.
- `PEER_REVIEWED`: peer-reviewed academic research.
- `ACADEMIC`: academic working paper, preprint, or scholarly publication not recorded as peer-reviewed.
- `INSTITUTIONAL`: identifiable institutional publication or documented desk practice.
- `DOCUMENTED_CASE`: bounded case with reviewable records and selection criteria.
- `PRACTITIONER`: identifiable professional explanation or experience.
- `ANECDOTE`: selected example, personal account, or unverified case.
- `OPINION`: interpretation or normative assertion without direct supporting evidence.
- `MARKETING`: promotional, sales, testimonial, or performance-claim material.
- `UNREVIEWED`: substantive evidence has not yet been reviewed.
- `MIXED`: used only with more specific codes when the source materially combines evidence forms.

## Profile Dimensions

### Provenance — `P0` to `P3`

| Code | Meaning |
| --- | --- |
| `P0` | Origin, identity, or artefact cannot currently be verified. |
| `P1` | Source is identifiable but secondary, incomplete, unstable, or weakly preserved. |
| `P2` | Identifiable primary presentation or traceable publication with usable provenance. |
| `P3` | Primary artefact, edition or version, identity, and provenance are independently preserved or verified. |

### Method Transparency — `M0` to `M3`

| Code | Meaning |
| --- | --- |
| `M0` | No substantive method has been reviewed or disclosed. |
| `M1` | Reasoning, anecdotes, selected examples, or a partial method are presented. |
| `M2` | Definitions, data basis, process, and material limitations are substantially described. |
| `M3` | Complete method, sample, assumptions, exclusions, and analysis procedure are disclosed and auditable. |

### Empirical Support — `E0` to `E3`

| Code | Meaning |
| --- | --- |
| `E0` | No reviewed empirical support; assertion, metadata, or opinion only. |
| `E1` | Anecdotes, selected examples, conceptual reasoning, or unverified cases. |
| `E2` | Systematic observations or data with material design, scope, or validation limitations. |
| `E3` | Direct, well-designed empirical or authoritative factual support with reviewable results. |

### Independence — `I0` to `I3`

| Code | Meaning |
| --- | --- |
| `I0` | Independence is unassessed, promotional, or dependent on shared evidence without separation. |
| `I1` | Single-source support or multiple sources whose independence is not established. |
| `I2` | At least two demonstrably independent sources, datasets, or methods support the claim. |
| `I3` | Independent replication or corroboration exists across materially distinct evidence families. |

### Reproducibility — `R0` to `R3`

| Code | Meaning |
| --- | --- |
| `R0` | No reviewed basis for reproduction or audit. |
| `R1` | Claim and examples are inspectable, but method or results cannot be reproduced. |
| `R2` | Material calculations or method steps can be partially reproduced; gaps remain. |
| `R3` | Method and results can be independently reproduced or formally audited. |

### Applicability — `A0` to `A3`

| Code | Meaning |
| --- | --- |
| `A0` | Scope or relevance is unreviewed, unclear, obsolete, or materially mismatched. |
| `A1` | Relevance is plausible, but transfer to the research question has material uncertainty. |
| `A2` | Evidence directly addresses the research question within documented limits. |
| `A3` | Evidence directly addresses the current scope with boundaries, venue, period, and conditions established. |

### Conflict Transparency — `T0` to `T3`

| Code | Meaning |
| --- | --- |
| `T0` | Promotional interest is present, disclosure is absent, or conflicts cannot be assessed. |
| `T1` | Author interest is identifiable, but disclosure or independence remains incomplete. |
| `T2` | Material interests and limitations are explicitly disclosed and reviewable. |
| `T3` | Independent basis is demonstrated and no material undisclosed conflict is identified. |

## Profile Status

- `PROVISIONAL`: based on incomplete or unreviewed evidence and must be revisited.
- `ASSESSED`: dimensions have been reviewed against the material currently available.
- `CLAIM_SPECIFIC_REQUIRED`: the source-level profile is insufficient for a particular claim; record a claim-level profile.

## Application Rules

1. Profile the evidence supporting each claim whenever claim-level properties differ from the source-level baseline.
2. A source-level profile is a navigation summary, not a blanket rating for every statement in the source.
3. Do not average, total, rank, or colour-code dimensions.
4. Record the weakest material dependency explicitly rather than hiding it in a composite.
5. Multiple sources repeating the same assertion do not improve `I`, `E`, or `R` without demonstrated independence, method, or replication.
6. Multiple transformations of the same underlying data do not improve independence.
7. `0` means absent, unreviewed, or unverified in the present record; it does not prove that the underlying claim is false.
8. A strong profile does not make a claim architecturally relevant or accepted.
9. A weak profile does not require deletion; it identifies validation and review needs.
10. Convergence is recorded separately under the [Convergence Model](convergence-model.md).

## Current Research Registers

- [Source Evidence Profiles](../evidence-profiles/SOURCES.md)
- [Extracted Principle Support Profiles](../evidence-profiles/PRINCIPLES.md)
