"""Governed subject-level MCX analytical commissioning publication.

Commissioning admits an MCX analytical subject to the frozen Probables V2
evaluation only. It establishes no execution, Risk, PAPER/LIVE, or broker
authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping


MCX_COMMISSIONING_REGISTRY_IDENTITY = (
    "KRONOS-INTRADAY-MCX-SUBJECT-COMMISSIONING-REGISTRY-V1"
)
MCX_COMMISSIONING_REGISTRY_VERSION = "1.0.0"
MCX_COMMISSIONING_PUBLICATION_VERSION = "1.0.0"
MCX_COMMISSIONING_AUTHORITY = "MCX_SUBJECT_ANALYTICAL_COMMISSIONING_ONLY"
MCX_CONTINUOUS_EVIDENCE_IDENTITY = (
    "INTRADAY-MCX-CONTINUOUS-RESEARCH-"
    "9D9603E2E00EF693A58898215F9C24CB9FEC0C1B01DF63D1984274A5C4D2F125"
)
MCX_CONTINUOUS_EVIDENCE_INTEGRITY = (
    "INTEGRITY-INTRADAY-MCX-CONTINUOUS-RESEARCH-"
    "9D9603E2E00EF693A58898215F9C24CB9FEC0C1B01DF63D1984274A5C4D2F125"
)
MCX_EXPIRY_EVIDENCE_IDENTITY = (
    "INTRADAY-MCX-EXPIRY-CONTINUITY-"
    "6317B1DC4A64472FD414856B44544C78776F3681199188B222EACB97BA6E74C7"
)
MCX_EXPIRY_EVIDENCE_INTEGRITY = (
    "INTEGRITY-INTRADAY-MCX-EXPIRY-CONTINUITY-"
    "6317B1DC4A64472FD414856B44544C78776F3681199188B222EACB97BA6E74C7"
)


class McxCommissioningError(ValueError):
    """Sanitized commissioning publication or resolution failure."""


class McxCommissioningState(StrEnum):
    COMMISSIONED = "COMMISSIONED"
    HELD = "HELD"


@dataclass(frozen=True, slots=True)
class McxSubjectCommissioning:
    canonical_subject_identity: str
    state: McxCommissioningState
    qualification_evidence_identity: str
    qualification_integrity_identity: str
    continuous_evidence_identity: str
    continuous_evidence_integrity: str
    family_expiry_evidence_identity: str
    family_expiry_evidence_integrity: str
    effective_boundary: datetime
    reason: str
    authority: str = MCX_COMMISSIONING_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            or type(self.state) is not McxCommissioningState
            or not _texts((
                self.qualification_evidence_identity,
                self.qualification_integrity_identity,
                self.continuous_evidence_identity,
                self.continuous_evidence_integrity,
                self.family_expiry_evidence_identity,
                self.family_expiry_evidence_integrity,
                self.reason,
                self.authority,
            ))
            or not _aware(self.effective_boundary)
            or self.continuous_evidence_identity != MCX_CONTINUOUS_EVIDENCE_IDENTITY
            or self.continuous_evidence_integrity != MCX_CONTINUOUS_EVIDENCE_INTEGRITY
            or self.family_expiry_evidence_identity != MCX_EXPIRY_EVIDENCE_IDENTITY
            or self.family_expiry_evidence_integrity != MCX_EXPIRY_EVIDENCE_INTEGRITY
            or self.authority != MCX_COMMISSIONING_AUTHORITY
            or (
                self.state is McxCommissioningState.COMMISSIONED
                and self.reason != "EMPIRICALLY_QUALIFIED"
            )
            or (
                self.state is McxCommissioningState.HELD
                and self.reason != "MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED"
            )
        ):
            raise McxCommissioningError("MCX_COMMISSIONING_ENTRY_INVALID")


@dataclass(frozen=True, slots=True)
class McxCommissioningPublication:
    publication_identity: str
    publication_version: str
    entries: tuple[McxSubjectCommissioning, ...]
    effective_boundary: datetime
    authority: str
    provenance: tuple[str, ...]
    integrity_identity: str
    contract_identity: str = MCX_COMMISSIONING_REGISTRY_IDENTITY
    contract_version: str = MCX_COMMISSIONING_REGISTRY_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("publication_identity")
        values.pop("integrity_identity")
        expected = (
            "MCX-SUBJECT-COPPER",
            "MCX-SUBJECT-CRUDE",
            "MCX-SUBJECT-GOLDM",
            "MCX-SUBJECT-NATGAS",
            "MCX-SUBJECT-SILVERM",
        )
        if (
            not self.publication_identity.startswith("INTRADAY-MCX-COMMISSIONING-PUBLICATION-")
            or self.publication_version != MCX_COMMISSIONING_PUBLICATION_VERSION
            or tuple(item.canonical_subject_identity for item in self.entries) != expected
            or any(type(item) is not McxSubjectCommissioning for item in self.entries)
            or not _aware(self.effective_boundary)
            or any(item.effective_boundary != self.effective_boundary for item in self.entries)
            or self.authority != MCX_COMMISSIONING_AUTHORITY
            or not _texts(self.provenance)
            or self.contract_identity != MCX_COMMISSIONING_REGISTRY_IDENTITY
            or self.contract_version != MCX_COMMISSIONING_REGISTRY_VERSION
            or self.publication_identity
            != _identity("INTRADAY-MCX-COMMISSIONING-PUBLICATION-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-COMMISSIONING-PUBLICATION-", values)
        ):
            raise McxCommissioningError("MCX_COMMISSIONING_PUBLICATION_INVALID")

    def subject(self, canonical_subject_identity: str) -> McxSubjectCommissioning:
        matches = tuple(
            item for item in self.entries
            if item.canonical_subject_identity == canonical_subject_identity
        )
        if len(matches) != 1:
            raise McxCommissioningError("MCX_SUBJECT_COMMISSIONING_UNKNOWN")
        return matches[0]


_EFFECTIVE_BOUNDARY = datetime(2026, 8, 29, tzinfo=timezone.utc)
_QUALIFICATION_BINDINGS = (
    ("MCX-SUBJECT-COPPER", McxCommissioningState.COMMISSIONED,
     "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-BF597A43CB7E0875B5382C382D51220393461A5D550A8E13F148EB03B4853DEE"),
    ("MCX-SUBJECT-CRUDE", McxCommissioningState.COMMISSIONED,
     "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-43435ED8F37995BC29CACD6C7DFC21AFC85E5FF57D83825983F59D27DAE45C69"),
    ("MCX-SUBJECT-GOLDM", McxCommissioningState.COMMISSIONED,
     "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-A45B1C61916A8E33A21916C307A382ACF82781DEB4BF147AB93A53068EDA1D29"),
    ("MCX-SUBJECT-NATGAS", McxCommissioningState.HELD,
     "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-30E677016375E03B28FB4D2171DD984401B670FC2F82E123481BAEF6A9FF341A"),
    ("MCX-SUBJECT-SILVERM", McxCommissioningState.COMMISSIONED,
     "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-D179B2E17CCA4D3228738A47037DC23FE1FC50EFA834987C78A56F905BB7CDCC"),
)


def load_mcx_commissioning_publication() -> McxCommissioningPublication:
    entries = tuple(
        McxSubjectCommissioning(
            canonical_subject_identity=subject,
            state=state,
            qualification_evidence_identity=evidence,
            qualification_integrity_identity=f"INTEGRITY-{evidence}",
            continuous_evidence_identity=MCX_CONTINUOUS_EVIDENCE_IDENTITY,
            continuous_evidence_integrity=MCX_CONTINUOUS_EVIDENCE_INTEGRITY,
            family_expiry_evidence_identity=MCX_EXPIRY_EVIDENCE_IDENTITY,
            family_expiry_evidence_integrity=MCX_EXPIRY_EVIDENCE_INTEGRITY,
            effective_boundary=_EFFECTIVE_BOUNDARY,
            reason=(
                "EMPIRICALLY_QUALIFIED"
                if state is McxCommissioningState.COMMISSIONED
                else "MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED"
            ),
        )
        for subject, state, evidence in _QUALIFICATION_BINDINGS
    )
    values = {
        "publication_version": MCX_COMMISSIONING_PUBLICATION_VERSION,
        "entries": entries,
        "effective_boundary": _EFFECTIVE_BOUNDARY,
        "authority": MCX_COMMISSIONING_AUTHORITY,
        "provenance": (
            "KRONOS-INTRADAY-MCX-SUBJECT-LEVEL-PRODUCTION-COMMISSIONING",
            MCX_CONTINUOUS_EVIDENCE_IDENTITY,
            MCX_EXPIRY_EVIDENCE_IDENTITY,
        ),
        "contract_identity": MCX_COMMISSIONING_REGISTRY_IDENTITY,
        "contract_version": MCX_COMMISSIONING_REGISTRY_VERSION,
    }
    return McxCommissioningPublication(
        publication_identity=_identity("INTRADAY-MCX-COMMISSIONING-PUBLICATION-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-COMMISSIONING-PUBLICATION-", values),
        **values,
    )


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _texts(values: tuple[str, ...]) -> bool:
    return bool(values) and all(type(item) is str and bool(item) and item == item.strip() for item in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "MCX_COMMISSIONING_AUTHORITY",
    "MCX_COMMISSIONING_PUBLICATION_VERSION",
    "MCX_COMMISSIONING_REGISTRY_IDENTITY",
    "MCX_COMMISSIONING_REGISTRY_VERSION",
    "McxCommissioningError",
    "McxCommissioningPublication",
    "McxCommissioningState",
    "McxSubjectCommissioning",
    "load_mcx_commissioning_publication",
]
