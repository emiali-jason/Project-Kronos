# ADR-0024 — Swing Step-31 Forward Target Eligibility Governance

## Metadata

- **ADR Number:** ADR-0024
- **Decision Identity:** SWING-STEP31-POLICY-02
- **Policy Identity:** SWING-V1-TRADE-CONSTRUCTION-V1
- **Policy Version:** 1.0
- **Title:** Swing Step-31 Forward Target Eligibility Governance
- **Status:** APPROVED
- **Date:** 2026-09-01
- **Decision Owner:** EA-SWING / Sponsor
- **Proposed By:** WO-SWING-STEP31-RESEARCH-01
- **Reviewers:** EA-SWING / Sponsor
- **Approved By:** EA-SWING / Sponsor
- **Decision Scope:** Swing Product / Step-31 Trade Construction / Evidence
- **Authority Level:** Swing Product Architecture
- **Repository Approval:** Approved decision; publication pending
- **Engineering Status:** Not started; WO-SWING-STEP31-ENG-03 requires separate authorization
- **Runtime Authority:** NONE
- **Broker Authority:** NONE

## Context

`SWING-V1-TRADE-CONSTRUCTION-V0` selects the existing setup-native target
candidate before it evaluates resulting reward geometry. For
`PULLBACK_CONTINUATION`, that candidate is the prior directional swing high for
LONG and the prior directional swing low for SHORT. A historically valid pivot
can therefore remain named as the canonical target even after price structure
has traversed it and the immutable Step-31 Entry lies beyond it.

The conventional Trade Plan already fails closed when risk or reward is not
positive. The policy weakness is the earlier canonical meaning: the Step-31
Observation layer can preserve a target above Entry for SHORT or below Entry
for LONG, calculate negative reward, and present the result as adverse geometry.
That historical evidence is truthful under V0, but the selected level does not
represent a positive forward objective.

[ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
requires Step-31 to preserve safely calculable facts and warnings without
substituting for Sponsor judgment. [ADR-0016](ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md)
preserves historical adverse Step-31 hypotheses for research. This decision is
compatible with both: it preserves rejected structural evidence, denies that
evidence future canonical-target authority, and rewrites no historical record.

## Research evidence

WO-SWING-STEP31-RESEARCH-01 inspected the current implementation and retained
governed evidence. Its bounded population contained:

- 95 KR-370 promotion records across 11 runs;
- 25 genuine `BUY/SELL READY/NOW` records;
- 18 unique direction/Entry/target geometries;
- 8 LONG and 17 SHORT records;
- 3 persisted Step-31 observations representing 2 unique geometries;
- no genuine consolidation-breakout Step-31 case; and
- no genuine material-barrier-modified Step-31 case.

Under the current latest-4H-pivot candidate rule, only 4 of 25 targets were
strictly forward and 21 of 25 were backward or non-forward. The 18 unique
geometries contained 3 forward and 15 non-forward geometries.

The symmetric genuine examples were:

| Subject | Direction | Entry | Historical target candidate | Reward | Historical V0 result |
| --- | --- | ---: | ---: | ---: | --- |
| VBL | SHORT | 408.75 | 432.25 | -23.50 | RED / invalid R:R |
| MCX NSE equity | LONG | 3211.40 | 3023.70 | -187.70 | RED / complete warning |

Offline candidate-set comparison found:

| Candidate authority searched | Forward target available |
| --- | ---: |
| Existing 4H candidate | 4 / 25 |
| 4H plus Daily | 7 / 25 |
| 4H plus Daily plus Weekly | 19 / 25 |

Availability improvement alone does not establish correct target authority.
Searching outward only after the setup-native candidate fails creates target-
shopping and ungoverned horizon-expansion risk.

## Decision

### 1. Canonical target meaning

A canonical Swing Step-31 Target must represent positive forward reward
relative to the immutable Step-31 Entry reference.

After authoritative rounding:

```text
LONG  -> canonical_target > entry
SHORT -> canonical_target < entry
```

Equality is ineligible. This is a universal target-eligibility invariant. It is
not a minimum-R:R threshold, Sponsor preference, discretionary heuristic,
target optimiser, or execution instruction.

### 2. Entry comparison authority

Eligibility is evaluated only against the immutable Step-31 Entry reference
bound to the construction. It is not evaluated against current LTP, a later
WebSocket price, Sponsor-observed price, future candle close, or other moving
price state.

Using a moving comparison reference would change target meaning after
construction and break evidence identity, restart determinism, and historical
replay.

### 3. Mandatory ordering

The governed order is:

1. construct Entry under the existing Entry policy;
2. apply authoritative Entry tick rounding;
3. construct the setup-native raw target candidate;
4. apply authoritative directional target tick rounding;
5. evaluate strict forward eligibility against the rounded Entry; and
6. grant canonical-target authority only when the rounded candidate passes.

Eligibility must not be evaluated on unrounded values if the published rounded
values would violate the invariant.

### 4. Rejected structural candidate

A structurally valid historical candidate that fails forward eligibility is
preserved as **REJECTED HISTORICAL TARGET CANDIDATE** evidence. Its retained
evidence must preserve, where supplied by the governed source:

- structural identity;
- price;
- timeframe;
- observation boundary;
- source;
- integrity hash and provenance; and
- forward-eligibility rejection reason.

It is historical structural context only. It is not a canonical target, profit
target, or forward objective.

The future versioned Step-31 evidence contract must distinguish this rejected
candidate evidence from canonical-target availability. Exact implementation
field and enum names belong to WO-SWING-STEP31-ENG-03; this ADR does not modify
an interface contract or production schema.

### 5. No fallback

Version 1 introduces no replacement search. If the setup-native candidate
fails forward eligibility, Step-31 must not automatically search another 4H,
Daily, Weekly, or 1H pivot; PDH/PDL; CPR or Classic Pivot level; measured move;
farther objective; next structural high/low; or material barrier.

The governed result is:

```text
rejected historical target candidate -> PRESERVED AS CONTEXT
canonical_target                     -> UNAVAILABLE
reward                               -> UNAVAILABLE
R:R                                  -> UNAVAILABLE
conventional Trade Plan              -> TRADE_PLAN_UNAVAILABLE
reason                               -> TARGET_NOT_FORWARD_OF_ENTRY equivalent
```

The exact future reason-code spelling is implementation-owned. It must remain
distinct from missing target evidence.

### 6. Pullback continuation

The existing setup-native candidate family remains unchanged:

```text
LONG  -> prior directional swing high
SHORT -> prior directional swing low
```

The candidate receives canonical-target authority only after passing the
forward invariant. No alternate pullback target family is introduced.

### 7. Consolidation breakout

The existing setup-native range projection remains conceptually unchanged.
Its rounded projected target must also pass the forward invariant before it can
be canonical. No breakout replacement hierarchy is established because the
retained genuine Step-31 breakout sample is zero.

### 8. Material barriers

A material barrier is evaluated only after a setup-native target has passed
forward eligibility:

```text
setup-native target
  -> forward eligibility
  -> eligible canonical path
  -> material-barrier assessment
  -> constrained canonical target, when applicable
  -> reward and R:R
```

A barrier is not a fallback for an invalid setup-native target. A constraining
barrier must itself remain strictly forward of Entry:

```text
LONG  -> barrier > entry
SHORT -> barrier < entry
```

A barrier equal to or behind Entry is ineligible. If directional rounding
eliminates positive reward, construction fails closed. Where multiple barriers
are eligible, the existing nearest-forward-barrier principle remains unchanged.
No broader barrier-selection authority is created.

### 9. R:R and Stop governance

R:R is a consequence of completed valid geometry. It does not select or replace
a target, expand timeframe, choose a farther pivot, tighten Stop, or change
Entry. No minimum R:R threshold is introduced. `1:1`, `1.5:1`, `2:1`, and every
other minimum remain `POLICY_UNRESOLVED`.

Stop construction remains governed by thesis invalidation. Stop must not be
tightened because reward is small or unavailable.

### 10. Observation-layer successor semantics

Future V1 observation evidence may retain a rejected target candidate for
research while reporting canonical Target, reward, and R:R as unavailable.
The structural state is:

```text
TARGET_UNAVAILABLE_DUE_TO_FORWARD_ELIGIBILITY
```

The final GREEN/AMBER/RED presentation for this state is not decided here:

```text
SEVERITY_FOR_FORWARD_REJECTED_TARGET = POLICY_UNRESOLVED
```

This does not change ADR-0015 Sponsor judgment or ADR-0016 Paper Observation
Track authority. Any downstream mechanism requiring a valid canonical Target
remains blocked. Research evidence may remain visible without manufacturing a
replacement target or position authority.

### 11. Partial staleness decision

A candidate at or behind Entry is ineligible and already-traversed historical
context. No age in days, candle count, regime-age threshold, pivot-age
threshold, structural-expiry timer, or general supersession rule is introduced.

### 12. Timeframe hierarchy deferred

This decision does not establish 4H-to-Daily, Daily-to-4H, Weekly, 1H, or any
other replacement hierarchy. Higher availability in offline replay is not
authority to search a wider horizon.

### 13. Entry architecture deferred

The current composer identifies the latest completed 4H bucket as
`QualificationCandleEvidence`. Whether Entry should instead bind to an
independently persisted qualification event remains
`ENTRY_ARCHITECTURE_RESEARCH_NOTE` and is outside this decision.

## VBL and MCX governed future interpretation

Under V1, VBL SHORT candidate 432.25 fails `432.25 < 408.75`. MCX NSE equity
LONG candidate 3023.70 fails `3023.70 > 3211.40`. Each candidate remains
historical structural context. Each future construction would publish no
canonical target, reward, R:R, or conventional Trade Plan, and would search no
replacement.

The existing persisted V0 VBL and MCX observations remain exactly as recorded.

## Policy versioning and effective boundary

`SWING-V1-TRADE-CONSTRUCTION-V1` is the successor target-eligibility policy to
`SWING-V1-TRADE-CONSTRUCTION-V0`. This documentation decision does not activate
V1 runtime behavior.

V1 becomes effective only for a new Step-31 construction after all of the
following occur:

1. WO-SWING-STEP31-ENG-03 is separately authorized and completed;
2. its versioned contract and persistence changes are approved;
3. its exact implementation is published; and
4. the governed runtime loads that published implementation.

Every earlier record retains its creating policy identity and meaning. Restart
and replay must route a persisted record through the policy/version that
created it. V0 records are restored as V0; they are not silently evaluated as
V1. A separately governed offline research replay may compare policies but may
not overwrite production evidence or current pointers.

## Historical compatibility

All historical Step-31 observations, Trade Plans, Risk records, Sponsor
decisions, Paper Observation Tracks, objective models, positions, closures,
journals, and research-ledger relationships remain immutable.

In particular, historical VBL remains recorded as `SELL NOW`, Step-31 RED,
Entry 408.75, Stop 447.90, Target 432.25, reward -23.50, and invalid R:R. The
historical MCX NSE equity observation likewise retains its V0 adverse geometry.

This ADR does not reinterpret ADR-0015 or ADR-0016 evidence as if V1 had existed
when those records were constructed.

## Authority boundaries

| Owner | Preserved authority | Not granted by ADR-0024 |
| --- | --- | --- |
| Native Discovery / Review | Existing thesis and evidence | Target replacement or geometry |
| KR-370 | Existing analytical promotion | Entry, Target, Risk, Sponsor choice |
| Step-31 | Entry/Stop/Target/invalidation/R:R geometry and availability | Risk, timing, execution, broker action |
| DOMAIN-007 | Existing Risk permission | Geometry modification |
| Sponsor | Existing explicit participation judgment | Machine target construction |
| KR-380 / KR-390 | Existing timing and objective lifecycle | Target repair or reinterpretation |
| Paper Observation Track | Existing non-position research evidence | Canonical-target replacement |
| Browser | Future presentation only after separate engineering authority | Policy, severity, or target selection |
| Intraday | No change | No reuse, migration, or implementation authority |
| Broker | None | All order and execution activity |

This decision changes no KR-370 criterion or state, Entry formula, Stop formula,
Risk rule, Sponsor authority, monitoring rule, lifecycle meaning, Pine content,
Provider behavior, Browser behavior, Intraday policy, or broker authority.

## Unresolved policy and September evidence plan

The following remain explicitly unresolved:

- replacement target hierarchy;
- Daily versus 4H ownership;
- Weekly target authority;
- genuine consolidation-breakout behavior;
- genuine barrier-modified behavior;
- general target expiry;
- structural supersession;
- 1H final-target authority;
- independent qualification-event Entry identity;
- minimum R:R; and
- presentation severity for a forward-rejected candidate.

September observation should continue to retain genuine cases across LONG and
SHORT, both setup families, READY-to-NOW progression, forward and rejected
targets, unavailable targets, and barrier-modified paths. Evidence collection
must not tune production policy, backfill synthetic cases, or broaden target
authority automatically.

## Rationale

Strict positive forward reward is deterministic, symmetric, stable across
restart, and directly supported by genuine LONG and SHORT evidence. Preserving
the rejected candidate retains factual research value. Refusing fallback avoids
target shopping while the replacement hierarchy lacks sufficient evidence.

## Alternatives considered

- **Keep adverse historical pivots as canonical targets:** rejected because a
  canonical target at or behind Entry cannot express positive forward reward.
- **Use current LTP as the eligibility reference:** rejected because target
  meaning would move after construction.
- **Search broader timeframes automatically:** rejected because availability
  improvement does not prove authority and introduces target shopping.
- **Choose a farther target to improve R:R:** rejected because R:R is a
  consequence, not a selector.
- **Delete the rejected pivot:** rejected because it would destroy governed
  historical context.

## Consequences

- Future invalid setup-native candidates cannot be published as canonical
  targets under V1.
- Some future Step-31 constructions will have no target and no conventional
  Trade Plan.
- The observation contract and persistence will require a versioned successor
  capable of retaining rejected-candidate evidence separately.
- Historical V0 evidence remains readable and semantically exact.
- No runtime behavior changes until a separately authorized implementation.

## Risks

- Target availability may remain low while fallback is prohibited.
- Presentation may confuse rejected context with a target unless the future
  contract and Browser distinguish them explicitly.
- Mixed V0/V1 restoration could reinterpret evidence unless policy identity is
  mandatory and fail closed.
- Pressure to improve availability could reintroduce target shopping before
  September evidence is sufficient.

## Affected products and interfaces

- KRONOS Swing V1;
- Step-31 Trade Construction and Observation Evidence;
- future Trade Window presentation;
- downstream consumers that require an available canonical Target; and
- historical restoration/replay routing.

Current interface contracts are not modified by this documentation work order.
WO-SWING-STEP31-ENG-03 must propose exact versioned contract changes before any
producer or consumer changes.

## Implementation implications

WO-SWING-STEP31-ENG-03 must be separately authorized. It must be bounded to the
future policy/version, strict post-rounding gate, rejected-candidate evidence,
no-fallback result, persistence/restoration compatibility, observation
semantics, and applicable presentation. It must not alter historical V0
records, KR-370, Risk, Entry, Stop, Sponsor authority, monitoring, Intraday, or
broker behavior.

## Validation requirements

- LONG rounded target must be strictly above rounded Entry.
- SHORT rounded target must be strictly below rounded Entry.
- Equality and backward candidates must be rejected before canonical authority.
- Rejected candidate evidence must remain immutable and identifiable.
- No fallback search may occur.
- Material barriers may run only after setup-native forward eligibility.
- Reward and R:R must remain unavailable without a canonical target.
- No minimum R:R or timeframe hierarchy may be introduced.
- V0 and V1 persistence/restart must remain unambiguous.
- Architecture and index links must resolve.
- Production code and Intraday must remain unchanged by this ADR.

## Validation evidence

- WO-SWING-STEP31-RESEARCH-01 retained-evidence audit and offline replay,
  completed 2026-09-01.
- Repository implementation and governed evidence inspected at commit
  `5a9528ab8e4892217f8721cc7496ffdc98467640`.
- Documentation and index validation recorded in the
  WO-SWING-STEP31-POLICY-02 return.

## Supersedes

- `SWING-V1-TRADE-CONSTRUCTION-V0` target-eligibility semantics prospectively,
  only after the V1 effective boundary.
- No approved ADR is superseded.

## Superseded by

None.

## Related ADRs and documents

- [ADR-0011 — KR-370 Analytical Promotion and KR-380 Entry Outcome Semantics](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0012 — Remaining Swing UX/OPS Scope and Disposition](ADR-0012-SWING-UX-GOV-01-REMAINING-SWING-UX-OPS-SCOPE-AND-DISPOSITION.md)
- [ADR-0015 — Swing Sponsor Observation-Phase Authority and Step-31 Evidence Governance](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
- [ADR-0016 — Swing Paper Observation Track Authority](ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md)
- [KR-370 / KR-380 state-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [Swing V1 Step-32 versioned contracts](../interfaces/SWING-V1-STEP-32-VERSIONED-CONTRACTS.md)
- [Swing Phase 1 Analytical Core](../../engineering/SWING-PHASE-1-ANALYTICAL-CORE.md)

## Revision history

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-09-01 | 1.0 | Codex Engineering Support | Recorded EA-SWING/Sponsor forward-target eligibility governance | APPROVED; publication pending |
