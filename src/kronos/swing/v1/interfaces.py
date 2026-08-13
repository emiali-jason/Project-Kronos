"""Explicit input relationships consumed by Swing V1 Layer 1."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


_RELATIONSHIP_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "nse"
    / "KRONOS_NSE_RELATIONSHIPS.csv"
)


class V1BenchmarkMappingError(RuntimeError):
    """Sanitized failure to establish reliable approved benchmark mappings."""


@dataclass(frozen=True, slots=True)
class BenchmarkRelationship:
    """One stable equity-to-index relationship used as supporting context."""

    canonical_identity: str
    benchmark_identity: str

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or self.benchmark_identity not in {"NIFTY", "BANK NIFTY"}
        ):
            raise ValueError("V1_BENCHMARK_RELATIONSHIP_INVALID")


@dataclass(frozen=True, slots=True)
class V1BenchmarkMap:
    """Immutable approved relationship map supplied to Layer-1 analysis."""

    relationships: tuple[BenchmarkRelationship, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.canonical_identity for item in self.relationships)
        if (
            type(self.relationships) is not tuple
            or any(type(item) is not BenchmarkRelationship for item in self.relationships)
            or len(set(identities)) != len(identities)
        ):
            raise ValueError("V1_BENCHMARK_MAP_INVALID")

    def benchmark_for(self, canonical_identity: str) -> str | None:
        """Return the reliable parent benchmark, if one is retained."""

        return next(
            (
                item.benchmark_identity
                for item in self.relationships
                if item.canonical_identity == canonical_identity
            ),
            None,
        )


def load_v1_benchmark_map(
    source: Path = _RELATIONSHIP_SOURCE,
) -> V1BenchmarkMap:
    """Load only the approved parent-index relationship needed by Slice 1."""

    if not isinstance(source, Path):
        raise V1BenchmarkMappingError("V1_BENCHMARK_MAPPING_INVALID")
    try:
        with source.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, strict=True)
            required = {"symbol", "parent_index_symbol", "relationship_status"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise V1BenchmarkMappingError("V1_BENCHMARK_MAPPING_INVALID")
            rows = tuple(reader)
    except V1BenchmarkMappingError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise V1BenchmarkMappingError("V1_BENCHMARK_MAPPING_UNAVAILABLE") from error

    relationships = []
    for row in rows:
        symbol = row.get("symbol")
        parent = row.get("parent_index_symbol")
        status = row.get("relationship_status")
        if (
            type(symbol) is not str
            or not symbol
            or status not in {"READY", "REVIEW"}
            or parent not in {"NSE:NIFTY", "NSE:BANKNIFTY"}
        ):
            raise V1BenchmarkMappingError("V1_BENCHMARK_MAPPING_INVALID")
        if status != "READY":
            continue
        benchmark = "BANK NIFTY" if parent == "NSE:BANKNIFTY" else "NIFTY"
        relationships.append(BenchmarkRelationship(symbol, benchmark))
    return V1BenchmarkMap(tuple(relationships))


__all__ = [
    "BenchmarkRelationship",
    "V1BenchmarkMap",
    "V1BenchmarkMappingError",
    "load_v1_benchmark_map",
]
