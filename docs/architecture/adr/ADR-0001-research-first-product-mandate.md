# ADR-0001 — Research-First Product Mandate and Execution Deferral

**Document Status:** Draft

## Metadata

- **ADR Number:** ADR-0001
- **Title:** Research-First Product Mandate and Execution Deferral
- **Status:** DRAFT
- **Date:** 2026-07-22
- **Decision Owner:** Chief Architect
- **Proposed By:** Chief Architect mandate; repository draft prepared by KRONOS Engineering
- **Reviewers:** Product Master Architect; Chief Architect
- **Approved By:** Not approved
- **Decision Scope:** Platform and Product
- **Authority Level:** Chief Architect
- **Repository Approval:** Not approved
- **Engineering Status:** Not started

## Context

KRONOS is proposed to prioritize institutional-grade market research and decision support for one discretionary trader. The proposed near-term workflow uses structured Kite data, historical and open-interest research, opportunity discovery, candidate ranking and explanation, TradingView-assisted visual validation, and a final human decision.

Approved architecture already separates Provider Integration, Instrument Identity, Market Schedule, Market Facts, Business Judgment, Risk Approval, Orders, Positions, Runtime Configuration, Platform Events, and Audit Trail. Existing product records, however, classify KRONOS Discover as future vision and retain a roadmap centered on current execution-model maturity.

Current KRONOS Execution is not broker automation. KR-380 produces confirmed execution-timing states, KR-390 manages an objective model trade, and KR-400 emits TradingView alert events. BUY NOW and SELL NOW are not broker orders. The phrase “execution deferral” must therefore distinguish deferred automated broker execution from existing approved decision-support behavior.

The approved platform has no Research domain. Discovery and Replay records are Draft placeholders and grant no ownership. Existing research libraries govern evidence and inquiry but do not authorize architecture or implementation.

## Decision

If approved, this ADR will establish the following decisions:

1. **Research-first product mandate.** The active near-term product objective is opportunity research and discretionary decision support for a single human trader.
2. **Human final authority.** Candidate presentation informs the trader; the trader retains final authority over personal trading action. Human action does not replace or mutate completed domain contracts.
3. **Discovery product boundary.** KRONOS Discover becomes the proposed product capability for research workflow orchestration and candidate presentation. It is not a new Platform Domain and does not acquire semantic ownership from existing domains.
4. **No Research domain in the initial architecture.** Research sources, hypotheses, and evidence governance remain in the Research Library. Runtime semantics remain with existing approved domains.
5. **Kite provider boundary.** Kite is a structured-data provider integrated only through Provider. SDK-specific objects, provider-private semantics, and provider failure details must not become business-domain contracts.
6. **TradingView boundary.** TradingView is the visual chart-validation and presentation interface for the human workflow. It does not own Market Facts, Business Judgment, candidate ranking, Risk Approval, or Execution.
7. **Research coverage.** Futures, Cash, and Options data may enter the research scope through approved Instrument, Market, Provider, and Observation boundaries. Options research does not activate an Options execution module or authorize Options trading logic.
8. **Evidence before presentation.** A presented candidate must reference approved Instrument Identity, attributable Market Facts, the applicable Validation Business Judgment, provenance and observation scope, and known availability or limitation status. This ADR defines no payload, schema, indicator, threshold, score, or BUY/SELL rule.
9. **Automated execution deferral.** Automated broker order placement is outside the active roadmap until 2028 at the earliest. The calendar date does not activate execution automatically; a separate approved ADR and engineering authorization are required.
10. **Existing execution preserved.** The approved Execution Domain, KR-380 timing states, KR-390 objective model trade, KR-400 alert events, ADR-006, and PP-007 remain unchanged. Automated execution is operationally dormant; existing decision-support execution timing may continue for current products.
11. **Research workflow endpoint.** The active KRONOS Discover workflow may end after explicit human-facing presentation and human decision. It does not replace the approved Platform Business Pipeline and creates no path around Risk or Execution if automated execution is later activated.
12. **Unresolved platform-support ownership.** Dataset persistence, replay orchestration, incremental-update mechanics, and TradingView-assisted validation-record ownership remain unassigned until separately approved. Engineering convenience must not decide these responsibilities.

The proposed near-term workflow is:

```text
Kite via Provider
  -> approved Instrument and Market context
  -> Observation Market Facts and reproducible research evidence
  -> Validation Business Judgment and candidate ranking
  -> candidate presentation
  -> TradingView-assisted human review
  -> Human Trading Decision
```

This product workflow is a consumer path, not a replacement domain pipeline.

## Domain Ownership Consequences

| Concern | Owner after approval | Consequence |
| --- | --- | --- |
| Kite connectivity and provider capability | Provider | No business meaning or SDK leakage. |
| Instrument master semantics and universe identity | Instrument | Discovery consumes identity; it does not recreate it. |
| Market schedule semantics | Market | Schedules are authoritative and not inferred from missing data. |
| Historical price, volume, OI, Futures, Cash, and Options facts | Observation | Provider acquisition does not transfer fact ownership. |
| Opportunity interpretation and ranking | Validation | Discovery must not implement an independent ranking meaning. |
| Runtime configuration and secrets | Configuration | Provider consumes approved configuration without owning it. |
| Candidate workflow orchestration and presentation | KRONOS Discover product capability | Product responsibility only; no domain semantic ownership. |
| Research-source and hypothesis lifecycle | Existing Research Library governance | Evidence remains non-authoritative until approval gates complete. |
| Risk Approval, Orders, and Positions | Risk, Execution, and Portfolio | Dormant for automated workflow; ownership remains unchanged. |
| Persistence, replay, and visual-validation records | Unresolved | Separate approval required before implementation. |

## Interface Consequences

This ADR approves no concrete interface fields. If approved, follow-on interface work must:

- formalize Configuration consumption by Provider;
- define a provider-neutral acquisition boundary between Provider and Observation;
- formalize Instrument Identity consumption for scalable universes and contract lifecycles;
- formalize Market Schedule consumption without misusing EAIC-001;
- formalize Market Facts for historical, volume, OI, provenance, and availability semantics;
- define how Discovery references reproducible evidence for Validation without taking fact ownership;
- authorize candidate ranking as Validation Business Judgment and define its presentation consumer;
- define a human-facing presentation boundary that preserves source-domain meaning;
- preserve the existing Risk → Execution → Portfolio path for any future automated workflow.

Each interface requires a separate approved contract or approved amendment before cross-domain implementation. No contract name, payload, schema, transport, or storage technology is decided here.

## Rationale

- Existing domains already own the relevant semantic responsibilities.
- A new Research domain would duplicate Observation, Validation, and existing research-governance responsibilities before a distinct semantic boundary is demonstrated.
- A product capability can coordinate work without violating CA-016 Single Semantic Ownership.
- Explicit human consumption is compatible with CA-018 when documented and does not replace domain completion.
- Deferring broker automation reduces near-term risk without deleting future Execution architecture.
- Provider isolation permits additional data providers without coupling business logic to Kite.
- A research-only Options scope allows evidence collection without prematurely activating Options execution.

## Alternatives Considered

### Create a first-class Research Platform Domain now

Rejected for the initial proposal. Current responsibilities decompose into existing domains and research governance. No distinct stable semantic ownership has been demonstrated.

### Assign market facts, studies, and ranking to Discovery

Rejected. Discovery would duplicate Observation Market Facts and Validation Business Judgment.

### Let Discovery or Validation consume Kite SDK objects directly

Rejected. This violates Provider isolation and contract-based dependencies.

### Replace the approved Platform Business Pipeline with the human workflow

Rejected. The research workflow is a product consumer path; it must not erase Risk, Execution, or Portfolio architecture.

### Deactivate KR-380, KR-390, or KR-400

Rejected. The mandate defers automated broker execution, not existing decision-support responsibilities.

### Implement one-instrument research scripts first and redesign later

Rejected. The required capability must support scalable universes and reproducible datasets without creating throwaway ownership or interfaces.

### Begin with distributed infrastructure

Rejected. Scale requirements should shape contracts and dataset identity, but infrastructure must follow measured need.

## Consequences

### Positive

- Product priority becomes explicit.
- Human authority and automation deferral are recorded.
- Existing domain ownership remains stable.
- Kite and future providers remain isolated from business semantics.
- Research data can expand across Futures, Cash, and Options without activating execution.
- Candidate presentation must retain evidence provenance and explainability.

### Negative

- EP-006 and later work cannot proceed safely until interface and ownership gaps are approved.
- Product roadmaps and permanent briefing documents require reconciliation after approval.
- Dataset persistence, replay, and validation-record responsibilities remain open.
- Existing Core and new Discovery work will coexist and require strict product-boundary discipline.

## Risks

- “Research” may become an informal catch-all that duplicates domain logic.
- Candidate ranking may become a second decision engine if Validation ownership is not enforced.
- Direct SDK use may leak Kite-specific semantics into business code.
- A human workflow may become an undocumented dependency if presentation and record boundaries are not explicit.
- Options research may be mistaken for Options execution approval.
- The 2028 date may be mistaken for automatic authorization.
- Premature persistence or parallelization choices may create infrastructure without approved ownership.

## Affected Products

- KRONOS Discover — proposed activation and primary near-term capability.
- KRONOS Core — remains the shared intelligence product; existing ownership is preserved.
- Cash and Futures execution modules — remain architecturally available but are not the focus of the research roadmap.
- Options — research-data coverage only; execution remains future and unapproved.
- KRONOS Analytics — replay and research records may inform future scope, but no responsibility is assigned by this ADR.

## Affected Interfaces

- Provider Integration Contract.
- Runtime Configuration Contract.
- Instrument Identity Contract.
- Market Schedule Contract and EAIC-001 boundary.
- Market Facts Contract.
- Business Judgment Contract.
- Candidate presentation and human-consumption boundaries, which are not yet approved.
- Existing Risk Approval, Execution Outcome, Order, and Portfolio State contracts remain unchanged.

## Implementation Implications

- EP-004 may proceed only as narrow, read-only Provider connectivity.
- EP-005 may establish scalable Instrument foundations without acquiring Observation or Validation responsibility.
- EP-006 requires approved Provider-to-Observation and Instrument/Market consumption boundaries before publishing research data.
- EP-007 is blocked until persistence, provenance, incremental-update, and replay ownership are approved.
- EP-008 is blocked until KRONOS Discover product responsibilities and scanning interfaces are approved.
- EP-009 is blocked until candidate evidence and Validation ranking responsibilities are approved.
- EP-010 is blocked until presentation, TradingView-assisted review, and human-record boundaries are approved.
- Automated order placement is excluded from the active roadmap.

## Migration Impact

No runtime migration is authorized by this Draft.

After approval:

1. Reconcile product architecture, vision, project memory, and canonical roadmap.
2. Approve KRONOS Discover responsibilities, constraints, and interfaces.
3. Approve required domain and product interface contracts without changing existing ownership.
4. Sequence EP-004 through EP-010 behind their architecture gates.
5. Preserve current Swing/Pine behavior and existing public contracts.
6. Record any later activation of automated execution in a separate ADR.

## Validation Requirements

- Confirm every proposed product responsibility maps to one approved owner or remains explicitly unresolved.
- Confirm no new direct business-domain dependency is introduced without an approved contract.
- Confirm Provider-specific objects cannot cross the Provider boundary.
- Confirm candidate ranking does not duplicate KR-370 or another Validation responsibility.
- Confirm human presentation cannot mutate Market Facts or Business Judgment.
- Confirm Options research cannot activate Options execution.
- Confirm existing KR-370, KR-380, KR-390, KR-400, ADR-006, and PP-007 behavior remains unchanged.
- Confirm each roadmap EP satisfies its stated architecture gate before implementation.

## Validation Evidence

- [Architecture Impact Assessment](../products/discovery/RESEARCH_FIRST_ARCHITECTURE_IMPACT_ASSESSMENT.md)
- [Proposed Engineering Roadmap](../products/discovery/RESEARCH_FIRST_ENGINEERING_ROADMAP.md)
- [Research Library Governance](../../../research/intraday/README.md)

## Supersedes

None.

## Superseded By

None.

## Related ADRs

- [ADR-006 — Execution Context Provider Architecture](ADR-006-Execution-Context-Provider-Architecture.md)
- [ADL-001 — Futures Model Architecture](../ADL-001-Futures-Model.md)
- [ADL-002 — MCX Self-Contained Execution](../ADL-002-MCX-Self-Contained-Execution.md)
- [ADL-003 — Execution Context Adapters](../ADL-003-Execution-Context-Adapters.md)
- [ADL-004 — Model Trade Ownership](../ADL-004-Model-Trade-Ownership.md)
- [ADL-005 — Alert Architecture](../ADL-005-Alert-Architecture.md)

## Related Documents

- [PLATFORM-000 — KRONOS Platform Constitution](../platform/PLATFORM-000-CONSTITUTION.md)
- [Platform Business Pipeline](../platform/PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [KRONOS Platform Product Architecture](../../product/KRONOS_PLATFORM_ARCHITECTURE.md)
- [KRONOS Platform Governance](../../product/PLATFORM_GOVERNANCE.md)
- [KRONOS Vision and Roadmap](../../product/KRONOS_VISION_AND_ROADMAP.md)
- [KRONOS Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../DATA_FLOW.md)
- [PP-007 — Execution Semantics Across Markets](../principles/PP-007-Execution-Semantics-Across-Markets.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-07-22 | 0.1 | KRONOS Engineering | Initial Draft for Chief Architect review. | Not approved |
