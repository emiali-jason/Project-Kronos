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
