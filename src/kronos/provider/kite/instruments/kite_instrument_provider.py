"""Deterministic Kite instrument resolution over normalized records."""

import re

from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentProvider,
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    ReadOnlyProviderOperation,
)


_STANDARD_FUTURE = re.compile(r"(?P<root>[A-Z]+)\d{2}[A-Z]{3}FUT\Z")


class KiteInstrumentProvider(InstrumentProvider):
    """Read-only Instrument Master access with exact representative resolution."""

    __slots__ = ("__capability",)

    def __init__(
        self,
        capability: AuthenticatedReadOnlyProviderCapability,
    ) -> None:
        if (
            capability.operations != frozenset(ReadOnlyProviderOperation)
            or not callable(getattr(capability, "instrument_records", None))
        ):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            )
        self.__capability = capability

    def retrieve(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        if not self.__capability.active:
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            )
        return self.__capability.instrument_records(exchange)

    def resolve(self, request: InstrumentResolutionRequest) -> InstrumentRecord:
        if type(request) is not InstrumentResolutionRequest:
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.INVALID_REQUEST
            )
        exchange = _exchange_for(request.kind)
        return _resolve_from_records(self.retrieve(exchange), request)

    def resolve_from_records(
        self,
        records: tuple[InstrumentRecord, ...],
        request: InstrumentResolutionRequest,
    ) -> InstrumentRecord:
        if (
            not isinstance(records, tuple)
            or any(type(record) is not InstrumentRecord for record in records)
            or type(request) is not InstrumentResolutionRequest
        ):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.INVALID_REQUEST
            )
        return _resolve_from_records(records, request)

    def __repr__(self) -> str:
        return "<KiteInstrumentProvider read-only>"


def _exchange_for(kind: InstrumentKind) -> str:
    return {
        InstrumentKind.NSE_EQUITY: "NSE",
        InstrumentKind.NSE_INDEX: "NSE",
        InstrumentKind.MCX_FUTURE: "MCX",
        InstrumentKind.CDS_FUTURE: "CDS",
    }[kind]


def _resolve_from_records(
    records: tuple[InstrumentRecord, ...],
    request: InstrumentResolutionRequest,
) -> InstrumentRecord:
    matches = tuple(record for record in records if _matches(record, request))
    if request.kind in {
        InstrumentKind.MCX_FUTURE,
        InstrumentKind.CDS_FUTURE,
    }:
        matches = _nearest_unexpired(matches, request)
    if not matches:
        raise InstrumentResolutionError(InstrumentResolutionFailure.NO_MATCH)
    if len(matches) != 1:
        raise InstrumentResolutionError(
            InstrumentResolutionFailure.AMBIGUOUS_MATCH
        )
    return matches[0]


def _matches(
    record: InstrumentRecord,
    request: InstrumentResolutionRequest,
) -> bool:
    if request.kind is InstrumentKind.NSE_EQUITY:
        return (
            record.exchange == "NSE"
            and record.segment == "NSE"
            and record.trading_symbol == request.symbol
            and record.instrument_type == "EQ"
            and record.expiry is None
        )
    if request.kind is InstrumentKind.NSE_INDEX:
        return (
            request.symbol == "NIFTY"
            and record.exchange == "NSE"
            and record.segment == "INDICES"
            and record.trading_symbol == "NIFTY 50"
            and record.instrument_type == "EQ"
            and record.expiry is None
        )
    expected_segment = (
        "MCX-FUT"
        if request.kind is InstrumentKind.MCX_FUTURE
        else "CDS-FUT"
    )
    future = _STANDARD_FUTURE.fullmatch(record.trading_symbol)
    return (
        record.segment == expected_segment
        and record.instrument_type == "FUT"
        and future is not None
        and future.group("root") == request.symbol
        and record.expiry is not None
        and record.expiry >= request.as_of
    )


def _nearest_unexpired(
    matches: tuple[InstrumentRecord, ...],
    request: InstrumentResolutionRequest,
) -> tuple[InstrumentRecord, ...]:
    eligible = tuple(
        record
        for record in matches
        if record.expiry is not None and record.expiry >= request.as_of
    )
    if not eligible:
        return ()
    nearest = min(record.expiry for record in eligible if record.expiry is not None)
    return tuple(record for record in eligible if record.expiry == nearest)
