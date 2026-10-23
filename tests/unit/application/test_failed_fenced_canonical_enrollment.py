"""Real native owner composition and prospective ledger, synthetic trust input.

No operational approval or Darwin/C-source qualification is substituted by this
component fixture. It executes the actual constructor/listener/accounting path.
"""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import pytest

from kronos.common.failed_fenced_recovery import ProspectiveLedger, RecoveryCodec, SCOPE_HASH, SCOPE_BYTES, PROTOCOL, VERSION
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.application.failed_fenced_owners import (
    ProspectiveComposition, initialize_canonical_roster, enroll_canonical_sources, FINITE_OWNERS,
)
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.intraday.wo10_futures_store import FuturesStore
from kronos.intraday.wo11_lifecycle_store import LifecycleStore
from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
from kronos.application.intraday_notifications import IntradayNotifications
from kronos.application.intraday_journal import IntradayJournalApplication
from kronos.application.intraday_books import IntradayBooks
from kronos.intraday.wo14_journal_store import JournalStore
from tests.unit.common.test_failed_fenced_recovery import private_store, CLOCK, CONTROL, PROCESS
from tests.unit.intraday.test_wo13_notifications import centre, _ResearchOriginSource, _NotificationSourceStore


@pytest.fixture
def native_composition(tmp_path):
    store=private_store(tmp_path)
    bundle=Path(__file__).resolve().parents[3]/'docs/architecture/interfaces/KRONOS-FAILED-FENCED-RECOVERY-V1.md'
    # The exact frozen block is retained by ADR-0068; avoid fixture-directory
    # assumptions about how many levels the isolated candidate was copied.
    raw=bundle.resolve().read_bytes(); marker=b'<<<KRONOS_NORMATIVE_FILE name=SUPPORTED-OWNER-AND-OBLIGATION-SCOPE.md '
    start=raw.index(marker);start=raw.index(b'\n',start)+1
    scope_raw=raw[start:start+int(SCOPE_BYTES)]
    assert sha256(scope_raw).hexdigest()==SCOPE_HASH
    scope={'authority':'CA','contract':PROTOCOL+':'+VERSION,'identity':'FAILED_FENCED_INITIAL_OWNER_SCOPE_V1','hash':SCOPE_HASH,'bytes':SCOPE_BYTES}
    store.write_blob(scope['identity'],scope_raw)
    source=store.write_blob('synthetic-source-inventory',b'[]')
    coordinator=MaintenanceAdmissionCoordinator()
    ledger=ProspectiveLedger.capture(coordinator,RecoveryCodec(CONTROL.encode(),CLOCK),store,PROCESS,scope)
    composition=ProspectiveComposition(ledger,source,scope);ledger.native_composition=composition
    initialize_canonical_roster(composition)
    with ledger.activate():
        wo09=Wo09Store(tmp_path/'wo09');futures=FuturesStore(tmp_path/'futures');lifecycle=LifecycleStore(tmp_path/'lifecycle')
        caller=IntradayLifecycleApplication(futures=None,store=lifecycle,clock=lambda:datetime.now(timezone.utc),
            session_source=None,timing_source=None,operational_guard=lambda:True)
        caller.bind_maintenance_admission(coordinator)
        research=_ResearchOriginSource()
        journal=IntradayJournalApplication(research=research,futures=futures,lifecycle=caller,store=JournalStore(tmp_path/'journal'))
        books=IntradayBooks(research=research,futures=futures,lifecycle=caller)
        notices=IntradayNotifications(centre=centre(tmp_path),research=research,wo09=wo09,futures=futures,lifecycle=lifecycle,background=False)
        notices.bind_maintenance_admission(coordinator)
        notices.bind(_NotificationSourceStore(),defer_start=True);journal.bind();books.bind()
        yield ledger,composition,dict(wo09=wo09,futures=futures,lifecycle=lifecycle,notifications=notices,journal=journal,books=books,caller=caller)
        notices.close()


def test_actual_canonical_sources_and_caller_are_enrolled_before_work(native_composition):
    ledger,composition,owners=native_composition
    adapters=enroll_canonical_sources(composition,**owners)
    assert tuple(a.owner for a in adapters)==('WO09','WO10','WO11')
    assert all(a._reference_group==adapters for a in adapters)
    assert owners['caller']._failed_fenced_accounting is adapters[2]
    assert set(composition._slots)==FINITE_OWNERS and len(composition._listeners)==7
    assert ledger.inventory and ledger._inventory_payload['phase']=='LIVE'
    assert not owners['notifications']._scheduled
    owners['notifications'].start_pending()
    with pytest.raises(ValueError):owners['notifications'].start_pending()
    with pytest.raises(ValueError):enroll_canonical_sources(composition,**owners)


def test_changed_listener_denies_before_any_inventory_or_source_effect(native_composition):
    ledger,composition,owners=native_composition
    owners['lifecycle'].notification_listener=lambda *args:None
    with pytest.raises(ValueError,match='LISTENER_CHANGED'):
        enroll_canonical_sources(composition,**owners)
    assert ledger.inventory is None and not owners['lifecycle'].root.exists()


def test_initial_absence_cannot_be_redeclared_after_construction(native_composition):
    _,composition,_=native_composition
    with pytest.raises(ValueError,match='ALREADY_STARTED'):
        initialize_canonical_roster(composition)


def test_actual_accepted_wo10_source_records_peers_reference_and_original_return(native_composition):
    from kronos.intraday.wo10_futures_contract import record
    from tests.unit.intraday.test_wo09_readiness import NOW
    ledger,composition,owners=native_composition
    enroll_canonical_sources(composition,**owners)
    owners['notifications'].start_pending()
    value=record('WO10_CONSTRUCTION_UNAVAILABLE_V1',subject='NSE-EQ-TEST',direction='LONG',
        readiness_identity='READY',reason='INTERNAL_PARSE_FAILURE',created_at=NOW)
    ticket=ledger.coordinator.admit('BROWSER_POST')
    try:
        with ticket.activate():
            assert owners['futures'].retain(value)==value
        assert owners['futures'].load(value.identity)==value
        assert len(ledger._operations)==2 and len(ledger._peers)==2
        assert all(row['payload']['state']=='COMPLETE' for row in ledger._operations.values())
        assert len(ledger._fulfillments)==2
        assert getattr(owners['futures'],'notification_failure',None) is None
    finally:
        ticket.release()
    assert sum(ledger.coordinator.snapshot()['owners'].values())==0
