from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_discovery_operation import (
    DiscoveryOperationFailure,
    DiscoveryOperationState,
)
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_probables_v2_control import (
    IntradayProbablesV2OperationalControl,
)
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION,
    PROBABLES_V2_CORRECTION_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_CORRECTION_PUBLICATION_IDENTITY,
    PROBABLES_V2_PUBLICATION_IDENTITY,
)
from kronos.intraday.completed_evidence import (
    EvidenceSessionRole,
    IntradayAnalysisPhase,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import DiscoveryReason
from kronos.intraday.discovery_runtime import DiscoveryMemberFactError
from kronos.intraday.discovery_source import _completed_intraday
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.refresh_v2 import (
    REFRESH_V2_OPERATION_TYPE,
    REFRESH_V2_REQUEST_IDENTITY,
    REFRESH_V2_REQUEST_VERSION,
    RefreshV2Outcome,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.application.test_intraday_discovery_operation import (
    SEMANTIC_BOUNDARY,
    _authenticate,
    _configured_shared,
    _request_at,
)


IST = ZoneInfo("Asia/Kolkata")


def _refresh_native_fixture(application, fixture):
    _, facts, mapping, run = fixture
    return application.refresh_analysis(
        source_discovery_run_identity=run.source_discovery_run_identity,
        universe_identity=run.universe_identity, universe_version=run.universe_version,
        reconciliation_identity=run.reconciliation_identity,
        reconciliation_version=run.reconciliation_version,
        market_session_identity=run.market_session_identity, analysis_boundary=run.analysis_boundary,
        member_evidence=(mapping,), unavailable_members=(), provenance=('ISOLATED',), native_facts=(facts,))


def test_conflicting_member_completes_native_companion_before_probables_publication(tmp_path):
    import json
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from tests.unit.intraday.test_native_pullback_decision import source_fixture, BOUNDARY
    fixture = source_fixture('CONFLICTING')
    native = NativeStructuralStore(tmp_path / 'native')
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    publisher = NativePullbackPublication(native, clock=lambda: BOUNDARY, commissioned_at=BOUNDARY)
    run = _refresh_native_fixture(IntradayProbablesV2Application(store=store, native_selection=publisher), fixture)
    assert store.load_current_run() == run
    assert len(run.results) == 1
    result, = run.results
    assert (result.direction.value, result.state.value) == ('CONFLICTING', 'NOT_ADMITTED')
    assert [r.value for r in result.reasons] == ['DIRECTION_CONFLICTING']
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    assert manifest['result_identities'] == [result.result_identity]
    decision = native.load(manifest['selections'][0])
    assert (decision.data['direction'], decision.data['result'], decision.data['reasons']) == (
        'CONFLICTING', 'NOT_ESTABLISHED', ['SOURCE_DIRECTION_MISMATCH'])


@pytest.mark.parametrize('failure', ['integrity', 'persistence'])
def test_native_errors_preserve_previous_complete_probables_publication(tmp_path, monkeypatch, failure):
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.application.intraday_native_selection import NativePullbackPublication
    import kronos.application.intraday_native_selection as publication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from tests.unit.intraday.test_native_pullback_decision import source_fixture, BOUNDARY
    native = NativeStructuralStore(tmp_path / 'native')
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    publisher = NativePullbackPublication(native, clock=lambda: BOUNDARY, commissioned_at=BOUNDARY)
    app = IntradayProbablesV2Application(store=store, native_selection=publisher)
    previous = _refresh_native_fixture(app, source_fixture())
    before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    original = publication.retain_decision

    def damaged(store, source, **kwargs):
        return original(store, {**source, 'unexpected': True}, **kwargs)

    def unwritable(*args, **kwargs):
        raise OSError('ISOLATED_NATIVE_PERSISTENCE_FAILURE')

    if failure == 'integrity':
        monkeypatch.setattr(publication, 'retain_decision', damaged)
    else:
        monkeypatch.setattr(native, 'retain', unwritable)
    with pytest.raises(RuntimeError, match='PROBABLES_V2_REFRESH_FAILED') as error:
        _refresh_native_fixture(app, source_fixture('CONFLICTING'))
    assert isinstance(error.value.__cause__, ValueError if failure == 'integrity' else OSError)
    assert store.load_current_run() == previous
    assert before == {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert len(tuple((native.root / 'runs').glob('*.json'))) == 1


def _payload(
    identity: str = "V2-CONTROL-ONE",
    *,
    boundary: datetime = SEMANTIC_BOUNDARY,
) -> dict[str, str]:
    serialized_boundary = boundary.isoformat()
    return {
        "request_identity": identity,
        "observation_boundary": serialized_boundary,
        "request_created_at": serialized_boundary,
        "source_class": "SPONSOR_BROWSER_CONTROL",
        "contract_identity": REFRESH_V2_REQUEST_IDENTITY,
        "contract_version": REFRESH_V2_REQUEST_VERSION,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_CORRECTION_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_CORRECTION_METHODOLOGY_CHECKSUM,
        "operation_type": REFRESH_V2_OPERATION_TYPE,
    }


def _control(
    tmp_path: Path,
    *,
    authenticated: bool = True,
    boundary: datetime = SEMANTIC_BOUNDARY,
):  # type: ignore[no-untyped-def]
    shared, _, factory_calls, provider_requests = _configured_shared()
    if authenticated:
        _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    )
    control = IntradayProbablesV2OperationalControl(
        composition.discovery_v2_operation,
        composition.probables_v2_application,
        composition.refresh_v2_provenance_store,
        clock=lambda: boundary,
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    return shared, composition, control, factory_calls, provider_requests


def test_exact_v2_binding_rejects_before_provider_acquisition(tmp_path: Path) -> None:
    _, _, control, factory_calls, provider_requests = _control(
        tmp_path, authenticated=False
    )
    wrong = {**_payload(), "methodology_checksum": "WRONG"}

    result = control.execute_document(wrong)

    assert result["outcome"] == RefreshV2Outcome.REJECTED.value
    assert result["failure"] == "INTRADAY_PROBABLES_V2_METHODOLOGY_BINDING_INVALID"
    assert factory_calls == []
    assert provider_requests == [0]


def test_success_is_append_only_reloadable_and_idempotent(tmp_path: Path) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path)
    request = _payload()

    first = control.execute_document(request)
    reads = provider_requests[0]
    duplicate = control.execute_document(request)
    retained = composition.refresh_v2_provenance_store.load_for_request(
        request["request_identity"]
    )

    assert first["outcome"] == "SUCCESS"
    assert first["resulting_discovery_identity"]
    assert first["resulting_probables_identity"]
    assert duplicate == {**first, "idempotent": True}
    assert provider_requests == [reads]
    assert retained is not None
    assert retained.provenance_identity == first["provenance_identity"]
    assert retained.outcome is RefreshV2Outcome.SUCCESS
    assert retained.remote_address_class == "LOOPBACK_ADMITTED"
    assert retained.origin_validation == "PASSED_BY_SHARED_BROWSER_ADMISSION"
    assert "token" not in repr(retained).lower()


def test_same_identity_different_content_fails_closed(tmp_path: Path) -> None:
    _, _, control, _, provider_requests = _control(tmp_path)
    request = _payload()
    control.execute_document(request)
    reads = provider_requests[0]
    conflict = {
        **request,
        "observation_boundary": request["observation_boundary"].replace("11:17", "11:18"),
    }

    result = control.execute_document(conflict)

    assert result["outcome"] == "REJECTED"
    assert result["failure"] == "INTRADAY_PROBABLES_V2_REQUEST_IDENTITY_CONFLICT"
    assert provider_requests == [reads]


def test_v1_and_v2_pointers_are_version_isolated(tmp_path: Path) -> None:
    _, composition, control, _, _ = _control(tmp_path)
    v1_pointer = tmp_path / "refresh-v1" / "current-state.json"
    v2_pointer = tmp_path / "refresh-v2" / "CURRENT-PROBABLES-V2.json"

    v2 = control.execute_document(_payload())
    assert v2["outcome"] == "SUCCESS"
    assert not v1_pointer.exists()
    v2_bytes = v2_pointer.read_bytes()

    v1 = composition.discovery_operation.execute(
        _request_at("LEGACY-V1-ISOLATION", SEMANTIC_BOUNDARY)
    )
    assert v1.state is DiscoveryOperationState.COMPLETE
    assert v1_pointer.exists()
    assert v2_pointer.read_bytes() == v2_bytes


def test_active_v2_refresh_rejects_concurrent_v1_before_second_provider_read(
    tmp_path: Path,
) -> None:
    blocked, proceed = Event(), Event()
    shared, _, _, provider_requests = _configured_shared(
        block=blocked,
        proceed=proceed,
    )
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: SEMANTIC_BOUNDARY,
    )
    control = IntradayProbablesV2OperationalControl(
        composition.discovery_v2_operation,
        composition.probables_v2_application,
        composition.refresh_v2_provenance_store,
        clock=lambda: SEMANTIC_BOUNDARY,
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    outcomes: list[dict[str, object]] = []
    thread = Thread(
        target=lambda: outcomes.append(
            control.execute_document(_payload("V2-CONCURRENCY-ACTIVE"))
        )
    )
    thread.start()
    assert blocked.wait(timeout=3)

    v1 = composition.discovery_operation.execute(
        _request_at("V1-CONCURRENT-WITH-V2", SEMANTIC_BOUNDARY)
    )

    assert v1.state is DiscoveryOperationState.CONFLICT
    assert v1.failure is DiscoveryOperationFailure.OPERATION_CONFLICT
    assert provider_requests == [1]

    proceed.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(outcomes) == 1 and outcomes[0]["outcome"] == "SUCCESS"
    assert provider_requests == [465]


def test_failed_later_v2_preserves_last_success(tmp_path: Path) -> None:
    shared, composition, control, _, provider_requests = _control(tmp_path)
    success = control.execute_document(_payload("V2-SUCCESS"))
    reads = provider_requests[0]
    shared.invalidate("CONTROLLED_TEST_CONTEXT_LOSS")

    failed = control.execute_document(_payload("V2-AFTER-LOSS"))
    snapshot = composition.probables_v2_application.snapshot()

    assert failed["outcome"] == "FAILED"
    assert failed["failure"] == "CONTEXT_UNAVAILABLE"
    assert provider_requests == [reads]
    assert snapshot.last_successful_run_identity == success["resulting_probables_identity"]
    assert snapshot.current_failure is None


def test_v2_execution_produces_v2_only(tmp_path: Path) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path)

    result = control.execute_document(_payload())
    v2 = composition.probables_v2_application.snapshot()

    assert result["outcome"] == "SUCCESS"
    assert v2.run is not None
    assert v2.run.methodology.methodology_identity == PROBABLES_V2_METHODOLOGY_IDENTITY
    assert v2.run.methodology.methodology_version == PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION
    assert composition.probables_application.snapshot().run is None
    assert composition.discovery_operation.last_result is None
    assert provider_requests == [465]


def test_v2_opening_allows_zero_completed_current_hour_and_restores_exactly(
    tmp_path: Path,
) -> None:
    boundary = datetime(2026, 8, 24, 9, 35, tzinfo=IST)
    shared, composition, control, _, provider_requests = _control(
        tmp_path,
        boundary=boundary,
    )

    result = control.execute_document(_payload("V2-OPENING-ZERO-1H", boundary=boundary))
    run = composition.probables_v2_application.snapshot().run

    assert result["outcome"] == "SUCCESS"
    assert run is not None
    retained_result = next(
        item for item in run.results if item.source_mapping_identity is not None
    )
    mapping = ProbablesV2Store(tmp_path.resolve()).load_mapping(
        retained_result.source_mapping_identity
    )
    assert mapping.phase is IntradayAnalysisPhase.OPENING
    assert mapping.completed_evidence.candles(
        IntradayTimeframe.ONE_HOUR,
        EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY,
    ) == ()
    assert len(mapping.completed_evidence.candles(
        IntradayTimeframe.ONE_HOUR,
        EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT,
    )) >= 2
    reads = provider_requests[0]

    restored = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    ).probables_v2_application.snapshot().run

    assert restored == run
    assert provider_requests == [reads]


def test_current_hour_empty_set_is_v2_only_and_missing_completed_hour_fails_closed() -> None:
    trading_day = date(2026, 8, 24)
    opened = datetime.combine(trading_day, time(9, 15), IST)
    schedule = MarketDaySchedule(
        exchange="NSE",
        trading_date=trading_day,
        session_id="NSE:2026-08-24:REGULAR",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            opens_at=opened,
            closes_at=datetime.combine(trading_day, time(15, 30), IST),
        ),),
        source_identity="KRONOS-MARKET-CALENDAR-V1/TEST",
        source_version="1",
    )
    opening_boundary = datetime.combine(trading_day, time(9, 35), IST)
    forming = HistoricalCandle(opened, 100.0, 102.0, 99.0, 101.0, 1000)

    assert _completed_intraday(
        candles=(forming,),
        schedule=schedule,
        timeframe=IntradayTimeframe.ONE_HOUR,
        observed_at=opening_boundary,
        allow_domain008_empty=True,
    ) == ()

    with pytest.raises(DiscoveryMemberFactError) as legacy_error:
        _completed_intraday(
            candles=(forming,),
            schedule=schedule,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observed_at=opening_boundary,
        )
    assert legacy_error.value.reason is DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE

    first_completed_boundary = datetime.combine(trading_day, time(10, 20), IST)
    with pytest.raises(DiscoveryMemberFactError) as missing_error:
        _completed_intraday(
            candles=(),
            schedule=schedule,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observed_at=first_completed_boundary,
            allow_domain008_empty=True,
        )
    assert missing_error.value.reason is DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE


@pytest.mark.parametrize('case', ['missing_binding', 'missing_facts'])
def test_conflicting_fallback_completes_native_and_probables_publication(tmp_path, case):
    import json
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from kronos.intraday.native_pullback_decision import load_decision_source
    from tests.unit.intraday.test_native_pullback_decision import conflicting_fallback_fixture, BOUNDARY
    fixture, facts, bundles, reason = conflicting_fallback_fixture(case)
    _, _, mapping, original = fixture
    native = NativeStructuralStore(tmp_path / 'native')
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    publisher = NativePullbackPublication(native, clock=lambda: BOUNDARY, commissioned_at=BOUNDARY)
    app = IntradayProbablesV2Application(store=store, native_selection=publisher)
    run = app.refresh_analysis(
        source_discovery_run_identity=original.source_discovery_run_identity,
        universe_identity=original.universe_identity, universe_version=original.universe_version,
        reconciliation_identity=original.reconciliation_identity,
        reconciliation_version=original.reconciliation_version,
        market_session_identity=original.market_session_identity, analysis_boundary=original.analysis_boundary,
        member_evidence=(mapping,), unavailable_members=(), provenance=('ISOLATED',),
        native_facts=facts, native_bundles=bundles)
    assert run.results == original.results and store.load_current_run() == run
    result, = run.results
    assert (result.direction.value, result.state.value) == ('CONFLICTING', 'NOT_ADMITTED')
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    assert manifest['result_identities'] == [result.result_identity]
    assert len(manifest['selections']) == 1
    decision = NativeStructuralStore(native.root).load(manifest['selections'][0])
    assert (decision.data['direction'], decision.data['result'], decision.data['reasons']) == (
        'CONFLICTING', 'NOT_ESTABLISHED', [reason])
    assert load_decision_source(native, decision, None)['failure'] == reason
    before = {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}
    assert publisher.publish(run, (mapping,), facts=facts, bundles=bundles,
                             newly_published=True) == (decision,)
    assert before == {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case', ['missing_binding', 'missing_facts'])
@pytest.mark.parametrize('failure', ['integrity', 'persistence'])
def test_conflicting_fallback_does_not_suppress_integrity_or_storage_errors(tmp_path, monkeypatch, case, failure):
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.application.intraday_native_selection import NativePullbackPublication
    import kronos.application.intraday_native_selection as publication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from tests.unit.intraday.test_native_pullback_decision import source_fixture, conflicting_fallback_fixture, BOUNDARY
    native = NativeStructuralStore(tmp_path / 'native')
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    publisher = NativePullbackPublication(native, clock=lambda: BOUNDARY, commissioned_at=BOUNDARY)
    app = IntradayProbablesV2Application(store=store, native_selection=publisher)
    previous = _refresh_native_fixture(app, source_fixture())
    before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    fixture, facts, bundles, _ = conflicting_fallback_fixture(case)
    _, _, mapping, original = fixture
    retain = publication.retain_decision
    def damaged(store, source, **kwargs):
        return retain(store, {**source, 'unexpected': True}, **kwargs)
    def unwritable(*args, **kwargs):
        raise OSError('ISOLATED_FALLBACK_PERSISTENCE_FAILURE')
    if failure == 'integrity':
        monkeypatch.setattr(publication, 'retain_decision', damaged)
    else:
        monkeypatch.setattr(native, 'retain', unwritable)
    with pytest.raises(RuntimeError, match='PROBABLES_V2_REFRESH_FAILED') as error:
        app.refresh_analysis(
            source_discovery_run_identity=original.source_discovery_run_identity,
            universe_identity=original.universe_identity, universe_version=original.universe_version,
            reconciliation_identity=original.reconciliation_identity,
            reconciliation_version=original.reconciliation_version,
            market_session_identity=original.market_session_identity, analysis_boundary=original.analysis_boundary,
            member_evidence=(mapping,), unavailable_members=(), provenance=('ISOLATED',),
            native_facts=facts, native_bundles=bundles)
    assert isinstance(error.value.__cause__, ValueError if failure == 'integrity' else OSError)
    assert store.load_current_run() == previous
    assert before == {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert len(tuple((native.root / 'runs').glob('*.json'))) == 1


def _refresh_mcx_binding_fixture(app, fixture):
    _, facts, mapping, original, _, bundle = fixture
    return app.refresh_analysis(
        source_discovery_run_identity=original.source_discovery_run_identity,
        universe_identity=original.universe_identity, universe_version=original.universe_version,
        reconciliation_identity=original.reconciliation_identity,
        reconciliation_version=original.reconciliation_version,
        market_session_identity=original.market_session_identity, analysis_boundary=original.analysis_boundary,
        member_evidence=(mapping,), unavailable_members=(), provenance=('ISOLATED',),
        native_facts=(facts,), native_bundles=(bundle,))


@pytest.mark.parametrize('family', ['GOLDM', 'SILVERM', 'COPPER', 'CRUDE', 'NATGAS'])
def test_canonical_mcx_binding_closes_native_companion_and_probables(tmp_path, family):
    import json
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from kronos.intraday.native_pullback_decision import load_decision_source
    from tests.unit.intraday.test_native_pullback_mcx import _publication_fixture
    publisher, native, bindings, *fixture = _publication_fixture(tmp_path, family)
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    app = IntradayProbablesV2Application(store=store, native_selection=publisher)
    run = _refresh_mcx_binding_fixture(app, fixture)
    assert store.load_current_run() == run
    assert run.results == fixture[3].results
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    assert manifest['result_identities'] == [r.result_identity for r in run.results]
    decision = NativeStructuralStore(native.root).load(manifest['selections'][0])
    assert load_decision_source(native, decision, None) == fixture[0]
    assert decision.data['exact_contract'] == fixture[4].active_binding.derivative_contract_id
    assert decision.data['roll_lineage'] == fixture[4].binding_identity
    if family == 'NATGAS':
        assert run.results[0].execution_eligibility != 'ELIGIBLE'
        assert decision.data['result'] == 'NOT_ESTABLISHED'


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'integrity'])
def test_mcx_binding_store_failure_preserves_previous_complete_probables_pointer(tmp_path, failure):
    import json
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.instrument.active_derivative import ActiveDerivativeSelectionError
    from tests.unit.intraday.test_native_pullback_decision import source_fixture
    from tests.unit.intraday.test_native_pullback_mcx import _publication_fixture
    publisher, native, bindings, *fixture = _publication_fixture(tmp_path)
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    app = IntradayProbablesV2Application(store=store, native_selection=publisher)
    previous = _refresh_native_fixture(app, source_fixture())
    before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    manifests = {p: p.read_bytes() for p in (native.root / 'runs').glob('*.json')}
    path = bindings.path_for(fixture[4].binding_identity)
    if failure == 'missing': path.unlink()
    elif failure == 'corrupt': path.write_bytes(b'{')
    else:
        raw = json.loads(path.read_bytes())
        raw['integrity_identity'] = 'WRONG'
        path.write_text(json.dumps(raw))
    with pytest.raises(RuntimeError, match='PROBABLES_V2_REFRESH_FAILED') as error:
        _refresh_mcx_binding_fixture(app, fixture)
    assert isinstance(error.value.__cause__, ActiveDerivativeSelectionError)
    assert str(error.value.__cause__) == ('ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE'
        if failure == 'missing' else 'ACTIVE_DERIVATIVE_BINDING_INTEGRITY_INVALID')
    assert app.snapshot().run == previous and store.load_current_run() == previous
    assert before == {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert manifests == {p: p.read_bytes() for p in (native.root / 'runs').glob('*.json')}
    assert native.bound_identity(fixture[2].semantic_evidence.evidence_identity) is None


@pytest.mark.parametrize('case', ['zero', 'multiple'])
def test_missing_or_ambiguous_mcx_lookup_is_bounded_negative_complete_publication(tmp_path, case):
    import json
    from types import SimpleNamespace
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.intraday.wo10_native_adapter import adapt_native
    from tests.unit.intraday.test_native_pullback_mcx import _publication_fixture, _lookup_bundle
    publisher, native, _, _, _, _, _, binding, _ = _publication_fixture(tmp_path)
    identities = ('UNRELATED',) if case == 'zero' else (
        binding.binding_identity, 'ACTIVE-DERIVATIVE-BINDING-' + 'a' * 64)
    fixture = _lookup_bundle('CRUDE', identities)
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    run = _refresh_mcx_binding_fixture(IntradayProbablesV2Application(
        store=store, native_selection=publisher), fixture)
    assert store.load_current_run() == run and run.results == fixture[3].results
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    decision = native.load(manifest['selections'][0])
    assert decision.data['reasons'] == ['MCX_CONTRACT_BINDING_INVALID']
    assert decision.data['cycle'] is None and decision.data['roles'] == {}
    assert decision.data['target_manifest'] is None and decision.data['exact_contract'] is None
    # Loader-only handoff-shaped probe grants no WO09 authority.
    handoff = SimpleNamespace(canonical_subject_identity=decision.data['subject'], direction=decision.data['direction'])
    with pytest.raises(ValueError, match='TARGET_POPULATION_INCOMPLETE'):
        adapt_native(decision, handoff, None, None, now=run.analysis_boundary)


def test_authentic_discovery_bundle_closes_all_98_native_and_probables_members(tmp_path):
    import json
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from kronos.intraday.native_pullback_decision import load_decision_source, decode_source
    from kronos.intraday.probables_v2_refresh import map_discovery_execution_to_probables_v2
    from tests.unit.intraday.test_discovery_source import _composition
    from tests.unit.intraday.test_discovery_runtime import _publications
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    boundary = datetime(2026, 8, 26, 11, 17, tzinfo=IST)
    # The shared fixture is a local fake capability; no network/Provider acquisition.
    execution, _, _, _, _ = _composition(tmp_path / 'discovery', observed_at=boundary,
        active_mcx=True, retain_mcx=True)
    _, reconciliation = _publications()
    mapped = map_discovery_execution_to_probables_v2(execution=execution, reconciliation=reconciliation)
    bindings = ActiveDerivativeBindingStore((tmp_path / 'bindings').resolve())
    for binding in _resolve(boundary).successful_bindings: bindings.retain(binding)
    native = NativeStructuralStore(tmp_path / 'native')
    publisher = NativePullbackPublication(native, clock=lambda: boundary,
        commissioned_at=boundary, binding_store=bindings)
    store = ProbablesV2Store((tmp_path / 'probables').resolve())
    original = execution.run
    run = IntradayProbablesV2Application(store=store, native_selection=publisher).refresh_analysis(
        source_discovery_run_identity=original.run_identity, universe_identity=original.universe_identity,
        universe_version=original.universe_version, reconciliation_identity=original.reconciliation_identity,
        reconciliation_version=original.reconciliation_version, market_session_identity=original.market_session_identity,
        analysis_boundary=boundary, member_evidence=mapped.member_evidence,
        unavailable_members=mapped.unavailable_members, provenance=('ISOLATED_DISCOVERY_02B',),
        native_facts=execution.probables_v2_facts, native_bundles=execution.bundles)
    assert len(run.results) == 98 and store.load_current_run() == run
    assert len(mapped.member_evidence) == 98 and not mapped.unavailable_members
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    assert manifest['result_identities'] == [r.result_identity for r in run.results]
    assert len(manifest['selections']) == 98
    decisions = [NativeStructuralStore(native.root).load(i) for i in manifest['selections']]
    mcx = [d for d in decisions if d.data['subject'].startswith('MCX-')]
    assert {d.data['subject'] for d in mcx} == {'MCX-SUBJECT-' + f for f in ('CRUDE', 'COPPER', 'GOLDM', 'SILVERM', 'NATGAS')}
    for decision in mcx:
        source = load_decision_source(native, decision, None)
        facts, mapping, result, binding = decode_source(source)
        assert 'failure' not in source
        assert binding.canonical_subject_id == decision.data['subject']
        assert decision.data['exact_contract'] == binding.active_binding.derivative_contract_id
        assert decision.data['roll_lineage'] == binding.binding_identity
        assert binding.domain008_session_identity == facts.current_schedule.session_id
        assert binding.binding_identity in source['machine_bundle']['fields']['source_identities']['$tuple']
        assert 'MCX_CONTRACT_BINDING_INVALID' not in decision.data['reasons']
        assert native.bound_identity(mapping.semantic_evidence.evidence_identity) == decision.identity
        if decision.data['subject'] == 'MCX-SUBJECT-NATGAS':
            assert result.execution_eligibility != 'ELIGIBLE'
            assert decision.data['result'] == 'NOT_ESTABLISHED'
