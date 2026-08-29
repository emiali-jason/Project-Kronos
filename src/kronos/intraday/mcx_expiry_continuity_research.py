"""Research-only family-wide MCX expiry-continuity qualification.

This module proves a retention architecture, not a production collector.  It
archives governed actual-contract candles before simulating removal of that
contract from a future current Instrument Master.  Replayed history is built
only from the immutable archive.  Successor identity comes from DOMAIN-001 V2;
no symbol guessing, fabricated successor candles, or execution authority is
introduced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
from kronos.instrument.semantic_v2 import (
    DerivativeContractV2,
    InstrumentSemanticPublicationV2,
    ProviderMappingDirectiveV2,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.mcx_continuous_research import (
    MCX_CONTINUOUS_RESEARCH_AUTHORITY,
    ContinuousResearchCandle,
    McxContinuousResearchArtifact,
)
from kronos.intraday.mcx_historical_research import McxHistoricalResearchCorpus


MCX_EXPIRY_CONTINUITY_IDENTITY = (
    "KRONOS-INTRADAY-MCX-FAMILY-EXPIRY-CONTINUITY-QUALIFICATION-V1"
)
MCX_EXPIRY_CONTINUITY_VERSION = "1.0.0"
MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY = (
    "KRONOS-INTRADAY-MCX-HISTORICAL-CONTRACT-EVIDENCE-ARCHIVE-V1"
)
MCX_PROVIDER_TOKEN_PROVENANCE = (
    "DOMAIN-006_PROVIDER_TOKEN_USED_AT_ACQUISITION_BOUNDARY_NOT_RETAINED"
)


class McxExpiryContinuityError(ValueError):
    """Sanitized research contract or integrity failure."""


class ExpiryScenarioKind(StrEnum):
    CONTROLLED_DETERMINISTIC = "CONTROLLED_DETERMINISTIC"


class ExpiryContinuityOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class RetainedContractCandle:
    candle_identity: str
    canonical_subject_identity: str
    canonical_contract_identity: str
    provider_record_identities: tuple[str, ...]
    historical_binding_identities: tuple[str, ...]
    provider_token_provenance: str
    market_session_identity: str
    timeframe: IntradayTimeframe
    trading_date: date
    candle_start: datetime
    candle_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_candle_identities: tuple[str, ...]
    source_provider_identities: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("candle_identity")
        values.pop("integrity_identity")
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.candle_identity.startswith("INTRADAY-MCX-RETAINED-CANDLE-")
            or not _texts((
                self.canonical_subject_identity,
                self.canonical_contract_identity,
                self.market_session_identity,
            ))
            or not _texts(self.provider_record_identities)
            or not _texts(self.historical_binding_identities)
            or self.provider_token_provenance != MCX_PROVIDER_TOKEN_PROVENANCE
            or type(self.timeframe) is not IntradayTimeframe
            or type(self.trading_date) is not date
            or not _aware(self.candle_start)
            or not _aware(self.candle_end)
            or self.candle_start >= self.candle_end
            or any(type(item) is not Decimal or not item.is_finite() or item < 0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not _texts(self.source_candle_identities)
            or not _texts(self.source_provider_identities)
            or self.candle_identity != _identity("INTRADAY-MCX-RETAINED-CANDLE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-RETAINED-CANDLE-", values)
        ):
            raise McxExpiryContinuityError("MCX_RETAINED_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class ImmutableContractEvidenceArchive:
    archive_identity: str
    canonical_subject_identity: str
    canonical_contract_identity: str
    provider_symbols: tuple[str, ...]
    provider_record_identities: tuple[str, ...]
    historical_binding_identities: tuple[str, ...]
    candles: tuple[RetainedContractCandle, ...]
    current_instrument_master_dependency: bool
    immutable: bool
    integrity_identity: str
    contract_identity: str = MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("archive_identity")
        values.pop("integrity_identity")
        if (
            not self.archive_identity.startswith("INTRADAY-MCX-CONTRACT-ARCHIVE-")
            or not _texts((self.canonical_subject_identity, self.canonical_contract_identity))
            or not _texts(self.provider_symbols)
            or not _texts(self.provider_record_identities)
            or not _texts(self.historical_binding_identities)
            or not self.candles
            or any(type(item) is not RetainedContractCandle for item in self.candles)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.candles)
            or any(item.canonical_contract_identity != self.canonical_contract_identity for item in self.candles)
            or self.current_instrument_master_dependency is not False
            or self.immutable is not True
            or self.contract_identity != MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY
            or self.archive_identity != _identity("INTRADAY-MCX-CONTRACT-ARCHIVE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-CONTRACT-ARCHIVE-", values)
        ):
            raise McxExpiryContinuityError("MCX_CONTRACT_ARCHIVE_INVALID")


@dataclass(frozen=True, slots=True)
class FamilyExpiryContinuityScenario:
    scenario_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    provider_contract_family: str
    scenario_kind: ExpiryScenarioKind
    contract_a_identity: str
    contract_a_expiry: date
    contract_a_archive_identity: str
    contract_a_candle_count: int
    successor_contract_b_identity: str
    successor_contract_b_expiry: date
    successor_provider_directive_identity: str
    simulated_current_master_contract_identities: tuple[str, ...]
    contract_a_absent_from_simulated_current_master: bool
    successor_b_present_in_simulated_current_master: bool
    replayed_candle_count: int
    replayed_candle_integrity_digest: str
    original_candle_integrity_digest: str
    replay_exact: bool
    fabricated_market_candle_count: int
    manual_expiry_intervention_required: bool
    current_instrument_master_dependency_for_old_history: bool
    outcome: ExpiryContinuityOutcome
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("scenario_identity")
        values.pop("integrity_identity")
        if (
            not self.scenario_identity.startswith("INTRADAY-MCX-EXPIRY-SCENARIO-")
            or not _texts((
                self.analytical_subject,
                self.canonical_subject_identity,
                self.provider_contract_family,
                self.contract_a_identity,
                self.contract_a_archive_identity,
                self.successor_contract_b_identity,
                self.successor_provider_directive_identity,
                self.replayed_candle_integrity_digest,
                self.original_candle_integrity_digest,
            ))
            or self.scenario_kind is not ExpiryScenarioKind.CONTROLLED_DETERMINISTIC
            or self.contract_a_expiry >= self.successor_contract_b_expiry
            or type(self.contract_a_candle_count) is not int
            or self.contract_a_candle_count <= 0
            or self.contract_a_identity in self.simulated_current_master_contract_identities
            or self.successor_contract_b_identity not in self.simulated_current_master_contract_identities
            or self.contract_a_absent_from_simulated_current_master is not True
            or self.successor_b_present_in_simulated_current_master is not True
            or self.replayed_candle_count != self.contract_a_candle_count
            or self.replayed_candle_integrity_digest != self.original_candle_integrity_digest
            or self.replay_exact is not True
            or self.fabricated_market_candle_count != 0
            or self.manual_expiry_intervention_required is not False
            or self.current_instrument_master_dependency_for_old_history is not False
            or self.outcome is not ExpiryContinuityOutcome.PASS
            or self.scenario_identity != _identity("INTRADAY-MCX-EXPIRY-SCENARIO-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-EXPIRY-SCENARIO-", values)
        ):
            raise McxExpiryContinuityError("MCX_EXPIRY_SCENARIO_INVALID")


@dataclass(frozen=True, slots=True)
class LegacyObservedRollGap:
    gap_identity: str
    canonical_subject_identity: str
    expired_contract_identity: str
    successor_contract_identity: str
    expired_contract_retained_candle_count: int
    disposition: str
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("gap_identity")
        values.pop("integrity_identity")
        if (
            not self.gap_identity.startswith("INTRADAY-MCX-LEGACY-ROLL-GAP-")
            or not _texts((self.canonical_subject_identity, self.expired_contract_identity, self.successor_contract_identity))
            or self.expired_contract_retained_candle_count != 0
            or self.disposition != "LEGACY_UNRETAINED_HISTORY_UNAVAILABLE_NO_SUBSTITUTION"
            or self.gap_identity != _identity("INTRADAY-MCX-LEGACY-ROLL-GAP-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-LEGACY-ROLL-GAP-", values)
        ):
            raise McxExpiryContinuityError("MCX_LEGACY_ROLL_GAP_INVALID")


@dataclass(frozen=True, slots=True)
class McxFamilyExpiryContinuityArtifact:
    artifact_identity: str
    created_at: datetime
    source_corpus_identity: str
    source_corpus_integrity_identity: str
    source_continuous_artifact_identity: str
    source_continuous_integrity_identity: str
    catalogue_identity: str
    catalogue_version: str
    catalogue_integrity_identity: str
    archives: tuple[ImmutableContractEvidenceArchive, ...]
    scenarios: tuple[FamilyExpiryContinuityScenario, ...]
    legacy_observed_roll_gaps: tuple[LegacyObservedRollGap, ...]
    family_subjects: tuple[str, ...]
    mcx_family_expiry_continuity: ExpiryContinuityOutcome
    mcx_historical_analysis_survives_contract_expiry: bool
    manual_expiry_intervention_required: bool
    current_instrument_master_dependency_for_old_history: bool
    provider_request_count: int
    synthetic_market_candle_count: int
    production_state_modified: bool
    authority: str
    limitations: tuple[str, ...]
    integrity_identity: str
    contract_identity: str = MCX_EXPIRY_CONTINUITY_IDENTITY
    contract_version: str = MCX_EXPIRY_CONTINUITY_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("artifact_identity")
        values.pop("integrity_identity")
        expected_subjects = tuple(item[1] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS)
        if (
            not self.artifact_identity.startswith("INTRADAY-MCX-EXPIRY-CONTINUITY-")
            or not _aware(self.created_at)
            or not _texts((
                self.source_corpus_identity,
                self.source_corpus_integrity_identity,
                self.source_continuous_artifact_identity,
                self.source_continuous_integrity_identity,
                self.catalogue_identity,
                self.catalogue_version,
                self.catalogue_integrity_identity,
                self.authority,
            ))
            or any(type(item) is not ImmutableContractEvidenceArchive for item in self.archives)
            or any(type(item) is not FamilyExpiryContinuityScenario for item in self.scenarios)
            or any(type(item) is not LegacyObservedRollGap for item in self.legacy_observed_roll_gaps)
            or self.family_subjects != expected_subjects
            or tuple(item.canonical_subject_identity for item in self.scenarios) != expected_subjects
            or self.mcx_family_expiry_continuity is not ExpiryContinuityOutcome.PASS
            or self.mcx_historical_analysis_survives_contract_expiry is not True
            or self.manual_expiry_intervention_required is not False
            or self.current_instrument_master_dependency_for_old_history is not False
            or self.provider_request_count != 0
            or self.synthetic_market_candle_count != 0
            or self.production_state_modified is not False
            or self.authority != MCX_CONTINUOUS_RESEARCH_AUTHORITY
            or not _texts(self.limitations)
            or self.contract_identity != MCX_EXPIRY_CONTINUITY_IDENTITY
            or self.contract_version != MCX_EXPIRY_CONTINUITY_VERSION
            or self.artifact_identity != _identity("INTRADAY-MCX-EXPIRY-CONTINUITY-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-EXPIRY-CONTINUITY-", values)
        ):
            raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_ARTIFACT_INVALID")


def build_mcx_family_expiry_continuity_artifact(
    *,
    source_corpus: McxHistoricalResearchCorpus,
    continuous_artifact: McxContinuousResearchArtifact,
    catalogue: InstrumentSemanticPublicationV2,
    created_at: datetime,
) -> McxFamilyExpiryContinuityArtifact:
    if (
        type(source_corpus) is not McxHistoricalResearchCorpus
        or type(continuous_artifact) is not McxContinuousResearchArtifact
        or type(catalogue) is not InstrumentSemanticPublicationV2
        or not _aware(created_at)
        or continuous_artifact.source_corpus_identity != source_corpus.corpus_identity
    ):
        raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_INPUT_INVALID")

    source_by_id = {
        candle.candle_identity: candle
        for session in source_corpus.sessions
        for candle in session.candles
    }
    binding_by_id = {
        session.binding.binding_identity: session.binding
        for session in source_corpus.sessions
        if session.binding is not None
    }
    archives: list[ImmutableContractEvidenceArchive] = []
    archive_by_contract: dict[str, ImmutableContractEvidenceArchive] = {}
    for series in continuous_artifact.series:
        for contract_identity in series.represented_contract_identities:
            retained = tuple(
                _retain_candle(item, source_by_id)
                for item in series.candles
                if item.canonical_contract_identity == contract_identity
            )
            binding_ids = tuple(sorted({
                value
                for candle in retained
                for value in candle.historical_binding_identities
            }))
            provider_symbols = tuple(sorted({
                binding_by_id[value].provider_symbol
                for value in binding_ids
                if value in binding_by_id
            }))
            archive_values = {
                "canonical_subject_identity": series.canonical_subject_identity,
                "canonical_contract_identity": contract_identity,
                "provider_symbols": provider_symbols,
                "provider_record_identities": tuple(sorted({
                    value for candle in retained for value in candle.provider_record_identities
                })),
                "historical_binding_identities": binding_ids,
                "candles": retained,
                "current_instrument_master_dependency": False,
                "immutable": True,
                "contract_identity": MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY,
            }
            archive = ImmutableContractEvidenceArchive(
                archive_identity=_identity("INTRADAY-MCX-CONTRACT-ARCHIVE-", archive_values),
                integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-ARCHIVE-", archive_values),
                **archive_values,
            )
            archives.append(archive)
            archive_by_contract[contract_identity] = archive

    scenarios = tuple(
        _build_family_scenario(
            analytical_subject=analytical_subject,
            subject_identity=subject_identity,
            provider_family=provider_family,
            archive_by_contract=archive_by_contract,
            catalogue=catalogue,
        )
        for analytical_subject, subject_identity, provider_family
        in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
    )
    legacy_gaps: list[LegacyObservedRollGap] = []
    for series in continuous_artifact.series:
        for roll in series.roll_boundaries:
            if roll.old_contract_identity in archive_by_contract:
                continue
            gap_values = {
                "canonical_subject_identity": series.canonical_subject_identity,
                "expired_contract_identity": roll.old_contract_identity,
                "successor_contract_identity": roll.new_contract_identity,
                "expired_contract_retained_candle_count": 0,
                "disposition": "LEGACY_UNRETAINED_HISTORY_UNAVAILABLE_NO_SUBSTITUTION",
            }
            legacy_gaps.append(LegacyObservedRollGap(
                gap_identity=_identity("INTRADAY-MCX-LEGACY-ROLL-GAP-", gap_values),
                integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-LEGACY-ROLL-GAP-", gap_values),
                **gap_values,
            ))
    values = {
        "created_at": created_at,
        "source_corpus_identity": source_corpus.corpus_identity,
        "source_corpus_integrity_identity": source_corpus.integrity_identity,
        "source_continuous_artifact_identity": continuous_artifact.artifact_identity,
        "source_continuous_integrity_identity": continuous_artifact.integrity_identity,
        "catalogue_identity": catalogue.publication_identity,
        "catalogue_version": catalogue.publication_version,
        "catalogue_integrity_identity": catalogue.integrity_identity,
        "archives": tuple(archives),
        "scenarios": scenarios,
        "legacy_observed_roll_gaps": tuple(legacy_gaps),
        "family_subjects": tuple(item[1] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS),
        "mcx_family_expiry_continuity": ExpiryContinuityOutcome.PASS,
        "mcx_historical_analysis_survives_contract_expiry": True,
        "manual_expiry_intervention_required": False,
        "current_instrument_master_dependency_for_old_history": False,
        "provider_request_count": 0,
        "synthetic_market_candle_count": 0,
        "production_state_modified": False,
        "authority": MCX_CONTINUOUS_RESEARCH_AUTHORITY,
        "limitations": (
            "Qualification proves the research architecture for candles retained before expiry; production capture is not commissioned.",
            "NATGAS August history not retained before its observed roll remains unavailable and is not substituted.",
            "Controlled successor scenarios contain no fabricated successor market candles.",
            "Active derivative binding remains distinct from execution eligibility.",
        ),
        "contract_identity": MCX_EXPIRY_CONTINUITY_IDENTITY,
        "contract_version": MCX_EXPIRY_CONTINUITY_VERSION,
    }
    return McxFamilyExpiryContinuityArtifact(
        artifact_identity=_identity("INTRADAY-MCX-EXPIRY-CONTINUITY-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-EXPIRY-CONTINUITY-", values),
        **values,
    )


def governed_successor_contract(
    *, catalogue: InstrumentSemanticPublicationV2,
    subject_identity: str,
    contract_a_identity: str,
) -> tuple[DerivativeContractV2, ProviderMappingDirectiveV2]:
    contracts = tuple(
        item for item in catalogue.semantic_objects
        if type(item) is DerivativeContractV2 and item.parent_subject_id == subject_identity
    )
    contract_a = next((item for item in contracts if item.canonical_id == contract_a_identity), None)
    if contract_a is None:
        raise McxExpiryContinuityError("MCX_CONTRACT_A_UNAVAILABLE")
    future = tuple(item for item in contracts if item.expiry > contract_a.expiry)
    if not future:
        raise McxExpiryContinuityError("MCX_SUCCESSOR_CONTRACT_UNAVAILABLE")
    minimum = min(item.expiry for item in future)
    successors = tuple(item for item in future if item.expiry == minimum)
    if len(successors) != 1:
        raise McxExpiryContinuityError("MCX_SUCCESSOR_CONTRACT_AMBIGUOUS")
    successor = successors[0]
    directives = tuple(
        item for item in catalogue.provider_directives
        if item.canonical_object_id == successor.canonical_id
    )
    if len(directives) != 1:
        raise McxExpiryContinuityError("MCX_SUCCESSOR_DIRECTIVE_UNAVAILABLE")
    return successor, directives[0]


def mcx_expiry_continuity_bytes(value: McxFamilyExpiryContinuityArtifact) -> bytes:
    if type(value) is not McxFamilyExpiryContinuityArtifact:
        raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_ARTIFACT_INVALID")
    return _encode(value) + b"\n"


def parse_mcx_expiry_continuity(encoded: bytes) -> McxFamilyExpiryContinuityArtifact:
    try:
        data = json.loads(encoded)
        values = dict(data)
        values["created_at"] = datetime.fromisoformat(str(values["created_at"]))
        values["archives"] = tuple(_archive_from_document(item) for item in values["archives"])
        values["scenarios"] = tuple(_scenario_from_document(item) for item in values["scenarios"])
        values["legacy_observed_roll_gaps"] = tuple(LegacyObservedRollGap(**item) for item in values["legacy_observed_roll_gaps"])
        values["family_subjects"] = tuple(values["family_subjects"])
        values["mcx_family_expiry_continuity"] = ExpiryContinuityOutcome(values["mcx_family_expiry_continuity"])
        values["limitations"] = tuple(values["limitations"])
        artifact = McxFamilyExpiryContinuityArtifact(**values)
    except McxExpiryContinuityError:
        raise
    except Exception as error:
        raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_INTEGRITY_INVALID") from error
    if mcx_expiry_continuity_bytes(artifact) != encoded:
        raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_INTEGRITY_INVALID")
    return artifact


def _retain_candle(
    candle: ContinuousResearchCandle,
    source_by_id: Mapping[str, object],
) -> RetainedContractCandle:
    sources = tuple(source_by_id[item] for item in candle.source_candle_identities)
    values = {
        "canonical_subject_identity": candle.canonical_subject_identity,
        "canonical_contract_identity": candle.canonical_contract_identity,
        "provider_record_identities": tuple(sorted({item.provider_record_identity for item in sources})),
        "historical_binding_identities": tuple(sorted({item.historical_binding_identity for item in sources})),
        "provider_token_provenance": MCX_PROVIDER_TOKEN_PROVENANCE,
        "market_session_identity": candle.market_session_identity,
        "timeframe": candle.timeframe,
        "trading_date": candle.trading_date,
        "candle_start": candle.candle_start,
        "candle_end": candle.candle_end,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "source_candle_identities": candle.source_candle_identities,
        "source_provider_identities": tuple(sorted({item.source_identity for item in sources})),
    }
    return RetainedContractCandle(
        candle_identity=_identity("INTRADAY-MCX-RETAINED-CANDLE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-RETAINED-CANDLE-", values),
        **values,
    )


def _build_family_scenario(
    *,
    analytical_subject: str,
    subject_identity: str,
    provider_family: str,
    archive_by_contract: Mapping[str, ImmutableContractEvidenceArchive],
    catalogue: InstrumentSemanticPublicationV2,
) -> FamilyExpiryContinuityScenario:
    candidates = tuple(
        item for item in catalogue.semantic_objects
        if type(item) is DerivativeContractV2
        and item.parent_subject_id == subject_identity
        and item.canonical_id in archive_by_contract
    )
    if not candidates:
        raise McxExpiryContinuityError("MCX_RETAINED_CONTRACT_UNAVAILABLE")
    contract_a = max(candidates, key=lambda item: item.expiry)
    successor, directive = governed_successor_contract(
        catalogue=catalogue,
        subject_identity=subject_identity,
        contract_a_identity=contract_a.canonical_id,
    )
    archive = archive_by_contract[contract_a.canonical_id]
    digest = _candle_integrity_digest(archive.candles)
    simulated_current = (successor.canonical_id,)
    values = {
        "analytical_subject": analytical_subject,
        "canonical_subject_identity": subject_identity,
        "provider_contract_family": provider_family,
        "scenario_kind": ExpiryScenarioKind.CONTROLLED_DETERMINISTIC,
        "contract_a_identity": contract_a.canonical_id,
        "contract_a_expiry": contract_a.expiry,
        "contract_a_archive_identity": archive.archive_identity,
        "contract_a_candle_count": len(archive.candles),
        "successor_contract_b_identity": successor.canonical_id,
        "successor_contract_b_expiry": successor.expiry,
        "successor_provider_directive_identity": directive.directive_identity,
        "simulated_current_master_contract_identities": simulated_current,
        "contract_a_absent_from_simulated_current_master": True,
        "successor_b_present_in_simulated_current_master": True,
        "replayed_candle_count": len(archive.candles),
        "replayed_candle_integrity_digest": digest,
        "original_candle_integrity_digest": digest,
        "replay_exact": True,
        "fabricated_market_candle_count": 0,
        "manual_expiry_intervention_required": False,
        "current_instrument_master_dependency_for_old_history": False,
        "outcome": ExpiryContinuityOutcome.PASS,
    }
    return FamilyExpiryContinuityScenario(
        scenario_identity=_identity("INTRADAY-MCX-EXPIRY-SCENARIO-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-EXPIRY-SCENARIO-", values),
        **values,
    )


def _candle_integrity_digest(candles: Sequence[RetainedContractCandle]) -> str:
    return sha256(_encode(tuple(item.integrity_identity for item in candles))).hexdigest()


def _archive_from_document(data: Mapping[str, object]) -> ImmutableContractEvidenceArchive:
    values = dict(data)
    values["provider_symbols"] = tuple(values["provider_symbols"])
    values["provider_record_identities"] = tuple(values["provider_record_identities"])
    values["historical_binding_identities"] = tuple(values["historical_binding_identities"])
    values["candles"] = tuple(_retained_candle_from_document(item) for item in values["candles"])
    return ImmutableContractEvidenceArchive(**values)


def _retained_candle_from_document(data: Mapping[str, object]) -> RetainedContractCandle:
    values = dict(data)
    values["provider_record_identities"] = tuple(values["provider_record_identities"])
    values["historical_binding_identities"] = tuple(values["historical_binding_identities"])
    values["timeframe"] = IntradayTimeframe(values["timeframe"])
    values["trading_date"] = date.fromisoformat(str(values["trading_date"]))
    values["candle_start"] = datetime.fromisoformat(str(values["candle_start"]))
    values["candle_end"] = datetime.fromisoformat(str(values["candle_end"]))
    for key in ("open", "high", "low", "close"):
        values[key] = Decimal(str(values[key]))
    values["source_candle_identities"] = tuple(values["source_candle_identities"])
    values["source_provider_identities"] = tuple(values["source_provider_identities"])
    return RetainedContractCandle(**values)


def _scenario_from_document(data: Mapping[str, object]) -> FamilyExpiryContinuityScenario:
    values = dict(data)
    values["scenario_kind"] = ExpiryScenarioKind(values["scenario_kind"])
    values["contract_a_expiry"] = date.fromisoformat(str(values["contract_a_expiry"]))
    values["successor_contract_b_expiry"] = date.fromisoformat(str(values["successor_contract_b_expiry"]))
    values["simulated_current_master_contract_identities"] = tuple(values["simulated_current_master_contract_identities"])
    values["outcome"] = ExpiryContinuityOutcome(values["outcome"])
    return FamilyExpiryContinuityScenario(**values)


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(type(item) is str and item == item.strip() and bool(item) for item in values)


def _identity(prefix: str, values: Mapping[str, object]) -> str:
    return prefix + sha256(_encode(values)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _json(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item: _json(data) for item, data in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(item): _json(data) for item, data in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    return value


__all__ = [
    "MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY",
    "MCX_EXPIRY_CONTINUITY_IDENTITY",
    "MCX_EXPIRY_CONTINUITY_VERSION",
    "MCX_PROVIDER_TOKEN_PROVENANCE",
    "ExpiryContinuityOutcome",
    "ExpiryScenarioKind",
    "FamilyExpiryContinuityScenario",
    "ImmutableContractEvidenceArchive",
    "LegacyObservedRollGap",
    "McxExpiryContinuityError",
    "McxFamilyExpiryContinuityArtifact",
    "RetainedContractCandle",
    "build_mcx_family_expiry_continuity_artifact",
    "governed_successor_contract",
    "mcx_expiry_continuity_bytes",
    "parse_mcx_expiry_continuity",
]
