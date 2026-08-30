"""Provider-independent runtime and restoration seam for Intraday WO-10 V2."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from kronos.application.intraday_wo10 import (
    IntradayWo10Application,
    Wo10ApplicationError,
    Wo10EvidenceInputs,
)
from kronos.intraday.probables_v2 import (
    ProbableMemberResultV2,
    ProbablesRunV2,
    ProbablesV2Error,
    SemanticQualificationEvidenceV2,
    SemanticQualificationFactV2,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError
from kronos.intraday.review_v2 import (
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10ReconciliationRequest,
)
from kronos.intraday.wo10_evidence import (
    Wo10EvidenceReference,
    Wo10EvidenceSnapshot,
    create_wo10_common_fact_bindings,
    create_wo10_equity_extension,
    create_wo10_index_extension,
    create_wo10_mcx_extension,
)
from kronos.intraday.wo10_persistence import (
    RestoredWo10State,
    Wo10PersistenceError,
    Wo10Store,
)
from kronos.intraday.wo10_policies import (
    Wo10EquityPolicy,
    Wo10IndexPolicy,
    Wo10McxPolicy,
    Wo10PolicyRegistry,
    create_wo10_equity_policy_evidence,
    create_wo10_index_policy_evidence,
    create_wo10_mcx_policy_evidence,
)


WO10_RUNTIME_IDENTITY = "KRONOS-INTRADAY-WO10-RUNTIME-COMPOSITION-V1"
WO10_RUNTIME_VERSION = "1.0.0"


class RuntimeWo10PolicyRegistry(Wo10PolicyRegistry):
    """Exact published policies with request-scoped retained evidence loading."""

    def __init__(self) -> None:
        super().__init__((Wo10EquityPolicy(()), Wo10IndexPolicy(()), Wo10McxPolicy(())))
        self._loaded: dict[str, object] = {}
        self._lock = RLock()

    def load_evidence(
        self,
        *,
        snapshot: Wo10EvidenceSnapshot,
        semantic: SemanticQualificationEvidenceV2,
        imported_visual: object,
    ) -> None:
        """Bind one exact snapshot to its published family policy.

        Slice-8 intentionally consumes only already-retained V2 semantic and
        visual evidence.  Successor numerical facts not present in the retained
        stores remain unavailable and therefore fail closed as
        ``CONTEXT_INCOMPLETE`` under the published policies.
        """

        facts = {item.family: item for item in semantic.facts}
        common = {
            "source_semantic_evidence": semantic,
            "one_day_context": facts.get("1D_CONTEXT"),
            "one_hour_regime": facts.get("1H_REGIME"),
            "fifteen_minute_structure": facts.get("15M_STRUCTURE"),
            "five_minute_progression": facts.get("5M_PROGRESSION"),
            "rsi": None,
            "railway_track": None,
            "structural_location": None,
            "volume_telemetry": None,
        }
        if snapshot.market_family is IntradayMarketFamily.NSE_EQUITY:
            loaded = create_wo10_equity_policy_evidence(
                snapshot=snapshot,
                nifty_fifteen_minute_context=None,
                nifty_one_hour_context=None,
                nifty_relationship=None,
                imported_visual_evidence=imported_visual,  # type: ignore[arg-type]
                **common,
            )
        elif snapshot.market_family is IntradayMarketFamily.NSE_INDEX:
            loaded = create_wo10_index_policy_evidence(
                snapshot=snapshot,
                weekly_structural_map=None,
                daily_structural_map=facts.get("1D_CONTEXT"),
                imported_visual_evidence=imported_visual,  # type: ignore[arg-type]
                **common,
            )
        else:
            loaded = create_wo10_mcx_policy_evidence(
                snapshot=snapshot,
                active_derivative_binding=None,
                commissioning_publication=None,
                paired_chart_bundle=None,
                paired_visual_evidence=None,
                **common,
            )
        with self._lock:
            self._loaded[snapshot.snapshot_identity] = loaded

    def evaluate(self, *, request, evidence):  # type: ignore[no-untyped-def]
        with self._lock:
            loaded = self._loaded.get(evidence.snapshot_identity)
        if loaded is None:
            raise Wo10ContractError("WO10_POLICY_EVIDENCE_NOT_LOADED")
        policies = {
            IntradayMarketFamily.NSE_EQUITY: Wo10EquityPolicy,
            IntradayMarketFamily.NSE_INDEX: Wo10IndexPolicy,
            IntradayMarketFamily.MCX: Wo10McxPolicy,
        }
        policy = policies[evidence.market_family]((loaded,))
        return policy.evaluate(request=request, evidence=evidence)


class RetainedWo10EvidenceLoader:
    """Read exact retained Probables/Review artifacts without Provider access."""

    def __init__(
        self,
        *,
        probables: ProbablesV2Store,
        review: IntradayReviewV2Store,
        registry: RuntimeWo10PolicyRegistry,
    ) -> None:
        self._probables = probables
        self._review = review
        self._registry = registry
        self._pending: dict[
            tuple[str, str], tuple[SemanticQualificationEvidenceV2, object]
        ] = {}

    def load(
        self,
        *,
        run: ProbablesRunV2,
        result: ProbableMemberResultV2,
        request: Wo10ReconciliationRequest,
    ) -> Wo10EvidenceInputs:
        try:
            mapping = self._probables.load_mapping(result.source_mapping_identity or "")
            expected_handoff = create_review_handoff_v2(run, result, mapping)
            handoff = self._review.load_handoff(expected_handoff.handoff_identity)
            if handoff != expected_handoff:
                raise Wo10ApplicationError("WO10_REVIEW_HANDOFF_CONFLICT")
            expected_cycle = create_review_cycle_v2(handoff)
            cycle = self._review.load_cycle(expected_cycle.cycle_identity)
            if cycle != expected_cycle:
                raise Wo10ApplicationError("WO10_REVIEW_CYCLE_CONFLICT")
            active = self._review.load_current_chart(cycle.cycle_identity)
            if active is None:
                raise Wo10ApplicationError("WO10_CHART_EVIDENCE_UNAVAILABLE")
            chart = self._review.load_chart(active.chart_revision_identity)
            expected_pack = create_question_pack_v2(handoff, cycle, chart)
            pack = self._review.load_pack(expected_pack.review_pack_identity)
            if pack != expected_pack:
                raise Wo10ApplicationError("WO10_REVIEW_PACK_CONFLICT")
            visual = self._review.load_visual_evidence_for_pack(pack.review_pack_identity)
            if visual is None:
                raise Wo10ApplicationError("WO10_VISUAL_EVIDENCE_UNAVAILABLE")
        except (ReviewError, ProbablesV2Error, OSError) as error:
            raise Wo10ApplicationError("WO10_RETAINED_EVIDENCE_UNAVAILABLE") from error

        semantic = mapping.semantic_evidence
        facts = {item.family: item for item in semantic.facts}
        references = [
            _reference(
                mapping.completed_evidence.selection_identity,
                mapping.completed_evidence.integrity_identity,
            ),
            _reference(semantic.evidence_identity, semantic.integrity_identity),
            _reference(cycle.cycle_identity, cycle.integrity_identity),
            _reference(chart.chart_revision_identity, chart.integrity_identity),
            _reference(pack.review_pack_identity, pack.integrity_identity),
            _reference(visual.visual_evidence_identity, visual.integrity_identity),
        ]
        common = create_wo10_common_fact_bindings(
            one_day_structure=_fact_reference(facts.get("1D_CONTEXT")),
            one_hour_structure=_fact_reference(facts.get("1H_REGIME")),
            fifteen_minute_structure=_fact_reference(facts.get("15M_STRUCTURE")),
            five_minute_progression=_fact_reference(facts.get("5M_PROGRESSION")),
            rsi=None,
            railway_track=None,
            structural_location=None,
            volume_telemetry=None,
        )
        if request.market_family is IntradayMarketFamily.NSE_EQUITY:
            relationship = (
                None
                if mapping.nifty_relative is None
                else _reference(
                    mapping.nifty_relative.evidence_identity,
                    mapping.nifty_relative.integrity_identity,
                )
            )
            if relationship is not None:
                references.append(relationship)
            extension = create_wo10_equity_extension(
                nifty_fifteen_minute_context=None,
                nifty_one_hour_context=None,
                nifty_relationship=relationship,
            )
        elif request.market_family is IntradayMarketFamily.NSE_INDEX:
            daily = _fact_reference(facts.get("1D_CONTEXT"))
            extension = create_wo10_index_extension(
                weekly_structural_map=None,
                daily_structural_map=daily,
                underlying_authority=_reference(
                    result.result_identity, result.integrity_identity
                ),
            )
        else:
            commissioning = handoff.mcx_commissioning
            commissioning_reference = (
                None
                if commissioning is None
                else _reference(
                    commissioning.publication_identity,
                    commissioning.publication_integrity_identity,
                )
            )
            if commissioning_reference is not None:
                references.append(commissioning_reference)
            extension = create_wo10_mcx_extension(
                actual_contract=None,
                commissioning_publication=commissioning_reference,
                roll_history=None,
                reference_relationship=None,
                paired_visual_evidence=None,
                session_reference_context=None,
            )

        loaded = Wo10EvidenceInputs(
            cycle=cycle,
            chart=chart,
            review_pack=pack,
            imported_visual_evidence=visual,
            common_facts=common,
            family_extension=extension,
            source_references=tuple(sorted(
                {item.evidence_identity: item for item in references}.values(),
                key=lambda item: (item.evidence_identity, item.evidence_integrity),
            )),
            provenance=(
                WO10_RUNTIME_IDENTITY,
                "EXACT_RETAINED_PROBABLES_V2",
                "EXACT_RETAINED_REVIEW_V2",
                "PROVIDER_CALLS_0",
            ),
        )
        # The typed assembler creates the snapshot after this method returns.
        # Registry loading is completed by ``register_snapshot`` below.
        self._pending[(run.run_identity, result.result_identity)] = (semantic, visual)
        return loaded

    def register_snapshot(self, snapshot: Wo10EvidenceSnapshot) -> None:
        key = (snapshot.probables_run_identity, snapshot.probable_result_identity)
        try:
            semantic, visual = self._pending.pop(key)
        except KeyError as error:
            raise Wo10ApplicationError("WO10_POLICY_EVIDENCE_NOT_LOADED") from error
        self._registry.load_evidence(
            snapshot=snapshot, semantic=semantic, imported_visual=visual
        )


class RuntimeWo10EvidenceAssembler:
    """Create a snapshot then attach its exact inputs to the policy registry."""

    def __init__(self, loader: RetainedWo10EvidenceLoader) -> None:
        from kronos.application.intraday_wo10 import Wo10TypedEvidenceAssembler

        self._loader = loader
        self._typed = Wo10TypedEvidenceAssembler(loader)

    def assemble(self, *, run, result, request):  # type: ignore[no-untyped-def]
        snapshot = self._typed.assemble(run=run, result=result, request=request)
        self._loader.register_snapshot(snapshot)
        return snapshot


@dataclass(frozen=True, slots=True)
class Wo10RuntimeFamilyStatus:
    market_family: IntradayMarketFamily
    state: str
    restored: RestoredWo10State | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo10RuntimeService:
    """Inert restoration/status boundary; only ``execute`` evaluates WO-10."""

    def __init__(self, application: IntradayWo10Application, store: Wo10Store) -> None:
        self._application = application
        self._store = store
        self._lock = RLock()
        self._active_request_identity: str | None = None
        self._last_execution = None
        self._families = self._restore()

    @property
    def application(self) -> IntradayWo10Application:
        return self._application

    @property
    def store(self) -> Wo10Store:
        return self._store

    @property
    def family_statuses(self) -> tuple[Wo10RuntimeFamilyStatus, ...]:
        with self._lock:
            return self._families

    @property
    def active_request_identity(self) -> str | None:
        with self._lock:
            return self._active_request_identity

    @property
    def last_execution(self):  # type: ignore[no-untyped-def]
        with self._lock:
            return self._last_execution

    def execute(self, request: Wo10ReconciliationRequest):  # type: ignore[no-untyped-def]
        with self._lock:
            self._active_request_identity = request.request_identity
        try:
            outcome = self._application.execute(request)
            with self._lock:
                self._last_execution = outcome
                if outcome.completed:
                    self._families = self._replace_family(
                        request.market_family, self._restore_one(request.market_family)
                    )
            return outcome
        finally:
            with self._lock:
                self._active_request_identity = None

    def _restore(self) -> tuple[Wo10RuntimeFamilyStatus, ...]:
        return tuple(self._restore_one(family) for family in IntradayMarketFamily)

    def _restore_one(self, family: IntradayMarketFamily) -> Wo10RuntimeFamilyStatus:
        try:
            restored = self._application.restore_current(family)
        except (Wo10PersistenceError, Wo10ContractError, OSError, ValueError):
            return Wo10RuntimeFamilyStatus(
                family, "CORRUPT", None, "RESTORATION", "WO10_RESTORATION_FAILED"
            )
        return Wo10RuntimeFamilyStatus(
            family, "NOT_YET_RUN" if restored is None else "LOADED", restored
        )

    def _replace_family(
        self, family: IntradayMarketFamily, value: Wo10RuntimeFamilyStatus
    ) -> tuple[Wo10RuntimeFamilyStatus, ...]:
        return tuple(value if item.market_family is family else item for item in self._families)


def _reference(identity: str, integrity: str) -> Wo10EvidenceReference:
    return Wo10EvidenceReference(identity, integrity)


def _fact_reference(
    value: SemanticQualificationFactV2 | None,
) -> Wo10EvidenceReference | None:
    return None if value is None else _reference(value.fact_identity, value.integrity_identity)


__all__ = [
    "IntradayWo10RuntimeService",
    "RetainedWo10EvidenceLoader",
    "RuntimeWo10EvidenceAssembler",
    "RuntimeWo10PolicyRegistry",
    "WO10_RUNTIME_IDENTITY",
    "WO10_RUNTIME_VERSION",
    "Wo10RuntimeFamilyStatus",
]
