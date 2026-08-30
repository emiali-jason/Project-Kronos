"""Fail-closed policy protocol and registry for future WO-10 family policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10PolicyBinding,
    Wo10ReasonCode,
    Wo10ReconciliationRequest,
    Wo10State,
    _reason_key,
    _text,
    reason_applies_to_family,
)
from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot


@dataclass(frozen=True, slots=True)
class Wo10PolicyDecision:
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    state: Wo10State
    reasons: tuple[Wo10ReasonCode, ...]

    def __post_init__(self) -> None:
        if (
            not _text(self.canonical_subject_identity)
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.state) is not Wo10State
            or not self.reasons
            or any(type(item) is not Wo10ReasonCode for item in self.reasons)
            or tuple(sorted(self.reasons, key=_reason_key)) != self.reasons
        ):
            raise Wo10ContractError("WO10_POLICY_DECISION_INVALID")


@runtime_checkable
class Wo10FamilyPolicy(Protocol):
    @property
    def binding(self) -> Wo10PolicyBinding:
        """Return the exact immutable family-policy publication binding."""

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        """Deterministically evaluate one bound candidate without side effects."""


class Wo10PolicyRegistry:
    """Exact-tuple registry with no default, cross-family, or latest fallback."""

    def __init__(self, policies: tuple[Wo10FamilyPolicy, ...]) -> None:
        entries: dict[
            tuple[str, str, str, str, IntradayMarketFamily],
            Wo10FamilyPolicy,
        ] = {}
        for policy in policies:
            if not isinstance(policy, Wo10FamilyPolicy):
                raise Wo10ContractError("WO10_POLICY_PROTOCOL_INVALID")
            binding = policy.binding
            if type(binding) is not Wo10PolicyBinding or binding.key in entries:
                raise Wo10ContractError("WO10_POLICY_REGISTRY_INVALID")
            entries[binding.key] = policy
        self._entries = entries

    def resolve(self, binding: Wo10PolicyBinding) -> Wo10FamilyPolicy:
        if type(binding) is not Wo10PolicyBinding:
            raise Wo10ContractError("WO10_POLICY_BINDING_INVALID")
        try:
            policy = self._entries[binding.key]
        except KeyError as error:
            raise Wo10ContractError("WO10_POLICY_UNKNOWN") from error
        if policy.binding != binding:
            raise Wo10ContractError("WO10_POLICY_BINDING_CONFLICT")
        return policy

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        if (
            type(request) is not Wo10ReconciliationRequest
            or type(evidence) is not Wo10EvidenceSnapshot
            or request.policy != evidence.policy
            or request.market_family is not evidence.market_family
        ):
            raise Wo10ContractError("WO10_POLICY_EVALUATION_BINDING_INVALID")
        policy = self.resolve(request.policy)
        decision = policy.evaluate(request=request, evidence=evidence)
        if (
            type(decision) is not Wo10PolicyDecision
            or decision.canonical_subject_identity
            != evidence.canonical_subject_identity
            or decision.inherited_direction is not evidence.inherited_direction
            or any(
                not reason_applies_to_family(item, evidence.market_family)
                for item in decision.reasons
            )
            or any(item.policy_identity != request.policy.policy_identity for item in decision.reasons)
        ):
            raise Wo10ContractError("WO10_POLICY_DECISION_BINDING_INVALID")
        return decision


__all__ = [
    "Wo10FamilyPolicy",
    "Wo10PolicyDecision",
    "Wo10PolicyRegistry",
]
