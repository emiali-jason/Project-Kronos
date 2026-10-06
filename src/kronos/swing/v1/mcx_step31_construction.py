"""Non-actionable MCX Step-31 construction and lifecycle admission checks.

The retained unit table permits exact *illustrative* arithmetic. It is not an
effective exchange specification or an authenticated Provider master. There
is deliberately no production proof issuer or persistence function here.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import re
from typing import Callable

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_step31_prepared_handoff import (
    MCX_STEP31_COMMISSIONING,
    McxStep31ChartBinding, McxStep31CurrentReadSet,
    McxStep31PreparedHandoff, McxStep31RequestBinding,
    prepare_mcx_review_v2_step31_handoff,
)
from kronos.swing.v1.review_evidence_binding import canonical
from kronos.swing.v1.review_evidence_store import (
    PreparedReadFence, record_prepared_read, capture_prepared_reads,
)


class McxConstructionRejected(ValueError):
    """A changed, incomplete or unproved prospective MCX entry failed closed."""


class McxProofOrigin(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    ISOLATED_FIXTURE = "ISOLATED_FIXTURE"


class McxQuantitySemantics(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOTS = "LOTS"
    BASE_UNITS = "BASE_UNITS"


@dataclass(frozen=True, slots=True)
class McxContractProofPrerequisites:
    """Explicit proof inputs; neither origin can commission a live entry."""

    family: McxFamily
    trading_symbol: str
    expiry: str
    origin: McxProofOrigin = McxProofOrigin.UNAVAILABLE
    provider_snapshot_identity: str | None = None
    provider_record_identity: str | None = None
    normalized_instrument_sha256: str | None = None
    effective_specification_sha256: str | None = None
    quantity_semantics: McxQuantitySemantics = McxQuantitySemantics.UNKNOWN
    expiry_session_identity: str | None = None
    expiry_eligibility_boundary: datetime | None = None
    entry_blackout_policy_identity: str | None = None
    energy_execution_decision_identity: str | None = None

    def __post_init__(self) -> None:
        try:
            expiry = date.fromisoformat(self.expiry)
        except (TypeError, ValueError) as error:
            raise McxConstructionRejected("MCX_CONTRACT_PROOF_INPUT_INVALID") from error
        if (
            type(self.family) is not McxFamily
            or type(self.trading_symbol) is not str or not self.trading_symbol
            or type(self.expiry) is not str or expiry.isoformat() != self.expiry
            or type(self.origin) is not McxProofOrigin
            or type(self.quantity_semantics) is not McxQuantitySemantics
            or any(value is not None and (type(value) is not str or not value.strip())
                   for value in (
                       self.provider_snapshot_identity, self.provider_record_identity,
                       self.expiry_session_identity, self.entry_blackout_policy_identity,
                       self.energy_execution_decision_identity,
                   ))
            or any(value is not None and (type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None)
                   for value in (self.normalized_instrument_sha256,
                                 self.effective_specification_sha256))
            or (self.expiry_eligibility_boundary is not None and not _aware(
                self.expiry_eligibility_boundary))
        ):
            raise McxConstructionRejected("MCX_CONTRACT_PROOF_INPUT_INVALID")
        if self.origin is McxProofOrigin.UNAVAILABLE and any((
            self.provider_snapshot_identity, self.provider_record_identity,
            self.normalized_instrument_sha256, self.effective_specification_sha256,
            self.expiry_session_identity, self.expiry_eligibility_boundary,
            self.entry_blackout_policy_identity, self.energy_execution_decision_identity,
        )) or (self.origin is McxProofOrigin.UNAVAILABLE
                and self.quantity_semantics is not McxQuantitySemantics.UNKNOWN):
            raise McxConstructionRejected("MCX_CONTRACT_PROOF_ORIGIN_INVALID")

    @property
    def permits_production_entry(self) -> bool:
        return False

    @property
    def missing(self) -> tuple[str, ...]:
        missing = []
        for field in (
            "provider_snapshot_identity", "provider_record_identity",
            "normalized_instrument_sha256", "effective_specification_sha256",
            "expiry_session_identity", "expiry_eligibility_boundary",
            "entry_blackout_policy_identity",
        ):
            if getattr(self, field) is None:
                missing.append(field.upper() + "_UNAVAILABLE")
        if self.quantity_semantics is McxQuantitySemantics.UNKNOWN:
            missing.append("PROVIDER_QUANTITY_SEMANTICS_UNAVAILABLE")
        if self.family in {McxFamily.CRUDEOIL, McxFamily.NATURALGAS} and self.energy_execution_decision_identity is None:
            missing.append("ENERGY_EXECUTION_DECISION_UNAVAILABLE")
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class McxOneHourGeometry:
    entry: Decimal
    stop: Decimal
    target: Decimal
    completed_one_hour_sha256: str
    completed_one_hour_boundary: datetime


@dataclass(frozen=True, slots=True)
class McxMonetaryRisk:
    lots: int
    quote_quantity_per_lot: Decimal
    physical_quantity: Decimal
    physical_unit: str
    quotation_base_quantity: Decimal
    quotation_unit: str
    price_to_rupee_multiplier: Decimal
    tick_value_per_lot: Decimal
    notional: Decimal
    stop_risk: Decimal
    maximum_stop_risk: Decimal
    provider_order_quantity: None = None
    authority: str = "ILLUSTRATIVE_ONLY_UNVERIFIED_SPECIFICATION"


@dataclass(frozen=True, slots=True)
class McxPendingPlan:
    """In-memory proposal, never a persisted TradePlanRecord."""

    run_identity: str
    assessment_sha256: str
    handoff_integrity_sha256: str
    family: McxFamily
    trading_symbol: str
    expiry: str
    risk: McxMonetaryRisk
    prepared_at: datetime
    commissioning_state: str = MCX_STEP31_COMMISSIONING
    entry_authority: bool = False


@dataclass(frozen=True, slots=True)
class McxOwnerSelectedHandoff:
    """Transient owner-selected read set; no persistence or entry authority."""

    prepared: McxStep31PreparedHandoff
    fence: PreparedReadFence
    workflow: object

    @contextmanager
    def final_fence(self):
        """WO-05 publication then WO-07 intake; byte-only recheck under locks."""

        bound = self.prepared.bound

        def recheck(snapshot):
            self.fence.check()
            if (
                snapshot.control["current_manifest"]["sha256"] != bound.manifest_sha256
                or snapshot.manifest["run_id"] != bound.run_identity
            ):
                raise McxConstructionRejected("MCX_STEP31_PUBLICATION_CHANGED")

        with self.workflow.store.publication_commit_guard(
            self.workflow.application.publication_mutation_guard, recheck,
        ):
            yield


def select_owner_current_mcx_handoff(
    workflow: object, family: McxFamily, derivative: InstrumentRecord,
    *, prepared_at: datetime, _response=None,
) -> McxOwnerSelectedHandoff:
    """Use the Review owner-selected current run, pointers, receipt and V2.

    The derivative is the normalized *request-bound* candle identity, not an
    authenticated current Provider-master proof. Full object validation and
    selected chart-byte checks occur outside business locks. The resulting
    exact byte fence is checked again at the prospective commit boundary.
    """

    if type(family) is not McxFamily or type(derivative) is not InstrumentRecord:
        raise McxConstructionRejected("MCX_STEP31_OWNER_SELECTION_INVALID")
    try:
        # A caller may reuse only this owner's live, fenced response. A new
        # standalone/action call retains the original full validation boundary.
        with capture_prepared_reads() as shared_reads:
            boundary = (workflow._validated_response() if _response is None
                        else nullcontext((_response, shared_reads)))
            if _response is not None:
                workflow.recheck_response(_response)
            with boundary as (response, reads):
                manifest, facts, _ = workflow._context(_response=response)
                requirement = workflow._requirements(
                    "MCX", (family.value,), _response=response,
                )[0]
                publication = workflow._publication("MCX", _response=response)
                if publication is None:
                    raise McxConstructionRejected("MCX_STEP31_REQUEST_UNAVAILABLE")
                key = sha256(canonical([
                    "NATIVE_REVIEW", "MCX", facts.run_identity,
                ])).hexdigest()
                commit = workflow.store.load_current_acceptance(key)
                if commit is None or commit.value["request_publication_identity"] != publication.identity:
                    raise McxConstructionRejected("MCX_STEP31_ACCEPTANCE_UNAVAILABLE")
                matching = tuple(item for item in commit.receipts
                    if item.binding.value["candidate_identity"] == requirement.requirement_sha256)
                if len(matching) != 1:
                    raise McxConstructionRejected("MCX_STEP31_RECEIPT_UNAVAILABLE")
                receipt = workflow.store.resolve_committed_receipt(
                    commit.identity, matching[0].receipt_id, current=True,
                )
                workflow._verify_receipt_current(receipt, _response=response)
                promotion = workflow.v2_for(
                    facts.run_identity, family.value, _response=response,
                )
                if promotion is None:
                    raise McxConstructionRejected("MCX_STEP31_V2_UNAVAILABLE")
                promotion_path = workflow._v2_store._path(
                    promotion.value["source"], promotion.value["input_sha256"],
                )
                promotion_bytes = workflow._v2_store._read(promotion_path)
                if promotion_bytes != promotion.payload:
                    raise McxConstructionRejected("MCX_STEP31_V2_BYTES_CHANGED")
                record_prepared_read(promotion_path, promotion_bytes)
                native, reference = publication.native.value, publication.reference.value
                requests = tuple(McxStep31RequestBinding(role, item["request_identity"], item["request_sha256"])
                    for role, item in (("NATIVE_MCX", native), ("SUPPORTING_REFERENCE", reference)))
                charts = tuple(McxStep31ChartBinding(
                    item["role"], item["timeframe"], item["chart_revision_identity"], item["chart_sha256"],
                ) for item in promotion.value["source"]["acceptance"]["visual_bindings"])
                selected = McxStep31CurrentReadSet(
                    run_identity=facts.run_identity, manifest_sha256=manifest,
                    requirement=requirement, facts=facts, publication=publication,
                    commit=commit, receipt=receipt, promotion=promotion,
                    derivative=derivative, request_bindings=requests,
                    chart_bindings=charts,
                )
                prepared = prepare_mcx_review_v2_step31_handoff(
                    lambda: selected, prepared_at=prepared_at,
                )
                fence = PreparedReadFence(tuple(reads.items()))
            if _response is not None:
                fence.check()
                workflow.recheck_response(_response)
        return McxOwnerSelectedHandoff(prepared, fence, workflow)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, McxConstructionRejected):
            raise
        raise McxConstructionRejected("MCX_STEP31_OWNER_SELECTION_STALE") from error


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _positive(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and value > 0


def _same_current(expected: McxStep31PreparedHandoff, selected: McxStep31PreparedHandoff) -> None:
    if (
        type(selected) is not McxStep31PreparedHandoff
        or selected.bound != expected.bound
        or selected.integrity_sha256 != expected.integrity_sha256
    ):
        raise McxConstructionRejected("MCX_STEP31_CURRENT_SELECTION_CHANGED")


def calculate_mcx_monetary_risk(
    prepared: McxStep31PreparedHandoff, geometry: McxOneHourGeometry,
    *, lots: int, maximum_stop_risk: Decimal,
) -> McxMonetaryRisk:
    """Exact quote-unit arithmetic, not an order quantity or risk approval."""

    if type(prepared) is not McxStep31PreparedHandoff or type(geometry) is not McxOneHourGeometry:
        raise McxConstructionRejected("MCX_STEP31_GEOMETRY_INVALID")
    bound = prepared.bound
    profile = mcx_unit_profile(bound.family)
    if (
        not all(_positive(value) for value in (geometry.entry, geometry.stop, geometry.target, maximum_stop_risk))
        or type(lots) is not int or lots <= 0
        or geometry.completed_one_hour_sha256 != bound.completed_one_hour_sha256
        or geometry.completed_one_hour_boundary != bound.completed_one_hour_boundary
        or not _aware(geometry.completed_one_hour_boundary)
        or any((price / profile.tick_in_quotation_units) % 1 for price in (
            geometry.entry, geometry.stop, geometry.target))
        or (bound.direction == "LONG" and not geometry.stop < geometry.entry < geometry.target)
        or (bound.direction == "SHORT" and not geometry.target < geometry.entry < geometry.stop)
        or bound.direction not in {"LONG", "SHORT"}
    ):
        raise McxConstructionRejected("MCX_STEP31_GEOMETRY_INVALID")
    quote_quantity = profile.quotation_multiplier_per_lot
    stop_risk = abs(geometry.entry - geometry.stop) * quote_quantity * lots
    if stop_risk > maximum_stop_risk:
        raise McxConstructionRejected("MCX_STEP31_MONETARY_RISK_EXCEEDED")
    return McxMonetaryRisk(
        lots=lots, quote_quantity_per_lot=quote_quantity,
        physical_quantity=profile.trading_quantity * lots,
        physical_unit=profile.trading_unit,
        quotation_base_quantity=profile.quotation_quantity,
        quotation_unit=profile.quotation_unit,
        price_to_rupee_multiplier=quote_quantity * lots,
        tick_value_per_lot=profile.rupees_per_tick_per_lot,
        notional=geometry.entry * quote_quantity * lots,
        stop_risk=stop_risk, maximum_stop_risk=maximum_stop_risk,
    )


def prepare_mcx_pending_construction(
    prepared: McxStep31PreparedHandoff,
    proof: McxContractProofPrerequisites,
    geometry: McxOneHourGeometry,
    *, lots: int, maximum_stop_risk: Decimal,
    selected_current: Callable[[], McxStep31PreparedHandoff],
    commit_guard: Callable[[], AbstractContextManager[object]],
    guarded_recheck: Callable[[McxStep31PreparedHandoff], None],
) -> McxPendingPlan:
    """Select current authority, then fence its exact bytes under owner locks.

    The owner supplies a previously prepared, exact-byte recheck. It must not
    run a projection, Provider call or full read-set reconstruction under the
    guard. No durable write follows this check while MCX is uncommissioned.
    """

    if (
        type(prepared) is not McxStep31PreparedHandoff
        or type(proof) is not McxContractProofPrerequisites
        or not callable(selected_current) or not callable(commit_guard)
        or not callable(guarded_recheck)
        or proof.family != prepared.bound.family
        or proof.trading_symbol != prepared.bound.derivative_symbol
        or proof.expiry != prepared.bound.derivative_expiry
    ):
        raise McxConstructionRejected("MCX_STEP31_CONTRACT_PROOF_MISMATCH")
    _same_current(prepared, selected_current())
    risk = calculate_mcx_monetary_risk(
        prepared, geometry, lots=lots, maximum_stop_risk=maximum_stop_risk,
    )
    try:
        with commit_guard():
            guarded_recheck(prepared)
    except (OSError, ValueError) as error:
        raise McxConstructionRejected("MCX_STEP31_COMMIT_FENCE_CHANGED") from error
    return McxPendingPlan(
        run_identity=prepared.bound.run_identity,
        assessment_sha256=prepared.bound.assessment_sha256,
        handoff_integrity_sha256=prepared.integrity_sha256,
        family=prepared.bound.family, trading_symbol=prepared.bound.derivative_symbol,
        expiry=prepared.bound.derivative_expiry, risk=risk,
        prepared_at=prepared.prepared_at,
    )


def prepare_mcx_pending_from_owner(
    workflow: object, family: McxFamily, derivative: InstrumentRecord,
    proof: McxContractProofPrerequisites, geometry: McxOneHourGeometry,
    *, prepared_at: datetime, lots: int, maximum_stop_risk: Decimal,
) -> McxPendingPlan:
    """Wire owner-selected currentness to the ordered final byte fence.

    The candidate is transient, with no persistence or production authority.
    The second selection happens before G; final_fence only compares captured
    bytes and publication primitives under G -> WO-05 -> WO-07.
    """

    selected = select_owner_current_mcx_handoff(
        workflow, family, derivative, prepared_at=prepared_at,
    )
    return prepare_mcx_pending_construction(
        selected.prepared, proof, geometry, lots=lots,
        maximum_stop_risk=maximum_stop_risk,
        selected_current=lambda: select_owner_current_mcx_handoff(
            workflow, family, derivative, prepared_at=prepared_at,
        ).prepared,
        commit_guard=selected.final_fence,
        guarded_recheck=lambda _: None,
    )


def check_mcx_pending_entry(
    pending: McxPendingPlan, current: McxStep31PreparedHandoff,
    proof: McxContractProofPrerequisites, *, observed_at: datetime,
) -> tuple[str, ...]:
    """Reject a stale/rolled/expired pending plan; never rewrite its contract."""

    if type(pending) is not McxPendingPlan or type(current) is not McxStep31PreparedHandoff or type(proof) is not McxContractProofPrerequisites or not _aware(observed_at):
        raise McxConstructionRejected("MCX_PENDING_ENTRY_INPUT_INVALID")
    reasons = list(proof.missing)
    if (
        pending.run_identity != current.bound.run_identity
        or pending.assessment_sha256 != current.bound.assessment_sha256
        or pending.handoff_integrity_sha256 != current.integrity_sha256
    ):
        reasons.append("MCX_PENDING_REVIEW_V2_STALE")
    if (pending.family, pending.trading_symbol, pending.expiry) != (
        current.bound.family, current.bound.derivative_symbol,
        current.bound.derivative_expiry,
    ) or (proof.family, proof.trading_symbol, proof.expiry) != (
        pending.family, pending.trading_symbol, pending.expiry,
    ):
        reasons.append("MCX_PENDING_CONTRACT_ROLLED_OR_CHANGED")
    if (proof.expiry_eligibility_boundary is None
            or observed_at.astimezone(UTC) >= proof.expiry_eligibility_boundary.astimezone(UTC)):
        reasons.append("MCX_PENDING_EXPIRY_ELIGIBILITY_UNAVAILABLE_OR_EXPIRED")
    # A complete isolated fixture still cannot commission production entry.
    reasons.append(MCX_STEP31_COMMISSIONING)
    return tuple(dict.fromkeys(reasons))


def existing_mcx_position_monitoring_and_exit_preserved(
    *, historical_contract_symbol: str, historical_expiry: str,
    current_contract_symbol: str | None,
) -> bool:
    """Entry/roll gates do not revoke monitoring or exit of an existing position.

    This helper grants no new position, execution or broker authority. The
    already-governed lifecycle handlers retain their separate checks.
    """

    if not historical_contract_symbol or not historical_expiry:
        raise McxConstructionRejected("MCX_HISTORICAL_POSITION_BINDING_INVALID")
    return True
