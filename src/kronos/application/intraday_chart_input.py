"""Read-only operational chart gate, bound to existing Review and Probables stores."""
from kronos.intraday.chart_input import (
    NSE_PANELS, MCX_PANELS, ExpectedChartPanel, compare_chart_panel,
)
from kronos.intraday.validation import ValidationState
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.market.calendar import MarketCalendarPublisher
from datetime import datetime, timezone


class IntradayChartInputGate:
    def __init__(self, review, probables, resolver, calendar=None, clock=None):
        self.review, self.probables, self.resolver = review, probables, resolver
        self.calendar = calendar or MarketCalendarPublisher()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def expectations(self, cycle, chart, bundle=None):
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
            target = (subject if role == 'REFERENCE' or bundle is None else
                      bundle.native_identity_binding.actual_derivative_contract_identity)
            venue = reference.venue.value if role == 'REFERENCE' else ('MCX' if bundle else 'NSE')
            # Existing selected evidence has no reference-series or 4H candle.
            # Never relabel native/1H evidence to fill those slots.
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
            result.append(ExpectedChartPanel(role, timeframe, subject, target, venue,
                cycle.analysis_boundary,
                chart.received_at if bundle and role == 'NATIVE' else cycle.analysis_boundary,
                source, schedule,
                'INR' if bundle and role == 'NATIVE' else 'USD' if role == 'REFERENCE' else None))
        return tuple(result)

    def evaluate(self, cycle, chart, *, bundle=None, resolver=None):
        payload = self.review.load_chart_bytes(chart)
        receipt = self.review.load_chart_input(chart)
        try:
            expected = self.expectations(cycle, chart, bundle)
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
                bundle=None, resolver=None, visual_answers=()):
        results = self.evaluate(cycle, chart, bundle=bundle, resolver=resolver)
        if any(r.overall is ValidationState.NOT_VALIDATED for r in results):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_INVALID)
        if not results or any(r.overall is not ValidationState.VALIDATED for r in results):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
        receipt = self.review.load_chart_input(chart)
        if receipt is None or any(
            (p.observed_subject != observed_native if p.role == 'NATIVE' else
             p.observed_series != observed_reference) for p in receipt.panels
        ):
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        if visual_answers:
            from kronos.intraday.visual_contract_v2 import require_question_content
            require_question_content(visual_answers, receipt.panels)
        return results
