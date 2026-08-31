"""Family-local completion adapter for Intraday WO-13 Slice 5."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    WO13_POLICY_CHECKSUM,
    WO13_POLICY_IDENTITY,
    Wo13GeometryAvailability,
)
from kronos.intraday.wo13_geometry import Wo13PriceAuthority
from kronos.intraday.wo13_handoff import WO13_CONTRACT_VERSION, WO13_POLICY_VERSION
from kronos.intraday.wo13_targets import (
    Wo13CanonicalTargetSelection,
    Wo13SetupGeometry,
    Wo13TargetConstraintPopulation,
    Wo13TargetSelectionFailure,
    Wo13TargetSelectionRejected,
    finalize_wo13_canonical_target,
)


WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY = (
    "KRONOS-INTRADAY-WO13-FAMILY-GEOMETRY-ADAPTER-V1"
)


_AUTHORITY = {
    IntradayMarketFamily.NSE_EQUITY: Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
    IntradayMarketFamily.NSE_INDEX: Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
    IntradayMarketFamily.MCX: Wo13PriceAuthority.MCX_ACTIVE_CONTRACT,
}


@dataclass(frozen=True, slots=True)
class Wo13FamilyGeometryAdapterResult:
    adapter_identity: str
    adapter_integrity: str
    market_family: IntradayMarketFamily
    selection: Wo13CanonicalTargetSelection
    family_locality_enforced: bool = True
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    schema_identity: str = WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    family_specific_rr_authority: bool = False
    tick_repair_authority: bool = False
    risk_authority: bool = False
    persistence_authority: bool = False
    runtime_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "adapter_identity", "adapter_integrity")
        if (
            type(self.market_family) is not IntradayMarketFamily
            or type(self.selection) is not Wo13CanonicalTargetSelection
            or not _selection_is_family_local(self.selection, self.market_family)
            or not self.family_locality_enforced
            or self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.schema_identity != WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.family_specific_rr_authority,
                self.tick_repair_authority,
                self.risk_authority,
                self.persistence_authority,
                self.runtime_authority,
                self.execution_authority,
            ))
            or self.adapter_identity
            != _identity("INTRADAY-WO13-FAMILY-ADAPTER-", values)
            or self.adapter_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-FAMILY-ADAPTER-", values)
        ):
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.SELECTION_INTEGRITY_INVALID
            )

    @property
    def geometry_availability(self) -> Wo13GeometryAvailability:
        return self.selection.geometry_availability


def finalize_wo13_family_geometry(
    *,
    setup_geometry: Wo13SetupGeometry,
    candidate_population: Wo13TargetConstraintPopulation,
) -> Wo13FamilyGeometryAdapterResult:
    selection = finalize_wo13_canonical_target(
        setup_geometry=setup_geometry,
        candidate_population=candidate_population,
    )
    entry = selection.entry_reference.selected_fact
    if entry is None or not _selection_is_family_local(selection, entry.market_family):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.CANDIDATE_CONTEXT_MISMATCH
        )
    values = {
        "market_family": entry.market_family,
        "selection": selection,
        "family_locality_enforced": True,
        "policy_identity": WO13_POLICY_IDENTITY,
        "policy_version": WO13_POLICY_VERSION,
        "policy_checksum": WO13_POLICY_CHECKSUM,
        "schema_identity": WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "family_specific_rr_authority": False,
        "tick_repair_authority": False,
        "risk_authority": False,
        "persistence_authority": False,
        "runtime_authority": False,
        "execution_authority": False,
    }
    return Wo13FamilyGeometryAdapterResult(
        adapter_identity=_identity("INTRADAY-WO13-FAMILY-ADAPTER-", values),
        adapter_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-FAMILY-ADAPTER-", values
        ),
        **values,
    )


def _selection_is_family_local(
    selection: Wo13CanonicalTargetSelection,
    family: IntradayMarketFamily,
) -> bool:
    entry = selection.entry_reference.selected_fact
    native = selection.setup_native_target.selected_fact
    canonical = selection.canonical_target.selected_fact
    facts = tuple(item for item in (entry, native, canonical) if item is not None)
    if not facts or entry is None or entry.market_family is not family:
        return False
    mcx = family is IntradayMarketFamily.MCX
    expected_authority = _AUTHORITY[family]
    return all(
        item.canonical_subject_identity == entry.canonical_subject_identity
        and item.market_family is family
        and item.price_authority is expected_authority
        and item.analysis_boundary == entry.analysis_boundary
        and item.instrument_identity == entry.instrument_identity
        and item.actual_contract_identity == entry.actual_contract_identity
        and item.roll_lineage_identity == entry.roll_lineage_identity
        and mcx == (item.actual_contract_identity is not None)
        and mcx == (item.roll_lineage_identity is not None)
        for item in facts
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    encoded = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"{prefix}{sha256(encoded).hexdigest().upper()}"


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if hasattr(value, "as_tuple") else value


__all__ = [
    "WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY",
    "Wo13FamilyGeometryAdapterResult",
    "finalize_wo13_family_geometry",
]
