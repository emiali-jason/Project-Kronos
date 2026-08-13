"""Execute one explicitly selected, retained Chart Analyst V2 validation call."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    run_security_framework_subprocess,
)
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystV2ActivationService,
    OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    OPENAI_CHART_ANALYST_PROVIDER,
)
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystV2Config,
    OpenAIChartAnalystV2Provider,
    UrllibOpenAIResponsesTransport,
)
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.chart_analyst_v2 import (
    CHART_ANALYST_V2_EVIDENCE_FAMILIES,
    CHART_ANALYST_V2_TIMEFRAMES,
    ChartAnalystProduct,
    ChartAnalystV2Request,
    ChartAnalystV2Thesis,
)
from kronos.swing.v1.chart_analyst_v2_store import LocalChartAnalystV2Store
from kronos.swing.v1.evidence_store import DEFAULT_V1_EVIDENCE_ROOT
from kronos.swing.v1.models import V1Direction


_PER_TIMEFRAME_FAMILIES = {
    "IDENTITY_READABILITY": "readability",
    "PINE_WORKSTATION": "pine_workstation",
    "MARKET_STRUCTURE": "market_structure",
    "IMPULSE": "impulse",
    "PULLBACK": "pullback",
    "CONTINUATION_PATTERN": "continuation_pattern",
    "POST_IMPULSE_BEHAVIOUR": "post_impulse_behaviour",
    "POST_IMPULSE_PROGRESS": "post_impulse_progress",
    "CANDLESTICK_EVIDENCE": "candlestick_evidence",
    "BREAKOUT_BREAKDOWN_RETEST": "breakout_breakdown_retest",
    "SMA20_SMA50_SMA200": "moving_averages",
    "VOLUME_PARTICIPATION": "volume_participation",
    "SUPPORT_RESISTANCE_BARRIERS": "support_resistance_barriers",
    "MATURITY_EXTENSION_CHASE_RISK": "maturity_extension_chase_risk",
    "WEAKENING_FAILURE_EVIDENCE": "weakening_failure_evidence",
    "RESUMPTION_EVIDENCE": "resumption_evidence",
}
_TOP_LEVEL_FAMILIES = {
    "MULTI_TIMEFRAME_ALIGNMENT": "multi_timeframe",
    "PINE_VS_CHART_CONTRADICTION": "pine_vs_chart",
    "THESIS_BEHAVIOUR_RELATIONSHIP": "thesis_behaviour",
    "NEXT_OBSERVABLE_EVENT": "next_observable_event",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Chart Analyst V2 once for one exact retained chart binding."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--product", choices=("NSE", "MCX"), required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selection = _load_selection(
        manifest_path=args.manifest,
        instrument=args.instrument,
        product=ChartAnalystProduct(args.product),
    )
    activation = ChartAnalystV2ActivationService()
    if not activation.enabled():
        raise SystemExit("CHART_ANALYST_V2_DISABLED")
    config = OpenAIChartAnalystV2Config.from_environment()
    store = LocalChartAnalystV2Store()
    provider = OpenAIChartAnalystV2Provider(
        config,
        store=store,
        transport=UrllibOpenAIResponsesTransport(
            credential_source=AppleKeychainApiKeySource(
                provider=OPENAI_CHART_ANALYST_PROVIDER,
                runner=run_security_framework_subprocess,
            ),
            credential_ref=OPENAI_CHART_ANALYST_CREDENTIAL_REF,
        ),
        activation_probe=activation.enabled,
    )
    request = ChartAnalystV2Request(
        run_identity=selection["run_identity"],
        swing_analysis_run_identity=selection["swing_analysis_run_identity"],
        instrument=selection["instrument"],
        product=selection["product"],
        observation_boundary=selection["observation_boundary"],
        request_timestamp=datetime.now(UTC),
        image_sha256=selection["image_sha256"],
        content_type=selection["content_type"],
        original_image=selection["original_image"],
        thesis=ChartAnalystV2Thesis(
            direction=selection["direction"],
            setup=selection["setup"],
        ),
    )
    response = provider.analyze(request)
    response.validate_binding(request)
    telemetry = _telemetry_for(request)
    retained = store.run_response(
        run_identity=request.run_identity,
        swing_analysis_run_identity=request.swing_analysis_run_identity,
        instrument=request.instrument,
        image_sha256=request.image_sha256,
    )
    result = {
        "instrument": response.instrument,
        "api_call": "PASS",
        "model": response.model_identity,
        "image_transmitted": not response.cache_hit,
        "structured_v2_response": "PASS",
        "four_timeframes_returned": _four_timeframes_returned(response.analysis),
        "twenty_evidence_families": _twenty_families_returned(response.analysis),
        "schema_validation": "PASS",
        "result_persisted": retained is not None,
        "input_tokens": telemetry["input_tokens"],
        "output_tokens": telemetry["output_tokens"],
        "total_tokens": telemetry["total_tokens"],
        "estimated_cost_usd": telemetry["estimated_cost_usd"],
        "latency_ms": telemetry["latency_ms"],
        "retries": telemetry["retry_count"],
        "cache_hit": response.cache_hit,
        "failure": "NONE",
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _load_selection(
    *,
    manifest_path: Path,
    instrument: str,
    product: ChartAnalystProduct,
) -> dict[str, object]:
    manifest_path = manifest_path.expanduser().resolve(strict=True)
    evidence_root = DEFAULT_V1_EVIDENCE_ROOT.resolve(strict=True)
    if evidence_root not in manifest_path.parents or manifest_path.name != "manifest.json":
        raise ValueError("CHART_ANALYST_V2_VALIDATION_MANIFEST_INVALID")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parent_run = manifest.get("swing_analysis_run_identity")
    active = manifest.get("active_revision_sha256_by_timeframe")
    revisions = manifest.get("revisions")
    assessments = manifest.get("probable_assessment_identities")
    if (
        manifest.get("schema") != "KRONOS_SWING_V1_TRADINGVIEW_MANIFEST_V1"
        or manifest.get("canonical_instrument") != instrument
        or not is_swing_analysis_run_id(parent_run)
        or type(active) is not dict
        or set(active) != {"DAILY"}
        or type(active["DAILY"]) is not str
        or type(revisions) is not list
        or type(assessments) is not list
        or not assessments
    ):
        raise ValueError("CHART_ANALYST_V2_VALIDATION_BINDING_INVALID")
    revision = next(
        (
            item
            for item in revisions
            if type(item) is dict and item.get("sha256") == active["DAILY"]
        ),
        None,
    )
    if (
        revision is None
        or revision.get("run_identity") != manifest.get("run_identity")
        or revision.get("swing_analysis_run_identity") != parent_run
        or revision.get("canonical_instrument") != instrument
        or revision.get("timeframe") != "DAILY"
    ):
        raise ValueError("CHART_ANALYST_V2_VALIDATION_BINDING_INVALID")
    assessment = str(assessments[0]).split("|", 3)
    if len(assessment) != 4 or assessment[0] != instrument:
        raise ValueError("CHART_ANALYST_V2_VALIDATION_BINDING_INVALID")
    image_path = (evidence_root / str(revision["relative_path"])).resolve(strict=True)
    if evidence_root not in image_path.parents:
        raise ValueError("CHART_ANALYST_V2_VALIDATION_BINDING_INVALID")
    original = image_path.read_bytes()
    if sha256(original).hexdigest() != revision["sha256"]:
        raise ValueError("CHART_ANALYST_V2_VALIDATION_IMAGE_HASH_INVALID")
    return {
        "run_identity": manifest["run_identity"],
        "swing_analysis_run_identity": parent_run,
        "instrument": instrument,
        "product": product,
        "observation_boundary": datetime.fromisoformat(
            str(manifest["observation_boundary"])
        ),
        "image_sha256": revision["sha256"],
        "content_type": revision["content_type"],
        "original_image": original,
        "setup": assessment[1],
        "direction": V1Direction(assessment[2]),
    }


def _telemetry_for(request: ChartAnalystV2Request) -> dict[str, object]:
    path = LocalChartAnalystV2Store().root / "telemetry" / "attempts.jsonl"
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    matching = [
        event
        for event in events
        if event.get("timestamp") == request.request_timestamp.isoformat()
        and event.get("instrument") == request.instrument
        and event.get("image_hash") == request.image_sha256
    ]
    if not matching:
        raise ValueError("CHART_ANALYST_V2_VALIDATION_TELEMETRY_MISSING")
    return matching[-1]


def _four_timeframes_returned(analysis: dict[str, object]) -> bool:
    timeframes = analysis.get("timeframes")
    expected = analysis.get("expected_timeframes_present")
    return (
        type(timeframes) is dict
        and set(timeframes) == set(CHART_ANALYST_V2_TIMEFRAMES)
        and type(expected) is dict
        and set(expected) == set(CHART_ANALYST_V2_TIMEFRAMES)
    )


def _twenty_families_returned(analysis: dict[str, object]) -> bool:
    timeframes = analysis.get("timeframes")
    if type(timeframes) is not dict:
        return False
    found = {
        family
        for family, field in _PER_TIMEFRAME_FAMILIES.items()
        if all(type(timeframes.get(key)) is dict and field in timeframes[key] for key in CHART_ANALYST_V2_TIMEFRAMES)
    }
    found.update(
        family
        for family, field in _TOP_LEVEL_FAMILIES.items()
        if field in analysis
    )
    return (
        len(CHART_ANALYST_V2_EVIDENCE_FAMILIES) == 20
        and found == set(CHART_ANALYST_V2_EVIDENCE_FAMILIES)
    )


if __name__ == "__main__":
    raise SystemExit(main())
