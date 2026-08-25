# ADR-0016 — Swing Paper Observation Track Authority

## Metadata

- **ADR Number:** ADR-0016
- **Decision Identity:** PAPER-OBS-GOV-01
- **Title:** Swing Paper Observation Track Authority
- **Status:** APPROVED
- **Date:** 2026-08-25
- **Decision Owner / Approved By:** Chief Architect
- **Product:** KRONOS Swing V1
- **Scope:** Swing Product / Observation Research / Interface / Presentation
- **Authority Level:** Chief Architect
- **Engineering Status:** Architecture and contracts approved; PAPER-OBS-01,
  PAPER-OBS-LEDGER-01, and JOURNAL-UX-01 not started
- **Runtime Authority:** NONE until a separately executed work order closes
- **Broker Authority:** NONE
- **Autonomous Trading:** NOT AUTHORIZED

## Context

[ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
separates Sponsor judgment from governed position activation. A Sponsor may
record `PAPER` against trustworthy GREEN, AMBER, or RED Step-31 evidence while
DOMAIN-007 correctly blocks the Sponsor Position because Risk is `REJECTED`,
`UNAVAILABLE`, or otherwise blocking. Current Version 1 contracts then prohibit
monitoring for that blocked decision.

Blocked PAPER choices are not random. Retaining the decision but systematically
omitting the subsequent market path creates outcome censoring in the intended
three-to-four-month observation programme. This ADR closes that evidence gap
without weakening Risk or creating a position, model, fill, P&L, actual R, or
broker authority.

## Decision

### 1. Operating principle

```text
KR-370 RECOMMENDS.
STEP-31 CALCULATES AND WARNS.
SPONSOR DECIDES.
DOMAIN-007 CONTROLS GOVERNED POSITION ACTIVATION.
PAPER OBSERVATION TRACK OBSERVES MARKET PATH ONLY.
KRONOS RECORDS THE EVIDENCE.
```

### 2. Three truth families

The following are separately identified, persisted, restored, and presented:

| Truth family | Meaning | Authority |
| --- | --- | --- |
| PAPER Observation Decision | Sponsor judgment: “I would take this as PAPER” | Judgment evidence only |
| Paper Observation Track | Non-position observation of the exact decision-time Step-31 hypothesis | Research evidence only |
| PAPER Sponsor Position | Existing governed PAPER position created only when current activation authority permits it | Sponsor-position lifecycle only |

No record in one family implies a record in another.

### 3. DOMAIN-007 remains unchanged

DOMAIN-007 remains the hard permission gate for Sponsor Position activation,
objective timing where already governed, and every other existing Risk-gated
boundary. A Paper Observation Track receives no Risk approval, override, or
bypass. It preserves the exact decision-time Risk identity, state, constraints,
reasons, and availability as research evidence.

The intentional prospective state is:

```text
Sponsor Decision       PAPER · RECORDED
Risk                   REJECTED / UNAVAILABLE / otherwise blocking
Position Activation    BLOCKED
Sponsor Position       NONE
Paper Observation Track AVAILABLE / ACTIVE when track trust gates pass
```

### 4. Eligibility and explicit start

A track may originate only from one exact, valid, prospectively governed
Sponsor Observation Decision whose choice is `PAPER`. Creation binds the exact
decision, immutable decision snapshot, run, instrument, assessment, Step-31
Observation Evidence, activation disposition, and integrity digests.

Track creation requires an explicit Sponsor action, presented as `START PAPER
OBSERVATION`. Recording PAPER does not start a track automatically. Start is
idempotent for the same exact lineage and fails closed for a foreign, stale-at-
creation, superseded-at-creation, malformed, corrupt, integrity-mismatched, or
unsupported record.

### 5. Blocked and activated PAPER relationship

The Paper Observation Track V1 is available only when the exact PAPER decision
has a blocked Sponsor Position activation disposition and no Sponsor Position
exists. When a governed PAPER Sponsor Position activates, its existing factual
lifecycle is the primary PAPER outcome relationship and a separate Paper
Observation Track is `NOT_APPLICABLE_POSITION_ACTIVATED`.

One Sponsor PAPER decision remains one primary research-ledger row. Track,
objective-model, and Sponsor-position evidence are relationships on that row;
none becomes a second decision population. This prevents double counting.

### 6. Geometry and severity

GREEN, AMBER, and RED Step-31 Observation Evidence are eligible when their
trust bindings pass. Step-31 Entry is retained as `OBSERVATION_ENTRY_REFERENCE`.
The exact Stop, Target, invalidation, availability, mathematical values,
warnings, severity, reward, risk, and R:R state are retained without repair.
V1 authorizes no arbitrary Sponsor replacement geometry.

The governed adverse example remains exact:

```text
KR-370                     BUY NOW
Sponsor                    PAPER
Entry                      3211.4
Stop                       2892.1
Target                     3023.7
Risk                       319.3
Reward                     -187.7
R:R                        INVALID
Step-31 severity           RED
DOMAIN-007                 UNAVAILABLE
Position activation        BLOCKED
Paper Observation Track    AUTHORIZED
```

No favourable target or valid R:R is manufactured.

### 7. Track and outcome state families

The contract `KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1`, Version 1, owns the
following track states:

- `AVAILABLE`;
- `ACTIVE`;
- `MONITORING_INTERRUPTED`;
- `COMPLETE`;
- `OUTCOME_NOT_ESTABLISHED`; and
- `NOT_APPLICABLE_POSITION_ACTIVATED`.

Its bounded outcome family is:

- `ENTRY_NOT_OBSERVED`;
- `ENTRY_OBSERVED`;
- `STOP_LEVEL_TOUCHED`;
- `TARGET_LEVEL_TOUCHED`;
- `BOTH_ORDERING_UNRESOLVED`;
- `EXPIRED`; and
- `OUTCOME_NOT_ESTABLISHED`.

`EXPIRED` is reserved in the contract but no V1 producer may emit it until a
later bounded expiry decision is approved. `OUTCOME_NOT_ESTABLISHED` preserves
open, interrupted, insufficient, or unreconciled evidence without guessing.

### 8. Event semantics and ordering

`ENTRY_OBSERVED` means governed factual observations established the exact
directional Step-31 observation-entry condition. It is never named or treated
as `FILLED`. Stop and Target states mean only that the exact retained level was
factually touched after Entry was governably observed. They do not mean win,
loss, execution, or favourable/unfavourable outcome.

Ordered accepted observations preserve factual sequence. Completed candles may
establish bounded level containment only after DOMAIN-008 determines them
complete. An unfinished candle establishes no final track outcome. If one
completed interval contains multiple relevant levels and ordering is not
independently established, the result is `BOTH_ORDERING_UNRESOLVED`.

### 9. Monitoring, gaps, and restart

`SharedSwingMonitoringHub` may be reused solely as authority-free factual
transport. Paper Track has its own consumer and owner identity. The Sponsor
Position lifecycle consumer and KR-380 consumer are not Paper Track authority.
A WebSocket subscription implies neither Position, Risk approval, objective
model, order, nor fill.

The track must detect disconnects, preserve `MONITORING_INTERRUPTED`, and use
bounded historical reconciliation after reconnect where governed facts permit.
Missing intervals or ambiguous reconstruction never manufacture ordering.
Restart restores immutable state and subscriptions idempotently; it never
manufactures an Entry, level touch, or outcome.

### 10. Expiry and supersession

`EXPIRY POLICY UNRESOLVED`. No automatic expiry threshold is authorized.
Open tracks may remain `ENTRY_NOT_OBSERVED` or `OUTCOME_NOT_ESTABLISHED`.

A later Native analysis run does not rewrite or terminate an existing Paper
Track. The original decision-time hypothesis continues to be observed because
the research purpose is prospective market-path evidence. Run supersession is
recorded as later context only. Trust or integrity failure in the track's own
lineage fails the track closed.

### 11. Objective, position, LIVE, and broker isolation

Paper Track cannot create or emulate a KR-380 state, KR-390 model, objective
lifecycle, `PAPER_ARMED`, `PAPER_ACTIVE`, LIVE position, Sponsor Position,
Sponsor Position closure, order, fill, execution query, or broker evidence.
Objective and Sponsor-position evidence remain independently linkable through
the Research Ledger when their own authority produces them.

LIVE authority is unchanged. ADR-0016 authorizes no LIVE Observation Track.
Broker authority remains `NONE`; autonomous trading remains prohibited.

### 12. P&L, actual R, and notifications

Paper Track monetary P&L and actual R are `UNAVAILABLE`. The track does not
calculate account economics or reuse Sponsor Position accounting. Any future
research metric requires STEP31-RESEARCH-01 authority.

No Telegram or other notification event is authorized by this ADR. Potential
track notifications require a later bounded runtime work order.

### 13. Research Ledger and Journal

`KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2`, Version 2, preserves the one
decision population and adds Paper Track and Paper Track outcome relationships.
It may also retain separately governed objective-model and Sponsor-position
relationships. It cannot calculate performance analytics or feed Production
authority.

The Sponsor projection contract
`KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2`, Version 2, may present:

```text
SPONSOR DECISION          PAPER
POSITION ACTIVATION       BLOCKED
PAPER OBSERVATION TRACK   ACTIVE
STEP-31                   RED
RISK AT DECISION          UNAVAILABLE
PAPER TRACK OUTCOME       <bounded state>
```

The Trade Window may expose `START PAPER OBSERVATION` separately from `PAPER
TRADE ENTRY` and `POSITION ACTIVATION`. JOURNAL-UX-01 may consume the final
track semantics only after PAPER-OBS-01 and PAPER-OBS-LEDGER-01 close.

### 14. Historical compatibility

This authority is prospective. Existing Sponsor Observation Decision V1,
Research Ledger V1, blocked PAPER decisions, positions, objective models,
lifecycles, journals, and outcomes retain their original meaning. No automatic
backfill or historical reinterpretation is permitted.

ADR-0016 prospectively supersedes only the V1 prohibition on monitoring a
blocked PAPER decision when—and only when—the monitoring is performed by the
separately identified Paper Observation Track V1. It does not change the
prohibition for Sponsor Position, KR-380, KR-390, LIVE, or any other consumer.

### 15. Authority matrix

| Owner | Owns | Does not own |
| --- | --- | --- |
| KR-370 | Analytical promotion | Track, Risk, Entry Outcome, position |
| Step-31 | Exact geometry, availability, warnings | Track outcome, Risk, fill |
| DOMAIN-007 | Existing Risk permission and activation gates | Paper Track research state |
| Sponsor Observation Decision | Explicit Sponsor judgment | Track start/outcome, position activation |
| Paper Observation Track | Non-position factual market-path state | Risk, position, objective model, execution |
| Sponsor Position | Governed LIVE/PAPER position lifecycle | Paper Track or objective truth |
| KR-380 | Objective entry timing | Paper Track Entry observation or fill |
| KR-390 | Objective model lifecycle | Paper Track or Sponsor Position truth |
| Research Ledger | Immutable joins and raw projection | Source outcomes, analytics, authority feedback |
| Broker | No KRONOS authority granted | All Paper Track activity |

### 16. Canonical data flow

```text
KR-370 BUY NOW / SELL NOW
  -> Step-31 Observation Evidence
  -> Sponsor chooses PAPER
  -> immutable PAPER decision
  -> DOMAIN-007 separately determines Sponsor Position activation

activation permitted
  -> existing PAPER Sponsor Position path
  -> Sponsor-position relationship on the one Research Ledger row

activation blocked + Sponsor explicitly starts track
  -> Paper Observation Track
  -> governed factual market observation
  -> bounded Paper Track outcome
  -> Paper Track relationship on the same Research Ledger row

independent valid objective path
  -> KR-380 / KR-390 evidence relationship on the same row

Research Ledger
  -> future STEP31-RESEARCH-01 only under a separate work order
```

## Consequences

- Blocked PAPER market paths can be observed without weakening Risk.
- One Sponsor decision remains one research population row.
- Adverse geometry remains visible and exact.
- Expiry remains unresolved without blocking open-track architecture.
- New contracts and runtime work are required prospectively.
- No current runtime behavior changes in this publication.

## Authorized future work orders

- **PAPER-OBS-01:** Paper Observation Track runtime, persistence, monitoring,
  reconciliation, restart, and bounded Browser control.
- **PAPER-OBS-LEDGER-01:** Research Ledger V2 integration and raw projection.
- **JOURNAL-UX-01:** May consume final Paper Track semantics only after both
  preceding work orders close.

STEP31-RESEARCH-01 remains future-only and is not authorized to begin.

## Validation requirements

- Paper Track is not Sponsor Position or objective model.
- Risk remains hard for Sponsor Position and objective activation.
- Blocked PAPER may have a track; activated PAPER cannot have a duplicate one.
- GREEN, AMBER, and RED trustworthy evidence remain eligible.
- LIVE is unchanged; broker authority is none.
- Monetary P&L and actual R are unavailable.
- Historical records are not reinterpreted.
- Runtime, Browser, WebSocket, Telegram, Provider, and Pine remain unchanged.

## Related documents

- [ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
- [ADR-0013](ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md)
- [Paper Observation Track V1](../interfaces/KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1.md)
- [Sponsor Observation Projection V2](../interfaces/KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2.md)
- [Observation Research Ledger V2](../interfaces/KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2.md)
- [DOMAIN-007](../platform/domains/risk/ARCHITECTURE.md)
- [Step-32 Product ADRs](../products/swing/SWING-V1-STEP-32-PRODUCT-ADRS.md)
- [Step-33](../products/swing/SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md)
- [Engine Ownership](../ENGINE_OWNERSHIP.md)
- [Data Flow](../DATA_FLOW.md)

## Supersedes

Prospectively and narrowly, the Sponsor Observation Decision V1 prohibition on
monitoring a blocked PAPER decision, only for a separately identified Paper
Observation Track V1. All original activation prohibitions remain.

## Superseded by

None.

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-25 | 1.0 | Codex Engineering Support | Published Chief Architect-authorized Paper Observation Track governance | APPROVED |
