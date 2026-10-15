"""TE-03A thin read-only owner-authority adapter, not a Theta fact store.

Default composition is unchanged. Explicit commissioning is required. The
retained candidate cannot commission genuine Questions before owner review.
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256

from kronos.instrument.option_series import OptionAuthorityError, canonical_bytes, check
from kronos.market.option_authority import OptionAuthorityPublication
from kronos.theta.contracts import AuthorityBundle, ExpiryTarget, ThetaError, require


@dataclass(frozen=True)
class ResolvedOptionTarget:
    horizon: str
    series: object
    endpoint: object
    instrument_reference: str
    market_reference: str
    authority_currentness_reference: str
    valid_from: datetime
    valid_through: datetime
    owner_qualified: bool


class OwnerOptionAuthority(OptionAuthorityPublication):
    """Theta's first/second eligible selection over shared owner publications."""
    def resolve(self, subject, at):
        eligible = sorted(self.eligible(subject, at), key=lambda item: item[1].expires_at)
        check(len(eligible) >= 2, "OPTION_AUTHORITY_E2_UNAVAILABLE")
        chosen = eligible[:2]
        check(chosen[0][0].expiry < chosen[1][0].expiry, "OPTION_AUTHORITY_SERIES_AMBIGUOUS")
        return tuple(ResolvedOptionTarget(horizon, row, endpoint, self.instrument.pin.reference,
                     self.market.pin.reference, self.current["identity"]+"/SHA256:"+
                     self.current_sha256, self.first, self.last, self.review is not None)
                     for horizon,(row,endpoint) in zip(("E1","E2"),chosen))


def target_record(target):
    """Exact public fact record addressed by V3's existing compact ID grammar."""
    return {"series": {**asdict(target.series), "expiry": target.series.expiry.isoformat(),
                       "futures_expiry": target.series.futures_expiry.isoformat()},
            "endpoint": {**asdict(target.endpoint), "expiry": target.endpoint.expiry.isoformat(),
                         "opens_at": target.endpoint.opens_at.isoformat(),
                         "expires_at": target.endpoint.expires_at.isoformat()},
            "instrument_reference": target.instrument_reference,
            "market_reference": target.market_reference,
            "currentness_reference": target.authority_currentness_reference}


def expiry_target(t):
    return ExpiryTarget(subject=t.series.family, canonical_subject=t.series.canonical_subject,
        horizon=t.horizon, option_expiry=t.series.expiry.isoformat(), expires_at=t.endpoint.expires_at.isoformat(),
        underlying_future=t.series.underlying_future, futures_expiry=t.series.futures_expiry.isoformat(),
        settlement_reference=t.series.settlement_reference,
        authority_reference="MCXA-"+sha256(canonical_bytes(target_record(t))).hexdigest(),
        exchange_evidence_reference="MCXE-"+sha256(canonical_bytes(t.endpoint.source_provenance)).hexdigest())


class ThetaTargetAuthorityAdapter:
    def __init__(self, owner, *, methodology_reference=None, methodology_instructions=None):
        self.owner = owner
        self.methodology_reference = methodology_reference
        self.methodology_instructions = methodology_instructions

    def resolve_targets(self, subjects, at):
        try:
            check(type(subjects) is tuple and subjects and len(set(subjects)) == len(subjects))
            return tuple(target for subject in subjects for target in self.owner.resolve(subject, at))
        except (OptionAuthorityError, ValueError, KeyError, TypeError):
            raise ThetaError("THETA_TARGET_AUTHORITY_UNAVAILABLE") from None

    def v3_inputs(self, subject, at):
        """Public target binding for the qualified V3 contract, without commissioning it."""
        resolved = self.resolve_targets((subject,), at)
        require(all(t.owner_qualified for t in resolved), "THETA_TARGET_OWNER_QUALIFICATION_REQUIRED")
        return {"target_authority": self.owner.descriptor,
                "targets": {t.horizon: {**asdict(expiry_target(t)), "price_unit": t.series.quotation_unit}
                            for t in resolved},
                "authority_valid_through": min(t.valid_through for t in resolved).isoformat()}

    def __call__(self, subjects, at):
        resolved = self.resolve_targets(subjects, at)
        require(all(t.owner_qualified for t in resolved), "THETA_TARGET_OWNER_QUALIFICATION_REQUIRED")
        require(bool(self.methodology_reference) and bool(self.methodology_instructions),
                "THETA_METHODOLOGY_UNAVAILABLE")
        targets = tuple(expiry_target(t) for t in resolved)
        # Keep the retained V1/V2 ExpiryTarget shape and all V3 contracts intact.
        # Exact units/series/session are bound by immutable authority references
        # and also rendered as factual target definitions, not a new methodology.
        definitions = "\n".join(f"{t.series.family} {t.horizon}: {t.series.identity}; "
            f"quotation {t.series.quotation_unit}; terminal = exact underlying future's daily settlement "
            f"on option expiry {t.series.expiry}, NOT futures-expiry DDR, LTP or OHLC close."
            for t in resolved)
        return AuthorityBundle(targets, max(t.valid_from for t in resolved).isoformat(),
            min(t.valid_through for t in resolved).isoformat(), self.methodology_reference,
            self.methodology_instructions+"\n\nOwner-bound factual target definitions:\n"+definitions)
