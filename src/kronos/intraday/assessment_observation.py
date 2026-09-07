"""WO-06C immutable admission measurement provenance; never admission policy.

The current producer has no designated price observation. Positive contracts
represent a supplied governed proof, not an authority to acquire/select prices.
No positive production adapter is installed by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbablesRunV2, ProbablesV2Error, _identity

ASSESSMENT_SCHEMA = "KRONOS-INTRADAY-ASSESSMENT-OBSERVATIONS"
ASSESSMENT_VERSION = "1.0.0"


class AssessmentPriceAuthority(StrEnum):
    EXACT_PRICE_PERSISTED = "EXACT_PRICE_PERSISTED"
    EXACT_PRICE_DERIVABLE_FROM_SAME_GOVERNED_ASSESSMENT_EVIDENCE = (
        "EXACT_PRICE_DERIVABLE_FROM_SAME_GOVERNED_ASSESSMENT_EVIDENCE"
    )
    PRICE_NOT_RETAINED = "PRICE_NOT_RETAINED"


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


@dataclass(frozen=True, slots=True)
class AdmissionPriceProof:
    """Exact designated observation retained with its source provenance.

    A hash proves integrity, not source authority. The publication identity must
    be established by the producing governed adapter, never supplied by a UI.
    No current adapter produces this type; fixtures cannot commission one.
    """
    canonical_subject_identity: str
    run_identity: str
    admission_identity: str
    source_mapping_identity: str
    market_session_identity: str
    source_identity: str
    source_artifact_digest: str
    authority_publication_identity: str
    price: Decimal
    observation_time: datetime
    available_at: datetime
    source_type: str
    integrity_identity: str

    def __post_init__(self) -> None:
        core = asdict(self)
        core.pop("integrity_identity")
        if (
            any(not _text(getattr(self, field)) for field in (
                "canonical_subject_identity", "run_identity", "admission_identity",
                "source_mapping_identity", "market_session_identity", "source_identity",
                "source_artifact_digest", "authority_publication_identity",
            ))
            or self.source_type != "GOVERNED_ADMISSION_PRICE_OBSERVATION"
            or type(self.price) is not Decimal or not self.price.is_finite()
            or not _aware(self.observation_time) or not _aware(self.available_at)
            or self.observation_time > self.available_at
            or self.integrity_identity != _identity("INTEGRITY-ADMISSION-PRICE-PROOF-", core)
        ):
            raise ProbablesV2Error("ASSESSMENT_PRICE_PROOF_INVALID")


@dataclass(frozen=True, slots=True)
class AdmissionAssessment:
    run_identity: str
    admission_identity: str
    canonical_subject_identity: str
    direction: str
    phase: str
    market_session_identity: str
    analysis_boundary: datetime
    source_mapping_identity: str
    methodology_version: str
    classification: AssessmentPriceAuthority
    assessment_price: Decimal | None
    assessment_time: datetime | None
    assessment_source_identity: str | None
    proof: AdmissionPriceProof | None
    derivation_rule: str | None
    reason: str

    def __post_init__(self) -> None:
        if (
            any(not _text(getattr(self, field)) for field in (
                "run_identity", "admission_identity", "canonical_subject_identity", "phase",
                "market_session_identity", "source_mapping_identity", "methodology_version", "reason",
            ))
            or self.direction not in ("LONG", "SHORT")
            or not _aware(self.analysis_boundary)
            or type(self.classification) is not AssessmentPriceAuthority
        ):
            raise ProbablesV2Error("ASSESSMENT_OBSERVATION_INVALID")
        if self.classification is AssessmentPriceAuthority.PRICE_NOT_RETAINED:
            if any(value is not None for value in (
                self.assessment_price, self.assessment_time, self.assessment_source_identity,
                self.proof, self.derivation_rule,
            )):
                raise ProbablesV2Error("ASSESSMENT_MISSING_AUTHORITY_HAS_VALUES")
            return
        proof = self.proof
        if type(proof) is not AdmissionPriceProof:
            raise ProbablesV2Error("ASSESSMENT_PRICE_PROOF_REQUIRED")
        proof.__post_init__()
        if (
            any(getattr(proof, field) != getattr(self, field) for field in (
                "run_identity", "admission_identity", "canonical_subject_identity",
                "market_session_identity", "source_mapping_identity",
            ))
            or type(self.assessment_price) is not Decimal
            or self.assessment_price != proof.price
            or not _aware(self.assessment_time)
            or self.assessment_time != proof.observation_time
            or self.assessment_source_identity != proof.source_identity
            or proof.available_at > self.analysis_boundary
            or (self.classification is AssessmentPriceAuthority.EXACT_PRICE_PERSISTED
                and self.derivation_rule is not None)
            or (self.classification is AssessmentPriceAuthority.EXACT_PRICE_DERIVABLE_FROM_SAME_GOVERNED_ASSESSMENT_EVIDENCE
                and self.derivation_rule != "EXACT_DESIGNATED_OBSERVATION_PRICE_AND_TIME")
        ):
            raise ProbablesV2Error("ASSESSMENT_OBSERVATION_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class ProbablesAssessmentObservations:
    evidence_identity: str
    run_identity: str
    run_integrity_identity: str
    observations: tuple[AdmissionAssessment, ...]
    integrity_identity: str
    schema_identity: str = ASSESSMENT_SCHEMA
    schema_version: str = ASSESSMENT_VERSION

    def __post_init__(self) -> None:
        if (
            not _text(self.run_identity) or not _text(self.run_integrity_identity)
            or type(self.observations) is not tuple
            or self.schema_identity != ASSESSMENT_SCHEMA or self.schema_version != ASSESSMENT_VERSION
        ):
            raise ProbablesV2Error("ASSESSMENT_MANIFEST_INVALID")
        for item in self.observations:
            if type(item) is not AdmissionAssessment or item.run_identity != self.run_identity:
                raise ProbablesV2Error("ASSESSMENT_MANIFEST_BINDING_INVALID")
            item.__post_init__()
        if len({item.admission_identity for item in self.observations}) != len(self.observations):
            raise ProbablesV2Error("ASSESSMENT_DUPLICATE_ADMISSION")
        core = asdict(self)
        core.pop("evidence_identity")
        core.pop("integrity_identity")
        if (
            self.evidence_identity != _identity("INTRADAY-ASSESSMENT-OBSERVATIONS-", core)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-ASSESSMENT-OBSERVATIONS-", core)
        ):
            raise ProbablesV2Error("ASSESSMENT_MANIFEST_INTEGRITY_INVALID")


def validate_assessment_run(value: ProbablesAssessmentObservations, run: ProbablesRunV2) -> None:
    if type(value) is not ProbablesAssessmentObservations or type(run) is not ProbablesRunV2:
        raise ProbablesV2Error("ASSESSMENT_RUN_INVALID")
    value.__post_init__()
    run.__post_init__()
    admitted = tuple(item for item in run.results if item.state in (
        ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE,
    ))
    if (
        value.run_identity != run.run_identity or value.run_integrity_identity != run.integrity_identity
        or tuple(item.admission_identity for item in value.observations)
        != tuple(item.result_identity for item in admitted)
    ):
        raise ProbablesV2Error("ASSESSMENT_RUN_BINDING_INVALID")
    for observation, result in zip(value.observations, admitted):
        result.__post_init__()
        if (
            any(getattr(observation, field) != getattr(result, field) for field in (
                "canonical_subject_identity", "market_session_identity", "analysis_boundary",
                "source_mapping_identity", "methodology_version",
            ))
            or observation.direction != result.direction.value
            or observation.phase != result.phase.value
        ):
            raise ProbablesV2Error("ASSESSMENT_ADMISSION_BINDING_INVALID")


def create_missing_assessment_observations(run: ProbablesRunV2) -> ProbablesAssessmentObservations:
    """Current producer adapter: no designated admission-price source exists.

    Never choose a stored candle, quote, analysis boundary or downstream value.
    Called only for new persistence, not restoration or historical backfill.
    """
    if type(run) is not ProbablesRunV2:
        raise ProbablesV2Error("ASSESSMENT_RUN_INVALID")
    run.__post_init__()
    observations = tuple(AdmissionAssessment(
        run_identity=run.run_identity, admission_identity=item.result_identity,
        canonical_subject_identity=item.canonical_subject_identity,
        direction=item.direction.value, phase=item.phase.value,
        market_session_identity=item.market_session_identity, analysis_boundary=item.analysis_boundary,
        source_mapping_identity=item.source_mapping_identity, methodology_version=item.methodology_version,
        classification=AssessmentPriceAuthority.PRICE_NOT_RETAINED,
        assessment_price=None, assessment_time=None, assessment_source_identity=None,
        proof=None, derivation_rule=None, reason="ADMISSION_PRICE_OBSERVATION_NOT_DESIGNATED",
    ) for item in run.results if item.state in (ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE))
    core = dict(run_identity=run.run_identity, run_integrity_identity=run.integrity_identity,
        observations=observations, schema_identity=ASSESSMENT_SCHEMA, schema_version=ASSESSMENT_VERSION)
    value = ProbablesAssessmentObservations(
        evidence_identity=_identity("INTRADAY-ASSESSMENT-OBSERVATIONS-", core),
        integrity_identity=_identity("INTEGRITY-INTRADAY-ASSESSMENT-OBSERVATIONS-", core), **core,
    )
    validate_assessment_run(value, run)
    return value
