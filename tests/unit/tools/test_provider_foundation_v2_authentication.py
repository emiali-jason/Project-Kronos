import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.models.authentication import AuthenticationAttemptState
from tools.provider_pilots import provider_foundation_v2_authentication as auth
from tools.provider_pilots.provider_foundation_v2_historical_proof import (
    SanitizedHistoricalProof,
    SanitizedLiveSnapshotProof,
    SanitizedResolutionProof,
)


def test_authentication_entry_point_has_same_process_market_data_but_no_order_path() -> None:
    source = inspect.getsource(auth)

    assert "execute_historical_proof" in source
    assert "execute_live_snapshot_proof" in source
    assert "instrument_records" not in source
    assert "historical_candles" not in source
    assert "market_data.quote(" not in source
    assert "market_data.ltp(" not in source
    assert "market_data.ohlc(" not in source
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source


def test_success_invokes_historical_proof_with_exact_retained_provider(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    captured: list[object] = []
    proofs = (
        SanitizedHistoricalProof(
            instrument="RELIANCE",
            status="PASS",
            interval="60minute",
            candle_count=2,
            first_timestamp=datetime(2026, 8, 7, 4, 0, tzinfo=UTC),
            last_timestamp=datetime(2026, 8, 7, 5, 0, tzinfo=UTC),
        ),
    )

    def execute(received_provider, *, now):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, now))
        return proofs

    monkeypatch.setattr(auth, "execute_historical_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert rendered[0].read_only_capability == "ACTIVE"
    assert rendered[0].instrument_master == "PASS"
    assert rendered[0].historical_proofs is proofs
    assert "Instrument Master: PASS" in rendered[0].render()
    assert "RELIANCE: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_live_mode_invokes_snapshot_proof_with_exact_retained_provider(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    captured: list[object] = []
    proofs = (
        SanitizedLiveSnapshotProof(
            instrument="RELIANCE",
            quote="PASS",
            ltp="PASS",
            ohlc="PASS",
            quote_value="last=100.0",
            ltp_value="last=100.0",
            ohlc_value="last=100.0 | ohlc=99.0/101.0/98.0/98.5",
        ),
    )

    def execute(received_provider, *, now, quote_only):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, now, quote_only))
        return proofs

    monkeypatch.setattr(auth, "execute_live_snapshot_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = True
    window._quote_only_proof = False
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert captured[2] is False
    assert rendered[0].read_only_capability == "ACTIVE"
    assert rendered[0].instrument_master == "PASS"
    assert rendered[0].historical_proofs == ()
    assert rendered[0].live_snapshot_proofs is proofs
    assert "Quote: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_equity_quote_mode_invokes_batch_with_exact_retained_provider(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    symbols = ("ADANIENT", "RELIANCE")
    captured: list[object] = []
    proofs = (
        SanitizedLiveSnapshotProof("ADANIENT", "PASS", "NOT RUN", "NOT RUN"),
        SanitizedLiveSnapshotProof("RELIANCE", "PASS", "NOT RUN", "NOT RUN"),
    )

    def execute(received_provider, *, symbols, now):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, symbols, now))
        return proofs

    monkeypatch.setattr(auth, "execute_equity_quote_batch_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = symbols
    window._mcx_symbols = ()
    window._live_snapshot_proof = True
    window._quote_only_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert captured[1] is symbols
    assert rendered[0].live_snapshot_proofs is proofs
    assert rendered[0].historical_proofs == ()
    assert capsys.readouterr().out == ""


def test_sanitized_success_evidence_contains_no_provider_material() -> None:
    evidence = auth.SanitizedAuthenticationEvidence(
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "ACTIVE",
    )

    assert evidence.render().splitlines() == [
        "Kite authentication: PASS",
        "Browser login: PASS",
        "Loopback callback: PASS",
        "Session exchange: PASS",
        "Principal verification: PASS",
        "Read-only capability: ACTIVE",
        "Secrets exposed: NO",
        "Order capability exposed: NO",
        "Order operations: 0",
    ]


def test_universe_mode_uses_same_retained_provider_without_market_data(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    proofs = (SanitizedResolutionProof("RELIANCE", "PASS", "RELIANCE"),)
    captured: list[object] = []

    def execute(received_provider, *, universe, now):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe, now))
        return proofs

    monkeypatch.setattr(auth, "execute_universe_resolution_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].historical_proofs == ()
    assert rendered[0].live_snapshot_proofs == ()
    assert rendered[0].resolution_proofs is proofs
    assert "RELIANCE: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_daily_dataset_mode_uses_same_retained_provider_and_sanitized_evidence(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    daily_proof = SimpleNamespace(render=lambda: "READY: 98/98")
    captured: list[object] = []

    def execute(received_provider, *, universe, now):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe, now))
        return daily_proof

    monkeypatch.setattr(auth, "execute_swing_daily_dataset_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = False
    window._swing_daily_dataset_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].historical_proofs == ()
    assert rendered[0].resolution_proofs == ()
    assert rendered[0].daily_dataset_proof is daily_proof
    assert "READY: 98/98" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_market_assessment_mode_uses_same_retained_provider_and_sanitized_evidence(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    market_proof = SimpleNamespace(render=lambda: "Setup assessments: 196/196")
    captured: list[object] = []

    def execute(received_provider, *, universe, now):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe, now))
        return market_proof

    monkeypatch.setattr(auth, "execute_swing_market_assessment_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = False
    window._swing_daily_dataset_proof = False
    window._swing_market_assessment_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].historical_proofs == ()
    assert rendered[0].resolution_proofs == ()
    assert rendered[0].daily_dataset_proof is None
    assert rendered[0].market_assessment_proof is market_proof
    assert "Setup assessments: 196/196" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_candidate_validation_mode_uses_same_retained_provider_and_sanitized_evidence(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    proof = SimpleNamespace(render=lambda: "Stage 5: PASS")
    captured: list[object] = []

    def execute(received_provider, *, universe):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe))
        return proof

    monkeypatch.setattr(auth, "execute_swing_candidate_validation_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = False
    window._swing_daily_dataset_proof = False
    window._swing_market_assessment_proof = False
    window._swing_candidate_validation_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].candidate_validation_proof is proof
    assert rendered[0].market_assessment_proof is None
    assert "Stage 5: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_trade_plan_mode_uses_same_retained_provider_and_sanitized_evidence(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    proof = SimpleNamespace(render=lambda: "Stage 7 Trade Plan proof: PASS")
    captured: list[object] = []

    def execute(received_provider, *, universe):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe))
        return proof

    monkeypatch.setattr(auth, "execute_swing_trade_plan_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = False
    window._swing_daily_dataset_proof = False
    window._swing_market_assessment_proof = False
    window._swing_candidate_validation_proof = False
    window._swing_trade_plan_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].trade_plan_proof is proof
    assert rendered[0].candidate_validation_proof is None
    assert "Stage 7 Trade Plan proof: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""


def test_candidate_ranking_mode_uses_same_retained_provider_and_sanitized_evidence(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    capability = SimpleNamespace(active=True)

    class _Provider:
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            assert attempt is expected_attempt
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
                callback_consumed=True,
                failure_code=None,
            )

        def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
            return capability

    provider = _Provider()
    expected_attempt = object()
    proof = SimpleNamespace(render=lambda: "Stage 8 Candidate Ranking proof: PASS")
    captured: list[object] = []

    def execute(received_provider, *, universe):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe))
        return proof

    monkeypatch.setattr(auth, "execute_swing_candidate_ranking_proof", execute)
    rendered: list[auth.SanitizedAuthenticationEvidence] = []
    window = object.__new__(auth._AuthenticationWindow)
    window._provider = provider
    window._attempt = expected_attempt
    window._equity_symbols = ()
    window._mcx_symbols = ()
    window._live_snapshot_proof = False
    window._quote_only_proof = False
    window._universe_resolution_proof = False
    window._swing_daily_dataset_proof = False
    window._swing_market_assessment_proof = False
    window._swing_candidate_validation_proof = False
    window._swing_trade_plan_proof = False
    window._swing_candidate_ranking_proof = True
    window._root = SimpleNamespace(after=lambda _delay, callback: callback())
    window._finish = rendered.append

    window._complete()

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert rendered[0].candidate_ranking_proof is proof
    assert rendered[0].trade_plan_proof is None
    assert "Stage 8 Candidate Ranking proof: PASS" in rendered[0].render()
    assert capsys.readouterr().out == ""



# PF-02A: exercise the factory imported by the real browser launcher. Only the
# external configuration, credential, listener, adapter and browser boundaries
# are replaced; the Provider, authentication service, shared runtime,
# application and durable admission are the actual production owners.
def _ordinary_production_connection(
    tmp_path,
    monkeypatch,
    *,
    configuration_hook=lambda: None,
    opener_hook=lambda: None,
    application_arguments=None,
    monotonic_now=None,
    navigator=None,
    callback_return_url="http://127.0.0.1:8947/swing/opportunities",
):
    from kronos.application import swing_opportunities as application_module
    from kronos.provider.contracts.provider_authentication import (
        ReadOnlyProviderOperation,
    )
    from kronos.provider.kite.auth import kite_authentication as kite_auth_module
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    from tests.unit.provider.test_connection_governance import governance
    from tests.unit.provider.test_provider_authentication_service import (
        _Harness,
        _NOW,
    )
    from tools import kronos_browser
    from tools.provider_pilots import provider_foundation_v2_historical_proof as proof

    # _Harness supplies external fakes only. Its separately prepared service is
    # deliberately unused: the production factory must construct the service.
    harness = _Harness()
    harness.adapter.dispose_count = 0

    def dispose_adapter():
        harness.adapter.dispose_count += 1

    # This external fake explicitly satisfies cleanup. Separate fault cases
    # remove/fail it so resolved-worker truth cannot hide retained resources.
    harness.adapter.dispose_local = dispose_adapter
    monotonic_now = [0.0] if monotonic_now is None else monotonic_now
    wall_now = [_NOW]
    jobs = []
    events = []
    restored = []
    listener_arguments = []

    class FixedWallClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return wall_now[0] if tz is None else wall_now[0].astimezone(tz)

    monkeypatch.setattr(proof, "datetime", FixedWallClock)
    monkeypatch.setattr(kite_auth_module, "datetime", FixedWallClock)
    monkeypatch.setattr(application_module.time, "monotonic", lambda: monotonic_now[0])

    connection_governance = governance(tmp_path, clock=lambda: wall_now[0])

    def read_records():
        return [
            connection_governance.store.read(path.name)
            for path in connection_governance.store.root.iterdir()
            if path.is_dir() and len(path.name) == 32
        ]

    def configuration(*, deadline=None):
        # This check establishes that actual durable admission precedes the
        # production configuration/construction boundary under test.
        rows = read_records()
        assert len(rows) == 1
        assert rows[0]["admission"]["state"] == "ACCEPTED"
        events.append("configuration")
        configuration_hook()
        return harness.configuration

    def open_browser(url):
        # Retain real KiteLoginNavigator validation of the real adapter URL.
        assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"
        events.append("opener")
        opener_hook()
        return True

    monkeypatch.setattr(proof, "load_provider_authentication_configuration", configuration)
    monkeypatch.setattr(
        proof, "AppleKeychainCredentialSource", lambda **_arguments: harness.credentials
    )
    monkeypatch.setattr(
        proof,
        "AppleKeychainIntendedPrincipalResolver",
        lambda **_arguments: harness.resolver,
    )
    monkeypatch.setattr(
        proof, "create_kite_authentication_adapter",
        lambda api_key, **_worker_options: harness.service_arguments["adapter_factory"](api_key)
    )
    def listener(**arguments):
        listener_arguments.append(arguments)
        return harness.listener

    monkeypatch.setattr(proof, "LoopbackAuthenticationCallbackListener", listener)
    from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
    monkeypatch.setattr(proof, "KiteLoginNavigator", lambda: KiteLoginNavigator(opener=open_browser))

    assert kronos_browser._build_provider is proof._build_provider
    provider_factory = lambda: kronos_browser._build_provider(
        navigator=navigator,
        callback_return_url=callback_return_url,
    )
    shared = SharedAuthenticatedProviderRuntime(
        provider_factory,
        provider_identity="KITE",
        clock=lambda: wall_now[0],
        connection_governance=connection_governance,
    )
    application = application_module.SwingOpportunitiesApplication(
        lambda: shared.compatibility_facade(
            consumer_identity="SWING",
            operations=frozenset(ReadOnlyProviderOperation),
        ),
        clock=lambda: wall_now[0],
        connection_governance=connection_governance,
        background_runner=lambda operation, name: jobs.append((name, operation)),
        **(application_arguments or {}),
    )
    application.register_sponsor_operability_restorer(restored.append)
    return SimpleNamespace(
        app=application,
        shared=shared,
        harness=harness,
        governance=connection_governance,
        monotonic_now=monotonic_now,
        wall_now=wall_now,
        jobs=jobs,
        events=events,
        restored=restored,
        records=read_records,
        listener_arguments=listener_arguments,
    )


def _run_ordinary_connection(case):
    assert case.app.connect_provider(
        action_reference=case.governance.action_reference("HEADER"),
        request_route="/provider/connect",
    )
    assert case.monotonic_now == [0.0]
    assert len(case.jobs) == 1
    name, authenticate = case.jobs.pop(0)
    assert name == "kronos-browser-auth"
    authenticate()
    # Dispatch the actual application restoration callback if one was wrongly
    # scheduled after late success; the final assertion must detect that too.
    while case.jobs:
        name, operation = case.jobs.pop(0)
        assert name == "kronos-browser-restoration"
        operation()


def _assert_ordinary_expiration_rejects_publication(case):
    records = case.records()
    assert len(records) == 1
    observed = {
        "application": case.app.snapshot().provider_state.value,
        "exposed_capability": case.app.authenticated_read_only_capability() is not None,
        "retained_capability": case.shared.read_only_status()["capability_state"],
        "durable_completion": records[0].get("completion", {}).get("state"),
        "restorations": len(case.restored),
    }
    assert observed == {
        "application": "ERROR",
        "exposed_capability": False,
        "retained_capability": "ABSENT",
        "durable_completion": "FAILURE",
        "restorations": 0,
    }


def test_ordinary_production_factory_cannot_publish_after_construction_uses_total_allowance(
    tmp_path, monkeypatch
):
    case = _ordinary_production_connection(
        tmp_path,
        monkeypatch,
        configuration_hook=lambda: case.monotonic_now.__setitem__(0, 331.0),
    )
    try:
        _run_ordinary_connection(case)
        assert case.events[0] == "configuration"
        assert case.monotonic_now == [331.0]
        _assert_ordinary_expiration_rejects_publication(case)
    finally:
        case.app.close()


def test_production_factory_passes_trusted_callback_return_destination(
    tmp_path, monkeypatch
):
    destination = "http://127.0.0.1:9123/swing/opportunities"
    case = _ordinary_production_connection(
        tmp_path,
        monkeypatch,
        callback_return_url=destination,
    )
    try:
        _run_ordinary_connection(case)
        assert len(case.listener_arguments) == 1
        assert case.listener_arguments[0]["return_url"] == destination
    finally:
        case.app.close()


def test_ordinary_production_factory_cannot_publish_after_browser_uses_total_allowance(
    tmp_path, monkeypatch
):
    case = _ordinary_production_connection(
        tmp_path,
        monkeypatch,
        opener_hook=lambda: case.monotonic_now.__setitem__(0, 331.0),
    )
    try:
        _run_ordinary_connection(case)
        assert case.events == ["configuration", "opener"]
        assert case.harness.listener.start_count == 1
        assert case.monotonic_now == [331.0]
        _assert_ordinary_expiration_rejects_publication(case)
    finally:
        case.app.close()


class _ManualConnectionTimer:
    """Deterministic scheduling seam; firing does not pretend to stop workers."""

    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        # An already queued callback can run after cancellation. Deliberately
        # allow it so committed-success and superseded-generation races run.
        self.callback()


def _timed_production_connection(
    tmp_path,
    monkeypatch,
    *,
    timeout_seconds=10.0,
    configuration_hook=lambda: None,
    opener_hook=lambda: None,
    navigator=None,
):
    now = [0.0]
    timers = []

    def timer_factory(seconds, callback):
        timer = _ManualConnectionTimer(seconds, callback)
        timers.append(timer)
        return timer

    case = _ordinary_production_connection(
        tmp_path,
        monkeypatch,
        configuration_hook=configuration_hook,
        opener_hook=opener_hook,
        monotonic_now=now,
        navigator=navigator,
        application_arguments={
            "connection_timeout_seconds": timeout_seconds,
            "connection_monotonic_clock": lambda: now[0],
            "connection_timer_factory": timer_factory,
        },
    )
    # The original fake listener assumes the historical five-minute lifetime.
    # This fake boundary records shorter ordinary deadlines without replacing
    # the actual service that determines them.
    case.listener_deadlines = []

    def receive_once(*, deadline):
        case.listener_deadlines.append(deadline)
        case.harness.listener.receive_count += 1
        return case.harness.callback

    case.harness.listener.receive_once = receive_once
    case.timers = timers
    return case


def _start_connection_worker(case):
    from threading import Thread

    assert case.app.connect_provider()
    assert len(case.jobs) == 1
    name, operation = case.jobs.pop(0)
    assert name == "kronos-browser-auth"
    errors = []

    def authenticate():
        try:
            operation()
        except BaseException as error:
            errors.append(error)

    thread = Thread(target=authenticate)
    thread.start()
    return thread, errors


def _install_blocked_exchange(case, entered, release):
    def exchange_once(request_token, api_secret):
        case.harness.adapter.exchange_count += 1

        def use_token(_token):
            def use_secret(_secret):
                entered.set()
                assert release.wait(5), "test exchange was not released"
                return case.harness.candidate

            return api_secret.reveal_for_call(use_secret)

        return request_token.consume_for_call(use_token)

    case.harness.adapter.exchange_once = exchange_once


def _assert_status_reads_finish_while_worker_blocked(case):
    from threading import Thread

    observations = []
    errors = []

    def status_reads():
        try:
            for _ in range(3):
                observations.append((
                    case.app.snapshot().provider_state.value,
                    dict(case.app.connection_attempt_status()),
                    case.shared.read_only_status(),
                ))
        except BaseException as error:
            errors.append(error)

    reader = Thread(target=status_reads)
    reader.start()
    reader.join(1)
    assert not reader.is_alive(), "status read waited for external authentication work"
    assert not errors
    assert len(observations) == 3
    assert observations[0] == observations[1] == observations[2]
    return observations[0]


import pytest


@pytest.mark.parametrize("phase", ["configuration", "opener", "exchange"])
def test_ordinary_production_timeout_retains_blocked_worker_and_fences_retry(
    tmp_path, monkeypatch, phase
):
    from threading import Event

    entered, release = Event(), Event()

    def block():
        entered.set()
        assert release.wait(5), "test external phase was not released"

    case = _timed_production_connection(
        tmp_path,
        monkeypatch,
        configuration_hook=block if phase == "configuration" else lambda: None,
        opener_hook=block if phase == "opener" else lambda: None,
    )
    if phase == "exchange":
        _install_blocked_exchange(case, entered, release)
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        active = case.app.connection_attempt_status()
        assert active["state"] == "ACTIVE"
        assert active["remaining_seconds"] == 10.0
        identity = active["request_identity"]
        assert identity is not None
        original_generation = active["generation"]
        original_timers = tuple(case.timers)
        assert original_timers and original_timers[0].started

        # Duplicate admission while active cannot reset the monotonic budget.
        case.monotonic_now[0] = 3.0
        assert not case.app.connect_provider()
        assert case.app.connection_attempt_status()["remaining_seconds"] == 7.0
        assert case.app.connection_attempt_status()["generation"] == original_generation
        assert tuple(case.timers) == original_timers
        _assert_status_reads_finish_while_worker_blocked(case)

        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        snapshot = case.app.connection_attempt_status()
        assert snapshot["state"] == "TIMED_OUT"
        assert snapshot["worker_active"] is True
        assert snapshot["cleanup_state"] == "PENDING"
        assert worker.is_alive(), "timer must not be evidence that blocking work stopped"
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.governance.store.read(identity)["completion"]["state"] == "FAILURE"
        assert case.app.authenticated_read_only_capability() is None
        assert case.shared.read_only_status()["capability_state"] != "RETAINED_UNEXPIRED"
        assert case.restored == []
        _assert_status_reads_finish_while_worker_blocked(case)

        for _ in range(3):
            assert not case.app.connect_provider()
            assert case.app.connection_attempt_status()["generation"] == original_generation
        assert case.jobs == []
        assert case.events.count("configuration") == 1
        assert tuple(case.timers) == original_timers

        release.set()
        worker.join(2)
        assert not worker.is_alive()
        assert not errors
        resolved = case.app.connection_attempt_status()
        assert resolved["state"] == "TIMED_OUT"
        assert resolved["worker_active"] is False
        assert resolved["cleanup_state"] == "COMPLETE"
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.app.authenticated_read_only_capability() is None
        assert case.governance.store.read(identity)["completion"]["state"] == "FAILURE"
        assert case.jobs == [] and case.restored == []
        if phase == "exchange":
            assert case.harness.candidate.dispose_count == 1
            assert case.harness.candidate.capability_issue_count == 0
            assert case.harness.credentials.lease.close_count == 1
            assert case.harness.callback.token.close_count == 1
        elif phase == "opener":
            assert case.harness.adapter.exchange_count == 0
            assert case.harness.listener.close_count == 1

        # Only the now-resolved generation permits a new explicit admission.
        case.monotonic_now[0] = 25.0
        assert case.app.connect_provider()
        retried = case.app.connection_attempt_status()
        assert retried["state"] == "ACTIVE"
        assert retried["generation"] > original_generation
        assert retried["request_identity"] != identity
        assert retried["remaining_seconds"] == 10.0
        assert len(case.jobs) == 1
        assert case.events.count("configuration") == 1  # retry is queued only
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()


def test_ordinary_production_construction_reduces_remaining_callback_allowance(
    tmp_path, monkeypatch
):
    from datetime import timedelta

    case = _timed_production_connection(
        tmp_path,
        monkeypatch,
        configuration_hook=lambda: case.monotonic_now.__setitem__(0, 8.0),
    )
    try:
        _run_ordinary_connection(case)
        assert case.app.snapshot().provider_state.value == "CONNECTED"
        assert len(case.listener_deadlines) == 1
        assert case.listener_deadlines[0] == case.wall_now[0] + timedelta(seconds=2)
        assert case.harness.adapter.exchange_count == 1
        assert case.app.connection_attempt_status()["state"] == "SUCCEEDED"
    finally:
        case.app.close()


def test_ordinary_production_committed_success_survives_late_timer_and_duplicate_connect(
    tmp_path, monkeypatch
):
    case = _timed_production_connection(tmp_path, monkeypatch)
    try:
        _run_ordinary_connection(case)
        retained = case.app.authenticated_read_only_capability()
        assert retained is not None and retained.active
        status = case.app.connection_attempt_status()
        assert status["state"] == "SUCCEEDED"
        identity, generation = status["request_identity"], status["generation"]
        assert case.governance.store.read(identity)["completion"]["state"] == "SUCCESS"
        assert len(case.restored) == 1
        timers = tuple(case.timers)
        assert timers
        case.monotonic_now[0] = 500.0
        for timer in timers:
            timer.fire()
        assert not case.app.connect_provider()
        assert case.app.snapshot().provider_state.value == "CONNECTED"
        assert case.app.authenticated_read_only_capability() is retained
        assert retained.active
        assert case.app.connection_attempt_status()["state"] == "SUCCEEDED"
        assert case.app.connection_attempt_status()["generation"] == generation
        assert case.governance.store.read(identity)["completion"]["state"] == "SUCCESS"
        assert case.events == ["configuration", "opener"]
        assert case.harness.adapter.exchange_count == 1
        assert case.harness.candidate.dispose_count == 0
        assert len(case.restored) == 1
        assert tuple(case.timers) == timers
    finally:
        case.app.close()


@pytest.mark.parametrize("wall_offset_days", [-30, 30])
def test_ordinary_production_wall_clock_change_does_not_extend_monotonic_allowance(
    tmp_path, monkeypatch, wall_offset_days
):
    from datetime import timedelta
    from threading import Event

    entered, release = Event(), Event()

    def block_opener():
        entered.set()
        assert release.wait(5), "test opener was not released"

    case = _timed_production_connection(tmp_path, monkeypatch, opener_hook=block_opener)
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        identity = case.app.connection_attempt_status()["request_identity"]
        case.wall_now[0] += timedelta(days=wall_offset_days)
        case.monotonic_now[0] = 9.0
        assert case.app.connection_attempt_status()["remaining_seconds"] == 1.0
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        assert case.app.connection_attempt_status()["state"] == "TIMED_OUT"
        assert case.app.connection_attempt_status()["remaining_seconds"] == 0.0
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.governance.store.read(identity)["completion"]["state"] == "FAILURE"
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert case.app.authenticated_read_only_capability() is None
        assert case.harness.adapter.exchange_count == 0
        assert case.harness.candidate.capability_issue_count == 0
        assert case.jobs == [] and case.restored == []
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()


@pytest.mark.parametrize("phase", ["configuration", "opener", "exchange"])
def test_ordinary_production_superseded_generation_cannot_publish_or_restore(
    tmp_path, monkeypatch, phase
):
    from threading import Event
    from tests.unit.provider.test_connection_governance import GENERATION

    entered, release = Event(), Event()

    def block():
        entered.set()
        assert release.wait(5), "test external phase was not released"

    case = _timed_production_connection(
        tmp_path,
        monkeypatch,
        configuration_hook=block if phase == "configuration" else lambda: None,
        opener_hook=block if phase == "opener" else lambda: None,
    )
    if phase == "exchange":
        _install_blocked_exchange(case, entered, release)
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        identity = case.app.connection_attempt_status()["request_identity"]
        case.app.enter_controlled_maintenance(GENERATION)
        case.monotonic_now[0] = 10.0
        for timer in tuple(case.timers):
            timer.fire()
        assert not case.app.connect_provider()
        assert case.app.authenticated_read_only_capability() is None
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert case.app.snapshot().provider_state.value != "CONNECTED"
        assert case.shared.read_only_status()["capability_state"] != "RETAINED_UNEXPIRED"
        assert case.app.authenticated_read_only_capability() is None
        assert case.restored == [] and case.jobs == []
        assert case.governance.store.read(identity).get("completion", {}).get("state") != "SUCCESS"
        if phase == "exchange":
            assert case.harness.candidate.dispose_count == 1
            assert case.harness.candidate.capability_issue_count == 0
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()



@pytest.mark.parametrize("cleanup_fault", ["adapter_missing", "adapter_raises", "listener_raises"])
def test_ordinary_production_returned_worker_does_not_hide_unresolved_cleanup(
    tmp_path, monkeypatch, cleanup_fault
):
    from threading import Event

    entered, release = Event(), Event()

    def block_opener():
        entered.set()
        assert release.wait(5), "test opener was not released"

    case = _timed_production_connection(tmp_path, monkeypatch, opener_hook=block_opener)

    def failed_disposal():
        raise RuntimeError("FAKE_LOCAL_RESOURCE_NOT_RELEASED")

    if cleanup_fault == "adapter_missing":
        case.harness.adapter.dispose_local = None
    elif cleanup_fault == "adapter_raises":
        case.harness.adapter.dispose_local = failed_disposal
    else:
        case.harness.listener.close = failed_disposal
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        generation = case.app.connection_attempt_status()["generation"]
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        assert case.app.snapshot().provider_state.value == "ERROR"
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        status = case.app.connection_attempt_status()
        assert status["state"] == "TIMED_OUT"
        assert status["worker_active"] is False
        assert status["cleanup_state"] == "PENDING"
        assert status["resources_pending"] is True
        assert status["unresolved_resources"]
        for _ in range(3):
            assert not case.app.connect_provider()
        assert case.app.connection_attempt_status()["generation"] == generation
        assert case.events == ["configuration", "opener"]
        assert case.jobs == [] and case.restored == []
        assert case.harness.adapter.exchange_count == 0
        assert case.app.authenticated_read_only_capability() is None
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()


def test_ordinary_production_five_minute_auth_limit_remains_stricter_than_total(
    tmp_path, monkeypatch
):
    from datetime import timedelta

    case = _timed_production_connection(
        tmp_path, monkeypatch, timeout_seconds=330.0,
        configuration_hook=lambda: case.monotonic_now.__setitem__(0, 20.0),
    )

    def callback_at_auth_expiration(*, deadline):
        case.listener_deadlines.append(deadline)
        case.harness.listener.receive_count += 1
        assert deadline == case.wall_now[0] + timedelta(minutes=5)
        # Only 320 total seconds have elapsed, but all 300 authentication
        # seconds have elapsed. The unused 10 total seconds cannot extend it.
        case.monotonic_now[0] = 320.0
        return case.harness.callback

    case.harness.listener.receive_once = callback_at_auth_expiration
    try:
        _run_ordinary_connection(case)
        assert len(case.listener_deadlines) == 1
        assert case.monotonic_now == [320.0]
        assert case.app.connection_attempt_status()["state"] == "TIMED_OUT"
        assert case.app.connection_attempt_status()["remaining_seconds"] == 0.0
        assert case.timers[-1].cancelled
        assert case.harness.credentials.acquire_count == 0
        assert case.harness.adapter.exchange_count == 0
        _assert_ordinary_expiration_rejects_publication(case)
    finally:
        case.app.close()


def test_ordinary_production_durable_completion_failure_releases_capability_but_bars_retry(
    tmp_path, monkeypatch
):
    case = _timed_production_connection(tmp_path, monkeypatch)
    completion_attempts = []
    original_result = case.governance.store.result

    def result(request, phase, state, at):
        if phase == "completion":
            completion_attempts.append((state, case.app.snapshot().provider_state.value))
            raise OSError("ISOLATED_COMPLETION_WRITE_FAILURE")
        return original_result(request, phase, state, at)

    monkeypatch.setattr(case.governance.store, "result", result)
    try:
        _run_ordinary_connection(case)
        assert completion_attempts == [("SUCCESS", "CONNECTED")]
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.app.authenticated_read_only_capability() is None
        assert case.shared.read_only_status()["capability_state"] != "RETAINED_UNEXPIRED"
        assert case.harness.candidate.dispose_count == 1
        assert case.restored == [] and case.jobs == []
        status = case.app.connection_attempt_status()
        assert status["worker_active"] is False
        assert status["cleanup_state"] == "PENDING"
        assert status["resources_pending"] is True
        assert "connection_completion" in status["unresolved_resources"]
        assert status["durable_completion"] == {
            "state": "FAILED", "disposition": "SUCCESS", "generation": 1,
        }
        assert status["restoration_readiness"] == {
            "state": "STALE", "ready": False, "generation": 1,
        }
        identity, generation = status["request_identity"], status["generation"]
        assert "completion" not in case.governance.store.read(identity)
        factory_count = case.events.count("configuration")
        for _ in range(3):
            assert not case.app.connect_provider()
        assert case.app.connection_attempt_status()["generation"] == generation
        assert case.events.count("configuration") == factory_count == 1
        assert case.jobs == []
    finally:
        case.app.close()


# PF-02B: the actual browser factory, service, Kite adapter and both client
# handle classes execute. Only the SDK/network boundary is replaced below;
# no fake adapter is given disposal behavior.
class _PF02BLocalSession:
    def __init__(self, close_error=None):
        self.close_error = close_error
        self.close_count = 0

    def close(self):
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


_PF02B_VALID_EXCHANGE = object()


class _PF02BKiteSDK:
    def __init__(
        self,
        *,
        api_key,
        debug,
        exchange_response=_PF02B_VALID_EXCHANGE,
        exchange_error=None,
        exchange_hook=lambda: None,
        profile_hook=lambda: None,
        close_error=None,
        principal="PRINCIPAL123",
    ):
        assert api_key == "service-api-key"
        assert debug is False
        self.api_key = api_key
        self.access_token = None
        self.reqsession = _PF02BLocalSession(close_error)
        self.exchange_response = exchange_response
        self.exchange_error = exchange_error
        self.exchange_hook = exchange_hook
        self.profile_hook = profile_hook
        self.principal = principal
        self.exchange_count = 0
        self.profile_count = 0
        self.remote_logout_count = 0
        self.expiry_hook = None

    def set_session_expiry_hook(self, hook):
        self.expiry_hook = hook

    def login_url(self):
        return "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"

    def generate_session(self, request_token, api_secret):
        assert request_token == "service-request-token"
        assert api_secret == "service-api-secret"
        self.exchange_count += 1
        self.exchange_hook()
        if self.exchange_error is not None:
            raise self.exchange_error
        if self.exchange_response is _PF02B_VALID_EXCHANGE:
            self.access_token = "pf02b-private-access-token"
            return {"access_token": self.access_token}
        return self.exchange_response

    def profile(self):
        self.profile_count += 1
        self.profile_hook()
        return {"user_id": self.principal}

    def invalidate_access_token(self):
        self.remote_logout_count += 1
        raise AssertionError("local disposal attempted remote logout")


def _pf02b_real_adapter_connection(
    tmp_path,
    monkeypatch,
    *,
    opener_hook=lambda: None,
    exchange_response=_PF02B_VALID_EXCHANGE,
    exchange_error=None,
    exchange_hook=lambda: None,
    profile_hook=lambda: None,
    close_error=None,
    principal="PRINCIPAL123",
):
    from kronos.provider.adapters.kite import authentication as kite_authentication
    from kronos.provider.adapters.kite import client as kite_client
    from tools.provider_pilots import provider_foundation_v2_historical_proof as proof

    case = _timed_production_connection(
        tmp_path, monkeypatch, opener_hook=opener_hook
    )
    case.sdks = []
    case.real_adapters = []
    case.real_services = []

    def create_sdk(**arguments):
        sdk = _PF02BKiteSDK(
            **arguments,
            exchange_response=exchange_response,
            exchange_error=exchange_error,
            exchange_hook=exchange_hook,
            profile_hook=profile_hook,
            close_error=close_error,
            principal=principal,
        )
        case.sdks.append(sdk)
        return sdk

    real_factory = kite_authentication.create_kite_authentication_adapter

    def create_adapter(*arguments, **keywords):
        # PF-02B/C/D deliberately qualify their in-parent SDK faults. PF-02E
        # separately restores the ordinary worker path with child-side SDKs.
        keywords.pop("use_sdk_worker", None)
        adapter = real_factory(*arguments, **keywords)
        assert type(adapter) is kite_authentication.KiteAuthenticationAdapter
        case.real_adapters.append(adapter)
        return adapter

    real_service = proof.ProviderAuthenticationService

    def create_service(*arguments, **keywords):
        service = real_service(*arguments, **keywords)
        case.real_services.append(service)
        return service

    monkeypatch.setattr(proof, "ProviderAuthenticationService", create_service)
    monkeypatch.setattr(kite_client, "_KiteConnect", create_sdk)
    # Restore the production factory after PF-02A's helper installed its older
    # external fake. This wrapper only records the real returned owner.
    monkeypatch.setattr(proof, "create_kite_authentication_adapter", create_adapter)
    return case


def _pf02b_assert_failed_but_resolved(case):
    status = case.app.connection_attempt_status()
    assert status["state"] in {"FAILED", "TIMED_OUT", "CANCELLED"}
    assert status["worker_active"] is False
    assert status["cleanup_state"] == "COMPLETE"
    assert status["resources_pending"] is False
    assert case.app.snapshot().provider_state.value == "ERROR"
    assert case.app.authenticated_read_only_capability() is None
    assert case.shared.read_only_status()["capability_state"] == "ABSENT"
    assert case.governance.store.read(status["request_identity"])["completion"]["state"] == "FAILURE"
    assert case.jobs == [] and case.restored == []
    return status


def _pf02b_assert_fresh_admission(case, previous):
    case.monotonic_now[0] += 20.0
    assert case.app.connect_provider()
    fresh = case.app.connection_attempt_status()
    assert fresh["state"] == "ACTIVE"
    assert fresh["generation"] > previous["generation"]
    assert fresh["request_identity"] != previous["request_identity"]
    assert fresh["remaining_seconds"] == 10.0
    assert len(case.jobs) == 1
    assert len(case.sdks) == 1  # The new generation is admitted, still queued.


def test_pf02b_real_production_pre_exchange_failure_closes_and_unfences_admission(
    tmp_path, monkeypatch
):
    def failed_opener():
        raise RuntimeError("pf02b-private-opener-detail")

    case = _pf02b_real_adapter_connection(
        tmp_path, monkeypatch, opener_hook=failed_opener
    )
    try:
        _run_ordinary_connection(case)
        assert len(case.sdks) == len(case.real_adapters) == 1
        sdk = case.sdks[0]
        assert sdk.exchange_count == sdk.profile_count == 0
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        previous = _pf02b_assert_failed_but_resolved(case)
        case.real_adapters[0].dispose_local()
        case.real_adapters[0].dispose_local()
        assert sdk.reqsession.close_count == 1
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        case.app.close()


@pytest.mark.parametrize("exchange_outcome", ["exception", "not_mapping", "missing_token", "invalid_token"])
def test_pf02b_real_production_exchange_failure_disposes_without_reexchange(
    tmp_path, monkeypatch, exchange_outcome
):
    from kronos.provider.exceptions.connectivity import ProviderConnectivityError

    arguments = {
        "exception": {"exchange_error": RuntimeError("pf02b-private-exchange-detail")},
        "not_mapping": {"exchange_response": None},
        "missing_token": {"exchange_response": {"user_id": "PRINCIPAL123"}},
        "invalid_token": {"exchange_response": {"access_token": ""}},
    }[exchange_outcome]
    case = _pf02b_real_adapter_connection(tmp_path, monkeypatch, **arguments)
    try:
        _run_ordinary_connection(case)
        sdk = case.sdks[0]
        assert sdk.exchange_count == 1
        assert sdk.profile_count == 0
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        previous = _pf02b_assert_failed_but_resolved(case)
        case.real_adapters[0].dispose_local()
        with pytest.raises(ProviderConnectivityError):
            case.real_adapters[0].login_url()
        assert sdk.exchange_count == sdk.reqsession.close_count == 1
        assert case.harness.credentials.lease.close_count == 1
        assert case.harness.callback.token.close_count == 1
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        case.app.close()


def test_pf02b_real_production_successful_transfer_survives_former_owner_disposal(
    tmp_path, monkeypatch
):
    case = _pf02b_real_adapter_connection(tmp_path, monkeypatch)
    try:
        _run_ordinary_connection(case)
        sdk = case.sdks[0]
        retained = case.app.authenticated_read_only_capability()
        assert retained is not None and retained.active
        assert case.app.snapshot().provider_state.value == "CONNECTED"
        assert sdk.exchange_count == sdk.profile_count == 1
        assert case.harness.resolver.resolve_count == 1
        assert sdk.reqsession.close_count == 0
        assert sdk.remote_logout_count == 0
        status = case.app.connection_attempt_status()
        assert status["state"] == "SUCCEEDED"
        assert status["worker_active"] is False
        assert status["cleanup_state"] == "COMPLETE"
        assert len(case.restored) == 1
        case.real_adapters[0].dispose_local()
        case.real_adapters[0].dispose_local()
        assert retained.active
        assert case.app.authenticated_read_only_capability() is retained
        assert sdk.reqsession.close_count == 0
        case.monotonic_now[0] = 100.0
        for timer in case.timers:
            timer.fire()
        assert retained.active
        assert case.app.connection_attempt_status()["state"] == "SUCCEEDED"
        assert not case.app.connect_provider()
        assert case.governance.store.read(status["request_identity"])["completion"]["state"] == "SUCCESS"
        case.app.close()
        assert not retained.active
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        case.real_adapters[0].dispose_local()
        assert sdk.reqsession.close_count == 1
    finally:
        case.app.close()


def test_pf02b_real_production_principal_mismatch_disposes_candidate_and_former_owner(
    tmp_path, monkeypatch
):
    case = _pf02b_real_adapter_connection(
        tmp_path, monkeypatch, principal="OTHER123"
    )
    try:
        _run_ordinary_connection(case)
        sdk = case.sdks[0]
        assert sdk.exchange_count == sdk.profile_count == 1
        assert case.harness.resolver.resolve_count == 1
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        previous = _pf02b_assert_failed_but_resolved(case)
        case.real_adapters[0].dispose_local()
        assert sdk.reqsession.close_count == 1
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        case.app.close()


def test_pf02b_real_production_failed_close_is_sticky_and_keeps_retry_fenced(
    tmp_path, monkeypatch
):
    from kronos.provider.exceptions.connectivity import (
        ProviderConnectivityError,
        ProviderErrorCode,
    )

    def failed_opener():
        raise RuntimeError("pf02b-private-opener-detail")

    case = _pf02b_real_adapter_connection(
        tmp_path,
        monkeypatch,
        opener_hook=failed_opener,
        close_error=RuntimeError("pf02b-private-close-detail"),
    )
    try:
        _run_ordinary_connection(case)
        sdk = case.sdks[0]
        status = case.app.connection_attempt_status()
        assert status["state"] == "CANCELLED"
        assert status["worker_active"] is False
        assert status["cleanup_state"] == "PENDING"
        assert status["resources_pending"] is True
        assert status["unresolved_resources"]
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.app.authenticated_read_only_capability() is None
        assert case.shared.read_only_status()["capability_state"] == "ABSENT"
        assert sdk.exchange_count == sdk.profile_count == 0
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        for _ in range(3):
            with pytest.raises(ProviderConnectivityError) as failed:
                case.real_adapters[0].dispose_local()
            assert failed.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            assert "pf02b-private-close-detail" not in str(failed.value)
            assert not case.app.connect_provider()
        assert sdk.reqsession.close_count == 1
        assert case.app.connection_attempt_status()["generation"] == status["generation"]
        assert case.app.connection_attempt_status()["cleanup_state"] == "PENDING"
        assert case.jobs == [] and case.restored == []
    finally:
        case.app.close()


def test_pf02b_real_production_blocked_sdk_exchange_retains_worker_until_return(
    tmp_path, monkeypatch
):
    from threading import Event

    entered, release = Event(), Event()

    def blocked_exchange():
        entered.set()
        assert release.wait(5), "test SDK exchange was not released"

    case = _pf02b_real_adapter_connection(
        tmp_path, monkeypatch, exchange_hook=blocked_exchange
    )
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        sdk = case.sdks[0]
        active = case.app.connection_attempt_status()
        assert active["state"] == "ACTIVE"
        assert sdk.exchange_count == 1
        assert sdk.profile_count == sdk.reqsession.close_count == 0
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        expired = case.app.connection_attempt_status()
        assert expired["state"] == "TIMED_OUT"
        assert expired["worker_active"] is True
        assert expired["cleanup_state"] == "PENDING"
        assert worker.is_alive()
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.app.authenticated_read_only_capability() is None
        assert case.shared.read_only_status()["capability_state"] == "ABSENT"
        _assert_status_reads_finish_while_worker_blocked(case)
        for _ in range(3):
            assert not case.app.connect_provider()
        assert len(case.sdks) == 1
        assert case.jobs == [] and case.restored == []
        assert sdk.reqsession.close_count == 0
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        resolved = _pf02b_assert_failed_but_resolved(case)
        assert resolved["state"] == "TIMED_OUT"
        assert resolved["generation"] == active["generation"]
        assert sdk.exchange_count == 1
        assert sdk.profile_count == 0
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        assert case.harness.credentials.lease.close_count == 1
        assert case.harness.callback.token.close_count == 1
        case.real_adapters[0].dispose_local()
        assert sdk.reqsession.close_count == 1
        _pf02b_assert_fresh_admission(case, resolved)
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()



def test_pf02b_real_production_end_during_principal_read_preserves_pending_owner(
    tmp_path, monkeypatch
):
    from threading import Event

    entered, release = Event(), Event()

    def blocked_profile():
        entered.set()
        assert release.wait(5), "test SDK profile was not released"

    case = _pf02b_real_adapter_connection(
        tmp_path, monkeypatch, profile_hook=blocked_profile
    )
    worker = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(2)
        sdk = case.sdks[0]
        assert sdk.exchange_count == sdk.profile_count == 1
        assert sdk.reqsession.close_count == 0
        active = case.app.connection_attempt_status()
        # This is the real service's local end API, called only against the
        # test-owned instance. Ending an owner cannot imply SDK termination.
        case.real_services[0].end_kronos_session()
        ended = case.app.connection_attempt_status()
        assert ended["state"] == "CANCELLED"
        assert ended["worker_active"] is True
        assert ended["cleanup_state"] == "PENDING"
        assert ended["resources_pending"] is True
        assert worker.is_alive()
        assert sdk.reqsession.close_count == 0
        assert case.app.authenticated_read_only_capability() is None
        for _ in range(3):
            assert not case.app.connect_provider()
        assert case.jobs == [] and case.restored == []
        _assert_status_reads_finish_while_worker_blocked(case)
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        resolved = _pf02b_assert_failed_but_resolved(case)
        assert resolved["state"] == "CANCELLED"
        assert resolved["generation"] == active["generation"]
        assert sdk.exchange_count == sdk.profile_count == 1
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        case.real_services[0].end_kronos_session()
        case.real_adapters[0].dispose_local()
        assert sdk.reqsession.close_count == 1
        _pf02b_assert_fresh_admission(case, resolved)
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()


def test_pf02b_real_retained_session_pending_close_resumes_only_after_profile_returns(
    tmp_path, monkeypatch
):
    from threading import Event, Thread
    from kronos.provider.models.authentication import (
        AuthenticatedContextState,
        ProviderAvailabilityState,
    )
    from kronos.provider.services.provider_authentication import (
        current_connection_deadline,
    )

    entered, release = Event(), Event()
    block_profile = [False]
    captured_deadlines = []

    def profile_hook():
        if not block_profile[0]:
            captured_deadlines.append(current_connection_deadline())
            return
        entered.set()
        assert release.wait(5), "test retained SDK profile was not released"

    case = _pf02b_real_adapter_connection(
        tmp_path, monkeypatch, profile_hook=profile_hook
    )
    worker = None
    try:
        _run_ordinary_connection(case)
        service = case.real_services[0]
        sdk = case.sdks[0]
        retained = case.app.authenticated_read_only_capability()
        assert retained is not None and retained.active
        deadline = captured_deadlines[0]
        assert deadline is not None and deadline.retry_ready
        assert deadline.snapshot()["state"] == "SUCCEEDED"
        assert sdk.exchange_count == sdk.profile_count == 1
        block_profile[0] = True
        results, errors = [], []

        def verify_availability():
            try:
                results.append(service.verify_provider_availability())
            except BaseException as error:
                errors.append(error)

        worker = Thread(target=verify_availability)
        worker.start()
        assert entered.wait(2)
        assert sdk.profile_count == 2
        service.end_kronos_session()
        pending = deadline.snapshot()
        assert pending["state"] == "SUCCEEDED"
        assert pending["cleanup_state"] == "PENDING"
        assert pending["resources_pending"] is True
        assert not deadline.retry_ready
        assert worker.is_alive()
        assert sdk.reqsession.close_count == 0
        assert not retained.active
        assert service.authenticated_read_only_capability() is None
        assert service.session_status().context_state is AuthenticatedContextState.ENDED
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert len(results) == 1
        assert results[0] is not ProviderAvailabilityState.AVAILABLE
        assert not retained.active
        assert sdk.reqsession.close_count == 0
        assert deadline.snapshot()["cleanup_state"] == "PENDING"
        assert not deadline.retry_ready

        # Explicit end resumes only the recorded PENDING owner. It may now
        # perform one physical close because the controlled SDK call ended.
        service.end_kronos_session()
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        assert deadline.snapshot()["cleanup_state"] == "COMPLETE"
        assert deadline.snapshot()["resources_pending"] is False
        assert deadline.retry_ready
        assert service.authenticated_read_only_capability() is None
        assert service.session_status().context_state is AuthenticatedContextState.ENDED
        service.end_kronos_session()
        assert sdk.reqsession.close_count == 1
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        case.app.close()


@pytest.mark.parametrize("blocked_phase", ["before_dispose", "physical_close"])
def test_pf02b_real_service_blocked_physical_close_is_owned_before_return(
    tmp_path, monkeypatch, blocked_phase
):
    from threading import Event, Thread
    from kronos.provider.models.authentication import AuthenticationFailureCode
    from kronos.provider.services.provider_authentication import (
        current_connection_deadline,
    )

    captured_deadlines = []
    case = _pf02b_real_adapter_connection(
        tmp_path,
        monkeypatch,
        profile_hook=lambda: captured_deadlines.append(current_connection_deadline()),
    )
    entered, release = Event(), Event()
    ending = repeated_end = None
    errors = []
    try:
        _run_ordinary_connection(case)
        service = case.real_services[0]
        sdk = case.sdks[0]
        retained = case.app.authenticated_read_only_capability()
        assert retained is not None and retained.active
        deadline = captured_deadlines[0]
        assert deadline is not None and deadline.retry_ready

        def blocked_close():
            sdk.reqsession.close_count += 1
            entered.set()
            assert release.wait(5), "test local SDK close was not released"

        expected_close_count = 1 if blocked_phase == "physical_close" else 0
        if blocked_phase == "physical_close":
            monkeypatch.setattr(sdk.reqsession, "close", blocked_close)
        else:
            service_type = type(service)
            original_dispose = service_type._ProviderAuthenticationService__dispose_resource

            def blocked_dispose(self, name, resource):
                if self is service and name == "candidate":
                    entered.set()
                    assert release.wait(5), "test extracted candidate was not released"
                return original_dispose(self, name, resource)

            monkeypatch.setattr(
                service_type, "_ProviderAuthenticationService__dispose_resource",
                blocked_dispose,
            )

        def end():
            try:
                service.end_kronos_session()
            except BaseException as error:
                errors.append(error)

        ending = Thread(target=end)
        ending.start()
        assert entered.wait(2)
        assert ending.is_alive()
        assert sdk.reqsession.close_count == expected_close_count
        if blocked_phase == "physical_close":
            assert not retained.active
        assert service.authenticated_read_only_capability() is None
        status = deadline.snapshot()
        assert status["state"] == "SUCCEEDED"
        assert status["worker_active"] is False  # The authentication worker ended.
        assert status["resources_pending"] is True  # Physical close has not ended.
        assert status["cleanup_state"] == "PENDING"
        assert not deadline.retry_ready
        with pytest.raises(
            RuntimeError,
            match=AuthenticationFailureCode.ATTEMPT_ALREADY_ACTIVE.value,
        ):
            service.begin_login()
        assert len(case.sdks) == len(case.real_adapters) == 1

        # A repeated close request must remain responsive without executing the
        # same external close concurrently or declaring the first one complete.
        repeated_end = Thread(target=end)
        repeated_end.start()
        repeated_end.join(1)
        assert not repeated_end.is_alive()
        assert not errors
        assert sdk.reqsession.close_count == expected_close_count
        assert deadline.snapshot()["resources_pending"] is True
        assert not deadline.retry_ready
        release.set()
        ending.join(2)
        assert not ending.is_alive() and not errors
        assert sdk.reqsession.close_count == 1
        assert sdk.remote_logout_count == 0
        assert deadline.snapshot()["cleanup_state"] == "COMPLETE"
        assert deadline.snapshot()["resources_pending"] is False
        assert deadline.retry_ready
        service.end_kronos_session()
        assert sdk.reqsession.close_count == 1
    finally:
        release.set()
        if ending is not None:
            ending.join(2)
        if repeated_end is not None:
            repeated_end.join(2)
        case.app.close()


def _pf02c_production_connection(tmp_path, monkeypatch, *, opener_hook=lambda: None):
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_real_listener
    from tools.provider_pilots import provider_foundation_v2_historical_proof as proof
    from kronos.provider.callbacks import loopback as transport

    case = _pf02b_real_adapter_connection(tmp_path, monkeypatch, opener_hook=opener_hook)
    case.transport = _pf02c_real_listener(monkeypatch, clock=lambda: case.wall_now[0])
    case.harness.listener = case.transport.listener

    def real_listener(**arguments):
        assert type(case.transport.listener) is transport.LoopbackAuthenticationCallbackListener
        return case.transport.listener

    monkeypatch.setattr(proof, "LoopbackAuthenticationCallbackListener", real_listener)
    return case


def _pf02c_service_request():
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_request_bytes
    return _pf02c_request_bytes(target="/kite/callback?request_token=service-request-token")


def test_pf02c_timeout_discards_unconsumed_callback_while_opener_stays_blocked(tmp_path, monkeypatch):
    from threading import Event
    from kronos.provider.models.authentication import CallbackCategory
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release

    entered, release = Event(), Event()

    def blocked_opener():
        entered.set()
        assert release.wait(4), "test opener was not released"

    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=blocked_opener)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(1)
        peer = case.transport.connect()
        peer.sendall(_pf02c_service_request())
        server = case.transport.servers[0]
        server._thread.join(1)
        assert not server._thread.is_alive()
        result = server._server.result
        assert result is not None and result.category() is CallbackCategory.ACCEPTED
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert worker.is_alive() and not case.app.connect_provider()
        assert server._server.result is None
        with pytest.raises(RuntimeError, match="CALLBACK_TOKEN_UNAVAILABLE"):
            result.consume_request_token(lambda _token: None)
        assert case.sdks[0].exchange_count == 0
        release.set()
        worker.join(1.5)
        assert not worker.is_alive() and not errors
        _pf02b_assert_failed_but_resolved(case)
    finally:
        release.set()
        if worker is not None:
            worker.join(1.5)
        case.app.close()
        _pf02c_release(case.transport, peer)


@pytest.mark.parametrize("partial", [None, b"GET /kite/", b"GET /kite/callback HTTP/1.1\r\nHost:"])
def test_pf02c_real_callback_worker_expires_while_opener_worker_remains_owned(tmp_path, monkeypatch, partial):
    from threading import Event
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released

    entered, release = Event(), Event()

    def blocked_opener():
        entered.set()
        assert release.wait(4), "test opener was not released"

    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=blocked_opener)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert entered.wait(1)
        server = case.transport.servers[0]
        if partial is not None:
            peer = case.transport.connect()
            peer.sendall(partial)
            assert case.transport.accepted.wait(1)
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        server._thread.join(0.75)
        assert not server._thread.is_alive()
        assert server._server.socket.fileno() == -1
        assert all(sock.fileno() == -1 for sock in case.transport.sockets)
        assert worker.is_alive()
        status = case.app.connection_attempt_status()
        assert status["state"] == "TIMED_OUT" and status["worker_active"] is True
        assert case.app.snapshot().provider_state.value == "ERROR"
        assert case.sdks[0].exchange_count == 0
        assert not case.app.connect_provider()
        assert len(case.sdks) == 1 and case.jobs == []
        release.set()
        worker.join(1.5)
        assert not worker.is_alive() and not errors
        previous = _pf02b_assert_failed_but_resolved(case)
        _pf02c_assert_released(case.transport)
        assert case.sdks[0].reqsession.close_count == 1
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        release.set()
        if worker is not None:
            worker.join(1.5)
        case.app.close()
        _pf02c_release(case.transport, peer)


def test_pf02c_real_callback_success_releases_transport_and_retains_session(tmp_path, monkeypatch):
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released
    from threading import Event

    opened = Event()
    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=opened.set)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert opened.wait(1)
        peer = case.transport.connect()
        peer.sendall(_pf02c_service_request())
        worker.join(1.5)
        assert not worker.is_alive() and not errors
        _pf02c_assert_released(case.transport)
        assert case.app.snapshot().provider_state.value == "CONNECTED"
        capability = case.app.authenticated_read_only_capability()
        assert capability is not None and capability.active
        assert case.sdks[0].exchange_count == case.sdks[0].profile_count == 1
        assert case.sdks[0].reqsession.close_count == 0
        assert case.harness.credentials.lease.close_count == 1
        case.transport.listener.close()
        assert capability.active
        assert case.sdks[0].reqsession.close_count == 0
    finally:
        if worker is not None:
            worker.join(1.5)
        case.app.close()
        _pf02c_release(case.transport, peer)


def test_pf02c_real_cancellation_racing_valid_handler_never_publishes_capability(tmp_path, monkeypatch):
    from threading import Event, Thread
    from kronos.provider.callbacks import loopback as transport
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released

    opened, entered, release = Event(), Event(), Event()
    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=opened.set)
    original = transport._OneRequestHTTPServer.publish_result
    material = []

    def blocked_publication(server, result):
        material.append(result)
        entered.set()
        assert release.wait(3), "test callback publication was not released"
        return original(server, result)

    monkeypatch.setattr(transport._OneRequestHTTPServer, "publish_result", blocked_publication)
    worker = peer = ending = None
    try:
        worker, errors = _start_connection_worker(case)
        assert opened.wait(1)
        peer = case.transport.connect()
        peer.sendall(_pf02c_service_request())
        assert entered.wait(1)
        ending = Thread(target=case.real_services[0].end_kronos_session)
        ending.start()
        assert case.transport.servers[0]._closed.wait(1)
        assert not case.app.connect_provider()
        release.set()
        ending.join(1.5)
        worker.join(1.5)
        assert not ending.is_alive() and not worker.is_alive() and not errors
        _pf02c_assert_released(case.transport)
        previous = _pf02b_assert_failed_but_resolved(case)
        assert previous["state"] == "CANCELLED"
        assert case.sdks[0].exchange_count == 0
        with pytest.raises(RuntimeError):
            material[0].consume_request_token(lambda _token: None)
        assert case.transport.servers[0]._server.result is None
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        release.set()
        if ending is not None:
            ending.join(1.5)
        if worker is not None:
            worker.join(1.5)
        case.app.close()
        _pf02c_release(case.transport, peer)


def test_pf02c_pending_real_listener_join_resolves_after_worker_return(tmp_path, monkeypatch):
    from threading import Event
    from kronos.provider.callbacks import loopback as transport
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released

    opened, entered, release = Event(), Event(), Event()
    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=opened.set)
    original = transport._StandardLibraryServer.join
    calls = []

    def controlled_join(server, timeout_seconds):
        calls.append(server)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3), "test listener join was not released"
        return original(server, timeout_seconds)

    monkeypatch.setattr(transport._StandardLibraryServer, "join", controlled_join)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert opened.wait(1)
        peer = case.transport.connect()
        peer.sendall(_pf02c_service_request())
        assert entered.wait(1)
        assert case.transport.listener.local_cleanup_state == "PENDING"
        case.real_services[0].end_kronos_session()
        assert worker.is_alive()
        status = case.app.connection_attempt_status()
        assert status["resources_pending"] is True
        assert "LISTENER" in status["unresolved_resources"]
        assert not case.app.connect_provider()
        assert len(calls) == 1
        release.set()
        worker.join(1.5)
        assert not worker.is_alive() and not errors
        _pf02c_assert_released(case.transport)
        assert case.sdks[0].exchange_count == 0
        previous = _pf02b_assert_failed_but_resolved(case)
        _pf02b_assert_fresh_admission(case, previous)
    finally:
        release.set()
        if worker is not None:
            worker.join(1.5)
        case.app.close()
        _pf02c_release(case.transport, peer)


def test_pf02c_unresolved_real_callback_thread_keeps_sticky_admission_fence(tmp_path, monkeypatch):
    from threading import Event
    from kronos.provider.callbacks import loopback as transport

    opened, entered, release = Event(), Event(), Event()
    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=opened.set)
    original = transport._CallbackRequestHandler._handle_terminal_request
    closes = []
    real_close = transport._StandardLibraryServer.close

    def blocked_handler(handler):
        entered.set()
        assert release.wait(4), "test handler was not released"
        original(handler)

    def observed_close(server):
        closes.append(server)
        real_close(server)

    monkeypatch.setattr(transport._CallbackRequestHandler, "_handle_terminal_request", blocked_handler)
    monkeypatch.setattr(transport._StandardLibraryServer, "close", observed_close)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert opened.wait(1)
        peer = case.transport.connect()
        peer.sendall(_pf02c_service_request())
        assert entered.wait(1)
        case.real_services[0].end_kronos_session()
        server = case.transport.servers[0]
        assert server._thread.is_alive()
        assert case.transport.listener.local_cleanup_state == "FAILED"
        assert case.app.connection_attempt_status()["resources_pending"] is True
        assert not case.app.connect_provider()
        release.set()
        worker.join(1.5)
        server._thread.join(1)
        assert not worker.is_alive() and not server._thread.is_alive() and not errors
        assert server._server.socket.fileno() == -1
        assert all(sock.fileno() == -1 for sock in case.transport.sockets)
        assert case.app.authenticated_read_only_capability() is None
        assert case.sdks[0].exchange_count == 0
        assert case.sdks[0].reqsession.close_count == 1
        for _ in range(3):
            case.real_services[0].end_kronos_session()
            assert not case.app.connect_provider()
        assert case.transport.listener.local_cleanup_state == "FAILED"
        assert len(closes) == 1
        assert len(case.sdks) == 1 and case.jobs == []
        assert "LISTENER" in case.app.connection_attempt_status()["unresolved_resources"]
    finally:
        release.set()
        if worker is not None:
            worker.join(1.5)
        if peer is not None:
            peer.close()
        case.app.close()
        for server in case.transport.servers:
            server._thread.join(1)
            assert not server._thread.is_alive()


def _pf02d_production_connection(tmp_path, monkeypatch, *, phase, mode=None):
    from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
    from kronos.configuration import apple_keychain as keychain, loader
    from tests.unit.provider.test_kite_login_navigator import _pf02d_process_fixture
    from tools.provider_pilots import provider_foundation_v2_historical_proof as proof
    from threading import Event
    import time
    real_monotonic = time.monotonic
    ready = Event()
    case = _pf02c_production_connection(tmp_path, monkeypatch, opener_hook=ready.set)
    # PF-02A's explicit injected clock remains on the attempt; multiprocessing
    # joins must use the real OS clock, not the older fixture's global patch.
    monkeypatch.setattr(time, 'monotonic', real_monotonic)
    case.transport.created = ready
    helper = _pf02d_process_fixture(monkeypatch, keychain=phase != 'browser',
        mode=mode or ('blocked' if phase == 'browser' else 'production-' + phase))
    if phase == 'browser':
        monkeypatch.setattr(proof, 'KiteLoginNavigator', KiteLoginNavigator)
    else:
        monkeypatch.setattr(proof, 'load_provider_authentication_configuration', loader.load_provider_authentication_configuration)
        monkeypatch.setattr(loader, '_provider_authentication_source', lambda **kwargs: (dict(loader._APPROVED_APPLICATION_CONFIG), True))
        monkeypatch.setattr(proof, 'AppleKeychainCredentialSource', keychain.AppleKeychainCredentialSource)
        monkeypatch.setattr(proof, 'AppleKeychainIntendedPrincipalResolver', keychain.AppleKeychainIntendedPrincipalResolver)
    case.helper = helper
    return case


@pytest.mark.parametrize('phase', ['browser', 'api-key', 'api-secret', 'intended-principal'])
@pytest.mark.parametrize('terminal', ['cancel', 'deadline'])
def test_pf02d_production_helper_terminalization_fences_and_releases(tmp_path, monkeypatch, phase, terminal):
    from tests.unit.provider.test_kite_login_navigator import _pf02d_assert_processes_released, _pf02d_finish
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released
    case = _pf02d_production_connection(tmp_path, monkeypatch, phase=phase)
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        if phase in {'api-secret', 'intended-principal'}:
            assert case.transport.created.wait(2)
            peer = case.transport.connect()
            peer.sendall(_pf02c_service_request())
        assert case.helper.entered.wait(2)
        if phase == 'browser':
            peer = case.transport.connect()
            peer.sendall(b'GET /kite/')
            assert case.transport.accepted.wait(1)
        if terminal == 'deadline':
            case.monotonic_now[0] = 10.0
            case.timers[-1].fire()
        else:
            case.app._SwingOpportunitiesApplication__connection_deadline.cancel()
        worker.join(2)
        assert not worker.is_alive() and not errors
        previous = _pf02b_assert_failed_but_resolved(case)
        _pf02d_assert_processes_released(case.helper)
        if phase != 'api-key':
            _pf02c_assert_released(case.transport)
            assert case.sdks[0].exchange_count == (1 if phase == 'intended-principal' else 0)
            _pf02b_assert_fresh_admission(case, previous)
        else:
            assert case.sdks == [] and case.transport.servers == []
            case.monotonic_now[0] += 20
            assert case.app.connect_provider()
            assert len(case.jobs) == 1
    finally:
        case.helper.release.set()
        if worker is not None:
            worker.join(2)
        _pf02d_finish(case.helper)
        case.app.close()
        _pf02c_release(case.transport, peer)


@pytest.mark.parametrize('phase', ['browser', 'api-key'])
def test_pf02d_production_failed_helper_cleanup_retains_retry_fence(tmp_path, monkeypatch, phase):
    from kronos.configuration import apple_keychain
    from tests.unit.provider.test_kite_login_navigator import _pf02d_finish
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release
    case = _pf02d_production_connection(tmp_path, monkeypatch, phase=phase)
    worker = owner = None
    try:
        worker, errors = _start_connection_worker(case)
        assert case.helper.entered.wait(2)
        process = case.helper.records[0].process
        terminate, kill = process.terminate, process.kill
        process.terminate = process.kill = lambda: None
        case.monotonic_now[0] = 10
        case.timers[-1].fire()
        assert not case.app.connect_provider()
        worker.join(2)
        assert not worker.is_alive() and not errors and process.is_alive()
        status = case.app.connection_attempt_status()
        assert status['resources_pending'] and status['worker_active'] is False
        assert any('HELPER' in name for name in status['unresolved_resources'])
        assert case.app.authenticated_read_only_capability() is None and case.restored == []
        assert not case.app.connect_provider() and case.jobs == []
        process.terminate, process.kill = terminate, kill
        case.helper.release.set(); process.join(1)
        assert not process.is_alive()
        assert not case.app.connect_provider()
        if phase == 'api-key':
            owner = apple_keychain._retrieval_owners[0]
            assert owner.local_cleanup_state == 'FAILED'
    finally:
        if 'terminate' in locals():
            process.terminate, process.kill = terminate, kill
        case.helper.release.set()
        if worker is not None:
            worker.join(2)
        _pf02d_finish(case.helper)
        case.app.close()
        _pf02c_release(case.transport, None)
        if owner in apple_keychain._retrieval_owners:
            apple_keychain._retrieval_owners.remove(owner)


def test_pf02d_production_keychain_success_releases_three_helpers(tmp_path, monkeypatch):
    from tests.unit.provider.test_kite_login_navigator import _pf02d_assert_processes_released, _pf02d_finish
    from tests.unit.provider.test_loopback_authentication_callback import _pf02c_release, _pf02c_assert_released
    case = _pf02d_production_connection(tmp_path, monkeypatch, phase='api-key', mode='production-success')
    worker = peer = None
    try:
        worker, errors = _start_connection_worker(case)
        assert case.transport.created.wait(2)
        peer = case.transport.connect(); peer.sendall(_pf02c_service_request())
        worker.join(3)
        assert not worker.is_alive() and not errors
        assert case.app.snapshot().provider_state.value == 'CONNECTED'
        assert case.app.authenticated_read_only_capability() is not None
        assert len(case.helper.records) == 3
        _pf02d_assert_processes_released(case.helper)
        _pf02c_assert_released(case.transport)
        assert case.sdks[0].exchange_count == case.sdks[0].profile_count == 1
    finally:
        case.helper.release.set()
        if worker is not None:
            worker.join(2)
        _pf02d_finish(case.helper)
        case.app.close()
        _pf02c_release(case.transport, peer)
