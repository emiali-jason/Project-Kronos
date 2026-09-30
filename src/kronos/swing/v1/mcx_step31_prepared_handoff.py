"""Non-actionable MCX Review/V2-to-Step-31 input preparation.

This pure, Swing-owned read-set check does not commission MCX Step-31.  In
particular, a request-bound historical candle is not an authenticated
Provider-master contract or an effective MCX specification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Callable

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
from kronos.swing.v1.mcx_contract_profile import (
    McxFamily, McxRequestBoundCandleLineage,
    mcx_lineage_matches_completed_facts, mcx_unit_profile,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.native_discovery import NativeProductPath
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.review_evidence_binding import ReviewAcceptanceReceipt
from kronos.swing.v1.review_evidence_store import (
    McxRequestPublication, ReviewAcceptanceCommit,
)


MCX_STEP31_PREPARED_CONTRACT = "KRONOS-SWING-MCX-REVIEW-V2-STEP31-PREPARED-V1"
MCX_STEP31_PREPARED_AUTHORITY = "BOUND_INPUT_ONLY_NO_ENTRY_AUTHORITY"
MCX_STEP31_COMMISSIONING = "MCX_STEP31_NOT_COMMISSIONED"
_ROLES_TIMEFRAMES = tuple(
    (role, timeframe)
    for role in ("NATIVE_MCX", "SUPPORTING_REFERENCE")
    for timeframe in ("1D", "4H", "1H")
)


class McxStep31HandoffRejected(ValueError):
    """An incomplete or changed MCX preparation read set failed closed."""


def _digest(value: object) -> str:
    def primitive(item: object) -> object:
        if isinstance(item, datetime):
            return item.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, dict):
            return {key: primitive(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [primitive(value) for value in item]
        return item

    return sha256(json.dumps(
        primitive(value), sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True)
class McxStep31RequestBinding:
    role: str
    request_identity: str
    request_sha256: str

    def __post_init__(self) -> None:
        if self.role not in {"NATIVE_MCX", "SUPPORTING_REFERENCE"} or not self.request_identity or not _sha(self.request_sha256):
            raise ValueError("MCX_STEP31_REQUEST_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class McxStep31ChartBinding:
    role: str
    timeframe: str
    revision_identity: str
    chart_sha256: str

    def __post_init__(self) -> None:
        if (self.role, self.timeframe) not in _ROLES_TIMEFRAMES or not self.revision_identity or not _sha(self.chart_sha256):
            raise ValueError("MCX_STEP31_CHART_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class McxStep31CurrentReadSet:
    """Owner-selected current objects and independently selected pointers.

    The eventual application caller must obtain these under its governed
    publication/currentness fence.  This isolated adapter performs no I/O.
    """

    run_identity: str
    manifest_sha256: str
    requirement: NativeReviewRequirement
    facts: SameRunMtfFactSnapshot
    publication: McxRequestPublication
    commit: ReviewAcceptanceCommit
    receipt: ReviewAcceptanceReceipt
    promotion: V2PromotionRecord
    derivative: InstrumentRecord
    request_bindings: tuple[McxStep31RequestBinding, ...]
    chart_bindings: tuple[McxStep31ChartBinding, ...]


@dataclass(frozen=True, slots=True)
class McxStep31BoundInputs:
    run_identity: str
    manifest_sha256: str
    family: McxFamily
    direction: str
    assessment_sha256: str
    requirement_sha256: str
    publication_identity: str
    commit_identity: str
    receipt_identity: str
    receipt_integrity_sha256: str
    review_pack_identity: str
    review_pack_sha256: str
    answer_pdf_sha256: str
    comparison_sha256: str
    request_bindings: tuple[McxStep31RequestBinding, ...]
    chart_bindings: tuple[McxStep31ChartBinding, ...]
    structured_evidence_sha256: tuple[str, ...]
    promotion_identity: str
    promotion_integrity_sha256: str
    confirmation_integrity_sha256: str
    promotion_state: str
    machine_snapshot_identity: str
    derivative_symbol: str
    derivative_expiry: str
    request_bound_lineage_sha256: str
    completed_one_hour_sha256: str
    completed_one_hour_boundary: datetime
    derivative_proof_state: str = "REQUEST_BOUND_MASTER_AND_SPECIFICATION_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class McxStep31PreparedHandoff:
    """Exact Review/V2/candle input join, explicitly without entry authority."""

    bound: McxStep31BoundInputs
    prepared_at: datetime
    integrity_sha256: str
    contract_identity: str = MCX_STEP31_PREPARED_CONTRACT
    authority: str = MCX_STEP31_PREPARED_AUTHORITY
    commissioning_state: str = MCX_STEP31_COMMISSIONING
    geometry_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    entry_authority: bool = False
    position_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.bound) is not McxStep31BoundInputs
            or self.prepared_at.tzinfo is None
            or self.prepared_at.utcoffset() is None
            or self.contract_identity != MCX_STEP31_PREPARED_CONTRACT
            or self.authority != MCX_STEP31_PREPARED_AUTHORITY
            or self.commissioning_state != MCX_STEP31_COMMISSIONING
            or any((self.geometry_authority, self.risk_authority,
                    self.sponsor_decision_authority, self.entry_authority,
                    self.position_authority, self.execution_authority,
                    self.broker_authority))
            or self.integrity_sha256 != _digest({
                "contract_identity": self.contract_identity,
                "authority": self.authority,
                "commissioning_state": self.commissioning_state,
                "bound": asdict(self.bound),
                "prepared_at": self.prepared_at,
            })
        ):
            raise ValueError("MCX_STEP31_PREPARED_HANDOFF_INVALID")

    @property
    def permits_new_entry(self) -> bool:
        return False


def _bind(read: McxStep31CurrentReadSet) -> McxStep31BoundInputs:
    if (
        type(read) is not McxStep31CurrentReadSet
        or not is_swing_analysis_run_id(read.run_identity)
        or not _sha(read.manifest_sha256)
        or type(read.requirement) is not NativeReviewRequirement
        or type(read.facts) is not SameRunMtfFactSnapshot
        or type(read.publication) is not McxRequestPublication
        or type(read.commit) is not ReviewAcceptanceCommit
        or type(read.receipt) is not ReviewAcceptanceReceipt
        or type(read.promotion) is not V2PromotionRecord
        or type(read.derivative) is not InstrumentRecord
        or type(read.request_bindings) is not tuple
        or type(read.chart_bindings) is not tuple
        or any(type(item) is not McxStep31RequestBinding for item in read.request_bindings)
        or any(type(item) is not McxStep31ChartBinding for item in read.chart_bindings)
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_INPUT_INVALID")

    requirement = read.requirement
    thesis = requirement.thesis
    if thesis.product_path is not NativeProductPath.MCX:
        raise McxStep31HandoffRejected("MCX_STEP31_ASSET_CLASS_MISMATCH")
    try:
        family = McxFamily(requirement.canonical_instrument)
        instrument = read.facts.instrument(family.value)
    except (ValueError, StopIteration) as error:
        raise McxStep31HandoffRejected("MCX_STEP31_BINDING_INCOMPLETE") from error
    source = read.promotion.value["source"]
    acceptance = source["acceptance"]
    promotion = read.promotion.value
    confirmation = promotion["confirmation"]
    receipt = read.receipt
    receipt_binding = receipt.binding.value
    receipt_body = receipt.body
    publication = read.publication
    native = publication.native.value
    reference = publication.reference.value
    comparison = receipt_body["comparison_evidence"]
    lineage = instrument.mcx_request_lineage
    if (
        read.run_identity != requirement.native_run_identity
        or read.run_identity != read.facts.run_identity
        or source["native_run_identity"] != read.run_identity
        or source["committed_run_manifest_identity"] != read.manifest_sha256
        or source["market"] != "MCX"
        or source["asset_class"] != "MCX_COMMODITY"
        or source["canonical_instrument"] != family.value
        or source["direction"] != thesis.direction.value
        or source["native_opportunity_identity"] != thesis.opportunity_identity.value
        or source["native_assessment_sha256"] != thesis.native_assessment_sha256
        or source["native_requirement_sha256"] != requirement.requirement_sha256
        or receipt_binding["market"] != "MCX"
        or receipt_binding["analytical_run_identity"] != read.run_identity
        or receipt_binding["committed_run_manifest_identity"] != read.manifest_sha256
        or receipt_binding["candidate_identity"] != requirement.requirement_sha256
        or receipt_binding["canonical_instrument"] != family.value
        or receipt_binding["native_assessment_sha256"] != thesis.native_assessment_sha256
        or receipt not in read.commit.receipts
        or acceptance["commit_identity"] != read.commit.identity
        or acceptance["receipt_identity"] != receipt.receipt_id
        or acceptance["receipt_integrity_sha256"] != receipt.value["integrity_sha256"]
        or acceptance["request_publication_identity"] != publication.identity
        or read.commit.value["request_publication_identity"] != publication.identity
        or receipt_binding["request_identity"] != native["request_identity"]
        or receipt_binding["review_cycle_identity"] != native["review_cycle_identity"]
        or acceptance["review_cycle_identity"] != native["review_cycle_identity"]
        or acceptance["review_pack_identity"] != receipt_binding["review_pack_identity"]
        or acceptance["review_pack_identity"] != native["review_pack_identity"]
        or acceptance["review_pack_sha256"] != receipt_binding["review_pack_sha256"]
        or acceptance["review_pack_sha256"] != native["review_pack_sha256"]
        or native["review_pack_identity"] != reference["review_pack_identity"]
        or receipt_body["answer"]["answer_identity"] != acceptance["answer_identity"]
        or receipt_body["answer"]["pdf_sha256"] != acceptance["answer_pdf_sha256"]
        or comparison is None
        or comparison["answer_pdf_sha256"] != acceptance["answer_pdf_sha256"]
        or comparison["native_candidate_reference"] != requirement.requirement_sha256
        or confirmation["kind"] != "MCX_GLOBAL_REFERENCE"
        or confirmation["mcx_binding"]["validation_state"] != "VALID"
        or confirmation["mcx_binding"]["payload"]["pair_binding_sha256"] != comparison["pair_binding_sha256"]
        or confirmation["mcx_binding"]["payload"]["comparison_artifact_sha256"] != comparison["sha256"]
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_REVIEW_V2_MISMATCH")
    if (
        promotion["evaluation_disposition"] != "EVALUATED"
        or promotion["promotion_state"] not in {"BUY_NOW", "SELL_NOW"}
        or promotion["satisfied_count"] != 5
        or promotion["missing_count"] != 0
        or promotion["confirmation_pending"] is not False
        or confirmation["state"] != "ESTABLISHED"
        or promotion["promotion_state"] != (
            "BUY_NOW" if thesis.direction.value == "LONG" else "SELL_NOW"
        )
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_V2_NOT_CONFIRMED_NOW")

    requests = tuple(McxStep31RequestBinding(
        role, mapping["request_identity"], mapping["request_sha256"],
    ) for role, mapping in (("NATIVE_MCX", native), ("SUPPORTING_REFERENCE", reference)))
    if (
        read.request_bindings != requests
        or tuple(McxStep31RequestBinding(
            item["role"], item["request_identity"], item["request_sha256"],
        ) for item in acceptance["request_bindings"]) != requests
        or (comparison["native_request_identity"], comparison["native_request_sha256"])
        != (requests[0].request_identity, requests[0].request_sha256)
        or (comparison["reference_request_identity"], comparison["reference_request_sha256"])
        != (requests[1].request_identity, requests[1].request_sha256)
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_REQUEST_MISMATCH")

    charts = tuple(McxStep31ChartBinding(
        item["role"], item["timeframe"], item["chart_revision_identity"],
        item["chart_sha256"],
    ) for item in acceptance["visual_bindings"])
    received_charts = tuple(McxStep31ChartBinding(
        item["role"], item["timeframe_or_panel_identity"],
        item["revision_identity"], item["sha256"],
    ) for item in receipt_body["chart_revisions"])
    structured = tuple(receipt_body["structured_evidence"])
    if (
        tuple((item.role, item.timeframe) for item in charts) != _ROLES_TIMEFRAMES
        or read.chart_bindings != charts
        or received_charts != charts
        or tuple((item["role"], item["timeframe_or_family_identity"])
                 for item in structured) != _ROLES_TIMEFRAMES
        or tuple(item["sha256"] for item in structured)
        != tuple(item["structured_evidence_sha256"] for item in acceptance["visual_bindings"])
        or tuple(receipt_body["contracts"]) != tuple(acceptance["visual_contracts"])
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_CHART_EVIDENCE_MISMATCH")

    one_hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    completed = tuple(instrument.fact(tf) for tf in (
        FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR, FactualTimeframe.ONE_HOUR,
    ))
    if (
        instrument.exchange != "MCX"
        or type(lineage) is not McxRequestBoundCandleLineage
        or not instrument.completed_series
        or not mcx_lineage_matches_completed_facts(
            lineage, run_identity=read.run_identity,
            canonical_instrument=family.value, current_instrument=read.derivative,
            completed_facts=completed, completed_series=instrument.completed_series,
        )
        or source["machine_snapshot_identity"] != read.facts.provider_source_identity
        or source["analysis_boundary"] != _time(max(
            item.analysis_boundary for item in instrument.reference_facts
        ))
        or tuple((item["timeframe"], item["integrity_sha256"])
                 for item in source["machine_fact_bindings"])
        != tuple((item.chart_timeframe.value, item.integrity_sha256)
                 for item in instrument.reference_facts)
        or tuple((item["timeframe"], item["boundary"])
                 for item in source["observation_boundaries"])
        != tuple((item.timeframe.value, _time(item.observation_boundary))
                 for item in instrument.timeframes)
        or tuple((item.timeframe.value, _time(item.observation_boundary))
                 for item in thesis.timeframe_facts)
        != tuple((item["timeframe"], item["boundary"])
                 for item in source["observation_boundaries"])
        or one_hour.source_interval != "60minute"
        or one_hour.observation_boundary > read.facts.observed_at
        # The lineage matcher above verifies the producer's exact 1H digest.
        # Its canonical timestamp encoding differs from this envelope's.
    ):
        raise McxStep31HandoffRejected("MCX_STEP31_COMPLETED_CANDLE_MISMATCH")

    if mcx_unit_profile(family).permits_new_entry or lineage.permits_new_entry:
        raise McxStep31HandoffRejected("MCX_STEP31_CONTRACT_PROOF_UNEXPECTED")
    return McxStep31BoundInputs(
        run_identity=read.run_identity, manifest_sha256=read.manifest_sha256,
        family=family, direction=thesis.direction.value,
        assessment_sha256=thesis.native_assessment_sha256,
        requirement_sha256=requirement.requirement_sha256,
        publication_identity=publication.identity,
        commit_identity=read.commit.identity, receipt_identity=receipt.receipt_id,
        receipt_integrity_sha256=receipt.value["integrity_sha256"],
        review_pack_identity=acceptance["review_pack_identity"],
        review_pack_sha256=acceptance["review_pack_sha256"],
        answer_pdf_sha256=acceptance["answer_pdf_sha256"],
        comparison_sha256=comparison["sha256"],
        request_bindings=requests, chart_bindings=charts,
        structured_evidence_sha256=tuple(item["sha256"] for item in structured),
        promotion_identity=read.promotion.identity,
        promotion_integrity_sha256=promotion["integrity_sha256"],
        confirmation_integrity_sha256=_digest(confirmation),
        promotion_state=promotion["promotion_state"],
        machine_snapshot_identity=read.facts.provider_source_identity,
        derivative_symbol=lineage.trading_symbol,
        derivative_expiry=lineage.expiry,
        request_bound_lineage_sha256=_digest(asdict(lineage)),
        completed_one_hour_sha256=lineage.completed_1h_sha256,
        completed_one_hour_boundary=one_hour.observation_boundary,
    )


def _safe_bind(current: Callable[[], McxStep31CurrentReadSet]) -> McxStep31BoundInputs:
    try:
        return _bind(current())
    except McxStep31HandoffRejected:
        raise
    except (AttributeError, IndexError, KeyError, StopIteration, TypeError, ValueError) as error:
        raise McxStep31HandoffRejected("MCX_STEP31_BINDING_INCOMPLETE") from error


def prepare_mcx_review_v2_step31_handoff(
    current: Callable[[], McxStep31CurrentReadSet], *, prepared_at: datetime,
) -> McxStep31PreparedHandoff:
    """Read, bind and recheck a source-owned current set; never persist it."""

    if not callable(current) or type(prepared_at) is not datetime or prepared_at.tzinfo is None or prepared_at.utcoffset() is None:
        raise McxStep31HandoffRejected("MCX_STEP31_INPUT_INVALID")
    first = _safe_bind(current)
    try:
        second = _safe_bind(current)
    except McxStep31HandoffRejected as error:
        raise McxStep31HandoffRejected("MCX_STEP31_BINDING_CHANGED") from error
    if first != second:
        raise McxStep31HandoffRejected("MCX_STEP31_BINDING_CHANGED")
    unsigned = dict(contract_identity=MCX_STEP31_PREPARED_CONTRACT,
        authority=MCX_STEP31_PREPARED_AUTHORITY,
        commissioning_state=MCX_STEP31_COMMISSIONING,
        bound=asdict(first), prepared_at=prepared_at)
    return McxStep31PreparedHandoff(
        first, prepared_at, _digest(unsigned),
    )


__all__ = [
    "MCX_STEP31_COMMISSIONING", "MCX_STEP31_PREPARED_AUTHORITY",
    "MCX_STEP31_PREPARED_CONTRACT", "McxStep31BoundInputs",
    "McxStep31ChartBinding", "McxStep31CurrentReadSet",
    "McxStep31HandoffRejected", "McxStep31PreparedHandoff",
    "McxStep31RequestBinding", "prepare_mcx_review_v2_step31_handoff",
]
