"""WO-06D: immutable downstream populations; no admission or outcome authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Iterable

from kronos.intraday.assessment_observation import (
    AssessmentPriceAuthority, ProbablesAssessmentObservations,
    create_missing_assessment_observations, validate_assessment_run,
)
from kronos.intraday.discovery import NativeDiscoveryRun
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2, ProbablesRunV2, ProbablesV2Error,
)
from kronos.intraday.probables_v2_persistence import _artifact_bytes, _artifact_from_bytes

SCHEMA = "KRONOS-INTRADAY-POPULATION-MEASUREMENT-V1"
EPISODE_POLICY = "WO06D-PROPOSED-CONTIGUOUS-SESSION-DIRECTION-V1"
ADMITTED = frozenset((ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE))


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class MeasurementPopulation:
    """Original run/mappings and WO-06C pair, never recomputed under new policy."""
    run: ProbablesRunV2
    mappings: tuple[DiscoveryProbablesEvidenceV2, ...]
    assessment: ProbablesAssessmentObservations | None
    discovery: NativeDiscoveryRun | None = None

    def __post_init__(self):
        if type(self.run) is not ProbablesRunV2 or type(self.mappings) is not tuple:
            raise ProbablesV2Error("MEASUREMENT_SOURCE_INVALID")
        # Deserialize existing contracts to recursively check source integrity.
        _artifact_from_bytes(_artifact_bytes(self.run))
        for item in self.mappings:
            if type(item) is not DiscoveryProbablesEvidenceV2:
                raise ProbablesV2Error("MEASUREMENT_SOURCE_INVALID")
            _artifact_from_bytes(_artifact_bytes(item))
        object.__setattr__(self, "mappings", tuple(sorted(self.mappings, key=lambda m: m.mapping_identity)))
        mapped = {m.mapping_identity: m for m in self.mappings}
        required = {r.source_mapping_identity for r in self.run.results if r.source_mapping_identity}
        if len(mapped) != len(self.mappings) or set(mapped) != required:
            raise ProbablesV2Error("MEASUREMENT_SOURCE_MEMBERSHIP_INVALID")
        if len({r.canonical_subject_identity for r in self.run.results}) != len(self.run.results):
            raise ProbablesV2Error("MEASUREMENT_SUBJECT_DUPLICATE")
        for result in self.run.results:
            if result.source_mapping_identity is None:
                continue
            mapping = mapped[result.source_mapping_identity]
            pairs = (
                ("canonical_subject_identity", "canonical_subject_identity"),
                ("universe_member_identity", "universe_member_identity"),
                ("source_discovery_run_identity", "source_discovery_run_identity"),
                ("source_discovery_member_identity", "source_discovery_member_identity"),
                ("analysis_boundary", "analysis_boundary"), ("phase", "phase"),
                ("market_session_identity", "market_session_identity"),
                ("methodology_publication_identity", "methodology_publication_identity"),
            )
            if any(getattr(result, a) != getattr(mapping, b) for a, b in pairs) or (
                result.completed_evidence_selection_identity != mapping.completed_evidence.selection_identity
                or result.semantic_evidence_identity != mapping.semantic_evidence.evidence_identity
            ):
                raise ProbablesV2Error("MEASUREMENT_SOURCE_BINDING_INVALID")
        if self.discovery is not None:
            if type(self.discovery) is not NativeDiscoveryRun:
                raise ProbablesV2Error("MEASUREMENT_DISCOVERY_INVALID")
            _artifact_from_bytes(_artifact_bytes(self.discovery))
            if (self.discovery.run_identity != self.run.source_discovery_run_identity
                or self.discovery.observation_boundary != self.run.analysis_boundary
                or {r.universe_member_identity for r in self.discovery.results}
                   != {r.universe_member_identity for r in self.run.results}):
                raise ProbablesV2Error("MEASUREMENT_DISCOVERY_BINDING_INVALID")
        if self.assessment is not None:
            _artifact_from_bytes(_artifact_bytes(self.assessment))
            validate_assessment_run(self.assessment, self.run)
        actual = [sum(r.state is state for r in self.run.results) for state in ProbableState]
        d = self.run.diagnostics
        if actual != [d.long_probables, d.short_probables, d.not_admitted_count, d.unavailable_count]:
            raise ProbablesV2Error("MEASUREMENT_DENOMINATOR_INVALID")

    @property
    def observations(self):
        # Legacy absence remains a missing projection, never a persisted backfill.
        return (self.assessment or create_missing_assessment_observations(self.run)).observations

    @property
    def observation_identities(self) -> tuple[str, ...]:
        return tuple(identity("INTRADAY-ADMISSION-OBSERVATION-", [
            SCHEMA, item.run_identity, item.admission_identity,
        ]) for item in self.observations)

    @property
    def denominators(self) -> dict[str, int | str]:
        d = self.run.diagnostics
        return dict(governed_population=d.starting_population,
            probables_evaluable=d.evaluable_count, probables_unavailable=d.unavailable_count,
            admission_evaluated=sum(r.source_mapping_identity is not None for r in self.run.results),
            admitted=d.total_probables, not_admitted=d.not_admitted_count,
            missing_measurement=sum(o.classification is AssessmentPriceAuthority.PRICE_NOT_RETAINED
                                    for o in self.observations),
            discovery_factually_evaluable=("NOT_RETAINED" if self.discovery is None else self.discovery.accounting.factually_evaluable),
            discovery_unavailable_failed=("NOT_RETAINED" if self.discovery is None else
                self.discovery.accounting.universe_members-self.discovery.accounting.factually_evaluable),
            reviewed="DOWNSTREAM_EVIDENCE_NOT_JOINED", not_reviewed="NOT_ESTABLISHED",
            rejected_later="DOWNSTREAM_EVIDENCE_NOT_JOINED",
            promoted_later="DOWNSTREAM_EVIDENCE_NOT_JOINED",
            traded_later="DOWNSTREAM_EVIDENCE_NOT_JOINED", not_traded="NOT_ESTABLISHED")

    def admission_records(self) -> tuple[dict, ...]:
        """Explicit projection fields; original capture/selection bytes remain above."""
        mappings = {m.mapping_identity: m for m in self.mappings}
        results = {r.result_identity: r for r in self.run.results}
        rows = []
        for observation, observation_id in zip(self.observations, self.observation_identities):
            mapping = mappings[observation.source_mapping_identity]
            selection = mapping.completed_evidence
            dates = {c.candle.candle_start.date().isoformat() for c in selection.selected_candles
                     if c.original_market_session_identity == selection.current_market_session_identity}
            proof = observation.proof
            rows.append(dict(observation_identity=observation_id,
                canonical_subject_identity=observation.canonical_subject_identity,
                direction=observation.direction, phase=observation.phase,
                market_session_identity=observation.market_session_identity,
                trading_date=next(iter(dates)) if len(dates) == 1 else "NOT_RETAINED",
                run_identity=self.run.run_identity, admission_identity=observation.admission_identity,
                methodology_version=observation.methodology_version,
                analysis_boundary=observation.analysis_boundary.isoformat(),
                assessment_authority=observation.classification.value,
                assessment_price=None if observation.assessment_price is None else str(observation.assessment_price),
                assessment_time=None if observation.assessment_time is None else observation.assessment_time.isoformat(),
                assessment_source_identity=observation.assessment_source_identity,
                assessment_observation_identity=getattr(proof, "observation_identity", None),
                assessment_companion_identity=None if self.assessment is None else self.assessment.evidence_identity,
                run_integrity=self.run.integrity_identity,
                source_mapping_identity=mapping.mapping_identity,
                source_integrity=mapping.integrity_identity,
                publication_identity=self.run.run_identity,
                publication_timestamp="NOT_RETAINED",
                admission_reasons=[r.value for r in results[observation.admission_identity].reasons],
                narrow_cpr_qualified=mapping.semantic_evidence.narrow_cpr_qualified,
                semantic_features=[dict(family=f.family, direction=f.direction.value,
                    availability=f.availability, role=f.evidence_role.value,
                    attributes=dict(f.attributes), identity=f.fact_identity,
                    retention="EXACTLY_RETAINED") for f in mapping.semantic_evidence.facts],
                opening_identity=None if mapping.opening_semantic is None else mapping.opening_semantic.evidence_identity,
                nifty_identity=None if mapping.nifty_relative is None else mapping.nifty_relative.evidence_identity))
        return tuple(rows)

    def document(self) -> dict:
        return dict(schema=SCHEMA, authority="DERIVED_POPULATION_NO_TRADING_AUTHORITY",
            retention="TEMPORARY_OPERATIONAL_EVIDENCE",
            run=json.loads(_artifact_bytes(self.run)),
            mappings=[json.loads(_artifact_bytes(m)) for m in sorted(self.mappings, key=lambda m:m.mapping_identity)],
            assessment=None if self.assessment is None else json.loads(_artifact_bytes(self.assessment)),
            discovery=None if self.discovery is None else json.loads(_artifact_bytes(self.discovery)))

    @property
    def measurement_identity(self) -> str:
        return identity("INTRADAY-POPULATION-MEASUREMENT-", self.document())

    def encode(self) -> bytes:
        return canonical(dict(identity=self.measurement_identity, population=self.document())) + b"\n"

    @classmethod
    def decode(cls, payload: bytes):
        try:
            doc = json.loads(payload)
            source = doc["population"]
            value = cls(_artifact_from_bytes(canonical(source["run"])),
                tuple(_artifact_from_bytes(canonical(m)) for m in source["mappings"]),
                None if source["assessment"] is None else _artifact_from_bytes(canonical(source["assessment"])),
                None if source["discovery"] is None else _artifact_from_bytes(canonical(source["discovery"])))
            if doc != dict(identity=value.measurement_identity, population=value.document()):
                raise ValueError
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise ProbablesV2Error("MEASUREMENT_ARTIFACT_INVALID") from error

    def population_slice(self):
        observations = dict(zip((o.admission_identity for o in self.observations), self.observation_identities))
        return PopulationSlice(self.run.run_identity, self.run.analysis_boundary, tuple(
            PopulationMember(r.canonical_subject_identity, r.market_session_identity, r.state.value,
                None if r.direction is None else r.direction.value,
                None if r.phase is None else r.phase.value, observations.get(r.result_identity))
            for r in self.run.results))


@dataclass(frozen=True)
class PopulationMember:
    subject: str
    session: str
    state: str
    direction: str | None
    phase: str | None
    observation_identity: str | None

    def __post_init__(self):
        if not isinstance(self.subject, str) or not self.subject or not isinstance(self.session, str) or not self.session or self.state not in {s.value for s in ProbableState}:
            raise ProbablesV2Error("MEASUREMENT_MEMBER_INVALID")
        admitted = self.state in {s.value for s in ADMITTED}
        if admitted and (self.direction not in {"LONG", "SHORT"} or not self.phase or not self.observation_identity):
            raise ProbablesV2Error("MEASUREMENT_MEMBER_INVALID")
        if admitted and self.state != self.direction + "_PROBABLE":
            raise ProbablesV2Error("MEASUREMENT_DIRECTION_INVALID")
        if not admitted and self.observation_identity is not None:
            raise ProbablesV2Error("MEASUREMENT_NON_ADMISSION_HAS_OBSERVATION")


@dataclass(frozen=True)
class PopulationSlice:
    run_identity: str
    analysis_boundary: datetime
    members: tuple[PopulationMember, ...]

    def __post_init__(self):
        if (not self.run_identity or type(self.analysis_boundary) is not datetime or self.analysis_boundary.tzinfo is None
            or type(self.members) is not tuple or not self.members
            or any(type(m) is not PopulationMember for m in self.members)
            or len({m.subject for m in self.members}) != len(self.members)):
            raise ProbablesV2Error("MEASUREMENT_POPULATION_INVALID")


@dataclass(frozen=True)
class PopulationTransition:
    run_identity: str
    subject: str
    session: str
    states: tuple[str, ...]
    observation_identity: str | None
    previous_observation_identity: str | None
    episode_identity: str | None


def longitudinal_population(populations: Iterable[PopulationSlice]) -> tuple[PopulationTransition, ...]:
    """Proposed research grouping only; never independence, admission or trade truth.

    Input order is irrelevant. Equal-time distinct runs are ambiguous and rejected.
    Coverage changes reject; unavailable is absence from admissions, not a loss.
    """
    unique = {}
    for population in populations:
        if type(population) is not PopulationSlice:
            raise ProbablesV2Error("MEASUREMENT_POPULATION_INVALID")
        prior = unique.get(population.run_identity)
        if prior is not None and prior != population:
            raise ProbablesV2Error("MEASUREMENT_RUN_CONFLICT")
        unique[population.run_identity] = population
    runs = sorted(unique.values(), key=lambda p:(p.analysis_boundary, p.run_identity))
    if len({p.analysis_boundary for p in runs}) != len(runs):
        raise ProbablesV2Error("MEASUREMENT_ORDER_AMBIGUOUS")
    if runs and any({m.subject for m in p.members} != {m.subject for m in runs[0].members} for p in runs):
        raise ProbablesV2Error("MEASUREMENT_COVERAGE_CHANGED")
    previous = {}; seen = set(); episodes = {}; transitions = []
    for population in runs:
        current = {}
        for member in sorted(population.members, key=lambda m:m.subject):
            prior = previous.get(member.subject)
            same_session = prior is not None and prior.session == member.session
            was_admitted = same_session and prior.observation_identity is not None
            states = []
            episode = None
            if member.observation_identity is not None:
                key = (member.session, member.subject)
                if was_admitted:
                    if prior.direction != member.direction:
                        states.append("DIRECTION_CHANGED")
                    else:
                        states.append("PERSISTED")
                        episode = episodes[member.subject]
                    if prior.phase != member.phase:
                        states.append("PHASE_CHANGED")
                else:
                    states.append("REENTERED" if key in seen else "NEW_ADMISSION")
                    if prior is not None and not same_session:
                        states.append("SESSION_CHANGED")
                if episode is None:
                    episode = identity("INTRADAY-RESEARCH-EPISODE-PROPOSAL-", [
                        EPISODE_POLICY, member.session, member.subject, member.direction, member.observation_identity])
                seen.add(key)
            elif was_admitted:
                states.append("DISAPPEARED")
            else:
                states.append("NOT_ADMITTED" if member.state == "NOT_ADMITTED" else "UNAVAILABLE")
            transitions.append(PopulationTransition(population.run_identity, member.subject,
                member.session, tuple(states), member.observation_identity,
                None if not same_session else prior.observation_identity, episode))
            current[member.subject] = member
            episodes[member.subject] = episode
        previous = current
    return tuple(transitions)
