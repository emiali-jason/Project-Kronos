
# Chief Architect Repository Architecture Review — Next Authorized Capability

**Project:** KRONOS
**Product:** KRONOS Swing
**Repository authority reviewed:** `develop`
**Current completed Engineering Architecture:** EAP-001 through EAP-004 Version 1.0
**Decision:** EAP-005 drafting may proceed

The repository confirms that EAP-004 is canonical Version 1.0 and ends before the ADP-001D Instrument-to-Observation attribution boundary. It produces approved Instrument meaning while explicitly excluding Observation attribution and Observation construction.

ADP-001D already defines the next governed semantic boundary: factual market information may become eligible for Observation participation only when it is attributable to an approved canonical Instrument identity and satisfies provenance, source, temporal, uncertainty, ambiguity and effective-context obligations. Eligibility does not create an Observation, confer Observation ownership or establish factual correctness.

The Document Register confirms EAP-001 through EAP-004 as approved canonical Engineering Architecture and contains no existing EAP-005 assignment.

# 1. Repository determination

## Sufficient canonical architecture

**Yes.**

The following architecture now forms a complete basis for the next engineering translation:

```text
EAP-004 Instrument Identity Contract
                  +
Source-neutral candidate factual information
                  ↓
ADP-001D Instrument-to-Observation
Governed Attribution Boundary
                  ↓
Observation Participation Eligibility
```

ADP-001D supplies:

* the attribution boundary;
* domain ownership;
* architectural admissibility;
* Observation eligibility;
* attribution requirements;
* failure preservation;
* provenance continuity;
* temporal attribution;
* uncertainty and ambiguity requirements;
* explicit prohibitions.

ADP-001E supplies the downstream Observation meaning and confirms that attributed factual information remains only eligible for Observation participation until Observation makes a separate acceptance decision.

## Next repository activity

> **EAP-005 — Instrument-to-Observation Attribution Eligibility Engineering Architecture**

A new ADP is not required before EAP-005.

# 2. Remaining architectural gaps

The repository still leaves certain matters unresolved:

* dataset-specific factual structures;
* factual-data acquisition;
* Provider-to-Observation runtime communication;
* mapping-effective-time mechanics;
* Instrument lifecycle transitions;
* exact runtime temporal representations;
* Observation Acceptance mechanisms;
* Observation construction and publication;
* persistence.

These do not block a provider-neutral, implementation-neutral translation of the existing ADP-001D attribution boundary.

EAP-005 must preserve unresolved conditions as unresolved or as attribution-ineligibility reasons. Engineering shall not invent their meaning.

# 3. Provider Mapping Architecture

**Not required before EAP-005.**

Provider Mapping Architecture becomes mandatory before Engineering defines:

* mapping establishment or selection;
* mapping conflict resolution;
* mapping-effective-time processing;
* reconciliation;
* Provider-token reuse processing;
* mapping persistence;
* historical mapping maintenance.

EAP-005 may consume only an already approved canonical Instrument Identity Contract. It shall not map a Provider reference to an Instrument identity.

# 4. Instrument Lifecycle Architecture

**Not required before EAP-005.**

Lifecycle Architecture becomes mandatory before Engineering defines:

* lifecycle transitions;
* authoritative transition facts;
* expiry processing;
* delisting or retirement processing;
* successor processing;
* rollover;
* continuous-futures handling.

EAP-005 may preserve applicable effective identity or lifecycle context where canonical architecture already supplies it. Where required context cannot be established, attribution shall remain ineligible.

# 5. EAP-005 Draft Authorization

## Official number

> **EAP-005**

## Official title

> **EAP-005 — Instrument-to-Observation Attribution Eligibility Engineering Architecture**

## Capability statement

EAP-005 shall translate ADP-001D into provider-neutral and implementation-neutral engineering contracts, representations and obligations through which:

* an EAP-004 Instrument Identity Contract;
* bounded candidate factual market information;
* source and provenance context;
* temporal context;
* uncertainty, ambiguity and factual limitations;

are evaluated to determine whether the factual information is:

* eligible for governed attribution and Observation participation; or
* ineligible for governed attribution and Observation participation.

EAP-005 shall terminate before:

* Candidate Observation construction;
* Observation Acceptance;
* Observation ownership;
* Observation publication.

## Purpose

EAP-005 shall preserve the distinction:

```text
Approved Canonical Instrument Identity
                  +
Candidate Factual Market Information
                  ↓
Attribution Evaluation
                  ↓
Attribution Eligible / Attribution Ineligible
                  ↓
Observation Participation Eligibility
                  ↓
EAP-005 terminates
```

The package shall prevent:

* identity from becoming factual state;
* factual state from creating identity;
* attribution eligibility from becoming factual correctness;
* eligibility from becoming Observation Acceptance;
* eligibility from conferring Observation ownership;
* attribution failure from being hidden;
* uncertainty or ambiguity from being silently resolved.

# 6. Governing and supporting architecture

## Primary governing ADP

> **ADP-001D — Instrument → Observation Contract**

ADP-001D defines the governed attribution boundary and requires approved identity, provenance continuity, source attribution, temporal attribution and preserved uncertainty and ambiguity.

## Supporting ADPs

* ADP-001A — Swing Phase 1 Market Data Inventory;
* ADP-001B — Instrument Identity Architecture;
* ADP-001C — Provider → Instrument Contract;
* ADP-001E — Observation Domain Architecture;
* ADP-001H — Provider Instrument Master Acquisition Capability;
* ADP-001I — Approved Instrument Universe and Reference Semantics;
* ADP-001J — Instrument Interpretation and Canonical Identity Establishment.

## Supporting Engineering Architecture

* EAP-001 Version 1.0;
* EAP-002 Version 1.0;
* EAP-003 Version 1.0;
* EAP-004 Version 1.0.

## Required repository dependencies

* Platform Constitution;
* Instrument Domain Architecture;
* Observation Domain Architecture;
* Provider Domain Architecture;
* Domain Ownership Matrix;
* `DOMAIN_DEPENDENCY_MATRIX.md`;
* ENGINE_OWNERSHIP;
* DATA_FLOW;
* Document Register;
* approved architecture and engineering indexes.

# 7. Semantic and domain ownership

| Meaning                               | Semantic owner                                              |
| ------------------------------------- | ----------------------------------------------------------- |
| Canonical Instrument Identity         | Instrument                                                  |
| Instrument Identity Contract          | Instrument                                                  |
| Candidate factual information         | Retains its source-owned meaning; not yet Observation-owned |
| Factual source provenance             | Retains its approved source ownership                       |
| Attribution Authority                 | Observation                                                 |
| Attribution Evaluation                | Observation                                                 |
| Attribution Outcome                   | Observation                                                 |
| Observation Participation Eligibility | Observation                                                 |
| Observation Acceptance                | Observation, outside EAP-005                                |
| Governed Observation                  | Observation, outside EAP-005                                |

ADP-001D assigns Instrument ownership of identity and Observation ownership of factual attribution and Market Facts. The boundary itself shall not become a third owner.

# 8. Engineering boundary

```text
EAP-004 Instrument Identity Contract
                  │
                  ├──────────────┐
                  │              │
                  │      Candidate Factual
                  │      Information Contract
                  │              │
                  └──────┬───────┘
                         ↓
          Attribution Evaluation Readiness
                         ↓
              Attribution Evaluation
                         ↓
                 Attribution Outcome
              ┌──────────┴──────────┐
              ↓                     ↓
   Attribution Eligible    Attribution Ineligible
              ↓                     ↓
 Observation Participation   No Observation
 Eligibility Contract        Participation Contract
              ↓
       EAP-005 terminates
```

This is a semantic engineering boundary, not a runtime sequence.

# 9. Upstream boundaries

## Identity input

Immediate canonical identity dependency:

> **EAP-004 Version 1.0 — Instrument Identity Contract**

EAP-005 may consume:

* canonical Instrument identity meaning;
* identity layer;
* approved classification and relationships;
* approved universe context;
* applicable historical or effective context;
* approved provenance association.

EAP-005 shall not recreate or reinterpret Instrument identity.

## Candidate factual input

EAP-005 may define a source-neutral:

> **Candidate Factual Information Input Contract**

It may carry conceptual factual meaning for evaluation, including:

* candidate factual assertion;
* factual category;
* source attribution;
* provenance;
* temporal context;
* partiality;
* failed-information distinction;
* unavailable-information distinction;
* uncertainty;
* ambiguity;
* limitations.

This contract grants no acquisition or runtime communication authority.

# 10. Downstream boundary

The downstream output is:

> **Observation Participation Eligibility Contract**

It represents only that candidate factual information:

* is attributable to an approved canonical Instrument identity;
* satisfies the governed ADP-001D attribution preconditions;
* may participate in later Observation architecture.

It shall not establish:

* Candidate Observation construction;
* Observation Acceptance;
* Observation ownership;
* factual correctness;
* Market Fact authority;
* publication;
* Validation;
* fitness for use.

A later separately authorized EAP may translate Observation Acceptance under ADP-001E.

# 11. Engineering scope

EAP-005 may define engineering architecture for:

* Attribution Evaluation Readiness;
* Attribution Evaluation Activity;
* Attribution Outcome;
* Attribution Eligible;
* Attribution Ineligible;
* attribution-ineligibility reasons;
* approved canonical identity association;
* candidate factual information association;
* source attribution;
* temporal attribution;
* provenance continuity;
* attribution continuity;
* partiality distinction;
* failed-information distinction;
* unavailable-information distinction;
* identity-metadata distinction;
* derived-interpretation distinction;
* retained uncertainty;
* unresolved ambiguity;
* effective identity-context preservation;
* Observation Participation Eligibility;
* Observation Participation Ineligibility;
* boundary conformance;
* boundary violations;
* non-sensitive observability;
* engineering verification.

# 12. Explicit out of scope

EAP-005 shall not define or authorize:

* factual-data acquisition;
* Provider communication;
* Provider-to-Observation runtime communication;
* APIs;
* schemas;
* fields;
* payloads;
* serialization;
* transport;
* market-data structures;
* quote models;
* candle or OHLC models;
* depth models;
* Open Interest structures;
* timestamp formats;
* matching or attribution algorithms;
* identity resolution;
* mapping establishment;
* mapping-effective-time processing;
* lifecycle transitions;
* factual correction;
* enrichment;
* normalization;
* Candidate Observation construction;
* Observation Acceptance;
* Observation ownership;
* Observation publication;
* Observation lifecycle;
* Market Schedule;
* Validation;
* Risk;
* Execution;
* Portfolio;
* Event or Audit meaning;
* persistence;
* caching;
* scheduling;
* retries;
* runtime orchestration;
* EDD;
* implementation;
* code;
* EAP-006.

# 13. Required engineering contracts

The Draft shall define at minimum:

1. **Instrument Identity Input Contract**
   Consumes the EAP-004 Instrument Identity Contract without recreating identity.

2. **Candidate Factual Information Input Contract**
   Represents source-neutral candidate factual information and its bounded context.

3. **Attribution Evaluation Readiness Contract**
   Represents whether governed attribution evaluation may begin.

4. **Attribution Evaluation Activity Contract**
   Represents bounded attribution evaluation without mechanics.

5. **Attribution Outcome Contract**
   Represents exactly one outcome: Attribution Eligible or Attribution Ineligible.

6. **Attribution Eligibility Contract**
   Represents satisfaction of the ADP-001D attribution preconditions.

7. **Attribution Ineligibility Contract**
   Represents failure to establish one or more required preconditions.

8. **Attribution Ineligibility Reason Contract**
   Preserves the exact non-sensitive reason or reasons without reinterpretation.

9. **Canonical Identity Association Contract**
   Associates candidate factual information with approved identity without ownership transfer.

10. **Provenance Continuity Contract**
    Preserves factual source and origin meaning.

11. **Attribution Continuity Contract**
    Preserves explainable identity-to-factual-information association.

12. **Source Attribution Contract**
    Preserves the factual information’s source association.

13. **Temporal Attribution Contract**
    Preserves approved temporal meaning without defining timestamp mechanics.

14. **Uncertainty and Ambiguity Preservation Contract**
    Preserves retained uncertainty and unresolved ambiguity.

15. **Provider-Condition Distinction Contract**
    Keeps partial, failed and unavailable Provider information distinguishable.

16. **Semantic Separation Contract**
    Keeps identity metadata, factual information and derived interpretation distinct.

17. **Effective Identity Context Contract**
    Preserves applicable approved identity or lifecycle context without lifecycle processing.

18. **Observation Participation Eligibility Contract**
    Represents only eligibility for later Observation participation.

19. **Boundary Violation Contract**
    Represents prohibited bypasses, ownership violations and unsupported inference.

# 14. Required engineering representations

The Draft shall define separate representations for at least:

* `ATTRIBUTION_EVALUATION_READY`;
* `ATTRIBUTION_EVALUATION_NOT_READY`;
* `ATTRIBUTION_EVALUATION_NOT_STARTED`;
* `ATTRIBUTION_EVALUATION_ACTIVE`;
* `ATTRIBUTION_ELIGIBLE`;
* `ATTRIBUTION_INELIGIBLE`;
* `CANONICAL_IDENTITY_ASSOCIATED`;
* `CANONICAL_IDENTITY_NOT_ESTABLISHED`;
* `FACTUAL_INFORMATION_ASSOCIATED`;
* `PROVENANCE_CONTINUITY_PRESERVED`;
* `PROVENANCE_CONTINUITY_NOT_ESTABLISHED`;
* `SOURCE_ATTRIBUTION_PRESERVED`;
* `SOURCE_ATTRIBUTION_NOT_ESTABLISHED`;
* `TEMPORAL_ATTRIBUTION_PRESERVED`;
* `TEMPORAL_ATTRIBUTION_NOT_ESTABLISHED`;
* `PARTIALITY_DISTINGUISHED`;
* `FAILED_INFORMATION_DISTINGUISHED`;
* `UNAVAILABLE_INFORMATION_DISTINGUISHED`;
* `UNCERTAINTY_PRESERVED`;
* `AMBIGUITY_PRESERVED`;
* `IDENTITY_METADATA_DISTINGUISHED`;
* `DERIVED_INTERPRETATION_DISTINGUISHED`;
* `EFFECTIVE_IDENTITY_CONTEXT_PRESERVED`;
* `EFFECTIVE_IDENTITY_CONTEXT_NOT_ESTABLISHED`;
* `OBSERVATION_PARTICIPATION_ELIGIBLE`;
* `OBSERVATION_PARTICIPATION_INELIGIBLE`;
* `BOUNDARY_CONFORMANT`;
* `BOUNDARY_VIOLATION`.

`CANONICAL_IDENTITY_NOT_ESTABLISHED` here means the required approved identity association is unavailable for attribution. It shall not create or alter Instrument identity.

No executable state machine is authorized.

# 15. Required engineering obligations

Engineering shall demonstrate that:

1. Instrument retains identity ownership.

2. Observation owns attribution authority.

3. candidate factual information does not become Observation-owned merely by entering EAP-005.

4. identity does not become factual state.

5. factual information does not create or redefine identity.

6. EAP-004 identity meaning is consumed without reinterpretation.

7. Attribution Readiness remains distinct from Attribution Outcome.

8. exactly one Attribution Outcome exists per bounded evaluation.

9. Attribution Eligible and Attribution Ineligible remain mutually exclusive.

10. Attribution Eligible does not imply factual correctness.

11. Attribution Eligible does not imply Observation Acceptance.

12. Attribution Eligible does not confer Observation ownership.

13. Attribution Eligible does not authorize publication.

14. approved canonical identity association is required.

15. provenance continuity is preserved.

16. attribution continuity is preserved.

17. source attribution is preserved.

18. temporal attribution is preserved.

19. partial Provider information remains distinguishable.

20. failed Provider information remains distinguishable.

21. unavailable Provider information remains distinguishable.

22. identity metadata remains distinct from factual information.

23. derived interpretation remains distinct from factual information.

24. uncertainty remains explicit.

25. ambiguity remains unresolved and explicit.

26. attribution failure remains visible.

27. missing information does not mean zero.

28. Provider unavailability does not become Instrument lifecycle or Market availability.

29. applicable effective identity context is preserved where required.

30. Mapping mechanics remain excluded.

31. Lifecycle transition mechanics remain excluded.

32. Observation Acceptance remains excluded.

33. sensitive information and raw Provider payloads remain excluded.

34. Provider neutrality and implementation neutrality are preserved.

35. EAP-005 terminates before Observation Acceptance architecture begins.

# 16. Authorized Engineering Question Set

The Draft shall retain and answer these 30 questions one-to-one.

1. What engineering contract represents Attribution Evaluation Readiness?

2. How is Attribution Evaluation Readiness kept distinct from Architectural Admissibility and Attribution Outcome?

3. What information may enter the EAP-005 boundary?

4. What information is prohibited from entering the EAP-005 boundary?

5. What engineering contract represents the approved canonical Instrument identity input?

6. How is Instrument identity consumed without reinterpretation or ownership transfer?

7. What engineering contract represents Candidate Factual Information?

8. Who owns candidate factual information before Observation Acceptance?

9. What engineering contract represents Attribution Evaluation Activity?

10. What exact preconditions permit Attribution Evaluation?

11. What engineering contract represents Attribution Outcome?

12. What Attribution Outcomes are permitted?

13. What engineering conditions establish Attribution Eligible?

14. What engineering conditions establish Attribution Ineligible?

15. How are attribution-ineligibility reasons preserved?

16. What constitutes an approved canonical identity association?

17. How is provenance continuity preserved?

18. How is attribution continuity preserved?

19. How is source attribution preserved?

20. How is temporal attribution preserved?

21. How are partial Provider information, failed Provider information and unavailable Provider information kept distinct?

22. How is identity metadata kept distinct from candidate factual information?

23. How is derived interpretation kept distinct from candidate factual information?

24. How are retained uncertainty and unresolved ambiguity preserved?

25. How is applicable effective identity context preserved without defining Lifecycle mechanics?

26. What does Attribution Eligible permit?

27. What does Attribution Eligible never establish?

28. What engineering contract may cross the downstream boundary?

29. Where does EAP-005 terminate?

30. What matters require further architecture rather than Engineering discretion?

# 17. Authorized Engineering Invariant Set

The following 35 invariants shall be reproduced without substantive alteration:

1. **Canonical Instrument Identity shall remain owned exclusively by Instrument.**

2. **Attribution Authority shall remain owned exclusively by Observation.**

3. **Engineering representation shall not transfer semantic ownership.**

4. **Candidate factual information shall not become Observation-owned merely by entering EAP-005.**

5. **Instrument Identity shall not become factual market state.**

6. **Factual market information shall not create or redefine Instrument Identity.**

7. **The EAP-004 Instrument Identity Contract shall be consumed without reinterpretation.**

8. **Attribution Evaluation Readiness shall remain distinct from Attribution Outcome.**

9. **Exactly one Attribution Outcome shall exist for one bounded attribution evaluation.**

10. **Attribution Eligible and Attribution Ineligible shall be the only Attribution Outcomes.**

11. **Attribution Eligible shall not imply factual correctness.**

12. **Attribution Eligible shall not imply Observation Acceptance.**

13. **Attribution Eligible shall not confer Observation ownership.**

14. **Attribution Eligible shall not authorize Observation publication.**

15. **Attribution Eligible shall not imply Validation success or fitness for use.**

16. **Approved canonical Instrument identity association shall be required for Attribution Eligible.**

17. **Provenance continuity shall remain preserved.**

18. **Attribution continuity shall remain preserved.**

19. **Source attribution shall remain preserved.**

20. **Temporal attribution shall remain preserved where required.**

21. **Partial Provider information shall remain distinguishable.**

22. **Failed Provider information shall remain distinguishable.**

23. **Unavailable Provider information shall remain distinguishable.**

24. **Identity metadata shall remain distinct from factual market information.**

25. **Derived interpretation shall remain distinct from factual market information.**

26. **Retained uncertainty shall remain explicit.**

27. **Unresolved ambiguity shall remain explicit and unresolved.**

28. **Attribution failure shall not be silently represented as Attribution Eligible.**

29. **Missing information shall not mean zero or prove market state.**

30. **Provider unavailability shall not establish Instrument Lifecycle or Market availability.**

31. **Provider Mapping mechanics shall remain outside EAP-005.**

32. **Instrument Lifecycle transition mechanics shall remain outside EAP-005.**

33. **Raw Provider payloads and sensitive values shall not enter EAP-005 governed contracts.**

34. **No Observation Acceptance, Market, Validation, Risk, Execution, Portfolio, Event or Audit meaning shall be created by EAP-005.**

35. **EAP-005 shall remain provider-neutral and implementation-neutral and shall not authorize Provider communication, an EDD, implementation or code.**

# 18. Mandatory review criteria

Chief Architect review shall verify:

1. Instrument and Observation ownership remain separate.

2. attribution does not create or alter identity.

3. candidate factual information does not become an Observation merely by crossing the boundary.

4. EAP-004 identity is consumed without reinterpretation.

5. exactly two attribution outcomes exist.

6. attribution eligibility is not factual correctness.

7. attribution eligibility is not Observation Acceptance or ownership.

8. provenance, source and temporal attribution are preserved.

9. partiality, failure and unavailability remain distinct.

10. uncertainty and ambiguity remain explicit.

11. attribution failure remains visible.

12. identity metadata and derived interpretation remain distinct from facts.

13. effective identity context is preserved without Lifecycle processing.

14. Mapping mechanics remain excluded.

15. Observation Acceptance remains excluded.

16. the exact 30-question set is retained.

17. the exact 35-invariant set is retained.

18. ADP-001D, ADP-001E and EAP-004 traceability is complete.

19. no runtime or Provider communication authority is introduced.

20. no EDD or implementation authority is introduced.

# 19. ADR determination

**ADR required: No**

No ADR is required provided EAP-005:

* translates ADP-001D;
* preserves Instrument and Observation ownership;
* uses the existing Instrument → Observation dependency;
* creates no new domain or dependency;
* does not define acquisition;
* does not enter Observation Acceptance;
* creates no reusable platform attribution framework.

An ADR becomes required if any of those conditions are violated.

# 20. Required Document Register entry

| Field                        | Required value                                                                      |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| Document ID                  | EAP-005                                                                             |
| Title                        | Instrument-to-Observation Attribution Eligibility Engineering Architecture          |
| Classification               | Engineering Architecture Package                                                    |
| Product                      | KRONOS Swing                                                                        |
| Phase                        | Phase 1 — Market Data Foundation                                                    |
| Owner                        | Engineering Architect                                                               |
| Governing ADP                | ADP-001D Version 1.0                                                                |
| Supporting ADPs              | ADP-001A, ADP-001B, ADP-001C, ADP-001E, ADP-001H, ADP-001I, ADP-001J                |
| Upstream EAP                 | EAP-004 Version 1.0                                                                 |
| Version                      | 0.1                                                                                 |
| Status                       | Draft                                                                               |
| Canonical Status             | Not Canonical                                                                       |
| ADR Required                 | No                                                                                  |
| Engineering Impact           | None                                                                                |
| Runtime Impact               | None                                                                                |
| EDD Authorization            | None                                                                                |
| Implementation Authorization | None                                                                                |
| Commit Authorization         | None                                                                                |
| Push Authorization           | None                                                                                |
| Next Authorized Capability   | None                                                                                |
| Repository location          | `docs/engineering/eap/EAP-005-INSTRUMENT-TO-OBSERVATION-ATTRIBUTION-ELIGIBILITY.md` |

# 21. Final authorization decision

| Question                                                  | Decision           |
| --------------------------------------------------------- | ------------------ |
| Sufficient canonical architecture exists                  | **Yes**            |
| New ADP required before continuation                      | **No**             |
| Provider Mapping Architecture required before EAP-005     | **No**             |
| Instrument Lifecycle Architecture required before EAP-005 | **No**             |
| Provider Mapping remains future architecture              | **Yes**            |
| Instrument Lifecycle remains future architecture          | **Yes**            |
| EAP-005 official capability                               | **Confirmed**      |
| EAP-005 Draft Version 0.1                                 | **AUTHORIZED**     |
| Engineering verification                                  | **REQUIRED**       |
| Canonicalization                                          | **NOT AUTHORIZED** |
| EAP-006                                                   | **NOT AUTHORIZED** |
| EDD                                                       | **NOT AUTHORIZED** |
| Implementation                                            | **NOT AUTHORIZED** |
| Runtime activity                                          | **NOT AUTHORIZED** |
| Commit                                                    | **NOT AUTHORIZED** |
| Push                                                      | **NOT AUTHORIZED** |

ADP-001D itself states that it creates no runtime or Engineering Package authority, so this authorization is a separate Chief Architect decision translating its already-approved semantic boundary.

**EAP-005 DRAFTING AUTHORIZED**
