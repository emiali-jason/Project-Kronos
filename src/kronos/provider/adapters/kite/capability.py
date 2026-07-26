"""Kite-local documentation and locked-SDK evidence for canonical EDD-002."""

from dataclasses import dataclass
from datetime import datetime

from kronos.provider.models.capability import (
    CapabilityEvidence,
    CapabilityIdentifier,
    CapabilityLimitation,
    EvidenceAssertion,
    EvidenceClass,
    EvidenceCurrentness,
    EvidenceScope,
    ImplementationDisposition,
    ImplementationDispositionEvidence,
    LimitationCategory,
)


KITE_PROVIDER = "KITE"
KITE_API_BASIS = "KITE_CONNECT_API_V3"
KITE_SDK_BASIS = "kiteconnect==5.2.0"

_MARKET_QUOTES_DOCUMENTATION = (
    "https://kite.trade/docs/connect/v3/market-quotes/"
)
_HISTORICAL_DOCUMENTATION = "https://kite.trade/docs/connect/v3/historical/"
_WEBSOCKET_DOCUMENTATION = "https://kite.trade/docs/connect/v3/websocket/"

_CAPABILITY_SOURCES = {
    CapabilityIdentifier.INSTRUMENT_REFERENCE: (
        _MARKET_QUOTES_DOCUMENTATION,
        "pykiteconnect.KiteConnect.instruments@5.2.0",
    ),
    CapabilityIdentifier.FULL_QUOTE_SNAPSHOT: (
        _MARKET_QUOTES_DOCUMENTATION,
        "pykiteconnect.KiteConnect.quote@5.2.0",
    ),
    CapabilityIdentifier.OHLC_SNAPSHOT: (
        _MARKET_QUOTES_DOCUMENTATION,
        "pykiteconnect.KiteConnect.ohlc@5.2.0",
    ),
    CapabilityIdentifier.LTP_SNAPSHOT: (
        _MARKET_QUOTES_DOCUMENTATION,
        "pykiteconnect.KiteConnect.ltp@5.2.0",
    ),
    CapabilityIdentifier.HISTORICAL_OBSERVATION: (
        _HISTORICAL_DOCUMENTATION,
        "pykiteconnect.KiteConnect.historical_data@5.2.0",
    ),
    CapabilityIdentifier.LIVE_OBSERVATION_STREAMING: (
        _WEBSOCKET_DOCUMENTATION,
        "pykiteconnect.KiteTicker@5.2.0",
    ),
}

_LIMITATIONS = {
    CapabilityIdentifier.INSTRUMENT_REFERENCE: (
        (
            LimitationCategory.DATA_CURRENTNESS,
            "The documented instrument dump is generated once daily.",
        ),
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "The documented instrument dump is large and is not a lightweight "
            "current-state response.",
        ),
        (
            LimitationCategory.DATA_CURRENTNESS,
            "The documented last_price value in the instrument dump is not "
            "real-time.",
        ),
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "Instrument tokens may be reused by the Provider and are not a "
            "permanent identity by themselves.",
        ),
    ),
    CapabilityIdentifier.FULL_QUOTE_SNAPSHOT: (
        (
            LimitationCategory.REQUEST_SIZE,
            "The documented maximum is 500 instruments per request.",
        ),
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "Requested keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.OHLC_SNAPSHOT: (
        (
            LimitationCategory.REQUEST_SIZE,
            "The documented maximum is 1000 instruments per request.",
        ),
        (
            LimitationCategory.DATA_CURRENTNESS,
            "The response is a current snapshot, not a completed historical candle.",
        ),
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "Requested instrument keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.LTP_SNAPSHOT: (
        (
            LimitationCategory.REQUEST_SIZE,
            "The documented maximum is 1000 instruments per request.",
        ),
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "Requested keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.HISTORICAL_OBSERVATION: (
        (
            LimitationCategory.INTERVAL_SUPPORT,
            "Documented intervals are minute, day, 3minute, 5minute, "
            "10minute, 15minute, 30minute and 60minute.",
        ),
        (
            LimitationCategory.PROVIDER_SCOPE,
            "Continuous history is limited to documented NFO and MCX futures "
            "behaviour and day candles.",
        ),
    ),
    CapabilityIdentifier.LIVE_OBSERVATION_STREAMING: (
        (
            LimitationCategory.OTHER_DOCUMENTED_TECHNICAL_CONSTRAINT,
            "The documented streaming modes are ltp, quote and full.",
        ),
        (
            LimitationCategory.SUBSCRIPTION_COUNT,
            "The documented maximum is 3000 instruments per connection.",
        ),
        (
            LimitationCategory.CONNECTION_COUNT,
            "The documented maximum is three WebSocket connections per API key.",
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class KiteCapabilityEvidenceBundle:
    """Adapter-local bundle containing no SDK object or Provider payload."""

    evidence: tuple[CapabilityEvidence, ...]
    limitations: tuple[CapabilityLimitation, ...]

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(item.source_reference for item in self.evidence)

    @property
    def evidence_classes(self) -> tuple[EvidenceClass, ...]:
        return tuple(item.evidence_class for item in self.evidence)


def kite_capability_evidence(
    capability_identifier: CapabilityIdentifier,
    *,
    evidence_time: datetime,
    adapter_revision: str,
) -> KiteCapabilityEvidenceBundle:
    """Build static official-documentation and SDK-compatibility evidence."""

    documentation, sdk_reference = _CAPABILITY_SOURCES[capability_identifier]
    prefix = capability_identifier.value.casefold()
    documentation_id = f"kite:{prefix}:official-documentation"
    evidence = (
        CapabilityEvidence(
            evidence_id=documentation_id,
            evidence_class=EvidenceClass.OFFICIAL_PROVIDER_DOCUMENTATION,
            provider=KITE_PROVIDER,
            capability_identifier=capability_identifier,
            source_reference=documentation,
            assertion=EvidenceAssertion.SUPPORTS,
            provider_api_basis=KITE_API_BASIS,
            currentness=EvidenceCurrentness.CURRENT,
            scope=EvidenceScope.PROVIDER_WIDE,
            evidence_time=evidence_time,
        ),
        CapabilityEvidence(
            evidence_id=f"kite:{prefix}:sdk-compatibility",
            evidence_class=(
                EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
            ),
            provider=KITE_PROVIDER,
            capability_identifier=capability_identifier,
            source_reference=sdk_reference,
            assertion=EvidenceAssertion.COMPATIBLE,
            provider_api_basis=KITE_API_BASIS,
            currentness=EvidenceCurrentness.CURRENT,
            scope=EvidenceScope.PROVIDER_WIDE,
            evidence_time=evidence_time,
            sdk_version_basis=KITE_SDK_BASIS,
            adapter_revision_basis=adapter_revision,
        ),
    )
    limitations = tuple(
        CapabilityLimitation(
            limitation_id=f"kite:{prefix}:limitation:{index}",
            capability_identifier=capability_identifier,
            provider=KITE_PROVIDER,
            category=category,
            description=description,
            source_evidence_id=documentation_id,
            provider_api_basis=KITE_API_BASIS,
            currentness=EvidenceCurrentness.CURRENT,
            determination_time=evidence_time,
        )
        for index, (category, description) in enumerate(
            _LIMITATIONS[capability_identifier],
            start=1,
        )
    )
    return KiteCapabilityEvidenceBundle(evidence=evidence, limitations=limitations)


def kite_implementation_evidence(
    repository_revision: str,
) -> dict[CapabilityIdentifier, ImplementationDispositionEvidence]:
    """Represent the canonical EDD-002 initial implementation dispositions."""

    if not repository_revision.strip():
        raise ValueError("repository revision is required")
    evidence = {
        identifier: ImplementationDispositionEvidence(
            capability_identifier=identifier,
            disposition=ImplementationDisposition.NOT_IMPLEMENTED,
            authority_reference="EDD-002:INITIAL_IMPLEMENTATION_DISPOSITION",
            repository_revision=repository_revision,
        )
        for identifier in CapabilityIdentifier
        if identifier is not CapabilityIdentifier.LIVE_OBSERVATION_STREAMING
    }
    evidence[CapabilityIdentifier.LIVE_OBSERVATION_STREAMING] = (
        ImplementationDispositionEvidence(
            capability_identifier=(
                CapabilityIdentifier.LIVE_OBSERVATION_STREAMING
            ),
            disposition=ImplementationDisposition.DEFERRED,
            authority_reference="ADR-007:CURRENT_PHASE_ROADMAP",
            repository_revision=repository_revision,
            reason="Implementation is outside the current authorized phase.",
        )
    )
    return evidence


def kite_approved_evidence_references(
) -> dict[CapabilityIdentifier, frozenset[str]]:
    """Return the bounded official and SDK evidence-source allowlist."""

    return {
        identifier: frozenset(references)
        for identifier, references in _CAPABILITY_SOURCES.items()
    }
