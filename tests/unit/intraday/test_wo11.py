from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.application.intraday_wo11 import (
    IntradayWo11Application,
    IntradayWo11RuntimeService,
    Wo11ApplicationError,
)
from kronos.intraday.wo10 import (
    Wo10OperationOutcome,
    Wo10OperationStage,
    Wo10ReasonCode,
    Wo10ReasonScope,
    Wo10State,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
    create_wo10_reconciliation_result,
)
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo11 import (
    WO11_CONTRACT_VERSION,
    WO11_PUBLICATION_IDENTITY,
    Wo11ContractError,
    Wo11DownstreamEligibility,
    create_wo11_handoff_reference,
    create_wo11_publication_request,
    create_wo11_source_batch_binding,
    eligibility_for_state,
)
from kronos.intraday.wo11_persistence import Wo11PersistenceError, Wo11Store

from .test_wo10_contracts import PROVENANCE, REQUESTED_AT, _bundle


def _retain_source(
    wo10: Wo10Store,
    *,
    subject: str = "NSE-EQ-RELIANCE",
    exchange: str = "NSE",
    state: Wo10State = Wo10State.PROMOTION_READY,
):  # type: ignore[no-untyped-def]
    _, _, request, snapshot, original = _bundle(subject, exchange)
    reason = Wo10ReasonCode(
        Wo10ReasonScope.COMMON,
        "REQUIRED_EVIDENCE_INCOMPLETE" if state is Wo10State.CONTEXT_INCOMPLETE else "GOVERNED_EVIDENCE_COHERENT",
        request.policy.policy_identity,
    )
    result = create_wo10_reconciliation_result(
        request=request,
        evidence=snapshot,
        state=state,
        reasons=(reason,),
        provenance=PROVENANCE,
    )
    assert result.inherited_direction is original.inherited_direction
    batch = create_wo10_batch_result(
        request=request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=PROVENANCE,
    )
    operation = create_wo10_operation_provenance(
        request=request,
        stage=Wo10OperationStage.BATCH_PUBLICATION,
        outcome=Wo10OperationOutcome.COMPLETED,
        started_at=REQUESTED_AT,
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        results=(result,),
        batch=batch,
        provenance=PROVENANCE,
    )
    for retain, value in (
        (wo10.retain_policy, request.policy),
        (wo10.retain_request, request),
        (wo10.retain_evidence_snapshot, snapshot),
        (wo10.retain_result, result),
        (wo10.retain_batch, batch),
        (wo10.retain_operation, operation),
    ):
        retain(value)
    wo10.publish_current(create_current_wo10_pointer(request, batch))
    return create_wo11_source_batch_binding(
        batch=batch, request=request, operation=operation
    ), request, result


def _request(*sources):  # type: ignore[no-untyped-def]
    return create_wo11_publication_request(
        source_batches=sources,
        requested_at=REQUESTED_AT + timedelta(minutes=2),
        sponsor_operation_identity="SPONSOR-WO11-TEST",
        provenance=("KRONOS-WO11-TEST",),
    )


@pytest.mark.parametrize("state", tuple(Wo10State))
def test_all_seven_states_pass_through_and_only_promotion_ready_is_eligible(
    tmp_path, state: Wo10State
) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, request, result = _retain_source(wo10, state=state)
    app = IntradayWo11Application(
        wo10_store=wo10,
        store=Wo11Store((tmp_path / "wo11").resolve()),
    )

    execution = app.execute(_request(source))
    member = execution.members[0]

    assert member.wo10_state is state
    assert member.inherited_direction is result.inherited_direction
    assert member.wo10_policy == request.policy
    assert member.wo10_result_identity == result.result_identity
    assert member.downstream_eligibility is eligibility_for_state(state)
    assert execution.publication.eligible_count == (1 if state is Wo10State.PROMOTION_READY else 0)
    assert execution.publication.schema_identity == WO11_PUBLICATION_IDENTITY
    assert execution.publication.schema_version == WO11_CONTRACT_VERSION


def test_cross_family_collation_preserves_lineage_without_ranking(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    equity, _, _ = _retain_source(wo10, subject="NSE-EQ-RELIANCE")
    index, _, _ = _retain_source(wo10, subject="NSE-INDEX-NIFTY")
    mcx, _, _ = _retain_source(wo10, subject="MCX-SUBJECT-GOLDM", exchange="MCX")
    execution = IntradayWo11Application(
        wo10_store=wo10,
        store=Wo11Store((tmp_path / "wo11").resolve()),
    ).execute(_request(mcx, equity, index))

    assert [item.market_family.value for item in execution.publication.family_counts] == [
        "NSE_EQUITY", "NSE_INDEX", "MCX"
    ]
    assert [item.canonical_subject_identity for item in execution.members] == [
        "NSE-EQ-RELIANCE", "NSE-INDEX-NIFTY", "MCX-SUBJECT-GOLDM"
    ]
    assert not hasattr(execution.publication, "score")
    assert not hasattr(execution.publication, "rank")
    assert not hasattr(execution.publication, "priority")


def test_persistence_is_immutable_explicit_and_restores_without_wo10(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    store = Wo11Store((tmp_path / "wo11").resolve())
    app = IntradayWo11Application(wo10_store=wo10, store=store)
    execution = app.execute(_request(source))

    restored = IntradayWo11RuntimeService(
        IntradayWo11Application(wo10_store=wo10, store=store)
    ).status.restored
    assert restored is not None
    assert restored.publication == execution.publication
    assert restored.members == execution.members
    assert store.load_publication(execution.publication.publication_identity) == execution.publication
    assert store.load_member(execution.members[0].member_identity) == execution.members[0]
    handoff = store.load_handoff(
        execution.publication.publication_identity,
        execution.members[0].member_identity,
    )
    assert handoff.inherited_direction is execution.members[0].inherited_direction
    assert store.retain_publication(execution.publication).exists()


def test_noneligible_member_cannot_cross_exact_handoff_seam(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10, state=Wo10State.CONTEXT_INCOMPLETE)
    execution = IntradayWo11Application(
        wo10_store=wo10,
        store=Wo11Store((tmp_path / "wo11").resolve()),
    ).execute(_request(source))
    with pytest.raises(Wo11ContractError, match="WO11_HANDOFF_INPUT_INVALID"):
        create_wo11_handoff_reference(execution.publication, execution.members[0])


def test_wrong_or_corrupt_source_fails_closed_without_replacing_pointer(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    store = Wo11Store((tmp_path / "wo11").resolve())
    app = IntradayWo11Application(wo10_store=wo10, store=store)
    first = app.execute(_request(source))
    pointer = store.load_current()

    wrong = replace(source, batch_integrity="INTEGRITY-WRONG")
    with pytest.raises(Wo11ApplicationError, match="WO11_WO10_SOURCE_BINDING_INVALID"):
        app.execute(_request(wrong))
    assert store.load_current() == pointer

    batch_path = wo10.root / "batches" / f"{source.batch_identity}.json"
    batch_path.write_bytes(batch_path.read_bytes().replace(b"INTRADAY", b"XNTRADAY", 1))
    changed_request = create_wo11_publication_request(
        source_batches=(source,),
        requested_at=REQUESTED_AT + timedelta(minutes=3),
        sponsor_operation_identity="SPONSOR-WO11-CORRUPTION-TEST",
        provenance=("KRONOS-WO11-TEST",),
    )
    with pytest.raises(Wo11ApplicationError):
        app.execute(changed_request)
    assert store.load_current() == pointer
    assert first.publication == store.load_publication(first.publication.publication_identity)


def test_changed_request_changes_identity_and_direction_mutation_is_rejected(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    first = _request(source)
    second = create_wo11_publication_request(
        source_batches=(source,),
        requested_at=first.requested_at + timedelta(seconds=1),
        sponsor_operation_identity=first.sponsor_operation_identity,
        provenance=first.provenance,
    )
    assert first.request_identity != second.request_identity

    execution = IntradayWo11Application(
        wo10_store=wo10,
        store=Wo11Store((tmp_path / "wo11").resolve()),
    ).execute(first)
    with pytest.raises(Wo11ContractError, match="WO11_MEMBER_INVALID"):
        replace(execution.members[0], inherited_direction="LONG")


def test_conflicting_or_corrupt_wo11_artifacts_fail_closed(tmp_path) -> None:
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    store = Wo11Store((tmp_path / "wo11").resolve())
    execution = IntradayWo11Application(wo10_store=wo10, store=store).execute(_request(source))
    path = store.root / "publications" / f"{execution.publication.publication_identity}.json"
    path.write_bytes(path.read_bytes().replace(b"INTRADAY", b"XNTRADAY", 1))
    with pytest.raises(Wo11PersistenceError, match="WO11_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_current()
    with pytest.raises(Wo11PersistenceError, match="WO11_PERSISTENCE_CONFLICT"):
        store.retain_publication(execution.publication)
