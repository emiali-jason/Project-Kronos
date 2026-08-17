# CHANGELOG

All notable changes to PROJECT KRONOS will be documented in this file.

This project follows a milestone-based development approach.

## [0.6.0] — 2026-08-17

### Production promotion

- Promoted the approved frozen KRONOS FUTURES V2 lineage to sole active Production authority.
- Retired KRONOS FUTURES V1 as `RETIRED / SUPERSEDED` while preserving its exact source, SHA-256, historical evidence, and rollback lineage.
- Closed the V1-versus-V2 comparison programme.
- Closed the separate MCX Pine Swing Observation programme after its evidence path was superseded by integrated Swing V1 probable-by-probable visual review; integrated Swing Visual Review continues.
- Replaced the KR-705 comparison workstation with one `DESCRIPTION | PROD` Trader column and single-engine Production developer diagnostics.
- Changed no analytical calculations, indicators, thresholds, readiness, decisions, triggers, lifecycle semantics, CPR, reference logic, or alerts.

### NSE Production promotion

- Promoted the approved NSE-V1-SR1 lineage to the first formal KRONOS NSE Production Pine.
- Preserved the byte-exact SR1 checkpoint and working candidate at SHA-256 `33ddbdd416d905bf4cb925d45d08d9d4efccfe6db969b668d5101164c96b48f2`.
- Replaced the Candidate-versus-legacy comparison workstation with one NSE Production column; changed no analytical logic or thresholds.
- Closed the separate NSE Pine programme while preserving NSE-A/B/C/D, 93/93 qualification, Week-1 evidence, the SBI CPR determination, and deferred NSE-T01.
- Integrated Swing Visual Review continues; evidence-backed future refinement remains permitted.

---

# [0.5.0-alpha.1] - 2026-07-04

## Added

### Repository
- Created Project-Kronos repository
- Added project documentation
- Created `develop` branch
- Established GitHub workflow

### Documentation
- Updated README with project overview
- Added project roadmap
- Added changelog

### KRONOS FUTURES

Completed Engines

- ✅ KR-100 Configuration Engine
- ✅ KR-150 Indicator Engine
- ✅ KR-200 Market Identification Engine
- ✅ KR-250 Asset Intelligence Engine

### Status

- Pine Script compiles successfully
- Foundation architecture established
- Ready to begin KR-260 Global Data Engine

---

# Upcoming

## 0.5.0-alpha.2

Planned

- KR-260 Global Data Engine
- KR-300 Local Trend Engine
- KR-350 Trend Alignment Engine

---

## 0.5.0-beta.1

Planned

- Decision Engine
- Risk Engine
- Dashboard
- Alerts

---

## 0.5.0

Initial public foundation release.

# KRONOS Change Log

## Build 0006
Date: 28-Jun-2026

### KR-260 Market Data Engine
- Added reusable getOHLCV() helper
- Added Primary OHLCV datasets
- Added Reference OHLCV datasets
- Added Market Data validation
- Standardized Market Data interface

Status:
Production Ready

Build 0008

Completed

KR-271 Mathematical Library

Added

True Range
ATR
Directional Movement
Directional Index
Trend Strength

Status

Frozen

## Build 0010 — KR-280 CPR Intelligence Engine

### Added
- KR-280 CPR Intelligence Engine
- Classic CPR calculations
- R1–R4 and S1–S4 pivot calculations
- Professional CPR renderer with shaded value zone
- CPR width analysis
- CPR width classification
- CPR relationship engine
- Price position analysis
- Virgin CPR detection
- Complete public interface

### Changed
- Adopted KRONOS CPR visual standard
- CPR rendered as a value zone instead of independent lines

### Design Decisions
- DD-0002: CPR is a value zone
- DD-0005: CPR Relationship Engine
