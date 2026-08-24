# ADR-0015 — Swing Sponsor Observation-Phase Authority and Step-31 Evidence Governance

## Metadata

- **ADR Number:** ADR-0015
- **Decision Identity:** SWING-OBS-GOV-01
- **Policy Identity:** SWING-STEP31-OBSERVATION-PHASE-V1
- **Title:** Swing Sponsor Observation-Phase Authority and Step-31 Evidence Governance
- **Status:** APPROVED
- **Date:** 2026-08-24
- **Decision Owner:** Chief Architect
- **Proposed By:** Sponsor / Swing Engineering Architect
- **Reviewers:** Chief Architect
- **Approved By:** Chief Architect
- **Decision Scope:** Swing Product / Platform / Interface / Research Governance
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved in repository
- **Engineering Status:** Architecture only; STEP31-OBS-01, SPONSOR-OBS-01, and JOURNAL-OBS-01 not started
- **Runtime Authority:** NONE
- **Broker Authority:** NONE
- **Autonomous Trading:** NOT AUTHORIZED

## Context

Current Swing V1 correctly separates KR-370 analytical promotion, Step-31
geometry, DOMAIN-007 Risk permission, KR-380 entry timing, the KR-390 objective
model, Sponsor Decision, and Sponsor Position. Real Sponsor operation exposed a
different concern: the current Step-31 implementation represents poor,
unfavourable, or incomplete geometry as an unavailable Trade Plan, which also
suppresses the downstream Sponsor decision surface.

That behavior allows a mathematical assessment to substitute for the Sponsor's
participation judgment. Step-31 has not yet accumulated enough real operational
evidence to justify that authority. The initial observation phase must retain
its mathematics and warnings as governed evidence while the Sponsor makes the
explicit participation choice and KRONOS independently observes subsequent
objective evidence.

The initial intended evidence horizon is approximately three to four months of
real Sponsor operation. It is not an automatic expiry timer and creates no
automatic methodology or authority change. A later approved work order is
required to evaluate the evidence or change Step-31.

## Authority audit

The following current authorities were reviewed before this decision:

| Authority | Current result | ADR-0015 disposition |
| --- | --- | --- |
| ADR-0011 / KR-370 | `BUY NOW` / `SELL NOW` means analytical promotion complete and Step-31 eligible | No change |
| ADR-0012 / UX-05 | Exact current promotion may enter Step-31; Step-31 alone owns geometry | No change to eligibility; future observation presentation is authorized |
| Step-31 V0 | Invalid or unavailable geometry produces `TRADE_PLAN_UNAVAILABLE` and currently suppresses Sponsor controls | Prospective contract amendment required under STEP31-OBS-01 |
| DOMAIN-007 / ADR-0013 | Fail-closed permission gate for objective KR-380 timing; current V1 requires an exact valid Step-31 plan | Remains hard for objective progression; it does not own Sponsor choice |
| ECPC V2 | Packages Risk-permitted, plan-bound monitoring context for KR-380 | No change |
| KR-380 V2 | Owns objective entry timing | No change |
| KR-390 | Owns the objective model lifecycle after a valid triggered Entry Outcome | No change |
| Sponsor Decision V1 | Records `LIVE`, `PAPER`, or `IGNORE` against current Risk and geometry | Prospective observation-phase version/extension required |
| Native active lifecycle | Tracks governed objective and Sponsor-position lifecycles | No authority change |
| Step 33 | Begins from a closed objective model and can consume optional Sponsor evidence | Insufficient alone for every ignored/no-model observation; linked research-ledger work required |
| UX-10 | Delivers governed notifications and owns no decision meaning | No change |
| Trade Window / Browser | Presents ready geometry and currently suppresses PAPER/LIVE when construction is invalid | Later presentation/runtime change required |
| ADR-0014 / DOMAIN-001 | Owns canonical Instrument V2 and derivative bindings | No relevant authority change |

No higher-authority ownership conflict prevents this prospective decision.
ADR-0015 supersedes only the current implication that Step-31 geometry quality
alone may silently determine the Sponsor participation outcome. It does not
supersede identity, integrity, Risk, execution-context, objective-model, or
broker boundaries.

## Decision

### 1. Observation-phase operating principle

The canonical operating principle is:

```text
KR-370 RECOMMENDS.
STEP-31 CALCULATES AND WARNS.
THE SPONSOR DECIDES.
KRONOS MONITORS AND RECORDS.
```

For `SWING-STEP31-OBSERVATION-PHASE-V1`, Step-31 geometry is governed
decision-time evidence. Geometry quality alone does not become the Sponsor's
`IGNORE` decision.

### 2. KR-370 remains unchanged

Current KR-370 `BUY NOW` and `SELL NOW` continue to mean only that all governed
K1-K5 analytical-promotion criteria are satisfied for the exact bound evidence.
They establish Step-31 eligibility only. They do not mean Entry triggered,
Trade Plan valid, Risk approved, Sponsor action taken, position created, order
placed, fill received, or broker execution performed.

`BUY READY`, `SELL READY`, potential states, `NO SETUP`, criteria, hard gates,
and their current authority remain unchanged.

### 3. Step-31 owns calculation and warning evidence

Step-31 continues to own Entry, Stop, Target, invalidation, risk distance,
reward distance, R:R, construction provenance, and mathematical availability.
It must preserve safely calculable facts exactly, including unfavourable facts,
and must never select a different level merely to improve the result.

The observation-phase contract must distinguish:

- each factual geometry value and its availability;
- mathematical/structural warning identities;
- warning severity for presentation, if used;
- hard trust-boundary failures; and
- downstream activation eligibility.

Presentation severity such as green, amber, or red is explanatory only. Red is
not automatically a Sponsor veto; green is not a guarantee; no colour carries
broker authority.

### 4. Step-31 geometry-warning classification

When supported by the existing governed calculation, the following are
**ADVISORY / MATHEMATICAL WARNINGS** during Observation Phase V1:

- `TARGET_BELOW_ENTRY` for LONG;
- `TARGET_ABOVE_ENTRY` where invalid for SHORT;
- `NON_POSITIVE_REWARD`;
- `NON_POSITIVE_RISK`;
- `RR_UNFAVOURABLE`;
- `TARGET_UNAVAILABLE`;
- `STOP_UNAVAILABLE`;
- `ENTRY_UNAVAILABLE`;
- `STRUCTURAL_GEOMETRY_WARNING`; and
- an existing equivalent factual geometry warning.

The list grants no new threshold or predicate. A producer may emit only a
warning justified by current approved mathematics. Unavailable facts remain
unavailable; R:R is unavailable where it cannot be meaningfully calculated.

These conditions may remain hard blockers for a downstream mechanism that
requires the missing or positive geometry fact. They are not, by themselves,
the Sponsor's participation decision.

### 5. Genuine hard blockers

The following remain fail closed and are never downgraded to presentation:

- stale or foreign run, instrument, assessment, evidence cycle, or policy;
- identity, lineage, version, digest, integrity, freshness, or currentness
  failure;
- malformed or corrupt evidence;
- missing mandatory trust-boundary identity;
- untrusted, foreign, or invalid execution context;
- Portfolio State source incompleteness where DOMAIN-007 requires it;
- a current DOMAIN-007 `REJECTED` or `UNAVAILABLE` result at a boundary that
  requires Risk permission;
- a non-`QUALIFIED` ECPC context at a boundary that requires it;
- ambiguous or unordered monitoring evidence where objective ordering is
  mandatory; and
- another existing governed security, safety, or authority prohibition.

A hard blocker prevents the affected downstream activation. It does not
rewrite KR-370 or manufacture an `IGNORE` decision.

### 6. DOMAIN-007 hard-blocker classification

DOMAIN-007 V1 remains a fail-closed objective-model Risk Permission gate:

| DOMAIN-007 state/fact | Classification under ADR-0015 |
| --- | --- |
| `APPROVED` | Permits objective timing only; not a Sponsor recommendation |
| `CONSTRAINED` | Permits bounded objective timing only; constraints remain authoritative |
| `REJECTED` | Genuine hard authority blocker for KR-380/KR-390 progression and Sponsor-position activation |
| `UNAVAILABLE` | Genuine fail-closed blocker wherever Risk permission is mandatory |
| Risk reason, constraint, and availability facts | Presentable and retainable evidence; they do not independently become Sponsor choice |
| Missing/stale/mismatched Risk lineage or Portfolio State | Genuine hard trust-boundary blocker |

No existing DOMAIN-007 state is reclassified as purely advisory. ADR-0015 does
not add a Risk threshold, quantity policy, allocation rule, or new Risk state.
Current `APPROVED`/`CONSTRAINED` permission remains mandatory for objective
KR-380 timing and any downstream activation that already requires it.

### 7. Sponsor participation authority

For an exact current KR-370 `BUY NOW` or `SELL NOW`, the observation-phase
Sponsor choices are `LIVE`, `PAPER`, and `IGNORE`. The choice must be explicit;
there is no default or automatic mode.

The observation-phase decision surface may record the Sponsor's exact choice
after showing every safely available Step-31 and Risk fact and warning. That
record is evidence of Sponsor judgment; it does not itself activate a position,
objective model, Entry Outcome, broker order, or fill.

Where a genuine hard blocker prevents Sponsor-position or objective-model
activation, the decision and blocker may be retained for research, but the
prohibited downstream effect must not occur. This preserves the Sponsor's
judgment without bypassing DOMAIN-007, ECPC, KR-380, KR-390, or lifecycle
integrity.

### 8. LIVE, PAPER, and IGNORE

`PAPER` remains Sponsor-selected simulated participation. A warning may be
attached. No broker fill, actual monetary P&L, or actual R may be fabricated.
A PAPER observation decision creates no Sponsor Position or simulated
activation unless the separately governed geometry, Risk, and lifecycle inputs
required by that mechanism are valid.

`LIVE` remains Sponsor-selected manual participation outside KRONOS broker
execution. Existing attestation and factual position requirements remain. A
LIVE observation decision alone is not evidence of an order, fill, quantity,
or actual position.

`IGNORE` means the Sponsor explicitly elects not to participate. It does not
cancel or rewrite the KR-370 analytical thesis and creates no Sponsor Position.
It must be retained as seriously as LIVE and PAPER.

### 9. Objective model and Sponsor position remain separate

KR-380 V2 continues to publish only `NO_TRIGGER`, `FORMING`,
`LONG_ENTRY_TRIGGERED`, `SHORT_ENTRY_TRIGGERED`, `EXTENDED`, and `FAILED` under
its current objective entry-timing authority. Sponsor choice cannot manufacture
one of those states.

KR-390 continues to activate only from a valid current Risk-permitted KR-380 V2
trigger. Objective truth proceeds independently of Sponsor `LIVE`, `PAPER`,
`IGNORE`, or no decision wherever the objective path has every mandatory valid
input. Sponsor Position history remains separate.

### 10. Immutable decision-time snapshot

Before or atomically with Sponsor decision capture, future implementation must
preserve an immutable snapshot binding at minimum:

- run and canonical instrument;
- Native assessment and V3/V3.1 evidence identity;
- KR-370 state, K1-K5 facts, and hard-gate state;
- Step-31 policy, factual mathematics, availability, and warnings;
- DOMAIN-007 policy, state, facts, constraints, and availability;
- execution-context identity and status;
- applicable MCX supporting-context identity;
- decision timestamp and Sponsor choice; and
- policy/version identities, provenance, and integrity.

Later evidence must never rewrite what the Sponsor saw or selected.

### 11. Optional Sponsor reason

SPONSOR-OBS-01 may define an optional bounded Sponsor-reason field. It must not
be mandatory and must not use unrestricted free text as decision authority.
Potential categories require implementation-contract approval; this ADR does
not freeze their enum.

### 12. Complete observation population

The observation dataset must include LIVE, PAPER, and IGNORE decisions. It must
not retain only accepted or activated trades. For every eligible exact
promotion, future implementation must preserve the decision-time evidence and
subsequent objective evidence wherever governably observable.

IGNORE creates no Sponsor Position. Missing Sponsor-position evidence does not
block objective observation and must remain explicit.

### 13. Outcome and research ledger

Current Step 33 integrates a closed objective model and optional Sponsor
position. It cannot, by itself, guarantee a record for every ignored or
non-activated promotion. JOURNAL-OBS-01 must therefore either extend Step 33
under a new version or publish an explicitly governed linked research ledger
that can join:

```text
KR-370 recommendation
  -> Step-31 facts and warnings
  -> DOMAIN-007 facts and permission
  -> Sponsor LIVE / PAPER / IGNORE
  -> objective KR-380 / KR-390 history where available
  -> Sponsor-position history where separately available
  -> objective and actual outcomes with explicit availability
```

The ledger cannot rewrite source records, fabricate outcomes, or feed research
conclusions automatically into Production authority.

### 14. Historical compatibility

This decision applies prospectively only under
`SWING-STEP31-OBSERVATION-PHASE-V1` and future compatible contract versions.
Historical Step-31 records, unavailable outcomes, Risk results, Sponsor
decisions, KR-380 V1/V2 records, objective models, positions, closures, and
journals retain their original meaning and are never rewritten.

### 15. Future work-order authorization

This ADR authorizes architecture-bounded implementation planning for:

- **STEP31-OBS-01 — Advisory Trade Construction:** preserve and present factual
  mathematics, individual availability, and warnings without geometry quality
  alone deciding Sponsor participation.
- **SPONSOR-OBS-01 — LIVE / PAPER / IGNORE Evidence Capture:** capture explicit
  Sponsor choice and the immutable decision-time snapshot while preserving all
  activation hard blockers.
- **JOURNAL-OBS-01 — Outcome & Research Ledger:** retain all three Sponsor
  populations and join subsequent objective/Sponsor evidence without
  fabrication.
- **STEP31-RESEARCH-01 — Empirical Performance Review:** future only, after
  sufficient evidence and a separate explicit work order.

The first three are authorized for later bounded work orders, not implemented
by this ADR. STEP31-RESEARCH-01 is not authorized to begin now.

## Rationale

The separation preserves analytical, mathematical, Risk, human-decision,
objective-timing, position, and broker authorities while creating an unbiased
evidence base. It allows future empirical review of Step-31 warnings without
concealing poor mathematics or prematurely granting Step-31 Sponsor-decision
authority.

## Alternatives considered

- **Retain geometry as an automatic Sponsor veto:** rejected for Observation
  Phase V1 because it prevents collection of Sponsor override and ignored-case
  evidence.
- **Make DOMAIN-007 advisory:** rejected. Risk remains authoritative for every
  objective or Sponsor-position boundary that requires permission.
- **Manufacture favourable Entry/Stop/Target/R:R:** rejected as evidence
  corruption.
- **Automatically choose PAPER:** rejected because Sponsor choice must be
  explicit.
- **Collect only LIVE/PAPER outcomes:** rejected because it creates selection
  bias and loses ignored-opportunity evidence.

## Consequences

- Current runtime remains unchanged until separately authorized work orders.
- Step-31, Sponsor Decision, Trade Window, Browser, and evidence persistence
  require prospective versioned implementation changes.
- KR-370, DOMAIN-007, ECPC, KR-380, KR-390, objective/Sponsor separation, and
  broker prohibitions remain authoritative.
- Step-31 warnings become researchable decision-time evidence.
- Three to four months is an intended evidence horizon, not a timer or change
  trigger.

## Risks

- Sponsor-facing language could confuse a warning with permission unless the
  future UI distinguishes advisory facts from hard blockers.
- Recording Sponsor intent when activation is blocked could be mistaken for a
  position unless decision and activation records remain separate.
- Incomplete objective evidence could bias research unless availability is
  explicit.
- Individual outcomes could encourage premature tuning; methodology changes
  remain governed separately.

## Affected products and interfaces

- KRONOS Swing V1;
- Step-31 Trade Construction;
- DOMAIN-007 Risk Permission;
- Sponsor Decision and Sponsor Position;
- KR-380 / KR-390 objective lifecycle;
- Trade Window and Browser presentation;
- Step 33 / linked research ledger; and
- UX-10 notification consumption without authority change.

## Implementation implications

Later work must version the affected contracts rather than reinterpret current
records. At minimum it must provide an observation-phase Step-31 evidence
record, an observation-phase Sponsor Decision binding, immutable decision-time
snapshot persistence, Browser warning/hard-blocker distinction, and complete
LIVE/PAPER/IGNORE research lineage.

No Python, Browser, Provider, Pine, Telegram, Risk-policy, or broker runtime is
changed by this ADR.

## Validation requirements

- ADR and index links resolve.
- Current KR-370 and KR-380 state-family contracts remain unchanged.
- DOMAIN-007 `REJECTED`/`UNAVAILABLE` and integrity failures remain hard at
  governed activation boundaries.
- Geometry warnings are not represented as Sponsor decisions.
- All three Sponsor choices are included without fabricating positions.
- Historical records remain immutable.
- Broker and autonomous-trading authority remain none.

## Supersedes

ADR-0015 prospectively supersedes only:

- the ADR-0012 UX-06 implication that Sponsor-decision controls require an
  already ready Step-31 Trade Plan when geometry quality is the sole blocker;
- the S32-003/S32-007/S32-008 implication that a geometry warning alone must
  suppress recording Sponsor observation-phase choice; and
- current presentation implications that `GEOMETRY_INVALID` itself equals a
  Sponsor participation veto.

It does not supersede the hard binding, Risk, objective timing, position,
lifecycle, or broker authority of those records.

## Superseded by

None.

## Related ADRs and documents

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0012](ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md)
- [ADR-0013](ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md)
- [ADR-0014](ADR-0014-DOMAIN-001-CANONICAL-INSTRUMENT-V2-SEMANTIC-LAYERING-PROVIDER-CLASSIFICATION-AND-ACTIVE-DERIVATIVE-BINDING.md)
- [KR-370 / KR-380 state-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [Step-32 versioned contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md)
- [DOMAIN-007 architecture](../platform/domains/risk/ARCHITECTURE.md)
- [DOMAIN-007 contracts](../platform/domains/risk/CONTRACTS.md)
- [ECPC-001](../interfaces/ECPC-001-Execution-Context-Payload-Contract.md)
- [Step-32 product ADRs](../products/swing/SWING-V1-STEP-32-PRODUCT-ADRS.md)
- [Step-33 architecture](../products/swing/SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md)
- [Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Data Flow](../DATA_FLOW.md)

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-24 | 1.0 | Codex Engineering Support | Published the Chief Architect-authorized observation-phase authority closure | APPROVED |
