from datetime import UTC, datetime, timedelta

import pytest

from tvca import CoreFailureCode, CoreStatus, IdentityChannel, TvcaCore, TvcaCoreError


REQUEST = "12345678-1234-4234-8234-123456789abc"
NOW = datetime(2026, 9, 6, tzinfo=UTC)
A = IdentityChannel.ADAPTER_OBSERVED
V = IdentityChannel.VISUALLY_OBSERVED


def files(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")}


@pytest.mark.parametrize("channels", [(), (A,), (V,), (A, V), (V, A)])
def test_create_observe_in_either_order_and_seal(channels, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    assert record.status is CoreStatus.OPEN and record.revision == 0
    observations = {A: "  Adapter:é  ", V: "Visually DIFFERENT"}
    for index, channel in enumerate(channels, 1):
        predecessor = record
        record = core.record_identity(record.ref, channel, observations[channel], NOW)
        assert record.revision == index
        assert record.previous_record_sha256 == predecessor.ref.sha256
        assert record.expected_subject_identity == "Expected"
        assert record.status is CoreStatus.OPEN
    assert record.adapter_observed_identity == (observations[A] if A in channels else None)
    assert record.visually_observed_identity == (observations[V] if V in channels else None)
    sealed = core.seal(record.ref, NOW)
    assert sealed.status is CoreStatus.SEALED
    assert sealed.adapter_observed_identity == record.adapter_observed_identity
    assert sealed.visually_observed_identity == record.visually_observed_identity
    assert len(files(tmp_path)) == len(channels) + 2


def test_equal_identities_do_not_create_verification_or_reconciliation(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Same", NOW)
    second = core.record_identity(first.ref, A, "Same", NOW)
    third = core.record_identity(second.ref, V, "Same", NOW)
    assert third.status is CoreStatus.OPEN
    assert set(CoreStatus) == {CoreStatus.OPEN, CoreStatus.SEALED}
    assert second.visually_observed_identity is None


@pytest.mark.parametrize("operation", ["seal", "adapter", "visual"])
def test_sealed_is_terminal_and_rejection_preserves_files(operation, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    sealed = core.seal(record.ref, NOW)
    before = files(tmp_path)
    with pytest.raises(TvcaCoreError) as caught:
        if operation == "seal":
            core.seal(sealed.ref, NOW)
        else:
            core.record_identity(sealed.ref, A if operation == "adapter" else V, "raw", NOW)
    assert caught.value.failure.code is CoreFailureCode.INVALID_TRANSITION
    assert files(tmp_path) == before


@pytest.mark.parametrize("value", ["same", "different"])
def test_occupied_channel_cannot_be_rewritten(value, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    second = core.record_identity(first.ref, A, "same", NOW)
    before = files(tmp_path)
    with pytest.raises(TvcaCoreError) as caught:
        core.record_identity(second.ref, A, value, NOW)
    assert caught.value.failure.code is CoreFailureCode.INVALID_TRANSITION
    assert files(tmp_path) == before


@pytest.mark.parametrize("operation", ["seal", "observe"])
def test_backward_timestamp_rejected_without_mutation(operation, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    before = files(tmp_path)
    with pytest.raises(TvcaCoreError) as caught:
        if operation == "seal":
            core.seal(record.ref, NOW - timedelta(microseconds=1))
        else:
            core.record_identity(record.ref, A, "raw", NOW - timedelta(microseconds=1))
    assert caught.value.failure.code is CoreFailureCode.INVALID_INPUT
    assert files(tmp_path) == before


def test_exact_operation_replays_remain_historical_after_later_revisions(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    second = core.record_identity(first.ref, A, "raw", NOW)
    sealed = core.seal(second.ref, NOW)
    before = files(tmp_path)
    assert core.create(REQUEST, "Expected", NOW) == first
    assert core.record_identity(first.ref, A, "raw", NOW) == second
    assert core.seal(second.ref, NOW) == sealed
    assert files(tmp_path) == before


@pytest.mark.parametrize("operation", ["create_identity", "create_time", "observe_value",
                                       "observe_time", "observe_other_channel", "seal"])
def test_conflicting_create_or_stale_predecessor_never_overwrites(operation, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    core.record_identity(first.ref, A, "raw", NOW)
    before = files(tmp_path)
    with pytest.raises(TvcaCoreError) as caught:
        if operation.startswith("create"):
            core.create(REQUEST, "changed" if operation == "create_identity" else "Expected",
                        NOW + timedelta(seconds=1) if operation == "create_time" else NOW)
        elif operation == "seal":
            core.seal(first.ref, NOW)
        else:
            core.record_identity(first.ref, V if operation == "observe_other_channel" else A,
                                 "changed" if operation == "observe_value" else "raw",
                                 NOW + timedelta(seconds=1) if operation == "observe_time" else NOW)
    assert caught.value.failure.code is CoreFailureCode.RECORD_CONFLICT
    assert files(tmp_path) == before


@pytest.mark.parametrize("channel,value", [("ADAPTER_OBSERVED", "raw"),
                                            (A, None), (V, ""), (A, "\x00"),
                                            (V, " \n"), (A, "\udfff")])
def test_invalid_observation_input(channel, value, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    before = files(tmp_path)
    with pytest.raises(TvcaCoreError) as caught:
        core.record_identity(record.ref, channel, value, NOW)
    assert caught.value.failure.code is CoreFailureCode.INVALID_INPUT
    assert files(tmp_path) == before
