"""Read-only operational chart gate, bound to existing Review and Probables stores."""
from kronos.intraday.chart_input import (
    NSE_PANELS, MCX_PANELS, ExpectedChartPanel, compare_chart_panel,
)
from kronos.intraday.validation import ValidationState
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.market.calendar import MarketCalendarPublisher
from datetime import datetime, timezone
from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
from kronos.application.intraday_mcx_chart_source import native_four_hour


class IntradayChartInputGate:
    def __init__(self, review, probables, resolver, calendar=None, clock=None):
        self.review, self.probables, self.resolver = review, probables, resolver
        self.calendar = calendar or MarketCalendarPublisher()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.native_history = McxContractHistoryStore(review.root.parent)
        self.native_bindings = ActiveDerivativeBindingStore(review.root.parent / "active-derivative-bindings")

    def expectations(self, cycle, chart, bundle=None, *, family_visual=False):
        handoff = self.review.load_handoff(cycle.handoff_identity)
        mapping = self.probables.load_mapping(handoff.source_mapping_identity)
        selection = self.probables.load_selection(handoff.completed_evidence_selection_identity)
        result = self.probables.load_result(cycle.probable_result_identity)
        run = self.probables.load_run(cycle.probables_run_identity)
        if (result not in run.results
            or result.source_mapping_identity != mapping.mapping_identity
            or result.completed_evidence_selection_identity != selection.selection_identity
            or run.analysis_boundary != cycle.analysis_boundary
            or mapping.completed_evidence != selection
            or mapping.mapping_identity != handoff.source_mapping_identity
            or mapping.canonical_subject_identity != cycle.canonical_subject_identity
            or mapping.analysis_boundary != cycle.analysis_boundary
            or selection.integrity_identity != handoff.completed_evidence_integrity_identity
            or chart.review_cycle_identity != cycle.cycle_identity
            or chart.probables_run_identity != cycle.probables_run_identity
            or chart.probable_result_identity != cycle.probable_result_identity
            or chart.expected_canonical_subject_identity != cycle.canonical_subject_identity):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        if bool(bundle) != bool(chart.paired_bundle_identity):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        panels = MCX_PANELS if bundle else NSE_PANELS
        result = []
        for role, timeframe in panels:
            reference = bundle.reference_relationship if bundle else None
            subject = (reference.reference_analytical_subject_identity if role == 'REFERENCE'
                       else cycle.canonical_subject_identity)
            target = (subject if role == 'REFERENCE' or bundle is None or family_visual else
                      bundle.native_identity_binding.actual_derivative_contract_identity)
            venue = reference.venue.value if role == 'REFERENCE' else ('MCX' if bundle else 'NSE')
            # Reference context is visual only; no reference market source is invented.
            candles = tuple(x.candle for x in selection.selected_candles
                            if x.candle.canonical_subject_identity == subject
                            and x.candle.timeframe.value == timeframe)
            source = max(candles, key=lambda x: x.candle_end) if candles else None
            schedule = None
            if source is not None:
                try:
                    profile = self.calendar.instrument_session_profile(
                        venue, source.candle_start.date(), canonical_instrument_id=subject,
                        observed_at=cycle.analysis_boundary)
                    if profile:
                        schedule = next((s for s in (profile.continuous_trading, profile.closing_auction_session)
                                         if s and s.session_identity == source.market_session_identity), None)
                except ValueError:
                    pass
            if bundle and role == "REFERENCE":
                source, schedule = None, None
            if bundle and role == "NATIVE" and timeframe == "4H":
                binding = self.native_bindings.load(binding_identity=bundle.native_identity_binding.active_binding_identity)
                if binding.integrity_identity != bundle.native_identity_binding.active_binding_integrity_identity:
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
                source, schedule = native_four_hour(cycle=cycle, binding=binding,
                    selection=selection, history=self.native_history, calendar=self.calendar)
            result.append(ExpectedChartPanel(role, timeframe, subject, target, venue,
                cycle.analysis_boundary,
                chart.received_at if bundle and role == 'NATIVE' and not family_visual else cycle.analysis_boundary,
                source, schedule,
                'INR' if bundle and role == 'NATIVE' else 'USD' if role == 'REFERENCE' else None,
                supporting_visual_only=bool(bundle and role == 'REFERENCE')))
        return tuple(result)

    def evaluate(self, cycle, chart, *, bundle=None, resolver=None, receipt=None):
        payload = self.review.load_chart_bytes(chart)
        receipt = receipt if receipt is not None else self.review.load_chart_input(chart)
        try:
            from kronos.instrument.visual_identity import uses_family_visual_authority
            expected = self.expectations(cycle, chart, bundle, family_visual=uses_family_visual_authority(resolver or self.resolver))
        except ReviewError:
            raise
        except (ValueError, OSError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
        if receipt is not None:
            self.review.validate_chart_input_binding(receipt, chart, payload)
            if not chart.received_at <= receipt.observed_at <= self.clock():
                raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
            keys = tuple((p.role, p.timeframe) for p in receipt.panels)
            if keys != tuple((p.role, p.timeframe) for p in expected):
                raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_INVALID)
        observations = {(p.role, p.timeframe): p for p in receipt.panels} if receipt else {}
        return tuple(compare_chart_panel(e, observations.get((e.role, e.timeframe)),
                     resolver=resolver or self.resolver, received_at=chart.received_at,
                     observed_at=receipt.observed_at if receipt else chart.received_at)
                     for e in expected)

    def require(self, cycle, chart, *, observed_native, observed_reference=None,
                bundle=None, resolver=None, visual_answers=(), receipt=None):
        from kronos.instrument.visual_identity import uses_family_visual_authority
        results = self.evaluate(cycle, chart, bundle=bundle, resolver=resolver, receipt=receipt)
        if any(r.overall is ValidationState.NOT_VALIDATED for r in results):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_INVALID)
        native = tuple(r for r in results if r.role == "NATIVE")
        reference = tuple(r for r in results if r.role == "REFERENCE")
        if (not native or any(r.overall is not ValidationState.VALIDATED for r in native)
            or any(r.identity is not ValidationState.VALIDATED
                   or r.visual_temporal_state in {"VISIBLY_CONTRADICTED", "INSUFFICIENT_VISUAL_EVIDENCE"}
                   or r.core_content is not ValidationState.VALIDATED
                   or r.authority != "SUPPORTING_VISUAL_CONTEXT_ONLY"
                   or r.independent_correspondence != "NOT_INDEPENDENTLY_ESTABLISHED" for r in reference)):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
        receipt = receipt if receipt is not None else self.review.load_chart_input(chart)
        if receipt is None or any(
            (p.observed_subject != observed_native if p.role == 'NATIVE' else
             (p.observed_subject if uses_family_visual_authority(resolver or self.resolver) else p.observed_series) != observed_reference) for p in receipt.panels
        ):
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        if visual_answers:
            from kronos.intraday.visual_contract_v2 import require_question_content
            require_question_content(visual_answers, receipt.panels)
        return results
