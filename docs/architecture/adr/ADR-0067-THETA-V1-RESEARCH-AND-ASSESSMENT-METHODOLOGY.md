# ADR-0067 — Theta V1 Astra Research and Analytical Assessment Methodology Governance

**Document Status:** Approved for the prospective isolated Theta candidate.
Publication into production and runtime acceptance are not granted.

## Metadata

- **ADR Number:** ADR-0067
- **Title:** Theta V1 Astra Research and Analytical Assessment Methodology Governance
- **Status:** APPROVED — prospective isolated candidate
- **Date:** 2026-10-12
- **Decision Owner:** Sponsor / Chief Architect / EA-Theta Earners
- **Proposed By:** Codex from the Sponsor-approved TE-05A/TE-05B methodology
- **Reviewed / Assigned By:** Chief Architect
- **Approved By:** Sponsor Imran for methodology semantics; Chief Architect for
  the coordinated governance structure and ADR identity
- **Decision Scope:** Theta research and documentary/evidentiary assessment
- **Authority Level:** Sponsor / Chief Architect
- **Effective After:** 2026-10-12T09:20:00+00:00, strictly prospectively
- **Supersedes:** None
- **Preserved Temporal Foundation:** ADR-0066
- **Production / Provider / Broker / Trading Authority:** None

## Context

TE-01 through TE-04C established exact chart evidence, Question production,
TE-03A owner targets, the V3 combined Answer contract and immutable Answer
intake. Genuine forecasting remained blocked because no governed Astra research
method or deterministic documentary-assessment method had been published.

The Sponsor approved the bounded V1 methods and their limits in TE-05B. The
Chief Architect assigned one coordinated ADR to govern the two publications
while preserving their separate identities, versions and content hashes.

ADR-0066 remains the unchanged temporal foundation: T0 is frozen at Question
commissioning; source publication/availability must be at or before T0; truthful
retrieval and analysis may occur later. ADR-0067 does not rename, overwrite,
renumber, reinterpret or supersede ADR-0066.

## Decision

Govern these exact canonical publications:

| Publication | Version | Canonical SHA-256 |
| --- | --- | --- |
| `KRONOS-THETA-ASTRA-RESEARCH-METHODOLOGY-V1` | `1.0.0` | `e9caff6ccf9b4b699737187a32e8eafe56366823fe280351868da6af06db9d5d` |
| `KRONOS-THETA-ANALYTICAL-ASSESSMENT-METHODOLOGY-V1` | `1.0.0` | `3595575c45db9aaf8bc165ffbe903737ed71124e7280291ab2e65259da4bb785` |

The approval/effective-boundary record has canonical SHA-256
`a15e8ec6e5dfd088721a19ea5ff4637228e2a54409db242e9c153453608e75f8`.
The integrity manifest binds those exact three records. Canonical JSON uses the
existing Theta UTF-8, sorted-key, compact-separator encoding.

### Astra research authority

The research publication governs prospective manual Astra research for GOLDM,
SILVERM, COPPER, CRUDEOIL and NATURALGAS, each with independent E1 and E2
terminal ranges against the exact TE-03A MCX option-expiry underlying-futures
Daily Settlement Price target and quotation unit.

The policy preserves exact per-Question T0, visible technical investigation,
international/reference-versus-MCX distinction, commodity-specific and relevant
macro research, bullish and bearish forces, counterevidence, assumptions,
limitations, chart/research reconciliation, scheduled events, horizon-specific
rationale, confidence justification, path risk, material provenance, Provider
neutrality and independence from Sponsor positions, P&L, margin, intended
strikes and contemplated option expression.

Confidence is Astra's stated terminal-range-containment percentage. It is not a
KRONOS-calibrated probability. No minimum confidence, forecasting guarantee or
use of the earlier 80% research objective as an admission threshold is approved.

### Analytical assessment authority

The assessment publication governs documentary/evidentiary assessment only:

- C1 — Identity, provenance and references
- C2 — Horizon-specific rationale
- C3 — Supportive and opposing research
- C4 — Assumptions and limitations
- C5 — T0 and source chronology
- C6 — Chart/fundamental reconciliation
- C7 — Scheduled-event treatment
- C8 — Confidence justification and path risk
- C9 — Declared unresolved contradictions

E1 and E2 are assessed independently. Shared commodity evidence is permitted
only where the accepted record links it to the applicable horizon.

The only result states are `DOCUMENTED`, `LIMITED` and `NOT_EVALUABLE`:

1. Assessment-admission failure gives `NOT_EVALUABLE` because the required
   evidence graph or authority cannot be evaluated.
2. After successful admission, any `LIMITED` criterion gives horizon result
   `LIMITED`.
3. Otherwise every criterion is `DOCUMENTED`, giving horizon result
   `DOCUMENTED`.

Required documentary evidence or proof of review completion that cannot be
established produces `LIMITED`. Empty evidence does not establish that an
investigation found nothing. An applicable declared `UNRESOLVED_CONTRADICTION`
produces `LIMITED`. C3 does not induce fabrication of opposing evidence.

`LIMITED` denotes documentary/evidentiary limitation. It does not mean forecast
error, forecast rejection, market direction, low confidence, do-not-trade, or a
trading instruction. `DOCUMENTED` establishes required documentary relationships;
it does not establish predictive accuracy or option profitability.

There is no numeric quality score, weighting, count threshold, ranking, promotion
state or commodity/package roll-up.

### Immutable forecast and evidence boundary

TE-05 preserves Astra `LOWER`, `UPPER` and `CONFIDENCE`. A structurally accepted
forecast remains accepted regardless of assessment disposition. Assessment is a
separate immutable authority. Later realized outcomes cannot rewrite the original
forecast, historical evidence or its prospective assessment meaning.

The strongest permitted KRONOS claim is: "KRONOS verified the integrity and
required documentary relationships of this assessment." TE-05 does not claim
independent verification of source truth, research completeness, chart
interpretation, economic correctness, forecast probability, forecast accuracy or
option profitability.

### Prospective admission and versioning

Only genuine Questions commissioned strictly after
`2026-10-12T09:20:00+00:00` may bind these publications. The producer must bind
the exact research identity, version and hash. No arbitrary approval string,
flag, mtime, directory order, cache or latest-file selection confers authority.

Historical Questions and Answers do not acquire the new method through replay,
re-T0, currentness changes or evidence replacement. Any normative revision
requires a new publication version/hash and preserves old policy bytes and
historical assessment meaning.

## Rationale

Separate canonical methods under one coordinated decision preserve the
difference between Analyst research obligations and KRONOS documentary checks.
Deterministic qualitative states support reproducibility without disguising
Analyst assertions as independently verified market facts or trading expectancy.

## Consequences

- Genuine prospective V3 Questions may use the exact research descriptor after
  the effective boundary when the publication graph is explicitly composed.
- TE-05C may consume the exact assessment descriptor and policy in a later,
  separately authorized slice.
- Some structurally valid Answers may later assess as `LIMITED`; their forecasts
  remain accepted and unchanged.
- No option-expression suitability, strategy, strike, lot, adjustment, execution,
  broker or production authority is created.
- The default runtime remains unenrolled; this ADR does not deploy the candidate.

## Alternatives considered

Numeric scores or weights, another AI assessor, inferred “none found,” forced
opposing evidence, forecast mutation, retrospective application, and combined
commodity grades were rejected by the Sponsor-approved methodology.

## Validation requirements

Verify exact canonical bytes and hashes, decision/manifest integrity, strict
effective-boundary behavior, rejection of arbitrary approval and tampered paths,
genuine V3 descriptor binding, loadable assessment policy, historical non-rewrite,
restart preservation, absence of evaluator/forecast mutation, and zero
Provider/broker/production operations.

## Related decisions and documents

- [ADR-0066 — Theta prospective information set and retrieval times](ADR-0066-THETA-PROSPECTIVE-INFORMATION-SET-AND-RETRIEVAL-TIMES.md)
- [Theta V3 combined Answer contract](../interfaces/KRONOS-THETA-V3-COMBINED-ANSWER-CONTRACT.md)
- [TE-03A target authority](../interfaces/KRONOS-MCX-OPTION-TARGET-AUTHORITY-V1.md)
- [TE-05B engineering record](../../engineering/THETA-TE05B-METHODOLOGY-PUBLICATION.md)

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-10-12 | 1 | Codex | Records Sponsor-approved methods and CA-assigned ADR-0067; preserves ADR-0066 | Approved prospective isolated candidate |
