"""CAR-014 pilot-local MCX Instrument Master and candle verification engine.

Possession of this module grants no live authority. The default SDK factory is
reachable only after a CAR-014 Version 1.1 activation context passes every
local gate and the process-lifetime one-attempt latch is consumed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


LIVE_EXECUTION_NOT_AUTHORIZED = (
    "LIVE_EXECUTION_NOT_AUTHORIZED_CAR_014_VERSION_1_1_REQUIRED"
)
_SECOND_EXECUTION_NOT_AUTHORIZED = "SECOND_EXECUTION_NOT_AUTHORIZED"
_CREDENTIAL_INPUT_INVALID = "CREDENTIAL_INPUT_INVALID"
_EXPECTED_CAR_ID = "CAR-014"
_EXPECTED_CAR_VERSION = "1.1"
_EXPECTED_INTERVAL = "5minute"
_STANDARD_GOLD_SYMBOL = re.compile(r"GOLD\d{2}[A-Z]{3}FUT")
_EXCLUDED_GOLD_VARIANTS = frozenset({"GOLDM", "GOLDGUINEA", "GOLDPETAL"})
_DEFINITIVE_GOLD_OPTION_TYPES = frozenset({"CE", "PE"})
_REQUIRED_INSTRUMENT_FIELDS = (
    "exchange",
    "name_or_underlying",
    "tradingsymbol",
    "instrument_type",
    "expiry",
    "instrument_token",
)
_CANDLE_FIELDS = ("date", "open", "high", "low", "close", "volume")
_execution_started = False
_authority_consumed = False


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    historical_start: str
    historical_end: str
    timezone: str
    interval: str = _EXPECTED_INTERVAL
    continuous: bool = False
    oi: bool = False


@dataclass(frozen=True, slots=True)
class LiveActivationContext:
    car_id: str
    car_version: str
    implementation_sha: str
    environment_id: str
    authority_expiry: str
    execution_date: str
    historical_start: str
    historical_end: str
    timezone: str
    interval: str = _EXPECTED_INTERVAL
    continuous: bool = False
    oi: bool = False

    def execution_plan(self) -> ExecutionPlan:
        return ExecutionPlan(
            historical_start=self.historical_start,
            historical_end=self.historical_end,
            timezone=self.timezone,
            interval=self.interval,
            continuous=self.continuous,
            oi=self.oi,
        )


@dataclass(frozen=True, slots=True)
class Stage1Evidence:
    initiated: bool = False
    completed: bool = False
    outcome_category: str = "NOT_INITIATED"
    total_record_count: int = 0
    qualifying_record_count: int = 0
    off_scope_structural_issue_count: int = 0
    definitive_option_record_count: int = 0
    excluded_variant_record_count: int = 0
    target_record_count: int = 0
    target_blocking_issue_count: int = 0
    required_field_presence_matrix: tuple[tuple[str, bool], ...] = ()
    expected_futures_value: str = "FUT"
    fut_observed: bool = False
    expiry_representation_type: str = "NONE"
    token_representation_type: str = "NONE"
    selected_exchange: str = "NONE"
    selected_trading_symbol: str = "NONE"
    selected_expiry: str = "NONE"
    selected_instrument_type: str = "NONE"
    deterministic_selection_result: str = "NOT_RUN"
    ambiguity_category: str = "NONE"
    payload_discarded: bool = False
    numeric_token_retained_in_evidence: bool = False


@dataclass(frozen=True, slots=True)
class Stage2Evidence:
    initiated: bool = False
    completed: bool = False
    outcome_category: str = "NOT_INITIATED"
    requested_interval: str = _EXPECTED_INTERVAL
    historical_start: str = "NONE"
    historical_end: str = "NONE"
    timezone: str = "NONE"
    continuous: bool = False
    oi: bool = False
    row_count: int = 0
    key_presence_matrix: tuple[tuple[str, bool], ...] = ()
    value_type_matrix: tuple[tuple[str, str], ...] = ()
    first_returned_timestamp: str = "NONE"
    last_returned_timestamp: str = "NONE"
    timezone_or_offset_observation: str = "NONE"
    chronological_order_result: str = "NOT_ASSESSED"
    duplicate_timestamp_count: int = 0
    interval_spacing_result: str = "NOT_ASSESSED"
    null_value_count: int = 0
    missing_value_count: int = 0
    raw_payload_discarded: bool = False


@dataclass(frozen=True, slots=True)
class PilotOutcome:
    outcome_category: str
    stage1: Stage1Evidence
    stage2: Stage2Evidence
    authority_consumed: bool
    local_cleanup: str


class _SelectedContract:
    __slots__ = (
        "exchange",
        "expiry",
        "instrument_type",
        "normalized_trading_symbol",
        "token",
        "trading_symbol",
    )

    def __init__(
        self,
        *,
        exchange: str,
        expiry: date,
        instrument_type: str,
        token: int,
        trading_symbol: str,
    ) -> None:
        self.exchange = exchange
        self.expiry = expiry
        self.instrument_type = instrument_type
        self.normalized_trading_symbol = trading_symbol.upper()
        self.token = token
        self.trading_symbol = trading_symbol

    def __repr__(self) -> str:
        return "_SelectedContract(<transient-provider-reference>)"


class _Stage1Analysis:
    __slots__ = ("evidence", "selected")

    def __init__(
        self,
        evidence: Stage1Evidence,
        selected: _SelectedContract | None,
    ) -> None:
        self.evidence = evidence
        self.selected = selected


class _PilotSdkAdapter:
    """Private narrow adapter for the two future CAR-014 operations."""

    __slots__ = ("__client", "__closed")

    def __init__(self, client: Any) -> None:
        self.__client = client
        self.__closed = False

    def instruments(self) -> object:
        return self.__client.instruments("MCX")

    def historical_data(
        self,
        instrument_token: int,
        plan: ExecutionPlan,
    ) -> object:
        return self.__client.historical_data(
            instrument_token=instrument_token,
            from_date=plan.historical_start,
            to_date=plan.historical_end,
            interval=plan.interval,
            continuous=plan.continuous,
            oi=plan.oi,
        )

    def close(self) -> None:
        if self.__closed:
            return
        self.__closed = True
        client = self.__client
        self.__client = None
        session = getattr(client, "reqsession", None)
        close_session = getattr(session, "close", None)
        if not callable(close_session):
            raise RuntimeError
        close_session()


_AdapterFactory = Callable[[str, str], _PilotSdkAdapter]
_Clock = Callable[[], datetime]


def _default_adapter_factory(api_key: str, access_token: str) -> _PilotSdkAdapter:
    from kiteconnect import KiteConnect

    client = KiteConnect(
        api_key=api_key,
        access_token=access_token,
        debug=False,
    )
    return _PilotSdkAdapter(client)


class Car014PilotEngine:
    """Execute at most one combined CAR-014 operation in this process."""

    __slots__ = ("__adapter_factory", "__clock")

    def __init__(
        self,
        adapter_factory: _AdapterFactory = _default_adapter_factory,
        clock: _Clock | None = None,
    ) -> None:
        self.__adapter_factory = adapter_factory
        self.__clock = clock or (lambda: datetime.now(timezone.utc))

    def activation_authorized(
        self,
        activation: LiveActivationContext | None,
        plan: ExecutionPlan | None,
    ) -> bool:
        return (
            not _execution_started
            and _validate_activation(activation, plan, self.__clock())
        )

    def execute(
        self,
        *,
        activation: LiveActivationContext | None,
        plan: ExecutionPlan | None,
        api_key: str,
        access_token: str,
    ) -> PilotOutcome:
        global _authority_consumed, _execution_started

        if not _validate_activation(activation, plan, self.__clock()):
            return _pre_execution_outcome(LIVE_EXECUTION_NOT_AUTHORIZED)
        if _execution_started:
            return _pre_execution_outcome(
                _SECOND_EXECUTION_NOT_AUTHORIZED,
                authority_consumed=_authority_consumed,
            )
        if not api_key or not access_token:
            return _pre_execution_outcome(_CREDENTIAL_INPUT_INVALID)

        _execution_started = True
        _authority_consumed = True
        stage1 = Stage1Evidence(
            initiated=True,
            outcome_category="STAGE_1_STARTED",
        )
        assert activation is not None
        assert plan is not None
        stage2 = Stage2Evidence(
            requested_interval=plan.interval,
            historical_start=plan.historical_start,
            historical_end=plan.historical_end,
            timezone=plan.timezone,
            continuous=plan.continuous,
            oi=plan.oi,
        )
        overall = "STAGE_1_FAILED"
        cleanup = "NOT_REQUIRED"
        adapter: _PilotSdkAdapter | None = None
        selected: _SelectedContract | None = None

        try:
            try:
                adapter = self.__adapter_factory(api_key, access_token)
            except Exception:
                stage1 = Stage1Evidence(
                    initiated=True,
                    outcome_category="SDK_CONSTRUCTION_FAILURE",
                )
            finally:
                del api_key, access_token

            if adapter is not None:
                try:
                    raw_instruments = adapter.instruments()
                except Exception:
                    stage1 = Stage1Evidence(
                        initiated=True,
                        outcome_category="STAGE_1_PROVIDER_FAILURE",
                    )
                else:
                    try:
                        analysis = _analyze_instruments(
                            raw_instruments,
                            execution_date=_parse_date(activation.execution_date),
                        )
                    except Exception:
                        stage1 = Stage1Evidence(
                            initiated=True,
                            outcome_category="LOCAL_STAGE_1_ANALYSIS_FAILURE",
                            payload_discarded=True,
                        )
                    else:
                        stage1 = analysis.evidence
                        selected = analysis.selected
                    finally:
                        del raw_instruments

            if adapter is not None and selected is not None:
                stage2 = Stage2Evidence(
                    initiated=True,
                    outcome_category="STAGE_2_STARTED",
                    requested_interval=plan.interval,
                    historical_start=plan.historical_start,
                    historical_end=plan.historical_end,
                    timezone=plan.timezone,
                    continuous=plan.continuous,
                    oi=plan.oi,
                )
                transient_token = selected.token
                try:
                    raw_candles = adapter.historical_data(transient_token, plan)
                except Exception:
                    stage2 = Stage2Evidence(
                        initiated=True,
                        outcome_category="STAGE_2_PROVIDER_FAILURE",
                        requested_interval=plan.interval,
                        historical_start=plan.historical_start,
                        historical_end=plan.historical_end,
                        timezone=plan.timezone,
                        continuous=plan.continuous,
                        oi=plan.oi,
                    )
                    overall = "STAGE_2_FAILED"
                else:
                    try:
                        stage2 = _analyze_candles(raw_candles, plan)
                    except Exception:
                        stage2 = Stage2Evidence(
                            initiated=True,
                            outcome_category="LOCAL_STAGE_2_ANALYSIS_FAILURE",
                            requested_interval=plan.interval,
                            historical_start=plan.historical_start,
                            historical_end=plan.historical_end,
                            timezone=plan.timezone,
                            continuous=plan.continuous,
                            oi=plan.oi,
                            raw_payload_discarded=True,
                        )
                    finally:
                        del raw_candles
                    overall = (
                        "COMPLETED"
                        if stage2.completed
                        else "STAGE_2_FAILED"
                    )
                finally:
                    del transient_token
            elif stage1.completed:
                overall = "STAGE_1_SELECTION_BLOCKED"
        finally:
            if selected is not None:
                selected.token = 0
                selected = None
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    cleanup = "SANITIZED_FAILURE"
                else:
                    cleanup = "SUCCESS"
                adapter = None

        return PilotOutcome(
            outcome_category=overall,
            stage1=stage1,
            stage2=stage2,
            authority_consumed=True,
            local_cleanup=cleanup,
        )


def _pre_execution_outcome(
    category: str,
    *,
    authority_consumed: bool = False,
) -> PilotOutcome:
    return PilotOutcome(
        outcome_category=category,
        stage1=Stage1Evidence(),
        stage2=Stage2Evidence(),
        authority_consumed=authority_consumed,
        local_cleanup="NOT_REQUIRED",
    )


def _validate_activation(
    activation: LiveActivationContext | None,
    plan: ExecutionPlan | None,
    now: datetime,
) -> bool:
    if activation is None or plan is None:
        return False
    if activation.car_id != _EXPECTED_CAR_ID:
        return False
    if activation.car_version != _EXPECTED_CAR_VERSION:
        return False
    if not activation.implementation_sha or not activation.environment_id:
        return False
    if not activation.authority_expiry or not activation.execution_date:
        return False
    if not activation.historical_start or not activation.historical_end:
        return False
    if not activation.timezone:
        return False
    if activation.interval != _EXPECTED_INTERVAL:
        return False
    if activation.continuous is not False or activation.oi is not False:
        return False
    if plan != activation.execution_plan():
        return False
    try:
        expiry = _as_aware_utc(_parse_datetime(activation.authority_expiry))
        execution_date = _parse_date(activation.execution_date)
        start_original = _parse_datetime(activation.historical_start)
        end_original = _parse_datetime(activation.historical_end)
        start = _as_aware_utc(start_original)
        end = _as_aware_utc(end_original)
        comparable_now = _as_aware_utc(now)
        frozen_timezone = ZoneInfo(activation.timezone)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return False
    if expiry <= comparable_now:
        return False
    if start >= end or end - start != timedelta(minutes=60):
        return False
    if end > comparable_now:
        return False
    if execution_date != now.astimezone(frozen_timezone).date():
        return False
    if start_original.utcoffset() != start_original.astimezone(
        frozen_timezone
    ).utcoffset():
        return False
    if end_original.utcoffset() != end_original.astimezone(
        frozen_timezone
    ).utcoffset():
        return False
    return True


def _analyze_instruments(
    payload: object,
    *,
    execution_date: date,
) -> _Stage1Analysis:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return _Stage1Analysis(
            Stage1Evidence(
                initiated=True,
                outcome_category="INSTRUMENT_RESPONSE_SHAPE_INVALID",
                payload_discarded=True,
            ),
            None,
        )

    total = len(payload)
    presence = {field: True for field in _REQUIRED_INSTRUMENT_FIELDS}
    candidates: list[_SelectedContract] = []
    fut_observed = False
    expiry_types: set[str] = set()
    token_types: set[str] = set()
    off_scope_structural_issue_count = 0
    definitive_option_record_count = 0
    excluded_variant_record_count = 0
    target_record_count = 0
    target_failures: list[str] = []
    ambiguity = "NONE"

    for item in payload:
        if not isinstance(item, Mapping):
            off_scope_structural_issue_count += 1
            continue

        exchange = _normalized_string(item.get("exchange"))
        segment = _normalized_string(item.get("segment"))
        name = _normalized_string(item.get("name"))
        underlying = _normalized_string(item.get("underlying"))
        public_symbol = _stripped_string(item.get("tradingsymbol"))
        symbol = public_symbol.upper()
        instrument_type = _normalized_string(item.get("instrument_type"))
        expiry_value = item.get("expiry")
        token_value = item.get("instrument_token")
        effective_name = name or underlying

        product_hints = {value for value in (name, underlying) if value}
        has_exact_gold_hint = "GOLD" in product_hints
        has_variant_hint = bool(product_hints & _EXCLUDED_GOLD_VARIANTS)
        symbol_has_standard_gold_hint = bool(
            symbol and _STANDARD_GOLD_SYMBOL.fullmatch(symbol)
        )

        if exchange and exchange != "MCX":
            continue
        if not exchange and not (
            has_exact_gold_hint or symbol_has_standard_gold_hint
        ):
            off_scope_structural_issue_count += 1
            continue
        if has_exact_gold_hint and len(product_hints) > 1:
            target_record_count += 1
            target_failures.append("CONFLICTING_NAME_AND_UNDERLYING")
            fields = {
                "exchange": bool(exchange),
                "name_or_underlying": bool(effective_name),
                "tradingsymbol": bool(symbol),
                "instrument_type": bool(instrument_type),
                "expiry": expiry_value is not None,
                "instrument_token": token_value is not None,
            }
            _merge_target_presence(presence, fields)
            if instrument_type == "FUT":
                fut_observed = True
            continue
        if not has_exact_gold_hint:
            if has_variant_hint or effective_name in _EXCLUDED_GOLD_VARIANTS:
                excluded_variant_record_count += 1
            elif symbol_has_standard_gold_hint:
                target_record_count += 1
                target_failures.append("REQUIRED_FIELDS_MISSING")
                fields = {
                    "exchange": bool(exchange),
                    "name_or_underlying": bool(effective_name),
                    "tradingsymbol": bool(symbol),
                    "instrument_type": bool(instrument_type),
                    "expiry": expiry_value is not None,
                    "instrument_token": token_value is not None,
                }
                _merge_target_presence(presence, fields)
                if instrument_type == "FUT":
                    fut_observed = True
            continue

        if instrument_type in _DEFINITIVE_GOLD_OPTION_TYPES:
            definitive_option_record_count += 1
            continue

        target_record_count += 1
        fields = {
            "exchange": bool(exchange),
            "name_or_underlying": bool(effective_name),
            "tradingsymbol": bool(symbol),
            "instrument_type": bool(instrument_type),
            "expiry": expiry_value is not None,
            "instrument_token": token_value is not None,
        }
        _merge_target_presence(presence, fields)

        if instrument_type == "FUT":
            fut_observed = True
        if not instrument_type:
            target_failures.append(
                "MISSING_INSTRUMENT_TYPE"
                if item.get("instrument_type") is None
                else "MALFORMED_INSTRUMENT_TYPE"
            )
            continue
        if instrument_type != "FUT":
            target_failures.append("NON_FUT_INSTRUMENT_TYPE")
            continue
        if not exchange:
            target_failures.append("REQUIRED_FIELDS_MISSING")
            continue
        if segment not in {"MCX", "MCX-FUT"}:
            target_failures.append("CONFLICTING_SEGMENT")
            continue
        if not symbol or not _STANDARD_GOLD_SYMBOL.fullmatch(symbol):
            target_failures.append("STANDARD_VARIANT_DISTINCTION_UNRESOLVED")
            continue
        if expiry_value is None or token_value is None:
            target_failures.append("REQUIRED_FIELDS_MISSING")
            continue

        expiry_types.add(type(expiry_value).__name__)
        token_types.add(type(token_value).__name__)
        try:
            expiry = _parse_date(expiry_value)
        except (TypeError, ValueError):
            target_failures.append("EXPIRY_PARSE_FAILED")
            continue
        try:
            token = _parse_token(token_value)
        except (TypeError, ValueError):
            target_failures.append("TOKEN_REPRESENTATION_INVALID")
            continue
        if expiry <= execution_date:
            continue
        candidates.append(
            _SelectedContract(
                exchange=exchange,
                expiry=expiry,
                instrument_type=instrument_type,
                token=token,
                trading_symbol=public_symbol,
            )
        )

    if target_record_count == 0:
        presence = {field: False for field in _REQUIRED_INSTRUMENT_FIELDS}

    if target_failures:
        failure_category, failure_ambiguity = _resolve_target_failure(
            target_failures
        )
        return _Stage1Analysis(
            _stage1_evidence(
                category=failure_category,
                total=total,
                candidates=candidates,
                presence=presence,
                fut_observed=fut_observed,
                expiry_types=expiry_types,
                token_types=token_types,
                ambiguity=failure_ambiguity,
                off_scope_structural_issue_count=(
                    off_scope_structural_issue_count
                ),
                definitive_option_record_count=definitive_option_record_count,
                excluded_variant_record_count=excluded_variant_record_count,
                target_record_count=target_record_count,
                target_blocking_issue_count=len(target_failures),
            ),
            None,
        )

    by_symbol: dict[str, set[tuple[str, str, str]]] = {}
    by_public_facts: dict[tuple[str, str, str, str], set[int]] = {}
    occurrence_count: dict[tuple[str, str, str, str, int], int] = {}
    for candidate in candidates:
        public = (
            candidate.exchange,
            candidate.normalized_trading_symbol,
            candidate.expiry.isoformat(),
            candidate.instrument_type,
        )
        by_symbol.setdefault(candidate.normalized_trading_symbol, set()).add(
            public[1:]
        )
        by_public_facts.setdefault(public, set()).add(candidate.token)
        complete = (*public, candidate.token)
        occurrence_count[complete] = occurrence_count.get(complete, 0) + 1

    if any(len(facts) > 1 for facts in by_symbol.values()):
        ambiguity = "CONFLICTING_DUPLICATE_PUBLIC_FACTS"
    elif any(len(tokens) > 1 for tokens in by_public_facts.values()):
        ambiguity = "SEMANTICALLY_IDENTICAL_TOKEN_VARIANTS"
    elif any(count > 1 for count in occurrence_count.values()):
        ambiguity = "DUPLICATE_RECORDS"

    if ambiguity != "NONE":
        return _Stage1Analysis(
            _stage1_evidence(
                category="AMBIGUOUS_GOLD_SELECTION",
                total=total,
                candidates=candidates,
                presence=presence,
                fut_observed=fut_observed,
                expiry_types=expiry_types,
                token_types=token_types,
                ambiguity=ambiguity,
                off_scope_structural_issue_count=(
                    off_scope_structural_issue_count
                ),
                definitive_option_record_count=definitive_option_record_count,
                excluded_variant_record_count=excluded_variant_record_count,
                target_record_count=target_record_count,
                target_blocking_issue_count=0,
            ),
            None,
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.expiry,
            candidate.normalized_trading_symbol,
            candidate.token,
        )
    )
    if not candidates:
        return _Stage1Analysis(
            _stage1_evidence(
                category="NO_QUALIFYING_GOLD_FUTURES",
                total=total,
                candidates=candidates,
                presence=presence,
                fut_observed=fut_observed,
                expiry_types=expiry_types,
                token_types=token_types,
                ambiguity="NONE",
                off_scope_structural_issue_count=(
                    off_scope_structural_issue_count
                ),
                definitive_option_record_count=definitive_option_record_count,
                excluded_variant_record_count=excluded_variant_record_count,
                target_record_count=target_record_count,
                target_blocking_issue_count=0,
            ),
            None,
        )

    selected = candidates[0]
    evidence = _stage1_evidence(
        category="STANDARD_GOLD_FUTURE_SELECTED",
        total=total,
        candidates=candidates,
        presence=presence,
        fut_observed=fut_observed,
        expiry_types=expiry_types,
        token_types=token_types,
        ambiguity="NONE",
        off_scope_structural_issue_count=off_scope_structural_issue_count,
        definitive_option_record_count=definitive_option_record_count,
        excluded_variant_record_count=excluded_variant_record_count,
        target_record_count=target_record_count,
        target_blocking_issue_count=0,
        selected=selected,
    )
    return _Stage1Analysis(evidence, selected)


def _stage1_evidence(
    *,
    category: str,
    total: int,
    candidates: Sequence[_SelectedContract],
    presence: Mapping[str, bool],
    fut_observed: bool,
    expiry_types: set[str],
    token_types: set[str],
    ambiguity: str,
    off_scope_structural_issue_count: int,
    definitive_option_record_count: int,
    excluded_variant_record_count: int,
    target_record_count: int,
    target_blocking_issue_count: int,
    selected: _SelectedContract | None = None,
) -> Stage1Evidence:
    return Stage1Evidence(
        initiated=True,
        completed=True,
        outcome_category=category,
        total_record_count=total,
        qualifying_record_count=len(candidates),
        off_scope_structural_issue_count=off_scope_structural_issue_count,
        definitive_option_record_count=definitive_option_record_count,
        excluded_variant_record_count=excluded_variant_record_count,
        target_record_count=target_record_count,
        target_blocking_issue_count=target_blocking_issue_count,
        required_field_presence_matrix=tuple(
            (field, presence[field]) for field in _REQUIRED_INSTRUMENT_FIELDS
        ),
        fut_observed=fut_observed,
        expiry_representation_type=_type_summary(expiry_types),
        token_representation_type=_type_summary(token_types),
        selected_exchange=selected.exchange if selected else "NONE",
        selected_trading_symbol=(
            selected.trading_symbol if selected else "NONE"
        ),
        selected_expiry=(
            selected.expiry.isoformat() if selected else "NONE"
        ),
        selected_instrument_type=(
            selected.instrument_type if selected else "NONE"
        ),
        deterministic_selection_result=(
            "SELECTED" if selected else "BLOCKED"
        ),
        ambiguity_category=ambiguity,
        payload_discarded=True,
        numeric_token_retained_in_evidence=False,
    )


_TARGET_FAILURE_PRECEDENCE = (
    (
        "CONFLICTING_NAME_AND_UNDERLYING",
        "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
        "CONFLICTING_NAME_AND_UNDERLYING",
    ),
    (
        "CONFLICTING_SEGMENT",
        "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
        "CONFLICTING_SEGMENT",
    ),
    (
        "STANDARD_VARIANT_DISTINCTION_UNRESOLVED",
        "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
        "STANDARD_VARIANT_DISTINCTION_UNRESOLVED",
    ),
    (
        "MALFORMED_INSTRUMENT_TYPE",
        "FUTURES_CLASSIFICATION_UNRESOLVED",
        "MALFORMED_INSTRUMENT_TYPE",
    ),
    (
        "NON_FUT_INSTRUMENT_TYPE",
        "FUTURES_CLASSIFICATION_UNRESOLVED",
        "NON_FUT_INSTRUMENT_TYPE",
    ),
    (
        "MISSING_INSTRUMENT_TYPE",
        "REQUIRED_FIELDS_MISSING",
        "MISSING_INSTRUMENT_TYPE",
    ),
    (
        "REQUIRED_FIELDS_MISSING",
        "REQUIRED_FIELDS_MISSING",
        "MISSING_TARGET_FIELDS",
    ),
    (
        "EXPIRY_PARSE_FAILED",
        "EXPIRY_PARSE_FAILED",
        "EXPIRY_PARSE_FAILED",
    ),
    (
        "TOKEN_REPRESENTATION_INVALID",
        "TOKEN_REPRESENTATION_INVALID",
        "TOKEN_REPRESENTATION_INVALID",
    ),
)


def _merge_target_presence(
    aggregate: dict[str, bool],
    fields: Mapping[str, bool],
) -> None:
    for field in _REQUIRED_INSTRUMENT_FIELDS:
        aggregate[field] = aggregate[field] and fields[field]


def _resolve_target_failure(failures: Sequence[str]) -> tuple[str, str]:
    observed = frozenset(failures)
    for failure, category, ambiguity in _TARGET_FAILURE_PRECEDENCE:
        if failure in observed:
            return category, ambiguity
    raise RuntimeError


def _analyze_candles(payload: object, plan: ExecutionPlan) -> Stage2Evidence:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return Stage2Evidence(
            initiated=True,
            outcome_category="HISTORICAL_RESPONSE_SHAPE_INVALID",
            requested_interval=plan.interval,
            historical_start=plan.historical_start,
            historical_end=plan.historical_end,
            timezone=plan.timezone,
            continuous=plan.continuous,
            oi=plan.oi,
            raw_payload_discarded=True,
        )

    row_count = len(payload)
    key_presence = {field: True for field in _CANDLE_FIELDS}
    value_types = {field: set() for field in _CANDLE_FIELDS}
    timestamps: list[datetime] = []
    timestamp_text: list[str] = []
    null_count = 0
    missing_count = 0

    for row in payload:
        if not isinstance(row, Mapping):
            for field in _CANDLE_FIELDS:
                key_presence[field] = False
                missing_count += 1
            continue
        for field in _CANDLE_FIELDS:
            if field not in row:
                key_presence[field] = False
                missing_count += 1
                continue
            value = row[field]
            if value is None:
                null_count += 1
                value_types[field].add("NoneType")
            else:
                value_types[field].add(type(value).__name__)
            if field == "date" and value is not None:
                try:
                    parsed = _parse_datetime(value)
                except (TypeError, ValueError):
                    value_types[field].add("UNPARSEABLE")
                else:
                    timestamps.append(parsed)
                    timestamp_text.append(parsed.isoformat())
            del value

    duplicate_count = len(timestamps) - len(set(timestamps))
    chronological = (
        "ASCENDING"
        if all(left <= right for left, right in zip(timestamps, timestamps[1:]))
        else "OUT_OF_ORDER"
    )
    if len(timestamps) < 2:
        spacing = "NOT_ASSESSABLE"
    elif chronological == "ASCENDING" and all(
        right - left == timedelta(minutes=5)
        for left, right in zip(timestamps, timestamps[1:])
    ):
        spacing = "EXACT_5_MINUTE"
    else:
        spacing = "IRREGULAR"

    awareness = {timestamp.utcoffset() is not None for timestamp in timestamps}
    if awareness == {True}:
        timezone_observation = "UTC_OFFSET_PRESENT"
    elif awareness == {False}:
        timezone_observation = "NAIVE"
    elif awareness:
        timezone_observation = "MIXED"
    else:
        timezone_observation = "NONE"

    complete_shape = (
        all(key_presence.values())
        and null_count == 0
        and missing_count == 0
        and len(timestamps) == row_count
    )
    category = (
        "HISTORICAL_EMPTY"
        if row_count == 0
        else (
            "HISTORICAL_STRUCTURE_VERIFIED"
            if complete_shape
            and chronological == "ASCENDING"
            and duplicate_count == 0
            and spacing in {"EXACT_5_MINUTE", "NOT_ASSESSABLE"}
            else "HISTORICAL_STRUCTURE_ISSUES_OBSERVED"
        )
    )
    return Stage2Evidence(
        initiated=True,
        completed=True,
        outcome_category=category,
        requested_interval=plan.interval,
        historical_start=plan.historical_start,
        historical_end=plan.historical_end,
        timezone=plan.timezone,
        continuous=plan.continuous,
        oi=plan.oi,
        row_count=row_count,
        key_presence_matrix=tuple(
            (field, key_presence[field]) for field in _CANDLE_FIELDS
        ),
        value_type_matrix=tuple(
            (field, _type_summary(value_types[field]))
            for field in _CANDLE_FIELDS
        ),
        first_returned_timestamp=(timestamp_text[0] if timestamp_text else "NONE"),
        last_returned_timestamp=(timestamp_text[-1] if timestamp_text else "NONE"),
        timezone_or_offset_observation=timezone_observation,
        chronological_order_result=chronological,
        duplicate_timestamp_count=duplicate_count,
        interval_spacing_result=spacing,
        null_value_count=null_count,
        missing_value_count=missing_count,
        raw_payload_discarded=True,
    )


def _normalized_string(value: object) -> str:
    return value.strip().upper() if isinstance(value, str) else ""


def _stripped_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_token(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise TypeError


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed
    raise TypeError


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError
    return value.astimezone(timezone.utc)


def _type_summary(types: set[str]) -> str:
    if not types:
        return "NONE"
    if len(types) == 1:
        return next(iter(types))
    return "MIXED"
