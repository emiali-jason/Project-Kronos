"""Closed, prospective FAILED_FENCED recovery protocol (R3, version 1.0.0).

This module supplies accounting and evidence primitives, not operational permission.
A missing independently prepared authority, native fact, or prospective owner record
is a denial. Ordinary maintenance V1/V2 records and state transitions are unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock, get_ident
from typing import Any, Mapping
import fcntl
import hmac
import json
import os
import re
import stat
import time

from . import failed_fenced_schema as schema
from .maintenance_admission import AdmissionTicket, MaintenanceAdmissionCoordinator

PROTOCOL = 'KRONOS-FAILED-FENCED-RECOVERY-V1'
VERSION = '1.0.0'
EXTERNAL_SCHEMA = 'KRONOS-FAILED-FENCED-EXTERNAL-PROOF/1.0.0'
ROOT_SCHEMA = 'KRONOS-FAILED-FENCED-ROOT-PROOF/1.0.0'
SCOPE_HASH = '7b89d47e66dde370773ecf3cb845b331e8e400212e999fa0b52cf1d68c2ebfde'
SCOPE_BYTES = '28487'
APPENDIX_HASH = '81c0c9dc75578bf28a85939e062fd1dc4ef0084bd2ef37945e0a2a0fbb3b227e'
MAX_RECORD = 1 << 20
MAX_U64 = (1 << 64)-1
STATIC_KINDS = frozenset({'CLOCK_QUALIFICATION','GUARD_APPLICABILITY','RESTORATION_PLAN'})
P_KINDS = frozenset({'EXECUTOR_TERMINATION','CONTROL_BINDING','ISSUED_ADMISSION','FENCE_ROSTER','TAIL','CLEANUP_APPLICABILITY','OWNER_RESULT','COMPOSITION_INVENTORY','PEER_REGISTRATION','PEER_FULFILLMENT'})
L_KINDS = frozenset({'ORIGINAL_AUTHORITY','RECOVERY_AUTHORITY','ORIGINAL_CONTROLLER','CONTROLLER_CAPABILITY','CONTROLLER_ADMISSION','CONTROLLER_DISPATCH','CONTROLLER_CLOSURE','TARGET_ARTIFACT','PACKAGE'})
S_KINDS = frozenset({'BOOTSTRAP_IDENTITY','RESTORATION'})
_active_ledger: ContextVar[ProspectiveLedger | None] = ContextVar('failed_fenced_ledger', default=None)
_verification_context: ContextVar[tuple | None] = ContextVar('failed_fenced_verification_context', default=None)
_verification_path: ContextVar[tuple] = ContextVar('failed_fenced_verification_path', default=())
_composition_scope = ContextVar('failed_fenced_composition_structure_scope', default=None)
_read_directory_scope = ContextVar('failed_fenced_read_directory_scope', default=None)

@contextmanager
def _evidence_path(registry, digest):
    # A recursive path belongs to this execution context, not to all concurrent
    # readers of the registry. Immutable tuples also isolate copied contexts.
    path = _verification_path.get()
    node = (registry, digest)
    _require(node not in path, 'PROVENANCE', 'evidence cycle')
    token = _verification_path.set(path + (node,))
    try:
        yield
    finally:
        _verification_path.reset(token)

def current_ledger():
    explicit = _active_ledger.get()
    if explicit is not None:
        return explicit
    # Ticket activation follows the exact issued owner across worker threads;
    # no process-global "last ledger" can attach an unrelated callback.
    from .maintenance_admission import _current_ticket
    ticket = _current_ticket.get()
    if isinstance(ticket, AdmissionTicket) and ticket._owner.is_live(ticket):
        return ticket._owner._prospective_ledger
    return None

class RecoveryError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code if code in schema.FAILURE_CODES else 'PROTOCOL'
        super().__init__(f'FAILED_FENCED_{self.code}: {message}')

def _require(condition, code='PROTOCOL', message='invalid recovery evidence'):
    if not condition: raise RecoveryError(code,message)

def _check_type(name,value):
    try: schema.validate_type(name,value)
    except schema.SchemaError as exc: raise RecoveryError('PROTOCOL',str(exc)) from exc

def _check_payload(kind,value,proof=False):
    try: schema.validate_payload(kind,value,proof=proof)
    except schema.SchemaError as exc: raise RecoveryError('PROTOCOL',str(exc)) from exc

def _ascii_tree(value, depth=0):
    _require(depth <= 64, message='JSON nesting bound')
    if value is None or type(value) is bool: return
    if type(value) is str:
        _require(value.isascii() and (not value or value.isprintable()),message='non-ASCII protocol string')
    elif type(value) is dict:
        _require(len(value) <= 4096,message='object bound')
        for k,v in value.items():
            _require(type(k) is str,message='object key'); _ascii_tree(k,depth+1); _ascii_tree(v,depth+1)
    elif type(value) is list:
        _require(len(value) <= 4096,message='array bound')
        for item in value: _ascii_tree(item,depth+1)
    else: raise RecoveryError('PROTOCOL','JSON numbers and coercions are forbidden')

def canonical_bytes(value) -> bytes:
    _ascii_tree(value)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('ascii')
    _require(len(raw)<=MAX_RECORD,message='record size bound')
    return raw

def _pairs(pairs):
    result={}
    for k,v in pairs:
        _require(k not in result,message='duplicate JSON key'); result[k]=v
    return result

def _number(_):
    raise RecoveryError('PROTOCOL','JSON number forbidden')

def decode_canonical(raw: bytes):
    _require(type(raw) is bytes and 0<len(raw)<=MAX_RECORD,message='record size/type')
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=_pairs,parse_int=_number,parse_float=_number,parse_constant=_number)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as exc:
        raise RecoveryError('PROTOCOL','invalid canonical JSON') from exc
    _require(canonical_bytes(value)==raw,message='noncanonical JSON encoding')
    return value

def record_ref(raw: bytes):
    value=decode_canonical(raw)
    _require(type(value) is dict and value.get('kind') in schema.RECORD_SCHEMAS,message='record reference kind')
    return {'kind':value['kind'],'hash':sha256(raw).hexdigest()}

def blob_ref(identity: str,raw: bytes):
    _check_type('Id',identity)
    return {'identity':identity,'hash':sha256(raw).hexdigest(),'bytes':str(len(raw))}

def source_identity(value: str | bytes):
    raw=value.encode('utf-8') if type(value) is str else value
    result={'encoding':'UTF-8','bytes':raw.hex()}
    _check_type('SourceIdentity',result); return result

def slot_key(lineage):
    _check_type('Lineage',lineage)
    return sha256(b'KRONOS/FAILED_FENCED/slot\n'+canonical_bytes(lineage)).hexdigest()

def _copy(value):
    return decode_canonical(canonical_bytes(value))

def _ordered(items,key='identity'):
    keys=[x[key] if type(x) is dict else x for x in items]
    _require(keys==sorted(keys) and len(set(keys))==len(keys),message='duplicate or unordered identities')

def _proof_role(kind,role):
    allowed = ({'PREDECESSOR'} if kind in P_KINDS else {'LAUNCHER'} if kind in L_KINDS
               else {'SUCCESSOR'} if kind in S_KINDS else {'PREDECESSOR','SUCCESSOR'} if kind in {'SOURCE','CAPABILITY','ABSENCE'}
               else {'LAUNCHER','SUCCESSOR'} if kind in {'COMPATIBILITY','PLATFORM_OBSERVATION'}
               else {'PREDECESSOR','LAUNCHER','SUCCESSOR'} if kind in {'ENDPOINT_CONFIGURATION','FAILURE_FACT'} else set())
    _require(role in allowed,'AUTHORITY','proof role mismatch')

def _semantics(kind,p):
    if kind in {'SEAL','OWNER_PROOF','PREPARED_COMMIT'}:
        _require((p['product_owners'],p['accepted_owners'],p['commit_owners'])==('0','0','1'),'ACCOUNTING','publisher counts')
    if kind == 'ACK':
        _require(p['recovery_owners']=='0','ACCOUNTING','ACK before release')
        _require(int(p['publication_complete_ns'])<=int(p['released_ns'])<=int(p['ack_ns'])<int(p['work_deadline_ns'])<=int(p['stop_deadline_ns']),'TIMEOUT','ACK time order')
    if kind == 'OBLIGATION':
        _require(p['effect']['kind']==p['relation'],'PROVENANCE','effect relation')
        _require((p['effect']['transition'] is not None)==('CURRENTNESS' in p['relation']),'PROVENANCE','currentness transition')
        _ordered(p['required_children'])
        _state_result(p,{'ACCEPTED','STARTED'})
        if p['state'] in {'ACCEPTED','STARTED'}: _require(not p['notices'],message='early notices')
    if kind == 'CLEANUP':
        _require(p['action'] in schema.CLEANUP_ACTIONS.get(p['owner'],()),'CLEANUP','unlisted cleanup action')
        _ordered(p['obligations']); _state_result(p,{'NOT_STARTED','STARTED'})
        if p['state']=='NOT_APPLICABLE': _require(p['owner_result'] is not None and p['failure'] is None,'CLEANUP','unproven non-applicability')
    if kind == 'EXECUTOR':
        fields=[p[k] for k in ('original_controller','no_child_start','no_consumption','completion')]
        _require(all(v is None for v in fields) if p['state']=='OWNED' else all(v is not None for v in fields),'ACCOUNTING','executor evidence')
        if p['state']=='TERMINATED': _require(fields[0]==fields[1]==fields[2],'ACCOUNTING','controller closure identity')
    if kind == 'OWNER_RESULT':
        _require(schema.owner_tuple(p['owner'],p['purpose'],p['action']),'AUTHORITY','unlisted owner action')
        _ordered(p['obligations']); _ordered(p['peer_fulfillment'])
        reason={'EFFECT':'EFFECT_COMPLETE','REFERENCE':'REFERENCE_COMPLETE','CLEANUP':'CLEANUP_COMPLETE','ABSENCE':'QUIESCENT','RECONCILIATION':'RECONCILED','CHECKPOINT':'CHECKPOINT_COMPLETE'}[p['purpose']]
        if p['result']=='COMPLETE':
            _require(p['reason']==reason and not p['notification_failure'] and not p['durability_unproven'],'PROVENANCE','owner completion flags')
            _require(all(p[k]=='0' for k in ('owned_workers','queued_items','callbacks','durable_writes')),'ACCOUNTING','owner has outstanding work')
        elif p['result']=='FAILED': _require(p['reason']=='UNPROVEN',message='failure reason')
        else:
            _require((p['reason']=='NOT_INSTALLED' and p['purpose'] in {'CLEANUP','ABSENCE'}) or (p['reason']=='NOT_REQUIRED' and p['purpose']=='REFERENCE'),'PROVENANCE','inapplicability reason')
    if kind == 'CLOCK_QUALIFICATION':
        _require(p['equivalent'] and p['nondecreasing'] and p['sleep_behavior_equal'],'TIMEOUT','clock not qualified')
    if kind == 'ABSENCE':
        _require(all(p[k]=='0' for k in ('active','retained_leases','callbacks','unresolved_cleanup')),'CLEANUP','absence is not zero')
    if kind == 'EXECUTOR_TERMINATION':
        _ordered(p['accepted_operations']);_ordered(p['completed_operations'])
        _require(p['accepted_operations']==p['completed_operations'] and all(p[k]=='0' for k in ('owned_workers','pending_callbacks','pending_publications')),'ACCOUNTING','original executor is not complete')
    if kind == 'TAIL':
        _ordered(p['required_cleanup']);_ordered(p['completed_cleanup']);_ordered(p['forbidden_hooks'])
        _require(p['required_cleanup']==p['completed_cleanup'] and p['product_owners']=='0' and p['recovery_executor_owners']=='1','ACCOUNTING','tail owner/cleanup proof')
    if kind == 'COMPOSITION_AUTHORITY':
        _require(max(int(p['child_started_durable_ns']),int(p['identity_verified_ns']))<=int(p['gate_ns'])<int(p['stop_deadline_ns']),'TIMEOUT','late composition gate')
    if kind == 'CHILD_STARTED':
        _require(int(p['fork_enter_ns'])<=int(p['fork_return_ns']) and int(p['ready_deadline_ns'])==int(p['fork_enter_ns'])+120_000_000_000,'TIMEOUT','child deadline')
    if kind == 'PEER_FULFILLMENT':
        _require(p['failure']==(p['outcome']=='FAILED'),'PROVENANCE','peer failure state')
        if p['outcome']=='NOT_REQUIRED': _require(p['invoked_ns'] is None and p['returned_ns'] is None and not p['outputs'],'PROVENANCE','peer non-applicability')
        elif p['outcome']=='COMPLETED': _require(p['invoked_ns'] is not None and p['returned_ns'] is not None and int(p['invoked_ns'])<=int(p['returned_ns'])<=int(p['recorded_ns']),'PROVENANCE','peer return time')

def _state_result(p,unfinished):
    if p['state'] in unfinished: _require(p['owner_result'] is None and p['failure'] is None,message='premature result')
    elif p['state']=='COMPLETE': _require(p['owner_result'] is not None and p['failure'] is None,message='missing completion')
    elif p['state']=='FAILED': _require(p['owner_result'] is not None and p['failure'] is not None,message='missing failure')

class RecoveryCodec:
    """Exact byte codec. A valid MAC is authentication, never human authority."""
    def __init__(self,private_control_bytes: bytes,clock: dict):
        _require(type(private_control_bytes) is bytes and re.fullmatch(rb'KRONOS_BROWSER_BACKEND_CONTROL_V1\n[1-9][0-9]*\n[0-9a-f]{64}\n',private_control_bytes) is not None,'IDENTITY','control checkpoint format')
        parts=private_control_bytes.splitlines();_require(int(parts[1])>=2,'IDENTITY','control PID')
        _check_type('Clock',clock)
        self.clock=_copy(clock);self.key_id=sha256(private_control_bytes).hexdigest();self.pid=parts[1].decode('ascii')
        self._control=bytes(private_control_bytes);self._key=bytes.fromhex(parts[2].decode('ascii'))
    def matches_control(self,raw):
        return type(raw) is bytes and hmac.compare_digest(raw,self._control)
    def verify_control_binding(self,payload,store):
        raw=store.read_custody(self.key_id)
        _require(self.matches_control(raw)
                 and payload['live_control']['bytes']==str(len(raw))
                 and payload['retained_control']['bytes']==str(len(raw)),
                 'IDENTITY','retained control mismatch')
    def _check_context(self):
        # The ordinary producer owns the actual control bytes. The strictly
        # read-only native semantic codec below has an additional live exchange.
        pass
    def _authenticate(self,raw,value,external=False):
        signed={k:v for k,v in value.items() if k!='mac'}
        _require(hmac.compare_digest(value['mac'],self._mac(signed,external)),
                 'AUTHORITY','external MAC' if external else 'record MAC')
    def _mac(self,value,external=False):
        role=value['role']; _require(role in {'PREDECESSOR','LAUNCHER','SUCCESSOR'},'AUTHORITY','role')
        key=hmac.digest(self._key,f'{PROTOCOL}/{VERSION}/key/{role}/{self.key_id}'.encode('ascii'),'sha256')
        domain=(EXTERNAL_SCHEMA if external else f'{PROTOCOL}/{VERSION}')+'/record\n'
        return hmac.new(key,domain.encode('ascii')+canonical_bytes(value),'sha256').hexdigest()
    def encode(self,kind,payload,role,issued_ns):
        _check_payload(kind,payload);_semantics(kind,payload)
        _require(role in schema.RECORD_ROLES[kind],'AUTHORITY','record role')
        _check_type('Ns',str(issued_ns))
        value={'protocol':PROTOCOL,'version':VERSION,'kind':kind,'role':role,'key_id':self.key_id,'clock':self.clock,'issued_ns':str(issued_ns),'payload':_copy(payload)}
        value['mac']=self._mac(value);raw=canonical_bytes(value)
        _require(len(raw)<=(8192 if kind=='COMPOSITION_AUTHORITY' else 131072 if kind=='ACK' else MAX_RECORD),message='kind size')
        return raw
    def decode(self,raw,expected_kind=None):
        self._check_context()
        value=decode_canonical(raw)
        _require(type(value) is dict and set(value)=={'protocol','version','kind','role','key_id','clock','issued_ns','payload','mac'},message='record envelope')
        _require(value['protocol']==PROTOCOL and value['version']==VERSION and value['key_id']==self.key_id and value['clock']==self.clock,'IDENTITY','record identity/clock')
        kind=value['kind'];_check_payload(kind,value['payload']);_semantics(kind,value['payload'])
        _require(expected_kind is None or kind==expected_kind,message='record kind mismatch')
        _require(value['role'] in schema.RECORD_ROLES[kind],'AUTHORITY','record issuer role')
        _check_type('Ns',value['issued_ns']);_check_type('Hash',value['mac'])
        self._authenticate(raw,value)
        _require(len(raw)<=(8192 if kind=='COMPOSITION_AUTHORITY' else 131072 if kind=='ACK' else MAX_RECORD),message='kind size')
        if kind in {'ACK','CHILD_IDENTITY','COMPOSITION_AUTHORITY'}:
            field={'ACK':'ack_ns','CHILD_IDENTITY':'observed_ns','COMPOSITION_AUTHORITY':'gate_ns'}[kind]
            _require(value['issued_ns']==value['payload'][field],'TIMEOUT','issuance time mismatch')
        return value
    def encode_proof(self,kind,payload,issuer,role,issued_ns):
        _check_payload(kind,payload,True);_semantics(kind,payload);_check_type('Process',issuer);_proof_role(kind,role)
        _check_type('Ns',str(issued_ns))
        value={'schema':EXTERNAL_SCHEMA,'kind':kind,'issuer':_copy(issuer),'role':role,'key_id':self.key_id,'clock':self.clock,'issued_ns':str(issued_ns),'payload':_copy(payload)}
        value['mac']=self._mac(value,True);return canonical_bytes(value)
    def decode_proof(self,raw,expected_kind=None):
        self._check_context()
        value=decode_canonical(raw)
        _require(type(value) is dict,message='external envelope')
        if value.get('schema')==ROOT_SCHEMA:
            _require(set(value)=={'schema','kind','payload'} and value['kind'] in STATIC_KINDS,message='root proof')
        else:
            _require(set(value)=={'schema','kind','issuer','role','key_id','clock','issued_ns','payload','mac'} and value['schema']==EXTERNAL_SCHEMA,message='external envelope')
            _require(value['key_id']==self.key_id and value['clock']==self.clock,'IDENTITY','external key/clock')
            _check_type('Process',value['issuer']);_check_type('Ns',value['issued_ns']);_check_type('Hash',value['mac']);_proof_role(value['kind'],value['role'])
            self._authenticate(raw,value,True)
        _require(expected_kind is None or value['kind']==expected_kind,message='external kind mismatch')
        _check_payload(value['kind'],value['payload'],True);_semantics(value['kind'],value['payload']);return value

_NATIVE_SEMANTIC_LOADER=object()

def _native_semantic_exchange(exchange):
    # This exact source-owned type is constructed only by its native inherited
    # pipe receiver. Neither a mapping of hashes nor a duck-typed verifier can
    # substitute for the actual C parent/process/source/dispatch-bound exchange.
    from .failed_fenced_startup import NativeSemanticExchange
    _require(type(exchange) is NativeSemanticExchange,'AUTHORITY','native semantic exchange required')
    exchange.require_current()
    return exchange

class NativeVerifiedCodec(RecoveryCodec):
    """Read-only semantics for bytes already authenticated by the native parent.

    No control token, derived role key or signing operation exists in this
    helper. Authentication is limited to the single actual native exchange;
    issuer/subject, schema and separately pinned human authority checks still
    run through the ordinary closed validators.
    """
    def __init__(self,exchange,*,_loader=None):
        _require(_loader is _NATIVE_SEMANTIC_LOADER,'AUTHORITY','native semantic loader required')
        self._exchange=_native_semantic_exchange(exchange)
        self._static_reader=(getattr(exchange,'stage',None)=='GUARD_ADMISSION'
                             and exchange.key_id is None and exchange.control_pid is None
                             and exchange._body['custody'] is None)
        if not self._static_reader:_check_type('Hash',exchange.key_id)
        _check_type('Clock',exchange.clock)
        _check_type('Process',exchange.controller);_check_type('Process',exchange.helper)
        _require(self._static_reader or (re.fullmatch(r'[1-9][0-9]*',exchange.control_pid) is not None
                 and int(exchange.control_pid)>=2),'IDENTITY','native custody PID')
        self.key_id=exchange.key_id;self.pid=exchange.control_pid;self.clock=_copy(exchange.clock)
        self._historical_claim=None;self._historical_controls={}
    def for_historical_claim(self,store,raw):
        """Read-only key/clock view of one exact retained, C-authenticated slot.

        The controller verifies the wrapper against that slot's fixed custody;
        no historical role secret, hash allowlist or alternative root reaches
        the helper. Full original attribution and READY semantics follow.
        """
        self._check_context()
        _require(type(store) is NativeReadOnlyStore and store._exchange is self._exchange,
                 'IDENTITY','native historical store changed')
        value=decode_canonical(raw)
        _require(type(value) is dict and value.get('kind')=='CLAIM',
                 'IDENTITY','historical exact claim required')
        self._exchange.authenticate(raw,external=False)
        payload=value['payload'];slot=payload['slot']
        _require(store.read_reservation(slot,'claim')==raw
                 and slot_key(payload['binding']['lineage'])==slot,
                 'IDENTITY','historical claim publication changed')
        result=NativeVerifiedCodec(self._exchange,_loader=_NATIVE_SEMANTIC_LOADER)
        result.key_id=value['key_id'];result.clock=_copy(value['clock'])
        result.pid=payload['binding']['lineage']['predecessor']['pid']
        result._historical_claim=(store,slot,raw,result.key_id,result.pid,canonical_bytes(result.clock))
        result.decode(raw,'CLAIM')
        return result
    def _check_context(self):
        _native_semantic_exchange(self._exchange)
        if self._historical_claim is None:
            _require(self.key_id==self._exchange.key_id and self.pid==self._exchange.control_pid
                     and self.clock==self._exchange.clock,'IDENTITY','native context changed')
        else:
            store,slot,raw,key,pid,clock=self._historical_claim
            _require(self.key_id==key and self.pid==pid and canonical_bytes(self.clock)==clock
                     and store.read_reservation(slot,'claim')==raw,
                     'IDENTITY','native historical context changed')
    def _authenticate(self,raw,value,external=False):
        self._check_context()
        _require(not self._static_reader or self._historical_claim is not None,
                 'AUTHORITY','static reader has no current operational key')
        self._exchange.authenticate(raw,external=external)
        if self._historical_claim is not None and external and value['kind']=='CONTROL_BINDING':
            # C's finite VERIFY adapter checks actual fixed historical custody
            # in addition to the MAC for this exact proof. A payload alone can
            # never be promoted into that observation.
            self._historical_controls[canonical_bytes(value['payload'])]=raw
    def _mac(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper has no role key')
    def encode(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper cannot issue records')
    def encode_proof(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper cannot issue proofs')
    def matches_control(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper cannot receive control bytes')
    def verify_control_binding(self,payload,store):
        self._check_context()
        _require(type(store) is NativeReadOnlyStore and store._exchange is self._exchange,
                 'IDENTITY','semantic custody context mismatch')
        if self._historical_claim is None:
            _require(not self._static_reader,'AUTHORITY','static reader has no control custody')
            self._exchange.verify_custody(payload)
        else:
            raw=self._historical_controls.get(canonical_bytes(payload))
            _require(raw is not None and payload['process']['pid']==self.pid
                     and payload['live_control']['hash']==payload['retained_control']['hash']==self.key_id
                     and payload['live_control']['bytes']==payload['retained_control']['bytes']
                     and payload['boot_id']==self.clock['boot_id'],
                     'IDENTITY','historical custody proof not authenticated')
            self._exchange.authenticate(raw,external=True)


_STATIC_PREPARATION_LOADER=object()


class StaticPreparationCodec(RecoveryCodec):
    """Only the three approved static roots; no current control or role key.

    Ordinary first entry validates its existing offline preparation before it
    constructs a predecessor. Historical slots use separate original codecs;
    this decoder cannot authenticate, issue or consume an operational record.
    """
    def __init__(self,preparation,*,_loader=None):
        _require(_loader is _STATIC_PREPARATION_LOADER and type(preparation) is PreparationContext,
                 'AUTHORITY','static prepared decoder required')
        self._preparation=preparation;self._record=canonical_bytes(preparation.record)
        self.clock=_copy(preparation.record['clock']);self.key_id=None;self.pid=None
    @classmethod
    def from_preparation(cls,preparation):
        return cls(preparation,_loader=_STATIC_PREPARATION_LOADER)
    def _check_context(self):
        _require(canonical_bytes(self._preparation.record)==self._record
                 and self.clock==self._preparation.record['clock'] and self.key_id is None and self.pid is None,
                 'IDENTITY','static prepared decoder changed')
    def decode_proof(self,raw,expected_kind=None):
        self._check_context();value=decode_canonical(raw)
        _require(type(value) is dict and value.get('schema')==ROOT_SCHEMA
                 and value.get('kind') in STATIC_KINDS,'AUTHORITY','static roots only')
        return super().decode_proof(raw,expected_kind)
    def _denied(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','static decoder has no operational or key authority')
    decode=encode=encode_proof=_mac=_authenticate=matches_control=_denied

class RecoveryBudget:
    """One immutable qualified CLOCK_MONOTONIC origin; expiry is sticky."""
    def __init__(self,clock,origin_ns,stop_deadline_ns):
        _check_type('Clock',clock);_check_type('Ns',str(origin_ns));_check_type('Ns',str(stop_deadline_ns))
        self.clock=_copy(clock);self.origin_ns=int(origin_ns);self.stop_deadline_ns=int(stop_deadline_ns)
        _require(self.stop_deadline_ns==self.origin_ns+15_000_000_000<=MAX_U64,'TIMEOUT','stop budget')
        self._last_ns=self.origin_ns;self._failure=False;self.work_deadline_ns=None
    def now_ns(self):
        now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if now<self._last_ns or now>MAX_U64: self._failure=True
        self._last_ns=max(now,self._last_ns)
        _require(not self._failure,'TIMEOUT','clock regression or prior expiry');return now
    def check(self,deadline_ns=None):
        now=self.now_ns();deadline=self.stop_deadline_ns if deadline_ns is None else min(int(deadline_ns),self.stop_deadline_ns)
        if now>=deadline:self._failure=True
        _require(not self._failure,'TIMEOUT','shared deadline expired');return now
    def remaining_seconds(self,deadline_ns=None):
        now=self.check(deadline_ns);deadline=self.stop_deadline_ns if deadline_ns is None else min(int(deadline_ns),self.stop_deadline_ns)
        return (deadline-now)/1_000_000_000
    def claim(self,claim_ns):
        _require(self.work_deadline_ns is None,'TIMEOUT','claim budget already fixed')
        self.check();_require(self.origin_ns<=int(claim_ns)<=self._last_ns,'TIMEOUT','claim timestamp')
        self.work_deadline_ns=min(int(claim_ns)+10_000_000_000,self.stop_deadline_ns);return self.work_deadline_ns
    def fresh(self,record,now_ns=None):
        now=self.check() if now_ns is None else int(now_ns)
        issued=int(record['issued_ns'])
        _require(issued<=now<=issued+45_000_000_000,'TIMEOUT','proof freshness')

class RecoveryStore:
    """Fixed private estate, no-follow descriptors and exclusive durable writes.

    Construction never provisions or repairs an estate. Call provision only in
    the separately authorized installation preparation, before capable startup.
    """
    def __init__(self,estate: Path):
        self.estate=Path(estate);_require(self.estate.is_absolute(),'DURABILITY','absolute canonical estate required')
        self.root=self.estate/'recovery-v1'
        self._sealed=False
    @staticmethod
    def _metadata(fd,directory=False):
        s=os.fstat(fd);expected=0o700 if directory else 0o600
        _require((stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)) and stat.S_IMODE(s.st_mode)==expected and s.st_uid==os.getuid() and (directory or s.st_nlink==1),'DURABILITY','private file metadata')
        # APFS directory link counts may change when this very publication adds
        # an entry. Inode, mode and owner must remain stable; the single-link
        # requirement applies to regular files, not directory entry counts.
        return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,0 if directory else s.st_nlink)
    def _active_read_directory_scope(self):
        scope=_read_directory_scope.get()
        if (scope is not None and scope['active'] and scope['store'] is self
                and scope['thread']==get_ident()):
            _require(self.root==scope['root'],'DURABILITY','read root identity changed')
            scope['deadline']()
            return scope
        return None
    @contextmanager
    def _read_directories(self,check_deadline):
        """Pin one no-follow root only for a closed read-only proof operation.

        Every file is still freshly opened/read/hashed and name/inode checked.
        Root metadata is checked on each use; the complete canonical ancestry
        is independently reopened at entry and exit before any result escapes.
        A changed path or root denies the whole operation. No fd survives it.
        """
        _require(self._active_read_directory_scope() is None,'DURABILITY','nested read directory scope')
        check_deadline();root=self._dir()
        try:identity=self._metadata(root,True)
        except BaseException:
            os.close(root);raise
        scope={'store':self,'thread':get_ident(),'active':True,'root':self.root,
               'fd':root,'identity':identity,'deadline':check_deadline}
        token=_read_directory_scope.set(scope)
        try:
            yield
            _require(scope is self._active_read_directory_scope(),'DURABILITY','read scope changed')
            _require(self._metadata(root,True)==identity,'DURABILITY','retained read root changed')
            scope['active']=False
            fresh=self._dir()
            try:_require(self._metadata(fresh,True)==identity,'DURABILITY','canonical read root replaced')
            finally:os.close(fresh)
            check_deadline()
        finally:
            scope['active']=False;_read_directory_scope.reset(token);os.close(root)
    def _dir(self,parts=()):
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
        scope=self._active_read_directory_scope()
        if scope is not None:
            _require(self._metadata(scope['fd'],True)==scope['identity'],'DURABILITY','retained read root changed')
            fd=os.dup(scope['fd'])
            try:
                for part in parts:
                    _require(type(part) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,160}',part) is not None,'DURABILITY','fixed estate component')
                    child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child;self._metadata(fd,True)
                return fd
            except BaseException:
                os.close(fd);raise
        # Verify each ancestor as a directory without following a symlink. Only
        # the service estate and its recovery children require private modes.
        fd=os.open('/',flags)
        try:
            for index,part in enumerate(self.root.parts[1:],start=1):
                child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child
                if index==len(self.estate.parts)-1:self._metadata(fd,True)
            self._metadata(fd,True)
            for part in parts:
                _require(type(part) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,160}',part) is not None,'DURABILITY','fixed estate component')
                child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child;self._metadata(fd,True)
            return fd
        except BaseException:
            os.close(fd);raise
    def _mkdir(self,parent,name):
        _require(self._active_read_directory_scope() is None,'DURABILITY','mutation during read-only proof scope')
        fd=self._dir(parent)
        try:
            os.mkdir(name,0o700,dir_fd=fd);os.fsync(fd)
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:self._metadata(child,True);os.fsync(child)
            finally:os.close(child)
        finally:os.close(fd)
    @classmethod
    def _file_snapshot(cls,fd):
        identity=cls._metadata(fd);value=os.fstat(fd)
        return identity+(value.st_size,value.st_mtime_ns,value.st_ctime_ns)
    @classmethod
    def _check_named_file(cls,parent,name,fd,snapshot):
        _require(cls._file_snapshot(fd)==snapshot,'DURABILITY','private file changed during access')
        value=os.stat(name,dir_fd=parent,follow_symlinks=False)
        _require((value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_nlink,
                  value.st_size,value.st_mtime_ns,value.st_ctime_ns)==snapshot,
                 'DURABILITY','private filename changed during access')
    def provision(self,guard_scope,expected_hash):
        _require(self._active_read_directory_scope() is None,'DURABILITY','mutation during read-only proof scope')
        _check_type('GuardScope',guard_scope);raw=canonical_bytes(guard_scope)
        _require(sha256(raw).hexdigest()==expected_hash,'AUTHORITY','sentinel pin')
        # This primitive is deliberately exclusive. A partial provisioning is
        # retained and must be denied; this API never repairs it.
        parent=os.open(self.estate,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            self._metadata(parent,True);os.mkdir('recovery-v1',0o700,dir_fd=parent);os.fsync(parent)
        finally:os.close(parent)
        for name in ('custody','guards','slots','records','blobs','preparation'):self._mkdir((),name)
        self._mkdir(('preparation',),'records')
        self._write((),'guard-scope.json',raw)
    def _write(self,parts,name,raw):
        _require(self._active_read_directory_scope() is None,'DURABILITY','mutation during read-only proof scope')
        _require(type(raw) is bytes and len(raw)<=16*MAX_RECORD,'DURABILITY','stored bytes bound')
        _require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,160}',name) is not None,'DURABILITY','fixed filename')
        fd=self._dir(parts);before=self._metadata(fd,True)
        try:
            file_fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd)
            try:
                identity=self._metadata(file_fd)
                offset=0
                while offset<len(raw):
                    n=os.write(file_fd,raw[offset:]);_require(n>0,'DURABILITY','short write');offset+=n
                os.fsync(file_fd);_require(self._metadata(file_fd)==identity,'DURABILITY','write inode changed')
                published=self._file_snapshot(file_fd)
                self._check_named_file(fd,name,file_fd,published)
            finally:os.close(file_fd)
            os.fsync(fd);_require(self._metadata(fd,True)==before,'DURABILITY','directory changed')
            read_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:
                self._check_named_file(fd,name,read_fd,published)
                result=self._read_fd(read_fd,len(raw)+1)
                _require(result==raw,'DURABILITY','exact readback failed')
                self._check_named_file(fd,name,read_fd,published)
            finally:os.close(read_fd)
            check=self._dir(parts)
            try:_require(self._metadata(check,True)==before,'DURABILITY','directory replacement')
            finally:os.close(check)
        except OSError as exc:raise RecoveryError('DURABILITY','exclusive immutable publication failed') from exc
        finally:os.close(fd)
        return raw
    @staticmethod
    def _read_fd(fd,limit):
        chunks=[];length=0
        while True:
            chunk=os.read(fd,min(65536,limit-length))
            if not chunk:break
            chunks.append(chunk);length+=len(chunk)
            _require(length<limit,'DURABILITY','file size bound')
        return b''.join(chunks)
    def _read(self,parts,name,limit=MAX_RECORD+1):
        fd=self._dir(parts);directory=self._metadata(fd,True)
        try:
            file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:
                before=self._file_snapshot(file_fd)
                self._check_named_file(fd,name,file_fd,before)
                raw=self._read_fd(file_fd,limit)
                self._check_named_file(fd,name,file_fd,before)
            finally:os.close(file_fd)
            _require(self._metadata(fd,True)==directory,'DURABILITY','read directory changed')
            check=self._dir(parts)
            try:_require(self._metadata(check,True)==directory,'DURABILITY','read directory replaced')
            finally:os.close(check)
            return raw
        except OSError as exc:raise RecoveryError('DURABILITY','required private file unreadable') from exc
        finally:os.close(fd)
    def write_blob(self,identity,raw):
        _require(not self._sealed,'ACCOUNTING','external publication after SEAL')
        ref=blob_ref(identity,raw);self._write(('blobs',),ref['hash']+'.blob',raw);return ref
    def retain_blob(self,identity,raw):
        """Retain exact factual bytes, reusing only an identical immutable blob.

        This is not a retry, overwrite, record replay or reservation repair.
        A corrupt existing name or publication race remains a hard failure.
        """
        _require(not self._sealed,'ACCOUNTING','external publication after SEAL')
        ref=blob_ref(identity,raw)
        try:existing=self._read(('blobs',),ref['hash']+'.blob',16*MAX_RECORD+1)
        except RecoveryError as exc:
            if not isinstance(exc.__cause__,FileNotFoundError):raise
            return self.write_blob(identity,raw)
        _require(existing==raw,'DURABILITY','retained native bytes changed')
        return ref
    def read_blob(self,ref):
        _check_type('Blob', {k:ref[k] for k in ('identity','hash','bytes')})
        # Bootstrap's native/proof bytes have their sole approved location in
        # the three-member bootstrap publication, not a second blob copy.
        # An existing corrupt ordinary blob never falls back to another file.
        parent=self._dir(('blobs',))
        try:
            try:os.stat(ref['hash']+'.blob',dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:present=False
            else:present=True
        finally:os.close(parent)
        if present:
            raw=self._read(('blobs',),ref['hash']+'.blob',16*MAX_RECORD+1)
        else:
            directory=self._dir(('slots',))
            try:slots=sorted(os.listdir(directory))
            finally:os.close(directory)
            _require(len(slots)<=4096,'DURABILITY','bootstrap resolution bound')
            matches=[]
            for slot in slots:
                _check_type('Hash',slot)
                try:directory=self._dir(('slots',slot,'bootstrap'))
                except FileNotFoundError:continue
                try:names=set(os.listdir(directory))
                finally:os.close(directory)
                expected={ref['hash']+'.startup.json',ref['hash']+'.bootstrap.json'}
                if not names.intersection(expected):continue
                published=self.read_bootstrap(slot)
                matches.extend(value for key,value in published.items()
                               if key in {'native','proof'} and sha256(value).hexdigest()==ref['hash'])
            _require(len(matches)==1,'DURABILITY','missing or ambiguous bootstrap blob')
            raw=matches[0]
        _require(len(raw)==int(ref['bytes']) and sha256(raw).hexdigest()==ref['hash'],'DURABILITY','blob identity');return raw
    def publish(self,raw):
        ref=record_ref(raw)
        _require(not self._sealed or ref['kind'] in {'SEAL','OWNER_PROOF','CERTIFICATE','PREPARED_COMMIT'},'ACCOUNTING','publication after SEAL')
        _require(ref['kind'] not in {'ACK','COMPOSITION_AUTHORITY','CHILD_IDENTITY'},'PROTOCOL','transport or bootstrap record has fixed location')
        self._write(('records',),f"{ref['kind']}-{ref['hash']}.json",raw);return ref
    def resolve(self,ref):
        _check_type('Ref',ref)
        fixed={'GUARD':'guard','CLAIM':'claim','CHILD_INTENT':'child-intent','CHILD_IDENTITY':'child-identity','CONSUMPTION':'consumption'}
        if ref['kind'] in fixed:
            matches=[]
            area='guards' if ref['kind']=='GUARD' else 'slots'
            fd=self._dir((area,))
            try:names=sorted(os.listdir(fd))
            finally:os.close(fd)
            _require(len(names)<=4096,'PROVENANCE','slot enumeration bound')
            for slot in names:
                _check_type('Hash',slot)
                child=self._dir((area,slot))
                try:entries=os.listdir(child)
                finally:os.close(child)
                if fixed[ref['kind']] not in entries:continue
                candidate=self.read_reservation(slot,fixed[ref['kind']])
                if sha256(candidate).hexdigest()==ref['hash']:matches.append(candidate)
            _require(len(matches)==1,'PROVENANCE','missing/ambiguous fixed reservation')
            raw=matches[0]
        else:
            raw=self._read(('records',),f"{ref['kind']}-{ref['hash']}.json")
        _require(record_ref(raw)==ref,'DURABILITY','record hash');return raw
    def read_custody(self,key_id):
        _check_type('Hash',key_id);raw=self._read(('custody',),key_id+'.control',256)
        _require(sha256(raw).hexdigest()==key_id,'IDENTITY','custody digest');return raw
    def write_custody(self,private_control_bytes):
        _require(not self._sealed,'ACCOUNTING','custody after seal');key_id=sha256(private_control_bytes).hexdigest()
        self._write(('custody',),key_id+'.control',private_control_bytes);return key_id
    def reserve(self,slot,name,raw):
        _check_type('Hash',slot)
        _require(name in {'guard','claim','child-intent','child-identity','consumption'},message='reservation name')
        area='guards' if name=='guard' else 'slots'
        if name in {'guard','claim'}:self._mkdir((area,),slot)
        self._write((area,slot),name,raw)
    def read_reservation(self,slot,name):
        _check_type('Hash',slot);_require(name in {'guard','claim','child-intent','child-identity','consumption'},message='reservation name')
        return self._read(('guards' if name=='guard' else 'slots',slot),name)
    def enumerate_guards(self):
        result=[]
        root=self._dir()
        try:
            members=set(os.listdir(root))
            _require(members in ({'custody','guards','slots','records','blobs','preparation','guard-scope.json'}, {'custody','guards','slots','records','blobs','preparation','guard-scope.json','service.lock'}),'PROVENANCE','unknown or partial recovery estate')
        finally:os.close(root)
        for area in ('guards','slots'):
            fd=self._dir((area,))
            try:
                names=sorted(os.listdir(fd));_require(len(names)<=4096,'PROVENANCE','guard enumeration bound')
                for name in names:
                    _check_type('Hash',name);child=self._dir((area,name))
                    try:
                        entries=set(os.listdir(child));allowed={'guard'} if area=='guards' else {'claim','child-intent','child-identity','consumption','bootstrap'}
                        _require(entries<=allowed and ('guard' if area=='guards' else 'claim') in entries,'PROVENANCE','partial/unknown slot')
                    finally:os.close(child)
                if area=='guards':result=names
                else:_require(names==result,'PROVENANCE','guard/slot mismatch')
            finally:os.close(fd)
        return tuple(result)
    def publish_bootstrap(self,slot,native_raw,proof_raw,identity_raw,*,budget):
        # Same exclusive fixed files; directory lock exposes only the completed
        # publication to C, never an O_EXCL-created but not-yet-written identity.
        _check_type('Hash',slot);budget.check();fd=self._dir(('slots',slot))
        try:
            while True:
                budget.check()
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:time.sleep(min(.001,budget.remaining_seconds()))
            budget.check();self._mkdir(('slots',slot),'bootstrap')
            self._write(('slots',slot,'bootstrap'),sha256(native_raw).hexdigest()+'.startup.json',native_raw)
            budget.check()
            self._write(('slots',slot,'bootstrap'),sha256(proof_raw).hexdigest()+'.bootstrap.json',proof_raw)
            budget.check();self.reserve(slot,'child-identity',identity_raw);budget.check()
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
    def read_bootstrap(self,slot):
        _check_type('Hash',slot);fd=self._dir(('slots',slot,'bootstrap'))
        try:names=sorted(os.listdir(fd))
        finally:os.close(fd)
        native=[n for n in names if re.fullmatch(r'[0-9a-f]{64}\.startup\.json',n)]
        proof=[n for n in names if re.fullmatch(r'[0-9a-f]{64}\.bootstrap\.json',n)]
        _require(len(names)==2 and len(native)==len(proof)==1,'CHILD','bootstrap publication set')
        n=self._read(('slots',slot,'bootstrap'),native[0]);p=self._read(('slots',slot,'bootstrap'),proof[0])
        _require(sha256(n).hexdigest()==native[0][:64] and sha256(p).hexdigest()==proof[0][:64],'DURABILITY','bootstrap hash')
        return {'native':n,'proof':p,'identity':self.read_reservation(slot,'child-identity')}
    @contextmanager
    def service_lock(self,budget):
        fd=self._dir();lock_fd=None
        try:
            try:lock_fd=os.open('service.lock',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd);os.fsync(lock_fd);os.fsync(fd)
            except FileExistsError:lock_fd=os.open('service.lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            self._metadata(lock_fd)
            while True:
                budget.check()
                try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:time.sleep(min(.005,budget.remaining_seconds()))
            budget.check();yield
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd,fcntl.LOCK_UN);os.close(lock_fd)
            os.close(fd)

class NativeReadOnlyStore(RecoveryStore):
    """Private immutable reads only; custody remains exclusively with C.

    The native controller retains its execution/service lock and publishes
    every output. This helper may neither acquire/create a lock nor provision,
    repair, reserve or publish any part of the estate.
    """
    def __init__(self,exchange,*,_loader=None):
        _require(_loader is _NATIVE_SEMANTIC_LOADER,'AUTHORITY','native semantic loader required')
        self._exchange=_native_semantic_exchange(exchange)
        super().__init__(exchange.estate)
    def _dir(self,parts=()):
        self._exchange.require_current()
        _require(self.estate==Path(self._exchange.estate)
                 and self.root==self.estate/'recovery-v1',
                 'IDENTITY','semantic estate changed')
        _require(not parts or parts[0] in {'guards','slots','records','blobs','preparation'},
                 'AUTHORITY','semantic helper cannot read custody')
        return super()._dir(parts)
    def _read(self,parts,name,limit=MAX_RECORD+1):
        self._exchange.require_current()
        _require(parts or name=='guard-scope.json','AUTHORITY','semantic root read denied')
        raw=super()._read(parts,name,limit)
        self._exchange.require_current()
        return raw
    def _deny_write(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper is read-only')
    _mkdir=_write=provision=write_blob=publish=reserve=publish_bootstrap=write_custody=_deny_write
    service_lock=_deny_write
    def read_custody(self,*args,**kwargs):
        raise RecoveryError('AUTHORITY','semantic helper cannot read custody')

@dataclass(frozen=True)
class PreparationAnchors:
    """Independently approved, exact control-preparation identities.

    These values belong to canonical offline control preparation, never to an
    HTTP request, environment, proof payload or package's self-authentication.
    Native controllers obtain them through their fixed preparation selection.
    """
    pin: Mapping[str,str]
    approval: Mapping[str,str]
    catalogue: Mapping[str,str]
    decisions: tuple[Mapping[str,str], ...]

_PREPARATION_LOADER=object()

class PreparationContext:
    def __init__(self,record,catalogue,pin,approval,anchors,store,original=None,*,_loader=None):
        _require(_loader is _PREPARATION_LOADER,'AUTHORITY','preparation must pass independent pinned loader')
        self.record=_copy(record);self.catalogue=_copy(catalogue);self.pin=_copy(pin);self.preparation_approval=_copy(approval)
        self.anchors=anchors;self.store=store;self.original=original
        self.rows={r['identity']:r for r in catalogue['rows']}
    @classmethod
    def load(cls,store,*,mode,service,installation,lineage,attempt,anchors,original=None):
        _require(type(anchors) is PreparationAnchors,'AUTHORITY','independently pinned preparation required')
        selector={'mode':mode,'service':service,'installation':installation,'lineage':lineage,'attempt':attempt}
        selection=sha256(canonical_bytes(selector)).hexdigest()
        pinraw=store._read(('preparation',),selection+'.pin');approvalraw=store._read(('preparation',),selection+'.approval')
        for raw,ref in ((pinraw,anchors.pin),(approvalraw,anchors.approval)):
            _check_type('Blob',dict(ref));_require(len(raw)==int(ref['bytes']) and sha256(raw).hexdigest()==ref['hash'],'AUTHORITY','preparation independent pin')
        pin=decode_canonical(pinraw);approval=decode_canonical(approvalraw)
        _check_type('PreparationPin',pin);_check_type('PreparationApproval',approval)
        _require(all(pin[k]==v for k,v in selector.items()),'IDENTITY','derived preparation selection')
        _require(approval['pin']==dict(anchors.pin) and approval['preparation']==pin['preparation'],'AUTHORITY','preparation approval binding')
        _require(pin['catalogue']==dict(anchors.catalogue),'AUTHORITY','catalogue pin')
        def retained(ref):
            raw=store._read(('preparation','records'),ref['hash']+'.json')
            _require(len(raw)==int(ref['bytes']) and sha256(raw).hexdigest()==ref['hash'],'AUTHORITY','preparation retained bytes');return decode_canonical(raw)
        record=retained(pin['preparation']);catalogue=retained(pin['catalogue'])
        _check_type('ControlPreparation',record);_check_type('ApprovalCatalogue',catalogue)
        _require(all(record[k]==v for k,v in selector.items()) and record['catalogue']==pin['catalogue'],'AUTHORITY','preparation fields')
        _require(catalogue['service']==service and catalogue['scope']['hash']==SCOPE_HASH and catalogue['appendix']['hash']==APPENDIX_HASH,'AUTHORITY','catalogue scope/appendix')
        _ordered(catalogue['rows']);_ordered(approval['attributions'],'authority')
        authorities={'CA','PCP'} | ({'SPONSOR'} if mode=='RECOVERY' else set())
        _require({x['authority'] for x in approval['attributions']}==authorities,'AUTHORITY','preparation attribution roster')
        decision_refs={canonical_bytes(dict(x)) for x in anchors.decisions}
        for item in approval['attributions']:
            _require(canonical_bytes(item['decision']) in decision_refs,'AUTHORITY','unattributed preparation approval')
            store.read_blob(item['decision'])
        for row in catalogue['rows']:
            _require(row['bindings']['kind']==row['purpose'],'AUTHORITY','approval purpose')
            _require(canonical_bytes(row['attribution']) in decision_refs,'AUTHORITY','unattributed catalogue row')
            store.read_blob(row['attribution']);store.read_blob(row['artifact'])
            if row['purpose']=='OWNER_SCOPE':_require(row['bindings']['owner']==row['authority'],'AUTHORITY','scope approval owner')
        if mode=='ORIGINAL':_require(record['original_preparation'] is None and original is None,'AUTHORITY','original preparation cycle')
        else:
            _require(type(original) is PreparationContext and original.record['mode']=='ORIGINAL' and record['original_preparation']==original.pin['preparation'],'AUTHORITY','original preparation dependency')
            _require(original.record['lineage']==lineage and original.record['control_hash']==record['control_hash'],'IDENTITY','original preparation lineage')
        return cls(record,catalogue,pin,approval,anchors,store,original,_loader=_PREPARATION_LOADER)
    def approval(self,identity,*,purpose,authority=None,bindings=None):
        row=self.rows.get(identity)
        _require(row is not None and row['purpose']==purpose and (authority is None or row['authority']==authority),'AUTHORITY','unapproved purpose/authority')
        if bindings is not None:_require(row['bindings']==bindings,'AUTHORITY','approval exact bindings')
        return row
    def matching_approval(self,purpose,authority,bindings):
        found=[r for r in self.rows.values() if r['purpose']==purpose and r['authority']==authority and r['bindings']==bindings]
        _require(len(found)==1,'AUTHORITY','missing/ambiguous exact approval');return found[0]

def _fixed_preparation_entries(store):
    """Enumerate only the approved immutable preparation namespace."""
    _require(type(store) in {RecoveryStore, NativeReadOnlyStore}, 'AUTHORITY', 'fixed preparation store')
    fd = store._dir(('preparation',))
    before = store._metadata(fd, True)
    try:
        names = os.listdir(fd)
        _require(len(names) <= 8193 and len(names) == len(set(names)),
                 'AUTHORITY', 'preparation namespace bound')
        _require(all(name == 'records' or re.fullmatch(r'[0-9a-f]{64}\.(pin|approval)', name)
                     for name in names), 'AUTHORITY', 'unknown preparation entry')
        pins = sorted(name[:-4] for name in names if name.endswith('.pin'))
        _require(set(names) == {'records'} | {key + suffix for key in pins for suffix in ('.pin', '.approval')},
                 'AUTHORITY', 'partial preparation publication')
        rows = []
        for key in pins:
            pinraw = store._read(('preparation',), key + '.pin')
            approvalraw = store._read(('preparation',), key + '.approval')
            pin = decode_canonical(pinraw); approval = decode_canonical(approvalraw)
            _check_type('PreparationPin', pin); _check_type('PreparationApproval', approval)
            selector = {field: pin[field] for field in ('mode', 'service', 'installation', 'lineage', 'attempt')}
            _require(sha256(canonical_bytes(selector)).hexdigest() == key,
                     'AUTHORITY', 'preparation filename selection')
            recordraw = store._read(('preparation', 'records'), pin['preparation']['hash'] + '.json')
            _require(blob_ref(pin['preparation']['identity'], recordraw) == pin['preparation'],
                     'AUTHORITY', 'preparation record bytes')
            record = decode_canonical(recordraw); _check_type('ControlPreparation', record)
            _require(all(record[field] == value for field, value in selector.items()),
                     'IDENTITY', 'preparation selector fields')
            _require(approval['pin'] == blob_ref(approval['pin']['identity'], pinraw)
                     and approval['preparation'] == pin['preparation'],
                     'AUTHORITY', 'preparation approval publication binding')
            rows.append((selector, pinraw, approvalraw, pin, approval, record))
        _require(sorted(os.listdir(fd)) == sorted(names) and store._metadata(fd, True) == before,
                 'DURABILITY', 'preparation namespace changed')
        reopened = store._dir(('preparation',))
        try: _require(store._metadata(reopened, True) == before, 'DURABILITY', 'preparation parent replaced')
        finally: os.close(reopened)
        return rows
    finally:
        os.close(fd)


def publish_reviewed_preparation(store, *, pin_raw, approval_raw, preparation_raw,
                                 catalogue_raw, anchors, retained, budget):
    """Trusted offline preparation's exclusive byte publisher (§1A).

    ``anchors`` is the independently reviewed exact-byte input to this local
    preparation operation, as with PreparationContext.load; no runtime endpoint,
    environment or catalogue may populate it. The caller must already possess
    the original attributable decisions obtained through their owner channels.
    This function does not read APPROVED text, infer a human decision, mint an
    approval, or substitute token possession for that offline verification.
    Its output is only the existing approved pin/approval/records estate.
    """
    _require(type(store) is RecoveryStore and type(anchors) is PreparationAnchors
             and type(budget) is RecoveryBudget, 'AUTHORITY', 'reviewed offline preparation inputs')
    for raw, ref in ((pin_raw, anchors.pin), (approval_raw, anchors.approval),
                     (catalogue_raw, anchors.catalogue)):
        _check_type('Blob', dict(ref))
        _require(type(raw) is bytes and blob_ref(ref['identity'], raw) == dict(ref),
                 'AUTHORITY', 'offline independently reviewed bytes changed')
    pin, approval = decode_canonical(pin_raw), decode_canonical(approval_raw)
    record, catalogue = decode_canonical(preparation_raw), decode_canonical(catalogue_raw)
    for kind, value in (('PreparationPin', pin), ('PreparationApproval', approval),
                        ('ControlPreparation', record), ('ApprovalCatalogue', catalogue)):
        _check_type(kind, value)
    selector = {key: pin[key] for key in ('mode', 'service', 'installation', 'lineage', 'attempt')}
    _require(all(record[key] == value for key, value in selector.items())
        and pin['preparation'] == blob_ref(record['identity'], preparation_raw)
        and pin['catalogue'] == dict(anchors.catalogue) == record['catalogue']
        and approval['pin'] == dict(anchors.pin) and approval['preparation'] == pin['preparation']
        and catalogue['service'] == pin['service'] and catalogue['scope']['hash'] == SCOPE_HASH
        and catalogue['appendix']['hash'] == APPENDIX_HASH,
        'AUTHORITY', 'offline complete preparation binding')
    _ordered(catalogue['rows']); _ordered(approval['attributions'], 'authority')
    required = {'CA', 'PCP'} | ({'SPONSOR'} if pin['mode'] == 'RECOVERY' else set())
    _require({row['authority'] for row in approval['attributions']} == required,
             'AUTHORITY', 'offline decisive preparation approvals required')
    decisions = {canonical_bytes(dict(ref)) for ref in anchors.decisions}
    for ref in anchors.decisions: _check_type('Blob', dict(ref))
    _require(type(retained) is tuple and all(type(row) is tuple and len(row) == 2 for row in retained),
             'AUTHORITY', 'offline retained exact blobs')
    by_hash = {}
    for ref, raw in retained:
        _check_type('Blob', ref)
        _require(type(raw) is bytes and blob_ref(ref['identity'], raw) == ref,
                 'AUTHORITY', 'offline retained bytes changed')
        _require(ref['hash'] not in by_hash, 'AUTHORITY', 'duplicate offline retained bytes')
        by_hash[ref['hash']] = (ref, raw)
    refs = [item['decision'] for item in approval['attributions']]
    refs.extend(item['attribution'] for item in catalogue['rows'])
    _require(all(canonical_bytes(ref) in decisions for ref in refs),
             'AUTHORITY', 'offline unreviewed attribution')
    for ref in (*anchors.decisions, *(row['artifact'] for row in catalogue['rows'])):
        _require(ref['hash'] in by_hash and by_hash[ref['hash']][0] == dict(ref),
                 'AUTHORITY', 'offline original decision or artifact unavailable')
    guard = decode_canonical(store._read((), 'guard-scope.json')); _check_type('GuardScope', guard)
    _require(guard['service'] == pin['service'] and guard['installation'] == pin['installation'],
             'IDENTITY', 'offline canonical installation')
    selection = sha256(canonical_bytes(selector)).hexdigest()
    with store.service_lock(budget):
        for ref, raw in retained:
            budget.check()
            try:
                existing = store._read(('blobs',), ref['hash'] + '.blob', 16 * MAX_RECORD + 1)
            except RecoveryError as exc:
                if not isinstance(exc.__cause__, FileNotFoundError): raise
                store.write_blob(ref['identity'], raw)
            else:
                _require(existing == raw, 'DURABILITY', 'offline immutable blob changed')
        for ref, raw in ((pin['catalogue'], catalogue_raw), (pin['preparation'], preparation_raw)):
            budget.check()
            try:
                existing = store._read(('preparation', 'records'), ref['hash'] + '.json')
            except RecoveryError as exc:
                if not isinstance(exc.__cause__, FileNotFoundError): raise
                store._write(('preparation', 'records'), ref['hash'] + '.json', raw)
            else:
                _require(existing == raw, 'DURABILITY', 'offline immutable record changed')
        budget.check(); store._write(('preparation',), selection + '.pin', pin_raw)
        budget.check(); store._write(('preparation',), selection + '.approval', approval_raw)
        budget.check()
    # No operational helper, reservation, dispatch, source or guard repair is
    # performed by this publisher. A partial publication remains a denial.
    return load_native_preparation(store, controller=record['controller'], mode=pin['mode'],
                                   lineage=pin['lineage'], attempt=pin['attempt'])


def load_native_preparation(store, *, controller, mode, lineage=None, attempt=None):
    """Select the trusted preparer's existing fixed publication, never a hint.

    The caller is the fixed native controller/child entry and supplies actual
    kernel identity, not request-selected hashes. PreparationAnchors is merely
    the internal exact-byte view of the already approved §1A publication; it is
    not a fourth persisted trust root. Human provenance is established by the
    separately authorized offline publisher, never by parsing APPROVED text.
    """
    _check_type('Process', controller)
    _require(mode in {'ORIGINAL', 'RECOVERY'}, 'AUTHORITY', 'preparation mode')
    if lineage is not None: _check_type('Lineage', lineage)
    if attempt is not None: _check_type('Id', attempt)
    guard = decode_canonical(store._read((), 'guard-scope.json')); _check_type('GuardScope', guard)
    entries = _fixed_preparation_entries(store)
    matches = [row for row in entries if row[0]['mode'] == mode
               and row[5]['controller'] == controller
               and row[0]['service'] == guard['service'] and row[0]['installation'] == guard['installation']
               and (lineage is None or row[0]['lineage'] == lineage)
               and (attempt is None or row[0]['attempt'] == attempt)]
    _require(len(matches) == 1, 'AUTHORITY', 'missing or ambiguous native preparation')
    def context(row, original=None):
        selector, pinraw, approvalraw, pin, approval, record = row
        catalogue_raw = store._read(('preparation', 'records'), pin['catalogue']['hash'] + '.json')
        _require(blob_ref(pin['catalogue']['identity'], catalogue_raw) == pin['catalogue'],
                 'AUTHORITY', 'catalogue exact publication bytes')
        catalogue = decode_canonical(catalogue_raw); _check_type('ApprovalCatalogue', catalogue)
        refs = [item['decision'] for item in approval['attributions']]
        refs.extend(item['attribution'] for item in catalogue['rows'])
        unique = {canonical_bytes(ref): ref for ref in refs}
        anchors = PreparationAnchors(blob_ref(approval['pin']['identity'], pinraw),
            blob_ref('preparation-approval-' + sha256(approvalraw).hexdigest(), approvalraw),
            pin['catalogue'], tuple(unique[key] for key in sorted(unique)))
        return PreparationContext.load(store, **selector, anchors=anchors, original=original)
    selected = matches[0]
    if mode == 'ORIGINAL': return context(selected)
    original_ref = selected[5]['original_preparation']
    originals = [row for row in entries if row[0]['mode'] == 'ORIGINAL'
                 and row[3]['preparation'] == original_ref and row[0]['lineage'] == selected[0]['lineage']
                 and row[0]['service'] == selected[0]['service'] and row[0]['installation'] == selected[0]['installation']]
    _require(len(originals) == 1, 'AUTHORITY', 'recovery original preparation missing or ambiguous')
    return context(selected, context(originals[0]))


def load_static_native_preparation(store, *, controller, clock, key_id, helper_plan):
    """Read-only installation gate from the existing trusted fixed pin estate.

    A historical preparation's controller remains historical. The actual
    current C identity selects only matching independently qualified executable,
    package and helper bytes; it acquires no operation, capability or ledger.
    """
    _check_type('Process',controller);_check_type('Clock',clock)
    if key_id is not None:_check_type('Hash',key_id)
    _check_type('Blob',helper_plan)
    matches=[]
    for selector,_pinraw,_approvalraw,_pin,_approval,record in _fixed_preparation_entries(store):
        if record['mode']!='ORIGINAL' or record['clock']!=clock or key_id is not None and record['control_hash']!=key_id:
            continue
        prep=load_native_preparation(store,controller=record['controller'],mode='ORIGINAL',
            lineage=selector['lineage'],attempt=selector['attempt'])
        artifacts=[row for row in prep.rows.values() if row['authority']=='CA' and row['purpose']=='ARTIFACT'
            and row['bindings']['executable']['hash']==controller['runtime']
            and row['bindings']['package']==record['launcher_package']
            and row['bindings']['bootstrap_plan']==helper_plan]
        guards=[row for row in prep.rows.values() if row['authority']=='CA' and row['purpose']=='GUARD'
            and row['bindings']['launcher']['hash']==controller['runtime']
            and row['bindings']['classification']=='MANDATORY'
            and any(peer['authority']=='PCP' and peer['purpose']=='GUARD'
                and peer['bindings']==row['bindings'] for peer in prep.rows.values())]
        if len(artifacts)==1 and len(guards)==1:
            matches.append((prep,guards[0]['artifact']))
        elif artifacts or guards:
            _require(False,'AUTHORITY','ambiguous static native installation')
    _require(len(matches)==1,'AUTHORITY','missing or ambiguous static native preparation')
    return matches[0]


class NativeSemanticContext:
    """Fixed assembly of the native helper's read-only validation context.

    This is an internal call context, never a serialized approval, new record
    kind, composition grant or an alternative authentication protocol.
    """
    def __init__(self,exchange,codec,store,registry,*,_loader=None):
        _require(_loader is _NATIVE_SEMANTIC_LOADER,'AUTHORITY','native semantic factory required')
        self.exchange=exchange;self.codec=codec;self.store=store;self.registry=registry
        self.budget=exchange.budget
    @classmethod
    def from_exchange(cls,exchange):
        exchange=_native_semantic_exchange(exchange)
        codec=NativeVerifiedCodec(exchange,_loader=_NATIVE_SEMANTIC_LOADER)
        store=NativeReadOnlyStore(exchange,_loader=_NATIVE_SEMANTIC_LOADER)
        selections=exchange.preparations
        if exchange.stage=='GUARD_ADMISSION':
            _require(exchange.action=='VERIFY_STATUS' and exchange.operation=='installation.guard'
                     and exchange.admission is None and exchange.dispatch is None
                     and exchange._body['controller_capability'] is None,
                     'AUTHORITY','static reader has no operational capability')
            prep,root=load_static_native_preparation(store,controller=exchange.controller,
                clock=codec.clock,key_id=codec.key_id,helper_plan=exchange._body['helper_plan'])
            _require(type(selections) in {tuple,list} and len(selections)==1,
                     'AUTHORITY','static historical selector assertion')
            selector=selections[0]
            _require(all(selector.get(name)==prep.record[name]
                         for name in ('mode','service','installation','lineage','attempt')),
                     'IDENTITY','static independently selected preparation changed')
            registry=EvidenceRegistry(codec,store,prep)
            applicability=registry.proof_evidence(store.read_blob(root))
            registry.verify(codec.clock['qualification'],'CLOCK_QUALIFICATION')
            registry.verify(applicability,'GUARD_APPLICABILITY')
            exchange.verify_preparation(registry)
            result=cls(exchange,codec,store,registry,_loader=_NATIVE_SEMANTIC_LOADER)
            result.guard_applicability=applicability
            return result
        _require(type(selections) in {list,tuple} and len(selections) in {1,2},
                 'AUTHORITY','native preparation chain')
        prior=None
        for index,selection in enumerate(selections):
            _require(type(selection) is dict and set(selection)=={
                'mode','service','installation','lineage','attempt','anchors'},
                'AUTHORITY','native preparation selector')
            _require(selection['mode']==('ORIGINAL' if index==0 else 'RECOVERY'),
                     'AUTHORITY','native preparation ordering')
            anchors=selection['anchors']
            _require(type(anchors) is dict and set(anchors)=={'pin','approval','catalogue','decisions'}
                     and type(anchors['decisions']) is list,'AUTHORITY','native independent anchors')
            # Legacy envelope refs are equality assertions only. Authority is
            # acquired independently from the fixed trusted preparation estate.
            if index == len(selections) - 1:
                prior = load_native_preparation(store, controller=exchange.controller,
                    mode=selection['mode'], lineage=selection['lineage'], attempt=selection['attempt'])
                _require(prior.record['service'] == selection['service']
                         and prior.record['installation'] == selection['installation'],
                         'IDENTITY', 'native fixed selection changed')
        _require(prior.record['controller']==exchange.controller
                 and prior.record['lineage']['predecessor']['pid']==codec.pid,
                 'IDENTITY','native controller/predecessor selection')
        registry=EvidenceRegistry(codec,store,prior)
        # The fixed native adapter checks actual parent image/source and actual
        # helper loaded bytes against this independently pinned preparation.
        # A role MAC or caller-provided list of hashes is never sufficient.
        exchange.verify_preparation(registry)
        if prior.record['mode']=='ORIGINAL':
            _require(exchange.admission is not None and exchange.dispatch is not None,
                     'ACCOUNTING','original helper dispatch missing')
            admission=registry.verify_blob(exchange.admission,'CONTROLLER_ADMISSION',
                                            context={'mode':'ORIGINAL'})['payload']
            dispatch=registry.verify_blob(exchange.dispatch,'CONTROLLER_DISPATCH',
                                           context={'mode':'ORIGINAL'})['payload']
            _require(admission['controller']==dispatch['controller']==exchange.controller
                     and admission['operation']==exchange.operation
                     and admission['action']==exchange.action
                     and dispatch['admission']==exchange.admission
                     and dispatch['state']=='DISPATCHED'
                     and dispatch['helper'] in (None,exchange.helper)
                     and exchange.budget.origin_ns<=int(admission['accepted_ns'])
                     <=int(dispatch['started_ns'])<=exchange.budget.check(),
                     'ACCOUNTING','actual original helper dispatch binding')
        else:
            # Appendix 1A assigns controller-ledger proofs to ORIGINAL only.
            # Current recovery helper ownership is the actual C dispatch;
            # historical ORIGINAL proofs cannot impersonate that controller.
            _require(exchange.admission is None and exchange.dispatch is None,
                     'AUTHORITY','recovery helper cannot transplant original ledger')
        exchange.require_current()
        return cls(exchange,codec,store,registry,_loader=_NATIVE_SEMANTIC_LOADER)

class EvidenceRegistry:
    """Finite field-selected proof adapters with independently prepared authority."""
    def __init__(self,codec,store,preparation):
        producer=type(codec) is RecoveryCodec and type(store) is RecoveryStore
        static=(type(codec) is StaticPreparationCodec and type(store) is RecoveryStore
                and codec._preparation is preparation)
        semantic=(type(codec) is NativeVerifiedCodec and type(store) is NativeReadOnlyStore
                  and codec._exchange is store._exchange)
        _require((producer or semantic or static) and type(preparation) is PreparationContext
                 and preparation.store is store,'AUTHORITY','typed evidence context')
        if semantic or static:codec._check_context()
        self.codec=codec;self.store=store;self.preparation=preparation
        self._native_contexts={}
        self._executor_witnesses={}
        self._validated_sources={}
        keyless=static or semantic and codec._static_reader and codec._historical_claim is None
        _require((keyless or preparation.record['control_hash']==codec.key_id)
                 and preparation.record['clock']==codec.clock,'IDENTITY','prepared key/clock')
    def bind_original_executor(self,witness):
        _require(type(witness) is OriginalExecutorWitness and witness.executor not in self._executor_witnesses,'ACCOUNTING','exact original executor witness')
        self._executor_witnesses[witness.executor]=witness
    def bind_native_ledger(self,ledger):
        _require(type(ledger) is ProspectiveLedger and ledger.codec is self.codec and ledger.store is self.store and self.preparation.record['lineage']['predecessor']==ledger.process,'IDENTITY','native ledger binding')
        existing=getattr(self,'_native_ledger',None)
        _require(existing is None or existing is ledger,'PROVENANCE','native ledger changed')
        self._native_ledger=ledger;self._native_composition=getattr(ledger,'native_composition',None)
        prior=ledger.registry
        if type(prior) is EvidenceRegistry and prior is not self:
            _require(self._prep(True).pin==prior._prep(True).pin,'AUTHORITY','native original preparation changed')
            for key,witness in prior._executor_witnesses.items():
                _require(key not in self._executor_witnesses or self._executor_witnesses[key] is witness,'ACCOUNTING','executor witness changed')
                self._executor_witnesses[key]=witness
    @property
    def native_ledger(self):return getattr(self,'_native_ledger',None)
    def bind_successor_runtime(self,witness):
        from .failed_fenced_startup import SuccessorReadyEvidence
        _require(type(witness) is SuccessorReadyEvidence and witness.session.codec is self.codec
                 and witness.session.store is self.store and witness.session.registry is self,
                 'AUTHORITY','exact successor runtime witness required')
        prior=getattr(self,'_successor_runtime',None)
        _require(prior is None or prior is witness,'PROVENANCE','successor runtime witness changed')
        witness.verify_native_binding()
        self._successor_runtime=witness
    def _prep(self,original=False):
        p=self.preparation
        if original and p.record['mode']!='ORIGINAL':p=p.original
        _require(type(p) is PreparationContext,'AUTHORITY','original preparation unavailable');return p
    @contextmanager
    def _readonly_validation(self):
        if type(self.codec) is NativeVerifiedCodec:
            _require(type(self.store) is NativeReadOnlyStore and self.store._exchange is self.codec._exchange,
                     'IDENTITY','exact native validation store')
            with self.codec._exchange._readonly_validation():
                yield
        else:
            yield
    def _active_composition_scope(self):
        scope=_composition_scope.get()
        if (scope is not None and scope['active'] and scope['registry'] is self
                and scope['thread']==get_ident() and scope['codec'] is self.codec
                and scope['store'] is self.store
                and scope['preparation'] is self.preparation):
            return scope
        return None
    @contextmanager
    def _composition_validation(self,check_deadline):
        """One closed read-only operation; only immutable structure is reused.

        Authentication, issuer, clock, source and live owner checks still run
        on every proof. All traversed inventory/listener bytes are freshly
        read and hashed before this scope can return successfully.
        """
        _require(type(self) is EvidenceRegistry,'AUTHORITY','read-only registry required')
        check_deadline()
        scope={'registry':self,'codec':self.codec,'store':self.store,'preparation':self.preparation,
               'thread':get_ident(),'active':True,'complete':set(),'dependencies':{}}
        with self.store._read_directories(check_deadline):
            token=_composition_scope.set(scope)
            try:
                yield
                _require(scope is self._active_composition_scope(),'IDENTITY','composition context changed')
                for ref in scope['dependencies'].values():
                    check_deadline()
                    self.store.read_blob(ref)
                check_deadline()
            finally:
                scope['active']=False
                scope['complete'].clear();scope['dependencies'].clear()
                _composition_scope.reset(token)
    def _composition_dependency(self,ref):
        scope=self._active_composition_scope()
        if scope is not None:
            key=(ref['identity'],ref['hash'],ref['bytes'])
            _require(key in scope['dependencies'] or len(scope['dependencies'])<4096,
                     'PROVENANCE','composition dependency bound')
            scope['dependencies'][key]=_as_blob(ref)
    def verify(self,evidence,expected_kind,subject=None,context=None):
        with self._readonly_validation():
            _check_type('Evidence',evidence)
            raw=self.store.read_blob(evidence)
            return self._verify_loaded(evidence,raw,expected_kind,subject,context)
    def _verify_loaded(self,evidence,raw,expected_kind,subject,context,proof=None):
        inherited=_verification_context.get()
        current=dict(inherited[1]) if inherited is not None and inherited[0] is self else {}
        if context is not None:current.update(context)
        context=current
        token=_verification_context.set((self,context))
        try:
            with _evidence_path(self,evidence['hash']):
                return self._verify_bytes(evidence,raw,expected_kind,subject,context,proof)
        finally:
            _verification_context.reset(token)
    def _verify_bytes(self,evidence,raw,expected_kind,subject,context,proof):
        if expected_kind=='SCOPE':
            _require(evidence=={'authority':'CA','contract':PROTOCOL+':'+VERSION,'identity':'FAILED_FENCED_INITIAL_OWNER_SCOPE_V1','hash':SCOPE_HASH,'bytes':SCOPE_BYTES},'AUTHORITY','scope identity')
            return {'kind':'SCOPE','payload':{'hash':SCOPE_HASH}}
        if expected_kind=='SCOPE_APPROVAL':
            _require(evidence['authority'] in {'CA','PCP','EA-SWING','EA-INTRADAY'},'AUTHORITY','owner scope authority')
            rows=[r for r in self.preparation.rows.values() if r['purpose']=='OWNER_SCOPE' and r['authority']==evidence['authority'] and r['artifact']['hash']==evidence['hash'] and r['artifact']['bytes']==evidence['bytes'] and r['bindings']['scope']['hash']==SCOPE_HASH]
            _require(len(rows)==1,'AUTHORITY','scope decision not in pinned catalogue');return {'kind':'SCOPE_APPROVAL','payload':rows[0]}
        if expected_kind=='ARTIFACT_APPROVAL':
            rows=[r for r in self.preparation.rows.values() if r['purpose']=='ARTIFACT' and r['authority']==evidence['authority']=='CA' and r['artifact']==_as_blob(evidence)]
            _require(len(rows)==1,'AUTHORITY','artifact decision not in pinned catalogue')
            return {'kind':'ARTIFACT_APPROVAL','payload':rows[0]}
        if expected_kind=='NATIVE':
            from kronos.intraday.failed_fenced_native_evidence import CLOSED_NATIVE_CONTRACTS,verify_native_evidence
            _require((evidence['authority'],evidence['contract']) in CLOSED_NATIVE_CONTRACTS,'AUTHORITY','unknown native adapter')
            return verify_native_evidence(evidence,raw,context)
        _require(expected_kind in schema.PROOF_SCHEMAS,'AUTHORITY','unknown external validator')
        if proof is None:proof=self.codec.decode_proof(raw,expected_kind)
        p=proof['payload']
        contract=('KRONOS-FAILED-FENCED-ROOT-PROOF' if expected_kind in STATIC_KINDS else 'KRONOS-FAILED-FENCED-EXTERNAL-PROOF')+':1.0.0:'+expected_kind
        _require(evidence['contract']==contract and evidence['identity']==p['identity'],'AUTHORITY','evidence contract identity')
        authority=('PCP' if expected_kind=='CLOCK_QUALIFICATION' else 'CA') if expected_kind in STATIC_KINDS else (p['owner'] if expected_kind in {'OWNER_RESULT','CLEANUP_APPLICABILITY'} else proof['role'])
        _require(evidence['authority']==authority,'AUTHORITY','evidence authority')
        if expected_kind not in STATIC_KINDS:
            self._issuer(proof,subject,context)
            self.verify(proof['clock']['qualification'],'CLOCK_QUALIFICATION')
        if expected_kind=='COMPOSITION_INVENTORY':self._composition_dependency(evidence)
        self._validate(proof,context)
        return proof
    @staticmethod
    def _proof_reference(proof,raw):
        kind=proof['kind'];p=proof['payload']
        authority=('PCP' if kind=='CLOCK_QUALIFICATION' else 'CA') if kind in STATIC_KINDS else (p['owner'] if kind in {'OWNER_RESULT','CLEANUP_APPLICABILITY'} else proof['role'])
        return {'authority':authority,'contract':('KRONOS-FAILED-FENCED-ROOT-PROOF' if kind in STATIC_KINDS else 'KRONOS-FAILED-FENCED-EXTERNAL-PROOF')+':1.0.0:'+kind,**blob_ref(p['identity'],raw)}
    def proof_evidence(self,raw):
        return self._proof_reference(self.codec.decode_proof(raw),raw)
    def verify_blob(self,blob,kind,subject=None,context=None):
        # Read and authenticate these exact immutable bytes once. This is not
        # a retained validation cache: every call repeats read/hash/MAC/schema,
        # issuer, clock and semantic checks under the current native context.
        with self._readonly_validation():
            raw=self.store.read_blob(blob)
            proof=self.codec.decode_proof(raw,kind)
            evidence=self._proof_reference(proof,raw)
            return self._verify_loaded(evidence,raw,kind,subject,context,proof)
    def native_evidence(self,owner,contract,identity,raw,context):
        from kronos.intraday.failed_fenced_native_evidence import CLOSED_NATIVE_CONTRACTS,verify_native_evidence
        _require((owner,contract) in CLOSED_NATIVE_CONTRACTS,'AUTHORITY','unlisted native contract')
        evidence={'authority':owner,'contract':contract,**blob_ref(identity,raw)}
        verify_native_evidence(evidence,raw,context)
        try:
            existing = self.store._read(('blobs',), evidence['hash'] + '.blob', 16 * MAX_RECORD + 1)
        except RecoveryError as exc:
            if not isinstance(exc.__cause__, FileNotFoundError): raise
            self.store.write_blob(identity,raw)
        else:
            _require(existing == raw, 'DURABILITY', 'native exact retained bytes changed')
        self._native_contexts[evidence['hash']]=_copy(context)
        return evidence
    def _issuer(self,proof,subject,context):
        p=proof['payload'];kind=proof['kind'];role=proof['role'];issuer=proof['issuer']
        original=(kind in {'ORIGINAL_AUTHORITY','ORIGINAL_CONTROLLER','CONTROLLER_ADMISSION','CONTROLLER_DISPATCH','CONTROLLER_CLOSURE'} or kind=='CONTROLLER_CAPABILITY' and p['phase']=='ORIGINAL' or context.get('mode')=='ORIGINAL')
        prep=self._prep(original)
        if role=='PREDECESSOR':expected=prep.record['lineage']['predecessor']
        elif role=='LAUNCHER':expected=prep.record['controller']
        else:
            expected=subject or context.get('child')
            _require(expected is not None,'IDENTITY','independent child identity unavailable')
        _require(issuer==expected,'IDENTITY','proof issuer/process mismatch')
        if 'process' in p:_require(p['process']==(prep.record['lineage']['predecessor'] if kind in {'ORIGINAL_AUTHORITY','ENDPOINT_CONFIGURATION'} else issuer),'IDENTITY','proof subject mismatch')
        for field in ('controller','observer'):
            if field in p:_require(p[field]==issuer,'IDENTITY','controller/observer issuer')
        if 'lineage' in p:_require(p['lineage']==prep.record['lineage'],'IDENTITY','proof lineage')
        if subject is not None and role!='SUCCESSOR' and 'subject' in p:_require(p['subject']==subject,'IDENTITY','observed subject')
    def _blob(self,ref):return self.store.read_blob(ref)
    def _validate(self,proof,context):
        kind=proof['kind'];p=proof['payload'];prep=self.preparation
        from .failed_fenced_startup import _HistoricalRecoveryValidation
        marker=context.get('historical_validation')
        retained=(type(marker) is _HistoricalRecoveryValidation and marker.native_payload(kind,p,self))
        if kind in STATIC_KINDS:
            purpose='CLOCK' if kind=='CLOCK_QUALIFICATION' else 'GUARD' if kind=='GUARD_APPLICABILITY' else 'ARTIFACT'
            authority='PCP' if kind=='CLOCK_QUALIFICATION' else 'CA'
            row=prep.approval(p['approval'],purpose=purpose,authority=authority)
            if kind=='CLOCK_QUALIFICATION':
                _require(p['boot_id']==self.codec.clock['boot_id'] and row['bindings']['root']['hash']==sha256(canonical_bytes(proof)).hexdigest() and row['bindings']['report']==p['report'],'TIMEOUT','clock qualification binding')
                _require(any(r['purpose']=='CLOCK' and r['authority']=='CA' and r['bindings']==row['bindings'] for r in prep.rows.values()),'AUTHORITY','CA clock approval')
                self._blob(p['report']);self._blob(p['platform'])
            elif kind=='GUARD_APPLICABILITY':
                b=row['bindings'];_require(all(p[k]==b[k] for k in ('service','classification','launcher','backend','sentinel','provisioning')),'AUTHORITY','guard classification')
                _require(any(r['purpose']=='GUARD' and r['authority']=='PCP' and r['bindings']==b for r in prep.rows.values()),'AUTHORITY','PCP guard approval')
                if p['classification']=='MANDATORY':
                    _require(p['sentinel'] is not None and p['provisioning'] is not None,'PROVENANCE','guard provisioning absent')
                    sentinel=decode_canonical(self.store._read((),'guard-scope.json'));_check_type('GuardScope',sentinel)
                    _require(sha256(canonical_bytes(sentinel)).hexdigest()==p['sentinel']['hash'] and sentinel['service']==p['service'] and sentinel['installation']==b['installation'],'IDENTITY','sentinel binding')
                    provisioning=decode_canonical(self._blob(p['provisioning']));_check_type('GuardProvisioning',provisioning)
                    _require(provisioning['before_first_capable_start'] and provisioning['fsync_verified'] and provisioning['readback_verified'] and provisioning['sentinel']==p['sentinel'],'PROVENANCE','provisioning outcome')
                else:_require(p['sentinel'] is None and p['provisioning'] is None,'PROVENANCE','legacy classification')
            else:
                _ordered(p['owners'],'owner');_require(len({v['owner'] for v in p['owners']})==len(p['owners']),'PROVENANCE','restoration roster')
                _require(row['bindings']['source_inventory']==p['source_inventory'] and row['bindings']['configuration']==p['configuration'] and row['bindings']['revision']==p['revision'],'AUTHORITY','restoration plan artifact')
                for item in p['owners']:self._blob(item['validator']);self._blob(item['applicability'])
            return
        if kind in {'ORIGINAL_AUTHORITY','RECOVERY_AUTHORITY'}:
            original=kind=='ORIGINAL_AUTHORITY';prepared=self._prep(original)
            _require(p['preparation']==prepared.pin['preparation'] and p['service']==prepared.record['service'],'AUTHORITY','authorization preparation')
            purpose='ORIGINAL_OPERATION' if original else 'RECOVERY_OPERATION'
            row=prepared.approval(p['approval'],purpose=purpose,authority='SPONSOR');b=row['bindings']
            for field in ('service','valid_from_ns','valid_until_ns','clock'):_require(p[field]==b[field],'AUTHORITY','authorization bounds')
            _require(int(p['valid_from_ns'])<=int(proof['issued_ns'])<int(p['valid_until_ns']),'AUTHORITY','authorization issuance validity')
            if original:
                _require(p['process']==b['predecessor'] and p['generation']==b['generation'] and p['kind']==b['operation_kind'] and p['source']==b['source'] and p['package']==b['package'] and p['control']['hash']==b['control'],'AUTHORITY','original approval binding')
                if p['kind']=='ORDINARY':
                    reservation=self.verify_blob(p['reservation'],'CONTROLLER_ADMISSION',context={'mode':'ORIGINAL'})['payload']
                    _require(reservation['action']=='RESERVE_ORIGINAL' and reservation['attempt']==prepared.record['attempt'] and reservation['lineage']==prepared.record['lineage'] and b['permission'] in reservation['inputs'],'AUTHORITY','prospective ordinary reservation')
                else:
                    from .failed_fenced_startup import validate_original_reservation
                    validate_original_reservation(self._blob(p['reservation']),self._blob(b['permission']),p,b)
            else:
                for field in ('lineage','slot','transaction','original_reservation','terminal','journal_heads','predecessor_source','predecessor_capability','installed_package','rollback_package','compatibility','diagnosis','interface','scope'):_require(p[field]==b[field],'AUTHORITY','recovery approval binding')
                _require(p['slot']==slot_key(p['lineage']),'IDENTITY','stable slot')
                _require(p['successor_source']==p['successor_capability']==b['target'],'AUTHORITY','target artifact')
            return
        if kind=='CONTROLLER_CAPABILITY':
            prepared=self._prep(p['phase']=='ORIGINAL')
            _require(p['controller']==prepared.record['controller'] and p['predecessor']==prepared.record['lineage']['predecessor'] and p['source_inventory']==prepared.record['launcher_source'] and p['package']==prepared.record['launcher_package'],'IDENTITY','actual controller prepared identity')
            _ordered(p['operations'],'action');_require({o['action'] for o in p['operations']}==schema.CONTROLLER_ACTIONS,'PROVENANCE','controller operation coverage')
            row=prepared.approval(p['qualified_artifact'],purpose='ARTIFACT',authority='CA')
            _require(row['bindings']['source_inventory']==p['source_inventory'] and row['bindings']['executable']==p['executable'] and row['bindings']['package']==p['package'],'AUTHORITY','controller artifact')
            for op in p['operations']:self._blob(op['implementation'])
            self._blob(p['proof_publication']);self._blob(p['executable']);return
        if kind=='CONTROLLER_ADMISSION':
            _ordered(p['inputs']);_require(p['attempt']==self._prep(True).record['attempt'],'IDENTITY','controller original attempt')
            for value in p['inputs']:self._blob(value)
            if p['previous'] is None:_require(p['sequence']=='0','PROVENANCE','controller sequence origin')
            else:
                previous=self.verify_blob(p['previous'],'CONTROLLER_ADMISSION')['payload']
                _require(int(p['sequence'])==int(previous['sequence'])+1 and p['attempt']==previous['attempt'],'PROVENANCE','controller sequence')
            return
        if kind=='CONTROLLER_DISPATCH':
            admission=self.verify_blob(p['admission'],'CONTROLLER_ADMISSION')['payload'];_require(p['attempt']==admission['attempt'],'PROVENANCE','dispatch admission')
            _ordered(p['outputs'])
            for output in p['outputs']:self._blob(output)
            if p['previous'] is None:_require(p['state']=='NOT_DISPATCHED' and p['helper'] is None and p['started_ns'] is None and p['completed_ns'] is None and p['outcome']=='NONE' and p['outstanding']=='0','PROVENANCE','dispatch initial state')
            else:
                before=self.verify_blob(p['previous'],'CONTROLLER_DISPATCH')['payload']
                _require(p['admission']==before['admission'],'PROVENANCE','dispatch identity')
                legal={'NOT_DISPATCHED':{'DISPATCHED'},'DISPATCHED':{'COMPLETED','FAILED_CLOSED','UNRESOLVED'}}
                _require(p['state'] in legal.get(before['state'],set()),'PROVENANCE','dispatch transition')
                if p['state']=='DISPATCHED':_require(p['started_ns'] is not None and int(p['outstanding'])>=1 and p['completed_ns'] is None,'ACCOUNTING','dispatch ownership')
                elif p['state']!='UNRESOLVED':_require(p['outstanding']=='0' and p['completed_ns'] is not None and int(p['started_ns'])<=int(p['completed_ns']) and p['outcome'] in ({'RETURNED','JOINED_SUCCESS'} if p['state']=='COMPLETED' else {'RETURNED','JOINED_FAILURE'}),'ACCOUNTING','dispatch completion')
            return
        if kind=='CONTROLLER_CLOSURE':
            cap=self.verify_blob(p['capability'],'CONTROLLER_CAPABILITY')['payload'];_require(cap['phase']=='ORIGINAL' and p['execution_lock']==cap['execution_lock'],'AUTHORITY','original execution lock')
            _require(p['outstanding']=='0' and p['publisher_owners']=='1','ACCOUNTING','controller publisher ownership')
            _require(p['rights']==[{'kind':k,'state':'CLOSED_UNUSED'} for k in sorted({'CHILD_INTENT','CHILD_FORK','CONSUME','RELEASE_COMPOSITION'})],'ACCOUNTING','closed rights')
            admissions=[self.verify_blob(x,'CONTROLLER_ADMISSION')['payload'] for x in p['admissions']]
            heads=[self.verify_blob(x,'CONTROLLER_DISPATCH')['payload'] for x in p['dispatch_heads']]
            _require(len(admissions)==len(heads) and {x['identity'] for x in admissions}=={x['admission']['identity'] for x in heads},'ACCOUNTING','closed controller roster')
            ordered=sorted(admissions,key=lambda a:int(a['sequence']))
            _require([a['sequence'] for a in ordered]==[str(i) for i in range(len(ordered))] and len({a['operation'] for a in ordered})==len(ordered),'ACCOUNTING','complete unique controller operation sequence')
            refs={ref['identity']:ref for ref in p['admissions']}
            _require(all(a['previous']==(None if index==0 else refs[ordered[index-1]['identity']]) for index,a in enumerate(ordered)),'ACCOUNTING','controller admission chain omitted')
            _require(all(a['action'] not in {'CHILD_INTENT','CHILD_FORK','CONSUME','RELEASE_COMPOSITION'} for a in admissions) and all(h['state'] in {'NOT_DISPATCHED','COMPLETED','FAILED_CLOSED'} for h in heads),'ACCOUNTING','original rights spent/unresolved')
            return
        if kind=='ORIGINAL_CONTROLLER':
            cap=self.verify_blob(p['control_capability'],'CONTROLLER_CAPABILITY')['payload'];closure=self.verify_blob(p['execution_closure'],'CONTROLLER_CLOSURE')['payload'];executor=self.verify_blob(p['executor'],'EXECUTOR_TERMINATION')['payload']
            _require(cap['phase']=='ORIGINAL' and p['admission_ledger']==closure['admissions'] and p['dispatch_ledger']==closure['dispatch_heads'] and p['sealed_ns']==closure['closed_ns'] and executor['original_controller']==p['controller'],'ACCOUNTING','original controller closure')
            operations=sorted(self.verify_blob(ref,'CONTROLLER_ADMISSION')['payload']['operation'] for ref in closure['admissions'])
            _require(operations==executor['accepted_operations']==executor['completed_operations'],'ACCOUNTING','controller/executor complete work set disagreement')
            return
        if kind=='EXECUTOR_TERMINATION':
            if p['process']['pid']==str(os.getpid()) and not retained:
                witness=self._executor_witnesses.get(p['executor'])
                _require(witness is not None,'ACCOUNTING','actual original executor witness missing')
                witness.validate(p)
            else:
                # Historical consumers require the independently qualified
                # actual producer source before trusting its owning receipt.
                _require(canonical_bytes(p['process']) in self._validated_sources,'PROVENANCE','original executor producer source not verified')
            return
        if kind=='CONTROL_BINDING':
            _require(p['process']['pid']==self.codec.pid and p['live_control']['hash']==p['retained_control']['hash']==self.codec.key_id and p['boot_id']==self.codec.clock['boot_id'],'IDENTITY','private control binding')
            self.codec.verify_control_binding(p,self.store);return
        if kind=='ISSUED_ADMISSION':
            _require(p['scope']['hash']==SCOPE_HASH,'AUTHORITY','admission scope');self._blob(p['input']);self._blob(p['effect'])
            if p['listener'] is not None:self._blob(p['listener'])
            return
        if kind=='FENCE_ROSTER':
            _ordered(p['admissions']);_ordered(p['tickets'],'ticket')
            _require(len({v['ticket'] for v in p['tickets']})==len(p['tickets']),'ACCOUNTING','fence ticket duplication')
            for item in p['tickets']:
                admission=self.verify_blob(item['admission'],'ISSUED_ADMISSION')['payload']
                _require(item['ticket']==admission['ticket'] and item['operation']==admission['operation'] and item['parent']==admission['parent'],'ACCOUNTING','fence admission')
            _require({x['hash'] for x in p['admissions']}=={x['admission']['hash'] for x in p['tickets']},'ACCOUNTING','fence complete admission set');return
        if kind=='COMPOSITION_INVENTORY':self._inventory(p);return
        if kind=='CLEANUP_APPLICABILITY':
            inv=self.verify_blob(p['composition'],'COMPOSITION_INVENTORY')['payload'];_require(p['predicate']['inventory']==p['composition'] and p['scope']['hash']==SCOPE_HASH,'PROVENANCE','cleanup inventory')
            if p['state']=='APPLICABLE':
                matches=[x for x in inv['cleanup'] if x['step']==p['predicate']['target']]
                _require(p['predicate']['kind']=='REGISTERED_TARGET' and len(matches)==1 and all(matches[0][k]==p[k] for k in ('owner','owner_instance','action','resource')),'CLEANUP','cleanup exact target')
            else:
                slots=[x for x in inv['slots'] if x['slot']==p['predicate']['slot']]
                _require(p['predicate']['kind']=='OWNER_SLOT_NOT_INSTALLED' and p['predicate']['target'] is None and len(slots)==1 and slots[0]['owner']==p['owner'] and slots[0]['presence']=='NOT_INSTALLED' and p['owner_instance']==p['resource']==slots[0]['slot'],'CLEANUP','cleanup absence predicate')
            return
        if kind=='OWNER_RESULT':self._owner_result(p,context);return
        if kind=='PEER_REGISTRATION':self._peer_registration(p);return
        if kind=='PEER_FULFILLMENT':self._peer_fulfillment(p,context);return
        if kind=='TAIL':
            row=prep.approval(p['approval'],purpose='TAIL',authority='CA');_require(row['bindings']['entry']==p['entry'] and row['bindings']['allowed']==p['allowed'],'AUTHORITY','reviewed tail entry')
            _require(any(r['authority']=='PCP' and r['purpose']=='TAIL' and r['bindings']==row['bindings'] for r in prep.rows.values()),'AUTHORITY','PCP tail approval')
            self.verify_blob(p['source'],'SOURCE',context=context);return
        if kind=='PACKAGE':
            prepared=self._prep(context.get('mode')=='ORIGINAL');row=prepared.approval(p['artifact_approval'],purpose='ARTIFACT',authority='CA')
            _require(row['bindings']['package']==p['manifest'] and row['bindings']['executable']==p['executable'],'AUTHORITY','package artifact')
            for k in ('manifest','executable','signature'):self._blob(p[k])
            return
        if kind=='TARGET_ARTIFACT':
            row=prep.approval(p['approval'],purpose='ARTIFACT',authority='CA');b=row['bindings']
            for k in ('revision','source_inventory','capability_manifest','configuration','package','bootstrap_plan'):_require(p[k]==b[k],'AUTHORITY','target artifact exact binding')
            _require(p['scope']['hash']==SCOPE_HASH and p['interface']==prep.catalogue['interface'],'AUTHORITY','target interface')
            plan=decode_canonical(self._blob(p['bootstrap_plan']));_check_type('BootstrapPlan',plan);_require(plan['source_inventory']==p['source_inventory'],'PROVENANCE','bootstrap source inventory')
            self.verify_blob(p['restoration_plan'],'RESTORATION_PLAN');return
        if kind=='SOURCE':self._native_source(p,context);return
        if kind=='CAPABILITY':
            source=self.verify_blob(p['source'],'SOURCE',subject=p['process'],context=context)['payload'];row=prep.approval(p['qualified_artifact'],purpose='ARTIFACT',authority='CA')
            _require(p['owner_scope']['hash']==SCOPE_HASH and row['bindings']['source_inventory']==source['source_inventory'] and row['bindings']['capability_manifest']==p['implementation'],'AUTHORITY','loaded capability artifact')
            from .failed_fenced_startup import recovery_operation_manifest, validate_source_inventory_blob
            from .failed_fenced_compatibility import read_native_runtime_manifest, verify_target_runtime_manifest
            operations=decode_canonical(self._blob(p['operation_manifest']))
            inventory=self._blob(source['source_inventory'])
            _require(operations==recovery_operation_manifest(validate_source_inventory_blob(inventory)),
                     'PROVENANCE','closed recovery operation manifest changed')
            manifest=read_native_runtime_manifest(self._blob(source['runtime_manifest']))
            verify_target_runtime_manifest(manifest,self._blob(p['implementation']),row['bindings'],inventory)
            self._blob(p['tail_plan'])
            if proof['role']=='SUCCESSOR' and p['process']['pid']==str(os.getpid()) and not retained:
                from .failed_fenced_startup import SuccessorReadyEvidence
                witness=getattr(self,'_successor_runtime',None)
                _require(type(witness) is SuccessorReadyEvidence,'PROVENANCE','actual successor capability witness unavailable')
                witness.verify_native_binding();witness.verify_capability_witness(p)
            return
        if kind=='ENDPOINT_CONFIGURATION':
            _require(0<int(p['port'])<=65535 and p['service']==prep.record['service'] and p['process']==prep.record['lineage']['predecessor'],'IDENTITY','endpoint subject')
            config=json.loads(self._blob(p['configuration']));_require(type(config) is dict and config.get('browser_port')==int(p['port']),'IDENTITY','canonical configured endpoint')
            self.verify_blob(p['source'],'SOURCE',subject=p['process'],context=context);self._blob(p['listener']);return
        if kind in {'BOOTSTRAP_IDENTITY','PLATFORM_OBSERVATION','RESTORATION','COMPATIBILITY','ABSENCE'}:
            # Fixed native adapter, not a supplied validator or a report flag.
            from .failed_fenced_startup import validate_external_native_proof
            validate_external_native_proof(proof,self,context);return
        if kind=='FAILURE_FACT':
            for b in p['owner_facts']:self._blob(b)
            return
        raise RecoveryError('AUTHORITY','unimplemented closed evidence adapter')
    def _native_source(self,p,context=None):
        from dataclasses import asdict
        from datetime import datetime
        from kronos.intraday.runtime_identity import StartupEvidence,RuntimeManifest,LoadedCapability,canonical
        def startup(data):
            fields=dict(data);fields['startup_boundary_at']=datetime.fromisoformat(fields['startup_boundary_at']);fields['loaded_modules']=tuple(tuple(x) for x in fields['loaded_modules']);return StartupEvidence(**fields)
        try:
            raw=self._blob(p['startup']);s=startup(json.loads(raw));_require(canonical(asdict(s))==raw,'PROVENANCE','native startup encoding')
            rawm=self._blob(p['runtime_manifest']);m=json.loads(rawm);m['startup']=startup(m['startup']);m['capabilities']=tuple(LoadedCapability(**x) for x in m['capabilities']);manifest=RuntimeManifest(**m)
            _require(canonical(asdict(manifest))==rawm and manifest.startup==s,'PROVENANCE','native runtime encoding')
        except (ValueError,TypeError,KeyError) as exc:raise RecoveryError('PROVENANCE','native source validation') from exc
        _require(s.source_state=='CLEAN_COMMIT' and s.source_revision==p['revision'] and str(s.process_id)==p['process']['pid'] and sha256(s.evidence_identity.encode()).hexdigest()==p['process']['runtime'] and s.load_verification=='PINNED_STARTUP_IMPORTS','PROVENANCE','actual loaded source identity')
        from .failed_fenced_startup import _HistoricalRecoveryValidation
        marker=(context or {}).get('historical_validation')
        retained=(type(marker) is _HistoricalRecoveryValidation and marker.native_payload('SOURCE',p,self))
        if p['process']['pid']==str(os.getpid()) and not retained:
            ledger=self.native_ledger
            native=(ledger is not None and ledger.process==p['process'] and getattr(ledger,'native_startup',None)==s and getattr(ledger,'native_runtime_manifest',None)==manifest)
            if not native:
                from .failed_fenced_startup import SuccessorReadyEvidence
                witness=getattr(self,'_successor_runtime',None)
                _require(type(witness) is SuccessorReadyEvidence,'PROVENANCE','actual canonical loaded-source witness unavailable')
                witness.verify_native_binding()
                _require(witness.verify_source_witness(p)==(s,manifest),'PROVENANCE','actual successor source witness changed')
        from .failed_fenced_startup import validate_source_inventory_blob
        inventory_raw=self._blob(p['source_inventory'])
        modules=dict(validate_source_inventory_blob(inventory_raw))
        _require(s.source_snapshot_digest==sha256(inventory_raw).hexdigest() and all(modules.get(name)==digest for name,digest in s.loaded_modules),'PROVENANCE','complete native source inventory')
        self._blob(p['canonical_parent']);self._blob(p['publication']);self._blob(p['package'])
        self._validated_sources[canonical_bytes(p['process'])]=_copy(p)
    def _inventory(self,p):
        scope=self._active_composition_scope()
        def context_key(value):
            if type(value) is dict:return tuple((k,context_key(v)) for k,v in sorted(value.items()))
            if type(value) in (list,tuple):return tuple(context_key(v) for v in value)
            if value is None or type(value) in (str,bool,int):return (type(value).__name__,value)
            return (type(value),id(value))
        inherited=_verification_context.get()
        context=inherited[1] if inherited is not None and inherited[0] is self else {}
        key=(sha256(canonical_bytes(p)).hexdigest(),context_key(context)) if scope is not None else None
        if scope is not None and key in scope['complete']:
            return
        self._inventory_structure(p)
        if scope is not None:
            _require(len(scope['complete'])<4096,'PROVENANCE','composition structure bound')
            scope['complete'].add(key)
    def _inventory_structure(self,p):
        _require(p['scope']['hash']==SCOPE_HASH,'AUTHORITY','composition scope')
        _ordered(p['slots'],'owner');_ordered(p['instances']);_ordered(p['resources']);_ordered(p['listeners']);_ordered(p['cleanup'],'step')
        _require({x['owner'] for x in p['slots']}==schema.OWNERS,'PROVENANCE','complete owner slots required')
        instances={x['identity']:x for x in p['instances']};resources={x['identity']:x for x in p['resources']};steps={x['step']:x for x in p['cleanup']}
        expected=set()
        for slot in p['slots']:
            _ordered(slot['instances']);_require((slot['presence']=='INSTALLED')==bool(slot['instances']),'PROVENANCE','slot presence')
            for i in slot['instances']:
                _require(i not in expected and i in instances and instances[i]['owner']==slot['owner'] and instances[i]['slot']==slot['slot'],'PROVENANCE','instance slot');expected.add(i)
        _require(expected==set(instances),'PROVENANCE','unassigned instance')
        aliases=set()
        for resource in p['resources']:
            _require(resource['owner_instance'] in instances and (resource['parent'] is None or resource['parent'] in resources),'PROVENANCE','resource owner/parent')
            _ordered(resource['aliases'])
            for alias in [resource['identity']]+resource['aliases']:
                _require(alias not in aliases,'PROVENANCE','duplicate resource alias');aliases.add(alias)
        for listener in p['listeners']:
            _require(listener['producer_instance'] in instances and listener['consumer_instance'] in instances,'PROVENANCE','listener actual instances')
            self._blob(listener['implementation'])
            self._composition_dependency(listener['implementation'])
        for step in p['cleanup']:
            _require(step['owner_instance'] in instances and instances[step['owner_instance']]['owner']==step['owner'] and step['resource'] in resources and resources[step['resource']]['owner_instance']==step['owner_instance'] and step['action'] in schema.CLEANUP_ACTIONS.get(step['owner'],()),'CLEANUP','cleanup registered target')
            _ordered(step['nested']);_require(all(x in steps for x in step['nested']),'CLEANUP','unknown nested action')
        def walk(s,seen):
            _require(s not in seen,'CLEANUP','nested cleanup cycle')
            for child in steps[s]['nested']:walk(child,seen|{s})
        for s in steps:walk(s,set())
        if p['previous'] is None:_require(p['phase']=='LIVE','PROVENANCE','fence without live inventory')
        else:
            old=self.verify_blob(p['previous'],'COMPOSITION_INVENTORY')['payload']
            _require(old['phase']=='LIVE','PROVENANCE','composition changed after original fence')
            _require(all(old[field]==p[field] for field in ('process','source','scope')),'IDENTITY','composition source identity changed')
            _require(int(old['observed_ns'])<=int(p['registered_ns'])<=int(p['observed_ns']),'PROVENANCE','composition time reversed')
            old_instances={v['identity'] for v in old['instances']}
            old_slots={v['owner']:v for v in old['slots']}
            for slot in p['slots']:
                prior=old_slots[slot['owner']]
                _require(slot['slot']==prior['slot'] and set(prior['instances'])<=set(slot['instances']),'PROVENANCE','owner slot history rewritten')
                _require(prior['presence']!='INSTALLED' or slot['presence']=='INSTALLED','PROVENANCE','installed owner removed')
                _require(all(i not in old_instances for i in set(slot['instances'])-set(prior['instances'])),'PROVENANCE','owner instance moved between slots')
            for field in ('instances','resources','listeners','cleanup'):
                keys='step' if field=='cleanup' else 'identity';new={v[keys]:v for v in p[field]}
                for v in old[field]:
                    _require(v[keys] in new,'PROVENANCE','inventory history removed')
                    current=new[v[keys]]
                    same=current==v
                    if field=='cleanup' and not same:
                        # A real newly constructed nested resource may append
                        # its cleanup edge while the inventory is LIVE. Old
                        # targets and edges cannot be changed or reclassified.
                        added=set(current['nested'])-set(v['nested'])
                        prior_steps={row['step'] for row in old['cleanup']}
                        same=(all(current[k]==v[k] for k in v if k!='nested')
                              and set(v['nested'])<=set(current['nested'])
                              and not (added & prior_steps))
                    elif field=='listeners' and not same:
                        same=(all(current[k]==v[k] for k in v if k!='retired_ns')
                              and v['retired_ns'] is None
                              and current['retired_ns'] is not None
                              and int(current['retired_ns'])>=int(v['registered_ns']))
                    _require(same,'PROVENANCE','inventory history rewritten')
    def _owner_result(self,p,context):
        inv=self.verify_blob(p['composition'],'COMPOSITION_INVENTORY')['payload']
        _require(p['scope']['hash']==SCOPE_HASH,'AUTHORITY','owner result scope')
        if p['result']=='NOT_APPLICABLE' and p['reason']=='NOT_INSTALLED':
            _require(any(s['owner']==p['owner'] and s['presence']=='NOT_INSTALLED' and s['slot']==p['owner_instance']==p['resource'] for s in inv['slots']),'PROVENANCE','owner absence original slot')
        else:_require(any(i['identity']==p['owner_instance'] and i['owner']==p['owner'] for i in inv['instances']),'PROVENANCE','owner actual instance')
        if p['purpose']=='CLEANUP':
            _require(inv['phase']=='ORIGINAL_FENCE','CLEANUP','cleanup original-fence inventory')
            _require(p['result']=='NOT_APPLICABLE' or any(x['owner']==p['owner'] and x['owner_instance']==p['owner_instance'] and x['action']==p['action'] and x['resource']==p['resource'] for x in inv['cleanup']),'CLEANUP','unregistered cleanup result')
        for peer in p['peer_fulfillment']:self.verify_blob(peer,'PEER_FULFILLMENT',context=context)
        _ordered(p['callback_results'],'listener')
        for callback in p['callback_results']:
            _require(any(l['identity']==callback['listener'] for l in inv['listeners']) and callback['operation']==p['operation'],'PROVENANCE','callback registered operation')
            _require(callback['state']=='RETURNED' or bool(p['peer_fulfillment']),'PROVENANCE','unproved callback exemption')
        for field in ('targets','before','after'):
            _ordered(p[field])
            for b in p[field]:self._blob(b)
        if p['purpose'] in {'RECONCILIATION','CHECKPOINT'}:
            _verify_notice_set(p,self,context)
        elif p['purpose'] in {'EFFECT','REFERENCE'}:
            from kronos.intraday.failed_fenced_native_evidence import verify_native_owner_result
            verify_native_owner_result(p,self,context)
        elif p['purpose'] in {'CLEANUP','ABSENCE'}:
            from .failed_fenced_startup import _HistoricalRecoveryValidation
            marker=context.get('historical_validation')
            retained=(type(marker) is _HistoricalRecoveryValidation and marker.native_payload('OWNER_RESULT',p,self))
            if p['process']['pid']==str(os.getpid()) and not retained:
                from kronos.application.failed_fenced_owners import verify_native_cleanup_result,verify_native_absence_result
                composition=getattr(self,'_native_composition',None)
                validator=verify_native_cleanup_result if p['purpose']=='CLEANUP' else verify_native_absence_result
                validator(p,self,composition)
            else:
                _require(canonical_bytes(p['process']) in self._validated_sources,'PROVENANCE','native owner-result producer source not verified')
    def _peer_registration(self,p):
        inv=self.verify_blob(p['composition'],'COMPOSITION_INVENTORY')['payload']
        _require(inv['phase']=='LIVE' and int(inv['observed_ns'])<=int(p['registered_ns']),'PROVENANCE','peer pre-effect LIVE composition')
        _require(p['producer'] in {'WO10','WO11'} and ((p['producer']=='WO10' and p['source_kind'] in {'SELECTION','COMPARISON','UNAVAILABLE'}) or (p['producer']=='WO11' and p['source_kind'] in {'ACTION','TRACK'})),'PROVENANCE','peer source edge')
        slots=[s for s in inv['slots'] if s['slot']==p['peer_slot'] and s['owner']==p['peer']];_require(len(slots)==1,'PROVENANCE','peer slot')
        if p['predicate']=='OWNER_SLOT_NOT_INSTALLED':_require(slots[0]['presence']=='NOT_INSTALLED' and p['peer_instance'] is None and p['listener'] is None,'PROVENANCE','peer absence')
        else:
            _require(slots[0]['presence']=='INSTALLED' and p['peer_instance'] in slots[0]['instances'],'PROVENANCE','peer installed instance')
            if p['predicate'] not in {'JOURNAL_UNSUPPORTED_KIND','BOOKS_NO_SOURCE_EDGE'}:_require(any(l['identity']==p['listener'] and l['consumer_instance']==p['peer_instance'] and l['producer_instance']==p['producer_instance'] for l in inv['listeners']),'PROVENANCE','actual bound peer listener')
        from kronos.intraday.failed_fenced_native_evidence import verify_native_peer_registration
        verify_native_peer_registration(p,self)
    def _peer_fulfillment(self,p,context):
        _require(p['outcome']!='FAILED' and not p['failure'],'PROVENANCE','failed peer cannot support recovery')
        reg=self.verify_blob(p['registration'],'PEER_REGISTRATION')['payload']
        _require(p['execution_owner']==reg['ticket'] and int(reg['registered_ns'])<=int(p['recorded_ns']),'PROVENANCE','peer retained original ticket')
        if 'claim_ns' in context:_require(int(p['recorded_ns'])<int(context['claim_ns']),'PROVENANCE','peer not completed before claim')
        no_call=reg['predicate'] in {'OWNER_SLOT_NOT_INSTALLED','JOURNAL_TRACK_UNCHANGED','JOURNAL_UNSUPPORTED_KIND','BOOKS_NO_SOURCE_EDGE'}
        _require((p['outcome']=='NOT_REQUIRED')==no_call,'PROVENANCE','peer result predicate')
        if not no_call:_require(int(reg['registered_ns'])<=int(p['invoked_ns']),'PROVENANCE','callback before registration')
        from kronos.intraday.failed_fenced_native_evidence import verify_native_peer_fulfillment
        verify_native_peer_fulfillment(reg,p,self)

class ProspectiveLedger:
    """Owner-native facts captured before effects, never reconstructed at recovery.

    Calls retain ownership through their durability boundary. This lock protects
    ledger transitions only; it is never the coordinator's accounting mutex.
    """
    def __init__(self,coordinator,codec,store,registry,process,scope):
        _require(type(coordinator) is MaintenanceAdmissionCoordinator and type(registry) in {EvidenceRegistry,_ProspectiveEvidenceWriter},'AUTHORITY','typed prospective ledger')
        _check_type('Process',process);_require(process['pid']==str(os.getpid())==codec.pid,'IDENTITY','actual predecessor process')
        _require(coordinator.snapshot()['state']=='OPEN','PROVENANCE','ledger installed too late')
        registry.verify(scope,'SCOPE')
        self.coordinator=coordinator;self.codec=codec;self.store=store;self.registry=registry;self.process=_copy(process);self.scope=_copy(scope)
        self._lock=RLock();self._operations={};self._cleanups={};self._peers={};self._fulfillments={};self._proofs={};self._blobs={}
        self._inventory=None;self._inventory_payload=None;self.original=None;self.terminal=None;self.executor_head=None;self.lineage=None
        self._sealed=False;self._failure=None;self._ineligible=None;self._sequence=0;self._original_payload=None;self._terminal_payload=None
        _require(coordinator._prospective_ledger is None,'PROVENANCE','ledger already installed')
        coordinator._prospective_ledger=self
        if type(registry) is _ProspectiveEvidenceWriter: registry._native_ledger=self
    @classmethod
    def capture(cls,coordinator,codec,store,process,scope):
        """Install before construction. Captured facts grant no authority."""
        return cls(coordinator,codec,store,_ProspectiveEvidenceWriter(codec,store,process),process,scope)
    def attach_registry(self,registry):
        with self._lock:
            self._mutable()
            _require(type(registry) is EvidenceRegistry and registry.codec is self.codec and registry.store is self.store and registry.preparation.record['lineage']['predecessor']==self.process,'AUTHORITY','prepared registry binding')
            registry.verify(self.scope,'SCOPE')
            registry.bind_native_ledger(self)
            for evidence in self._proofs.values():
                kind=evidence['contract'].rsplit(':',1)[-1]
                registry.verify(evidence,kind)
            self.registry=registry
    def now_ns(self):
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    def bind_runtime_manifest(self,manifest):
        from kronos.intraday.runtime_identity import RuntimeManifest
        with self._lock:
            self._mutable()
            _require(type(manifest) is RuntimeManifest and getattr(self,'native_startup',None) is manifest.startup and getattr(self,'native_runtime_manifest',None) is None,'PROVENANCE','actual canonical runtime manifest required once')
            self.native_runtime_manifest=manifest
    @contextmanager
    def activate(self):
        token=_active_ledger.set(self)
        try:yield self
        finally:_active_ledger.reset(token)
    def current_ticket(self):return self.coordinator.current_ticket()
    def _mutable(self):
        _require(not self._sealed and self._failure is None,'ACCOUNTING','ledger sealed or failed')
    def mark_ineligible(self,code):
        """Capture a permanent negative gate without changing ordinary work."""
        _check_type('FailureCode',code)
        with self._lock:
            _require(not self._sealed,'ACCOUNTING','ineligibility after seal')
            if self._ineligible is not None:return self._ineligible
            # Set the live negative gate before I/O; a failed durability attempt
            # also denies recovery and is never retried or treated as absence.
            self._ineligible={'code':code,'evidence':None}
            facts={'identity':self._identity('ineligible'),'process':self.process,'phase':'PROSPECTIVE_OWNER','code':code,'original_failure':None,'observed_ns':str(self.now_ns()),'owner_facts':[],'outstanding_owners':str(sum(self.coordinator.snapshot()['owners'].values()))}
            self._ineligible['evidence']=self.publish_proof('FAILURE_FACT',facts)
            return _copy(self._ineligible)
    def _identity(self,prefix):
        self._sequence+=1;return f'{prefix}:{self._sequence}'
    def retain_native(self,identity,raw):
        with self._lock:
            self._mutable();ref=blob_ref(identity,raw)
            old=self._blobs.get(ref['hash'])
            if old is not None:
                _require(self.store.read_blob(old)==raw,'DURABILITY','retained blob changed');return ref
            self.store.retain_blob(identity,raw);self._blobs[ref['hash']]=ref;return ref
    def native_evidence(self,owner,contract,identity,raw,context):
        with self._lock:
            self._mutable()
            from kronos.intraday.failed_fenced_native_evidence import CLOSED_NATIVE_CONTRACTS,verify_native_evidence
            _require((owner,contract) in CLOSED_NATIVE_CONTRACTS,'AUTHORITY','unlisted native contract')
            evidence={'authority':owner,'contract':contract,**blob_ref(identity,raw)}
            verify_native_evidence(evidence,raw,context);self.retain_native(identity,raw)
            self.registry._native_contexts[evidence['hash']]=_copy(context);return evidence
    def publish_proof(self,kind,payload,*,context=None):
        with self._lock:
            if kind in {'FAILURE_FACT','EXECUTOR_TERMINATION'}:
                _require(not self._sealed,'ACCOUNTING','proof after seal')
            else:self._mutable()
            _require(kind in P_KINDS or kind in {'SOURCE','CAPABILITY','ENDPOINT_CONFIGURATION','FAILURE_FACT','ABSENCE'},'AUTHORITY','predecessor proof kind')
            raw=self.codec.encode_proof(kind,payload,self.process,'PREDECESSOR',self.now_ns())
            evidence=self.registry.proof_evidence(raw)
            # Validate dependencies before exposing this new proof. The store's
            # exclusive write/readback is the publication completion boundary.
            self.registry._issuer(self.codec.decode_proof(raw),self.process,{})
            self.registry._validate(self.codec.decode_proof(raw),{} if context is None else context)
            self.store.write_blob(payload['identity'],raw);self._proofs[evidence['hash']]=evidence
            return evidence
    def register_inventory(self,payload):
        with self._lock:
            self._mutable()
            _require(payload['process']==self.process,'IDENTITY','inventory process')
            _require(payload['previous']==(None if self._inventory is None else _as_blob(self._inventory)),'PROVENANCE','inventory predecessor')
            evidence=self.publish_proof('COMPOSITION_INVENTORY',payload)
            self._inventory=evidence;self._inventory_payload=_copy(payload);return evidence
    @property
    def inventory(self):
        return _copy(self._inventory) if self._inventory else None
    def begin_operation(self,ticket,owner,owner_instance,operation,relation,effect,listener=None,parent=None,required_children=()):
        with self._lock:
            self._mutable();_check_type('Id',operation)
            _require(self.coordinator.snapshot()['state']=='OPEN' and self.coordinator.is_live(ticket),'ACCOUNTING','pre-effect OPEN issued admission required')
            _require(operation not in self._operations and self._inventory is not None and self._inventory_payload['phase']=='LIVE','PROVENANCE','operation registration')
            _require(any(x['identity']==owner_instance and x['owner']==owner for x in self._inventory_payload['instances']),'PROVENANCE','operation owner instance')
            purpose='REFERENCE' if relation.endswith('_REFERENCE') else 'EFFECT'
            _require(schema.owner_tuple(owner,purpose,relation),'AUTHORITY','unlisted operation relation')
            _check_type('Effect',effect);_require(effect['kind']==relation,'PROVENANCE','fixed effect relation')
            context={'owner':owner,'owner_instance':owner_instance,'operation':operation,'ticket':ticket.identity,'source_identity':effect['identity']}
            for field in ('source','input'):
                self.registry.verify(effect[field],'NATIVE',context=context)
            if effect['transition'] is not None:self.registry.verify(effect['transition'],'NATIVE',context=context)
            if parent is not None:
                _check_type('Ref',parent)
                matches=[o for o in self._operations.values() if o['accepted']==parent]
                _require(len(matches)==1 and operation in matches[0]['payload']['required_children'] and ticket.parent_identity==matches[0]['ticket'].identity,'PROVENANCE','registered parent/child relationship')
            elif ticket.parent_identity is not None:
                # A browser/worker admission parent is not an executable
                # business obligation; its accounting still remains visible.
                _require(ticket.kind!='NOTIFICATION','PROVENANCE','notification root forbidden')
            self.coordinator.bind_operation(ticket,operation)
            history=self.coordinator.ticket_snapshot()['history'][ticket.identity]
            effect_blob=self.retain_native(self._identity('effect'),canonical_bytes(effect))
            admission_payload={'identity':self._identity('admission'),'process':self.process,'operation':operation,'ticket':ticket.identity,'parent':ticket.parent_identity,'relation':relation,'accepted_ns':str(history['accepted_ns']),'state':'OPEN_ACCEPTED','scope':_as_blob(self.scope),'input':_as_blob(effect['input']),'effect':effect_blob,'listener':None if listener is None else _as_blob(listener)}
            admission=self.publish_proof('ISSUED_ADMISSION',admission_payload)
            payload={'predecessor':self.process,'obligation':operation,'previous':None,'state':'ACCEPTED','owner':owner,'owner_instance':owner_instance,'operation':operation,'relation':relation,'effect':_copy(effect),'listener':_copy(listener),'ticket':ticket.identity,'admission':admission,'owner_scope':self.scope,'parent':_copy(parent),'required_children':list(required_children),'notices':[],'owner_result':None,'failure':None}
            raw=self.codec.encode('OBLIGATION',payload,'PREDECESSOR',self.now_ns());ref=self.store.publish(raw)
            _require(self.coordinator.is_live(ticket),'ACCOUNTING','ticket released before registration durability')
            self._operations[operation]={'accepted':ref,'head':ref,'payload':payload,'ticket':ticket,'admission':admission,'completed_ns':None}
            return operation
    def operation_head(self,operation):
        with self._lock:
            _require(operation in self._operations,'PROVENANCE','unknown operation');return _copy(self._operations[operation]['head'])
    def operation_payload(self,operation):
        with self._lock:
            _require(operation in self._operations,'PROVENANCE','unknown operation');return _copy(self._operations[operation]['payload'])
    def operation_ticket(self,operation):
        with self._lock:
            _require(operation in self._operations,'PROVENANCE','unknown operation');return self._operations[operation]['ticket']
    def _operation_transition(self,operation,state,owner_result=None,notices=(),failure=None):
        self._mutable();o=self._operations.get(operation);_require(o is not None,'PROVENANCE','unknown operation')
        before=o['payload'];allowed={'ACCEPTED':{'STARTED','FAILED'},'STARTED':{'COMPLETE','FAILED'}}
        if before['relation'].endswith('_REFERENCE'):allowed['ACCEPTED'].add('COMPLETE')
        _require(state in allowed.get(before['state'],set()) and self.coordinator.is_live(o['ticket']),'ACCOUNTING','operation transition/ownership')
        for child in before['required_children']:_require(child in self._operations and self._operations[child]['payload']['parent']==o['accepted'],'PROVENANCE','required child was not registered before effect')
        if owner_result is not None:
            result=self.registry.verify(owner_result,'OWNER_RESULT',context={})['payload']
            _require(result['operation']==operation and result['owner']==before['owner'] and result['owner_instance']==before['owner_instance'] and result['action']==before['relation'] and result['result']==('COMPLETE' if state=='COMPLETE' else 'FAILED'),'PROVENANCE','operation result binding')
        payload=_copy(before);payload.update(previous=o['head'],state=state,owner_result=owner_result,notices=list(notices),failure=failure)
        ref=self.store.publish(self.codec.encode('OBLIGATION',payload,'PREDECESSOR',self.now_ns()))
        _require(self.coordinator.is_live(o['ticket']),'ACCOUNTING','ticket released during completion publication')
        o.update(head=ref,payload=payload)
        if state in {'COMPLETE','FAILED'}:o['completed_ns']=self.now_ns()
        if state=='FAILED':self._ineligible={'code':failure,'evidence':owner_result}
        return ref
    def start_operation(self,operation):
        with self._lock:return self._operation_transition(operation,'STARTED')
    def complete_operation(self,operation,owner_result,notices=()):
        with self._lock:return self._operation_transition(operation,'COMPLETE',owner_result,notices)
    def fail_operation(self,operation,owner_result,code):
        with self._lock:return self._operation_transition(operation,'FAILED',owner_result,(),code)
    def register_peer(self,payload):
        with self._lock:
            self._mutable();operation=self._operations.get(payload['operation'])
            _require(operation is not None and operation['payload']['state']=='ACCEPTED' and self.coordinator.is_live(operation['ticket']) and payload['ticket']==operation['ticket'].identity,'PROVENANCE','peer registered after effect/release')
            _require(payload['identity'] not in self._peers,'PROVENANCE','duplicate peer registration')
            result=self.publish_proof('PEER_REGISTRATION',payload);self._peers[payload['identity']]={'evidence':result,'payload':_copy(payload)};return result
    def complete_peer(self,payload):
        with self._lock:
            registration=self._peers.get(payload['registration']['identity'])
            _require(registration is not None and _as_blob(registration['evidence'])==payload['registration'] and payload['registration']['identity'] not in self._fulfillments,'PROVENANCE','unknown/repeated peer fulfillment')
            operation=self._operations[registration['payload']['operation']]
            _require(self.coordinator.is_live(operation['ticket']),'ACCOUNTING','peer ticket released')
            if payload['outcome']=='FAILED':
                # Preserve the actual negative receipt. It is never accepted by
                # the positive peer validator and cannot later be repaired.
                raw=self.codec.encode_proof('PEER_FULFILLMENT',payload,self.process,'PREDECESSOR',self.now_ns())
                self.store.write_blob(payload['identity'],raw);result=self.registry.proof_evidence(raw)
                self._ineligible={'code':'PROVENANCE','evidence':result}
            else:result=self.publish_proof('PEER_FULFILLMENT',payload)
            _require(self.coordinator.is_live(operation['ticket']),'ACCOUNTING','peer released before durability')
            self._fulfillments[payload['registration']['identity']]={'evidence':result,'completed_ns':self.now_ns()};return result
    def publish_owner_result(self,payload,*,context=None):return self.publish_proof('OWNER_RESULT',payload,context=context)
    def register_cleanup(self,payload):
        with self._lock:
            self._mutable();_require(payload['step'] not in self._cleanups and payload['previous'] is None and payload['state'] in {'NOT_STARTED','NOT_APPLICABLE'},'CLEANUP','cleanup registration')
            applicability=self.registry.verify(payload['applicability'],'CLEANUP_APPLICABILITY')['payload']
            _require(all(payload[k]==applicability[k] for k in ('owner','owner_instance','action','resource','operation')),'CLEANUP','cleanup applicability binding')
            if payload['owner_result'] is not None:self.registry.verify(payload['owner_result'],'OWNER_RESULT')
            ref=self.store.publish(self.codec.encode('CLEANUP',payload,'PREDECESSOR',self.now_ns()));self._cleanups[payload['step']]={'head':ref,'payload':_copy(payload)};return ref
    def _cleanup_transition(self,step,state,result=None,code=None):
        self._mutable();entry=self._cleanups.get(step);_require(entry is not None,'CLEANUP','missing cleanup journal')
        before=entry['payload'];_require(state in {'NOT_STARTED':{'STARTED'},'STARTED':{'COMPLETE','FAILED'}}.get(before['state'],set()),'CLEANUP','cleanup repeated/unknown outcome')
        if state=='STARTED':
            target=next((x for x in self._inventory_payload['cleanup'] if x['step']==step),None)
            _require(target is not None and all(self._cleanups.get(x,{}).get('payload',{}).get('state')=='COMPLETE' for x in target['nested']),'CLEANUP','nested cleanup incomplete')
        if result is not None:
            proof=self.registry.verify(result,'OWNER_RESULT')['payload']
            _require(proof['purpose']=='CLEANUP' and all(proof[k]==before[k] for k in ('owner','owner_instance','action','resource','operation')) and proof['result']==('COMPLETE' if state=='COMPLETE' else 'FAILED'),'CLEANUP','cleanup exact result')
        payload=_copy(before);payload.update(previous=entry['head'],state=state,owner_result=result,failure=code)
        ref=self.store.publish(self.codec.encode('CLEANUP',payload,'PREDECESSOR',self.now_ns()));entry.update(head=ref,payload=payload)
        if state=='FAILED':self._failure=code
        return ref
    def start_cleanup(self,step):
        with self._lock:return self._cleanup_transition(step,'STARTED')
    def complete_cleanup(self,step,owner_result):
        with self._lock:return self._cleanup_transition(step,'COMPLETE',owner_result)
    def fail_cleanup(self,step,owner_result,code):
        with self._lock:return self._cleanup_transition(step,'FAILED',owner_result,code)
    def cleanup_payload(self,step):
        with self._lock:
            _require(step in self._cleanups,'CLEANUP','unknown cleanup step');return _copy(self._cleanups[step]['payload'])
    def publish_executor(self,payload):
        with self._lock:
            _require(not self._sealed,'ACCOUNTING','executor publication after seal');_require(self.original is not None and payload['original']==self.original and payload['lineage']==self.lineage,'ACCOUNTING','executor original binding')
            _require(payload['previous']==self.executor_head and payload['state']==('OWNED' if self.executor_head is None else 'TERMINATED'),'ACCOUNTING','executor transition')
            if payload['state']=='TERMINATED':
                for field in ('original_controller','no_child_start','no_consumption'):self.registry.verify(payload[field],'ORIGINAL_CONTROLLER',context={'mode':'ORIGINAL'})
                self.registry.verify(payload['completion'],'EXECUTOR_TERMINATION')
                _require(self.coordinator.original_execution_snapshot()['operational_owners']==0,'ACCOUNTING','original executor still running')
            self.executor_head=self.store.publish(self.codec.encode('EXECUTOR',payload,'PREDECESSOR',self.now_ns()));return self.executor_head
    def finalize_original(self,payload):
        with self._lock:
            self._mutable();snap=self.coordinator.snapshot()
            _require(type(self.registry) is EvidenceRegistry,'AUTHORITY','original operational preparation missing')
            _require(self.original is None and snap['state']=='FENCED' and payload['lineage']=={'predecessor':self.process,'generation':snap['generation']},'PROVENANCE','original before cleanup at fence')
            _require(self._inventory_payload is not None and self._inventory_payload['phase']=='ORIGINAL_FENCE','PROVENANCE','original inventory not frozen')
            for field,kind in (('source','SOURCE'),('capability','CAPABILITY'),('control','CONTROL_BINDING'),('authorization','ORIGINAL_AUTHORITY')):self.registry.verify(payload[field],kind,context={'mode':'ORIGINAL'})
            source=self.registry.verify(payload['source'],'SOURCE',context={'mode':'ORIGINAL'})['payload']
            _require(self._inventory_payload['process']==self.process and self._inventory_payload['source']==source['source_inventory'],'IDENTITY','frozen owner inventory differs from actual source')
            self.registry.verify(payload['owner_scope'],'SCOPE');_verify_scope_approvals(self.registry,payload['scope_approvals'])
            custody=self.codec.decode(self.store.resolve(payload['custody']),'CUSTODY')['payload'];_require(custody['lineage']==payload['lineage'] and custody['checkpoint_hash']==self.codec.key_id,'IDENTITY','original custody binding')
            self.registry.verify(custody['controller_capability'],'CONTROLLER_CAPABILITY',context={'mode':'ORIGINAL'});self.registry.verify(custody['live_control'],'CONTROL_BINDING',context={'mode':'ORIGINAL'})
            roster=self.coordinator.ticket_snapshot();admitted={o['ticket'].identity:o for o in self._operations.values()}
            _require(set(roster['fence'])<=set(admitted),'ACCOUNTING','unregistered accepted owner at original fence')
            tickets=[]
            for tid,o in sorted(admitted.items()):
                h=roster['history'][tid]
                tickets.append({'ticket':tid,'operation':o['payload']['operation'],'parent':h['parent'],'state':'OWNED' if h['released_ns'] is None else 'RELEASED','admission':_as_blob(o['admission'])})
            fence_payload={'identity':self._identity('fence'),'process':self.process,'generation':snap['generation'],'original_claim':payload['attempt'],'fenced_ns':str(self.now_ns()),'admissions':sorted([_as_blob(o['admission']) for o in admitted.values()],key=lambda v:v['identity']),'tickets':tickets}
            roster_evidence=self.publish_proof('FENCE_ROSTER',fence_payload)
            actual=_copy(payload);actual.update(accepted_roots=_refs(o['accepted'] for o in self._operations.values() if o['payload']['parent'] is None),accepted_heads=self.obligation_heads(),ticket_roster=roster_evidence)
            raw=self.codec.encode('ORIGINAL',actual,'PREDECESSOR',self.now_ns());self.original=self.store.publish(raw);self.lineage=actual['lineage'];self._original_payload=actual;return self.original
    def record_terminal(self,payload):
        with self._lock:
            _require(not self._sealed,'ACCOUNTING','terminal publication after seal');_require(self.terminal is None and self.original is not None,'PROVENANCE','terminal already recorded/missing original')
            snap=self.coordinator.failure_snapshot();mapping={'DRAIN_TIMEOUT':'TIMEOUT','CLEANUP_UNRESOLVED':'CLEANUP','OWNER_PROOF_UNAVAILABLE':'ACCOUNTING','HANDOFF_FAILED':'DURABILITY'}
            _require(snap['state']=='FAILED_FENCED' and payload['first_failure']==mapping[snap['failure']] and payload['original']==self.original and payload['lineage']==self.lineage and payload['original_deadline_ns']==self._original_payload['original_drain_deadline_ns'],'PROVENANCE','immutable original terminal facts')
            _require(payload['failed_ns']==str(snap['failed_ns']),'TIMEOUT','original first failure timestamp')
            self.registry.verify(payload['failure_evidence'],'FAILURE_FACT')
            actual=_copy(payload);actual.update(obligations=self.obligation_heads(),cleanup=self.cleanup_heads(),executor=self.executor_head)
            self.terminal=self.store.publish(self.codec.encode('TERMINAL',actual,'PREDECESSOR',self.now_ns()));self._terminal_payload=actual;return self.terminal
    def obligation_heads(self):return _refs(o['head'] for o in self._operations.values())
    def cleanup_heads(self):return _refs(o['head'] for o in self._cleanups.values())
    def original_binding(self):
        _require(self.original is not None and self.terminal is not None and self.executor_head is not None,'PROVENANCE','original lineage incomplete')
        return {'lineage':_copy(self.lineage),'original':_copy(self.original),'terminal':_copy(self.terminal),'obligations':self.obligation_heads(),'cleanup':self.cleanup_heads(),'executor':_copy(self.executor_head)}
    def reconcile(self,claim_ns,*,complete=False):
        with self._lock:
            self._mutable();_require(self._ineligible is None,'PROVENANCE','prospectively recorded ineligible owner outcome')
            _require(self._inventory_payload is not None and self._inventory_payload['phase']=='ORIGINAL_FENCE','PROVENANCE','complete frozen composition missing')
            history=self.coordinator.ticket_snapshot()['history'];known=set()
            for operation,o in self._operations.items():
                p=o['payload'];h=history[o['ticket'].identity]
                if self.coordinator.is_live(o['ticket']):known.add(o['ticket'].identity)
                if h['released_ns'] is not None:_require(o['completed_ns'] is not None and h['released_ns']>=o['completed_ns'],'ACCOUNTING','release before durable operation completion')
                _require(p['state']!='FAILED','PROVENANCE','failed operation')
                if complete:_require(p['state']=='COMPLETE','ACCOUNTING','unfinished product effect/reference')
                elif p['state']!='COMPLETE':_require(p['relation']=='WO11_PUBLICATION' or p['relation'] in schema.REFERENCE_ACTIONS,'AUTHORITY','unsupported active operation')
                for child in p['required_children']:_require(child in self._operations and self._operations[child]['payload']['parent']==o['accepted'],'PROVENANCE','required child missing')
                required=[v for v in self._peers.values() if v['payload']['operation']==operation]
                for peer in required:
                    fulfillment=self._fulfillments.get(peer['payload']['identity'])
                    _require(fulfillment is not None and fulfillment['completed_ns']<int(claim_ns),'PROVENANCE','peer incomplete at claim')
                    self.registry.verify(fulfillment['evidence'],'PEER_FULFILLMENT',context={'claim_ns':str(claim_ns)})
                    if p['state']!='COMPLETE':_require(peer['payload']['predicate'] in {'OWNER_SLOT_NOT_INSTALLED','JOURNAL_TRACK_UNCHANGED','JOURNAL_UNSUPPORTED_KIND','BOOKS_NO_SOURCE_EDGE'},'AUTHORITY','active publication has required historical peer')
            _require(set(self._cleanups)=={s['step'] for s in self._inventory_payload['cleanup']},'CLEANUP','complete cleanup target roster')
            for c in self._cleanups.values():
                state=c['payload']['state'];_require(state in ({'COMPLETE','NOT_APPLICABLE'} if complete else {'COMPLETE','NOT_APPLICABLE','NOT_STARTED'}),'CLEANUP','unknown/interrupted cleanup outcome')
            return known
    def reference_completion(self,owner,obligation,accounting):
        from kronos.application.failed_fenced_owners import NativeOwnerAccounting
        _require(type(accounting) is NativeOwnerAccounting and accounting.ledger is self,'AUTHORITY','fixed native reference adapter')
        return accounting.reference_completion(owner,obligation)

def _as_blob(evidence):
    return {k:evidence[k] for k in ('identity','hash','bytes')}

def _refs(refs):
    result=sorted((_copy(r) for r in refs),key=lambda r:r['hash'])
    _require(len({r['hash'] for r in result})==len(result),'PROVENANCE','duplicate chain heads');return result

def _verify_scope_approvals(registry,approvals):
    _require([x['authority'] for x in approvals]==['CA','EA-INTRADAY','EA-SWING','PCP'],'AUTHORITY','four exact scope owners')
    for approval in approvals:registry.verify(approval,'SCOPE_APPROVAL')

class _ProspectiveEvidenceWriter:
    """Schema/native fact checking before later operational preparation.

    This type cannot be passed to RecoveryTransaction. Its records remain
    unauthoritative until an EvidenceRegistry validates the complete historical
    graph under the exact subsequently approved preparation. It cannot validate
    approvals, authority, controller rights, source capability, or recovery.
    """
    def __init__(self,codec,store,process):
        self.codec=codec;self.store=store;self.process=process;self._native_contexts={};self._validated_sources={}
    @property
    def native_ledger(self):return getattr(self,'_native_ledger',None)
    _proof_reference=staticmethod(EvidenceRegistry._proof_reference)
    proof_evidence=EvidenceRegistry.proof_evidence
    native_evidence=EvidenceRegistry.native_evidence
    _blob=EvidenceRegistry._blob
    _inventory=EvidenceRegistry._inventory_structure
    _active_composition_scope=EvidenceRegistry._active_composition_scope
    _composition_dependency=EvidenceRegistry._composition_dependency
    _native_source=EvidenceRegistry._native_source
    _peer_registration=EvidenceRegistry._peer_registration
    _peer_fulfillment=EvidenceRegistry._peer_fulfillment
    _owner_result=EvidenceRegistry._owner_result
    def _issuer(self,proof,subject,context):
        _require(proof['role']=='PREDECESSOR' and proof['issuer']==self.process and proof['payload'].get('process',self.process)==self.process,'IDENTITY','actual prospective issuer')
    def _validate(self,proof,context):
        kind=proof['kind'];p=proof['payload']
        if kind=='COMPOSITION_INVENTORY':self._inventory(p)
        elif kind=='PEER_REGISTRATION':self._peer_registration(p)
        elif kind=='PEER_FULFILLMENT':
            if p['outcome']=='FAILED':
                registration=self.verify_blob(p['registration'],'PEER_REGISTRATION')['payload']
                _require(p['execution_owner']==registration['ticket'],'PROVENANCE','negative peer original ticket')
                from kronos.intraday.failed_fenced_native_evidence import verify_native_peer_fulfillment
                verify_native_peer_fulfillment(registration,p,self)
            else:self._peer_fulfillment(p,context)
        elif kind=='OWNER_RESULT':self._owner_result(p,context)
        elif kind=='SOURCE':self._native_source(p)
        elif kind=='CAPABILITY':
            self.verify_blob(p['source'],'SOURCE',subject=self.process)
            expected=getattr(self.native_ledger,'native_capability_payload',None)
            _require(expected is not None and p==expected,'PROVENANCE','actual captured capability required')
            for field in ('implementation','owner_scope','operation_manifest','tail_plan'):self._blob(p[field])
        elif kind=='CONTROL_BINDING':
            self.codec.verify_control_binding(p,self.store)
        elif kind=='ENDPOINT_CONFIGURATION':
            ledger=self.native_ledger
            _require(ledger is not None and getattr(ledger,'native_endpoint_payload',None)==p,
                     'PROVENANCE','actual captured endpoint required')
            server=getattr(ledger,'native_server',None)
            _require(server is not None and server.socket.getsockname()==(p['host'],int(p['port']))
                     and server.server_port==int(p['port']),'IDENTITY','actual listener changed')
            self.verify_blob(p['source'],'SOURCE')
            for field in ('configuration','listener'):self._blob(p[field])
        elif kind=='ISSUED_ADMISSION':
            _require(p['scope']['hash']==SCOPE_HASH,'PROVENANCE','prospective scope');self._blob(p['input']);self._blob(p['effect'])
        elif kind=='FAILURE_FACT':
            _require(p['original_failure'] is None,'PROVENANCE','prospective failure cannot invent original history')
            for blob in p['owner_facts']:self._blob(blob)
        else:raise RecoveryError('AUTHORITY','operational preparation required for this proof')
    def verify(self,evidence,expected_kind,subject=None,context=None):
        _check_type('Evidence',evidence);raw=self.store.read_blob(evidence);context={} if context is None else context
        if expected_kind=='SCOPE':
            _require(evidence=={'authority':'CA','contract':PROTOCOL+':'+VERSION,'identity':'FAILED_FENCED_INITIAL_OWNER_SCOPE_V1','hash':SCOPE_HASH,'bytes':SCOPE_BYTES},'PROVENANCE','frozen scope bytes');return {'kind':'SCOPE','payload':{'hash':SCOPE_HASH}}
        if expected_kind=='NATIVE':
            from kronos.intraday.failed_fenced_native_evidence import CLOSED_NATIVE_CONTRACTS,verify_native_evidence
            _require((evidence['authority'],evidence['contract']) in CLOSED_NATIVE_CONTRACTS,'PROVENANCE','unknown native contract');return verify_native_evidence(evidence,raw,context)
        proof=self.codec.decode_proof(raw,expected_kind)
        return self._verify_proof(evidence,raw,proof,subject,context)
    def _verify_proof(self,evidence,raw,proof,subject,context):
        with _evidence_path(self,evidence['hash']):
            _require(self._proof_reference(proof,raw)==evidence,'PROVENANCE','prospective proof reference')
            self._issuer(proof,subject,context);self._validate(proof,context);return proof
    def verify_blob(self,blob,kind,subject=None,context=None):
        raw=self.store.read_blob(blob);proof=self.codec.decode_proof(raw,kind)
        return self._verify_proof(self._proof_reference(proof,raw),raw,proof,subject,{} if context is None else context)

class RecoveryTransaction:
    """Distinct transaction; the predecessor's ordinary state stays FAILED_FENCED."""
    def __init__(self,coordinator,ledger,codec,store,registry,budget):
        _require(type(coordinator) is MaintenanceAdmissionCoordinator and type(ledger) is ProspectiveLedger and type(registry) is EvidenceRegistry and type(budget) is RecoveryBudget,'AUTHORITY','typed recovery transaction')
        _require(ledger.coordinator is coordinator and ledger.codec is codec and ledger.store is store and registry.codec is codec and registry.store is store,'IDENTITY','shared recovery ownership')
        _require(registry.preparation.record['mode']=='RECOVERY' and ledger.lineage==registry.preparation.record['lineage'],'AUTHORITY','separate recovery preparation')
        _require(budget.clock==codec.clock,'TIMEOUT','shared clock')
        self.coordinator=coordinator;self.ledger=ledger;self.codec=codec;self.store=store;self.registry=registry;self.budget=budget
        self.slot=slot_key(ledger.lineage);self.state='GUARDED';self.work_deadline_ns=None;self.claim=None;self.accepted=None
        self._claim_raw=None;self._claim_payload=None;self._seal_payload=None;self._owner_payload=None;self._certificate_payload=None
        self._published={};self._publisher=None;self._publication_complete_ns=None;self._released_ns=None;self._ack=None
        self._lock=RLock();self._tail=False;self._original_failure=coordinator.failure_snapshot()
        self._execution_thread=None;self._execution_closed=False;self._failure_record=None;self._failure_publication_error=None
        registry.bind_native_ledger(ledger)
    @property
    def write_free_tail_required(self):return self._tail
    @property
    def released(self):return self._released_ns is not None
    @property
    def claim_ns(self):
        _require(hasattr(self,'_claim_ns'),'ACCOUNTING','claim has not been accepted')
        return self._claim_ns
    def _fail(self,error):
        self.state='SPENT_FAILED';self.coordinator.fail_recovery(error.code if isinstance(error,RecoveryError) else 'INTERRUPTED')
    @contextmanager
    def execution(self):
        """Bind the one actual handler through transport and its final return."""
        from threading import current_thread
        with self._lock:
            _require(self._execution_thread is None and not self._execution_closed,'ACCOUNTING','recovery execution already dispatched')
            self._execution_thread=current_thread()
        try:
            yield self
        except BaseException as exc:
            self.fail(exc)
            raise
        finally:
            with self._lock:
                # This observes return of this exact synchronous execution. It
                # does not join, abandon or zero any separate product owner.
                if self.state not in {'ACKNOWLEDGED','SPENT_FAILED'}:
                    self.fail(RecoveryError('INTERRUPTED','recovery execution returned incomplete'))
                snap=self.coordinator.recovery_snapshot()
                if snap is not None and snap['state']=='SPENT_FAILED' and snap['owners']==1:
                    self.coordinator.finish_failed_recovery_execution(snap['transaction'])
                self._execution_closed=True
    def fail(self,error):
        """Retain a bounded pre-seal failure; never write after the seal."""
        from threading import current_thread
        with self._lock:
            _require(self._execution_thread is current_thread() and not self._execution_closed,'ACCOUNTING','failure outside actual recovery execution')
            phase=next((k for k in ('PREPARED_COMMIT','CERTIFICATE','OWNER_PROOF','SEAL') if k in self._published),'CLAIM_ACCEPTED' if self.accepted is not None else 'CLAIM')
            self._fail(error)
            snap=self.coordinator.recovery_snapshot()
            if self._tail or self._released_ns is not None or self._failure_record is not None or self._failure_publication_error is not None or snap is None:
                return self._failure_record
            try:
                observed=self.budget.check(self.work_deadline_ns)
                code=error.code if isinstance(error,RecoveryError) else 'INTERRUPTED'
                fact={'identity':'recovery-failure:'+self.slot[:32],'process':self.ledger.process,'phase':phase,'code':code,'original_failure':_as_blob(self.ledger._terminal_payload['failure_evidence']),'observed_ns':str(observed),'owner_facts':[],'outstanding_owners':str(snap['owners'])}
                evidence=self.ledger.publish_proof('FAILURE_FACT',fact)
                payload={'slot':self.slot,'transaction':self._claim_payload['transaction'],'phase':phase,'code':code,'earlier':self.accepted or self.claim,'observed_ns':str(observed),'evidence':evidence,'outstanding_owners':str(snap['owners'])}
                self.budget.check(self.work_deadline_ns)
                self._failure_record=self.store.publish(self.codec.encode('FAILURE',payload,'PREDECESSOR',observed))
                self.budget.check(self.work_deadline_ns)
            except BaseException as publication_error:
                # Retain ambiguity; no retry, repair, new allowance or false
                # zero is produced when even failure publication cannot finish.
                self._failure_publication_error=publication_error
            return self._failure_record
    def _check_original(self):
        _require(self.coordinator.failure_snapshot()==self._original_failure and self._original_failure['state']=='FAILED_FENCED','PROVENANCE','original terminal mutation')
    def expected_claim_raw(self):
        # Publish no validated claim state until the complete read-only scope
        # has rechecked retained dependencies/ancestry and the deadline holds.
        with self._lock:
            with self.registry._composition_validation(self.budget.check):
                raw,p,guard_payload=self._read_expected_claim()
            self.budget.check()
            self._claim_raw=raw;self._claim_payload=p
            self._guard_payload=guard_payload;self.claim=record_ref(raw)
            return raw

    def _read_expected_claim(self):
        _require(self.state=='GUARDED','PROTOCOL','claim exchange already used');self.budget.check();self._check_original()
        raw=self.store.read_reservation(self.slot,'claim');claim=self.codec.decode(raw,'CLAIM');p=claim['payload']
        _require(p['slot']==self.slot and p['transaction']==self.registry.preparation.record['attempt'] and p['binding']['lineage']==self.ledger.lineage,'IDENTITY','reserved claim lineage')
        _require(p['limits']=={'clock':self.budget.clock,'origin_ns':str(self.budget.origin_ns),'stop_deadline_ns':str(self.budget.stop_deadline_ns)},'TIMEOUT','claim budget identity')
        guard=self.codec.decode(self.store.read_reservation(self.slot,'guard'),'GUARD')
        _require(record_ref(canonical_bytes(guard))==p['guard'] and guard['payload']['slot']==self.slot and guard['payload']['binding']==p['binding'] and guard['payload']['transaction']==p['transaction'] and guard['payload']['authorization']==p['authorization'] and guard['payload']['limits']==p['limits'],'PROVENANCE','guard claim binding')
        _require(p['launcher']==self.registry.preparation.record['controller'],'IDENTITY','prepared actual launcher')
        self.registry.verify(p['authorization'],'RECOVERY_AUTHORITY');_verify_scope_approvals(self.registry,p['scope_approvals'])
        self.registry.verify(guard['payload']['scope'],'SCOPE')
        self.registry.verify(p['launcher_capability'],'CONTROLLER_CAPABILITY')
        endpoint=self.registry.verify(p['endpoint']['configuration'],'ENDPOINT_CONFIGURATION')['payload']
        _require(endpoint['process']==self.ledger.process and endpoint['host']==p['endpoint']['host'] and endpoint['port']==p['endpoint']['port'],'IDENTITY','claim listener')
        _require(p['successor_source']==p['successor_capability'],'AUTHORITY','approved target identity')
        target=self.registry.verify(p['successor_source'],'TARGET_ARTIFACT')['payload']
        artifacts=self.registry.verify(guard['payload']['artifacts'],'ARTIFACT_APPROVAL')['payload']
        _require(artifacts['identity']==target['approval'],'AUTHORITY','guard target artifact decision')
        for field,kind in (('installed_package','PACKAGE'),('rollback_package','PACKAGE'),('compatibility','COMPATIBILITY')):self.registry.verify(p[field],kind)
        self._validate_original_binding(p['binding'])
        self.budget.check();return raw,p,guard['payload']

    def _validate_original_binding(self,binding):
        _require(binding['original']==self.ledger.original and binding['terminal']==self.ledger.terminal and binding['executor']==self.ledger.executor_head,'PROVENANCE','retained original binding')
        original=self.codec.decode(self.store.resolve(binding['original']),'ORIGINAL')['payload'];terminal=self.codec.decode(self.store.resolve(binding['terminal']),'TERMINAL')['payload']
        _require(original==self.ledger._original_payload and terminal==self.ledger._terminal_payload and terminal['original']==binding['original'],'PROVENANCE','original terminal bytes')
        for field,kind in (('source','SOURCE'),('capability','CAPABILITY'),('control','CONTROL_BINDING'),('authorization','ORIGINAL_AUTHORITY'),('ticket_roster','FENCE_ROSTER')):self.registry.verify(original[field],kind,context={'mode':'ORIGINAL'})
        self.registry.verify(original['owner_scope'],'SCOPE');_verify_scope_approvals(self.registry,original['scope_approvals'])
        executor=self.codec.decode(self.store.resolve(binding['executor']),'EXECUTOR')['payload']
        _require(executor['state']=='TERMINATED' and executor['lineage']==binding['lineage'] and executor['original']==binding['original'],'ACCOUNTING','original executor not terminated')
        for field in ('original_controller','no_child_start','no_consumption'):self.registry.verify(executor[field],'ORIGINAL_CONTROLLER',context={'mode':'ORIGINAL'})
        self.registry.verify(executor['completion'],'EXECUTOR_TERMINATION',context={'mode':'ORIGINAL'})
        self._check_heads(binding['obligations'],self.ledger.obligation_heads(),'OBLIGATION')
        self._check_heads(binding['cleanup'],self.ledger.cleanup_heads(),'CLEANUP')
    def _check_heads(self,old,new,kind):
        _require(len(old)==len(new),'PROVENANCE','journal head completeness')
        oldmap={};newmap={};identity='obligation' if kind=='OBLIGATION' else 'step'
        for refs,mapping in ((old,oldmap),(new,newmap)):
            for ref in refs:
                record=self.codec.decode(self.store.resolve(ref),kind);name=record['payload'][identity]
                _require(name not in mapping,'PROVENANCE','duplicate journal identity');mapping[name]=(ref,record['payload'])
        _require(set(oldmap)==set(newmap),'PROVENANCE','journal roster changed')
        for name,(head,payload) in newmap.items():
            visited=set()
            while head!=oldmap[name][0]:
                _require(head['hash'] not in visited and len(visited)<4096 and payload['previous'] is not None,'PROVENANCE','journal does not descend from claim')
                visited.add(head['hash']);head=payload['previous'];payload=self.codec.decode(self.store.resolve(head),kind)['payload']
                _require(payload[identity]==name,'PROVENANCE','journal chain identity')
    def accept_claim(self,raw,current_control_bytes):
        with self._lock:
            try:
                expected=self.expected_claim_raw() if self._claim_raw is None else self._claim_raw
                _require(type(raw) is bytes and hmac.compare_digest(raw,expected),'PROTOCOL','wire claim differs from reservation')
                _require(self.codec.matches_control(current_control_bytes) and self.codec.matches_control(self.store.read_custody(self.codec.key_id)),'IDENTITY','current/retained control mismatch')
                claim_ns=self.budget.check();self.work_deadline_ns=self.budget.claim(claim_ns)
                known=self.ledger.reconcile(claim_ns)
                self.coordinator.claim_recovery(self._claim_payload['transaction'],known)
                # Counting begins atomically before any accepted publication.
                self.state='ACCEPTED';self._claim_ns=claim_ns
                original=self.ledger._original_payload
                payload={'slot':self.slot,'claim':self.claim,'transaction':self._claim_payload['transaction'],'predecessor':self.ledger.process,'capability':original['capability'],'control':original['control'],'claim_ns':str(claim_ns),'work_deadline_ns':str(self.work_deadline_ns),'executor':self.ledger.executor_head,'active_obligations':_refs(o['head'] for o in self.ledger._operations.values() if o['payload']['state']!='COMPLETE')}
                self.accepted=self.store.publish(self.codec.encode('CLAIM_ACCEPTED',payload,'PREDECESSOR',self.budget.check(self.work_deadline_ns)))
                self.budget.check(self.work_deadline_ns);return self.accepted
            except BaseException as exc:self._fail(exc);raise
    def wait_for_accepted_completion(self):
        _require(self.state=='ACCEPTED','ACCOUNTING','recovery not accepted')
        try:
            self.budget.check(self.work_deadline_ns)
            _require(self.coordinator.wait_recovery_zero(self._claim_payload['transaction'],self.work_deadline_ns),'TIMEOUT','accepted owners still active')
            self.budget.check(self.work_deadline_ns)
        except BaseException as exc:self._fail(exc);raise
    def seal(self,checkpoint,owner_results,reconciliation,write_free_tail,retained_control,publisher):
        with self._lock,self.ledger._lock:
            try:
                _require(self.state=='ACCEPTED','ACCOUNTING','seal phase');_check_type('Id',publisher);_check_type('Checkpoint',checkpoint)
                self.budget.check(self.work_deadline_ns);self._check_original();self.ledger.reconcile(self._claim_ns,complete=True)
                _require((checkpoint['state']=='EMPTY')==(checkpoint['pending']=='0'),'NOTIFICATION','checkpoint state/count')
                context=self._reconciliation_context(checkpoint)
                reconcile=self.registry.verify(reconciliation,'OWNER_RESULT',context=context)['payload']
                _require(reconcile['purpose']=='RECONCILIATION' and reconcile['result']=='COMPLETE','NOTIFICATION','notice reconciliation')
                check=self.registry.verify(checkpoint['evidence'],'OWNER_RESULT',context=context)['payload']
                _require(check['purpose']=='CHECKPOINT' and check['result']=='COMPLETE','NOTIFICATION','durable checkpoint proof')
                with self.registry._composition_validation(lambda:self.budget.check(self.work_deadline_ns)):
                    results=[self.registry.verify(r,'OWNER_RESULT',context={'claim_ns':str(self._claim_ns),**context})['payload'] for r in owner_results]
                self._complete_owner_roster(results)
                tail=self.registry.verify(write_free_tail,'TAIL')['payload'];control=self.registry.verify(retained_control,'CONTROL_BINDING')['payload']
                _require(tail['process']==self.ledger.process and tail['executor']==publisher and set(tail['completed_cleanup'])==set(self.ledger._cleanups),'ACCOUNTING','tail actual cleanup/owner')
                _require(control['process']==self.ledger.process,'IDENTITY','retained control process')
                _require(any(c['payload']['owner']=='CONTROL' and c['payload']['state']=='COMPLETE' for c in self.ledger._cleanups.values()),'CLEANUP','control removal not complete')
                heads=self.ledger.obligation_heads();cleanup=self.ledger.cleanup_heads();self.budget.check(self.work_deadline_ns)
                # No domain/validation/I/O is performed under the coordinator
                # mutex. This single transition bans descendants and transfers
                # exactly one execution owner into the publisher.
                sealed_ns=self.coordinator.seal_recovery(self._claim_payload['transaction'],self.work_deadline_ns)
                self.ledger._sealed=True;self.store._sealed=True;self._tail=True;self.state='SEALED';self._publisher=publisher
                self._seal_payload={'slot':self.slot,'claim':self.claim,'accepted':self.accepted,'transaction':self._claim_payload['transaction'],'seal':'seal:'+self.slot[:32],'sealed_ns':str(sealed_ns),'obligation_heads':heads,'cleanup_heads':cleanup,'owner_scope':self.ledger.scope,'checkpoint':_copy(checkpoint),'product_owners':'0','accepted_owners':'0','commit_owners':'1','publisher':publisher,'write_free_tail':write_free_tail,'retained_control':retained_control}
                self._owner_payload={'slot':self.slot,'claim':self.claim,'seal':None,'transaction':self._claim_payload['transaction'],'binding':self._claim_payload['binding'],'obligation_heads':heads,'cleanup_heads':cleanup,'owner_results':_copy(owner_results),'reconciliation':reconciliation,'checkpoint':_copy(checkpoint),'product_owners':'0','accepted_owners':'0','commit_owners':'1','publisher':publisher}
                self._certificate_payload={'slot':self.slot,'transaction':self._claim_payload['transaction'],'claim':self.claim,'accepted':self.accepted,'seal':None,'owner_proof':None,'authorization':self._claim_payload['authorization'],'artifacts':self._guard_payload['artifacts'],'scope':self.ledger.scope,'limits':self._claim_payload['limits'],'work_deadline_ns':str(self.work_deadline_ns)}
                return _copy(self._seal_payload)
            except BaseException as exc:self._fail(exc);raise
    def _reconciliation_context(self,checkpoint):
        _require(hasattr(self,'_certified_checkpoint') and checkpoint==self._certified_checkpoint,'NOTIFICATION','native whole-set certification required')
        _require(self._notification_owner.checkpoint(certify_durable=True)==self._native_checkpoint,'NOTIFICATION','native checkpoint changed before seal')
        return {'accepted_heads':self.ledger.obligation_heads()}
    def _complete_owner_roster(self,results):
        slots=self.ledger._inventory_payload['slots'];expected={(s['owner'],i) for s in slots for i in (s['instances'] if s['presence']=='INSTALLED' else [s['slot']])}
        absent=[r for r in results if r['purpose']=='ABSENCE']
        _require({(r['owner'],r['owner_instance']) for r in absent}==expected and len(absent)==len(expected),'ACCOUNTING','all actual owners require separate absence proof')
        for r in absent:
            _require(r['result'] in {'COMPLETE','NOT_APPLICABLE'},'ACCOUNTING','owner not quiescent')
        _require({r['operation'] for r in results if r['purpose']=='CLEANUP'}=={c['payload']['operation'] for c in self.ledger._cleanups.values()},'CLEANUP','cleanup result coverage')
    def publish_commit(self):
        with self._lock:
            try:
                _require(self.state=='SEALED','ACCOUNTING','publisher phase')
                transaction=self._claim_payload['transaction']
                for kind in ('SEAL','OWNER_PROOF','CERTIFICATE','PREPARED_COMMIT'):
                    if kind=='SEAL':payload=self._seal_payload
                    elif kind=='OWNER_PROOF':payload={**self._owner_payload,'seal':self._published['SEAL']}
                    elif kind=='CERTIFICATE':payload={**self._certificate_payload,'seal':self._published['SEAL'],'owner_proof':self._published['OWNER_PROOF']}
                    else:payload={'slot':self.slot,'transaction':transaction,'seal':self._published['SEAL'],'owner_proof':self._published['OWNER_PROOF'],'certificate':self._published['CERTIFICATE'],'publisher':self._publisher,'product_owners':'0','accepted_owners':'0','commit_owners':'1'}
                    raw=self.codec.encode(kind,payload,'PREDECESSOR',self.budget.check(self.work_deadline_ns));self._published[kind]=self.store.publish(raw)
                    self.budget.check(self.work_deadline_ns)
                self._publication_complete_ns=self.budget.check(self.work_deadline_ns);self.state='PREPARED';return _copy(self._published)
            except BaseException as exc:self._fail(exc);raise
    def release_ack(self):
        with self._lock:
            try:
                _require(self.state=='PREPARED' and self._publication_complete_ns is not None,'ACCOUNTING','release before complete publication')
                self.budget.check(self.work_deadline_ns);self._check_original()
                self._released_ns=self.coordinator.release_recovery(self._claim_payload['transaction'],self.work_deadline_ns)
                ack_ns=self.budget.check(self.work_deadline_ns)
                payload={'slot':self.slot,'transaction':self._claim_payload['transaction'],'claim':self.claim,'seal':self._published['SEAL'],'owner_proof':self._published['OWNER_PROOF'],'certificate':self._published['CERTIFICATE'],'prepared':self._published['PREPARED_COMMIT'],'predecessor':self.ledger.process,'control_challenge':self._claim_payload['control_challenge'],'publication_complete_ns':str(self._publication_complete_ns),'released_ns':str(self._released_ns),'ack_ns':str(ack_ns),'publisher':self._publisher,'recovery_owners':'0','release':'CONFIRMED','deadline':'WITHIN','work_deadline_ns':str(self.work_deadline_ns),'stop_deadline_ns':str(self.budget.stop_deadline_ns)}
                self._ack=self.codec.encode('ACK',payload,'PREDECESSOR',ack_ns);self.state='ACKNOWLEDGED';return self._ack
            except BaseException as exc:self._fail(exc);raise

class OriginalExecutorWitness:
    """Actual original thread/operation completion, retained by its observer.

    The executor cannot certify its own return. A distinct observer joins the
    exact registered Thread and every registered helper, then freezes the real
    operation ledger. Expiry does not abandon or zero any outstanding owner.
    """
    def __init__(self,coordinator,executor,original_controller,original_attempt):
        from threading import Event
        _require(type(coordinator) is MaintenanceAdmissionCoordinator,'ACCOUNTING','original coordinator')
        _check_type('Id',executor);_check_type('Id',original_attempt);_check_type('Process',original_controller)
        self.coordinator=coordinator;self.executor=executor;self.original_controller=_copy(original_controller);self.original_attempt=original_attempt
        self._lock=RLock();self._returned=Event();self._thread=None;self._helpers={};self._accepted=set();self._completed=set();self._outstanding=set();self._closed=False;self._join_attempted=False;self._joined_ns=None
        self._controller_operations=None;self._controller_closure=None
    def bind_thread(self,thread):
        from threading import Thread
        with self._lock:
            _require(type(thread) is Thread and thread.ident is None and self._thread is None,'ACCOUNTING','original actual thread must register before start')
            self._thread=thread
    @contextmanager
    def operation(self,identity):
        from threading import current_thread
        _check_type('Id',identity)
        with self._lock:
            _require(current_thread() is self._thread and not self._closed and not self._returned.is_set() and identity not in self._accepted,'ACCOUNTING','original operation admission')
            self._accepted.add(identity);self._outstanding.add(identity)
        try:yield
        finally:
            with self._lock:
                self._outstanding.remove(identity);self._completed.add(identity)
    def register_helper(self,identity,thread):
        from threading import Thread,current_thread
        _check_type('Id',identity)
        with self._lock:
            _require(current_thread() is self._thread and type(thread) is Thread and thread.ident is None and not self._closed and identity not in self._accepted,'ACCOUNTING','original helper registration before dispatch')
            self._helpers[identity]=thread;self._accepted.add(identity);self._outstanding.add(identity)
    def return_observed(self):
        from threading import current_thread
        with self._lock:
            _require(current_thread() is self._thread and not self._returned.is_set(),'ACCOUNTING','original return witness')
            # This event alone is deliberately insufficient for termination.
            self._returned.set()
    def join_and_close(self,budget,deadline_ns=None):
        from threading import current_thread
        with self._lock:
            _require(self._thread is not None and current_thread() is not self._thread and not self._closed and not self._join_attempted,'ACCOUNTING','independent original join observer, once')
            self._join_attempted=True;thread=self._thread
        thread.join(budget.remaining_seconds(deadline_ns));budget.check(deadline_ns)
        _require(not thread.is_alive() and self._returned.is_set(),'ACCOUNTING','original executor not actually joined')
        with self._lock:helpers=tuple(self._helpers.items())
        for identity,helper in helpers:
            helper.join(budget.remaining_seconds(deadline_ns));budget.check(deadline_ns)
            _require(not helper.is_alive(),'ACCOUNTING','original helper still owned')
            with self._lock:self._outstanding.remove(identity);self._completed.add(identity)
        with self._lock:
            _require(not self._outstanding and self._accepted==self._completed,'ACCOUNTING','original operation ledger incomplete')
            self._joined_ns=budget.check(deadline_ns);self._closed=True
            self.coordinator.complete_original_execution(self.executor)
            return self._joined_ns
    def termination_payload(self,identity,process,lineage):
        with self._lock:
            _require(self._closed and self._joined_ns is not None,'ACCOUNTING','original executor closure not observed')
            operations=self._accepted if self._controller_operations is None else self._controller_operations
            return {'identity':identity,'process':_copy(process),'lineage':_copy(lineage),'executor':self.executor,'original_controller':self.original_controller,'original_attempt':self.original_attempt,'accepted_operations':sorted(operations),'completed_operations':sorted(operations),'owned_workers':'0','pending_callbacks':'0','pending_publications':'0','joined_ns':str(self._joined_ns),'state':'TERMINATED'}
    def observe_controller_closure(self,registry,evidence,lineage):
        """Join local work first, then independently observe C's closed ledger.

        C publishes CONTROLLER_CLOSURE without a P termination dependency. The
        observer validates that immutable, authenticated native ledger before P
        attests its complete original work set. Local accepted/completed sets
        remain unchanged; unknown operations or caller booleans never close it.
        """
        _require(type(registry) is EvidenceRegistry and registry._executor_witnesses.get(self.executor) is self,
                 'ACCOUNTING','bound original controller observer required')
        proof=registry.verify(evidence,'CONTROLLER_CLOSURE',context={'mode':'ORIGINAL'})
        closure=proof['payload'];cap=registry.verify_blob(closure['capability'],'CONTROLLER_CAPABILITY',context={'mode':'ORIGINAL'})['payload']
        expected='controller-closure-'+sha256(canonical_bytes({'attempt':self.original_attempt,'controller':self.original_controller})).hexdigest()
        _require(closure['identity']==expected and closure['controller']==self.original_controller
                 and closure['attempt']==self.original_attempt and closure['lineage']==lineage
                 and cap['controller']==self.original_controller and cap['predecessor']==lineage['predecessor']
                 and cap['phase']=='ORIGINAL','IDENTITY','original controller closure lineage')
        admissions=[registry.verify_blob(ref,'CONTROLLER_ADMISSION',context={'mode':'ORIGINAL'})['payload'] for ref in closure['admissions']]
        heads=[registry.verify_blob(ref,'CONTROLLER_DISPATCH',context={'mode':'ORIGINAL'})['payload'] for ref in closure['dispatch_heads']]
        operations=frozenset(item['operation'] for item in admissions)
        _require(len(operations)==len(admissions) and all(item['attempt']==self.original_attempt
                 and item['controller']==self.original_controller and item['lineage']==lineage for item in admissions+heads),
                 'ACCOUNTING','exact native original operation roster')
        with self._lock:
            _require(self._closed and self._joined_ns is not None and not self._outstanding
                     and self._accepted==self._completed and self._accepted<=operations
                     and self._controller_closure is None,'ACCOUNTING','local executor must actually join before native observation, once')
            state=self.coordinator.original_execution_snapshot()
            _require(state['executor']==self.executor and state['state']=='PUBLISHING'
                     and state['operational_owners']==0 and state['publisher_owners']==1,
                     'ACCOUNTING','original closure publisher must remain owned')
            self._controller_operations=operations;self._controller_closure=_copy(evidence)
        return _copy(evidence)
    def validate(self,payload):
        _require(payload==self.termination_payload(payload['identity'],payload['process'],payload['lineage']),'ACCOUNTING','executor proof disagrees with actual joined ledger')
        state=self.coordinator.original_execution_snapshot()
        _require(state['executor']==self.executor and state['state'] in {'PUBLISHING','COMPLETE'} and state['operational_owners']==0,'ACCOUNTING','original executor ownership still live')

def _verify_notice_set(payload,registry,context):
    """Fixed native WO13 checkpoint plus complete accepted-obligation bijection."""
    from .maintenance import _valid_notification_checkpoint
    heads=context.get('accepted_heads')
    _require(type(heads) is list,'NOTIFICATION','complete accepted heads required')
    operations={}
    for ref in heads:
        p=registry.codec.decode(registry.store.resolve(ref),'OBLIGATION')['payload']
        _require(p['operation'] not in operations and p['state']=='COMPLETE','NOTIFICATION','duplicate/incomplete obligation')
        operations[p['operation']]=p
    required={key:p for key,p in operations.items() if p['relation'] in schema.REFERENCE_ACTIONS}
    _require(payload['obligations']==sorted(required),'NOTIFICATION','reference obligation coverage')
    expected={}
    kinds={'WO09_READINESS_REFERENCE':'READINESS','WO09_CURRENTNESS_REFERENCE':'CURRENTNESS','WO10_COMPARISON_REFERENCE':'COMPARISON','WO10_UNAVAILABLE_REFERENCE':'UNAVAILABLE','WO11_TRACK_REFERENCE':'TRACK'}
    for operation,p in operations.items():
        for child in p['required_children']:
            _require(child in operations and operations[child]['parent'] is not None,'NOTIFICATION','missing required callback obligation')
    for p in required.values():
        _require(len(p['notices'])==1,'NOTIFICATION','missing/ambiguous committed notice')
        notice=p['notices'][0];identity=bytes.fromhex(notice['identity']['bytes']).decode('utf-8')
        key=sha256((kinds[p['relation']]+':'+identity).encode()).hexdigest()
        _require(key not in expected,'NOTIFICATION','repeated reference key')
        expected[key]=(kinds[p['relation']],identity,registry.store.read_blob(notice['evidence']))
    _require(len(payload['after'])==1,'NOTIFICATION','checkpoint native result')
    try:checkpoint=json.loads(registry.store.read_blob(payload['after'][0]))
    except (ValueError,TypeError) as exc:raise RecoveryError('NOTIFICATION','invalid native checkpoint bytes') from exc
    _require(_valid_notification_checkpoint(checkpoint),'NOTIFICATION','native checkpoint validator')
    actual={};entries=[];pending=0
    for blob in payload['targets']:
        name=blob['identity'];_require(re.fullmatch(r'[0-9a-f]{64}\.(?:pending|done)',name) is not None,'NOTIFICATION','native reference filename')
        key=name.split('.')[0];_require(key not in actual and key in expected,'NOTIFICATION','unknown/duplicate actual reference')
        raw=registry.store.read_blob(blob);kind,identity,retained=expected[key]
        try:ref=json.loads(raw)
        except (ValueError,TypeError) as exc:raise RecoveryError('NOTIFICATION','native reference decoding') from exc
        _require(raw==retained and set(ref)=={'kind','identity','received_at'} and ref['kind']==kind and ref['identity']==identity and raw==json.dumps(ref,sort_keys=True).encode(),'NOTIFICATION','actual committed reference bytes')
        from datetime import datetime
        at=datetime.fromisoformat(ref['received_at']);_require(at.tzinfo is not None and at.utcoffset() is not None,'NOTIFICATION','native reference time')
        actual[key]=name;pending+=name.endswith('.pending');entries.append(name.encode()+b':'+sha256(raw).hexdigest().encode())
    _require(set(actual)==set(expected),'NOTIFICATION','required reference not retained')
    digest=sha256(b'\n'.join(sorted(entries))).hexdigest()
    _require(checkpoint=={'state':'VALID_PENDING' if pending else 'EMPTY','pending_count':pending,'sha256':digest},'NOTIFICATION','native checkpoint whole-set digest')
    return checkpoint


def _certify_notifications(self,owner,owner_instance,resource):
    from kronos.application.intraday_notifications import IntradayNotifications
    from kronos.application.failed_fenced_owners import ProspectiveComposition
    _require(type(owner) is IntradayNotifications and owner._maintenance_admission is self.coordinator,'NOTIFICATION','actual native notification owner')
    composition=getattr(self.ledger,'native_composition',None)
    _require(type(composition) is ProspectiveComposition and composition.instance(owner)==owner_instance and composition.resource_identity(owner)==resource,'PROVENANCE','notification actual registered target')
    _require(self.state=='ACCEPTED','ACCOUNTING','checkpoint phase')
    self.ledger.reconcile(self.claim_ns,complete=True);self.budget.check(self.work_deadline_ns)
    context={'accepted_heads':self.ledger.obligation_heads()}
    with owner._lock:
        _require(owner._closed and not owner._scheduled and not owner._durability_unproven,'NOTIFICATION','notification work/durability unresolved')
        checkpoint=owner.checkpoint(certify_durable=True)
        targets=[]
        if owner.root.exists():
            for path in sorted(owner.root.iterdir()):
                _require(re.fullmatch(r'[0-9a-f]{64}\.(?:pending|done)',path.name) is not None,'NOTIFICATION','unknown notification member')
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
                try:
                    info=os.fstat(fd);_require(stat.S_ISREG(info.st_mode) and info.st_size<=1024,'NOTIFICATION','native reference type/size')
                    raw=os.read(fd,1025);after=os.fstat(fd)
                    _require((info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'NOTIFICATION','native reference changed')
                finally:os.close(fd)
                targets.append(self.ledger.retain_native(path.name,raw))
        _require(owner.checkpoint(certify_durable=True)==checkpoint,'NOTIFICATION','checkpoint changed during capture')
    checkpoint_blob=self.ledger.retain_native('native-checkpoint:'+self.slot[:32],json.dumps(checkpoint,sort_keys=True,separators=(',',':')).encode())
    peer_refs=sorted([_as_blob(x['evidence']) for x in self.ledger._fulfillments.values()],key=lambda v:v['identity'])
    obligations=sorted(k for k,o in self.ledger._operations.items() if o['payload']['relation'] in schema.REFERENCE_ACTIONS)
    base={'owner':'WO13','owner_instance':owner_instance,'process':self.ledger.process,'resource':resource,'scope':_as_blob(self.ledger.scope),'composition':_as_blob(self.ledger.inventory),'peer_fulfillment':peer_refs,'callback_results':[],'obligations':obligations,'targets':sorted(targets,key=lambda v:v['identity']),'before':[],'after':[checkpoint_blob],'result':'COMPLETE','owned_workers':'0','queued_items':'0','callbacks':'0','durable_writes':'0','notification_failure':False,'durability_unproven':False}
    rec={**base,'identity':'notice-reconciliation:'+self.slot[:32],'operation':'reconciliation:'+self.slot[:32],'action':'RECONCILE_NOTICES','purpose':'RECONCILIATION','reason':'RECONCILED'}
    _verify_notice_set(rec,self.registry,context)
    reconciliation=self.ledger.publish_owner_result(rec,context=context)
    cp={**base,'identity':'notice-checkpoint:'+self.slot[:32],'operation':'checkpoint:'+self.slot[:32],'action':'CERTIFY_CHECKPOINT','purpose':'CHECKPOINT','reason':'CHECKPOINT_COMPLETE'}
    proof=self.ledger.publish_owner_result(cp,context=context)
    result={'state':checkpoint['state'],'pending':str(checkpoint['pending_count']),'digest':checkpoint['sha256'],'evidence':proof}
    self._native_checkpoint=checkpoint;self._notification_owner=owner;self._certified_checkpoint=result
    self.budget.check(self.work_deadline_ns)
    return {'checkpoint':result,'reconciliation':reconciliation}

RecoveryTransaction.certify_notifications=_certify_notifications
