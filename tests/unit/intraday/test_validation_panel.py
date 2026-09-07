from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.visual_identity import (
    VisualIdentityResolver, VisualIdentityRelationshipStatus,
    VisualIdentitySourceContext, create_visual_identity_relationship,
    create_visual_identity_publication,
)
from kronos.intraday import validation as v
from kronos.intraday.contracts import (
    GovernedCandle, CandleBoundary, CandleCompletion, ObservationBoundary,
    SourceProvenance, governed_candle_identity, IntradayTimeframe,
)
from kronos.intraday.validation_persistence import LocalSlice3VValidationStore
from kronos.market.calendar import MarketCalendarPublisher

IST = ZoneInfo("Asia/Kolkata")
AT = datetime(2026, 9, 4, 12, tzinfo=IST)
PAYLOAD = b"isolated chart fixture; not real market validation"
SUBJECT = "NSE-EQ-RBLBANK"
LABEL = "RBL Bank Ltd"
S = v.ValidationState
O = v.FactObservability


def resolver(subject=SUBJECT, label=LABEL, ambiguous=False):
    def relationship(source):
        return create_visual_identity_relationship(
            canonical_subject_identity=subject, observed_visible_subject_identity=label,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=AT - timedelta(days=10), effective_through=AT + timedelta(days=10),
            status=VisualIdentityRelationshipStatus.ACTIVE, source_identity=source,
            provenance=("WO-02B-ISOLATED-FIXTURE",), supersedes=None,
        )
    return VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=(subject,), publication_version="1.0.0",
        effective_from=AT - timedelta(days=10), effective_through=AT + timedelta(days=10),
        source_identities=("WO-02B-ISOLATED-FIXTURE",), provenance=("WO-02B",),
        relationships=(relationship("one"), relationship("two")) if ambiguous else (relationship("one"),),
        supersedes=None,
    ))


def candle(calendar, day, timeframe, subject=SUBJECT):
    schedule = calendar.instrument_session_profile("NSE", day, canonical_instrument_id=subject, observed_at=AT).continuous_trading
    start = schedule.windows[0].window_open
    end = schedule.windows[-1].window_close if timeframe is IntradayTimeframe.DAILY else start + timeframe.duration
    boundary = CandleBoundary(day, schedule.session_identity, timeframe, start, end)
    values = tuple(Decimal(x) for x in ("100", "110", "90", "105"))
    provenance = SourceProvenance("FIXTURE", "ISOLATED-CANDLE", AT, "1")
    return GovernedCandle(
        governed_candle_identity(canonical_instrument_id=subject, boundary=boundary, values=values, volume=1000, provenance=provenance),
        subject, boundary, *values, 1000, CandleCompletion.COMPLETE,
        ObservationBoundary(AT), provenance,
    )


def fixture(timeframe=IntradayTimeframe.FIFTEEN_MINUTES, subject=SUBJECT, label=LABEL):
    calendar = MarketCalendarPublisher()
    current = candle(calendar, date(2026, 9, 3) if timeframe is IntradayTimeframe.DAILY else AT.date(), timeframe, subject)
    previous = candle(calendar, date(2026, 9, 3), IntradayTimeframe.DAILY, subject)
    sources = (v.PanelSource("panel", "CURRENT-MACHINE-SOURCE", current),
               v.PanelSource("previous", "PREVIOUS-MACHINE-SOURCE", previous))
    requirements = tuple(v.RequiredPanelFact(key, "previous" if key.startswith(("previous.", "pivot.", "cpr.")) else "panel",
                                               relational_permitted=key.startswith("structure."))
                         for key, _ in v.PANEL_REQUIRED_FACTS)
    facts = tuple(v.MachineFact(question, key,
                  v.FactualValueKind.RELATION if key.startswith("structure.") else v.FactualValueKind.NUMERIC,
                  "inside" if key.startswith("structure.") else (
                      getattr(current if key.startswith("candle.") else previous, {"pdh": "high", "pdl": "low"}.get(key.split(".")[1], key.split(".")[1]))
                      if key.startswith(("candle.", "previous.")) else Decimal("100")),
                  v.DiscrepancyFamily.OTHER_GOVERNED_FACTUAL_DISCREPANCY)
                  for key, question in v.PANEL_REQUIRED_FACTS)
    machine = v.MachineEvidence("MACHINE-EVIDENCE", "MACHINE-RUN", subject, label, "NSE", AT.date(),
                                timeframe, AT, AT + timedelta(minutes=1), facts)
    request = v.PanelValidationRequest(machine, "CHART-REVISION-001", sha256(PAYLOAD).hexdigest(),
                 AT + timedelta(minutes=2), "panel", sources, requirements, ("WO-02B-ISOLATED",))
    times = []
    for source in sources:
        b = source.candle.boundary
        times.append(v.ObservedPanelTime(source.context_key, b.trading_date, calendar.instrument_session_profile("NSE", b.trading_date, canonical_instrument_id=subject, observed_at=AT).continuous_trading.session_type, "Asia/Kolkata",
                                         b.timeframe, b.start, b.end, CandleCompletion.COMPLETE))
    observations = tuple(v.PanelFactObservation(f.fact_key, O.RELATIONAL if f.value_kind is v.FactualValueKind.RELATION else O.EXACT,
                                                f.value_kind, f.value) for f in facts)
    visual = v.PanelVisualObservation(label, "NSE", timeframe, AT + timedelta(minutes=1),
                                      AT + timedelta(minutes=3), tuple(times), observations)
    return request, visual, calendar


def compare(request=None, visual=None, *, identity=None, payload=PAYLOAD, revision="CHART-REVISION-001"):
    base, observation, calendar = fixture()
    return v.validate_panel(request or base, visual or observation, chart_payload=payload,
              bound_chart_revision_identity=revision, identity_resolver=identity or resolver(),
              calendar=calendar, compared_at=AT + timedelta(minutes=4))


def change_fact(visual, key, **changes):
    return replace(visual, facts=tuple(replace(f, **changes) if f.fact_key == key else f for f in visual.facts))


def change_time(visual, context="panel", **changes):
    return replace(visual, temporal_contexts=tuple(replace(t, **changes) if t.context_key == context else t
                                                  for t in visual.temporal_contexts))


@pytest.mark.parametrize("timeframe", tuple(IntradayTimeframe))
def test_all_timeframes_and_lawful_previous_session(timeframe):
    request, visual, calendar = fixture(timeframe)
    record = v.validate_panel(request, visual, chart_payload=PAYLOAD, bound_chart_revision_identity=request.chart_revision_identity,
                             identity_resolver=resolver(), calendar=calendar, compared_at=AT + timedelta(minutes=4))
    assert record.overall is S.VALIDATED
    assert record.coverage is v.RequiredFactCoverage.COMPLETE
    assert len(record.fact_results) == 30
    assert record.answer_import is S.NOT_VALIDATED
    assert record.visual_reliability is S.NOT_VALIDATED
    assert record.temporal_results[1].schedule.trading_date < request.machine.trading_date
    assert record.request.sources[1].candle.candle_id == request.sources[1].candle.candle_id


@pytest.mark.parametrize("subject,label", [
    ("NSE-INDEX-NIFTY", "Nifty 50 Index"), ("NSE-INDEX-BANKNIFTY", "Nifty Bank Index"),
    ("NSE-EQ-EICHERMOT", "Exact governed equity label"),
])
def test_generic_equity_index_and_governed_alias(subject, label):
    request, visual, calendar = fixture(subject=subject, label=label)
    record = v.validate_panel(request, visual, chart_payload=PAYLOAD, bound_chart_revision_identity=request.chart_revision_identity,
                             identity_resolver=resolver(subject, label), calendar=calendar, compared_at=AT + timedelta(minutes=4))
    assert record.visual_identity_state is S.VALIDATED
    assert record.visual_identity.canonical_subject_identity == subject


@pytest.mark.parametrize("label", ["Wrong instrument", "rbl bank ltd", "RBL Bank Ltd ", "RBLBANK"])
def test_wrong_or_unavailable_identity_fails_closed(label):
    request, visual, _ = fixture()
    record = compare(request, replace(visual, observed_subject=label))
    assert record.file_identity is S.VALIDATED
    assert record.visual_identity_state is S.NOT_VALIDATED
    assert record.factual_correspondence is S.NOT_VALIDATED


def test_ambiguous_and_foreign_identity_fail_closed():
    assert compare(identity=resolver(ambiguous=True)).visual_identity_failure.endswith("AMBIGUOUS")
    assert compare(identity=resolver("NSE-EQ-FOREIGN")).visual_identity_state is S.NOT_VALIDATED


@pytest.mark.parametrize("field,value", [
    ("session", "WRONG-SESSION"), ("trading_date", date(2026, 9, 3)),
    ("timezone", "UTC"), ("candle_end", AT + timedelta(days=1)),
    ("candle_start", AT - timedelta(hours=1)), ("timeframe", IntradayTimeframe.FIVE_MINUTES),
])
def test_temporal_mismatches(field, value):
    request, visual, _ = fixture()
    record = compare(request, change_time(visual, **{field: value}))
    assert record.temporal_results[0].result is S.NOT_VALIDATED
    assert record.overall is S.NOT_VALIDATED


@pytest.mark.parametrize("field", ["session", "trading_date", "timezone", "candle_start", "candle_end", "completion"])
def test_missing_temporal_proof_is_unverifiable(field):
    request, visual, _ = fixture()
    record = compare(request, change_time(visual, **{field: None}))
    assert record.temporal_results[0].result is S.UNVERIFIABLE
    assert record.fact_results[0].result is S.UNVERIFIABLE


def test_missing_capture_time_and_incomplete_candle_are_unverifiable():
    request, visual, _ = fixture()
    assert compare(request, replace(visual, chart_captured_at=None)).temporal_correspondence is S.UNVERIFIABLE
    assert compare(request, change_time(visual, completion=CandleCompletion.INCOMPLETE)).temporal_results[0].result is S.UNVERIFIABLE
    assert compare(request, replace(visual, temporal_contexts=())).factual_correspondence is S.UNVERIFIABLE


def test_machine_future_or_incomplete_candle_cannot_validate():
    request, visual, _ = fixture()
    source = request.sources[0]
    early = source.candle.boundary.start
    incomplete = replace(source.candle, observation_boundary=ObservationBoundary(early), completion=CandleCompletion.INCOMPLETE)
    altered = replace(request, sources=(replace(source, candle=incomplete), request.sources[1]))
    assert compare(altered, visual).temporal_results[0].result is S.UNVERIFIABLE
    altered = replace(request, machine=replace(request.machine, observation_boundary=early))
    assert compare(altered, visual).temporal_results[0].result is S.UNVERIFIABLE


@pytest.mark.parametrize("key", [k for k, _ in v.PANEL_REQUIRED_FACTS])
def test_each_required_fact_exact_or_relational_mismatch(key):
    request, visual, _ = fixture()
    old = next(f for f in visual.facts if f.fact_key == key)
    changed = change_fact(visual, key, value="outside" if old.value_kind is v.FactualValueKind.RELATION else Decimal("999"))
    record = compare(request, changed)
    row = next(r for r in record.fact_results if r.fact_key == key)
    assert row.result is S.NOT_VALIDATED
    assert record.factual_correspondence is S.NOT_VALIDATED


@pytest.mark.parametrize("observability", [O.NOT_VISIBLE, O.UNVERIFIABLE, O.APPROXIMATE])
@pytest.mark.parametrize("key", ["candle.close", "pivot.p", "cpr.lower", "volume.participation"])
def test_unobservable_and_approximate_never_exact(key, observability):
    request, visual, _ = fixture()
    changed = change_fact(visual, key, observability=observability,
                          value=Decimal("100") if observability is O.APPROXIMATE else None,
                          value_kind=v.FactualValueKind.NUMERIC if observability is O.APPROXIMATE else None)
    record = compare(request, changed)
    assert next(r for r in record.fact_results if r.fact_key == key).result is S.UNVERIFIABLE
    assert record.factual_correspondence is S.PARTIALLY_VALIDATED


def test_relational_permission_and_unobservable_structure():
    request, visual, _ = fixture()
    requirements = tuple(replace(r, relational_permitted=False) if r.fact_key == "structure.range" else r for r in request.required_facts)
    assert compare(replace(request, required_facts=requirements), visual).factual_correspondence is S.NOT_VALIDATED
    changed = change_fact(visual, "structure.range", observability=O.NOT_VISIBLE, value_kind=None, value=None)
    assert compare(request, changed).factual_correspondence is S.PARTIALLY_VALIDATED


def test_previous_source_session_mismatch_blocks_pivots_and_cpr():
    request, visual, _ = fixture()
    record = compare(request, change_time(visual, "previous", session="FOREIGN"))
    assert all(r.result is S.NOT_VALIDATED for r in record.fact_results if r.context_key == "previous")
    assert record.fact_results[0].result is S.VALIDATED


def test_all_partial_zero_missing_required_and_subset_request():
    request, visual, _ = fixture()
    partial = compare(request, replace(visual, facts=visual.facts[:1]))
    assert partial.coverage is v.RequiredFactCoverage.PARTIAL
    assert partial.factual_correspondence is S.PARTIALLY_VALIDATED
    assert sum(r.disposition is v.FactDisposition.MISSING for r in partial.fact_results) == 29
    zero = compare(request, replace(visual, facts=()))
    assert zero.coverage is v.RequiredFactCoverage.NONE
    assert zero.factual_correspondence is S.UNVERIFIABLE
    with pytest.raises(ValueError):
        replace(request, required_facts=request.required_facts[:1])
    machine_subset = compare(replace(request, machine=replace(request.machine, facts=request.machine.facts[:1])), visual)
    assert machine_subset.factual_correspondence is S.PARTIALLY_VALIDATED
    assert machine_subset.coverage is v.RequiredFactCoverage.PARTIAL
    assert sum(r.reason == "MACHINE_FACT_UNAVAILABLE" for r in machine_subset.fact_results) == 29


def test_not_applicable_requires_machine_authority_and_never_fabricates_value():
    request, visual, _ = fixture()
    changed = change_fact(visual, "cpr.width", observability=O.NOT_APPLICABLE, value_kind=None, value=None)
    assert compare(request, changed).factual_correspondence is S.NOT_VALIDATED
    required = tuple(replace(r, applicable=False, applicability_provenance="GOVERNED-FACT-UNAVAILABLE")
                     if r.fact_key == "cpr.width" else r for r in request.required_facts)
    record = compare(replace(request, required_facts=required), changed)
    assert record.coverage is v.RequiredFactCoverage.COMPLETE
    assert record.factual_correspondence is S.VALIDATED
    for state in (O.NOT_VISIBLE, O.UNVERIFIABLE, O.NOT_APPLICABLE):
        with pytest.raises(ValueError, match="VALUE_PROHIBITED"):
            v.PanelFactObservation("candle.close", state, v.FactualValueKind.NUMERIC, Decimal("1"))


@pytest.mark.parametrize("changes", [{"payload": b"different"}, {"revision": "CHART-REVISION-002"}])
def test_file_and_visual_identity_are_separate(changes):
    record = compare(**changes)
    assert record.file_identity is S.NOT_VALIDATED
    assert record.visual_identity_state is S.VALIDATED
    assert record.factual_correspondence is S.NOT_VALIDATED


def test_persistence_exact_linkage_restore_idempotency_and_tamper(tmp_path):
    record = compare()
    store = LocalSlice3VValidationStore(tmp_path)
    store.retain_panel_record(record)
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("*.json")}
    store.retain_panel_record(record)
    restored = LocalSlice3VValidationStore(tmp_path).load_panel_record(validation_record_identity=record.validation_record_identity)
    assert restored == record
    assert before == {p.name: p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert restored.request.machine.run_identity == "MACHINE-RUN"
    assert restored.request.chart_payload_sha256 == sha256(PAYLOAD).hexdigest()
    assert restored.visual_identity.relationship_integrity_identity
    assert restored.temporal_results[0].schedule.provenance
    path = next(tmp_path.rglob("*.json"))
    document = json.loads(path.read_bytes())
    document["fields"]["request"]["fields"]["chart_revision_identity"] = "TAMPERED"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        store.load_panel_record(validation_record_identity=record.validation_record_identity)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.retain_panel_record(record)


@pytest.mark.parametrize("identity", ["../escape", "/tmp/escape", "SLICE3V-PANEL-RECORD-no", ""])
def test_load_identity_cannot_traverse(tmp_path, identity):
    with pytest.raises(ValueError):
        LocalSlice3VValidationStore(tmp_path).load_panel_record(validation_record_identity=identity)


def test_legacy_answer_cannot_be_upgraded_and_unproven_chart_stays_unverifiable(tmp_path):
    legacy = tmp_path / "old-review.json"
    legacy.write_text('{"schema_identity":"KRONOS-INTRADAY-REVIEW-V2","answers":[]}')
    before = legacy.read_bytes()
    with pytest.raises(ValueError):
        v.panel_validation_from_document(json.loads(before))
    request, visual, _ = fixture()
    record = compare(request, replace(visual, temporal_contexts=(), chart_captured_at=None))
    assert record.overall is S.UNVERIFIABLE
    assert record.coverage is v.RequiredFactCoverage.COMPLETE  # Observations supplied; time still unproven.
    LocalSlice3VValidationStore(tmp_path).retain_panel_record(record)
    assert legacy.read_bytes() == before


def test_observer_contract_has_no_machine_or_analytical_authority():
    _, visual, _ = fixture()
    document = v._panel_encode(visual)
    fields = document["fields"]
    assert not set(fields) & {"direction", "readiness", "promotion", "canonical_instrument_id",
                               "run_identity", "machine_evidence_identity", "chart_revision_identity"}
    assert "1H" in {t.value for t in IntradayTimeframe}
    request, _, _ = fixture()
    with pytest.raises(ValueError):
        replace(request, machine=replace(request.machine, exchange="MCX"))


def test_duplicate_contexts_facts_and_revision_integrity_reject():
    request, visual, _ = fixture()
    with pytest.raises(ValueError):
        replace(visual, facts=visual.facts + visual.facts[:1])
    with pytest.raises(ValueError):
        replace(visual, temporal_contexts=visual.temporal_contexts + visual.temporal_contexts[:1])
    with pytest.raises(ValueError):
        replace(request, chart_payload_sha256="bad")
    record = compare()
    with pytest.raises(ValueError):
        replace(record, overall=S.NOT_VALIDATED)


def test_wrong_governed_previous_source_cannot_validate_even_if_observer_agrees():
    request, visual, calendar = fixture()
    older = candle(calendar, date(2026, 9, 2), IntradayTimeframe.DAILY)
    request = replace(request, sources=(request.sources[0], replace(request.sources[1], candle=older)))
    schedule = calendar.instrument_session_profile("NSE", older.boundary.trading_date,
        canonical_instrument_id=SUBJECT, observed_at=AT).continuous_trading
    visual = change_time(visual, "previous", trading_date=older.boundary.trading_date,
        session=schedule.session_type, candle_start=older.boundary.start, candle_end=older.boundary.end)
    record = compare(request, visual)
    assert record.temporal_results[1].result is S.VALIDATED
    assert all(r.reason == "PREVIOUS_SESSION_SOURCE_MISMATCH" for r in record.fact_results if r.context_key == "previous")
    assert record.overall is S.NOT_VALIDATED


def test_machine_ohlc_cannot_be_rebound_to_different_source_values():
    request, visual, _ = fixture()
    facts = tuple(replace(f, value=Decimal("999")) if f.fact_key == "candle.close" else f for f in request.machine.facts)
    request = replace(request, machine=replace(request.machine, facts=facts))
    visual = change_fact(visual, "candle.close", value=Decimal("999"))
    record = compare(request, visual)
    assert next(r.reason for r in record.fact_results if r.fact_key == "candle.close") == "MACHINE_SOURCE_FACT_MISMATCH"


def test_unavailable_session_and_capture_chronology_do_not_pass():
    request, visual, calendar = fixture()
    class MissingCalendar:
        def instrument_session_profile(self, *args, **kwargs):
            raise ValueError("MARKET_SESSION_APPLICABILITY_UNAVAILABLE")
        def publication(self, exchange):
            return calendar.publication(exchange)
    record = v.validate_panel(request, visual, chart_payload=PAYLOAD,
        bound_chart_revision_identity=request.chart_revision_identity, identity_resolver=resolver(),
        calendar=MissingCalendar(), compared_at=AT + timedelta(minutes=4))
    assert record.overall is S.UNVERIFIABLE
    assert compare(request, replace(visual, chart_captured_at=AT + timedelta(minutes=4))).overall is S.UNVERIFIABLE
    with pytest.raises(ValueError, match="CHRONOLOGY"):
        compare(request, replace(visual, answered_at=AT))


def test_partial_record_restores_and_unknown_version_is_rejected(tmp_path):
    request, visual, _ = fixture()
    record = compare(request, replace(visual, facts=visual.facts[:2]))
    store = LocalSlice3VValidationStore(tmp_path)
    store.retain_panel_record(record)
    assert store.load_panel_record(validation_record_identity=record.validation_record_identity) == record
    with pytest.raises(ValueError):
        replace(visual, contract_version="1.0.0")
    with pytest.raises(ValueError):
        replace(request, required_facts=tuple(replace(f, context_key="previous") if f.fact_key == "candle.close" else f
                                             for f in request.required_facts))


def test_all_not_visible_has_zero_coverage_without_invented_values():
    request, visual, _ = fixture()
    visual = replace(visual, facts=tuple(v.PanelFactObservation(f.fact_key, O.NOT_VISIBLE) for f in visual.facts))
    record = compare(request, visual)
    assert record.coverage is v.RequiredFactCoverage.NONE
    assert record.overall is S.UNVERIFIABLE
    assert all(r.disposition is v.FactDisposition.NOT_VISIBLE for r in record.fact_results)


def test_relationship_cannot_masquerade_as_exact_observation():
    with pytest.raises(ValueError, match="RELATIONAL_PRECISION_REQUIRED"):
        v.PanelFactObservation("structure.range", O.EXACT, v.FactualValueKind.RELATION, "inside")


def test_source_observed_after_freeze_rejects():
    request, _, _ = fixture()
    source = request.sources[0]
    with pytest.raises(ValueError, match="PANEL_REQUEST"):
        replace(request, sources=(replace(source, candle=replace(source.candle,
            observation_boundary=ObservationBoundary(AT + timedelta(days=1)))), request.sources[1]))


def test_invalid_decimal_restoration_is_bounded():
    doc = v.panel_validation_document(compare())
    doc["fields"]["visual"]["fields"]["facts"][0]["fields"]["value"]["value"] = "not-a-number"
    with pytest.raises(ValueError, match="PANEL_DOCUMENT_INVALID"):
        v.panel_validation_from_document(doc)
