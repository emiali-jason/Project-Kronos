"""WO-06D read-only adapter over the original Probables/WO-06C stores."""
from pathlib import Path
import os
from uuid import uuid4
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.population_measurement import MeasurementPopulation
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2 import ProbablesV2Error


class IntradayPopulationMeasurement:
    def __init__(self, store: ProbablesV2Store):
        if type(store) is not ProbablesV2Store:
            raise ProbablesV2Error("MEASUREMENT_STORE_INVALID")
        self.store = store

    def population(self, run_identity: str) -> MeasurementPopulation:
        run = self.store.load_run(run_identity)
        self.store._verify_run_lineage(run)
        mappings = tuple(self.store.load_mapping(r.source_mapping_identity)
            for r in run.results if r.source_mapping_identity is not None)
        source = NativeDiscoveryStore(self.store.root / "discovery-v2")
        discovery = (source.load_run(run_identity=run.source_discovery_run_identity)
            if source.run_path(run.source_discovery_run_identity).is_file() else None)
        return MeasurementPopulation(run, mappings, self.store.load_assessment_observations(run_identity), discovery)

    def history(self) -> tuple[MeasurementPopulation, ...]:
        values = tuple(self.population(p.stem) for p in
            sorted((self.store.root / "probables-v2" / "runs").glob("*.json")))
        return tuple(sorted(values, key=lambda p:(p.run.analysis_boundary, p.run.run_identity)))

    def current(self) -> MeasurementPopulation | None:
        pointer = self.store.load_current()
        return None if pointer is None else self.population(pointer.run_identity)


class PopulationMeasurementStore:
    """Optional immutable derived snapshots. Never changes a producer/current pointer.

    No runtime wiring or automatic historical materialization. Operational snapshots
    are temporary; the future verified monthly finalization governs purge eligibility.
    """
    def __init__(self, root: Path):
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ProbablesV2Error("MEASUREMENT_STORE_INVALID")
        self.root = root

    def _path(self, run_identity: str) -> Path:
        if (not isinstance(run_identity, str) or not run_identity.startswith("INTRADAY-PROBABLES-V2-RUN-")
            or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in run_identity)):
            raise ProbablesV2Error("MEASUREMENT_PATH_INVALID")
        path = self.root / "population-measurement-v1" / (run_identity + ".json")
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ProbablesV2Error("MEASUREMENT_PATH_INVALID")
        return path

    def retain(self, population: MeasurementPopulation) -> Path:
        if type(population) is not MeasurementPopulation:
            raise ProbablesV2Error("MEASUREMENT_SOURCE_INVALID")
        path = self._path(population.run.run_identity)
        payload = population.encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # Established WO-05B/WO-B create-once publication pattern.
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ProbablesV2Error("MEASUREMENT_IMMUTABLE_CONFLICT")
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def load(self, run_identity: str) -> MeasurementPopulation:
        try:
            population = MeasurementPopulation.decode(self._path(run_identity).read_bytes())
        except OSError as error:
            raise ProbablesV2Error("MEASUREMENT_SOURCE_MISSING") from error
        if population.run.run_identity != run_identity:
            raise ProbablesV2Error("MEASUREMENT_SOURCE_BINDING_INVALID")
        return population
