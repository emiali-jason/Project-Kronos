# Architecture Interfaces

**Status:** Draft  
**Owner:** Architecture Librarian  
**Approved By:** Not approved

## Purpose

This directory contains reusable templates and approved or proposed interface contracts between KRONOS products.

Product communication must be documented through an interface contract. A Draft or Proposed interface is not authoritative.

## Interface Index

| Interface | Title | Status | Version | Owner | Producer | Consumer | Related documents |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [ECIC-001](ECIC-001-Execution-Context-Interface-Contract.md) | Execution Context Interface Contract | Approved | 1.0 | Chief Architect | Execution Context Provider | Defined by product architecture | [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md); [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md); [ECPC-001](ECPC-001-Execution-Context-Payload-Contract.md); [ECM-001](../models/ECM-001-Execution-Context-Model.md); [ADL-003](../ADL-003-Execution-Context-Adapters.md) |
| [ECPC-001](ECPC-001-Execution-Context-Payload-Contract.md) | Execution Context Payload Contract | Approved | Not stated | Not stated | Execution Context Provider | Defined by product architecture | [ECIC-001](ECIC-001-Execution-Context-Interface-Contract.md); [ECM-001](../models/ECM-001-Execution-Context-Model.md); [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md); [ADL-003](../ADL-003-Execution-Context-Adapters.md); [PP-007](../principles/PP-007-Execution-Semantics-Across-Markets.md) |
| [EAIC-001](EAIC-001-Exchange-Availability-Interface-Contract.md) | Exchange Availability Interface Contract | Approved | 1.0 | Chief Architect | KR-200 | Presentation components | [ENGINE_OWNERSHIP](../ENGINE_OWNERSHIP.md); [DATA_FLOW](../DATA_FLOW.md); [ECPC-001](ECPC-001-Execution-Context-Payload-Contract.md); [ADR-006](../adr/ADR-006-Execution-Context-Provider-Architecture.md); [ECM-001](../models/ECM-001-Execution-Context-Model.md) |

Create proposed contracts from [`INTERFACE_TEMPLATE.md`](INTERFACE_TEMPLATE.md). Do not infer interface fields, dependencies, or ownership from product names.
