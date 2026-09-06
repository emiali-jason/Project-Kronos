from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from tvca import (CoreFailure, CoreFailureCode, CoreRecord, CoreStatus,
                  RecordRef, TvcaCoreError)
from tvca.contracts import _canonical, _decode, _validate_successor


REQUEST = "12345678-1234-4234-8234-123456789abc"
NOW = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)


def initial(**changes):
    values = dict(format_version=1, request_id=REQUEST, revision=0,
                  previous_record_sha256=None, status=CoreStatus.OPEN,
                  expected_subject_identity="  NSE:Example-é  ",
                  adapter_observed_identity=None, visually_observed_identity=None,
                  recorded_at=NOW)
    return CoreRecord(**(values | changes))


def test_initial_record_and_three_value_concepts_are_immutable():
    record = initial()
    assert record.status is CoreStatus.OPEN and record.revision == 0
    assert record.ref == RecordRef(REQUEST, 0, record.ref.sha256)
    for value, field, replacement in (
        (record, "revision", 9), (record.ref, "revision", 9),
        (CoreFailure(CoreFailureCode.INVALID_INPUT), "code", CoreFailureCode.RECORD_CONFLICT),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)


@pytest.mark.parametrize("changes", [
    {"format_version": 2}, {"format_version": True}, {"format_version": 1.0},
    {"request_id": REQUEST.upper()}, {"request_id": REQUEST.replace("-", "")},
    {"request_id": "../escape"}, {"request_id": None},
    {"revision": -1}, {"revision": True}, {"revision": 0.0},
    {"revision": 1, "previous_record_sha256": None},
    {"revision": 1, "previous_record_sha256": "A" * 64},
    {"previous_record_sha256": "a" * 64},
    {"recorded_at": NOW.replace(tzinfo=None)}, {"recorded_at": "now"},
    {"expected_subject_identity": ""}, {"expected_subject_identity": " \t\n"},
    {"expected_subject_identity": "NSE\x00X"}, {"expected_subject_identity": "\ud800"},
    {"expected_subject_identity": 123}, {"status": "OPEN"},
    {"status": CoreStatus.SEALED}, {"adapter_observed_identity": "observed"},
    {"visually_observed_identity": "observed"},
])
def test_invalid_core_record(changes):
    with pytest.raises(TvcaCoreError) as caught:
        initial(**changes)
    assert caught.value.failure.code is CoreFailureCode.INVALID_INPUT


@pytest.mark.parametrize("changes", [
    {"request_id": "not-a-uuid"}, {"revision": -1}, {"revision": False},
    {"sha256": "a" * 63}, {"sha256": "A" * 64}, {"sha256": "g" * 64},
    {"sha256": None},
])
def test_invalid_record_reference(changes):
    with pytest.raises(TvcaCoreError) as caught:
        RecordRef(**(dict(request_id=REQUEST, revision=0, sha256="a" * 64) | changes))
    assert caught.value.failure.code is CoreFailureCode.INVALID_INPUT


def test_canonical_bytes_digest_and_exact_identity_roundtrip():
    record = initial()
    offset = timezone(timedelta(hours=5, minutes=30))
    equivalent = replace(record, recorded_at=NOW.astimezone(offset))
    expected = (
        '{"adapter_observed_identity":null,"expected_subject_identity":"  NSE:Example-\\u00e9  ",'
        '"format_version":1,"previous_record_sha256":null,'
        '"recorded_at":"2026-09-06T10:00:00.000000Z","request_id":"'
        + REQUEST + '","revision":0,"status":"OPEN","visually_observed_identity":null}'
    ).encode("utf-8")
    assert _canonical(record) == expected == _canonical(equivalent)
    assert record.ref == equivalent.ref
    assert _decode(expected).expected_subject_identity == "  NSE:Example-é  "
    assert not expected.endswith(b"\n")


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(extra="not allowed"),
    lambda p: p.pop("adapter_observed_identity"),
    lambda p: p.update(format_version=2),
    lambda p: p.update(revision=float("nan")),
    lambda p: p.update(revision=float("inf")),
    lambda p: p.update(status="VERIFIED"),
    lambda p: p.update(recorded_at="2026-09-06T10:00:00"),
])
def test_invalid_persisted_fields(mutate):
    payload = json.loads(_canonical(initial()))
    mutate(payload)
    with pytest.raises(TvcaCoreError) as caught:
        _decode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    assert caught.value.failure.code is CoreFailureCode.INTEGRITY_FAILURE


def test_expected_identity_change_and_two_channel_transition_are_rejected():
    previous = initial()
    successor = replace(previous, revision=1, previous_record_sha256=previous.ref.sha256,
                        adapter_observed_identity="raw")
    for invalid in (replace(successor, expected_subject_identity="different"),
                    replace(successor, visually_observed_identity="second")):
        with pytest.raises(TvcaCoreError) as caught:
            _validate_successor(previous, invalid)
        assert caught.value.failure.code is CoreFailureCode.INVALID_TRANSITION


def test_failure_payload_contains_only_an_approved_code():
    assert {code.value for code in CoreFailureCode} == {
        "INVALID_INPUT", "INVALID_TRANSITION", "RECORD_NOT_FOUND", "RECORD_CONFLICT",
        "INTEGRITY_FAILURE", "STORAGE_ROOT_INVALID", "STORAGE_IO_FAILURE",
    }
    failure = CoreFailure(CoreFailureCode.STORAGE_IO_FAILURE)
    assert str(TvcaCoreError(failure)) == "STORAGE_IO_FAILURE"
    with pytest.raises(TypeError):
        CoreFailure("raw filesystem secret")


def test_repeated_local_hour_is_ordered_by_utc_instant():
    zone = ZoneInfo("America/New_York")
    # The second 01:15 occurs after the first 01:45 during the DST fold.
    first = initial(recorded_at=datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0))
    later = replace(first, revision=1, previous_record_sha256=first.ref.sha256,
                    adapter_observed_identity="raw",
                    recorded_at=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1))
    _validate_successor(first, later)
    earlier = replace(later, recorded_at=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=0))
    with pytest.raises(TvcaCoreError, match="^INVALID_INPUT$"):
        _validate_successor(first, earlier)
