# CHANGELOG

All notable changes to PROJECT KRONOS will be documented in this file.

This project follows a milestone-based development approach.

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