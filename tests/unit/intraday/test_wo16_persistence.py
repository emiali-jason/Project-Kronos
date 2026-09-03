from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.application.intraday_wo16 import (
    IntradayWo16PersistenceApplication,
    IntradayWo16RestorationService,
    Wo16ApplicationError,
    Wo16ApplicationOutcome,
    Wo16BusyOutcome,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo16 import (
    WO16_POLICY_CHECKSUM,
    WO16_POLICY_IDENTITY,
    WO16_POLICY_VERSION,
    Wo16LifecycleAdmissionDisposition,
    Wo16SponsorDecision,
    Wo16SuccessorTrigger,
)
from kronos.intraday.wo16_persistence import (
    DEFAULT_WO16_ROOT,
    Wo16PersistenceError,
    Wo16RestorationState,
    Wo16Store,
)

from .test_wo16_application import _request
from .test_wo16_contracts import _chain


def _components(  # type: ignore[no-untyped-def]
    tmp_path: Path, choice=Wo16SponsorDecision.PAPER, **options
):
    chain = _chain(tmp_path / "chain", **options)
    request = _request(chain, choice)
    store = Wo16Store((tmp_path / "wo16").resolve())
    return chain, request, store, IntradayWo16PersistenceApplication(store=store)


@pytest.mark.parametrize(
    ("choice", "disposition"),
    (
        (
            Wo16SponsorDecision.PAPER,
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
        ),
        (
            Wo16SponsorDecision.LIVE,
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
        ),
        (
            Wo16SponsorDecision.IGNORE,
            Wo16LifecycleAdmissionDisposition.NOT_APPLICABLE_IGNORE,
        ),
    ),
)
def test_decision_graph_persists_and_restores(
    tmp_path, choice, disposition
) -> None:  # type: ignore[no-untyped-def]
    _, request, store, application = _components(tmp_path, choice)
    result = application.execute(request)
    restored = store.restore_current(
        request.wo13_trade_plan.canonical_subject_identity
    )
    assert restored is not None
    assert restored.request == request
    assert restored.snapshot == result.execution.snapshot
    assert restored.decision == result.execution.decision
    assert restored.admission == result.execution.admission
    assert restored.operation == result.operation
    assert restored.admission.disposition is disposition
    assert restored.pointer.policy.policy_identity == WO16_POLICY_IDENTITY
    assert restored.pointer.policy.policy_version == WO16_POLICY_VERSION
    assert restored.pointer.policy.policy_checksum == WO16_POLICY_CHECKSUM


def test_empty_loaded_and_corrupt_restoration_states(tmp_path) -> None:
    store = Wo16Store((tmp_path / "wo16").resolve())
    service = IntradayWo16RestorationService(store=store)
    assert service.restore().state is Wo16RestorationState.NOT_YET_RUN

    _, request, _, application = _components(tmp_path)
    application.execute(request)
    service = IntradayWo16RestorationService(store=application.store)
    assert service.restore().state is Wo16RestorationState.LOADED

    alias = next((application.store.root / "current").glob("CURRENT-*.json"))
    alias.write_text("{}", encoding="utf-8")
    corrupt = service.restore()
    assert corrupt.state is Wo16RestorationState.CORRUPT
    assert corrupt.failure_reason == "WO16_RESTORATION_FAILED"


def test_exact_replay_is_idempotent_and_writes_nothing(tmp_path) -> None:
    _, request, store, application = _components(tmp_path)
    first = application.execute(request)
    before = _file_fingerprints(store.root)
    replay = application.execute(request)
    assert replay.replayed
    assert replay.execution.outcome is Wo16ApplicationOutcome.RETAINED_IDEMPOTENT
    assert replay.execution.decision == first.execution.decision
    assert replay.pointer == first.pointer
    assert _file_fingerprints(store.root) == before


def test_conflicting_choice_preserves_current_and_records_failure(tmp_path) -> None:
    chain, request, store, application = _components(tmp_path)
    first = application.execute(request)
    conflict = _request(chain, Wo16SponsorDecision.LIVE)
    with pytest.raises(Wo16ApplicationError, match="WO16_DECISION_ALREADY_FINAL"):
        application.execute(conflict)
    restored = store.restore_current(
        request.wo13_trade_plan.canonical_subject_identity
    )
    assert restored is not None and restored.pointer == first.pointer
    assert restored.decision.choice is Wo16SponsorDecision.PAPER
    assert restored.latest_failure is not None
    assert restored.latest_failure.reason == "WO16_DECISION_ALREADY_FINAL"
    assert len(tuple((store.root / "decisions").glob("*.json"))) == 1
    assert len(tuple((store.root / "admissions").glob("*.json"))) == 1
    assert not tuple((store.root / "supersessions").glob("*.json"))


def test_stale_lineage_failure_preserves_current_without_false_graph(tmp_path) -> None:
    first_chain = _chain(tmp_path / "first")
    foreign_chain = _chain(
        tmp_path / "foreign", direction=SemanticDirection.SHORT
    )
    store = Wo16Store((tmp_path / "wo16").resolve())
    application = IntradayWo16PersistenceApplication(store=store)
    first = application.execute(_request(first_chain))
    stale = _request(
        first_chain,
        current_wo13_pointer=foreign_chain["pointer13"],
    )
    with pytest.raises(Wo16ApplicationError, match="WO13_NOT_CURRENT"):
        application.execute(stale)
    restored = store.restore_current(
        first_chain["plan"].canonical_subject_identity
    )
    assert restored is not None and restored.pointer == first.pointer
    assert len(tuple((store.root / "decisions").glob("*.json"))) == 1
    assert len(tuple((store.root / "admissions").glob("*.json"))) == 1
    assert not tuple((store.root / "supersessions").glob("*.json"))


def test_same_identity_different_bytes_conflicts_without_overwrite(tmp_path) -> None:
    _, request, store, _ = _components(tmp_path)
    path = store.retain_request(request)
    path.write_text("foreign", encoding="utf-8")
    with pytest.raises(Wo16PersistenceError, match="WO16_IMMUTABLE_CONFLICT"):
        store.retain_request(request)
    assert path.read_text(encoding="utf-8") == "foreign"


def test_full_graph_is_reloaded_before_current_alias_publication(tmp_path) -> None:
    _, request, store, application = _components(tmp_path)
    result = application.execute(request)
    restored = store.restore_pointer(result.pointer)
    assert restored.pointer == result.pointer
    assert restored.operation.outcome.value == "COMPLETED"
    assert restored.operation.decision_identity == restored.decision.decision_identity
    assert restored.operation.admission_identity == restored.admission.admission_identity
    assert restored.pointer.scope_identity.startswith("INTRADAY-WO16-SCOPE-")


def test_nse_and_mcx_pointer_scope_preserve_exact_lineage(tmp_path) -> None:
    nse_chain, nse_request, _, nse_app = _components(tmp_path / "nse")
    nse = nse_app.execute(nse_request).pointer
    assert nse.instrument_identity == nse_chain["plan"].instrument_identity
    assert nse.actual_contract_identity is None
    assert nse.roll_lineage_identity is None

    mcx_chain, mcx_request, _, mcx_app = _components(
        tmp_path / "mcx", mcx=True
    )
    mcx = mcx_app.execute(mcx_request).pointer
    assert mcx.instrument_identity == mcx_chain["plan"].instrument_identity
    assert mcx.actual_contract_identity == (
        mcx_chain["handoff13"].actual_contract_identity
    )
    assert mcx.roll_lineage_identity == mcx_chain["handoff13"].roll_lineage_identity
    assert mcx.session_identity == mcx_chain["session15"].session_identity


def test_successor_retains_prior_decision_and_ignore_is_exact_lineage(tmp_path) -> None:
    first_chain = _chain(tmp_path / "first")
    second_chain = _chain(
        tmp_path / "second", direction=SemanticDirection.SHORT
    )
    store = Wo16Store((tmp_path / "wo16").resolve())
    application = IntradayWo16PersistenceApplication(store=store)
    first = application.execute(
        _request(first_chain, Wo16SponsorDecision.IGNORE)
    )
    second = application.execute(
        _request(second_chain, Wo16SponsorDecision.PAPER)
    )
    assert second.successor is not None
    assert second.successor.trigger is Wo16SuccessorTrigger.WO13_PLAN
    assert second.successor.predecessor_decision_identity == (
        first.execution.decision.decision_identity
    )
    assert second.execution.decision.predecessor_decision_identity == (
        first.execution.decision.decision_identity
    )
    restored = store.restore_current(
        first_chain["plan"].canonical_subject_identity
    )
    assert restored is not None
    assert restored.history == (
        first.execution.decision,
        second.execution.decision,
    )
    assert first.execution.decision.choice is Wo16SponsorDecision.IGNORE
    assert len(tuple((store.root / "decisions").glob("*.json"))) == 2


@pytest.mark.parametrize(
    ("field", "replacement", "trigger"),
    (
        ("session_identity", "SUCCESSOR-SESSION", Wo16SuccessorTrigger.MARKET_SESSION),
        (
            "actual_contract_identity",
            "SUCCESSOR-CONTRACT",
            Wo16SuccessorTrigger.MCX_ACTIVE_CONTRACT_OR_ROLL_LINEAGE,
        ),
        (
            "roll_lineage_identity",
            "SUCCESSOR-ROLL",
            Wo16SuccessorTrigger.MCX_ACTIVE_CONTRACT_OR_ROLL_LINEAGE,
        ),
    ),
)
def test_successor_trigger_classification_is_explicit(
    tmp_path, field, replacement, trigger
) -> None:  # type: ignore[no-untyped-def]
    from kronos.application.intraday_wo16 import (
        IntradayWo16Application,
        _successor_trigger,
    )

    chain = _chain(tmp_path, mcx=True)
    execution = IntradayWo16Application().execute(_request(chain))
    _, _, _, persistent = _components(tmp_path / "persist", mcx=True)
    pointer = persistent.execute(
        _request(_chain(tmp_path / "persist-chain", mcx=True))
    ).pointer
    altered = _copy_slots(pointer)
    object.__setattr__(altered, field, replacement)
    # The changed value belongs to the predecessor; classification remains
    # about which governed boundary differs, not about artifact validity.
    assert _successor_trigger(altered, execution) is trigger


def test_missing_and_altered_artifacts_fail_closed(tmp_path) -> None:
    _, request, store, application = _components(tmp_path)
    result = application.execute(request)
    decision_path = (
        store.root
        / "decisions"
        / f"{result.execution.decision.decision_identity}.json"
    )
    original = decision_path.read_bytes()
    decision_path.unlink()
    with pytest.raises(Wo16PersistenceError, match="WO16_ARTIFACT_UNAVAILABLE"):
        store.restore_pointer(result.pointer)
    decision_path.write_bytes(original[:-4])
    with pytest.raises(Wo16PersistenceError, match="WO16_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_pointer(result.pointer)


def test_altered_canonical_hash_and_pointer_are_detected(tmp_path) -> None:
    _, request, store, application = _components(tmp_path)
    result = application.execute(request)
    request_path = store.root / "requests" / f"{request.request_identity}.json"
    document = json.loads(request_path.read_bytes())
    document["artifact"]["fields"]["choice"]["value"] = "LIVE"
    core = {
        key: document[key]
        for key in ("artifact_type", "artifact_identity", "artifact")
    }
    encoded_core = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    document["document_integrity"] = sha256(encoded_core).hexdigest()
    request_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(Wo16PersistenceError, match="WO16_ARTIFACT_INTEGRITY_INVALID"):
        store.load_request(request.request_identity)

    pointer = _copy_slots(result.pointer)
    object.__setattr__(pointer, "decision_identity", "ALTERED")
    with pytest.raises(Wo16PersistenceError, match="WO16_CURRENT_POINTER_INVALID"):
        pointer.__post_init__()


def test_path_traversal_is_rejected(tmp_path) -> None:
    store = Wo16Store((tmp_path / "wo16").resolve())
    with pytest.raises(Wo16PersistenceError, match="WO16_ARTIFACT_PATH_INVALID"):
        store.load_decision("../CURRENT")
    with pytest.raises(Wo16PersistenceError, match="WO16_ARTIFACT_PATH_INVALID"):
        store.load_current("../../SWING")


def test_partial_write_never_publishes_current(tmp_path, monkeypatch) -> None:
    _, request, store, application = _components(tmp_path)

    def fail(_pointer):  # type: ignore[no-untyped-def]
        raise OSError("bounded test failure")

    monkeypatch.setattr(store, "publish_current", fail)
    with pytest.raises(Wo16ApplicationError, match="WO16_APPLICATION_FAILURE"):
        application.execute(request)
    assert store.load_current(
        request.wo13_trade_plan.canonical_subject_identity
    ) is None
    assert not tuple((store.root / "decisions").glob("*.json")) == ()
    assert store.load_latest_failure(
        request.wo13_trade_plan.canonical_subject_identity
    ) is not None
    restored = IntradayWo16RestorationService(store=store).restore()
    assert restored.state is Wo16RestorationState.NOT_YET_RUN
    assert len(restored.latest_failures) == 1


def test_concurrent_operation_returns_busy_without_writes(tmp_path) -> None:
    _, request, store, application = _components(tmp_path)
    assert application._lock.acquire(blocking=False)  # noqa: SLF001
    try:
        result = application.execute(request)
    finally:
        application._lock.release()  # noqa: SLF001
    assert type(result) is Wo16BusyOutcome
    assert not store.root.exists()


def test_restoration_is_read_only_and_performs_no_decision_evaluation(
    tmp_path, monkeypatch
) -> None:
    from kronos.application.intraday_wo16 import IntradayWo16Application

    _, request, store, application = _components(tmp_path)
    application.execute(request)
    before = _file_fingerprints(store.root)

    def prohibited(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("restoration evaluated a decision")

    monkeypatch.setattr(IntradayWo16Application, "execute", prohibited)
    status = IntradayWo16RestorationService(store=store).restore()
    assert status.state is Wo16RestorationState.LOADED
    assert _file_fingerprints(store.root) == before

    source = Path(
        "src/kronos/intraday/wo16_persistence.py"
    ).read_text(encoding="utf-8")
    assert "kronos.provider" not in source
    assert "kronos.browser" not in source
    assert "kronos.runtime" not in source


def test_no_position_fill_quantity_economics_or_broker_authority(tmp_path) -> None:
    _, request, _, application = _components(tmp_path)
    result = application.execute(request).execution
    assert result.admission.position_consequence == "NONE"
    assert not result.admission.position_authority
    assert not result.admission.fill_authority
    assert not result.admission.quantity_authority
    assert not result.admission.execution_authority
    assert not result.admission.broker_authority
    forbidden = {"pnl", "realised_r", "quantity", "fill", "position"}
    assert forbidden.isdisjoint(_slot_names(result))


def test_store_root_is_intraday_product_local() -> None:
    assert DEFAULT_WO16_ROOT.parts[-3:] == (
        "evidence",
        "intraday-v1",
        "wo16-sponsor-decision-lifecycle-admission-v1",
    )
    assert "swing" not in str(DEFAULT_WO16_ROOT).lower()


def test_persisted_values_are_immutable(tmp_path) -> None:
    _, request, _, application = _components(tmp_path)
    result = application.execute(request)
    with pytest.raises(FrozenInstanceError):
        result.pointer.decision_identity = "CHANGED"


def _file_fingerprints(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _copy_slots(value):  # type: ignore[no-untyped-def]
    copied = object.__new__(type(value))
    for name in _slot_names(value):
        object.__setattr__(copied, name, getattr(value, name))
    return copied


def _slot_names(value):  # type: ignore[no-untyped-def]
    return tuple(
        name
        for cls in type(value).__mro__
        for name in getattr(cls, "__slots__", ())
        if name not in {"__dict__", "__weakref__"}
    )
