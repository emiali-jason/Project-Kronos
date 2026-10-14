"""Opt-in external Swing Analyst timing sidecar. No KRONOS application imports.

This records public operation boundaries, never reasoning, output, argv or secrets.
It performs no analytical/currentness verification and grants no workflow authority.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from time import monotonic_ns
from uuid import uuid4

PHASES = tuple(f'M{i:02d}' for i in range(1, 18))
SCHEMA = 'KRONOS-SWING-ANALYST-DIAGNOSTIC-TIMING-V1'
HASH = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z')

class MeasurementError(ValueError):
    pass

def require(value, code='DIAGNOSTIC_EVIDENCE_INVALID'):
    if not value:
        raise MeasurementError(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode() + b'\n'

def digest(value):
    return sha256(canonical(value)).hexdigest()

def object_pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'DIAGNOSTIC_DUPLICATE_KEY')
        value[key] = item
    return value

def read_json(path):
    data = path.read_bytes()
    require(len(data) <= 1024 * 1024)
    try:
        return json.loads(data, object_pairs_hook=object_pairs,
                          parse_constant=lambda _: require(False))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise MeasurementError('DIAGNOSTIC_JSON_INVALID') from error

def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected))

def identity(value):
    require(type(value) is str and ID.fullmatch(value))

def hashed(value, nullable=False):
    require(nullable and value is None or type(value) is str and HASH.fullmatch(value))

def stamp(value):
    require(type(value) is str)
    try:
        result = datetime.fromisoformat(value)
        require(result.tzinfo is not None and result.utcoffset() is not None)
        return result
    except ValueError as error:
        raise MeasurementError('DIAGNOSTIC_TIME_INVALID') from error

def safe_path(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'DIAGNOSTIC_PATH_INVALID')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'DIAGNOSTIC_SYMLINK')
    forbidden = ('/Library/Application Support/KRONOS', '/Library/Application Support/Project-KRONOS',
                 '/Applications/KRONOS.app', '/KRONOS REVIEW PACK')
    require(not any(x.casefold() in str(path).casefold() for x in forbidden), 'DIAGNOSTIC_PRODUCTION_ROOT_DENIED')
    return path

def validate_binding(value):
    keys(value, ('execution_identity','pack_identity','pack_sha256','pack_bytes','candidates'))
    identity(value['execution_identity']);identity(value['pack_identity']);hashed(value['pack_sha256'])
    require(type(value['pack_bytes']) is int and value['pack_bytes'] > 0)
    require(type(value['candidates']) is list and 1 <= len(value['candidates']) <= 100)
    seen = set()
    for candidate in value['candidates']:
        keys(candidate, ('candidate_identity','instrument','charts'))
        identity(candidate['candidate_identity']);identity(candidate['instrument'])
        require(candidate['candidate_identity'] not in seen);seen.add(candidate['candidate_identity'])
        require(type(candidate['charts']) is list and 1 <= len(candidate['charts']) <= 8)
        rows = set()
        for chart in candidate['charts']:
            keys(chart, ('leg','timeframe','request_identity','subject_identity','revision_identity','chart_sha256'))
            require(chart['leg'] in ('NATIVE','SUPPORTING_REFERENCE'))
            require(chart['timeframe'] in ('1W','1D','4H','1H'))
            pair=(chart['leg'],chart['timeframe']);require(pair not in rows);rows.add(pair)
            for k in ('request_identity','subject_identity','revision_identity'):identity(chart[k])
            hashed(chart['chart_sha256'])
    return value

def validate_attribution(binding, phase, candidate, timeframe, leg):
    require(phase in PHASES)
    if candidate is None:
        require(timeframe is None and leg is None)
    else:
        row = next((x for x in binding['candidates'] if x['candidate_identity']==candidate),None)
        require(row is not None, 'DIAGNOSTIC_CANDIDATE_MISMATCH')
        if timeframe is None:
            require(leg is None)
        else:
            require(any(x['timeframe']==timeframe and x['leg']==leg for x in row['charts']),
                    'DIAGNOSTIC_CHART_MISMATCH')
    require(phase!='M07' or candidate is not None)
    require(phase!='M08' or timeframe is not None)
    require(phase not in ('M01','M02','M03','M17') or candidate is None)


def publish(path, value):
    """Exclusive immutable publication; caller holds the run lock for events."""
    path=safe_path(path);data=canonical(value)
    if path.exists():
        require(path.read_bytes()==data,'DIAGNOSTIC_REPLAY_CONFLICT')
        return sha256(data).hexdigest()
    fd,name=tempfile.mkstemp(prefix='.timing-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),0o600);f.write(data);f.flush();os.fsync(f.fileno())
        try:
            os.link(name,path)
        except FileExistsError:
            require(path.read_bytes()==data,'DIAGNOSTIC_REPLAY_CONFLICT')
        d=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:
        Path(name).unlink(missing_ok=True)
    return sha256(data).hexdigest()

class Meter:
    def __init__(self, root, *, clock=monotonic_ns, wall=None):
        self.root=safe_path(root)
        self.manifest=read_json(safe_path(self.root/'manifest.json'))
        keys(self.manifest, ('schema','authority','binding','binding_sha256'))
        require(self.manifest['schema']==SCHEMA and self.manifest['authority']=='DIAGNOSTIC_ONLY')
        self.binding=validate_binding(self.manifest['binding'])
        require(self.manifest['binding_sha256']==digest(self.binding))
        self.clock=clock;self.wall=wall or (lambda:datetime.now(UTC).isoformat())
        self.domain=uuid4().hex

    @classmethod
    def create(cls, root, binding, question_pdf, **kwargs):
        root=safe_path(root);question_pdf=safe_path(question_pdf)
        validate_binding(binding)
        data=question_pdf.read_bytes()
        require(len(data)==binding['pack_bytes'] and sha256(data).hexdigest()==binding['pack_sha256'],
                'DIAGNOSTIC_PACK_MISMATCH')
        root.mkdir(mode=0o700)  # no reuse, replacement or implicit parent creation
        (root/'events').mkdir(mode=0o700)
        with (root/'lock').open('xb') as f:os.fchmod(f.fileno(),0o600)
        publish(root/'manifest.json',dict(schema=SCHEMA,authority='DIAGNOSTIC_ONLY',
                                        binding=binding,binding_sha256=digest(binding)))
        return cls(root,**kwargs)

    def events(self, extra=None):
        with safe_path(self.root/'lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_SH)
            return self._events(extra)

    def _events(self, extra=None):
        directory=safe_path(self.root/'events');paths=sorted(directory.iterdir())
        require(all(p.suffix=='.json' and not p.is_symlink() for p in paths),'DIAGNOSTIC_INCOMPLETE_PUBLICATION')
        result=[];starts={};ended=set()
        allowed=('sequence','binding_sha256','phase','candidate','timeframe','leg','kind','start_identity',
                 'clock_domain','start_ns','end_ns','elapsed_ns','wall_start','wall_end','method',
                 'outcome','failure_code','retry_of','operation_identity_sha256','result_sha256',
                 'source_receipt_sha256','retried','integrity_sha256')
        values=[(p.name,read_json(p)) for p in paths]
        if extra is not None:
            values.append((f'{len(paths)+1:06d}-{extra["integrity_sha256"]}.json',extra))
        for number,(filename,e) in enumerate(values,1):
            keys(e,allowed)
            checksum=e['integrity_sha256'];v={k:x for k,x in e.items() if k!='integrity_sha256'}
            require(checksum==digest(v) and filename==f'{number:06d}-{checksum}.json')
            require(e['sequence']==number and e['binding_sha256']==self.manifest['binding_sha256'])
            validate_attribution(self.binding,e['phase'],e['candidate'],e['timeframe'],e['leg'])
            require(e['kind'] in ('START','END','DERIVED'))
            require(e['method'] in ('DIRECT_MONOTONIC','DERIVED_PUBLIC_RECEIPT'))
            require(e['outcome'] in ('STARTED','SUCCEEDED','FAILED'))
            require(e['failure_code'] in (None,'PROCESS_EXIT_NONZERO','OPERATION_EXCEPTION','VALIDATION_REJECTED','JSON_DECODE_ERROR'))
            require((e['outcome']=='FAILED') == (e['failure_code'] is not None))
            for k in ('operation_identity_sha256','result_sha256','source_receipt_sha256','retry_of'):hashed(e[k],True)
            hashed(e['start_identity'],True)
            require(type(e['retried']) is bool and e['retried']==(e['retry_of'] is not None))
            stamp(e['wall_start'])
            if e['kind']=='START':
                require(e['outcome']=='STARTED' and e['end_ns'] is None and e['elapsed_ns'] is None and e['wall_end'] is None)
                require(e['method']=='DIRECT_MONOTONIC' and type(e['start_ns']) is int and e['start_ns']>=0)
                identity(e['clock_domain']);require(e['start_identity'] is None and e['result_sha256'] is None and e['source_receipt_sha256'] is None)
                starts[checksum]=e
            else:
                require(e['outcome']!='STARTED')
                require(type(e['elapsed_ns']) is int and e['elapsed_ns']>=0)
                require(stamp(e['wall_end'])>=stamp(e['wall_start']) or e['method']=='DIRECT_MONOTONIC')
                if e['kind']=='END':
                    start=starts.get(e['start_identity']);require(start is not None and e['start_identity'] not in ended)
                    for k in ('phase','candidate','timeframe','leg','clock_domain','retry_of','operation_identity_sha256'):
                        require(start[k]==e[k])
                    require(e['method']=='DIRECT_MONOTONIC' and type(e['end_ns']) is int and type(e['start_ns']) is int)
                    require(e['start_ns']>=start['start_ns'] and e['end_ns']>=e['start_ns'])
                    require(e['elapsed_ns']==e['end_ns']-e['start_ns']);ended.add(e['start_identity'])
                else:
                    require(e['method']=='DERIVED_PUBLIC_RECEIPT' and e['clock_domain'] is None and e['start_identity'] is None)
                    require(e['start_ns'] is None and e['end_ns'] is None and e['source_receipt_sha256'] is not None)
            if e['retry_of'] is not None:
                previous=next((x for x in result if x['integrity_sha256']==e['retry_of']),None)
                require(previous is not None and previous['outcome']=='FAILED')
                for k in ('phase','candidate','timeframe','leg'):require(previous[k]==e[k])
            result.append(e)
        require(paths==sorted(directory.iterdir()),'DIAGNOSTIC_READ_CHANGED')
        return result

    def _append(self, values):
        with safe_path(self.root/'lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            return self._append_locked(values)

    def _append_locked(self, values):
        records=self._events()
        if values['kind'] in ('START','DERIVED'):
            operation=values['operation_identity_sha256']
            require(operation is None or not any(e['operation_identity_sha256']==operation for e in records),
                    'DIAGNOSTIC_OPERATION_ALREADY_RECORDED')
            retry=values['retry_of']
            if retry is not None:
                previous=next((x for x in records if x['integrity_sha256']==retry),None)
                require(previous is not None and previous['outcome']=='FAILED')
                require((previous['phase'],previous['candidate'],previous['timeframe'],previous['leg'])==
                        (values['phase'],values['candidate'],values['timeframe'],values['leg']),
                        'DIAGNOSTIC_RETRY_MISMATCH')
        value=dict(sequence=len(records)+1,binding_sha256=self.manifest['binding_sha256'],**values)
        h=digest(value);value['integrity_sha256']=h
        # Caller holds the exclusive lock through validation and publication.
        path=self.root/'events'/f'{len(records)+1:06d}-{h}.json'
        self._events(extra=value)
        publish(path,value)
        self._events()
        return h

    def _values(self, phase, candidate, timeframe, leg, operation, retry):
        validate_attribution(self.binding,phase,candidate,timeframe,leg)
        hashed(operation,True);hashed(retry,True)
        return dict(phase=phase,candidate=candidate,timeframe=timeframe,leg=leg,
                    operation_identity_sha256=operation,retry_of=retry,retried=retry is not None,result_sha256=None,source_receipt_sha256=None,
                    kind='START',start_identity=None,clock_domain=self.domain,start_ns=self.clock(),end_ns=None,
                    elapsed_ns=None,wall_start=self.wall(),wall_end=None,method='DIRECT_MONOTONIC',
                    outcome='STARTED',failure_code=None)

    @contextmanager
    def phase(self, phase, *, candidate=None, timeframe=None, leg=None,
              operation_identity_sha256=None, retry_of=None):
        value=self._values(phase,candidate,timeframe,leg,operation_identity_sha256,retry_of)
        start_id=self._append(value);start=self.clock();wall=self.wall()
        result={'result_sha256':None,'failure_code':None,'event_identity':None}
        try:
            yield result
        except BaseException as error:
            result['failure_code']='JSON_DECODE_ERROR' if isinstance(error,json.JSONDecodeError) else 'OPERATION_EXCEPTION'
            raise
        finally:
            end=self.clock();wall_end=self.wall()
            hashed(result['result_sha256'],True)
            require(result['failure_code'] in (None,'PROCESS_EXIT_NONZERO','OPERATION_EXCEPTION','VALIDATION_REJECTED','JSON_DECODE_ERROR'))
            result['event_identity']=self._append(dict(value,kind='END',start_identity=start_id,
                start_ns=start,end_ns=end,elapsed_ns=end-start,wall_start=wall,wall_end=wall_end,
                outcome='FAILED' if result['failure_code'] else 'SUCCEEDED',failure_code=result['failure_code'],
                result_sha256=result['result_sha256']))

    def import_public_receipt(self, phase, receipt, *, candidate=None, timeframe=None, leg=None, retry_of=None):
        with safe_path(self.root/'lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            return self._import_public_receipt_locked(phase,receipt,candidate=candidate,
                timeframe=timeframe,leg=leg,retry_of=retry_of)

    def _import_public_receipt_locked(self, phase, receipt, *, candidate=None, timeframe=None, leg=None, retry_of=None):
        keys(receipt,('operation_identity_sha256','wall_start','wall_end','elapsed_ns','outcome','failure_code','result_sha256'))
        validate_attribution(self.binding,phase,candidate,timeframe,leg)
        scope=(phase,candidate,timeframe,leg,retry_of)
        receipt_hash=digest(receipt)
        for e in self._events():
            same_scope=(e['phase'],e['candidate'],e['timeframe'],e['leg'],e['retry_of'])==scope
            same_operation=(receipt['operation_identity_sha256'] is not None and
                            e['operation_identity_sha256']==receipt['operation_identity_sha256'])
            ambiguous_identity=(receipt['operation_identity_sha256'] is None and
                                e['operation_identity_sha256'] is None and
                                (same_scope or e['source_receipt_sha256']==receipt_hash))
            if e['kind']=='DERIVED' and (same_operation or ambiguous_identity):
                require(e['source_receipt_sha256']==receipt_hash and same_scope,
                        'DIAGNOSTIC_REPLAY_CONFLICT')
                return e['integrity_sha256']
        value=self._values(phase,candidate,timeframe,leg,receipt['operation_identity_sha256'],retry_of)
        # No raw model/tool output or private reasoning is accepted in this contract.
        require(receipt['outcome'] in ('SUCCEEDED','FAILED'))
        require(receipt['failure_code'] in (None,'PROCESS_EXIT_NONZERO','OPERATION_EXCEPTION','VALIDATION_REJECTED','JSON_DECODE_ERROR'))
        require((receipt['outcome']=='FAILED')==(receipt['failure_code'] is not None))
        require(type(receipt['elapsed_ns']) is int and receipt['elapsed_ns']>=0)
        require(stamp(receipt['wall_end'])>=stamp(receipt['wall_start']))
        hashed(receipt['result_sha256'],True)
        return self._append_locked(dict(value,**receipt,kind='DERIVED',clock_domain=None,start_ns=None,end_ns=None,
                                source_receipt_sha256=digest(receipt),method='DERIVED_PUBLIC_RECEIPT'))

    def report(self):
        events=self.events();complete=[e for e in events if e['kind']!='START']
        ends={e['start_identity'] for e in complete};unfinished=[e for e in events if e['kind']=='START' and e['integrity_sha256'] not in ends]
        total=[e for e in complete if e['phase']=='M17'];require(len(total)<=1,'DIAGNOSTIC_TOTAL_AMBIGUOUS')
        stages=[e for e in complete if e['phase']!='M17'];measured=sum(e['elapsed_ns'] for e in stages)
        if total and total[0]['method']=='DIRECT_MONOTONIC':
            require(all(e['start_ns']>=total[0]['start_ns'] and e['end_ns']<=total[0]['end_ns']
                        for e in stages if e['method']=='DIRECT_MONOTONIC' and e['clock_domain']==total[0]['clock_domain']),
                    'DIAGNOSTIC_TOTAL_BOUNDARY_CONTRADICTION')
        covered=remainder=None
        if total and total[0]['method']=='DIRECT_MONOTONIC' and all(e['method']=='DIRECT_MONOTONIC' and
                e['clock_domain']==total[0]['clock_domain'] and e['start_ns']>=total[0]['start_ns'] and
                e['end_ns']<=total[0]['end_ns'] for e in stages):
            intervals=sorted((e['start_ns'],e['end_ns']) for e in stages);merged=[]
            for a,b in intervals:
                if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
                else:merged.append((a,b))
            covered=sum(b-a for a,b in merged);remainder=total[0]['elapsed_ns']-covered
        coverage=[]
        for phase in PHASES:
            targets=([dict(candidate=c['candidate_identity'],timeframe=None,leg=None) for c in self.binding['candidates']]
                     if phase=='M07' else [dict(candidate=c['candidate_identity'],timeframe=x['timeframe'],leg=x['leg'])
                        for c in self.binding['candidates'] for x in c['charts']] if phase=='M08' else [None])
            for target in targets:
                matches=[e for e in complete if e['phase']==phase and (target is None or all(e[k]==v for k,v in target.items()))]
                coverage.append(dict(phase=phase,attribution=target,state='OBSERVED' if matches else 'UNKNOWN',
                    reason=None if matches else 'NO_OBSERVABLE_BOUNDARY_RECORDED',events=[e['integrity_sha256'] for e in matches]))
        return dict(schema=SCHEMA,authority='DIAGNOSTIC_ONLY',evidence_state='INCOMPLETE' if unfinished else 'READABLE_DIAGNOSTIC',binding=self.binding,events=events,
            phase_coverage=coverage,incomplete_events=[e['integrity_sha256'] for e in unfinished],
            total_elapsed_ns=total[0]['elapsed_ns'] if total else None,measured_stage_sum_ns=measured,
            covered_union_ns=covered,unattributed_elapsed_ns=remainder,
            remainder_state='KNOWN_UNATTRIBUTED' if remainder is not None else 'UNKNOWN',
            remainder_reason=None if remainder is not None else 'TOTAL_OR_COMPARABLE_CLOCK_BOUNDARIES_UNAVAILABLE',
            attribution_buckets={scope:[e['integrity_sha256'] for e in complete if
                ('TOTAL_EXECUTION' if e['phase']=='M17' else 'PER_TIMEFRAME' if e['timeframe'] else 'PER_CANDIDATE' if e['candidate'] else 'FIXED_PACK')==scope]
                for scope in ('FIXED_PACK','PER_CANDIDATE','PER_TIMEFRAME','TOTAL_EXECUTION')})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='action',required=True)
    init=commands.add_parser('init');init.add_argument('--root',required=True);init.add_argument('--binding',required=True);init.add_argument('--question-pdf',required=True)
    report=commands.add_parser('report');report.add_argument('--root',required=True)
    imported=commands.add_parser('import-public-receipt');imported.add_argument('--root',required=True);imported.add_argument('--receipt',required=True)
    measure=commands.add_parser('measure');measure.add_argument('--enabled',action='store_true');measure.add_argument('--root');measure.add_argument('command',nargs=argparse.REMAINDER)
    for p in (measure,imported):
        p.add_argument('--phase',choices=PHASES);p.add_argument('--candidate');p.add_argument('--timeframe',choices=('1W','1D','4H','1H'));p.add_argument('--leg',choices=('NATIVE','SUPPORTING_REFERENCE'));p.add_argument('--operation-sha256');p.add_argument('--retry-of')
    args=parser.parse_args(argv)
    if args.action=='init':
        Meter.create(args.root,read_json(safe_path(args.binding)),args.question_pdf);return 0
    if args.action=='report':
        print(json.dumps(Meter(args.root).report(),sort_keys=True,indent=2));return 0
    if args.action=='import-public-receipt':
        Meter(args.root).import_public_receipt(args.phase,read_json(safe_path(args.receipt)),candidate=args.candidate,timeframe=args.timeframe,leg=args.leg,retry_of=args.retry_of);return 0
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    require(bool(command),'DIAGNOSTIC_COMMAND_REQUIRED')
    if not args.enabled:
        return subprocess.run(command).returncode
    require(args.root is not None and args.phase is not None,'DIAGNOSTIC_ENABLED_BINDING_REQUIRED')
    meter=Meter(args.root)
    with meter.phase(args.phase,candidate=args.candidate,timeframe=args.timeframe,leg=args.leg,
                     operation_identity_sha256=args.operation_sha256,retry_of=args.retry_of) as result:
        completed=subprocess.run(command)  # serial, no capture/argv persistence/retry or env alteration
        if completed.returncode:result['failure_code']='PROCESS_EXIT_NONZERO'
    return completed.returncode

if __name__=='__main__':
    try:raise SystemExit(main())
    except (MeasurementError,OSError):raise SystemExit('DIAGNOSTIC_MEASUREMENT_FAILED')
