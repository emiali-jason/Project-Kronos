from __future__ import annotations

from pathlib import Path
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from zipfile import ZipFile
from io import BytesIO

from kronos.application.intraday_research import (
    IntradayResearchApplication, OPPORTUNITY_COLUMNS, TRACK_COLUMNS,
)
from kronos.browser.intraday_research import export_research_workbook
from kronos.intraday.wo12_research_contract import POLICY_CHECKSUM, SHEETS, opportunity_id
from kronos.intraday.wo12_research_store import ResearchStore
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run


class _Probables:
    def __init__(self, root: Path, run) -> None:
        self.root = root
        (root / "runs").mkdir(parents=True)
        (root / "runs" / f"{run.run_identity}.json").write_text("{}")
        self._run = run

    def load_run(self, identity):
        assert identity == self._run.run_identity
        return self._run

    def load_result(self, identity):
        return next(item for item in self._run.results if item.result_identity == identity)


class _Wo09:
    def __init__(self, root: Path) -> None:
        self.readiness = root
        root.mkdir()

    def load_readiness(self, identity):
        raise AssertionError(identity)


class _EmptyStore:
    def records(self, schema):
        return ()

    def load(self, identity):
        raise AssertionError(identity)


class _Lifecycle(_EmptyStore):
    def restore(self):
        return ()


def _application(tmp_path):
    run = _run(_opening_inputs()[-1])
    application = IntradayResearchApplication(
        probables=_Probables(tmp_path / "probables", run),
        wo09=_Wo09(tmp_path / "wo09"),
        futures=_EmptyStore(), lifecycle=_Lifecycle(),
        store=ResearchStore(tmp_path / "research"),
        publication_root=tmp_path / "Statistics" / "Intraday",
        clock=lambda: run.analysis_boundary,
    )
    return application, run


def test_opportunity_id_is_stable_separate_and_origin_bound(tmp_path) -> None:
    application, run = _application(tmp_path)
    projection = application.project(ensure_origins=True)
    row = dict(zip(OPPORTUNITY_COLUMNS, projection.opportunities[0], strict=True))

    assert row["opportunity_id"] == "RELIANCE-20260828-101500"
    assert row["opportunity_identity"].startswith("INTRADAY-WO12-OPPORTUNITY-")
    assert row["opportunity_id"] != row["opportunity_identity"]
    assert opportunity_id("NSE-EQ-RELIANCE", run.analysis_boundary) == row["opportunity_id"]
    assert opportunity_id("NSE-EQ-M&M", run.analysis_boundary) == "M&M-20260828-101500"

    again = application.project(ensure_origins=True)
    assert again.opportunities[0][:2] == projection.opportunities[0][:2]
    assert len(application.store.records("WO12_OPPORTUNITY_ORIGIN_V1")) == 1


def test_six_sheet_workbook_has_tables_formulas_and_no_active_content(tmp_path) -> None:
    application, _ = _application(tmp_path)
    projection = application.project(ensure_origins=True)
    first = export_research_workbook(projection)
    second = export_research_workbook(projection)
    assert first == second

    with ZipFile(BytesIO(first)) as archive:
        names = archive.namelist()
        workbook = archive.read("xl/workbook.xml").decode()
        analysis = archive.read("xl/worksheets/sheet4.xml").decode()
        opportunities = archive.read("xl/tables/table1.xml").decode()
        metadata = archive.read("xl/worksheets/sheet6.xml").decode()
    assert all(f'name="{name}"' in workbook for name in SHEETS)
    assert len([name for name in names if name.startswith("xl/tables/table")]) == 6
    assert '<tableColumn id="1" name="opportunity_id"/>' in opportunities
    assert 'name="opportunity_identity"' in opportunities
    assert "<f>" in analysis and "COUNTIF('Opportunities'!" in analysis
    assert not any("vbaProject" in name or "externalLinks" in name for name in names)
    assert POLICY_CHECKSUM in metadata
    assert all(name in OPPORTUNITY_COLUMNS for name in (
        "wo09_first_three_of_five_at", "wo09_first_four_of_five_at", "wo09_first_five_of_five_at",
        "underlying_entry", "future_entry", "risk_warning_state", "wo11_sponsor_action",
        "discovery_to_three_seconds", "three_to_four_seconds", "four_to_five_seconds",
        "five_to_trade_plan_seconds", "trade_plan_to_sponsor_decision_seconds",
        "sponsor_decision_to_wo11_action_seconds",
    ))
    assert all(name in TRACK_COLUMNS for name in (
        "planned_rr", "holding_seconds", "eligible_sample_count", "gap_duration_seconds",
    ))
    assert "PAPER Position expectancy R" in analysis
    assert "Paper Observation expectancy R" in analysis
    assert "Median model R" in analysis
    assert "Median holding seconds" in analysis


def test_atomic_monthly_publication_receipt_readback_and_idempotency(tmp_path) -> None:
    application, _ = _application(tmp_path)
    result = application.update(operation_identity="SPONSOR-UPDATE-001")
    assert result.workbook_path.name == "KRONOS_Intraday_Research_2026_08.xlsx"
    assert result.workbook_path.parent == tmp_path / "Statistics" / "Intraday"
    assert result.idempotent is False
    assert application.open_current("2026_08")[1] == result.workbook_path.read_bytes()
    assert not list((tmp_path / "research" / "staging").glob("*"))

    repeated = application.update(operation_identity="SPONSOR-UPDATE-001")
    assert repeated.idempotent is True
    assert repeated.receipt_identity == result.receipt_identity
    assert repeated.workbook_sha256 == result.workbook_sha256

    unchanged = application.update(operation_identity="SPONSOR-UPDATE-002")
    assert unchanged.outcome == "ALREADY_UP_TO_DATE"
    assert unchanged.receipt_identity == result.receipt_identity
    assert application.store.records("WO12_DAILY_PACKAGE_V1")[0].data["day_state"] == "PUBLISHED"
    receipt = application.store.load(result.receipt_identity).data
    assert receipt["status"] == "VERIFIED"
    assert receipt["daily_package_identity"].startswith("WO12_DAILY_PACKAGE_V1-")
    assert receipt["source_boundary_identity"].startswith("WO12-SOURCE-BOUNDARY-")
    assert receipt["workbook_filename"] == result.workbook_path.name


def test_failed_receipt_publication_restores_prior_monthly_bytes(tmp_path, monkeypatch) -> None:
    application, _ = _application(tmp_path)
    first = application.update(operation_identity="SPONSOR-UPDATE-001")
    before = first.workbook_path.read_bytes()
    # Force a changed source boundary without changing production code paths.
    original_project = application.project
    monkeypatch.setattr(application, "project", lambda **kwargs: original_project(**kwargs))
    monkeypatch.setattr(application.store, "current_receipt", lambda month: None)
    monkeypatch.setattr(application.store, "publish_receipt", lambda receipt: (_ for _ in ()).throw(OSError("disk fault")))

    try:
        application.update(operation_identity="SPONSOR-UPDATE-FAIL")
    except OSError as error:
        assert str(error) == "disk fault"
    else:
        raise AssertionError("failure must remain visible")
    assert first.workbook_path.read_bytes() == before
    assert len(application.store.records("WO12_LOCAL_PUBLICATION_FAILURE_V1")) == 1


def test_corrupt_canonical_workbook_is_deterministically_rebuilt(tmp_path) -> None:
    application, _ = _application(tmp_path)
    first = application.update(operation_identity="SPONSOR-UPDATE-001")
    original = first.workbook_path.read_bytes()
    first.workbook_path.write_bytes(b"corrupt")

    rebuilt = application.update(operation_identity="SPONSOR-REBUILD-002")

    assert rebuilt.outcome == "RECOVERED_CANONICAL_WORKBOOK"
    assert rebuilt.receipt_identity == first.receipt_identity
    assert rebuilt.workbook_path.read_bytes() == original
    assert rebuilt.workbook_sha256 == first.workbook_sha256
    assert len(application.store.records("WO12_DAILY_PACKAGE_V1")) == 1
    assert application.open_current("2026_08")[2] == first.receipt_identity


def test_exact_wo09_wo10_wo11_lineage_projects_without_recalculation(tmp_path, monkeypatch) -> None:
    from tests.unit.intraday.test_wo11_lifecycle_application import (
        emit, fixture,
    )
    from kronos.intraday.probables import ProbableState

    lifecycle, handoff, _, _, clock, capability, _ = fixture(tmp_path / "lineage", monkeypatch)
    current = lifecycle.action(handoff_identity=handoff.identity, action="ACTIVATE_PAPER", action_identity="ARM")
    clock[0] += timedelta(minutes=5)
    lifecycle.pulse()
    current = lifecycle.store.restore()[0]
    clock[0] += timedelta(seconds=1)
    current = emit(lifecycle, capability, clock, current, str(Decimal(current.data["intake"]["entry"]) + 1))
    clock[0] += timedelta(seconds=1)
    emit(lifecycle, capability, clock, current, str(Decimal(current.data["intake"]["target"]) + 1))

    readiness = next(lifecycle.futures.wo09.load_readiness(path.stem)
                     for path in lifecycle.futures.wo09.readiness.glob("*.json"))
    result = SimpleNamespace(
        state=ProbableState.LONG_PROBABLE, canonical_subject_identity=readiness.canonical_subject_identity,
        market_session_identity=readiness.session_identity, result_identity=readiness.probable_result_identity,
        analysis_boundary=readiness.analysis_boundary, direction=SimpleNamespace(value=readiness.direction),
    )
    run = SimpleNamespace(analysis_boundary=readiness.analysis_boundary,
                          run_identity=readiness.probables_run_identity, results=(result,))
    research = IntradayResearchApplication(
        probables=_Probables(tmp_path / "lineage-probables", run),
        wo09=lifecycle.futures.wo09,
        futures=lifecycle.futures.store,
        lifecycle=lifecycle.store,
        store=ResearchStore(tmp_path / "lineage-research"),
        publication_root=tmp_path / "lineage-publication",
        clock=lambda: clock[0],
    )
    projection = research.project(ensure_origins=True)
    opportunity = dict(zip(OPPORTUNITY_COLUMNS, projection.opportunities[0], strict=True))
    assert projection.tracks, opportunity
    track = dict(zip(TRACK_COLUMNS, projection.tracks[0], strict=True))

    assert opportunity["wo09_highest_satisfied_count"] == 5
    assert opportunity["wo09_first_five_of_five_at"] is not None
    assert opportunity["setup_family"] == "INTRADAY_PULLBACK_CONTINUATION"
    assert opportunity["future_entry"] is not None and opportunity["future_oi"] is not None
    assert opportunity["wo10_selected_lots_context"] == 25
    assert opportunity["wo11_sponsor_action"] == "ACTIVATE_PAPER"
    assert opportunity["day_state"] == "FINALIZED"
    assert opportunity["discovery_to_three_seconds"] is not None
    assert opportunity["sponsor_decision_to_wo11_action_seconds"] is not None
    assert track["truth_class"] == "PAPER_POSITION" and track["model_lots"] == 1
    assert track["model_r"] is not None and track["eligible_sample_count"] > 0
    assert any(row[3] == "WO11_LIFECYCLE_EVENT" for row in projection.events)
