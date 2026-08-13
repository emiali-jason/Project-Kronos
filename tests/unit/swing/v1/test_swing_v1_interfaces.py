from pathlib import Path

import pytest

from kronos.swing.v1 import V1BenchmarkMappingError, load_v1_benchmark_map


def test_approved_relationship_source_retains_only_ready_equity_mappings() -> None:
    result = load_v1_benchmark_map()

    assert len(result.relationships) == 90
    assert result.benchmark_for("ICICIBANK") == "BANK NIFTY"
    assert result.benchmark_for("IOC") == "NIFTY"
    assert result.benchmark_for("KAYNES") is None
    assert result.benchmark_for("GOLDM") is None


def test_malformed_benchmark_mapping_fails_closed_without_source_contents(
    tmp_path: Path,
) -> None:
    source = tmp_path / "relationships.csv"
    source.write_text("symbol,parent_index_symbol\nIOC,NSE:NIFTY\n", encoding="utf-8")

    with pytest.raises(V1BenchmarkMappingError) as captured:
        load_v1_benchmark_map(source)

    assert str(captured.value) == "V1_BENCHMARK_MAPPING_INVALID"
