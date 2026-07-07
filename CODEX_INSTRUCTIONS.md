# Project KRONOS
# CODEX ENGINEERING INSTRUCTIONS

Version: 1.1
Last Updated: 2026-07-07

---

# Mission

Project KRONOS is an institutional trend-following trading framework.

The objective is NOT to predict tops or bottoms.

The objective is to identify high-probability institutional trends, remain with the trend while the evidence remains strong, and exit only when the evidence weakens.

Every implementation must support this philosophy.

---

# Core Engineering Principles

- Preserve the existing architecture.
- Extend the framework instead of rewriting it.
- One engine = One responsibility.
- Simplicity is preferred over clever code.
- Readability is preferred over shorter code.
- Never sacrifice maintainability for fewer lines.

---

# Engine Architecture

Each engine must perform ONE major responsibility.

Example:

KR-100 Configuration

KR-150 Display

KR-200 Market Detection

KR-250 Asset Mapping

KR-260 Market Data

KR-270 Indicators

KR-271 Mathematical Functions

KR-275 Market Structure

KR-280 CPR Intelligence

KR-300 Trend Intelligence

KR-310 Evidence Engine

KR-320 Barrier Interaction

KR-350 Opportunity Engine

KR-400 Position Management

KR-500 Decision Engine

Never merge engine responsibilities.

---

# Engine Dependency Rules

Higher engines consume ONLY public outputs from lower engines.

Never consume internal variables.

Every mature engine should expose a clean public interface.

Loose coupling is mandatory.

---

# Frozen Modules

Frozen engines must never be modified unless specifically requested.

Currently Frozen

KR-280 CPR Intelligence

Bug fixes are allowed.

Feature changes require approval.

---

# Coding Standards

Use Pine Script Version 6.

Follow the existing naming conventions.

Keep functions modular.

Avoid duplicated calculations.

Reuse helper functions whenever possible.

Comment all major sections.

Preserve existing comments.

Never remove comments without approval.

---

# Code Formatting

Readability is more important than compact code.

Preferred:

- One logical statement per line.
- Use multiline expressions when they improve clarity.
- Group related calculations together.
- Use blank lines between logical sections.
- Keep indentation consistent.
- Align assignments where practical.

Avoid:

- Long compressed one-line calculations.
- Nested ternary operators unless unavoidable.
- Extremely long function calls on one line.

Exception:

If Pine Script parsing requires a single-line expression,
use a single line and add a short explanatory comment if helpful.

---

# Engine Section Format

Every engine must begin with a banner.

Example

//=============================================================================
// KR-300.20 - SMA ALIGNMENT ENGINE
//=============================================================================

This format must remain consistent throughout the project.

---

# Function Style

Prefer small reusable functions.

Good example

f_example() =>
    value = ...
    result = ...
    result

Avoid huge anonymous calculations inside the main body.

---

# Public Interfaces

Expose only what downstream engines require.

Do not expose unnecessary internal calculations.

Public variables should have clear names.

---

# Performance

Avoid unnecessary request.security() calls.

Avoid duplicated indicator calculations.

Reuse previously calculated values.

Keep execution efficient.

---

# Trading Philosophy

Indicators never generate trades.

Indicators contribute evidence.

No single indicator is sufficient.

Confluence is required.

Trend is more important than prediction.

Follow institutional participation.

Never introduce trading rules that have not been approved.

Never invent trading logic.

When uncertain, ask instead of assuming.

---

# Development Workflow

Before implementation

1. Understand the architecture.

2. Identify affected engines.

3. Preserve compatibility.

Implementation

1. Implement only the requested feature.

2. Preserve existing interfaces.

3. Keep code modular.

After implementation

1. Review your own work.

2. Check for duplicated logic.

3. Check public interfaces.

4. Report assumptions.

---

# Before Modifying Existing Code

Always determine

- Which engine is changing.
- Which engines consume it.
- Whether public interfaces change.

If interfaces change,

EXPLAIN WHY

before implementing.

---

# Validation Checklist

Before considering a task complete

✓ Compiles successfully

✓ No duplicated logic

✓ No interface conflicts

✓ Existing functionality preserved

✓ Existing architecture preserved

✓ Comments updated

✓ Public outputs documented

---

# Never Do

Never redesign the architecture without approval.

Never move engine boundaries.

Never rename public interface variables without approval.

Never delete working functionality.

Never modify frozen engines unless requested.

Never introduce trading rules based on assumptions.

Never optimize code at the expense of readability.

Never compress code simply to reduce line count.

---

# Preferred Response Format

After every implementation provide:

Summary

Files Modified

Engine Modified

Public Interface Changes

Compile Risks

Trading Logic Assumptions

Recommended Next Step

---

# Project Philosophy

KRONOS is NOT an indicator.

KRONOS is a modular institutional trend-following framework.

Every new feature must improve one of these:

- Trend Understanding
- Market Context
- Evidence Quality
- Opportunity Recognition
- Position Management
- Decision Quality

If a feature does not improve one of these areas,
it probably does not belong in KRONOS.