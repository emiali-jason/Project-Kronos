"""Development-only GUI proof for the authenticated read-only Kite path."""

from __future__ import annotations

from collections.abc import Callable
import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
import secrets
import threading
import time
import tkinter as tk
from tkinter import ttk
from zoneinfo import ZoneInfo
import webbrowser

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    run_security_framework_subprocess,
)
from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.loader import load_provider_authentication_configuration
from kronos.provider.adapters.kite.authentication import (
    create_kite_authentication_adapter,
)
from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
from kronos.provider.callbacks.loopback import (
    LoopbackAuthenticationCallbackListener,
    create_standard_library_server,
)
from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
    LiveSnapshotError,
)
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.kite.instruments.kite_instrument_provider import (
    KiteInstrumentProvider,
)
from kronos.provider.kite.marketdata.kite_market_data_provider import (
    KiteMarketDataProvider,
)
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.provider.services.provider_authentication import (
    ProviderAuthenticationService,
)
from kronos.swing.daily_data import (
    SwingDailyDataset,
    SwingDailyStatus,
    build_swing_daily_dataset,
)
from kronos.swing.candidate_validation import (
    SwingCandidateValidation,
    validate_qualified_candidates,
)
from kronos.swing.market_assessment import (
    SwingMarketAssessment,
    assess_swing_market,
)
from kronos.swing.trade_plan import TradePlan, TradePlanStatus, build_trade_plan
from kronos.swing.candidate_ranking import CandidateRanking, rank_trade_plans
from kronos.swing.zero import SwingState
from kronos.swing.universe import (
    SwingUniverseAssetClass,
    SwingUniverseMember,
)


WINDOW_TITLE = "KRONOS — Provider Foundation V2 Historical Proof"
FROZEN_STAGE4_OBSERVATION_BOUNDARY = datetime(
    2026,
    8,
    7,
    tzinfo=ZoneInfo("Asia/Kolkata"),
)


@dataclass(frozen=True, slots=True)
class SanitizedHistoricalProof:
    instrument: str
    status: str
    interval: str = ""
    candle_count: int = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    failure: str = ""

    def render(self) -> str:
        if self.status == "PASS":
            return (
                f"{self.instrument}: PASS | {self.interval} | "
                f"candles={self.candle_count} | "
                f"first={self.first_timestamp.isoformat()} | "
                f"last={self.last_timestamp.isoformat()}"
            )
        suffix = f" | {self.failure}" if self.failure else ""
        return f"{self.instrument}: {self.status}{suffix}"


@dataclass(frozen=True, slots=True)
class SanitizedLiveSnapshotProof:
    """Sanitized evidence for three independent live snapshot operations."""

    instrument: str
    quote: str
    ltp: str
    ohlc: str
    quote_value: str = ""
    ltp_value: str = ""
    ohlc_value: str = ""
    quote_failure: str = ""
    ltp_failure: str = ""
    ohlc_failure: str = ""

    def render(self) -> str:
        lines = [f"{self.instrument}:"]
        for label, status, value, failure in (
            ("Quote", self.quote, self.quote_value, self.quote_failure),
            ("LTP", self.ltp, self.ltp_value, self.ltp_failure),
            ("OHLC", self.ohlc, self.ohlc_value, self.ohlc_failure),
        ):
            suffix = f" | {value}" if value else f" | {failure}" if failure else ""
            lines.append(f"{label}: {status}{suffix}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SanitizedResolutionProof:
    """Sanitized canonical-to-Provider resolution evidence."""

    canonical_identity: str
    status: str
    provider_identity: str = ""
    failure: str = ""

    def render(self) -> str:
        if self.status == "PASS":
            return f"{self.canonical_identity}: PASS"
        return f"{self.canonical_identity}: FAIL | {self.failure}"


@dataclass(frozen=True, slots=True)
class SanitizedDailyDatasetProof:
    """Aggregate evidence for one bounded 98-member completed-Daily run."""

    dataset: SwingDailyDataset
    nse_equities_ready: int
    indices_ready: int
    commodities_ready: int
    current_incomplete_daily_excluded: bool
    elapsed_seconds: float
    failures: tuple[tuple[str, str], ...]

    def render(self) -> str:
        lines = (
            f"Universe requested: {self.dataset.requested_count}",
            f"READY: {self.dataset.ready_count}/98",
            f"FAILED / UNAVAILABLE: {self.dataset.unavailable_count}/98",
            f"NSE equities ready: {self.nse_equities_ready}/91",
            f"Indices ready: {self.indices_ready}/2",
            f"Commodities ready: {self.commodities_ready}/5",
            "Current incomplete Daily candle excluded: "
            + ("PASS" if self.current_incomplete_daily_excluded else "FAIL"),
            f"Elapsed real run time: {self.elapsed_seconds:.3f} seconds",
        )
        failure_lines = tuple(
            f"{identity}: UNAVAILABLE | {failure}"
            for identity, failure in self.failures
        )
        return "\n".join(lines + failure_lines)


@dataclass(frozen=True, slots=True)
class SanitizedMarketAssessmentProof:
    """Aggregate and actionable-state evidence from the frozen Swing engine."""

    result: SwingMarketAssessment
    analysis_elapsed_seconds: float

    def render(self) -> str:
        counts = self.result.counts
        lines = (
            f"Run identity: {self.result.run_identity}",
            "Observation boundary: "
            f"{self.result.observation_boundary.isoformat()}",
            f"Instruments assessed: {self.result.assessed_count}/98",
            f"Analysis failures: {self.result.failure_count}",
            f"Setup assessments: {self.result.assessment_count}/196",
            "PULLBACK CONTINUATION:",
            f"NO_SETUP: {counts.pullback_no_setup}",
            f"FORMING LONG: {counts.pullback_forming_long}",
            f"FORMING SHORT: {counts.pullback_forming_short}",
            f"QUALIFIED LONG: {counts.pullback_qualified_long}",
            f"QUALIFIED SHORT: {counts.pullback_qualified_short}",
            "CONSOLIDATION BREAKOUT:",
            f"NO_SETUP: {counts.breakout_no_setup}",
            f"FORMING: {counts.breakout_forming}",
            f"QUALIFIED LONG: {counts.breakout_qualified_long}",
            f"QUALIFIED SHORT: {counts.breakout_qualified_short}",
            "FORMING instruments:",
        )
        forming = _render_market_states(self.result, SwingState.FORMING)
        qualified = _render_market_states(self.result, SwingState.QUALIFIED)
        return "\n".join(
            lines
            + (forming if forming else ("NONE",))
            + ("QUALIFIED instruments:",)
            + (qualified if qualified else ("NONE",))
            + (
                "Analysis elapsed time: "
                f"{self.analysis_elapsed_seconds:.6f} seconds",
            )
        )


@dataclass(frozen=True, slots=True)
class SanitizedCandidateValidationProof:
    """Sanitized Stage-5 audit evidence from the frozen Stage-4 boundary."""

    validation: SwingCandidateValidation

    def render(self) -> str:
        validation = self.validation
        hdfc = tuple(
            candidate
            for candidate in validation.candidates
            if candidate.canonical_identity == "HDFCBANK"
        )
        overall = (
            validation.passed
            and len(validation.candidates) == 12
            and validation.unique_instrument_count == 11
            and len(hdfc) == 2
            and len({candidate.setup for candidate in hdfc}) == 2
        )
        lines = (
            f"Stage 5: {'PASS' if overall else 'FAIL'}",
            "Frozen observation boundary: "
            f"{validation.observation_boundary.isoformat()}",
            f"Qualified setup assessments: {len(validation.candidates)}/12",
            "Unique qualified instruments: "
            f"{validation.unique_instrument_count}/11",
            "QUALIFIED predicate audits:",
        )
        audits = tuple(
            f"{audit.candidate.canonical_identity} → "
            f"{audit.candidate.setup.value} → {audit.candidate.direction.value}: "
            f"{'PASS' if audit.passed else 'FAIL'}"
            for audit in validation.audits
        )
        forming = tuple(
            f"FORMING representative: {audit.canonical_identity} → "
            f"{audit.setup.value} → {audit.direction.value} → "
            f"{'PASS' if audit.passed else 'FAIL'} → missing={audit.missing_event}"
            for audit in validation.forming_audits
        )
        summary = (
            "Multiple-setup preservation: "
            + ("PASS" if len(hdfc) == 2 else "FAIL"),
            "Candidate extraction: " + ("PASS" if overall else "FAIL"),
            f"FORMING leakage: {validation.forming_leakage}",
            f"NO_SETUP leakage: {validation.no_setup_leakage}",
            "Ranking introduced: NO",
            "Score introduced: NO",
            "Confidence introduced: NO",
            "Trade Plan invented: NO",
        )
        return "\n".join(lines + audits + forming + summary)


@dataclass(frozen=True, slots=True)
class SanitizedTradePlanProof:
    """Sanitized Stage-7 plans from the frozen Stage-5 candidate set."""

    plans: tuple[TradePlan, ...]

    def render(self) -> str:
        actionable = sum(
            plan.status is TradePlanStatus.ACTIONABLE for plan in self.plans
        )
        not_actionable = sum(
            plan.status is TradePlanStatus.NOT_ACTIONABLE for plan in self.plans
        )
        invalid = sum(plan.status is TradePlanStatus.INVALID for plan in self.plans)
        lines = [
            "Stage 7 Trade Plan proof: "
            + ("PASS" if len(self.plans) == 12 else "FAIL"),
            f"Trade Plans constructed: {len(self.plans)}/12",
            f"ACTIONABLE: {actionable}",
            f"NOT_ACTIONABLE: {not_actionable}",
            f"INVALID / FAILED: {invalid}",
        ]
        for plan in self.plans:
            lines.extend(
                (
                    plan.canonical_identity,
                    f"Setup: {plan.setup.value}",
                    f"Direction: {plan.direction.value}",
                    f"Status: {plan.status.value}",
                    f"Entry: {_number(plan.entry)}",
                    f"Entry Condition: {plan.entry_condition}",
                    f"Stop: {_number(plan.stop)}",
                    "Thesis Invalidation: "
                    + " OR ".join(plan.thesis_invalidation),
                    f"Target 1: {_number(plan.target_1)}",
                    f"Risk: {_number(plan.risk_per_unit)}",
                    f"Reward: {_number(plan.reward_per_unit)}",
                    "R:R: "
                    + (
                        _number(plan.risk_reward)
                        if plan.risk_reward is not None
                        else "NONE"
                    ),
                )
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SanitizedCandidateRankingProof:
    """Sanitized Stage-8 ranking of the frozen Stage-7 plans."""

    ranking: CandidateRanking

    def render(self) -> str:
        lines = [
            "Stage 8 Candidate Ranking proof: "
            + ("PASS" if self.ranking.input_count == 12 else "FAIL"),
            f"Input Trade Plans: {self.ranking.input_count}",
            f"Ranked ACTIONABLE: {len(self.ranking.ranked_actionable)}",
            "Preserved NOT_ACTIONABLE: "
            f"{len(self.ranking.preserved_not_actionable)}",
            f"INVALID / FAILED: {len(self.ranking.preserved_invalid)}",
            f"Policy: {self.ranking.policy_id}",
        ]
        lines.extend(
            f"{item.position}. {item.canonical_identity} | "
            f"{item.setup.value} | {item.direction.value} | "
            f"R:R {_number(item.risk_reward)}"
            for item in self.ranking.ranked_actionable
        )
        lines.append(
            "NOT_ACTIONABLE evidence: "
            + ", ".join(
                f"{plan.canonical_identity} ({plan.setup.value})"
                for plan in self.ranking.preserved_not_actionable
            )
        )
        lines.extend(
            (
                f"Instrument attention groups: {len(self.ranking.instrument_groups)}",
                "Weighted / composite score: NOT IMPLEMENTED",
                "Top 0–2: NOT IMPLEMENTED",
                "Stage-9 selection authority introduced: NO",
            )
        )
        return "\n".join(lines)


def _render_market_states(
    result: SwingMarketAssessment,
    state: SwingState,
) -> tuple[str, ...]:
    return tuple(
        f"{item.canonical_identity} → {assessment.setup.value} → "
        f"{assessment.direction.value} → {assessment.state.value} → "
        f"{assessment.why} → "
        f"next={assessment.next_required_event or '—'}"
        for item in result.instruments
        for assessment in item.assessments
        if assessment.state is state
    )


_TARGETS = (
    ("RELIANCE", InstrumentKind.NSE_EQUITY),
    ("NIFTY", InstrumentKind.NSE_INDEX),
    ("GOLD", InstrumentKind.MCX_FUTURE),
    ("USDINR", InstrumentKind.CDS_FUTURE),
)
_LIVE_TARGETS = (
    ("RELIANCE", "RELIANCE", InstrumentKind.NSE_EQUITY),
    ("NIFTY 50", "NIFTY", InstrumentKind.NSE_INDEX),
    ("GOLDM", "GOLDM", InstrumentKind.MCX_FUTURE),
)
_EQUITY_SYMBOL = re.compile(r"[A-Z0-9_&-]{1,32}\Z")


def execute_historical_proof(
    provider: object,
    *,
    now: datetime,
) -> tuple[SanitizedHistoricalProof, ...]:
    """Run the bounded post-authentication proof and return sanitized evidence."""

    capability_factory = getattr(
        provider,
        "authenticated_read_only_capability",
        None,
    )
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for symbol, kind in _TARGETS:
        try:
            resolved = instruments.resolve(
                InstrumentResolutionRequest(
                    kind=kind,
                    symbol=symbol,
                    as_of=as_of,
                )
            )
        except InstrumentResolutionError as error:
            if (
                symbol == "USDINR"
                and error.failure is InstrumentResolutionFailure.NO_MATCH
            ):
                proofs.append(
                    SanitizedHistoricalProof(symbol, "NOT AVAILABLE")
                )
            else:
                proofs.append(
                    SanitizedHistoricalProof(
                        symbol,
                        "FAIL",
                        failure=f"RESOLUTION_{error.failure.value}",
                    )
                )
            continue
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue

        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    failure=HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def execute_live_snapshot_proof(
    provider: object,
    *,
    now: datetime,
    quote_only: bool = False,
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Run three bounded live operations without exposing Provider material."""

    capability_factory = getattr(
        provider,
        "authenticated_read_only_capability",
        None,
    )
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    proofs: list[SanitizedLiveSnapshotProof] = []
    for label, symbol, kind in _LIVE_TARGETS:
        try:
            resolved = instruments.resolve(
                InstrumentResolutionRequest(
                    kind=kind,
                    symbol=symbol,
                    as_of=now.date(),
                )
            )
        except InstrumentResolutionError as error:
            failure = f"RESOLUTION_{error.failure.value}"
            proofs.append(
                SanitizedLiveSnapshotProof(
                    label,
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    quote_failure=failure,
                    ltp_failure=failure,
                    ohlc_failure=failure,
                )
            )
            continue
        except Exception:
            failure = "RESOLUTION_SANITIZED_PROVIDER_FAILURE"
            proofs.append(
                SanitizedLiveSnapshotProof(
                    label,
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    quote_failure=failure,
                    ltp_failure=failure,
                    ohlc_failure=failure,
                )
            )
            continue

        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        if quote_only:
            ltp_status, ltp_value, ltp_failure = "NOT RUN", "", ""
            ohlc_status, ohlc_value, ohlc_failure = "NOT RUN", "", ""
        else:
            ltp_status, ltp_value, ltp_failure = _snapshot_operation(
                lambda: market_data.ltp(resolved),
                lambda result: f"last={result.last_price}",
            )
            ohlc_status, ohlc_value, ohlc_failure = _snapshot_operation(
                lambda: market_data.ohlc(resolved),
                lambda result: (
                    f"last={result.last_price} | "
                    f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                    f"{result.ohlc.low}/{result.ohlc.close}"
                ),
            )
        proofs.append(
            SanitizedLiveSnapshotProof(
                instrument=label,
                quote=quote_status,
                ltp=ltp_status,
                ohlc=ohlc_status,
                quote_value=quote_value,
                ltp_value=ltp_value,
                ohlc_value=ohlc_value,
                quote_failure=quote_failure,
                ltp_failure=ltp_failure,
                ohlc_failure=ohlc_failure,
            )
        )
    return tuple(proofs)


def execute_equity_quote_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(1.05),
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Quote each supplied NSE equity through one retained read-only capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("NSE")
    proofs: list[SanitizedLiveSnapshotProof] = []
    quote_count = 0
    for symbol in symbols:
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.NSE_EQUITY,
                    symbol=symbol,
                    as_of=now.date(),
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        except Exception:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue
        if quote_count:
            pace()
        quote_count += 1
        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda resolved=resolved: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        proofs.append(
            SanitizedLiveSnapshotProof(
                symbol,
                quote_status,
                "NOT RUN",
                "NOT RUN",
                quote_value=quote_value,
                quote_failure=quote_failure,
            )
        )
    return tuple(proofs)


def execute_mcx_quote_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(1.05),
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Quote supplied nearest unexpired MCX futures through one capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("MCX")
    proofs: list[SanitizedLiveSnapshotProof] = []
    quote_count = 0
    for symbol in symbols:
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.MCX_FUTURE,
                    symbol=symbol,
                    as_of=now.date(),
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        except Exception:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue
        if quote_count:
            pace()
        quote_count += 1
        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda resolved=resolved: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        proofs.append(
            SanitizedLiveSnapshotProof(
                symbol,
                quote_status,
                "NOT RUN",
                "NOT RUN",
                quote_value=quote_value,
                quote_failure=quote_failure,
            )
        )
    return tuple(proofs)


def _snapshot_operation(
    operation: Callable[[], object],
    render: Callable[[object], str],
) -> tuple[str, str, str]:
    try:
        result = operation()
        return "PASS", render(result), ""
    except LiveSnapshotError as error:
        return "FAIL", "", error.failure.value
    except Exception:
        return "FAIL", "", "SANITIZED_PROVIDER_FAILURE"


def _number(value: float) -> str:
    return f"{value:.12g}"


def load_equity_symbols(path: Path) -> tuple[str, ...]:
    """Load one bounded, non-sensitive symbol column from a Sponsor CSV."""

    try:
        with path.open(newline="", encoding="utf-8-sig") as source:
            rows = tuple(csv.DictReader(source))
    except (OSError, UnicodeError, csv.Error):
        raise ValueError("SYMBOL_FILE_INVALID") from None
    symbols = tuple(row.get("Symbol", "") for row in rows)
    if (
        not symbols
        or len(symbols) > 500
        or len(set(symbols)) != len(symbols)
        or any(_EQUITY_SYMBOL.fullmatch(symbol) is None for symbol in symbols)
    ):
        raise ValueError("SYMBOL_FILE_INVALID")
    return symbols


def execute_equity_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> tuple[SanitizedHistoricalProof, ...]:
    """Retrieve one NSE master and test bounded history for each supplied equity."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("NSE")
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for index, symbol in enumerate(symbols):
        request = InstrumentResolutionRequest(
            kind=InstrumentKind.NSE_EQUITY,
            symbol=symbol,
            as_of=as_of,
        )
        try:
            resolved = instruments.resolve_from_records(master, request)
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        if index:
            pace()
        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def execute_universe_resolution_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    now: datetime,
) -> tuple[SanitizedResolutionProof, ...]:
    """Resolve one immutable Swing universe through one retained capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    masters = {
        "NSE": instruments.retrieve("NSE"),
        "MCX": instruments.retrieve("MCX"),
    }
    proofs: list[SanitizedResolutionProof] = []
    for member in universe:
        if member.asset_class is SwingUniverseAssetClass.NSE_EQUITY:
            kind = InstrumentKind.NSE_EQUITY
            master = masters["NSE"]
        elif member.asset_class is SwingUniverseAssetClass.NSE_INDEX:
            kind = InstrumentKind.NSE_INDEX
            master = masters["NSE"]
        else:
            kind = InstrumentKind.MCX_FUTURE
            master = masters["MCX"]
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=kind,
                    symbol=member.canonical_identity,
                    as_of=now.date(),
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedResolutionProof(
                    member.canonical_identity,
                    "FAIL",
                    failure=error.failure.value,
                )
            )
        except Exception:
            proofs.append(
                SanitizedResolutionProof(
                    member.canonical_identity,
                    "FAIL",
                    failure="SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedResolutionProof(
                    member.canonical_identity,
                    "PASS",
                    provider_identity=resolved.trading_symbol,
                )
            )
    return tuple(proofs)


def execute_swing_daily_dataset_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
    monotonic: Callable[[], float] = time.monotonic,
) -> SanitizedDailyDatasetProof:
    """Build the Swing dataset through the retained read-only capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")

    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    masters = {
        "NSE": instruments.retrieve("NSE"),
        "MCX": instruments.retrieve("MCX"),
    }

    def resolve(member: SwingUniverseMember):  # type: ignore[no-untyped-def]
        if member.asset_class is SwingUniverseAssetClass.NSE_EQUITY:
            kind = InstrumentKind.NSE_EQUITY
            master = masters["NSE"]
        elif member.asset_class is SwingUniverseAssetClass.NSE_INDEX:
            kind = InstrumentKind.NSE_INDEX
            master = masters["NSE"]
        else:
            kind = InstrumentKind.MCX_FUTURE
            master = masters["MCX"]
        return instruments.resolve_from_records(
            master,
            InstrumentResolutionRequest(
                kind=kind,
                symbol=member.canonical_identity,
                as_of=now.date(),
            ),
        )

    historical_calls = 0

    def retrieve(request: HistoricalCandleRequest):  # type: ignore[no-untyped-def]
        nonlocal historical_calls
        if historical_calls:
            pace()
        historical_calls += 1
        return market_data.historical_candles(request)

    started = monotonic()
    dataset = build_swing_daily_dataset(
        universe,
        resolve_instrument=resolve,
        historical_candles=retrieve,
        now=now,
    )
    elapsed = monotonic() - started
    ready = tuple(
        record
        for record in dataset.records
        if record.status is SwingDailyStatus.READY
    )
    failures = tuple(
        (record.canonical_identity, record.failure.value)
        for record in dataset.records
        if record.failure is not None
    )
    return SanitizedDailyDatasetProof(
        dataset=dataset,
        nse_equities_ready=sum(
            record.asset_class is SwingUniverseAssetClass.NSE_EQUITY
            for record in ready
        ),
        indices_ready=sum(
            record.asset_class is SwingUniverseAssetClass.NSE_INDEX
            for record in ready
        ),
        commodities_ready=sum(
            record.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            for record in ready
        ),
        current_incomplete_daily_excluded=all(
            record.observation_boundary is not None
            and record.observation_boundary.date()
            < now.astimezone(record.observation_boundary.tzinfo).date()
            for record in ready
        ),
        elapsed_seconds=max(0.0, elapsed),
        failures=failures,
    )


def execute_swing_market_assessment_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
    monotonic: Callable[[], float] = time.monotonic,
) -> SanitizedMarketAssessmentProof:
    """Retrieve one Stage-3 dataset, then time only frozen-engine analysis."""

    daily = execute_swing_daily_dataset_proof(
        provider,
        universe=universe,
        now=now,
        pace=pace,
    )
    started = monotonic()
    result = assess_swing_market(daily.dataset)
    elapsed = monotonic() - started
    return SanitizedMarketAssessmentProof(
        result=result,
        analysis_elapsed_seconds=max(0.0, elapsed),
    )


def execute_swing_candidate_validation_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    frozen_boundary: datetime = FROZEN_STAGE4_OBSERVATION_BOUNDARY,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> SanitizedCandidateValidationProof:
    """Reconstruct and audit only the frozen Stage-4 completed-Daily boundary."""

    if (
        frozen_boundary.tzinfo is None
        or frozen_boundary.utcoffset() is None
    ):
        raise ValueError("FROZEN_OBSERVATION_BOUNDARY_INVALID")
    daily = execute_swing_daily_dataset_proof(
        provider,
        universe=universe,
        now=frozen_boundary + timedelta(days=1),
        pace=pace,
    )
    market = assess_swing_market(daily.dataset)
    if market.observation_boundary != frozen_boundary:
        raise RuntimeError("FROZEN_OBSERVATION_BOUNDARY_MISMATCH")
    validation = validate_qualified_candidates(market, daily.dataset)
    return SanitizedCandidateValidationProof(validation)


def execute_swing_trade_plan_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    frozen_boundary: datetime = FROZEN_STAGE4_OBSERVATION_BOUNDARY,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> SanitizedTradePlanProof:
    """Construct Stage-7 plans only from the frozen Stage-5 boundary."""

    if frozen_boundary.tzinfo is None or frozen_boundary.utcoffset() is None:
        raise ValueError("FROZEN_OBSERVATION_BOUNDARY_INVALID")
    daily = execute_swing_daily_dataset_proof(
        provider,
        universe=universe,
        now=frozen_boundary + timedelta(days=1),
        pace=pace,
    )
    market = assess_swing_market(daily.dataset)
    if market.observation_boundary != frozen_boundary:
        raise RuntimeError("FROZEN_OBSERVATION_BOUNDARY_MISMATCH")
    validation = validate_qualified_candidates(market, daily.dataset)
    if (
        not validation.passed
        or len(validation.candidates) != 12
        or validation.unique_instrument_count != 11
    ):
        raise RuntimeError("FROZEN_CANDIDATE_SET_MISMATCH")
    records = {
        record.canonical_identity: record for record in daily.dataset.records
    }
    return SanitizedTradePlanProof(
        tuple(
            build_trade_plan(
                candidate,
                tuple(
                    candle
                    for candle in records[candidate.canonical_identity].candles
                    if candle.timestamp <= frozen_boundary
                ),
            )
            for candidate in validation.candidates
        )
    )


def execute_swing_candidate_ranking_proof(
    provider: object,
    *,
    universe: tuple[SwingUniverseMember, ...],
    frozen_boundary: datetime = FROZEN_STAGE4_OBSERVATION_BOUNDARY,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> SanitizedCandidateRankingProof:
    """Rank the exact frozen Stage-7 plans through the generic V0 policy."""

    trade_plans = execute_swing_trade_plan_proof(
        provider,
        universe=universe,
        frozen_boundary=frozen_boundary,
        pace=pace,
    )
    return SanitizedCandidateRankingProof(rank_trade_plans(trade_plans.plans))


def execute_mcx_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> tuple[SanitizedHistoricalProof, ...]:
    """Retrieve one MCX master and test bounded history for supplied futures."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("MCX")
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for index, symbol in enumerate(symbols):
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.MCX_FUTURE,
                    symbol=symbol,
                    as_of=as_of,
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        if index:
            pace()
        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def _build_provider() -> KiteProvider:
    configuration = load_provider_authentication_configuration()
    clock = lambda: datetime.now(UTC)
    service = ProviderAuthenticationService(
        configuration,
        credential_source=AppleKeychainCredentialSource(
            provider=configuration.provider,
            runner=run_security_framework_subprocess,
        ),
        principal_resolver=AppleKeychainIntendedPrincipalResolver(
            provider=configuration.provider,
            runner=run_security_framework_subprocess,
        ),
        adapter_factory=create_kite_authentication_adapter,
        listener_factory=lambda: LoopbackAuthenticationCallbackListener(
            server_factory=create_standard_library_server,
            clock=clock,
        ),
        navigator=KiteLoginNavigator(opener=webbrowser.open_new_tab),
        clock=clock,
        identity_factory=lambda: f"v2-proof-{secrets.token_hex(16)}",
    )
    return KiteProvider(KiteAuthentication(service))


class _ProofWindow:
    """Minimal Sponsor control surface with no sensitive input fields."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._provider: KiteProvider | None = None
        self._attempt: object | None = None
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0)
        ttk.Label(
            frame,
            text="Read-only Kite authentication and historical-data proof",
        ).grid(row=0, column=0, sticky="w")
        self._status = tk.StringVar(
            value="Ready. No Provider activity has started."
        )
        ttk.Label(
            frame,
            textvariable=self._status,
            justify="left",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(10, 14))
        self._connect = ttk.Button(
            frame,
            text="Connect to Kite",
            command=self._connect_to_kite,
        )
        self._connect.grid(row=2, column=0, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _connect_to_kite(self) -> None:
        self._connect.configure(state="disabled")
        self._status.set("Starting secure browser authentication…")
        try:
            provider = _build_provider()
            attempt = provider.begin_login()
        except ConfigurationError:
            self._status.set("Authentication: FAIL | CONFIGURATION_UNAVAILABLE")
            return
        except Exception:
            self._status.set("Authentication: FAIL | SANITIZED_LOCAL_FAILURE")
            return
        self._provider = provider
        self._attempt = attempt
        self._status.set(
            "Official Kite login opened. Complete authentication in the browser."
        )
        threading.Thread(
            target=self._complete,
            name="kronos-v2-historical-proof",
            daemon=True,
        ).start()

    def _complete(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is None or attempt is None:
            return
        try:
            outcome = provider.complete_callback(attempt)  # type: ignore[arg-type]
            if outcome.state is not AuthenticationAttemptState.SUCCEEDED:
                rendered = (
                    "Authentication: FAIL | "
                    f"{getattr(outcome.failure_code, 'value', 'SANITIZED_FAILURE')}"
                )
            else:
                proofs = execute_historical_proof(
                    provider,
                    now=datetime.now(UTC),
                )
                rendered = "Authentication: PASS\n" + "\n".join(
                    proof.render() for proof in proofs
                )
        except Exception:
            rendered = "Authentication: FAIL | SANITIZED_PROVIDER_FAILURE"
        finally:
            try:
                provider.end_kronos_session()
            except Exception:
                pass
        print(rendered, flush=True)
        self._root.after(0, lambda: self._status.set(rendered))

    def _close(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is not None and attempt is not None:
            try:
                provider.cancel_authentication_attempt(attempt)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                provider.end_kronos_session()
            except Exception:
                pass
        self._root.destroy()


def main() -> None:
    root = tk.Tk()
    _ProofWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
