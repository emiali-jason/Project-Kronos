"""Read-only composition of Instrument and Market option publications.

This publication boundary owns no product E1/E2 selection. Review is supplied
explicitly by the trusted commissioning caller, never inferred from a nonempty
string, file order or the presence of an exchange PDF.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from kronos.instrument.option_series import (
    DEFAULT_OPTION_ROOT, PublicationPin, aware, authority_boundary, canonical_bytes,
    check, document, load_option_series, public_id, read_exact)
from kronos.market.option_expiry import DEFAULT_EXPIRY_ROOT, load_option_expiries


@dataclass(frozen=True)
class OptionAuthorityReview:
    review_reference: str
    instrument_reference: str
    market_reference: str
    current_sha256: str
    instrument_disposition: str
    market_disposition: str


class OptionAuthorityPublication:
    @authority_boundary
    def __init__(self, *, instrument_root=DEFAULT_OPTION_ROOT, market_root=DEFAULT_EXPIRY_ROOT,
                 current_filename="current.json", calendar_publisher=None, review=None):
        self.instrument_root, self.market_root = instrument_root, market_root
        self.current_filename, self.calendar_publisher = current_filename, calendar_publisher
        self.current = self._current()
        self.current_sha256 = sha256(canonical_bytes(self.current)).hexdigest()
        self.instrument = load_option_series(instrument_root, pin=PublicationPin(**self.current["instrument"]))
        self.market = load_option_expiries(instrument=self.instrument,
            pin=PublicationPin(**self.current["market"]), root=market_root, calendar_publisher=calendar_publisher)
        self.first = max(self.instrument.effective_from, self.market.effective_from,
                         aware(self.current["effective_from"]))
        self.last = min(self.instrument.effective_through, self.market.effective_through,
                        aware(self.current["effective_through"]))
        check(self.first <= self.last)
        self.review = review
        if review is not None:
            check(type(review) is OptionAuthorityReview, "OPTION_AUTHORITY_REVIEW_INVALID")
            public_id(review.review_reference)
            check(review.instrument_reference == self.instrument.pin.reference
                  and review.market_reference == self.market.pin.reference
                  and review.current_sha256 == self.current_sha256
                  and review.instrument_disposition == "APPROVED"
                  and review.market_disposition == "APPROVED", "OPTION_AUTHORITY_REVIEW_INVALID")

    @authority_boundary
    def _current(self):
        value = document(read_exact(self.market_root, self.current_filename))
        check(set(value) == {"schema_identity", "schema_version", "identity", "instrument", "market",
                             "effective_from", "effective_through", "owner_reviews", "supersedes"})
        check(value["schema_identity"] == "KRONOS-MCX-OPTION-AUTHORITY-CURRENT-V1"
              and value["schema_version"] == "1.0.0")
        public_id(value["identity"])
        check(set(value["owner_reviews"]) == {"INSTRUMENT", "MARKET", "CHIEF_ARCHITECT"})
        # Historical candidate review placeholders confer no admission.
        return value

    @property
    def descriptor(self):
        return {"identity": self.current["identity"], "version": self.instrument.pin.version,
                "sha256": self.current_sha256}

    @authority_boundary
    def eligible(self, subject, at):
        check(type(at) is datetime and at.tzinfo is not None and at.utcoffset() is not None,
              "OPTION_AUTHORITY_TEMPORAL_INVALID")
        check(sha256(canonical_bytes(self._current())).hexdigest() == self.current_sha256,
              "OPTION_AUTHORITY_PUBLICATION_SUPERSEDED")
        check(self.first <= at <= self.last, "OPTION_AUTHORITY_PUBLICATION_STALE")
        # Revalidate pins and sources at every admission, including an already
        # loaded instance. A replaced PDF/calendar never leaves a cached fallback.
        instrument = load_option_series(self.instrument_root, pin=self.instrument.pin)
        market = load_option_expiries(instrument=instrument, pin=self.market.pin,
            root=self.market_root, calendar_publisher=self.calendar_publisher)
        rows = [r for r in instrument.rows if r.family == subject
                and market.coverage_start <= r.expiry <= market.coverage_end]
        check(bool(rows), "OPTION_AUTHORITY_FAMILY_UNAVAILABLE")
        endpoints = {e.series_identity: e for e in market.endpoints}
        check(all(r.identity in endpoints for r in rows), "OPTION_AUTHORITY_COVERAGE_UNAVAILABLE")
        return tuple((r, endpoints[r.identity]) for r in rows if at < endpoints[r.identity].expires_at)
