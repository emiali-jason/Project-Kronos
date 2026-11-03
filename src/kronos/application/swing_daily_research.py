"""LOCAL-03 retained-only WO-12 adapters. No acquisition or analytical capability.

The existing WO-12 application/store/exporter own all publication. A daily BASE
and its SUPPLEMENTs are immutable, linked research snapshots, not historical
as-of reconstructions, accepted Review evidence or trading authority.
"""
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile
import re

from kronos.swing.v1.prospective_research import IST, Record, record, _canonical, _digest, _fsync_dir
from kronos.browser.swing_research_workbook import SwingResearchProjection, LOCAL_COLUMNS

SOURCE_KINDS = ('ORIGIN', 'MILESTONE', 'DECISION', 'LIFECYCLE_TRACK', 'CANDLE',
                'CHECKPOINT', 'CALENDAR', 'LOCAL_ANALYSIS_ORIGINAL', 'LOCAL_ANALYSIS_DISPOSITION')
MAX_RECORDS = 5000


def require(ok, code='SWING_DAILY_EVIDENCE_INVALID'):
    if not ok:
        raise ValueError(code)


def aware(raw):
    value = datetime.fromisoformat(raw)
    require(value.tzinfo is not None and value.utcoffset() is not None)
    return value


def event_time(item):
    # No filesystem times or discovery time are substituted for source time.
    for key in ('occurred_at', 'observed_at', 'decided_at', 'admitted_at',
                'completed_at', 'checked_at', 'retrieved_at'):
        if item.data.get(key) is not None:
            return aware(item.data[key]).isoformat()
    return None


def local_originals(research):
    reader = getattr(research, 'local_history_reader', None)
    if reader is not None:
        return reader()
    # Explicit publication/isolated callers may validate immutable replay. Browser
    # wiring supplies the already-validated owner's fenced read, never this path.
    from kronos.application.swing_local_analysis import _original
    result = research.store.records('LOCAL_ANALYSIS_ORIGINAL')
    for item in result:
        _original(item)
    return result


def local_observations(research, current=None, *, as_of=None):
    observed = research.clock() if as_of is None else as_of
    observations = []
    calendars = research.store.records("CALENDAR")
    candles = research.store.records("CANDLE")
    require(len(calendars) + len(candles) <= MAX_RECORDS, "SWING_DAILY_CAPACITY_UNAVAILABLE")
    originals = local_originals(research)
    require(len(originals) <= MAX_RECORDS, 'SWING_DAILY_CAPACITY_UNAVAILABLE')
    dispositions = research.store.records('LOCAL_ANALYSIS_DISPOSITION')
    from kronos.application.swing_local_analysis import _disposition
    for d in dispositions:
        _disposition(d, {o.identity:o for o in originals})
    origins = research.store.origins()
    links = { (o.data['origin_run_identity'], o.data['origin_assessment_sha256']):o for o in origins }
    owner_events = tuple(e for k in ('MILESTONE','DECISION','LIFECYCLE_TRACK')
                         for e in research.store.records(k))
    for item in originals:
        item.__post_init__()
        data = item.data
        result = json.loads(data['result_json'])['result']
        binding = result['binding']
        require(binding['instrument'] and result['authority'] == 'RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION')
        matches = [d for d in dispositions if d.data['original_identity'] == item.identity]
        require(len(matches) <= 1)
        status = 'HISTORICAL'
        if current is not None:
            control = current.get('control') or {}
            attempt = control.get('latest_attempt') or {}
            ref = control.get('current_manifest') or {}
            if (not current.get('reconciliation_unavailable') and attempt.get('state') == 'SUCCEEDED'
                    and attempt.get('run_id') == binding['run_identity']
                    and ref.get('sha256') == binding['publication_sha256']
                    and matches and matches[0].data['state'] == 'SUCCEEDED'):
                status = 'MATCHES_RETAINED_PUBLICATION_NOT_CURRENTNESS_CERTIFICATION'
        linked = [o for o in origins if (o.data['origin_run_identity'], o.data['origin_assessment_sha256'])
                  == (binding['run_identity'], binding['assessment_sha256'])]
        origin = linked[0] if len(linked) == 1 else None
        from kronos.swing.v1.local_research_outcomes import measure
        outcome = measure(item, json.loads(data['input_json'])['evidence'], result,
                          calendars, candles, as_of=observed, origin=origin,
                          basis=getattr(research, 'local_outcome_basis', None))
        observations.append(dict(original_identity=item.identity, source_sha256=item.integrity_sha256,
            opportunity_identity=None if origin is None else origin.data['opportunity_identity'],
            journey_events=[dict(identity=e.identity, schema=e.schema,event_at=event_time(e),
                                 state=e.data.get('state',e.data.get('readiness_state')))
                            for e in owner_events if origin is not None and e.data.get('origin_identity')==origin.identity],
            instrument=binding['instrument'], native_direction=binding['direction'],
            run_identity=binding['run_identity'], publication_sha256=binding['publication_sha256'],
            assessment_sha256=binding['assessment_sha256'], method_version=result['method_version'],
            captured_at=data['captured_at'], completed_at=data['completed_at'],
            evidence_cutoff=result['information_cutoff'], native_observed_at=result['native_observed_at'],
            observation_date=aware(data['captured_at']).astimezone(IST).date().isoformat(),
            currentness=status, thesis=result['thesis'], authority=result['authority'], outcomes=outcome,
            factual_tracks=[dict(identity=e.identity, **e.data) for e in owner_events
                            if origin is not None and e.schema == 'SWING_WO12_LIFECYCLE_TRACK_V1'
                            and e.data.get('origin_identity') == origin.identity
                            and aware(e.data['observed_at']) <= observed]))
    return tuple(sorted(observations, key=lambda r:(r['captured_at'],r['original_identity'])))


def local_rows(observations, month):
    rows = []
    for item in observations:
        if item['observation_date'][:7].replace('-', '_') != month:
            continue
        t = item['thesis'];o = t['overall']
        missing = sorted({m['reason'] for f in t['frame_assessments'] for m in f['missing']})
        for scenario in t['scenarios']:
            entry, stop, target, risk = (scenario[k] for k in
                ('entry_zone', 'stop_reference', 'target_zone', 'risk_reward'))
            values = dict(original_identity=item['original_identity'], instrument=item['instrument'],
                native_direction=item['native_direction'], local_direction=o['direction'],
                local_conclusion=o['disposition'], conviction=o['conviction'],
                reason=o['reason'], method_version=item['method_version'],
                run_identity=item['run_identity'], publication_sha256=item['publication_sha256'],
                assessment_sha256=item['assessment_sha256'], captured_at=item['captured_at'],
                completed_at=item['completed_at'], evidence_cutoff=item['evidence_cutoff'],
                observation_date=item['observation_date'], horizon=scenario['horizon'],
                scenario=scenario['kind'], scenario_direction=scenario['direction'],
                structural_radius=scenario['structural_radius'], availability=scenario['state'],
                entry_low=None if entry is None else entry['low'],
                entry_high=None if entry is None else entry['high'],
                invalidation=None if stop is None else stop['value'],
                target_low=None if target is None else target['low'],
                target_high=None if target is None else target['high'],
                reward_risk=None if risk is None else risk['conservative_ratio'],
                unavailable_reason=scenario['reason'], missing_evidence='; '.join(missing),
                currentness=item['currentness'], authority=item['authority'],
                opportunity_identity=item['opportunity_identity'])
            rows.append(tuple(values.get(k) for k in LOCAL_COLUMNS))
    require(len(rows) == len(set((r[0],r[15],r[16],r[17],r[18]) for r in rows)),
            'SWING_DAILY_DUPLICATE_OBSERVATION')
    return tuple(rows)


def publication_path(research_root, data):
    day=data['reporting_date'];source=data['source_digest'];seq=data['sequence']
    require(type(day) is str and date.fromisoformat(day).isoformat()==day)
    require(type(source) is str and re.fullmatch('[a-f0-9]{64}',source) is not None)
    require(type(seq) is int and seq>=0 and type(data['workbook_sha256']) is str
            and re.fullmatch('[a-f0-9]{64}',data['workbook_sha256']) is not None)
    suffix=Path('daily')/day/f'v{seq:06d}-{source}'/('KRONOS_Swing_Research_'+day[:7].replace('-','_')+'.xlsx')
    path=Path(data['workbook_path'])
    require(path.is_absolute() and '..' not in path.parts and path.parts[-4:]==suffix.parts,
            'SWING_DAILY_PATH_INVALID')
    if research_root is not None:require(path==Path(research_root)/suffix,'SWING_DAILY_PATH_INVALID')
    require(not any(p.is_symlink() for p in (path,*path.parents)),'SWING_DAILY_PATH_INVALID')
    return path


def daily_chain(store, day, publication_root=None, *, publications=None, prepared_index=None):
    # publications / prepared_index let a caller verify many days from one
    # load of the store; every record and workbook is still fully checked.
    if publications is None:
        publications = store.records('DAILY_PUBLICATION')
    values = sorted((r for r in publications
                     if r.data['reporting_date'] == day), key=lambda r:r.data['sequence'])
    prior = None
    for index, item in enumerate(values):
        d = item.data
        require(type(d['sequence']) is int and d['sequence'] == index
                and d['prior_publication'] == prior
                and d['publication_kind'] == ('BASE' if index == 0 else 'SUPPLEMENT'), 'SWING_DAILY_CHAIN_INVALID')
        if prepared_index is None:
            prepared = [p for p in store.records('DAILY_PREPARED') if p.identity == d['prepared_identity']]
        else:
            prepared = prepared_index.get(d['prepared_identity'], [])
        require(len(prepared) == 1 and prepared[0].data['source_digest'] == d['source_digest'])
        path = publication_path(publication_root,d)
        require(path.is_file() and not path.is_symlink()
                and sha256(path.read_bytes()).hexdigest() == d['workbook_sha256'],
                'SWING_DAILY_ARTIFACT_UNAVAILABLE')
        prior = item.identity
    return tuple(values)


def _publish_prepared(research, prepared):
    from kronos.browser.swing_research_workbook import export_swing_research_workbook
    d = prepared.data
    p = dict(d['projection']);p['generated_at'] = aware(p['generated_at'])
    projection = SwingResearchProjection(**p)
    # Recovery validates the original frozen sources, not a newer live pointer.
    source_records={r.identity:r for k in SOURCE_KINDS for r in research.store.records(k)}
    for ref in d['source_records']:
        require(ref['identity'] in source_records and source_records[ref['identity']].integrity_sha256==ref['sha256'],
                'SWING_DAILY_FROZEN_SOURCE_UNAVAILABLE')
    for run in d['native_runs']:
        for ref in run['artifacts'].values():
            if ref is not None:
                path=Path(ref['path']);require(path.is_file() and not path.is_symlink())
                h=sha256()
                with path.open('rb') as stream:
                    for part in iter(lambda:stream.read(1048576),b''):h.update(part)
                require(h.hexdigest()==ref['sha256'],'SWING_DAILY_FROZEN_SOURCE_UNAVAILABLE')
    payload = export_swing_research_workbook(projection)
    require(sha256(payload).hexdigest() == d['workbook_sha256'])
    target = publication_path(research.publication_root,d)
    expected = research.publication_root / 'daily' / d['reporting_date'] / (
        f"v{d['sequence']:06d}-{d['source_digest']}" ) / f"KRONOS_Swing_Research_{projection.year_month}.xlsx"
    require(target == expected and not target.is_symlink(), 'SWING_DAILY_PATH_INVALID')
    from kronos.swing.run_publication import _mkdir
    _mkdir(target.parent)
    require(not any(p.is_symlink() for p in (target.parent, *target.parents)), 'SWING_DAILY_PATH_INVALID')
    fd, temp = tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        try:os.link(temp,target)
        except FileExistsError:require(target.read_bytes() == payload, 'SWING_DAILY_IMMUTABLE_CONFLICT')
    finally:os.unlink(temp)
    _fsync_dir(target.parent)
    require(target.read_bytes() == payload, 'SWING_DAILY_READBACK_INVALID')
    research.fault_hook('daily_after_artifact')
    receipt = record('DAILY_PUBLICATION', reporting_date=d['reporting_date'],
        sequence=d['sequence'], publication_kind='BASE' if d['sequence']==0 else 'SUPPLEMENT',
        prior_publication=d['prior_publication'], prepared_identity=prepared.identity,
        source_digest=d['source_digest'], workbook_path=str(target),
        workbook_sha256=d['workbook_sha256'], workbook_bytes=len(payload),
        source_cut_at=d['source_cut_at'], published_at=research.clock().isoformat(),
        source_records=d['source_records'], native_runs=d['native_runs'],
        coverage=d['coverage'],publication_control=d['publication_control'],
        capture_receipts=d['capture_receipts'],source_runtime=d['source_runtime'],
        recording_policy=d['recording_policy'], authority='RETAINED_RESEARCH_ONLY')
    research.store.retain(receipt)
    research.fault_hook('daily_after_receipt')
    return receipt


def record_daily(research, *, reporting_date, trigger, history=(), attempt_identity, publication_control=None, capture_receipts=(), source_runtime=None):
    """One date/commit under existing WO-12 flock; retry recovers same frozen cut."""
    from kronos.browser.swing_research_workbook import export_swing_research_workbook
    require(type(reporting_date) is date and trigger in {'MANUAL','SCHEDULE','CATCHUP'})
    observed=research.clock();require(observed.tzinfo is not None and observed.utcoffset() is not None)
    require(reporting_date <= observed.astimezone(IST).date(), 'SWING_DAILY_FUTURE_DATE')
    day=reporting_date.isoformat()
    with research.store.transaction():
        marker=research.store.pointer('COMMISSIONING','active')
        require(marker is not None,'SWING_RESEARCH_COMMISSIONING_REQUIRED')
        require(reporting_date >= aware(marker.data['commissioned_at']).astimezone(IST).date(),
                'SWING_DAILY_BEFORE_COMMISSIONING')
        chain=daily_chain(research.store,day,research.publication_root)
        pending=[r for r in research.store.records('DAILY_PREPARED')
                 if r.data['reporting_date']==day and r.data['sequence']==len(chain)]
        require(len(pending)<=1,'SWING_DAILY_PREPARED_CONFLICT')
        if pending:
            require(pending[0].data['prior_publication']==(chain[-1].identity if chain else None))
            _publish_prepared(research,pending[0])
            chain=daily_chain(research.store,day,research.publication_root)
        records=tuple(r for kind in SOURCE_KINDS for r in research.store.records(kind))
        require(len(records)<=MAX_RECORDS,'SWING_DAILY_CAPACITY_UNAVAILABLE')
        sources=[]
        for r in records:
            stamp=event_time(r)
            require(stamp is None or aware(stamp)<=observed,'SWING_DAILY_FUTURE_SOURCE')
            if stamp is None or aware(stamp).astimezone(IST).date()==reporting_date:
                sources.append(dict(identity=r.identity,sha256=r.integrity_sha256,
                    event_at=stamp, capture_at=r.data.get('captured_at'),
                    occurrence='UNRESOLVED_TIME' if stamp is None else 'REPORTING_DAY'))
        native=[]
        missing_local=[]
        existing={(json.loads(o.data['result_json'])['result']['binding']['run_identity'],
                   json.loads(o.data['result_json'])['result']['binding']['assessment_sha256'])
                  for o in local_originals(research)}
        from kronos.swing.v1.native_discovery import NativeProductPath
        for retained in history:
            at=aware(retained['completed_at'])
            require(at<=observed and at.astimezone(IST).date()==reporting_date,
                    'SWING_DAILY_SOURCE_DATE_INVALID')
            for assessment in retained['assessments']:
                # Archival selector mirrors Native's existing NSE PROBABLE
                # scope, never creates a new Review requirement or eligibility.
                if (assessment['product_path']!=NativeProductPath.NSE.value or assessment['status']!='PROBABLE'
                        or assessment['weekly_state']=='OPPOSING'):
                    continue
                if (retained['run_identity'],assessment['assessment_sha256']) not in existing:
                    row=dict(original_identity=None,instrument=assessment['instrument'],
                        native_direction=assessment['direction'],run_identity=retained['run_identity'],
                        publication_sha256=retained['publication']['sha256'],
                        assessment_sha256=assessment['assessment_sha256'],
                        captured_at=None, completed_at=None,evidence_cutoff=retained['evidence_cutoff'],
                        observation_date=day,horizon='UNAVAILABLE',scenario='UNAVAILABLE',
                        availability='UNAVAILABLE',unavailable_reason='LOCAL_ASSESSMENT_MISSING',
                        currentness='HISTORICAL_RESEARCH_SNAPSHOT',authority='RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION')
                    missing_local.append(tuple(row.get(k) for k in LOCAL_COLUMNS))
            native.append(retained)
        projection=research._projection(reporting_date.strftime('%Y_%m'),observed)
        used = {identity for row in projection.local_outcomes
                if row[-1] is not None for identity in json.loads(row[-1])['source_records']}
        known = {s['identity'] for s in sources}
        for record_item in records:
            if record_item.identity in used and record_item.identity not in known:
                sources.append(dict(identity=record_item.identity, sha256=record_item.integrity_sha256,
                    event_at=event_time(record_item), capture_at=record_item.data.get('captured_at'),
                    occurrence='OUTCOME_DEPENDENCY_FROM_RETAINED_HISTORY'))
        require(used <= {s['identity'] for s in sources}, 'SWING_DAILY_OUTCOME_SOURCE_UNAVAILABLE')
        if missing_local:
            from dataclasses import replace
            projection=replace(projection,local_research=(*projection.local_research,*missing_local),
                               local_contract='LOCAL_RESEARCH_1.0')
        # Six legacy sheets are preserved. Local rows are additive research;
        # old dates include explicitly timestamped month context, not backdating.
        source_digest=_digest(dict(sources=sorted(sources,key=lambda r:r['identity']),
            native=sorted(native,key=lambda r:r['run_identity']), projection=projection.projection_identity,
            publication_control=publication_control,capture_receipts=capture_receipts))
        if chain and chain[-1].data['source_digest']==source_digest:
            return dict(state='ALREADY_COVERED',publication_identity=chain[-1].identity,reporting_date=day)
        p=asdict(projection);p['generated_at']=observed.isoformat()
        p['metadata']=(*projection.metadata,('reporting_date',day),('snapshot_captured_at',observed.isoformat()),
            ('temporal_scope','RETAINED_SNAPSHOT_WITH_TIMESTAMPED_MONTH_CONTEXT_NOT_HISTORICAL_ASOF'),
            ('local_authority','RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION'))
        projection=SwingResearchProjection(**{**p,'generated_at':observed})
        payload=export_swing_research_workbook(projection)
        p['generated_at']=observed.isoformat()
        seq=len(chain);target=research.publication_root/'daily'/day/f'v{seq:06d}-{source_digest}'/f'KRONOS_Swing_Research_{projection.year_month}.xlsx'
        coverage='RECORDED_WITH_GAPS' if any(r['event_at'] is None for r in sources) or not native else 'RETAINED_SOURCES_RECORDED'
        prepared=record('DAILY_PREPARED', reporting_date=day,sequence=seq,
            prior_publication=chain[-1].identity if chain else None,source_digest=source_digest,
            projection=p,source_cut_at=observed.isoformat(),workbook_path=str(target),
            workbook_sha256=sha256(payload).hexdigest(),source_records=sources,native_runs=native,
            coverage=coverage,trigger=trigger,attempt_identity=attempt_identity,
            commissioning_identity=marker.identity,publication_control=publication_control,
            capture_receipts=capture_receipts,source_runtime=source_runtime or {'availability':'UNAVAILABLE'},
            recording_policy='KRONOS-SWING-RETAINED-DAILY-1.0')
        from kronos.swing.run_publication import _mkdir
        for kind in ('DAILY_PREPARED','DAILY_PUBLICATION'):
            _mkdir(research.store.root/'records'/('SWING_WO12_'+kind+'_V1'))
        research.store.retain(prepared);research.fault_hook('daily_after_prepare')
        receipt=_publish_prepared(research,prepared)
        return dict(state='PUBLISHED',publication_identity=receipt.identity,reporting_date=day,
            kind=receipt.data['publication_kind'],coverage=coverage)
