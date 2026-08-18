"""Read-only projection boundary for the Intraday evidence workstation."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.instrument.runtime import RuntimeInstrument, RuntimeInstrumentRegistry
from kronos.intraday.composition import CoreSlice1FactualComposition
from kronos.intraday.context import Slice1EContext
from kronos.intraday.structure import StructuralEvidence
from kronos.intraday.telemetry import ShadowTelemetryEvidence


@dataclass(frozen=True, slots=True)
class IntradayEvidenceBundle:
    """One immutable, aligned set of factual evidence for Browser inspection."""

    composition: CoreSlice1FactualComposition
    slice1e_context: Slice1EContext | None = None
    structural_evidence: tuple[StructuralEvidence, ...] = ()
    shadow_telemetry: tuple[ShadowTelemetryEvidence, ...] = ()

    def __post_init__(self) -> None:
        if type(self.composition) is not CoreSlice1FactualComposition:
            raise ValueError("INTRADAY_WORKSTATION_BUNDLE_INVALID")
        run = self.composition.run
        instrument = self.composition.instrument
        if (
            self.slice1e_context is not None
            and (
                type(self.slice1e_context) is not Slice1EContext
                or self.slice1e_context.run != run
                or self.slice1e_context.instrument != instrument
            )
        ):
            raise ValueError("INTRADAY_WORKSTATION_BUNDLE_INVALID")
        if any(
            type(item) is not StructuralEvidence
            or item.run != run
            or item.instrument != instrument
            for item in self.structural_evidence
        ):
            raise ValueError("INTRADAY_WORKSTATION_BUNDLE_INVALID")
        if any(
            type(item) is not ShadowTelemetryEvidence
            or item.run != run
            or item.instrument != instrument
            for item in self.shadow_telemetry
        ):
            raise ValueError("INTRADAY_WORKSTATION_BUNDLE_INVALID")

    @property
    def canonical_instrument_id(self) -> str:
        return self.composition.instrument.canonical_instrument_id


@dataclass(frozen=True, slots=True)
class IntradayWorkstationSnapshot:
    instruments: tuple[RuntimeInstrument, ...]
    selected_instrument: RuntimeInstrument | None
    evidence: IntradayEvidenceBundle | None
    runtime_state: str | None = None
    runtime_detail: str = ""

    @property
    def availability(self) -> str:
        if self.runtime_state is not None:
            return self.runtime_state
        if self.selected_instrument is None or self.evidence is None:
            return "UNAVAILABLE"
        return "AVAILABLE"


class IntradayEvidenceWorkstation:
    """Expose governed publications and retained evidence without deriving policy."""

    def __init__(
        self,
        instrument_registry: RuntimeInstrumentRegistry | None = None,
        evidence: tuple[IntradayEvidenceBundle, ...] = (),
    ) -> None:
        if (
            instrument_registry is not None
            and type(instrument_registry) is not RuntimeInstrumentRegistry
        ) or any(type(item) is not IntradayEvidenceBundle for item in evidence):
            raise ValueError("INTRADAY_WORKSTATION_INVALID")
        instruments = () if instrument_registry is None else instrument_registry.instruments
        known = {item.canonical.canonical_instrument_id for item in instruments}
        evidence_ids = tuple(item.canonical_instrument_id for item in evidence)
        if len(set(evidence_ids)) != len(evidence_ids) or any(
            item not in known for item in evidence_ids
        ):
            raise ValueError("INTRADAY_WORKSTATION_INVALID")
        self._instruments = instruments
        self._evidence = {item.canonical_instrument_id: item for item in evidence}

    def snapshot(
        self, selected_canonical_instrument_id: str | None = None
    ) -> IntradayWorkstationSnapshot:
        selected = None
        if selected_canonical_instrument_id:
            selected = next(
                (
                    item for item in self._instruments
                    if item.canonical.canonical_instrument_id
                    == selected_canonical_instrument_id
                ),
                None,
            )
        elif self._instruments:
            selected = self._instruments[0]
        identity = None if selected is None else selected.canonical.canonical_instrument_id
        return IntradayWorkstationSnapshot(
            instruments=self._instruments,
            selected_instrument=selected,
            evidence=None if identity is None else self._evidence.get(identity),
        )


__all__ = [
    "IntradayEvidenceBundle",
    "IntradayEvidenceWorkstation",
    "IntradayWorkstationSnapshot",
]
