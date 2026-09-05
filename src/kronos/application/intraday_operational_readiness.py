"""WO-B Browser/runtime composition over persisted Intraday evidence only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.instrument.semantic_v2 import InstrumentSemanticPublicationV2
from kronos.intraday.market_context import (
    CurrentMarketCalendarScheduleSource,
    IntradayMarketContextAdapter,
)
from kronos.intraday.operational_readiness import (
    WO_B_AUTHORITY,
    WO_B_CONTRACT_VERSION,
    WO_B_POLICY_IDENTITY,
    WO_B_POLICY_VERSION,
    WO_B_PRODUCT_IDENTITY,
    WoBOperationalReviewSnapshot,
    WoBSourceBoundary,
)
from kronos.intraday.operational_readiness_composition import (
    WoBCompositionError,
    WoBCompositionRequest,
    adapt_domain_001_source,
    adapt_domain_001_v2_source,
    adapt_domain_008_source,
    adapt_probables_source,
    adapt_promotion_source,
    adapt_wo13_source,
    adapt_wo14_source,
    adapt_wo15_source,
    adapt_wo16_source,
    adapt_wo17_source,
    publish_operational_review,
    reconstruct_operational_review,
)
from kronos.intraday.operational_readiness_persistence import (
    RestoredWoBState,
    WoBPersistenceError,
    WoBStore,
    safe_wo_b_failure_reason,
    wo_b_exception_reason,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_session_lineage import load_probables_session_envelope
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo14_persistence import Wo14Store
from kronos.intraday.wo15_persistence import Wo15Store
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.wo17_persistence import Wo17Store
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import MarketDaySchedule


class WoBRuntimeState(StrEnum):
    NOT_YET_RUN = "NOT_YET_RUN"
    RESTORED = "RESTORED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    CORRUPT = "CORRUPT"


class WoBRequestLoader(Protocol):
    def current_requests(self, observed_at: datetime) -> tuple[WoBCompositionRequest, ...]: ...


@dataclass(frozen=True, slots=True)
class WoBRuntimeProjection:
    state: WoBRuntimeState
    reviews: tuple[WoBOperationalReviewSnapshot, ...]
    latest_failures: tuple[dict[str, object], ...]
    failure_reason: str | None = None


class PersistedWoBRequestLoader:
    """Read exact current producer pointers without invoking any producer."""

    def __init__(
        self,
        *,
        probables: ProbablesV2Store,
        catalogue: InstrumentSemanticPublicationV2,
        active_derivatives: ActiveDerivativeBindingStore,
        calendar: MarketCalendarPublisher,
        wo12: Wo12V2Store,
        wo13: Wo13Store,
        wo14: Wo14Store,
        wo15: Wo15Store,
        wo16: Wo16Store,
        wo17: Wo17Store,
    ) -> None:
        self._probables = probables
        self._catalogue = catalogue
        self._active_derivatives = active_derivatives
        self._calendar = calendar
        self._wo12 = wo12
        self._wo13 = wo13
        self._wo14 = wo14
        self._wo15 = wo15
        self._wo16 = wo16
        self._wo17 = wo17

    def current_requests(self, observed_at: datetime) -> tuple[WoBCompositionRequest, ...]:
        pointer = self._probables.load_current()
        run = self._probables.load_current_run()
        if pointer is None or run is None:
            return ()
        admitted = tuple(
            result for result in run.results
            if result.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        )
        try:
            envelope = (
                load_probables_session_envelope(self._probables.root, run)
                if admitted else None
            )
        except (ValueError, OSError) as error:
            raise WoBCompositionError("WO_B_PROBABLES_CURRENT_BINDING_MISMATCH") from error
        downstream = self._restore_downstream()
        requests = []
        for result in admitted:
            family = _family(result.canonical_subject_identity)
            active = (
                self._active_derivatives.load_current(
                    canonical_subject_id=result.canonical_subject_identity
                )
                if family is IntradayMarketFamily.MCX
                else None
            )
            instrument_identity = (
                active.provider_symbol if active is not None
                else result.canonical_subject_identity
            )
            anchor, probable = adapt_probables_source(
                run=run,
                result=result,
                current_pointer=pointer,
                canonical_instrument_identity=instrument_identity,
                active_contract_identity=(
                    None if active is None
                    else active.active_binding.derivative_contract_id
                ),
                opportunity_identity=result.result_identity,
                source_mapping=(
                    self._probables.load_mapping(result.source_mapping_identity)
                    if result.source_mapping_identity is not None
                    else None
                ),
                replay_envelope=envelope,
            )
            sources = [probable]
            if active is not None:
                sources.append(adapt_domain_001_source(
                    anchor=anchor,
                    active_derivative=active,
                    review_boundary=observed_at,
                ))
            else:
                matches = tuple(
                    item for item in self._catalogue.semantic_objects
                    if item.canonical_id == result.canonical_subject_identity
                )
                if len(matches) != 1:
                    raise WoBCompositionError("WO_B_DOMAIN_001_BINDING_UNAVAILABLE")
                sources.append(adapt_domain_001_v2_source(
                    anchor=anchor,
                    publication=self._catalogue,
                    semantic_object=matches[0],  # type: ignore[arg-type]
                    review_boundary=observed_at,
                ))
            trading_date = run.analysis_boundary.astimezone(
                ZoneInfo("Asia/Kolkata")
            ).date()
            schedule_source = (
                _mcx_schedule_source(
                    self._calendar,
                    active=active,
                    trading_date=trading_date,
                    # Resolve the retained session at its historical boundary;
                    # session_facts below still evaluates currentness at review time.
                    observed_at=run.analysis_boundary,
                )
                if active is not None
                else CurrentMarketCalendarScheduleSource(
                    self._calendar,
                    observed_at=observed_at,
                    canonical_instrument_id=result.canonical_subject_identity,
                )
            )
            fact = IntradayMarketContextAdapter(schedule_source).session_facts(
                exchange="MCX" if family is IntradayMarketFamily.MCX else "NSE",
                trading_date=trading_date,
                observed_at=observed_at,
            )
            sources.append(adapt_domain_008_source(anchor=anchor, fact=fact))
            self._append_exact_downstream(sources, anchor, downstream)
            requests.append(WoBCompositionRequest(
                anchor=anchor,
                review_boundary=observed_at,
                created_at=observed_at,
                sources=tuple(sources),
                provenance=("ADR-0029", "WO-B3", "PERSISTED-SOURCES-ONLY"),
            ))
        return tuple(sorted(requests, key=lambda item: item.anchor.candidate_identity))

    def _restore_downstream(self) -> tuple[object | None, ...]:
        return (
            self._wo12.restore_current(),
            self._wo13.restore_current(),
            self._wo14.restore_current(),
            self._wo15.restore_current(),
        )

    def _append_exact_downstream(self, sources, anchor, restored) -> None:  # type: ignore[no-untyped-def]
        wo12, wo13, wo14, wo15 = restored
        if (
            wo12 is None
            or wo12.handoff.probables_run_identity != anchor.analysis_run_identity
            or wo12.handoff.probable_result_identity != anchor.candidate_identity
        ):
            return
        sources.append(adapt_promotion_source(
            anchor=anchor,
            handoff=wo12.handoff,
            result=wo12.result,
            current_pointer=wo12.pointer,
        ))
        if (
            wo13 is None
            or wo13.handoff.wo12_result_identity != wo12.result.result_identity
            or wo13.pointer.analysis_boundary != wo12.handoff.analysis_boundary
        ):
            return
        sources.append(adapt_wo13_source(
            anchor=anchor, plan=wo13.trade_plan, current_pointer=wo13.pointer
        ))
        if (
            wo14 is not None
            and wo14.pointer.trade_plan_identity == wo13.trade_plan.trade_plan_identity
        ):
            sources.append(adapt_wo14_source(
                anchor=anchor,
                observation=wo14.observation,
                current_pointer=wo14.pointer,
                trade_plan=wo13.trade_plan,
            ))
        if (
            wo15 is not None
            and wo15.pointer.wo13_trade_plan_identity == wo13.trade_plan.trade_plan_identity
        ):
            sources.append(adapt_wo15_source(
                anchor=anchor,
                current_pointer=wo15.pointer,
                handoff=wo15.timing_handoff,
            ))
        if wo14 is None or wo15 is None:
            return
        wo16 = self._wo16.restore_current(anchor.canonical_subject_identity)
        if (
            wo16 is None
            or wo16.pointer.wo13_trade_plan_identity != wo13.trade_plan.trade_plan_identity
            or wo16.pointer.wo14_observation_identity != wo14.observation.observation_identity
            or wo15.timing_handoff is None
            or wo16.pointer.wo15_handoff_identity != wo15.timing_handoff.handoff_identity
        ):
            return
        sources.append(adapt_wo16_source(
            anchor=anchor,
            snapshot=wo16.snapshot,
            decision=wo16.decision,
            admission=wo16.admission,
            current_pointer=wo16.pointer,
        ))
        wo17 = self._wo17.restore_current(anchor.canonical_subject_identity)
        if (
            wo17 is None
            or wo17.snapshot.lineage.current_wo16_pointer_identity
            != wo16.pointer.pointer_identity
        ):
            return
        sources.append(adapt_wo17_source(
            anchor=anchor,
            current_pointer=wo17.pointer,
            position=wo17.position,
            lifecycle=wo17.lifecycle,
        ))


class IntradayOperationalReadinessRuntimeService:
    """Pure Browser projection plus an explicit WO-B-only publication seam."""

    def __init__(
        self,
        *,
        loader: WoBRequestLoader,
        store: WoBStore,
        clock: Callable[[], datetime],
    ) -> None:
        self._loader = loader
        self._store = store
        self._clock = clock
        self._restoration_failure: str | None = None
        self._restored = self._restore()

    @property
    def store(self) -> WoBStore:
        return self._store

    def preview(self) -> WoBRuntimeProjection:
        """Compose from persisted upstream facts without writing any artifact."""

        if self._restoration_failure is not None:
            return WoBRuntimeProjection(
                WoBRuntimeState.CORRUPT,
                tuple(item.snapshot for item in self._restored),
                self._failure_documents(self._restored),
                self._restoration_failure,
            )
        try:
            requests = self._loader.current_requests(self._clock())
            reviews = tuple(reconstruct_operational_review(item) for item in requests)
            return WoBRuntimeProjection(
                WoBRuntimeState.AVAILABLE if reviews else WoBRuntimeState.NOT_YET_RUN,
                reviews,
                self._failure_documents(self._restored),
            )
        except Exception as error:
            return WoBRuntimeProjection(
                WoBRuntimeState.UNAVAILABLE,
                tuple(item.snapshot for item in self._restored),
                self._failure_documents(self._restored),
                _safe_reason(error),
            )

    def rebuild(self) -> WoBRuntimeProjection:
        """Explicitly publish only WO-B artifacts; never invoke upstream work."""

        requests = self._loader.current_requests(self._clock())
        published = []
        for request in requests:
            try:
                published.append(publish_operational_review(request, store=self._store).snapshot)
            except (WoBCompositionError, WoBPersistenceError):
                raise
        self._restored = self._restore()
        return WoBRuntimeProjection(
            WoBRuntimeState.AVAILABLE if published else WoBRuntimeState.NOT_YET_RUN,
            tuple(published),
            self._failure_documents(self._restored),
        )

    def status_document(self) -> dict[str, object]:
        projection = self.preview()
        return {
            "product_identity": WO_B_PRODUCT_IDENTITY,
            "product_version": WO_B_CONTRACT_VERSION,
            "policy_identity": WO_B_POLICY_IDENTITY,
            "policy_version": WO_B_POLICY_VERSION,
            "authority": WO_B_AUTHORITY,
            "runtime_loaded": True,
            "restoration_state": projection.state.value,
            "operation_state": "IDLE",
            "busy": False,
            "active_request": None,
            "reviews": tuple(_review_document(item) for item in projection.reviews),
            "latest_failures": projection.latest_failures,
            "failure_reason": projection.failure_reason,
            "provider_calls": 0,
            "upstream_operations": 0,
            "sponsor_operations": 0,
            "lifecycle_mutations": 0,
            "position_mutations": 0,
            "monitoring_mutations": 0,
            "broker_operations": 0,
        }

    def _restore(self) -> tuple[RestoredWoBState, ...]:
        restored: list[RestoredWoBState] = []
        try:
            for candidate in self._store.current_candidates():
                restored.append(self._store.restore_current(candidate))
        except Exception as error:
            self._restoration_failure = _safe_reason(error)
        else:
            self._restoration_failure = None
        return tuple(restored)

    @staticmethod
    def _failure_documents(restored: tuple[RestoredWoBState, ...]) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "candidate_identity": item.latest_failure.candidate_identity,
                "stage": item.latest_failure.stage.value,
                "reason": safe_wo_b_failure_reason(item.latest_failure.reason),
                "failed_at": item.latest_failure.failed_at.isoformat(),
            }
            for item in restored if item.latest_failure is not None
        )


def _review_document(snapshot: WoBOperationalReviewSnapshot) -> dict[str, object]:
    next_stage = next(
        (item.next_governed_stage for item in snapshot.review_items if item.next_governed_stage),
        None,
    )
    sponsor_attention = next_stage == WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE.value
    probable = next(
        item for item in snapshot.review_items
        if item.source_boundary is WoBSourceBoundary.PROBABLES
    )
    direction = {
        "LONG_PROBABLE": "LONG",
        "SHORT_PROBABLE": "SHORT",
    }.get(probable.exact_source_state, "UNAVAILABLE")
    return {
        "review_snapshot_identity": snapshot.review_snapshot_identity,
        "candidate_identity": snapshot.candidate_identity,
        "opportunity_identity": snapshot.opportunity_identity,
        "analysis_run_identity": snapshot.analysis_run_lineage[-1],
        "canonical_subject_identity": snapshot.canonical_subject_identity,
        "canonical_instrument_identity": snapshot.canonical_instrument_identity,
        "market_family": snapshot.market_family.value,
        "direction": direction,
        "active_contract_identity": snapshot.active_contract_identity,
        "review_boundary": snapshot.review_boundary.isoformat(),
        "created_at": snapshot.created_at.isoformat(),
        "next_governed_stage": next_stage,
        "sponsor_attention_available": sponsor_attention,
        "items": tuple({
            "source_boundary": item.source_boundary.value,
            "source_state": item.exact_source_state,
            "source_reason": item.exact_source_reason,
            "classification": item.review_classification.value,
            "classification_basis": item.classification_basis.value,
            "diagnostic": item.bounded_diagnostic,
            "next_governed_stage": item.next_governed_stage,
            "source_reference_identity": item.source_reference_identity,
        } for item in snapshot.review_items),
        "source_references": tuple({
            "source_boundary": item.source_boundary.value,
            "artifact_identity": item.artifact_identity,
            "schema": f"{item.artifact_schema_identity} / {item.artifact_schema_version}",
            "policy": f"{item.source_policy_identity} / {item.source_policy_version}",
            "observed_at": item.observed_at.isoformat(),
            "current": item.current_at_review_boundary,
            "superseded": item.superseded,
        } for item in snapshot.source_artifact_references),
    }


def _family(subject: str) -> IntradayMarketFamily:
    if subject.startswith("MCX-SUBJECT-"):
        return IntradayMarketFamily.MCX
    if subject.startswith("NSE-INDEX-"):
        return IntradayMarketFamily.NSE_INDEX
    if subject.startswith("NSE-EQ-"):
        return IntradayMarketFamily.NSE_EQUITY
    raise WoBCompositionError("WO_B_CANONICAL_SUBJECT_FAMILY_UNAVAILABLE")


def _safe_reason(error: Exception) -> str:
    return wo_b_exception_reason(error)


class _BoundScheduleSource:
    def __init__(self, schedule: MarketDaySchedule | None) -> None:
        self._schedule = schedule

    def schedule_for(self, exchange, trading_date):  # type: ignore[no-untyped-def]
        schedule = self._schedule
        if (
            schedule is None
            or schedule.exchange != exchange
            or schedule.trading_date != trading_date
        ):
            return None
        return schedule


def _mcx_schedule_source(
    calendar: MarketCalendarPublisher,
    *,
    active,
    trading_date,
    observed_at: datetime,
) -> _BoundScheduleSource:
    profile = calendar.mcx_contract_session_profile(
        contract_family=active.provider_contract_family,
        contract_expiry=active.contract_expiry,
        trading_date=trading_date,
        observed_at=observed_at,
    )
    schedule = (
        None if profile.continuous_trading is None
        else CurrentMarketCalendarScheduleSource._adapt(profile.continuous_trading)
    )
    return _BoundScheduleSource(schedule)


__all__ = [
    "IntradayOperationalReadinessRuntimeService",
    "PersistedWoBRequestLoader",
    "WoBRequestLoader",
    "WoBRuntimeProjection",
    "WoBRuntimeState",
]
