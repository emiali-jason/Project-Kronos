from __future__ import annotations

from dataclasses import replace

import pytest

from kronos.application.intraday_wo10 import (
    IntradayWo10Application,
    Wo10ApplicationError,
    Wo10EvidenceInputs,
    Wo10TypedEvidenceAssembler,
)
from kronos.intraday.probables_v2 import evaluate_probables_v2_run
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_v2 import (
    bind_imported_visual_evidence_v2,
    create_chart_revision_v2,
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10ReasonCode,
    Wo10ReasonScope,
    Wo10State,
    create_wo10_reconciliation_request,
)
from kronos.intraday.wo10_evidence import (
    Wo10EvidenceReference,
    create_wo10_evidence_snapshot,
)
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo10_policies import (
    Wo10PolicyDecision,
    Wo10PolicyRegistry,
)

from .test_probables_v2 import PROVENANCE, SOURCE_RUN, _opening_inputs
from .test_review import _png
from .test_wo10_contracts import (
    REQUESTED_AT,
    _answer,
    _bundle,
    _extension,
    _facts,
    _policy,
    _resolver,
)


class _Assembler:
    def __init__(self, snapshot, *, fail: bool = False):  # type: ignore[no-untyped-def]
        self.snapshot = snapshot
        self.fail = fail
        self.calls = 0
        self.provider_calls = 0

    def assemble(self, *, run, result, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail:
            raise Wo10ApplicationError("WO10_EVIDENCE_UNAVAILABLE")
        return self.snapshot


class _Policy:
    def __init__(self, binding, state=Wo10State.PROMOTION_READY):  # type: ignore[no-untyped-def]
        self._binding = binding
        self._state = state
        self.calls = 0

    @property
    def binding(self):  # type: ignore[no-untyped-def]
        return self._binding

    def evaluate(self, *, request, evidence):  # type: ignore[no-untyped-def]
        self.calls += 1
        return Wo10PolicyDecision(
            canonical_subject_identity=evidence.canonical_subject_identity,
            inherited_direction=evidence.inherited_direction,
            state=self._state,
            reasons=(Wo10ReasonCode(
                Wo10ReasonScope.COMMON,
                "GOVERNED_EVIDENCE_COHERENT",
                request.policy.policy_identity,
            ),),
        )


def _application(
    tmp_path, *, fail: bool = False, registry: bool = True,
    state: Wo10State = Wo10State.PROMOTION_READY,
):  # type: ignore[no-untyped-def]
    run, probable, request, snapshot, _ = _bundle()
    run_store = ProbablesV2Store(tmp_path / "probables")
    run_store.retain_result(probable)
    run_store.retain_run(run)
    store = Wo10Store(tmp_path / "wo10")
    assembler = _Assembler(snapshot, fail=fail)
    policy = _Policy(request.policy, state)
    application = IntradayWo10Application(
        run_store=run_store,
        store=store,
        policy_registry=Wo10PolicyRegistry((policy,) if registry else ()),
        evidence_assembler=assembler,
        backend_identity="KRONOS-BACKEND-TEST",
        process_identity="PID-TEST",
    )
    return application, store, assembler, policy, request


def test_explicit_operation_persists_before_evaluation_and_publishes_complete_pointer(tmp_path) -> None:
    application, store, assembler, policy, request = _application(tmp_path)
    outcome = application.execute(request)

    assert outcome.completed
    assert outcome.batch is not None and outcome.pointer is not None
    assert outcome.candidates[0].state == "PROMOTION_READY"
    assert assembler.calls == policy.calls == 1
    assert assembler.provider_calls == 0
    assert store.load_request(request.request_identity) == request
    restored = application.restore_current(IntradayMarketFamily.NSE_EQUITY)
    assert restored is not None
    assert restored.batch == outcome.batch
    assert restored.results[0].state is Wo10State.PROMOTION_READY


def test_same_request_is_deterministic_idempotent_and_does_not_duplicate_files(tmp_path) -> None:
    application, store, _, _, request = _application(tmp_path)
    first = application.execute(request)
    counts = {
        directory.name: len(tuple(directory.glob("*.json")))
        for directory in store.root.iterdir()
        if directory.is_dir()
    }
    second = application.execute(request)
    assert second.batch == first.batch
    assert second.pointer == first.pointer
    assert second.operation == first.operation
    assert counts == {
        directory.name: len(tuple(directory.glob("*.json")))
        for directory in store.root.iterdir()
        if directory.is_dir()
    }


@pytest.mark.parametrize("state", tuple(Wo10State))
def test_all_seven_states_persist_without_remapping(tmp_path, state: Wo10State) -> None:
    application, _, _, _, request = _application(tmp_path, state=state)
    outcome = application.execute(request)
    assert outcome.completed
    assert outcome.candidates[0].state == state.value
    assert outcome.batch is not None
    assert next(item.count for item in outcome.batch.state_counts if item.state is state) == 1


def test_unknown_policy_fails_after_request_retention_without_pointer(tmp_path) -> None:
    application, store, _, _, request = _application(tmp_path, registry=False)
    with pytest.raises(Wo10ApplicationError, match="WO10_POLICY_UNKNOWN"):
        application.execute(request)
    assert store.load_request(request.request_identity) == request
    assert store.load_current(request.market_family) is None


def test_evidence_failure_is_retained_and_never_publishes_false_current(tmp_path) -> None:
    application, store, assembler, policy, request = _application(tmp_path, fail=True)
    outcome = application.execute(request)
    assert not outcome.completed
    assert outcome.batch is None and outcome.pointer is None
    assert outcome.candidates[0].failure_reason == "WO10_EVIDENCE_UNAVAILABLE"
    assert assembler.calls == 1
    assert policy.calls == 0
    assert store.load_current(request.market_family) is None


def test_failed_repeat_does_not_overwrite_last_complete_pointer(tmp_path) -> None:
    application, store, assembler, _, request = _application(tmp_path)
    complete = application.execute(request)
    assert complete.pointer is not None
    assembler.fail = True
    failed = application.execute(request)
    assert not failed.completed
    assert store.load_current(request.market_family) == complete.pointer


def test_exact_run_result_and_snapshot_bindings_fail_closed(tmp_path) -> None:
    application, store, assembler, policy, request = _application(tmp_path)
    assembler.snapshot = replace(
        assembler.snapshot,
        snapshot_identity=assembler.snapshot.snapshot_identity,
        snapshot_integrity=assembler.snapshot.snapshot_integrity,
    )
    # A different-family snapshot cannot be constructed validly; a wrong result
    # binding is caught before policy dispatch by the exact retained run lookup.
    result_path = (
        tmp_path / "probables" / "probables-v2" / "results"
        / f"{request.probable_bindings[0].probable_result_identity}.json"
    )
    result_path.write_bytes(b"{}\n")
    outcome = application.execute(request)
    assert not outcome.completed
    assert outcome.candidates[0].failure_reason.startswith("PROBABLES_V2_")
    assert policy.calls == 0
    assert store.load_current(request.market_family) is None


def test_nonblocking_concurrency_guard_rejects_overlap(tmp_path) -> None:
    application, _, _, _, request = _application(tmp_path)
    assert application._lock.acquire(blocking=False)  # bounded white-box concurrency proof
    try:
        with pytest.raises(Wo10ApplicationError, match="WO10_OPERATION_BUSY"):
            application.execute(request)
    finally:
        application._lock.release()


def test_typed_assembler_constructs_snapshot_from_exact_retained_inputs() -> None:
    mapping = _opening_inputs()[4]
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=mapping.market_session_identity,
        analysis_boundary=mapping.analysis_boundary,
        member_evidence=(mapping,),
        unavailable_members=(),
        provenance=PROVENANCE,
    )
    probable = run.results[0]
    request = create_wo10_reconciliation_request(
        run=run,
        results=(probable,),
        market_family=IntradayMarketFamily.NSE_EQUITY,
        policy=_policy(IntradayMarketFamily.NSE_EQUITY),
        requested_at=REQUESTED_AT,
        sponsor_operation_identity="SPONSOR-WO10-ASSEMBLY-TEST",
        provenance=PROVENANCE,
    )

    class _Loader:
        def load(self, *, run, result, request):  # type: ignore[no-untyped-def]
            handoff = create_review_handoff_v2(run, result, mapping)
            cycle = create_review_cycle_v2(handoff)
            chart = create_chart_revision_v2(
                cycle,
                revision_ordinal=1,
                payload=_png(91),
                media_type="image/png",
                received_at=result.analysis_boundary,
            )
            pack = create_question_pack_v2(handoff, cycle, chart)
            visual = bind_imported_visual_evidence_v2(
                pack,
                _answer(pack, "Visible RELIANCE"),
                imported_at=result.analysis_boundary,
                visual_identity_resolver=_resolver(
                    result.canonical_subject_identity,
                    "Visible RELIANCE",
                    result.analysis_boundary,
                ),
            )
            return Wo10EvidenceInputs(
                cycle=cycle,
                chart=chart,
                review_pack=pack,
                imported_visual_evidence=visual,
                common_facts=_facts(),
                family_extension=_extension(request.market_family),
                source_references=(Wo10EvidenceReference("SOURCE", "INTEGRITY-SOURCE"),),
                provenance=PROVENANCE,
            )

    assembler = Wo10TypedEvidenceAssembler(_Loader())
    snapshot = assembler.assemble(run=run, result=probable, request=request)
    assert snapshot.probables_run_identity == run.run_identity
    assert snapshot.probable_result_identity == probable.result_identity
    assert snapshot.policy == request.policy


def test_one_candidate_failure_does_not_hide_another_persisted_result(tmp_path) -> None:
    mappings = (
        _opening_inputs("NSE-EQ-RELIANCE")[4],
        _opening_inputs("NSE-EQ-TCS")[4],
    )
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=mappings[0].market_session_identity,
        analysis_boundary=mappings[0].analysis_boundary,
        member_evidence=mappings,
        unavailable_members=(),
        provenance=PROVENANCE,
    )
    policy_binding = _policy(IntradayMarketFamily.NSE_EQUITY)
    request = create_wo10_reconciliation_request(
        run=run,
        results=run.results,
        market_family=IntradayMarketFamily.NSE_EQUITY,
        policy=policy_binding,
        requested_at=REQUESTED_AT,
        sponsor_operation_identity="SPONSOR-WO10-ISOLATION-TEST",
        provenance=PROVENANCE,
    )
    snapshots = {}
    for result, mapping in zip(run.results, sorted(mappings, key=lambda item: item.universe_member_identity), strict=True):
        handoff = create_review_handoff_v2(run, result, mapping)
        cycle = create_review_cycle_v2(handoff)
        chart = create_chart_revision_v2(
            cycle,
            revision_ordinal=1,
            payload=_png(93),
            media_type="image/png",
            received_at=result.analysis_boundary,
        )
        pack = create_question_pack_v2(handoff, cycle, chart)
        observed = f"Visible {result.canonical_subject_identity}"
        visual = bind_imported_visual_evidence_v2(
            pack,
            _answer(pack, observed),
            imported_at=result.analysis_boundary,
            visual_identity_resolver=_resolver(
                result.canonical_subject_identity, observed, result.analysis_boundary
            ),
        )
        snapshots[result.result_identity] = create_wo10_evidence_snapshot(
            run=run,
            result=result,
            cycle=cycle,
            chart=chart,
            review_pack=pack,
            imported_visual_evidence=visual,
            market_family=request.market_family,
            policy=request.policy,
            common_facts=_facts(),
            family_extension=_extension(request.market_family),
            source_references=(Wo10EvidenceReference(
                f"SOURCE-{result.canonical_subject_identity}",
                f"INTEGRITY-{result.canonical_subject_identity}",
            ),),
            provenance=PROVENANCE,
        )

    class _IsolatingAssembler:
        provider_calls = 0

        def assemble(self, *, run, result, request):  # type: ignore[no-untyped-def]
            if result.canonical_subject_identity == "NSE-EQ-TCS":
                raise Wo10ApplicationError("WO10_EVIDENCE_UNAVAILABLE")
            return snapshots[result.result_identity]

    run_store = ProbablesV2Store(tmp_path / "probables")
    for result in run.results:
        run_store.retain_result(result)
    run_store.retain_run(run)
    store = Wo10Store(tmp_path / "wo10")
    application = IntradayWo10Application(
        run_store=run_store,
        store=store,
        policy_registry=Wo10PolicyRegistry((_Policy(request.policy),)),
        evidence_assembler=_IsolatingAssembler(),
    )
    outcome = application.execute(request)
    successful = next(item for item in outcome.candidates if item.failure_reason is None)
    failed = next(item for item in outcome.candidates if item.failure_reason is not None)
    assert store.load_result(successful.reconciliation_result_identity).state is Wo10State.PROMOTION_READY  # type: ignore[arg-type]
    assert failed.canonical_subject_identity == "NSE-EQ-TCS"
    assert outcome.batch is None and outcome.pointer is None
    assert store.load_current(request.market_family) is None


def test_natgas_held_fails_before_analytical_result_or_pointer(tmp_path) -> None:
    mapping = _opening_inputs("MCX-SUBJECT-NATGAS", subject_exchange="MCX")[4]
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=mapping.market_session_identity,
        analysis_boundary=mapping.analysis_boundary,
        member_evidence=(mapping,),
        unavailable_members=(),
        provenance=PROVENANCE,
    )
    probable = run.results[0]
    # NATGAS is HELD upstream and therefore cannot become an admitted V2
    # Probable or a valid WO-10 request.  No application/policy evaluation or
    # synthetic seven-state outcome is possible.
    with pytest.raises(Wo10ContractError, match="WO10_REQUEST_INPUT_INVALID"):
        create_wo10_reconciliation_request(
            run=run,
            results=(probable,),
            market_family=IntradayMarketFamily.MCX,
            policy=_policy(IntradayMarketFamily.MCX),
            requested_at=REQUESTED_AT,
            sponsor_operation_identity="SPONSOR-WO10-NATGAS-HELD-TEST",
            provenance=PROVENANCE,
        )
    assert not (tmp_path / "wo10").exists()
