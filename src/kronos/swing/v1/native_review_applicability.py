"""Read-only dependency tracing for pre-witness Native preparation estates.

This deliberately excludes Analysis existence and the receipt-based V3 intake
stores. That path derives a ProspectiveNativeReview directly from the published
Analysis and does not require NativeReviewEvidenceStore.complete-runs.
"""
from __future__ import annotations

from kronos.swing.v1.native_review import _read, _native_evidence_paths, build_native_review_requirements


def legacy_preparation_lineage(native_run, facts, *, store, visual_store,
                               readiness_store, chart_store, plan_store,
                               pdf_store, sponsor_store):
    run_id = native_run.run_identity
    evidence = []
    # These exact run namespaces are exclusively written by the historical
    # requirement-bound producers, including a corrupt/partially lost record.
    for label, directory, boundary in (
        ("REFERENCE", store.root / "reference-results" / run_id, store.root),
        ("VISUAL_V2", visual_store.root / run_id, visual_store.root),
        ("READINESS_V0", readiness_store.root / run_id, readiness_store.root),
        ("NATIVE_CHART", chart_store.root / "native-review-composite-charts" / run_id,
         chart_store.root),
    ):
        if _native_evidence_paths(directory, "*", boundary=boundary):
            evidence.append(label)

    # Historical PDF transports are distinct from receipt-intake request and
    # acceptance stores. Both V0 and V3 Question packs consume prepared Review;
    # their Answer import records reference that exact pack rather than a run.
    pdf_roots = {store.root / "pdf-transport-v0", store.root / "pdf-transport-v3"}
    if pdf_store is not None:
        pdf_roots.add(pdf_store.root)
    if _historical_pdf_lineage(pdf_roots, run_id):
        evidence.append("HISTORICAL_REVIEW_PACK")

    # Trade plans may use either V0 readiness or receipt-based V3/KR370 readiness.
    # Only the exact former identity proves preparation from the plan alone.
    # Native Sponsor admission is checked separately below: its workflow also
    # requires prepared requirements, even when the plan uses V3 readiness.
    plan_root = plan_store.root / run_id
    plan_paths = _native_evidence_paths(plan_root, "*", boundary=plan_store.root)
    if plan_paths:
        if any(len(path.relative_to(plan_root).parts) != 2 or path.suffix != ".json"
               for path in plan_paths):
            raise ValueError("NATIVE_REVIEW_LEGACY_LINEAGE_INVALID")
        requirements = build_native_review_requirements(native_run, facts)
        if not requirements:
            raise ValueError("NATIVE_REVIEW_LEGACY_LINEAGE_INVALID")
        plans = plan_store.load_for_requirements(requirements)
        if set(plan_paths) != {plan_root / plan.canonical_instrument / (plan.trade_plan_id + ".json")
                              for plan in plans}:
            raise ValueError("NATIVE_REVIEW_LEGACY_LINEAGE_INVALID")
        for plan in plans:
            if plan.readiness_record_identity == "NATIVE-READINESS-" + plan.readiness_record_sha256:
                evidence.append("V0_READINESS_TRADE_PLAN")
    if _native_sponsor_decisions(sponsor_store, run_id):
        evidence.append("NATIVE_SPONSOR_DECISION")
    return tuple(sorted(set(evidence)))


def retained_preparation_presence(*, store, visual_store, readiness_store,
                                  chart_store, plan_store, pdf_store, sponsor_store,
                                  lifecycle):
    """Find evidence needing absent upstream without selecting or guessing a run."""
    evidence = []
    for label, directory, boundary in (
        ("REQUIREMENTS", store.root / "complete-runs", store.root),
        ("INTENT", store.root / "preparation-intents", store.root),
        ("WITNESS", store.root / "preparation-witnesses", store.root),
        ("REFERENCE", store.root / "reference-results", store.root),
        ("VISUAL_V2", visual_store.root, visual_store.root),
        ("READINESS_V0", readiness_store.root, readiness_store.root),
        ("NATIVE_CHART", chart_store.root / "native-review-composite-charts", chart_store.root),
    ):
        if _native_evidence_paths(directory, "*", boundary=boundary):
            evidence.append(label)
    pdf_roots = {store.root / "pdf-transport-v0", store.root / "pdf-transport-v3"}
    if pdf_store is not None:
        pdf_roots.add(pdf_store.root)
    if _historical_pdf_lineage(pdf_roots):
        evidence.append("HISTORICAL_REVIEW_PACK")
    from kronos.swing.v1.native_trade_construction import (
        _record_from_dict, TRADE_PLAN_SCHEMA, TRADE_PLAN_SCHEMA_V0,
    )
    for path in _native_evidence_paths(plan_store.root, "*"):
        payload = _read(path)
        if payload.get("schema") not in {TRADE_PLAN_SCHEMA, TRADE_PLAN_SCHEMA_V0}:
            raise ValueError("NATIVE_REVIEW_LEGACY_LINEAGE_INVALID")
        plan = _record_from_dict(payload.get("record"))
        if plan.readiness_record_identity == "NATIVE-READINESS-" + plan.readiness_record_sha256:
            evidence.append("V0_READINESS_TRADE_PLAN")
    if _native_sponsor_decisions(sponsor_store):
        evidence.append("NATIVE_SPONSOR_DECISION")
    # Lifecycle has no run ID, so it cannot be assigned to an exact current run.
    # With all Analysis absent, a validated Native position is nevertheless
    # positive unresolved preparation lineage. MCX uses independent admission.
    if any(item.trade_plan_id.startswith("TRADE-PLAN-") for item in lifecycle.positions):
        evidence.append("NATIVE_LIFECYCLE")
    return tuple(sorted(set(evidence)))


def _native_sponsor_decisions(store, run_id=None):
    """Native admission requires _requirement_for; MCX V1 admission does not.

    See NativeReviewWorkflow.bind_operability_inputs / initiate_sponsor_decision,
    versus mcx_trade_plan.arm_mcx_v1_paper and mcx_live_attestation admission.
    Both use LocalSponsorDecisionStore, with distinct exact plan ID contracts.
    """
    root = store.root if run_id is None else store.root / run_id
    found = []
    bindings = set()
    for path in _native_evidence_paths(root, "*", boundary=store.root):
        parts = path.relative_to(root).parts
        if len(parts) < (3 if run_id is None else 2):
            raise ValueError("NATIVE_REVIEW_SPONSOR_LINEAGE_INVALID")
        run, plan = (parts[:2] if run_id is None else (run_id, parts[0]))
        # MCX's independent producer shares this store; it does not establish
        # applicability of the historical Native preparation operation.
        if plan.startswith("MCX-TRADE-PLAN-"):
            continue
        if not plan.startswith("TRADE-PLAN-"):
            raise ValueError("NATIVE_REVIEW_SPONSOR_LINEAGE_INVALID")
        bindings.add((run, plan))
    for run, plan in sorted(bindings):
        # A surviving position with a lost decision is incomplete Native lineage,
        # never absence. The existing typed owner reader fails closed for it.
        result = store.load_plan(run, plan)
        decision = result.decision
        if (decision is None or decision.native_run_identity != run
                or decision.trade_plan_id != plan):
            raise ValueError("NATIVE_REVIEW_SPONSOR_LINEAGE_INVALID")
        found.append(decision)
    return tuple(found)


def _historical_pdf_lineage(roots, run_id=None):
    """Resolve old Question/Answer/current/recovery references without guessing a run."""
    from kronos.swing.run_identity import is_swing_analysis_run_id
    from kronos.swing.v1.pdf_visual_review import REVIEW_PACK_RECORD_SCHEMA, _review_pack_from_dict
    from kronos.swing.v1.pdf_visual_review_v3_live import VISUAL_V3_LIVE_REVIEW_SCHEMA, _pack_from_dict
    readers = {REVIEW_PACK_RECORD_SCHEMA: _review_pack_from_dict,
               VISUAL_V3_LIVE_REVIEW_SCHEMA: _pack_from_dict}
    found = False
    for root in sorted(roots):
        packs = {}
        paths = _native_evidence_paths(root, "*")
        pack_root = root / "review-packs"
        for path in paths:
            if path.parent != pack_root:
                continue
            # Validate the governed envelope, complete typed pack contract and
            # NativeDiscoveryRun's existing identity contract before deciding
            # a pack belongs to another run. Malformed bindings are not absence.
            payload = _read(path)
            try:
                record = readers[payload.get("schema")](payload.get("record"))
                if (not is_swing_analysis_run_id(record.native_run_identity)
                        or record.review_pack_id != path.stem or path.suffix != ".json"):
                    raise ValueError("NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE")
            except (KeyError, TypeError, AttributeError, ValueError) as error:
                raise ValueError("NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE") from error
            packs[path.stem] = record
            if run_id is None or record.native_run_identity == run_id:
                found = True
        for path in paths:
            if path.parent == pack_root:
                continue
            try:
                references = _historical_reference_bindings(root, path, _read(path), packs)
            except (KeyError, TypeError, AttributeError, ValueError) as error:
                raise ValueError("NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE") from error
            if not references or not references.issubset(packs):
                # A surviving pointer/Answer with its pack lost is incomplete
                # historical authority; do not silently assign it another run.
                raise ValueError("NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE")
    return found


def _historical_reference_bindings(root, path, payload, packs):
    """Check existing reference metadata contracts without opening PDF artifacts."""
    from kronos.swing.v1 import pdf_visual_review as v0
    from kronos.swing.v1 import pdf_visual_review_v3_live as v3
    from kronos.swing.v1 import pdf_visual_review_v3_recovery as recovery
    invalid = "NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE"
    parts = path.relative_to(root).parts
    references = _historical_pack_references(payload)
    if len(references) != 1 or not references.issubset(packs) or path.suffix != ".json":
        raise ValueError(invalid)
    pack_id = next(iter(references))
    schema = payload.get("schema")
    v0_schemas = {v0.ANSWER_IMPORT_RECORD_SCHEMA, v0.ANSWER_ARTIFACT_RECORD_SCHEMA,
                  v0.CURRENT_REVIEW_PACK_SELECTION_SCHEMA}
    expected_type = v0.ReviewPackRecord if schema in v0_schemas else v3.VisualV3LiveReviewPack
    if type(packs[pack_id]) is not expected_type:
        raise ValueError(invalid)
    if parts[0] in {"answer-imports", "answer-artifacts"}:
        # retain_answer_import/artifact and retain_import bind the namespace
        # pack as well as the record; neither identity may hide the other.
        readers = {v0.ANSWER_IMPORT_RECORD_SCHEMA: v0._answer_import_from_dict,
                   v0.ANSWER_ARTIFACT_RECORD_SCHEMA: v0._answer_artifact_from_dict,
                   v3.VISUAL_V3_LIVE_IMPORT_SCHEMA: v3._import_from_dict}
        record = readers[schema](payload.get("record"))
        if schema == v0.ANSWER_ARTIFACT_RECORD_SCHEMA:
            expected = ("answer-artifacts", pack_id, record.answer_pdf_sha256 + ".json")
        else:
            attempt = (record.attempt_identity if schema == v0.ANSWER_IMPORT_RECORD_SCHEMA
                       else f"{record.observed_at.timestamp():.6f}")
            expected = ("answer-imports", pack_id, record.answer_pdf_sha256, attempt + ".json")
        if parts != expected or record.review_pack_id != pack_id:
            raise ValueError(invalid)
    elif parts == ("pending-publication.json",):
        # Publication intent repeats the immutable typed V3 pack. Its temporary
        # artifact is outside this read-only applicability assessment.
        if v3._pack_from_dict(payload.get("record")) != packs[pack_id]:
            raise ValueError(invalid)
    elif parts == ("current-review-pack.json",) or parts[0] == "selection-history":
        if schema == v0.CURRENT_REVIEW_PACK_SELECTION_SCHEMA:
            value = payload["selection"]
            selection = v0.CurrentReviewPackSelection(value["review_pack_id"], value["scope"],
                                                      tuple(tuple(item) for item in value["skipped"]))
            if selection.review_pack_id != pack_id or parts != ("current-review-pack.json",):
                raise ValueError(invalid)
        elif schema == v3.VISUAL_V3_LIVE_SELECTION_SCHEMA:
            if payload.get("review_pack_id") != pack_id:
                raise ValueError(invalid)
            if parts[0] == "selection-history" and parts != (
                    "selection-history", recovery._digest(payload) + ".json"):
                raise ValueError(invalid)
            identity = payload.get("artifact_recovery_sha256")
            if identity is not None:
                if (not isinstance(identity, str) or len(identity) != 64
                        or any(c not in "0123456789abcdef" for c in identity)):
                    raise ValueError(invalid)
                target = root / "artifact-recoveries" / (identity + ".json")
                retained = _read(target)
                if _historical_reference_bindings(root, target, retained, packs) != references:
                    raise ValueError(invalid)
        else:
            raise ValueError(invalid)
    elif parts[0] == "artifact-recoveries":
        body = dict(payload)
        checksum = body.pop("checksum", None)
        if (schema != recovery.SCHEMA or body.get("version") != recovery.VERSION
                or checksum != recovery._digest(body)
                or parts != ("artifact-recoveries", checksum + ".json")
                or body.get("canonical_pack_digest") != recovery._digest(v3._primitive(packs[pack_id]))
                or body.get("predecessor_selection") != {
                    "schema": v3.VISUAL_V3_LIVE_SELECTION_SCHEMA, "review_pack_id": pack_id}):
            raise ValueError(invalid)
    else:
        raise ValueError(invalid)
    return references


def _historical_pack_references(value):
    references = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "review_pack_id":
                if not isinstance(item, str) or not item:
                    raise ValueError("NATIVE_REVIEW_HISTORICAL_PACK_LINEAGE_UNAVAILABLE")
                references.add(item)
            else:
                references.update(_historical_pack_references(item))
    elif isinstance(value, list):
        for item in value:
            references.update(_historical_pack_references(item))
    return references
