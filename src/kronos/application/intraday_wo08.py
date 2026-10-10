"""Prospective production WO08 publication inside normal Analysis only.

No Provider, Review, Answer, WO07F or research authority is consumed. Exceptions
from source validation or persistence propagate to the owning publication gate.
"""
import json
from kronos.intraday.wo08_assessment import assess
from kronos.intraday.wo08_assessment_store import validate_run
from kronos.intraday.native_pullback_decision import load_decision_source
from kronos.intraday.native_pullback_policy import CHECKSUM as NATIVE_CHECKSUM


class Wo08Publication:
    def __init__(self, store):
        self.store = store

    def publish_run(self, *, run, mapping, native_publication, published_at, newly_published=True):
        if type(newly_published) is not bool:
            raise ValueError('WO08_PUBLICATION_MODE_INVALID')
        if not newly_published:
            return ()
        validate_run(run)
        expected = self.store.current_pointer()
        # Explicit duplicate calls read retained evidence; never republish an old
        # run or change its creation time/currentness on restart.
        try:
            existing = self.store._io._read(self.store._manifest_path(run.run_identity))
        except FileNotFoundError:
            existing = None
        if existing is not None:
            records = self.store.load_run(run.run_identity)
            if any(r.data['run_integrity'] != run.integrity_identity for r in records):
                raise ValueError('WO08_RUN_INTEGRITY_MISMATCH')
            return records
        mappings = tuple(mapping.member_evidence) if hasattr(mapping, 'member_evidence') else tuple(mapping)
        by_mapping = {m.mapping_identity: m for m in mappings}
        required = {r.source_mapping_identity for r in run.results if r.source_mapping_identity is not None}
        if len(by_mapping) != len(mappings) or set(by_mapping) != required:
            raise ValueError('WO08_MAPPING_POPULATION_INVALID')
        if native_publication is None:
            raise ValueError('WO08_NATIVE_COMPANION_UNAVAILABLE')
        companion_path = native_publication.store.root / 'runs' / (run.run_identity + '.json')
        # Native currently has no safe JSON reader. Reuse the existing pinned,
        # no-follow directory/file primitive; do not follow a substituted link.
        companion = json.loads(self.store._io._read(companion_path))
        expected_results = [r.result_identity for r in run.results if r.source_mapping_identity is not None]
        if (companion.get('run_identity') != run.run_identity or companion.get('result_identities') != expected_results
                or companion.get('policy_checksum') != NATIVE_CHECKSUM
                or len(companion.get('selections', [])) != len(expected_results)
                or len(set(companion['selections'])) != len(expected_results)):
            raise ValueError('WO08_NATIVE_COMPANION_INCOMPLETE')
        native_by_result = {}
        for result_id, identity in zip(companion['result_identities'], companion['selections']):
            native = native_publication.store.load(identity)
            load_decision_source(native_publication.store, native, None)
            if (native.data['probable_result_identity'] != result_id or native.data['analysis_cycle'] != run.run_identity
                    or native_publication.store.bound_identity(native.data['machine_identity']) != identity):
                raise ValueError('WO08_NATIVE_COMPANION_LINEAGE_INVALID')
            native_by_result[result_id] = native
        records = tuple(assess(run_identity=run.run_identity, run_integrity=run.integrity_identity,
            result=result, mapping=by_mapping.get(result.source_mapping_identity),
            native=native_by_result.get(result.result_identity), created_at=published_at) for result in run.results)
        return self.store.publish(run, records, expected_pointer=expected)
