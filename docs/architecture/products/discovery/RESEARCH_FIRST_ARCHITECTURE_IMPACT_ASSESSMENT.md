# Research-First Product Mandate — Architecture Impact Assessment

**Status:** Draft
**Owner:** Chief Architect
**Approved By:** Not approved
**Date:** 2026-07-22

## Purpose

Assess whether the approved KRONOS architecture can support a research-first, discretionary decision-support workflow and identify the formal decisions required before that workflow becomes authoritative.

This assessment is not approved architecture. It changes no domain, dependency, contract, engine responsibility, product priority, or runtime behavior.

## Executive Conclusion

The approved platform already contains most semantic boundaries needed for a research-first workflow: Provider, Instrument, Market, Observation, Validation, Configuration, Audit, and the existing research-governance lifecycle. It does not yet approve the proposed end-to-end Discovery product workflow, candidate-presentation interfaces, dataset-lifecycle ownership, or the change from future Discovery work to a near-term product mandate.

A new first-class Research domain is not currently justified. The least disruptive proposal is to treat research-first opportunity discovery as a KRONOS Discover product capability implemented through a bounded subsystem or application orchestration layer. That capability must consume approved domain contracts without acquiring their semantic ownership.

A new ADR is required because the mandate changes product priority, explicitly authorizes a human-decision endpoint, activates Futures/Cash/Options research scope, and defers automated broker execution until 2028. The ADR must not deactivate or reinterpret the existing KR-370, KR-380, KR-390, or KR-400 responsibilities.

EP-004 may proceed conditionally as a narrow, read-only Provider integration step. It must not publish Market Facts, expose Kite SDK objects to business domains, or establish any unapproved cross-domain contract.

## Current Approved Architecture

### Platform domains

The approved Platform Architecture defines eleven domains:

- Instrument owns Instrument Identity.
- Observation owns Market Facts.
- Validation owns Business Judgment.
- Risk owns Risk Approval.
- Execution owns Orders and preserves KR-380 execution-timing ownership.
- Portfolio owns Positions and preserves the KR-390 objective model trade.
- Provider owns Provider Integration.
- Market owns Market Schedule.
- Event owns Platform Events.
- Configuration owns Runtime Configuration.
- Audit owns the read-only Audit Trail.

The approved business pipeline is:

**Instrument → Observation → Validation → Risk → Execution → Portfolio**

Provider, Market, Event, and Configuration support the pipeline without acquiring business judgment. Audit observes published contracts read-only.

### Product architecture

The existing product architecture defines KRONOS Core and current Cash/Futures execution modules. It records KRONOS Discover and KRONOS Analytics as future vision, not active development. The canonical roadmap prioritizes current execution-model maturity before scanner and broader platform workflows.

### Research governance

The repository already separates source review, research synthesis, architecture governance, engineering, live validation, and production. Research evidence does not create architecture or implementation authority. This lifecycle can govern hypothesis testing and research provenance without creating a Platform Domain.

### Current execution boundary

The current KRONOS execution architecture is decision support, not broker automation:

- KR-370 owns direction and BUY READY / SELL READY.
- KR-380 owns final execution timing and BUY NOW / SELL NOW.
- BUY NOW and SELL NOW are not broker orders.
- KR-390 owns the objective model trade, not a personal broker position.
- KR-400 owns confirmed TradingView alert-event edges, not broker automation.

## Existing Support for the Proposed Workflow

| Proposed need | Approved architectural support | Remaining gap |
| --- | --- | --- |
| Kite integration | Provider owns external Provider Integration. | No approved provider-neutral market-data acquisition interface exists. |
| Instrument master and universe identity | Instrument owns canonical Instrument Identity and approved relationships. | Scalable master lifecycle and product-consumer contract are not formally specified. |
| Market schedules and availability | Market owns Market Schedule; EAIC-001 governs presentation-facing Exchange Availability. | EAIC-001 explicitly does not define acquisition schedules, calendars, or market-data readiness. |
| Historical price, volume, OI, Futures, Cash, and Options facts | Observation owns Market Facts. | Dataset provenance, persistence, replay, retention, expiry, rollover, and update ownership are not approved. |
| Evidence interpretation and candidate ranking | Validation owns Business Judgment. | Candidate ranking is not yet defined as an approved Validation output or product interface. |
| Hypothesis testing | Existing research governance defines evidence and hypothesis lifecycles. | Runtime/product ownership and reproducible dataset linkage are not approved. |
| Candidate presentation | Current KR-705 and approved explainability contracts demonstrate presentation separation. | No approved Discovery candidate-presentation contract or consumer is defined. |
| TradingView-assisted review | TradingView is the current human-facing chart environment. | No approved visual-validation workflow or record ownership exists. |
| Human final decision | CA-018 permits explicitly authorized human review, presentation, approval, and action. | The proposed endpoint is not yet explicitly authorized for KRONOS Discover. |
| Future execution | Risk, Execution, and Portfolio remain approved and available. | Activation from a research candidate or human decision would require a separately approved path. |

## Domain Ownership Findings

The following findings preserve approved ownership. Items marked unresolved must not be assigned during implementation without approval.

| Concern | Approved owner or current authority | Assessment |
| --- | --- | --- |
| Provider capability and external connectivity | Provider | Kite belongs behind Provider. Provider must not own Market Facts or Business Judgment. |
| Instrument identifiers, classifications, contracts, expiries, and analysis/reference/execution relationships | Instrument | Instrument owns semantic identity. Exact master lifecycle behavior remains to be specified. |
| Market sessions and authoritative schedule meaning | Market | Market owns schedules; absence or staleness of data must not be used to infer schedule state. |
| Historical price, volume, and OI as observed facts | Observation | Observation owns published facts, irrespective of whether Provider acquired them. |
| Derived factual studies that do not interpret business meaning | Observation | Permitted only when they remain factual; the boundary with judgment must be reviewed explicitly. |
| Opportunity interpretation and candidate ranking | Validation | Ranking is Business Judgment if it expresses comparative business meaning. It must not be recreated in Discovery. |
| Research sources, hypotheses, evidence profiles, and architecture-candidate traceability | Existing Research Library governance | These are research artefacts, not runtime domain contracts or production authority. |
| Market-scan orchestration | Unresolved; proposed Discovery product capability | Scanning may coordinate approved contracts but must not own Instrument Identity, Market Facts, or ranking meaning. |
| Dataset persistence and incremental-update mechanics | Unresolved | Storage mechanics are not semantic ownership. A platform responsibility and governing contract must be approved before EP-007. |
| Replay dataset lifecycle and replay orchestration | Unresolved | The existing Replay domain scaffold is Draft and grants no authority. |
| TradingView-assisted validation records | Unresolved | Presentation does not own source meaning; Audit does not automatically acquire workflow-record ownership. |
| Candidate presentation | Unresolved product responsibility | Presentation must preserve Validation meaning and must not become a second decision engine. |
| Human discretionary action | External actor | The human may act on presented information but does not replace completed domain contracts or silently become a domain. |

## Is a New Research Domain Required?

No, not on current evidence.

The proposed responsibilities separate into existing semantic owners plus product orchestration:

- Provider integrates with Kite.
- Instrument identifies the universe.
- Market owns schedules.
- Observation publishes facts.
- Validation owns interpretation and ranking.
- Existing research governance owns the evidence-to-architecture lifecycle for research artefacts.
- A Discovery product capability can coordinate the workflow and presentation without taking semantic ownership.

A new domain should be considered only if a stable semantic responsibility remains after these boundaries are applied, has multiple independent consumers, cannot be expressed through existing approved contracts, and receives Chief Architect approval through an ADR. Dataset size, persistence technology, or application convenience alone does not establish a domain.

An application service is an implementation pattern, not an ownership decision. Engineering may use one only after product responsibilities and interfaces are approved.

## Conflicts and Gaps

| Repository authority | Proposed mandate | Assessment |
| --- | --- | --- |
| KRONOS Discover is Future Vision and not active development. | Research/discovery becomes the near-term priority. | Direct product-priority conflict; requires an approved ADR and roadmap amendments. |
| The canonical roadmap prioritizes KR-390/KR-400 validation and model parity before scanner workflows. | EP-004 through EP-010 become the active roadmap. | Roadmap conflict; current roadmap must not be silently replaced. |
| The approved platform pipeline continues through Risk, Execution, and Portfolio. | The near-term workflow ends with a Human Trading Decision. | Compatible only as an explicitly authorized product-consumer path that does not replace the platform pipeline. |
| Current Execution owns KR-380 timing and remains active in the existing product. | “Execution is operationally dormant.” | Ambiguous conflict. Only automated broker execution may be declared dormant; existing decision-support timing must remain unchanged unless separately approved. |
| Options is a current non-goal/future execution module. | Options data is part of near-term research coverage. | Requires a scope distinction: Options research data may be proposed without activating Options execution or trading rules. |
| Discovery product files are Draft placeholders. | Discovery is expected to orchestrate production workflow. | No approved responsibilities or interfaces exist yet. |
| Replay domain files are Draft placeholders. | Replay and reproducible datasets are required. | No approved Replay ownership exists. |
| Existing approved interfaces cover Exchange Availability and Execution Context. | Provider, research, ranking, presentation, and human-decision boundaries require contracts. | Required contracts are absent or only named semantically in domain documents. |
| No approved record states the year 2028. | Automated execution is deferred until 2028. | The date must be recorded through an approved ADR; it cannot be inferred from existing architecture. |

## Required Interface Decisions

This assessment defines no payloads or schemas. It identifies contract decisions that must be reviewed.

| Boundary | Existing basis | Required decision |
| --- | --- | --- |
| Configuration → Provider | Runtime Configuration Contract is named in approved domain architecture. | Formalize Provider consumption without exposing secrets outside Configuration. |
| Provider → Observation | Provider Integration and Market Facts are separately owned. | Approve a provider-neutral acquisition boundary that prevents Kite SDK objects and provider semantics from leaking into Observation. |
| Instrument → acquisition and Discovery | Instrument Identity Contract is named in approved domain architecture. | Formalize identity, universe, contract-expiry, and relationship semantics needed by consumers. |
| Market → acquisition and Discovery | Market Schedule Contract is named; EAIC-001 is presentation-only. | Formalize authoritative scheduling use without deriving schedules from data availability. |
| Observation → Discovery and Validation | Market Facts Contract is named in approved domain architecture. | Formalize historical, OI, volume, provenance, and availability semantics without embedding interpretation. |
| Research/Discovery → Validation | No approved product contract exists. | Decide how reproducible evidence sets and hypothesis context are referenced without creating a new semantic owner. |
| Validation → candidate presentation | Business Judgment Contract is named in approved domain architecture. | Approve candidate-ranking meaning and a presentation consumer without duplicating KR-370 or other Validation ownership. |
| Candidate presentation → Human | CA-018 permits explicit human consumption. | Approve a read-only human-facing workflow that preserves source meaning and records no hidden domain completion. |
| Human decision → future Risk/Execution | Existing Risk Approval, Execution Outcome, and Order contracts govern the platform pipeline. | Any activation path requires a future approved decision; a human action must not bypass Risk or redefine Execution. |

## Approved Documents Requiring Amendment After ADR Approval

No approved document is amended by this assessment. If ADR-0001 is approved, the following should be reviewed and updated through repository governance:

- `docs/product/KRONOS_PLATFORM_ARCHITECTURE.md` — activate and define KRONOS Discover at product level.
- `docs/product/KRONOS_VISION_AND_ROADMAP.md` — record the research-first priority, human endpoint, research coverage, and automation deferral.
- `docs/product/KRONOS_PROJECT_MEMORY.md` — align the permanent briefing and current priorities.
- `ROADMAP.md` — replace or reconcile the canonical delivery sequence.
- `docs/architecture/products/discovery/` — define approved responsibilities, constraints, and interfaces.
- `docs/architecture/interfaces/` — add approved contracts or profiles for the new boundaries.
- Architecture and ADR indexes — add approved references after review.

The frozen Platform Constitution, domain identities, Domain Ownership Matrix, Domain Dependency Matrix, and existing domain architecture documents do not require amendment if the proposal preserves their current responsibilities and treats Discovery as a product capability. Any new domain, dependency, or ownership assignment would require explicit amendments under CA-019.

## Areas That Must Remain Unchanged

- DOMAIN-001 through DOMAIN-011 identities and approved ownership.
- Instrument Identity, Market Facts, Business Judgment, Risk Approval, Orders, Positions, Provider Integration, Market Schedule, Runtime Configuration, Platform Events, and Audit Trail ownership.
- KR-370 direction and BUY READY / SELL READY ownership.
- KR-380 timing and BUY NOW / SELL NOW ownership.
- KR-390 objective model-trade ownership.
- KR-400 confirmed alert-event ownership.
- ADR-006 Execution Context Provider and consumer boundaries.
- PP-007 market-neutral execution semantics.
- Research evidence remaining non-authoritative until governance approval.
- Options research remaining separate from Options execution.
- Existing Swing production behavior.

## Recommendation

1. Submit the accompanying ADR-0001 Draft for Chief Architect review.
2. Do not create a Research Platform Domain at this stage.
3. Treat KRONOS Discover as the proposed product capability and bounded workflow coordinator.
4. Preserve semantic ownership in Provider, Instrument, Market, Observation, Validation, and Configuration.
5. Approve interface boundaries before EP-006 publishes data beyond Provider internals.
6. Resolve dataset persistence, replay, candidate-presentation, and workflow-record ownership before EP-007, EP-008, EP-009, or EP-010 implementation.
7. Keep automated broker execution outside the active roadmap until 2028 at the earliest and require a separate approval before activation.
8. Preserve current KRONOS Core/Swing execution-timing behavior; product reprioritization does not disable approved engines.

## EP-004 Safety Assessment

EP-004 may proceed safely only as a narrow Provider-internal, read-only connectivity capability under the approved Provider and Configuration boundaries.

EP-004 must not:

- publish Market Facts;
- expose Kite SDK-specific objects outside Provider;
- define the Provider-to-Observation data contract;
- create candidate ranking or business judgment;
- persist research datasets;
- place, modify, or cancel orders;
- activate an Execution path.

Any scope beyond connection capability, provider availability, and internally verified read-only access must wait for the applicable approved interfaces.

## Open Decisions Requiring Chief Architect Approval

- Approval or rejection of the research-first product mandate and 2028 automation deferral.
- Whether KRONOS Discover becomes the active product name and boundary.
- Whether candidate ranking is an approved extension of Validation Business Judgment and which existing engine or future component may implement it.
- Ownership of dataset persistence, provenance, retention, incremental updates, and reproducibility.
- Ownership of replay orchestration and replay records.
- Ownership and lifecycle of TradingView-assisted validation records.
- The approved candidate-presentation consumer and human-decision record boundary.
- The exact interfaces and compatibility rules between existing domains and Discovery.
- Whether Options research coverage may become active while Options execution remains deferred.
- The approval gates for EP-005 through EP-010.

## Authoritative References

- [PLATFORM-000 — KRONOS Platform Constitution](../../platform/PLATFORM-000-CONSTITUTION.md)
- [KRONOS Platform Overview](../../platform/PLATFORM_OVERVIEW.md)
- [Platform Business Pipeline](../../platform/PLATFORM_BUSINESS_PIPELINE.md)
- [Domain Dependency Matrix](../../platform/DOMAIN_DEPENDENCY_MATRIX.md)
- [Domain Ownership Matrix](../../platform/DOMAIN_OWNERSHIP_MATRIX.md)
- [KRONOS Platform Product Architecture](../../../product/KRONOS_PLATFORM_ARCHITECTURE.md)
- [KRONOS Platform Governance](../../../product/PLATFORM_GOVERNANCE.md)
- [KRONOS Vision and Roadmap](../../../product/KRONOS_VISION_AND_ROADMAP.md)
- [KRONOS Engine Ownership](../../ENGINE_OWNERSHIP.md)
- [Project KRONOS Data Flow](../../DATA_FLOW.md)
- [Research Library](../../../../research/README.md)
- [ADR Governance](../../adr/ADR_GOVERNANCE.md)
