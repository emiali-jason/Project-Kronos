# PROJECT KRONOS ARCHITECTURE

This document describes the software architecture of PROJECT KRONOS.

---

# Design Philosophy

PROJECT KRONOS is built as a modular Decision Support System (DSS).

Each engine has a single responsibility.

Each engine receives clearly defined inputs, performs one task, and produces outputs for the next engine.

No engine should perform multiple unrelated functions.

---

# High-Level Architecture

```
Configuration
        │
        ▼
Indicator Engine
        │
        ▼
Market Identification
        │
        ▼
Asset Intelligence
        │
        ▼
Global Data
        │
        ▼
Global Indicators
        │
        ▼
Local Trend
        │
        ▼
Trend Alignment
        │
        ▼
Trend Quality
        │
        ▼
Setup Qualification
        │
        ▼
Decision Engine
        │
        ▼
Decision Explanation
        │
        ▼
Risk Management
        │
        ▼
Dashboard
        │
        ▼
Alerts
```

---

# Engine Responsibilities

| Engine | Responsibility |
|---------|----------------|
| KR-100 | Configuration and user settings |
| KR-150 | Indicators and moving averages |
| KR-200 | Identify market and timeframe |
| KR-250 | Map trading instrument to global benchmark |
| KR-260 | Retrieve global market data |
| KR-270 | Calculate global indicators |
| KR-300 | Calculate local trend |
| KR-350 | Compare global and local trends |
| KR-400 | Measure trend quality |
| KR-450 | Validate trading setup |
| KR-500 | Generate trading decision |
| KR-550 | Explain the decision |
| KR-600 | Calculate risk parameters |
| KR-700 | Display dashboard |
| KR-800 | Generate alerts |

---

# Engineering Principles

- One engine, one responsibility.
- Every engine must compile before the next engine begins.
- Outputs should be reusable by downstream engines.
- Avoid duplicate calculations.
- Keep code readable and maintainable.

---

# Branch Strategy

- `main` — Stable releases
- `develop` — Active development

Future feature branches may be created for major enhancements.

---

# Documentation

The repository documentation is organized as follows:

- `README.md` — Project overview
- `CHANGELOG.md` — History of changes
- `ROADMAP.md` — Planned development
- `ENGINE_STATUS.md` — Current implementation progress
- `ENGINE_SPECIFICATIONS.md` — Detailed engine specifications
- `ARCHITECTURE.md` — System architecture
- `DECISIONS.md` — Major engineering decisions

---

This document should be updated whenever the architecture changes.