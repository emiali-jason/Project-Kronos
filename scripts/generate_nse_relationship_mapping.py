#!/usr/bin/env python3
# Generate the KR-252 NSE relationship mapping block from the curated CSV.

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "data/nse/KRONOS_NSE_RELATIONSHIPS.csv"
PINE_PATH = REPO_ROOT / "KRONOS_FUTURES/source/KRONOS_FUTURES.pine"
BEGIN_MARKER = "// BEGIN GENERATED NSE RELATIONSHIP MAPPING"
END_MARKER = "// END GENERATED NSE RELATIONSHIP MAPPING"
REQUIRED_COLUMNS = [
    "symbol",
    "company_name",
    "cash_symbol",
    "primary_sector_group",
    "sector_index_symbol",
    "parent_index_symbol",
    "market_model",
    "execution_profile",
    "benchmark_type",
    "relationship_status",
    "mapping_confidence",
    "mapping_reason",
]
APPROVED_INDEX_SYMBOLS = {
    "NSE:CNXIT",
    "NSE:CNXAUTO",
    "NSE:CNXPHARMA",
    "NSE:CNXMETAL",
    "NSE:CNXENERGY",
    "NSE:CNXFINANCE",
    "NSE:CNXFMCG",
    "NSE:CNXREALTY",
    "NSE:CNXMEDIA",
    "NSE:CNXINFRA",
    "NSE:CNXPSUBANK",
    "NSE:CNXCOMMODITIES",
    "NSE:CNXCONSUMPTION",
    "NSE:CNXSERVICE",
    "NSE:CNXPSE",
    "NSE:NIFTY",
    "NSE:BANKNIFTY",
}
VALID_STATUS = {"READY", "REVIEW"}
VALID_BENCHMARK_TYPES = {"DIRECT", "LOGICAL_PROXY", "TEMPORARY_PROXY"}


def pine_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Missing required columns: {', '.join(missing)}")
        rows = list(reader)

    symbols = [row["symbol"] for row in rows]
    duplicates = sorted(symbol for symbol, count in Counter(symbols).items() if count > 1)
    if len(rows) != 91:
        raise SystemExit(f"Expected 91 rows, found {len(rows)}")
    if duplicates:
        raise SystemExit(f"Duplicate symbols: {', '.join(duplicates)}")
    if any(not row["cash_symbol"] for row in rows):
        raise SystemExit("Empty cash_symbol detected")
    if any(row["symbol"] in {"NIFTY", "BANKNIFTY"} for row in rows):
        raise SystemExit("NIFTY/BANKNIFTY must remain context indices, not stock rows")

    status_counts = Counter(row["relationship_status"] for row in rows)
    if status_counts != {"READY": 90, "REVIEW": 1}:
        raise SystemExit(f"Expected 90 READY and 1 REVIEW, found {dict(status_counts)}")
    review_symbols = [row["symbol"] for row in rows if row["relationship_status"] == "REVIEW"]
    if review_symbols != ["KAYNES"]:
        raise SystemExit(f"Expected KAYNES as the only REVIEW row, found {review_symbols}")

    for row in rows:
        if row["relationship_status"] not in VALID_STATUS:
            raise SystemExit(f"Invalid relationship_status for {row['symbol']}: {row['relationship_status']}")
        if row["benchmark_type"] not in VALID_BENCHMARK_TYPES:
            raise SystemExit(f"Invalid benchmark_type for {row['symbol']}: {row['benchmark_type']}")
        for column in ("sector_index_symbol", "parent_index_symbol"):
            if row[column] not in APPROVED_INDEX_SYMBOLS:
                raise SystemExit(f"Unsupported {column} for {row['symbol']}: {row[column]}")

    return rows


def generate_block(rows: list[dict[str, str]]) -> str:
    status_counts = Counter(row["relationship_status"] for row in rows)
    lines = [
        BEGIN_MARKER,
        "// Source: data/nse/KRONOS_NSE_RELATIONSHIPS.csv",
        "// Dataset version/date: Curated 2026-07-11",
        f"// Generated row count: {len(rows)}",
        f"// READY count: {status_counts['READY']}",
        f"// REVIEW count: {status_counts['REVIEW']}",
        "// Generation method: scripts/generate_nse_relationship_mapping.py",
        "// This block is generated configuration only. Do not add trading logic here.",
        "if relationshipIsNSEEquity",
    ]

    for index, row in enumerate(rows):
        branch = "if" if index == 0 else "else if"
        status_constant = "KR252_STATUS_READY" if row["relationship_status"] == "READY" else "KR252_STATUS_REVIEW"
        lines.extend(
            [
                f"    {branch} relationshipSymbolMatches(\"{pine_string(row['symbol'])}\", \"{pine_string(row['company_name'].upper())}\", relationshipSymbolRoot, relationshipSymbolTicker, relationshipSymbolDescription)",
                f"        relationshipNormalizedNSESymbol := \"{pine_string(row['symbol'])}\"",
                "        relationshipNSEMapped := true",
                f"        relationshipCashSymbol := \"{pine_string(row['cash_symbol'])}\"",
                f"        relationshipPrimaryReferenceSymbol := \"{pine_string(row['sector_index_symbol'])}\"",
                f"        relationshipSecondaryReferenceSymbol := \"{pine_string(row['parent_index_symbol'])}\"",
                f"        relationshipSectorIndexSymbol := \"{pine_string(row['sector_index_symbol'])}\"",
                f"        relationshipParentIndexSymbol := \"{pine_string(row['parent_index_symbol'])}\"",
                f"        relationshipDatasetStatus := {status_constant}",
                f"        relationshipDatasetReason := \"{pine_string(row['mapping_reason'])}\"",
            ]
        )

    lines.append(END_MARKER)
    return "\n".join(lines)


def replace_generated_block(block: str) -> None:
    text = PINE_PATH.read_text()
    begin = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit("Generated NSE relationship mapping markers are missing or malformed")
    end += len(END_MARKER)
    PINE_PATH.write_text(text[:begin] + block + text[end:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the KR-252 NSE relationship mapping block.")
    parser.add_argument("--check", action="store_true", help="validate the CSV and print counts without rewriting Pine")
    args = parser.parse_args()

    rows = load_rows()
    if not args.check:
        replace_generated_block(generate_block(rows))
    counts = Counter(row["relationship_status"] for row in rows)
    action = "Validated" if args.check else "Generated"
    print(f"{action} {len(rows)} NSE relationship rows")
    print(f"READY={counts['READY']} REVIEW={counts['REVIEW']}")


if __name__ == "__main__":
    main()
