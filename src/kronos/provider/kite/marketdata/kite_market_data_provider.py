"""Kite read-only market-data provider."""

from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    LiveSnapshotError,
    LiveSnapshotFailure,
    LtpSnapshot,
    MarketDataProvider,
    OhlcSnapshot,
    QuoteSnapshot,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    ReadOnlyProviderOperation,
)


class KiteMarketDataProvider(MarketDataProvider):
    """Expose validated read-only market data through the bounded capability."""

    __slots__ = ("__capability",)

    def __init__(
        self,
        capability: AuthenticatedReadOnlyProviderCapability,
    ) -> None:
        if (
            ReadOnlyProviderOperation.HISTORICAL_DATA not in capability.operations
            or not callable(getattr(capability, "historical_candles", None))
        ):
            raise HistoricalDataError(HistoricalDataFailure.CAPABILITY_UNAVAILABLE)
        self.__capability = capability

    def historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        if not self.__capability.active:
            raise HistoricalDataError(HistoricalDataFailure.CAPABILITY_UNAVAILABLE)
        return self.__capability.historical_candles(request)

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        return self.__live_operation("quote", instrument, QuoteSnapshot)

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        return self.__live_operation("ltp", instrument, LtpSnapshot)

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        return self.__live_operation("ohlc", instrument, OhlcSnapshot)

    def __live_operation(
        self,
        operation: str,
        instrument: InstrumentRecord,
        expected_type: type[QuoteSnapshot] | type[LtpSnapshot] | type[OhlcSnapshot],
    ) -> QuoteSnapshot | LtpSnapshot | OhlcSnapshot:
        if not self.__capability.active:
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE)
        endpoint = getattr(self.__capability, operation, None)
        if not callable(endpoint):
            raise LiveSnapshotError(LiveSnapshotFailure.CAPABILITY_UNAVAILABLE)
        result = endpoint(instrument)
        if type(result) is not expected_type:
            raise LiveSnapshotError(LiveSnapshotFailure.MALFORMED_PROVIDER_DATA)
        return result

    def __repr__(self) -> str:
        return "<KiteMarketDataProvider read-only>"
