# ADR-0017 — KRONOS Platform Governed Active Derivative Contract Selection V1

## Metadata

- **ADR Number:** ADR-0017
- **Title:** KRONOS Platform Governed Active Derivative Contract Selection V1
- **Status:** APPROVED
- **Date:** 2026-08-26
- **Decision Owner:** Chief Architect
- **Proposed By:** KRONOS Intraday Engineering Architect
- **Reviewers:** Chief Architect / KRONOS Intraday Engineering Architect
- **Approved By:** Chief Architect
- **Decision Scope:** Platform / DOMAIN-001 / DOMAIN-006 / DOMAIN-008 / Intraday
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for publication
- **Engineering Status:** WO-06MCX-R implementation authorized after publication
- **Runtime Authority:** Existing WO-06MCX-R operational gates only
- **Provider Acquisition Authority:** Existing WO-06MCX-R operational gates only
- **Broker Authority:** NONE
- **Trading / Risk / Entry Authority:** NONE

## Context

[ADR-0014](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md)
approved persistent MCX analytical subjects, expiry-specific derivative
contracts and immutable active derivative bindings. It deliberately deferred
automatic contract selection, including nearest-expiry selection.

WO-06MCX-A subsequently published DOMAIN-008 contract-family expiry-session
authority, including exact expiry-day eligibility cutoffs. The five governed
Intraday MCX subjects still require one deterministic, fail-closed selection
rule before a new factual Refresh can bind an eligible Provider contract.

This decision supplies only that missing selection authority. It does not
change persistent analytical identity, Provider ownership, session ownership,
Intraday methodology or execution eligibility.

## Decision

### 1. Selection-rule identity

The approved selection rule is:

`KRONOS-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1 / 1.0.0`.

### 2. Ownership

Ownership is fixed as follows:

- DOMAIN-001 owns analytical-subject and derivative-family mapping,
  candidate-set meaning, active-contract resolution and immutable Active
  Derivative Binding.
- DOMAIN-006 owns factual Provider Instrument Master records only.
- DOMAIN-008 owns trading date and session, contract-family expiry-session
  eligibility and expiry-day cutoff semantics.
- Intraday consumes an Active Derivative Binding and owns no selection
  authority.

### 3. Explicit family mappings

The V1 mappings are exact:

| Persistent analytical subject | Governed Provider contract family |
| --- | --- |
| `GOLDM` | `GOLDM` |
| `SILVERM` | `SILVERM` |
| `COPPER` | `COPPER` |
| `NATGAS` | `NATURALGAS` |
| `CRUDE` | `CRUDEOIL` |

Prefix, substring, fuzzy, Provider-order and inferred alias matching are
prohibited. Unknown mappings fail closed.

### 4. Candidate eligibility

A Provider record is an eligible candidate if and only if all of the following
hold at the governed observation boundary:

1. the Provider record is valid;
2. exchange and segment are the governed MCX values;
3. instrument type is futures (`FUT`);
4. the record matches the exact governed family mapping;
5. expiry is present and valid;
6. DOMAIN-008 temporal eligibility is available;
7. expiry eligibility has not passed; and
8. canonical and Provider integrity validation passes.

Provider options, wrong variants, wrong exchange or segment, stale or expired
records, unknown families and integrity failures are ineligible. A missing or
stale Provider source fails closed.

### 5. Selection

Among eligible candidates, DOMAIN-001 selects the minimum expiry only when
exactly one governed candidate exists at that minimum expiry.

If two or more governed candidates remain at the minimum expiry, resolution
fails closed as `ACTIVE_DERIVATIVE_BINDING_AMBIGUOUS`. Symbol, Provider token,
Provider response order and directory order are prohibited tie-breakers.

If no eligible candidate exists, resolution fails closed as an unavailable
active derivative binding. A stale prior binding is not a fallback.

### 6. Same-day expiry

DOMAIN-008 exclusively determines whether a same-day expiry remains eligible
at the observation boundary. DOMAIN-001 consumes that result without
reinterpreting the cutoff.

At or before an inclusive DOMAIN-008 expiry-day cutoff, the candidate may
remain eligible. After the governed cutoff, it is ineligible and the resolver
evaluates the remaining eligible candidates.

### 7. Observation boundary

Every resolution uses a governed market or analysis observation boundary, not
an arbitrary process wall clock where such a boundary already exists. The
binding preserves the exact boundary and DOMAIN-008 authority under which the
selected contract was eligible.

### 8. Immutable binding and roll

The resolver reevaluates at every new governed analysis or Refresh boundary.
When the previously selected contract becomes ineligible, a newly selected
minimum-expiry contract produces a new immutable binding identity.

Earlier bindings and all Discovery, Probables and replay evidence linked to
them remain unchanged. A current binding for a new Refresh cannot reinterpret
the contract bound to a historical run.

### 9. Failure isolation

Selection failure is per analytical subject unless a shared publication,
integrity or runtime prerequisite prevents the entire governed operation. One
MCX subject failure does not remove that subject from the Intraday universe and
does not stop other MCX, NSE equity or index members.

### 10. Authority boundary

An Active Derivative Binding establishes contract-specific factual
consumability only. It is not execution eligibility and grants no trading,
Entry, Risk, Sponsor-decision or broker authority.

Provider tokens remain DOMAIN-006-owned operational identifiers and must not
appear in canonical identity, binding identity, Sponsor-facing evidence or
Browser projection.

## Rationale

Minimum eligible expiry is deterministic, auditable and compatible with the
published DOMAIN-008 expiry-session boundary. Requiring uniqueness at the
minimum expiry prevents hidden tie-break policy. Exact family mappings preserve
canonical analytical identity while allowing Provider-specific contract
lineage.

## Alternatives Considered

- **Continue requiring a manually supplied active binding:** superseded for
  this bounded five-family V1 path because Chief Architect authority now
  approves deterministic selection.
- **Use volume, open interest or liquidity:** rejected; no such selection
  authority is granted.
- **Use Provider response order, symbol order or token order:** rejected as
  non-governed and non-semantic.
- **Reuse the last binding after Provider or eligibility failure:** rejected;
  selection must fail closed at the new boundary.

## Consequences

- DOMAIN-001 may implement the typed V1 resolver and binding persistence.
- DOMAIN-006 remains a factual-source owner and does not choose contracts.
- DOMAIN-008 remains the sole expiry-session and cutoff authority.
- Intraday may consume a successful binding without owning selection.
- Contract roll creates new immutable evidence without rewriting history.
- WO-06MCX-R engineering may resume after this ADR is published.

## Risks

- Loose alias matching could bind the wrong commodity variant.
- A hidden secondary sort could conceal an ambiguous minimum expiry.
- Process wall-clock use could disagree with a governed analysis boundary.
- A stale binding fallback could misattribute new facts after expiry.
- Provider tokens could leak into product-visible evidence.

All listed risks require focused fail-closed tests.

## Affected Products

- Intraday: consumer of active derivative bindings for the five governed MCX
  analytical subjects.
- Swing: no analytical or product-state change authorized.

## Affected Interfaces

- DOMAIN-001 `ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1` remains the immutable
  binding contract.
- DOMAIN-006 Provider Instrument Master records remain factual inputs.
- DOMAIN-008 MCX contract-family expiry-session authority supplies temporal
  eligibility.

## Implementation Implications

WO-06MCX-R may implement:

- exact V1 family mapping;
- typed candidate filtering and minimum-expiry resolution;
- immutable binding persistence and explicit-identity reload;
- roll and ambiguity behavior;
- Intraday factual-source consumption; and
- sanitized Browser lineage.

Live Provider acquisition and live Refresh remain subject to their existing
operational authorization gates.

## Validation Requirements

- ADR numbering and index integrity;
- repository-relative link validation;
- explicit mapping tests for all five families;
- before, at and after expiry-cutoff tests;
- ambiguity, missing, stale and integrity failure tests;
- roll and immutable-history tests;
- DOMAIN-001, DOMAIN-006, DOMAIN-008, Intraday, Browser and Swing regression;
- secret and Provider-token projection scans; and
- confirmation that no execution authority is introduced.

## Validation Evidence

WO-06MCX-R publication evidence.

## Supersedes

[ADR-0014](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md)
only for its deferred automatic-contract-selection boundary. All other
ADR-0014 decisions remain approved and unchanged.

## Superseded By

None.

## Related ADRs

- [ADR-0014 — DOMAIN-001 Canonical Instrument V2 Semantic Layering, Provider
  Classification, and Active Derivative Binding Architecture](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md)
- [ADR-009 — Provider-Bounded Instrument Master Acquisition
  Architecture](../platform/domains/provider/ADR-009-PROVIDER-BOUNDED-INSTRUMENT-MASTER-ACQUISITION-ARCHITECTURE.md)

## Related Documents

- [DOMAIN-001 Instrument Architecture](../platform/domains/instrument/ARCHITECTURE.md)
- [DOMAIN-006 Provider Architecture](../platform/domains/provider/ARCHITECTURE.md)
- [DOMAIN-008 Market Engineering](../platform/domains/market/ENGINEERING.md)
- [Intraday Native Universe V1](../products/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1.md)
- [Intraday Engineering Methodology and Architecture
  Record](../products/intraday/KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-26 | 1.0 | Codex Engineering Support | Published the Chief Architect-approved governed active derivative contract selection authority | APPROVED |
