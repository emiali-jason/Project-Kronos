"""Sponsor-governed, same-operation post-decision assessment quote capture.

No retries, candle fallback, after-publication lookup, or admission filtering.
The Provider lease and previously governed instrument binding are operation-local.
"""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256

from kronos.intraday.assessment_observation import (
    ASSESSMENT_CAPTURE_POLICY, AdmissionMarketPriceProof, AssessmentPriceAuthority,
    ProbablesAssessmentObservations, create_missing_assessment_observations, validate_assessment_run,
)
from kronos.intraday.operation_accounting import ProviderRequestCategory
from kronos.intraday.probables_v2 import _identity, _encode
from kronos.provider.contracts.market_data import QuoteSnapshot


def capture_admission_observations(run, *, operation_identity, records, quote, counter, clock):
    """Capture once for every admitted member using its exact prior binding.

    records is owned by the factual source, not Browser/Sponsor input. Each entry
    is the canonical identity and exact InstrumentRecord actually resolved for
    that universe member during the same Discovery operation.
    """
    base = create_missing_assessment_observations(run)
    observations = []
    for item in base.observations:
        result = next(result for result in run.results if result.result_identity == item.admission_identity)
        try:
            canonical, instrument = records[result.universe_member_identity]
            if canonical != item.canonical_subject_identity:
                raise ValueError("BINDING")
            if (item.canonical_subject_identity.startswith("NSE-") and instrument.exchange != "NSE"
                or item.canonical_subject_identity.startswith("MCX-") and instrument.exchange != "MCX"):
                raise ValueError("BINDING")
            if item.canonical_subject_identity.startswith("NSE-INDEX-") and instrument.segment != "INDICES":
                raise ValueError("BINDING")
            # Never use NSE derivatives as an equity/index observation.
            if instrument.exchange == "NSE" and (
                instrument.expiry is not None or instrument.instrument_type in ("FUT", "CE", "PE")
            ):
                raise ValueError("BINDING")
            started = clock()
            snapshot = counter.invoke(ProviderRequestCategory.ASSESSMENT_OBSERVATION_REQUEST,
                quote, instrument, benchmark=canonical == "NSE-INDEX-NIFTY")
            completed = clock()
            if type(snapshot) is not QuoteSnapshot or snapshot.instrument != instrument:
                raise ValueError("BINDING")
            snapshot.__post_init__()
            source_document = _encode(snapshot).decode()
            digest = sha256(source_document.encode()).hexdigest()
            instrument_identity = _identity("PROVIDER-QUOTE-INSTRUMENT-", instrument)
            core = dict(canonical_subject_identity=item.canonical_subject_identity,
                run_identity=run.run_identity, admission_identity=item.admission_identity,
                source_mapping_identity=item.source_mapping_identity,
                market_session_identity=item.market_session_identity,
                source_identity="DOMAIN006-QUOTE:" + instrument_identity,
                source_artifact_digest=digest, authority_publication_identity=ASSESSMENT_CAPTURE_POLICY,
                price=Decimal(str(snapshot.last_price)), observation_time=snapshot.timestamp,
                available_at=completed, source_type="GOVERNED_ADMISSION_PRICE_OBSERVATION",
                operation_identity=operation_identity,
                observation_identity=_identity("INTRADAY-ADMISSION-QUOTE-OBSERVATION-", {
                    "operation":operation_identity,"run":run.run_identity,
                    "admission":item.admission_identity,"source_digest":digest}),
                capture_started_at=started,capture_completed_at=completed,
                provider_instrument_identity=instrument_identity,source_document=source_document)
            proof = AdmissionMarketPriceProof(integrity_identity=_identity(
                "INTEGRITY-ADMISSION-MARKET-PRICE-PROOF-",core),**core)
            observation = replace(item, classification=AssessmentPriceAuthority.EXACT_PRICE_PERSISTED,
                assessment_price=proof.price, assessment_time=proof.observation_time,
                assessment_source_identity=proof.source_identity, proof=proof,
                reason="SAME_ADMISSION_OPERATION_PROVIDER_QUOTE")
        except Exception:
            # No raw Provider exceptions, partial pair, retry or candidate deletion.
            observation = replace(item, reason="ADMISSION_MARKET_OBSERVATION_UNAVAILABLE")
        observations.append(observation)
    core = dict(run_identity=run.run_identity,run_integrity_identity=run.integrity_identity,
        observations=tuple(observations),schema_identity=base.schema_identity,schema_version="1.1.0")
    value = ProbablesAssessmentObservations(
        evidence_identity=_identity("INTRADAY-ASSESSMENT-OBSERVATIONS-",core),
        integrity_identity=_identity("INTEGRITY-INTRADAY-ASSESSMENT-OBSERVATIONS-",core),**core)
    validate_assessment_run(value,run)
    return value
