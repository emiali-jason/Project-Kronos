from __future__ import annotations

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_wo10 import IntradayWo10Application
from kronos.application.intraday_wo10_runtime import RuntimeWo10PolicyRegistry
from kronos.application.intraday_wo10_runtime import (
    RetainedWo10EvidenceLoader,
    RuntimeWo10EvidenceAssembler,
)
from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_mcx_paired_persistence import (
    IntradayMcxPairedReviewStore,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo14_persistence import Wo14Store
from kronos.intraday.wo10_policies import (
    Wo10PolicyRegistry,
    wo10_equity_policy_binding,
    wo10_index_policy_binding,
    wo10_mcx_policy_binding,
)
from kronos.intraday.wo10 import create_wo10_reconciliation_request, Wo10State
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import IntradayReviewV2Transport
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import (
    _completed_batch_payload,
    _resolver,
)
from tests.unit.intraday.test_wo10_application import _Assembler, _Policy
from tests.unit.intraday.test_wo10_contracts import _bundle
from tests.unit.provider.test_shared_provider_runtime import _shared


def test_central_runtime_owns_single_reused_v2_and_wo10_composition(tmp_path) -> None:
    shared, provider, factory_calls = _shared()
    root = tmp_path.resolve()

    composition = create_intraday_runtime(shared, evidence_root=root)

    assert type(composition.probables_v2_store) is ProbablesV2Store
    assert composition.review_v2_application.probables_store is composition.probables_v2_store
    assert composition.wo10_application._run_store is composition.probables_v2_store
    assert composition.wo10_application._store is composition.wo10_store
    assert type(composition.wo10_store) is Wo10Store
    assert type(composition.wo12_v2_store) is Wo12V2Store
    assert composition.wo12_v2_application.store is composition.wo12_v2_store
    assert composition.wo12_v2_application.wo11_store is composition.wo11_store
    assert composition.wo12_v2_runtime.application is composition.wo12_v2_application
    assert composition.wo12_v2_runtime.status.state == "NOT_YET_RUN"
    assert composition.wo12_v2_runtime.last_execution is None
    assert type(composition.wo13_store) is Wo13Store
    assert composition.wo13_application.store is composition.wo13_store
    assert composition.wo13_restoration.restore().state == "NOT_YET_RUN"
    assert type(composition.wo14_store) is Wo14Store
    assert composition.wo14_application.store is composition.wo14_store
    assert composition.wo14_application.wo13_store is composition.wo13_store
    assert composition.wo14_restoration.restore().state == "NOT_YET_RUN"
    assert type(composition.wo10_policy_registry) is RuntimeWo10PolicyRegistry
    assert type(composition.mcx_paired_review_store) is IntradayMcxPairedReviewStore
    assert composition.mcx_paired_review_application._store is composition.mcx_paired_review_store
    assert {item.state for item in composition.wo10_runtime.family_statuses} == {
        "NOT_YET_RUN"
    }
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []


def test_exact_three_family_policy_registry_has_no_default_or_cross_family_fallback(
    tmp_path,
) -> None:
    shared, _, _ = _shared()
    composition = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())
    registry = composition.wo10_policy_registry

    assert registry.resolve(wo10_equity_policy_binding()).binding == wo10_equity_policy_binding()
    assert registry.resolve(wo10_index_policy_binding()).binding == wo10_index_policy_binding()
    assert registry.resolve(wo10_mcx_policy_binding()).binding == wo10_mcx_policy_binding()


def test_startup_restores_current_without_policy_evaluation_or_provider_calls(tmp_path) -> None:
    root = tmp_path.resolve()
    run, probable, request, snapshot, _ = _bundle()
    probables = ProbablesV2Store(root)
    probables.retain_result(probable)
    probables.retain_run(run)
    store = Wo10Store(root / "wo10-reconciliation-v2")
    policy = _Policy(request.policy)
    seed = IntradayWo10Application(
        run_store=probables,
        store=store,
        policy_registry=Wo10PolicyRegistry((policy,)),
        evidence_assembler=_Assembler(snapshot),
    )
    expected = seed.execute(request)
    assert expected.completed and policy.calls == 1
    shared, provider, factory_calls = _shared()

    composition = create_intraday_runtime(shared, evidence_root=root)

    status = next(
        item for item in composition.wo10_runtime.family_statuses
        if item.market_family is IntradayMarketFamily.NSE_EQUITY
    )
    assert status.state == "LOADED"
    assert status.restored is not None
    assert status.restored.pointer == expected.pointer
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []


def test_corrupt_wo10_pointer_is_sanitized_without_blocking_runtime(tmp_path) -> None:
    root = tmp_path.resolve()
    pointer = (
        root
        / "wo10-reconciliation-v2"
        / "current"
        / "CURRENT-NSE_EQUITY-WO10-V2.json"
    )
    pointer.parent.mkdir(parents=True)
    pointer.write_bytes(b"{}")
    shared, provider, factory_calls = _shared()

    composition = create_intraday_runtime(shared, evidence_root=root)

    status = next(
        item for item in composition.wo10_runtime.family_statuses
        if item.market_family is IntradayMarketFamily.NSE_EQUITY
    )
    assert status.state == "CORRUPT"
    assert status.failure_stage == "RESTORATION"
    assert status.failure_reason == "WO10_RESTORATION_FAILED"
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []


def test_retained_v2_loader_executes_exact_equity_request_without_provider(
    tmp_path,
) -> None:
    root = tmp_path.resolve()
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    probable = next(item for item in run.results if item.direction is not None)
    probables = ProbablesV2Store(root)
    probables.retain_complete(run=run, mappings=(mapping,))
    review_store = IntradayReviewV2Store(root / "review-v2")
    review = IntradayReviewV2Application(
        probables_store=probables,
        review_store=review_store,
        transport=IntradayReviewV2Transport(
            question_outbox=(root / "questions").resolve(),
            answer_inbox=(root / "answers").resolve(),
        ),
        visual_identity_resolver=_resolver(run.analysis_boundary),
    )
    cycle = review.create_eligible_cycles(run)[0]
    review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(93))
    transport = review.create_combined_question_transport()
    review.import_combined_answer(
        _completed_batch_payload(
            transport.answer_template_path, "Reliance Industries Ltd"
        )
    )
    store = Wo10Store(root / "wo10-reconciliation-v2")
    registry = RuntimeWo10PolicyRegistry()
    loader = RetainedWo10EvidenceLoader(
        probables=probables, review=review_store, registry=registry
    )
    application = IntradayWo10Application(
        run_store=probables,
        store=store,
        policy_registry=registry,
        evidence_assembler=RuntimeWo10EvidenceAssembler(loader),
    )
    request = create_wo10_reconciliation_request(
        run=run,
        results=(probable,),
        market_family=IntradayMarketFamily.NSE_EQUITY,
        policy=wo10_equity_policy_binding(),
        requested_at=run.analysis_boundary,
        sponsor_operation_identity="SPONSOR-WO10-RUNTIME-FIXTURE",
        provenance=("SLICE-8-TEST",),
    )

    outcome = application.execute(request)

    assert outcome.completed
    assert outcome.candidates[0].state == Wo10State.CONTEXT_INCOMPLETE.value
    assert store.restore_current(IntradayMarketFamily.NSE_EQUITY) is not None
