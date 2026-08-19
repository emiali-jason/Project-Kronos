from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.application.swing_progression_watch import SwingProgressionWatchWorkflow
from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
    SwingOpportunitiesApplication,
)
from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.progression_watch import (
    ProgressionComparator,
    ProgressionRequirement,
    ProgressionRequirementState,
    ProgressionWatchState,
    ProgressionWatchStore,
)


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
RUN = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"
INSTRUMENT = InstrumentRecord(
    "KITE", "NSE", "NSE", "RELIANCE", "RELIANCE",
    "EQ", None, Decimal("0.05"), 1,
)


def _requirement(run: str = RUN) -> ProgressionRequirement:
    return ProgressionRequirement(
        "1" * 64, "SWING", "RELIANCE", V1Direction.LONG, run, "2" * 64,
        "WAIT_PULLBACK_DEVELOPING", "ONE_HOUR_PROGRESSION",
        "1H close above 1482.5", ProgressionRequirementState.WATCH_AVAILABLE,
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
        1482.5, None, None, ("3" * 64,), NOW, ("KITE",),
    )


class _Session:
    def __init__(self, consumer) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.subscriptions = []
        self.unsubscribe_count = 0
        self.connect_count = 0
        self.disconnect_count = 0

    def subscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.subscriptions.append(instruments)

    def unsubscribe(self, _instruments) -> None:  # type: ignore[no-untyped-def]
        self.unsubscribe_count += 1

    def connect(self) -> None:
        self.connect_count += 1

    def disconnect(self) -> None:
        self.disconnect_count += 1


class _Capability:
    active = True

    def __init__(self) -> None:
        self.sessions = []

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        session = _Session(consumer)
        self.sessions.append(session)
        return session


def _workflow(tmp_path: Path) -> SwingProgressionWatchWorkflow:
    return SwingProgressionWatchWorkflow(
        ProgressionWatchStore(tmp_path), clock=lambda: NOW,
        instrument_resolver=lambda _capability, _identity, _date: INSTRUMENT,
        bar_loader=lambda *_args: None,
    )


def test_explicit_activation_is_current_run_bound_duplicate_safe_and_closes(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    capability = _Capability()
    requirement = _requirement()
    workflow.synchronize(RUN, (requirement,))

    watch = workflow.activate_requirement(requirement.requirement_id, capability)
    duplicate = workflow.activate_requirement(requirement.requirement_id, capability)

    assert watch == duplicate
    assert watch.state is ProgressionWatchState.ACTIVE
    assert workflow.active_monitoring_count == 1
    assert len(capability.sessions) == 1
    assert capability.sessions[0].subscriptions == [(INSTRUMENT,)]
    assert capability.sessions[0].connect_count == 1
    capability.sessions[0].consumer.on_connection_state(MonitoringConnectionState.RECONNECTING)
    assert workflow.active_monitoring_count == 1

    workflow.close_monitoring()
    assert workflow.active_monitoring_count == 0
    assert capability.sessions[0].unsubscribe_count == 1
    assert capability.sessions[0].disconnect_count == 1


def test_ineligible_arbitrary_or_disconnected_activation_fails_closed(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    requirement = _requirement()
    workflow.synchronize(RUN, (requirement,))
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        workflow.activate_requirement("f" * 64, _Capability())
    capability = _Capability()
    capability.active = False
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        workflow.activate_requirement(requirement.requirement_id, capability)


def test_restart_restores_only_same_run_watch_and_stale_run_is_not_rebound(tmp_path: Path) -> None:
    first = _workflow(tmp_path)
    requirement = _requirement()
    first.synchronize(RUN, (requirement,))
    original = first.activate_requirement(requirement.requirement_id, _Capability())
    first.close_monitoring()

    restored = _workflow(tmp_path)
    capability = _Capability()
    restored.synchronize(RUN, (requirement,))
    assert restored.restore_active(capability) == (original.watch_id,)
    assert restored.active_monitoring_count == 1
    restored.close_monitoring()

    stale = _workflow(tmp_path)
    stale.synchronize("SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", ())
    snapshot = stale.snapshot()
    assert snapshot.watches[0].state is ProgressionWatchState.STALE
    other = _Capability()
    assert stale.restore_active(other) == ()
    assert other.sessions == []


def test_provider_connect_disconnect_and_application_close_own_watch_cleanup() -> None:
    capability = _Capability()

    class Provider:
        def begin_login(self):
            return "attempt"

        def complete_callback(self, attempt):
            assert attempt == "attempt"
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
            )

        def authenticated_read_only_capability(self):
            return capability

        def end_kronos_session(self):
            capability.active = False

    class Workflow:
        def __init__(self) -> None:
            self.restored = []
            self.closed = 0

        def activate_requirement(self, _identity, _capability):
            return None

        def restore_active(self, value):
            self.restored.append(value)

        def close_monitoring(self):
            self.closed += 1

    workflow = Workflow()
    application = SwingOpportunitiesApplication(
        Provider,
        background_runner=lambda operation, _name: operation(),
        initial_snapshot=BrowserWorkspaceSnapshot(
            ProviderConnectionState.DISCONNECTED,
            AnalysisState.NOT_RUN,
            98,
        ),
    )
    application.register_progression_watch_workflow(workflow)
    assert application.connect_provider()
    assert workflow.restored == [capability]
    assert application.disconnect_provider()
    assert workflow.closed == 1
    application.close()
    assert workflow.closed == 2
