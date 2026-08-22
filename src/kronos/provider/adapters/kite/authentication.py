"""Adapter-local Kite exchange, candidate and verification containment."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kiteconnect.exceptions import (
    DataException as _DataException,
    KiteException as _KiteException,
    NetworkException as _NetworkException,
    PermissionException as _PermissionException,
    TokenException as _TokenException,
)
from requests.exceptions import (
    ConnectionError as _RequestsConnectionError,
    Timeout as _RequestsTimeout,
)

from kronos.configuration.credentials import SecretLease
from kronos.configuration.principals import PrincipalBindingResult, PrincipalEvidence
from kronos.provider.adapters.kite.client import (
    _KiteAuthenticationClientHandle,
    _KiteCandidateClientHandle,
    _KiteCleanupError,
    _KiteClientClosedError,
    _KiteExchangeAlreadyAttempted,
    _KiteSessionInvalidated,
    _UnexpectedAuthenticationResponse,
    _UnexpectedProfileResponse,
    _create_kite_authentication_client,
)
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    OneUseRequestToken,
    ReadOnlyProviderOperation,
)
from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
)
from kronos.provider.contracts.instrument_master import (
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentMasterError,
    ProviderInstrumentMasterFailure,
    ProviderInstrumentMasterSourceRecord,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
    create_provider_instrument_master_source_record,
    provider_instrument_schema_error,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
    LiveSnapshotError,
    LiveSnapshotFailure,
    LtpSnapshot,
    OhlcSnapshot,
    OhlcValues,
    QuoteSnapshot,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConsumer,
    MonitoringError,
    MonitoringFailure,
    ReadOnlyMonitoringSession,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.kite.live_activation import RemainingBudget
from kronos.provider.models.authentication import GovernedAuthenticationOperation
from kronos.instrument.runtime import (
    ProviderInstrumentAssertion,
    create_provider_assertion,
)


_CANONICAL_PRINCIPAL = re.compile(r"[A-Za-z0-9]{1,64}\Z")
_KITE_MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


class KiteContextEvidence(StrEnum):
    """Sanitized result of one explicit Kite availability verification."""

    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    UNAVAILABLE = "PROVIDER_OPERATIONALLY_UNAVAILABLE"


class _KitePrincipalEvidence:
    """One-use minimum principal evidence with no raw-value getter."""

    __slots__ = ("_closed", "_forced", "_principal", "_used")

    def __init__(
        self,
        principal: str | None,
        *,
        forced: PrincipalBindingResult | None = None,
    ) -> None:
        self._principal = principal
        self._forced = forced
        self._used = False
        self._closed = False

    def compare_expected(self, expected_principal: str) -> PrincipalBindingResult:
        if self._closed or self._used:
            raise RuntimeError("PRINCIPAL_EVIDENCE_UNAVAILABLE")
        self._used = True
        principal = self._principal
        self._principal = None
        try:
            if self._forced is not None:
                return self._forced
            if not _canonical_principal(principal) or not _canonical_principal(
                expected_principal
            ):
                return PrincipalBindingResult.UNCONFIRMED
            return (
                PrincipalBindingResult.MATCHED
                if principal == expected_principal
                else PrincipalBindingResult.MISMATCHED
            )
        finally:
            self.close()

    def close(self) -> None:
        self._principal = None
        self._closed = True

    def __repr__(self) -> str:
        return "<_KitePrincipalEvidence redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_PRINCIPAL_EVIDENCE_SERIALIZATION_PROHIBITED")


class _KiteCandidateContext:
    """Opaque unpublished candidate restricted to bounded verification."""

    __slots__ = (
        "__budget",
        "__capability_issued",
        "__disposed",
        "__handle",
        "__instrument_tokens",
        "__principal_requested",
        "__record",
    )

    def __init__(
        self,
        handle: _KiteCandidateClientHandle,
        *,
        operation_recorder: Callable[[GovernedAuthenticationOperation], None] | None,
        remaining_budget: Callable[[], RemainingBudget] | None,
    ) -> None:
        self.__handle: _KiteCandidateClientHandle | None = handle
        self.__record = operation_recorder
        self.__budget = remaining_budget
        self.__disposed = False
        self.__principal_requested = False
        self.__capability_issued = False
        self.__instrument_tokens: dict[InstrumentRecord, int] = {}

    def principal_evidence(self) -> PrincipalEvidence:
        self.__principal_requested = True
        timeout_seconds = self.__before(
            GovernedAuthenticationOperation.PRINCIPAL_PROFILE_VERIFICATION
        )
        handle = self._active_handle()
        try:
            principal = handle.principal_user_id_once(
                timeout_seconds=timeout_seconds
            )
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return _KitePrincipalEvidence(principal)

        if code is ProviderErrorCode.UNEXPECTED_RESPONSE:
            return _KitePrincipalEvidence(
                None,
                forced=PrincipalBindingResult.UNCONFIRMED,
            )
        if _operationally_unavailable(code):
            return _KitePrincipalEvidence(
                None,
                forced=PrincipalBindingResult.UNAVAILABLE,
            )
        raise ProviderConnectivityError(code) from None

    def issue_read_only_capability(self) -> AuthenticatedReadOnlyProviderCapability:
        """Issue one opaque handoff after principal evidence has been requested."""

        if (
            self.__disposed
            or not self.__principal_requested
            or self.__capability_issued
        ):
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        self._active_handle()
        self.__capability_issued = True
        return _KiteReadOnlyProviderCapability(self)

    def verify_provider_availability(self) -> KiteContextEvidence:
        """Run one separate, explicitly initiated profile verification."""

        timeout_seconds = self.__before(
            GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
        )

        try:
            self._active_handle().verify_profile_once(
                timeout_seconds=timeout_seconds
            )
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return KiteContextEvidence.VALID
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            return KiteContextEvidence.INVALID
        if _operationally_unavailable(code):
            return KiteContextEvidence.UNAVAILABLE
        raise ProviderConnectivityError(code) from None

    def dispose_local(self) -> None:
        """Release only local SDK/session state; never mutate Provider state."""

        if self.__disposed:
            return
        self.__disposed = True
        self.__instrument_tokens.clear()
        handle = self.__handle
        self.__handle = None
        if handle is None:
            return
        try:
            handle.close_local()
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            return
        raise ProviderConnectivityError(code)

    def _active_handle(self) -> _KiteCandidateClientHandle:
        handle = self.__handle
        if self.__disposed or handle is None:
            raise ProviderConnectivityError(ProviderErrorCode.INTERNAL_ADAPTER_DEFECT)
        return handle

    def _read_only_capability_active(self) -> bool:
        handle = self.__handle
        return not self.__disposed and handle is not None and handle.active

    def _instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        if not _canonical_exchange(exchange):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.INVALID_REQUEST
            )
        try:
            raw = self._active_handle().instrument_records(exchange)
            normalized = _normalize_instrument_records(
                raw,
                expected_exchange=exchange,
            )
        except InstrumentResolutionError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            retained = {
                record: token
                for record, token in self.__instrument_tokens.items()
                if record.exchange != exchange
            }
            retained.update({record: token for record, token in normalized})
            self.__instrument_tokens = retained
            return tuple(record for record, _token in normalized)
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            self.dispose_local()
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            ) from None
        raise ProviderConnectivityError(code) from None

    def _instrument_master_records(
        self,
    ) -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
        """Acquire the consolidated master without releasing raw SDK material."""

        try:
            raw = self._active_handle().instrument_master_records()
            normalized = _normalize_instrument_master_records(raw)
        except ProviderInstrumentMasterError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            self.__instrument_tokens = {
                item.sanitized_instrument_record(): item.provider_instrument_token
                for item in normalized
            }
            return normalized
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            self.dispose_local()
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE
            ) from None
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.PROVIDER_ACQUISITION_FAILED
        ) from None

    def _instrument_assertions(
        self,
        exchange: str,
        *,
        source_boundary: datetime,
        valid_through: datetime,
    ) -> tuple[ProviderInstrumentAssertion, ...]:
        """Publish governed Provider facts without exposing the private token map."""

        if (
            not _canonical_exchange(exchange)
            or not _aware(source_boundary)
            or not _aware(valid_through)
            or valid_through < source_boundary
        ):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.INVALID_REQUEST
            )
        records = self._instrument_records(exchange)
        material = tuple(
            {
                "provider": record.provider,
                "exchange": record.exchange,
                "segment": record.segment,
                "symbol": record.trading_symbol,
                "instrument_type": record.instrument_type,
                "expiry": None if record.expiry is None else record.expiry.isoformat(),
                "token": self.__instrument_tokens[record],
            }
            for record in records
        )
        digest = sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest().upper()
        source_identity = f"KITE-INSTRUMENT-MASTER-{digest[:24]}"
        return tuple(
            create_provider_assertion(
                provider=record.provider,
                provider_symbol=record.trading_symbol,
                provider_instrument_token=self.__instrument_tokens[record],
                exchange=record.exchange,
                segment=record.segment,
                instrument_type=record.instrument_type,
                asserted_tick_size=(
                    record.tick_size
                    if record.tick_size is not None and record.tick_size > 0
                    else None
                ),
                asserted_lot_size=(
                    record.lot_size
                    if record.lot_size is not None and record.lot_size > 0
                    else None
                ),
                binding_source_identity=source_identity,
                source_boundary=source_boundary,
                valid_through=valid_through,
            )
            for record in records
        )

    def _historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        if type(request) is not HistoricalCandleRequest:
            raise HistoricalDataError(HistoricalDataFailure.INVALID_REQUEST)
        token = self.__instrument_tokens.get(request.instrument)
        if token is None:
            raise HistoricalDataError(
                HistoricalDataFailure.INSTRUMENT_NOT_RESOLVED
            )
        try:
            raw = self._active_handle().historical_candles(
                instrument_token=token,
                from_date=request.start,
                to_date=request.end,
                interval=request.interval.value,
            )
            candles = _normalize_historical_candles(raw)
            leading_overlap = _historical_interval_span(request.interval)
            if any(
                candle.timestamp < request.start - leading_overlap
                or candle.timestamp > request.end
                for candle in candles
            ):
                raise HistoricalDataError(
                    HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
            return candles
        except HistoricalDataError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            self.dispose_local()
            raise HistoricalDataError(
                HistoricalDataFailure.CAPABILITY_UNAVAILABLE
            ) from None
        raise HistoricalDataError(HistoricalDataFailure.PROVIDER_FAILURE) from None

    def _live_snapshot(
        self,
        instrument: InstrumentRecord,
        operation: ReadOnlyProviderOperation,
    ) -> QuoteSnapshot | LtpSnapshot | OhlcSnapshot:
        if type(instrument) is not InstrumentRecord or operation not in {
            ReadOnlyProviderOperation.QUOTE,
            ReadOnlyProviderOperation.LTP,
            ReadOnlyProviderOperation.OHLC,
        }:
            raise LiveSnapshotError(LiveSnapshotFailure.INVALID_REQUEST)
        token = self.__instrument_tokens.get(instrument)
        if token is None:
            raise LiveSnapshotError(LiveSnapshotFailure.INSTRUMENT_NOT_RESOLVED)
        kite_identity = f"{instrument.exchange}:{instrument.trading_symbol}"
        handle = self._active_handle()
        try:
            if operation is ReadOnlyProviderOperation.QUOTE:
                raw = handle.quote(kite_identity)
                return _normalize_quote_snapshot(
                    raw,
                    instrument=instrument,
                    kite_identity=kite_identity,
                    expected_token=token,
                )
            if operation is ReadOnlyProviderOperation.LTP:
                raw = handle.ltp(kite_identity)
                return _normalize_ltp_snapshot(
                    raw,
                    instrument=instrument,
                    kite_identity=kite_identity,
                    expected_token=token,
                )
            raw = handle.ohlc(kite_identity)
            return _normalize_ohlc_snapshot(
                raw,
                instrument=instrument,
                kite_identity=kite_identity,
                expected_token=token,
            )
        except LiveSnapshotError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            self.dispose_local()
            raise LiveSnapshotError(
                LiveSnapshotFailure.CAPABILITY_UNAVAILABLE
            ) from None
        raise LiveSnapshotError(LiveSnapshotFailure.PROVIDER_FAILURE) from None

    def _open_monitoring_session(
        self,
        consumer: MonitoringConsumer,
    ) -> ReadOnlyMonitoringSession:
        if not callable(getattr(consumer, "on_market_tick", None)) or not callable(
            getattr(consumer, "on_order_update", None)
        ) or not callable(getattr(consumer, "on_connection_state", None)):
            raise MonitoringError(MonitoringFailure.INVALID_REQUEST)

        def token_resolver(instrument: InstrumentRecord) -> int | None:
            return self.__instrument_tokens.get(instrument)

        try:
            return self._active_handle().open_monitoring_session(
                token_resolver=token_resolver,
                consumer=consumer,
            )  # type: ignore[return-value]
        except MonitoringError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            self.dispose_local()
            raise MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE) from None
        raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE) from None

    def __before(
        self,
        operation: GovernedAuthenticationOperation,
    ) -> float | None:
        budget = self.__budget
        record = self.__record
        if budget is None and record is None:
            return None
        try:
            if budget is None or record is None:
                raise TypeError
            remaining = budget()
            if type(remaining) is not RemainingBudget:
                raise TypeError
            remaining.require_available()
            record(operation)
            return remaining.seconds
        except Exception:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            ) from None

    def __repr__(self) -> str:
        return "<_KiteCandidateContext redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_CANDIDATE_SERIALIZATION_PROHIBITED")


_READ_ONLY_OPERATIONS = frozenset(ReadOnlyProviderOperation)


class _KiteReadOnlyProviderCapability:
    """Opaque application handoff retaining the private candidate ownership chain."""

    __slots__ = ("__candidate",)

    def __init__(self, candidate: _KiteCandidateContext) -> None:
        self.__candidate = candidate

    @property
    def operations(self) -> frozenset[ReadOnlyProviderOperation]:
        return _READ_ONLY_OPERATIONS

    @property
    def active(self) -> bool:
        return self.__candidate._read_only_capability_active()

    def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        if not self.active:
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            )
        return self.__candidate._instrument_records(exchange)

    def instrument_master_records(
        self,
    ) -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
        if not self.active:
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE
            )
        return self.__candidate._instrument_master_records()

    def instrument_assertions(
        self,
        exchange: str,
        *,
        source_boundary: datetime,
        valid_through: datetime,
    ) -> tuple[ProviderInstrumentAssertion, ...]:
        if not self.active:
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
            )
        return self.__candidate._instrument_assertions(
            exchange,
            source_boundary=source_boundary,
            valid_through=valid_through,
        )

    def historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        if not self.active:
            raise HistoricalDataError(
                HistoricalDataFailure.CAPABILITY_UNAVAILABLE
            )
        return self.__candidate._historical_candles(request)

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        if not self.active:
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE)
        result = self.__candidate._live_snapshot(
            instrument,
            ReadOnlyProviderOperation.QUOTE,
        )
        if type(result) is not QuoteSnapshot:
            raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
        return result

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        if not self.active:
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE)
        result = self.__candidate._live_snapshot(
            instrument,
            ReadOnlyProviderOperation.LTP,
        )
        if type(result) is not LtpSnapshot:
            raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
        return result

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        if not self.active:
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE)
        result = self.__candidate._live_snapshot(
            instrument,
            ReadOnlyProviderOperation.OHLC,
        )
        if type(result) is not OhlcSnapshot:
            raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
        return result

    def open_monitoring_session(
        self,
        consumer: MonitoringConsumer,
    ) -> ReadOnlyMonitoringSession:
        if not self.active:
            raise MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE)
        return self.__candidate._open_monitoring_session(consumer)

    def __repr__(self) -> str:
        return "<AuthenticatedReadOnlyProviderCapability redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("READ_ONLY_PROVIDER_CAPABILITY_SERIALIZATION_PROHIBITED")


def _historical_interval_span(interval: HistoricalInterval) -> timedelta:
    minutes = {
        HistoricalInterval.MINUTE: 1,
        HistoricalInterval.THREE_MINUTE: 3,
        HistoricalInterval.FIVE_MINUTE: 5,
        HistoricalInterval.TEN_MINUTE: 10,
        HistoricalInterval.FIFTEEN_MINUTE: 15,
        HistoricalInterval.THIRTY_MINUTE: 30,
        HistoricalInterval.SIXTY_MINUTE: 60,
        HistoricalInterval.DAY: 24 * 60,
    }[interval]
    return timedelta(minutes=minutes)


_CANONICAL_EXCHANGE = re.compile(r"[A-Z]{2,8}\Z")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _canonical_exchange(value: object) -> bool:
    return isinstance(value, str) and _CANONICAL_EXCHANGE.fullmatch(value) is not None


def _normalize_instrument_records(
    raw: object,
    *,
    expected_exchange: str,
) -> tuple[tuple[InstrumentRecord, int], ...]:
    if not isinstance(raw, list):
        raise InstrumentResolutionError(
            InstrumentResolutionFailure.MALFORMED_PROVIDER_DATA
        )
    normalized: list[tuple[InstrumentRecord, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.MALFORMED_PROVIDER_DATA
            )
        exchange = item.get("exchange")
        segment = item.get("segment")
        trading_symbol = item.get("tradingsymbol")
        name = item.get("name")
        instrument_type = item.get("instrument_type")
        instrument_token = item.get("instrument_token")
        tick_size = _nonnegative_decimal(item.get("tick_size"))
        lot_size = item.get("lot_size")
        expiry = _normalized_expiry(item.get("expiry"))
        normalized_name = name.strip() if isinstance(name, str) else name
        if (
            exchange != expected_exchange
            or not _canonical_text(segment)
            or not _canonical_text(trading_symbol)
            or not _canonical_optional_text(normalized_name)
            or not _canonical_optional_text(instrument_type)
            or type(instrument_token) is not int
            or instrument_token <= 0
            or tick_size is None
            or type(lot_size) is not int
            or lot_size < 0
            or expiry is _MALFORMED_EXPIRY
        ):
            raise InstrumentResolutionError(
                InstrumentResolutionFailure.MALFORMED_PROVIDER_DATA
            )
        normalized.append(
            (
                InstrumentRecord(
                    provider="KITE",
                    exchange=exchange,
                    segment=segment,
                    trading_symbol=trading_symbol,
                    name=normalized_name,
                    instrument_type=instrument_type,
                    expiry=expiry,
                    tick_size=tick_size,
                    lot_size=lot_size,
                ),
                instrument_token,
            )
        )
    return tuple(normalized)


def _normalize_instrument_master_records(
    raw: object,
) -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
    if not isinstance(raw, list):
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.PROVIDER_DATASET_UNAVAILABLE
        )
    normalized: list[ProviderInstrumentMasterSourceRecord] = []
    for ordinal, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
                rule=ProviderInstrumentValidationRule.RECORD_MAPPING_REQUIRED,
                field_family=ProviderInstrumentFieldFamily.RECORD,
                value_classification=(
                    ProviderInstrumentValueClassification.NULL
                    if item is None
                    else ProviderInstrumentValueClassification.MALFORMED
                ),
                input_ordinal=ordinal,
            )
        expiry = _normalized_expiry(item.get("expiry"))
        if expiry is _MALFORMED_EXPIRY:
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
                rule=ProviderInstrumentValidationRule.EXPIRY_SHAPE_INVALID,
                field_family=ProviderInstrumentFieldFamily.EXPIRY,
                value_classification=ProviderInstrumentValueClassification.MALFORMED,
                input_ordinal=ordinal,
            )
        name = item.get("name")
        normalized_name = name.strip() if isinstance(name, str) else name
        exchange_token = _normalized_exchange_token(item.get("exchange_token"))
        missing_fields = frozenset(
            internal
            for provider_field, internal in (
                ("instrument_token", "provider_instrument_token"),
                ("tradingsymbol", "trading_symbol"),
                ("name", "name"),
                ("tick_size", "tick_size"),
                ("lot_size", "lot_size"),
                ("instrument_type", "instrument_type"),
                ("segment", "segment"),
                ("exchange", "exchange"),
            )
            if provider_field not in item
        )
        record = create_provider_instrument_master_source_record(
            provider="KITE",
            provider_instrument_token=item.get("instrument_token"),
            exchange_token=exchange_token,
            trading_symbol=item.get("tradingsymbol"),
            name=normalized_name,
            last_price=item.get("last_price"),
            expiry=expiry,
            strike=item.get("strike"),
            tick_size=item.get("tick_size"),
            lot_size=item.get("lot_size"),
            instrument_type=item.get("instrument_type"),
            segment=item.get("segment"),
            exchange=item.get("exchange"),
            missing_fields=missing_fields,
            phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
            input_ordinal=ordinal,
        )
        normalized.append(record)
    if not normalized:
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.PROVIDER_DATASET_UNAVAILABLE
        )
    return tuple(normalized)


_MALFORMED_EXPIRY = object()


def _normalized_expiry(value: object) -> date | None | object:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    return _MALFORMED_EXPIRY


def _normalized_exchange_token(value: object) -> object:
    """Normalize only CA-approved canonical ASCII decimal text."""

    if type(value) is not str or re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None:
        return value
    try:
        return int(value)
    except ValueError:
        return value


def _canonical_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _canonical_optional_text(value: object) -> bool:
    return isinstance(value, str) and value == value.strip()


def _nonnegative_decimal(value: object) -> Decimal | None:
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _normalize_historical_candles(raw: object) -> tuple[HistoricalCandle, ...]:
    if not isinstance(raw, list):
        raise HistoricalDataError(HistoricalDataFailure.MALFORMED_PROVIDER_DATA)
    candles: list[HistoricalCandle] = []
    previous_timestamp: datetime | None = None
    for item in raw:
        if not isinstance(item, dict):
            raise HistoricalDataError(
                HistoricalDataFailure.MALFORMED_PROVIDER_DATA
            )
        timestamp = item.get("date")
        try:
            candle = HistoricalCandle(
                timestamp=timestamp,  # type: ignore[arg-type]
                open=_price(item.get("open")),
                high=_price(item.get("high")),
                low=_price(item.get("low")),
                close=_price(item.get("close")),
                volume=_volume(item.get("volume")),
            )
        except (TypeError, ValueError):
            raise HistoricalDataError(
                HistoricalDataFailure.MALFORMED_PROVIDER_DATA
            ) from None
        if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
            raise HistoricalDataError(
                HistoricalDataFailure.MALFORMED_PROVIDER_DATA
            )
        previous_timestamp = candle.timestamp
        candles.append(candle)
    return tuple(candles)


def _normalize_quote_snapshot(
    raw: object,
    *,
    instrument: InstrumentRecord,
    kite_identity: str,
    expected_token: int,
) -> QuoteSnapshot:
    item = _live_snapshot_item(
        raw,
        kite_identity=kite_identity,
        expected_token=expected_token,
    )
    try:
        return QuoteSnapshot(
            instrument=instrument,
            timestamp=_quote_timestamp(item.get("timestamp")),
            last_price=_price(item.get("last_price")),
            volume=_quote_volume(item.get("volume"), instrument=instrument),
            ohlc=_normalize_ohlc_values(item.get("ohlc")),
        )
    except (TypeError, ValueError):
        raise LiveSnapshotError(
            LiveSnapshotFailure.MALFORMED_PROVIDER_DATA
        ) from None


def _quote_timestamp(value: object) -> datetime:
    """Normalize KiteConnect's exchange-local naive quote timestamp only."""

    if not isinstance(value, datetime):
        raise ValueError
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_KITE_MARKET_TIMEZONE)
    return value


def _quote_volume(
    value: object,
    *,
    instrument: InstrumentRecord,
) -> int | None:
    """Preserve Kite's legitimate unavailable volume for index quotes only."""

    if value is None and instrument.segment == "INDICES":
        return None
    return _volume(value)


def _normalize_ltp_snapshot(
    raw: object,
    *,
    instrument: InstrumentRecord,
    kite_identity: str,
    expected_token: int,
) -> LtpSnapshot:
    item = _live_snapshot_item(
        raw,
        kite_identity=kite_identity,
        expected_token=expected_token,
    )
    try:
        return LtpSnapshot(
            instrument=instrument,
            last_price=_price(item.get("last_price")),
        )
    except (TypeError, ValueError):
        raise LiveSnapshotError(
            LiveSnapshotFailure.MALFORMED_PROVIDER_DATA
        ) from None


def _normalize_ohlc_snapshot(
    raw: object,
    *,
    instrument: InstrumentRecord,
    kite_identity: str,
    expected_token: int,
) -> OhlcSnapshot:
    item = _live_snapshot_item(
        raw,
        kite_identity=kite_identity,
        expected_token=expected_token,
    )
    try:
        return OhlcSnapshot(
            instrument=instrument,
            last_price=_price(item.get("last_price")),
            ohlc=_normalize_ohlc_values(item.get("ohlc")),
        )
    except (TypeError, ValueError):
        raise LiveSnapshotError(
            LiveSnapshotFailure.MALFORMED_PROVIDER_DATA
        ) from None


def _live_snapshot_item(
    raw: object,
    *,
    kite_identity: str,
    expected_token: int,
) -> Mapping[object, object]:
    if (
        not isinstance(raw, Mapping)
        or len(raw) != 1
        or kite_identity not in raw
        or not isinstance(raw[kite_identity], Mapping)
    ):
        raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
    item = raw[kite_identity]
    if item.get("instrument_token") != expected_token:
        raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
    return item


def _normalize_ohlc_values(raw: object) -> OhlcValues:
    if not isinstance(raw, Mapping):
        raise ValueError
    return OhlcValues(
        open=_price(raw.get("open")),
        high=_price(raw.get("high")),
        low=_price(raw.get("low")),
        close=_price(raw.get("close")),
    )


def _price(value: object) -> float:
    if type(value) not in {int, float}:
        raise ValueError
    return float(value)


def _volume(value: object) -> int:
    if type(value) is not int:
        raise ValueError
    return value


class KiteAuthenticationAdapter:
    """Contain SDK and credential mechanics behind the Kite boundary."""

    __slots__ = (
        "__api_secret",
        "__budget",
        "__client",
        "__legacy_candidate",
        "__record",
    )

    def __init__(
        self,
        api_secret: str | None,
        client: _KiteAuthenticationClientHandle,
        *,
        operation_recorder: Callable[[GovernedAuthenticationOperation], None] | None = None,
        remaining_budget: Callable[[], RemainingBudget] | None = None,
    ) -> None:
        self.__api_secret = api_secret
        self.__client: _KiteAuthenticationClientHandle | None = client
        self.__legacy_candidate: _KiteCandidateContext | None = None
        self.__record = operation_recorder
        self.__budget = remaining_budget

    def login_url(self, redirect_uri: str | None = None) -> str:
        self.__before(GovernedAuthenticationOperation.LOGIN_URL_GENERATION)
        if redirect_uri is not None and not redirect_uri:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        client = self.__client
        if client is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            return client.login_url()
        except Exception as error:
            code = _map_authentication_error_code(error)
        raise ProviderConnectivityError(code)

    def exchange_once(
        self,
        request_token: OneUseRequestToken,
        api_secret: SecretLease,
    ) -> _KiteCandidateContext:
        """Consume one token and secret and return one unpublished candidate."""

        timeout_seconds = self.__before(
            GovernedAuthenticationOperation.SESSION_EXCHANGE
        )
        self.__api_secret = None

        def exchange_token(raw_token: str) -> _KiteCandidateContext:
            return api_secret.reveal_for_call(
                lambda raw_secret: self.__exchange_values(
                    raw_token,
                    raw_secret,
                    timeout_seconds=timeout_seconds,
                )
            )

        try:
            candidate = request_token.consume_for_call(exchange_token)
        except ProviderConnectivityError:
            raise
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            if not isinstance(candidate, _KiteCandidateContext):
                raise ProviderConnectivityError(
                    ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
                )
            return candidate
        raise ProviderConnectivityError(code)

    def exchange(self, request_token: str) -> _KiteCandidateContext:
        """Compatibility bridge retained until the Stage 4 caller migration."""

        api_secret = self.__api_secret
        self.__api_secret = None
        if api_secret is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            candidate = self.__exchange_values(request_token, api_secret)
        finally:
            del api_secret
        self.__legacy_candidate = candidate
        return candidate

    def context_evidence(self) -> KiteContextEvidence:
        """Compatibility bridge to separately invoked availability verification."""

        candidate = self.__legacy_candidate
        if candidate is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        return candidate.verify_provider_availability()

    def terminate(self) -> None:
        """Compatibility bridge that performs local disposal only."""

        candidate = self.__legacy_candidate
        self.__legacy_candidate = None
        if candidate is not None:
            candidate.dispose_local()

    def __exchange_values(
        self,
        request_token: str,
        api_secret: str,
        *,
        timeout_seconds: float | None = None,
    ) -> _KiteCandidateContext:
        client = self.__client
        if client is None:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            )
        try:
            handle = client.exchange_once(
                request_token,
                api_secret,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            code = _map_authentication_error_code(error)
        else:
            self.__client = None
            return _KiteCandidateContext(
                handle,
                operation_recorder=self.__record,
                remaining_budget=self.__budget,
            )
        raise ProviderConnectivityError(code)

    def __before(
        self,
        operation: GovernedAuthenticationOperation,
    ) -> float | None:
        if self.__budget is None and self.__record is None:
            return None
        try:
            if self.__budget is None or self.__record is None:
                raise TypeError
            budget = self.__budget()
            if type(budget) is not RemainingBudget:
                raise TypeError
            budget.require_available()
            self.__record(operation)
            return budget.seconds
        except Exception:
            raise ProviderConnectivityError(
                ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
            ) from None

    def __repr__(self) -> str:
        return "<KiteAuthenticationAdapter redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_AUTHENTICATION_ADAPTER_SERIALIZATION_PROHIBITED")


def create_kite_authentication_adapter(
    api_key: str,
    api_secret: str | None = None,
    *,
    operation_recorder: Callable[[GovernedAuthenticationOperation], None] | None = None,
    remaining_budget: Callable[[], RemainingBudget] | None = None,
) -> KiteAuthenticationAdapter:
    try:
        client = _create_kite_authentication_client(api_key)
    except Exception as error:
        code = _map_authentication_error_code(error)
    else:
        return KiteAuthenticationAdapter(
            api_secret,
            client,
            operation_recorder=operation_recorder,
            remaining_budget=remaining_budget,
        )
    raise ProviderConnectivityError(code)


def _canonical_principal(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and _CANONICAL_PRINCIPAL.fullmatch(value) is not None
    )


def _operationally_unavailable(code: ProviderErrorCode) -> bool:
    return code in {
        ProviderErrorCode.NETWORK_TIMEOUT,
        ProviderErrorCode.CONNECTION_FAILURE,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
    }


def _map_authentication_error_code(error: Exception) -> ProviderErrorCode:
    if isinstance(error, (_KiteSessionInvalidated, _TokenException)):
        return ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
    if isinstance(error, _PermissionException):
        return ProviderErrorCode.AUTHENTICATION_REJECTED
    if isinstance(error, (_RequestsTimeout, TimeoutError)):
        return ProviderErrorCode.NETWORK_TIMEOUT
    if isinstance(error, (_RequestsConnectionError, ConnectionError, OSError)):
        return ProviderErrorCode.CONNECTION_FAILURE
    if isinstance(
        error,
        (
            _UnexpectedAuthenticationResponse,
            _UnexpectedProfileResponse,
            _DataException,
        ),
    ):
        return ProviderErrorCode.UNEXPECTED_RESPONSE
    if isinstance(error, (_NetworkException, _KiteException)):
        status_code = getattr(error, "code", None)
        return (
            ProviderErrorCode.RATE_LIMITED
            if status_code == 429
            else ProviderErrorCode.PROVIDER_SERVICE_FAILURE
        )
    if isinstance(
        error,
        (_KiteCleanupError, _KiteClientClosedError, _KiteExchangeAlreadyAttempted),
    ):
        return ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    if isinstance(error, ProviderConnectivityError):
        return error.code
    return ProviderErrorCode.INTERNAL_ADAPTER_DEFECT


__all__ = [
    "KiteAuthenticationAdapter",
    "KiteContextEvidence",
    "create_kite_authentication_adapter",
]
