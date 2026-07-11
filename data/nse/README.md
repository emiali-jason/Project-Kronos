# KRONOS NSE Relationships

`KRONOS_NSE_RELATIONSHIPS.csv` is the reviewed relationship dataset for the approved KRONOS NSE futures trading universe.

## Purpose

The dataset defines the market relationships KR-252 will later expose for NSE instruments: cash symbol, primary sector benchmark, parent index, market model, execution profile, and review status. It is data-only source material and does not retrieve market data or create trading intelligence.

## Supported Universe vs Relationships

The supported universe answers whether an NSE symbol is approved for KRONOS coverage. The relationship dataset answers which market references influence that approved symbol.

`NSE:NIFTY` and `NSE:BANKNIFTY` are context indices. They are not included as stock rows in this dataset.

## Update Process

1. Update the approved TradingView watchlist universe.
2. Refresh the source universe export used for company names and index memberships.
3. Regenerate or edit this relationship CSV.
4. Validate that every approved stock is present exactly once.
5. Validate that `cash_symbol`, `sector_index_symbol`, and `parent_index_symbol` use only verified TradingView symbols.
6. Keep ambiguous mappings marked `REVIEW` until manually approved.

## Benchmark Type

`benchmark_type` identifies how the primary benchmark was selected:

- `DIRECT` means the benchmark directly represents the stock's sector or primary market context.
- `LOGICAL_PROXY` means the benchmark is the closest approved TradingView index when no dedicated verified benchmark exists.
- `TEMPORARY_PROXY` means the mapping is provisional and must remain `REVIEW` until a better benchmark is approved.

## Review Policy

Rows marked `READY` have a clear primary benchmark from verified watchlist indices. Rows marked `REVIEW` need human confirmation because the company has mixed exposure, lacks a dedicated verified sector index, or uses a provisional proxy.

`mapping_confidence` is intentionally conservative:

- `HIGH` means the benchmark is directly supported by the source index memberships or an explicit banking rule.
- `MEDIUM` means the benchmark is reasonable but should be reviewed.
- `LOW` means the benchmark is provisional and must be reviewed before Pine generation.

## One Primary Sector Benchmark

KRONOS uses one primary sector benchmark per stock so downstream engines receive a stable dependency relationship. Factor indices, equal-weight variants, broad-market indices, and multi-index memberships are not used as primary sector benchmarks.

## Pine Generation

Pine mappings will later be generated from this CSV into KR-252. The CSV is the source of truth; KR-252 should not hand-maintain the full NSE relationship map once generation begins.
