"""Branch B actual application denial and immutable historical compatibility."""
from dataclasses import replace
from datetime import timedelta
import pytest
from kronos.application.intraday_wo09 import IntradayWo09Application
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.intraday.wo09_readiness import CurrentnessState, evaluate_readiness
from kronos.intraday.evidence_currentness import NewWorkNotEligible, EligibilityReason
from tests.unit.intraday.test_wo09_readiness import NOW, evaluated, source, evidence
from tests.unit.intraday.recovery_r2b_fixtures import historical_handoff


def estate(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('supplied', [None, NOW, NOW-timedelta(seconds=1), NOW+timedelta(seconds=1)])
def test_no_caller_time_establishes_first_event(tmp_path,supplied):
    record, requirements=evaluated(); store=Wo09Store(tmp_path)
    store.retain(record,requirements,expected=store.expectation(record.canonical_subject_identity)); before=estate(tmp_path); events=[]
    store.notification_listener=lambda *args:events.append(args)
    with pytest.raises(NewWorkNotEligible) as caught:
        IntradayWo09Application(store).create_handoff(record,created_at=NOW,first_five_of_five_at=supplied)
    assert caught.value.reason is EligibilityReason.FIRST_FIVE_TIME_NOT_ESTABLISHED
    assert estate(tmp_path)==before and events==[] and not store.handoffs.exists()


@pytest.mark.parametrize('subject,session', [('NSE-EQ-LUPIN','NSE-2026-09-11'),('NSE-EQ-OTHER','OTHER'),('MCX-FUT-COPPER','MCX-2026-09-11')])
def test_subject_or_session_label_cannot_substitute_provenance(tmp_path,subject,session):
    # Lawful readiness fixtures, no claimed original event in any subject/session.
    record,req=evaluate_readiness(source(subject=subject),evidence(subject=subject,session_identity=session),created_at=NOW)
    store=Wo09Store(tmp_path);store.retain(record,req,expected=store.expectation(record.canonical_subject_identity))
    with pytest.raises(NewWorkNotEligible,match='FIRST_FIVE_TIME_NOT_ESTABLISHED'):
        IntradayWo09Application(store).create_handoff(record,created_at=NOW,first_five_of_five_at=NOW)
    assert not store.handoffs.exists()


def test_superseded_lineage_preserves_original_failure(tmp_path):
    record, req=evaluated();store=Wo09Store(tmp_path);store.retain(record,req,expected=store.expectation(record.canonical_subject_identity))
    store.mark_currentness(record.canonical_subject_identity,CurrentnessState.SUPERSEDED,updated_at=NOW+timedelta(seconds=1),expected=store.expectation(record.canonical_subject_identity))
    with pytest.raises(ValueError,match='SOURCE_NOT_CURRENT') as caught:
        IntradayWo09Application(store).create_handoff(record,created_at=NOW+timedelta(seconds=2),first_five_of_five_at=NOW)
    assert type(caught.value) is ValueError


def test_later_readiness_time_is_not_original_time_and_history_is_immutable(tmp_path):
    record,req=evaluated();store=Wo09Store(tmp_path);store.retain(record,req,expected=store.expectation(record.canonical_subject_identity))
    historical=historical_handoff(store,record,created_at=NOW,first_five_of_five_at=NOW)
    before=estate(tmp_path)
    for offset in [1,30,299]:
        with pytest.raises(NewWorkNotEligible):
            IntradayWo09Application(store).create_handoff(record,created_at=NOW+timedelta(seconds=offset),first_five_of_five_at=NOW+timedelta(seconds=offset))
    assert store.load_handoff(historical.handoff_identity)==historical
    assert estate(tmp_path)==before


def test_storage_failure_is_not_a_provenance_denial(tmp_path,monkeypatch):
    record,req=evaluated();store=Wo09Store(tmp_path);store.retain(record,req,expected=store.expectation(record.canonical_subject_identity))
    def unavailable(*args):raise OSError('DISPOSABLE_STORE_FAILURE')
    monkeypatch.setattr(store,'load_pointer',unavailable)
    with pytest.raises(OSError,match='DISPOSABLE_STORE_FAILURE'):
        IntradayWo09Application(store).create_handoff(record,created_at=NOW)
