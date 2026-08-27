# ADR-0018 — DOMAIN-001 Governed Visual Identity Relationship V1

## Metadata

- **ADR Number:** ADR-0018
- **Title:** DOMAIN-001 Governed Visual Identity Relationship V1
- **Status:** APPROVED
- **Date:** 2026-08-27
- **Decision Owner:** Chief Architect
- **Proposed By:** KRONOS Intraday Engineering Architect
- **Reviewers:** Chief Architect / KRONOS Intraday Engineering Architect
- **Approved By:** Chief Architect
- **Decision Scope:** Platform / DOMAIN-001 / Intraday
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for publication
- **Engineering Status:** Bounded DOMAIN-001 implementation authorized
- **Provider Acquisition Authority:** NONE
- **Broker Authority:** NONE
- **Trading / Risk / Entry Authority:** NONE

## Context

Intraday Review preserves two independent identities: the KRONOS-owned expected
canonical subject identity and the Chart-Analyst-owned visible chart label.
Literal equality between these values is not a valid universal equivalence
rule. DOMAIN-001 already owns canonical equivalence and Instrument
relationships, but its current publications contain no external visual-label
relationship authority. Provider symbols are Provider mappings and cannot fill
that gap.

Retained governed TradingView artifacts visibly establish the exact labels
`RBL Bank Ltd` and `Nifty Bank Index`. The retained Analyst Answer preserves
those exact labels and has SHA-256
`3cbd1b77ff47dd487d194adbb27710cdb31d54d3c39cfbf7720fe04fd824be09`.

## Decision

### 1. Contract and publication identities

The relationship contract is:

`GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1 / 1.0.0`.

The immutable publication is:

`KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1 / 1.0.0`.

### 2. Ownership

DOMAIN-001 exclusively owns:

```text
observed visible label
+ source context
+ governed observation boundary
        ↓
canonical analytical-subject relationship resolution
```

Products consume the DOMAIN-001 result and do not maintain product-owned alias
dictionaries. Provider mappings do not establish visual identity.

### 3. V1 source context

V1 authorizes exactly one source context:

`TRADINGVIEW_VISUAL_CHART`.

No relationship is universal across external sources. A relationship for
another source requires a separately governed publication.

### 4. Exact matching

The matching key is the exact pair:

```text
(observed_visible_subject_identity, source_context)
```

Matching is case-sensitive, effective-boundary-aware and integrity-bound.
Normalization, trimming, case folding, whitespace guessing, substring,
prefix/suffix or regular-expression inference, ticker inference, Provider
symbol inference, fuzzy matching and LLM interpretation are prohibited.

### 5. Relationship content

Each immutable relationship contains:

- contract identity and version;
- publication identity;
- deterministic relationship identity;
- canonical subject identity;
- raw observed visible subject identity;
- source context;
- effective-from and effective-through boundaries;
- active/inactive status;
- source identity and provenance;
- optional supersession identity; and
- deterministic integrity identity.

The raw observed value is never replaced or normalized by resolution.

### 6. First publication

Version 1.0.0 contains exactly:

| Raw observed label | Source context | Canonical subject |
| --- | --- | --- |
| `RBL Bank Ltd` | `TRADINGVIEW_VISUAL_CHART` | `NSE-EQ-RBLBANK` |
| `Nifty Bank Index` | `TRADINGVIEW_VISUAL_CHART` | `NSE-INDEX-BANKNIFTY` |

Both relationships are effective from
`2026-08-27T10:59:49.164000+00:00` through the repository-standard open end
`9999-12-31T23:59:59.999999+00:00` while active.

### 7. Resolution and failure

Exactly one active relationship at the governed observation boundary resolves.
Zero matches fail closed as `VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE`.
Multiple matches fail closed as `VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS`, even
when they target the same canonical subject. No tie-breaker or fallback exists.

Publication sealing rejects invalid intervals, duplicate relationship
identities, overlapping relationships for the same exact key that target
different canonical subjects, dangling canonical subjects, and relationship or
publication integrity failure.

### 8. Effective validity and replay

Resolution uses the consuming evidence's governed observation boundary, not a
process wall clock. Historical replay uses the relationship effective at that
boundary. A later publication may provide authority for a new replay or import
attempt but does not rewrite an earlier Answer, chart artifact, import record,
or failure.

### 9. Intraday consumption

Intraday may replace only its invalid literal observed-versus-canonical
equality check. It supplies the raw observed label,
`TRADINGVIEW_VISUAL_CHART`, and the Review Pack observation boundary to
DOMAIN-001. A resolved canonical identity must equal the independently retained
expected canonical identity. A different canonical identity is a mismatch;
unavailable or ambiguous resolution fails closed.

Imported evidence retains expected identity, raw observed identity, and the
exact relationship, publication and integrity evidence used.

### 10. Swing boundary

Swing behavior is unchanged. This ADR does not migrate Swing to the resolver.
Any future Swing adoption requires separate authorization.

### 11. Authority exclusions

This relationship grants no Discovery, Probables, reconciliation, Entry,
Trade Construction, Risk, PAPER/LIVE, execution or broker authority.

## Rationale

An explicit, source-qualified, effective-dated relationship preserves both
trust boundaries without asking an external Analyst to manufacture KRONOS
identity. Exact fail-closed resolution follows current DOMAIN-001 semantic and
persistence patterns while preventing Provider vocabulary or product policy
from becoming canonical authority.

## Alternatives Considered

- Literal observed/canonical equality: rejected because visible platforms use
  human-readable labels.
- Intraday alias dictionary: rejected because canonical equivalence belongs to
  DOMAIN-001.
- Provider symbol fallback: rejected because Provider mapping has different
  ownership and meaning.
- Normalized, fuzzy or inferred matching: rejected as non-deterministic and
  capable of false binding.
- Analyst regeneration with canonical labels: rejected because it violates the
  observed-evidence trust boundary.

## Consequences

- DOMAIN-001 gains an additive immutable publication, resolver and store.
- Intraday can consume the result without changing its other Answer validation.
- The unchanged retained Analyst Answer can qualify successfully only through
  the exact two governed relationships.
- Failed pre-ADR-0018 import evidence remains valid historical evidence.
- Swing retains existing semantics.

## Validation Requirements

- exact resolution for both first-publication labels;
- before/at/after effective-boundary behavior;
- exact-source and exact-string near-miss failures;
- missing, ambiguous, duplicate, conflicting, dangling and tamper failures;
- publication encode/decode, immutable persistence and explicit reload;
- unchanged retained Answer SHA and in-memory binding proof;
- all existing Answer schema/cycle/chart/Q1-Q10 tests;
- DOMAIN-001, Instrument, Intraday, Browser, Swing and complete regressions;
- secret, Provider-token, broker, OpenAI, Pine and trading/Risk scans.

## Supersedes

None. ADR-0018 is additive to ADR-0014 and ADR-0017.

## Superseded By

None.

## Related ADRs and Documents

- [ADR-0014](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md)
- [ADR-0017](ADR-0017-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1.md)
- [DOMAIN-001 Instrument Architecture](../platform/domains/instrument/ARCHITECTURE.md)
- [Intraday WO-09 Answer Import](../products/intraday/KRONOS-INTRADAY-WO-09-GOVERNED-CHART-ANALYST-ANSWER-IMPORT-V1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-27 | 1.0 | Chief Architect / Engineering | Initial governed visual identity authority | APPROVED |
