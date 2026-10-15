"""Synthetic TE-04A fixture. NOT FOR GENUINE FORECASTING; no owner enrollment."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from kronos.theta.contracts import CANONICAL, SUBJECTS, digest
from kronos.theta.contracts_v3 import make_question_v3, make_question_batch_v3, combined_answer_template
from kronos.theta.schema_v3 import RESEARCH_SECTIONS

T0 = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
RECEIPT = T0 + timedelta(hours=3)


def synthetic_contracts():
    questions = {}
    macro = {"subject": "GLOBAL_MACRO", "cycle_id": "SYNTHETIC-CYCLE",
             "chart_id": "SYNTHETIC-MACRO", "revision_id": "SYNTHETIC-MACRO-REV1",
             "sha256": digest(b"SYNTHETIC shared Macro original")}
    for i, subject in enumerate(SUBJECTS):
        binding = {"subject": subject, "canonical_subject": CANONICAL[subject],
            "cycle_id": macro["cycle_id"], "macro_chart": deepcopy(macro),
            "commodity_chart": {"subject": subject, "cycle_id": macro["cycle_id"],
                "chart_id": "SYNTHETIC-" + subject, "revision_id": "SYNTHETIC-" + subject + "-REV1",
                "sha256": digest(("SYNTHETIC " + subject + " original").encode())},
            "methodology": {"identity": "SYNTHETIC-METHOD", "version": "0.0.1", "sha256": digest(b"SYNTHETIC policy")},
            "target_authority": {"identity": "SYNTHETIC-TARGET-AUTHORITY", "version": "0.0.1", "sha256": digest(subject.encode())}}
        targets = {h: {"subject": subject, "canonical_subject": CANONICAL[subject], "horizon": h,
            "option_expiry": expiry, "expires_at": expiry + "T23:00:00+05:30",
            "underlying_future": "SYNTHETIC-" + subject + "-FUT-" + future, "futures_expiry": future,
            "settlement_reference": "SYNTHETIC-MCX-DSP", "authority_reference": "SYNTHETIC-EXCHANGE-AUTHORITY",
            "exchange_evidence_reference": "SYNTHETIC-EXCHANGE-DOCUMENT",
            "target": "OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE", "price_unit": "SYNTHETIC INR/unit"}
            for h, expiry, future in (("E1", "2026-10-25", "2026-10-30"), ("E2", "2026-11-25", "2026-11-30"))}
        questions[subject] = make_question_v3(binding=binding, targets=targets,
            created_at=(T0+timedelta(minutes=i)).isoformat(), authority_valid_through="2026-12-01T00:00:00+00:00",
            methodology_instructions="SYNTHETIC - NOT FOR GENUINE FORECASTING. Contract test only.", synthetic=True)
    batch = make_question_batch_v3(questions)
    answer = combined_answer_template(batch, questions)
    answer["answer_package_id"] = "SYNTHETIC-PACKAGE-1"
    for subject, child in answer["answers"].items():
        child.update(answer_id="SYNTHETIC-ANSWER-" + subject, analyzed_at=(T0+timedelta(hours=2)).isoformat(),
            analyst={"identity": "SYNTHETIC Astra", "model": "SYNTHETIC Astra-Ultra",
                     "provenance": "SYNTHETIC NOT FOR GENUINE FORECASTING"})
        r = child["research"]
        for section in RESEARCH_SECTIONS:
            r[section] = {"availability": "AVAILABLE", "classification": "HYPOTHESIS",
                "text": "SYNTHETIC " + section + " — research fixture only.", "reason": None, "evidence_ids": ["CLAIM-1"]}
        r["chart_observations"] = [{"observation_id": "OBS-1", "chart_reference": deepcopy(child["binding"]["commodity_chart"]),
            "panel_locator": "SYNTHETIC top-left", "role": "REFERENCE", "displayed_instrument": "SYNTHETIC Reference",
            "timeframe": "1D", "availability": "AVAILABLE", "observation_text": "SYNTHETIC visible observation",
            "classification": "HYPOTHESIS", "visible_as_of": None, "completion": "UNKNOWN", "unavailable_reason": None,
            "horizons": ["E1", "E2"]}]
        r["evidence_items"] = [{"evidence_id": "CLAIM-1", "statement": "SYNTHETIC supported claim",
            "classification": "HYPOTHESIS", "source_ids": ["SOURCE-1"], "observation_ids": ["OBS-1"],
            "horizons": ["E1", "E2"], "assumption_ids": ["ASSUMPTION-1"]}]
        r["sources"] = [{"source_id": "SOURCE-1", "publisher": "SYNTHETIC publisher", "title": "SYNTHETIC research",
            "source_kind": "UNKNOWN", "url": "https://example.com/synthetic", "reference": None,
            "published_at": None, "available_at": (T0-timedelta(hours=1)).isoformat(),
            "accessed_at": (T0+timedelta(hours=1)).isoformat(), "availability_evidence": "SYNTHETIC archive assertion",
            "observation_period": "SYNTHETIC period", "lineage": {"status": "UNKNOWN", "original_information_id": None,
                "derivative_source_ids": []}, "archive_version_locator": None, "relevance": "SYNTHETIC relevance",
            "linked_evidence_ids": ["CLAIM-1"]}]
        r["assumptions"] = [{"identity": "ASSUMPTION-1", "statement": "SYNTHETIC assumption", "scope": "COMMODITY",
            "horizons": ["E1", "E2"], "supporting_evidence_ids": ["CLAIM-1"],
            "affected_references": [{"kind": "FORECAST", "identity": "E1"}, {"kind": "FORECAST", "identity": "E2"}],
            "unresolved_consequence": "SYNTHETIC uncertainty"}]
        r["limitations"] = [{"identity": "LIMITATION-1", "statement": "SYNTHETIC limitation", "scope": "COMMODITY",
            "horizons": ["E1", "E2"], "supporting_evidence_ids": [],
            "affected_references": [{"kind": "EVIDENCE", "identity": "CLAIM-1"}],
            "unresolved_consequence": "SYNTHETIC no quality conclusion"}]
        r["relationships"] = [{"relation_id": "RELATION-1",
            "references": [{"kind": "EVIDENCE", "identity": "CLAIM-1"}, {"kind": "OBSERVATION", "identity": "OBS-1"}],
            "relationship_type": "ALIGNMENT", "horizons": ["E1", "E2"],
            "explanation": "SYNTHETIC asserted relationship only", "unresolved_limitation": None, "limitation_ids": []}]
        r["scheduled_events"] = [{"event_id": "EVENT-1", "description": "SYNTHETIC event", "availability": "AVAILABLE",
            "scheduled_window": {"start": "2026-10-20T00:00:00+00:00", "end": "2026-10-20T23:59:59+00:00"},
            "schedule_source_id": "SOURCE-1", "schedule_known_at": (T0-timedelta(minutes=30)).isoformat(),
            "horizons": ["E1", "E2"], "evidence_ids": ["CLAIM-1"], "possible_impact": "SYNTHETIC impact",
            "limitations": "SYNTHETIC outcome unknown at T0"}]
        for h, f in child["forecasts"].items():
            f.update(lower="-10.00" if h == "E1" else "100.00", upper="120.000", confidence_pct="82.00",
                material_evidence_ids=["CLAIM-1"], material_source_ids=["SOURCE-1"],
                assumption_ids=["ASSUMPTION-1"], limitation_ids=["LIMITATION-1"])
            for section in ("rationale", "counterevidence", "uncertainty", "path_risk", "confidence_justification"):
                f[section] = {"classification": "HYPOTHESIS", "text": "SYNTHETIC " + h + " " + section,
                              "evidence_ids": ["CLAIM-1"], "source_ids": ["SOURCE-1"]}
    return questions, batch, answer
