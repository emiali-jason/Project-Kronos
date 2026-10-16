"""Bounded historical evidence reads; no current analytical or trading authority."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import re

RUN = re.compile(r'INTRADAY-PROBABLES-V2-RUN-[A-Fa-f0-9]{64}\Z')
ASSESSMENT = re.compile(r'WO08-ASSESSMENT-[a-f0-9]{64}\Z')
READINESS = re.compile(r'INTRADAY-WO09-(?:EXPERIMENTAL-|MACHINE-READINESS-)[A-F0-9]{64}\Z')
FINGERPRINT = re.compile(r'[a-f0-9]{64}\Z')
CONTRACT = 'KRONOS-INTRADAY-LIMITED-MACHINE-HISTORY/1.0.0'


class MachineHistoryError(ValueError):
    def __init__(self, reason, status=503):
        super().__init__(reason)
        self.reason, self.status = reason, status


def _identity(pattern, value):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise MachineHistoryError('MACHINE_HISTORY_IDENTITY_INVALID', 400)
    return value


class IntradayMachineHistory:
    """Reads exact immutable populations; never current pointers or evaluators."""
    def __init__(self, *, assessments, probables, readiness, recent_attempts):
        from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
        from kronos.intraday.probables_v2_persistence import ProbablesV2Store
        from kronos.intraday.wo09_persistence import Wo09Store
        if (type(assessments) is not Wo08AssessmentStore
                or type(probables) is not ProbablesV2Store
                or type(readiness) is not Wo09Store or not callable(recent_attempts)):
            raise TypeError('MACHINE_HISTORY_DEPENDENCIES_REQUIRED')
        self.assessments, self.probables = assessments, probables
        self.readiness, self.recent_attempts = readiness, recent_attempts

    def recent(self):
        try:
            entries = tuple(self.recent_attempts())
            if len(entries) > 5 or any(type(x) is not dict for x in entries):
                raise ValueError('RECENT_ANALYSIS_BOUND_INVALID')
            return dict(entries=entries, unavailable=None)
        except FileNotFoundError:
            return dict(entries=(), unavailable='RECENT_ANALYSIS_EVIDENCE_MISSING')
        except (ValueError, TypeError, KeyError):
            return dict(entries=(), unavailable='RECENT_ANALYSIS_EVIDENCE_INVALID')
        except OSError:
            return dict(entries=(), unavailable='RECENT_ANALYSIS_STORAGE_UNAVAILABLE')

    def page(self, *, run=None, page=1, page_size=25, population=None,
             assessment=None, readiness=None):
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 50:
            raise MachineHistoryError('MACHINE_HISTORY_PAGE_INVALID', 400)
        if (assessment is None) != (readiness is None):
            raise MachineHistoryError('MACHINE_HISTORY_EXACT_JOIN_PAIR_REQUIRED', 400)
        if population is not None:
            _identity(FINGERPRINT, population)
        if run is None and (page != 1 or population is not None or assessment is not None):
            raise MachineHistoryError('MACHINE_HISTORY_RUN_REQUIRED', 400)
        recent = self.recent()
        document = dict(contract=CONTRACT, history_only=True, new_work_authority='NONE',
            scope='RECENT_FIVE_AND_EXACT_SELECTED_RUN_ONLY', recent=recent,
            run_identity=run, rows=(), total=None, page=page, page_size=page_size,
            population=None, readiness_detail=None, readiness_http_status=200)
        if run is None:
            return document
        _identity(RUN, run)
        if page > 1 and population is None:
            raise MachineHistoryError('MACHINE_HISTORY_POPULATION_REQUIRED', 400)
        if assessment is not None:
            _identity(ASSESSMENT, assessment)
            _identity(READINESS, readiness)
        try:
            # Existing scope encloses only its own owner's complete-run read.
            # Release before another owner's read; no cross-store/global lock.
            with self.assessments.page_read_scope():
                records = self.assessments.load_run(run)
            companion = self.probables.load_assessment_observations(run)
        except FileNotFoundError as error:
            raise MachineHistoryError('MACHINE_HISTORY_SELECTED_RUN_EVIDENCE_MISSING', 404) from error
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            # Existing schema dispatch may call .get on non-object JSON.
            raise MachineHistoryError('MACHINE_HISTORY_SELECTED_RUN_INVALID', 422) from error
        except OSError as error:
            raise MachineHistoryError('MACHINE_HISTORY_STORAGE_UNAVAILABLE') from error
        if len(records) != 98:
            raise MachineHistoryError('MACHINE_HISTORY_COMPLETE_POPULATION_REQUIRED', 422)
        # Response-position fingerprint, not a persisted manifest or authority token.
        fingerprint = sha256(json.dumps(dict(contract=CONTRACT, run=run, page_size=page_size,
            assessments=[(r.identity, sha256(r.payload).hexdigest()) for r in records],
            price_companion=None if companion is None else (companion.evidence_identity, companion.integrity_identity)),
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if population is not None and population != fingerprint:
            raise MachineHistoryError('MACHINE_HISTORY_POPULATION_CHANGED', 409)
        start = (page - 1) * page_size
        if start >= len(records):
            raise MachineHistoryError('MACHINE_HISTORY_PAGE_OUT_OF_RANGE', 400)
        prices = {} if companion is None else {p.admission_identity: p for p in companion.observations}
        rows = []
        for record in records[start:start + page_size]:
            d = record.data
            price = prices.get(d['probable_result_identity'])
            if price is not None and (price.run_identity != run
                    or price.canonical_subject_identity != d['subject']
                    or price.market_session_identity != d['session_identity']
                    or price.direction != d['direction']):
                raise MachineHistoryError('MACHINE_HISTORY_PRICE_BINDING_INVALID', 422)
            rows.append(dict(identity=record.identity, integrity=record.integrity,
                **{k: d.get(k) for k in ('subject', 'direction', 'market_family', 'session_identity',
                    'analysis_boundary', 'exact_mcx_contract_identity', 'exact_mcx_roll_lineage',
                    'probables_state', 'disposition', 'criteria', 'hard_gate')},
                assessment_price=None if price is None or price.assessment_price is None else str(price.assessment_price),
                assessment_price_time=None if price is None or price.assessment_time is None else price.assessment_time.isoformat(),
                assessment_price_source=None if price is None else price.assessment_source_identity,
                assessment_price_evidence='ASSESSMENT_PRICE_NOT_RETAINED' if price is None else price.classification.value,
                original_readiness='ORIGINAL_READINESS_NOT_LINKED'))
        detail = None
        status = 200
        if readiness is not None:
            selected = next((r for r in records if r.identity == assessment), None)
            if selected is None:
                raise MachineHistoryError('MACHINE_HISTORY_ASSESSMENT_NOT_IN_RUN', 422)
            detail, status = self._readiness(readiness, selected)
        return dict(document, rows=tuple(rows), total=len(records), population=fingerprint,
            readiness_detail=detail, readiness_http_status=status,
            selected_outside_recent_five=run not in {x.get('run_identity') for x in recent['entries']})

    def _readiness(self, identity, assessment):
        from kronos.intraday.wo09_persistence import Wo09PersistenceError
        try:
            record = self.readiness.load_readiness(identity)
        except FileNotFoundError:
            return dict(identity=identity, state='EXACT_READINESS_EVIDENCE_MISSING'), 200
        except Wo09PersistenceError as error:
            if str(error) == 'EXPERIMENTAL_FIRST_FIVE_NOT_RETAINED':
                # Existing public reader conflates absent and unequal proof.
                # Do not label either as missing or expose an unverified record.
                return dict(identity=identity,
                    state='EXACT_READINESS_REQUIRED_PROOF_NOT_ESTABLISHED',
                    limitation='Required proof absent or differs from embedded proof; existing reader does not distinguish.',
                    new_work_authority='NONE'), 200
            return dict(identity=identity, state='EXACT_READINESS_EVIDENCE_INVALID'), 422
        except (ValueError, TypeError, KeyError):
            return dict(identity=identity, state='EXACT_READINESS_EVIDENCE_INVALID'), 422
        except OSError:
            return dict(identity=identity, state='EXACT_READINESS_STORAGE_UNAVAILABLE'), 503
        d = assessment.data
        expected = dict(source_authority='WO08', wo08_identity=assessment.identity,
            wo08_integrity=assessment.integrity, probables_run_identity=d['run_identity'],
            probable_result_identity=d['probable_result_identity'], canonical_subject_identity=d['subject'],
            market_family=d['market_family'], direction=d['direction'] or 'UNAVAILABLE',
            session_identity=d['session_identity'], exact_mcx_contract_identity=d.get('exact_mcx_contract_identity'),
            exact_mcx_roll_lineage=d.get('exact_mcx_roll_lineage'),
            methodology_identity=d['methodology_identity'], methodology_version=d['methodology_version'],
            methodology_checksum=d['methodology_checksum'])
        if (any(getattr(record, k, None) != v for k, v in expected.items())
                or record.analysis_boundary != datetime.fromisoformat(d['analysis_boundary'])
                or (getattr(record, 'assessment_document', None) is not None
                    and record.assessment_document != d)):
            return dict(identity=identity, state='EXACT_READINESS_LINEAGE_MISMATCH'), 422
        values = asdict(record)
        keep = ('readiness_identity', 'integrity_identity', 'canonical_subject_identity',
            'direction', 'session_identity', 'exact_mcx_contract_identity', 'exact_mcx_roll_lineage',
            'wo08_identity', 'wo08_integrity', 'probables_run_identity', 'probable_result_identity',
            'criteria', 'satisfied_count', 'outstanding_count', 'readiness_state', 'currentness',
            'created_at', 'first_five_document', 'source_authority', 'authority')
        return dict(identity=identity, state='VALIDATED_EXACT_HISTORICAL_READINESS',
            original={k: values[k] for k in keep if k in values}, new_work_authority='NONE'), 200
