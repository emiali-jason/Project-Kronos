"""Closed R3 schemas. These constants implement the frozen 1.0.0 contract.

No schema, validator name, action, or authority is discovered from a request.
The source constants are reviewable; the application never reads design docs.
"""
from __future__ import annotations
import re

RECORD_SCHEMAS = {'ACK': '{slot:Hash, transaction:Id, claim:Ref, seal:Ref, owner_proof:Ref, certificate:Ref, prepared:Ref, '
        'predecessor:Process, control_challenge:Hash, publication_complete_ns:Ns, released_ns:Ns, ack_ns:Ns, '
        'publisher:Id, recovery_owners:Count, release:"CONFIRMED", deadline:"WITHIN", work_deadline_ns:Ns, '
        'stop_deadline_ns:Ns}',
 'CERTIFICATE': '{slot:Hash, transaction:Id, claim:Ref, accepted:Ref, seal:Ref, owner_proof:Ref, '
                'authorization:Evidence, artifacts:Evidence, scope:Evidence, limits:Limits, '
                'work_deadline_ns:Ns}',
 'CHILD_IDENTITY': '{slot:Hash, transaction:Id, intent:Ref, child:Process, child_nonce:Hash, parent:Process, '
                   'bootstrap:Evidence, observed_ns:Ns, execution_owner:Id}',
 'CHILD_INTENT': '{slot:Hash, transaction:Id, claim:Ref, observation:Ref, exit_proof:Ref, child_nonce:Hash, '
                 'successor_source:Evidence, successor_capability:Evidence, installed_package:Evidence, '
                 'checkpoint:Checkpoint, limits:Limits, execution_owner:Id, bootstrap_owner:Id}',
 'CHILD_STARTED': '{slot:Hash, transaction:Id, intent:Ref, child_identity:Ref, child:Process, '
                  'child_nonce:Hash, fork_enter_ns:Ns, fork_return_ns:Ns, ready_deadline_ns:Ns, '
                  'parent:Process, kernel_parent:Evidence}',
 'CLAIM': '{slot:Hash, guard:Ref, transaction:Id, binding:OriginalBinding, authorization:Evidence, '
          'scope_approvals:Evidence[], control_challenge:Hash, launcher:Process, '
          'launcher_capability:Evidence, endpoint:Endpoint, limits:Limits, successor_source:Evidence, '
          'successor_capability:Evidence, installed_package:Evidence, rollback_package:Evidence, '
          'compatibility:Evidence}',
 'CLAIM_ACCEPTED': '{slot:Hash, claim:Ref, transaction:Id, predecessor:Process, capability:Evidence, '
                   'control:Evidence, claim_ns:Ns, work_deadline_ns:Ns, executor:Ref, '
                   'active_obligations:Ref[]}',
 'CLEANUP': '{lineage:Lineage, step:Id, previous:?Ref, owner:Owner, owner_instance:Id, action:Action, '
            'resource:Id, operation:Id, state:"NOT_STARTED"|"STARTED"|"COMPLETE"|"NOT_APPLICABLE"|"FAILED", '
            'applicability:Evidence, obligations:Id[], owner_result:?Evidence, failure:?FailureCode}',
 'COMPOSITION_AUTHORITY': '{slot:Hash, transaction:Id, claim:Ref, intent:Ref, child_started:Ref, '
                          'parent:Process, controller_capability:Evidence, child:Process, child_nonce:Hash, '
                          'child_started_durable_ns:Ns, identity_verified_ns:Ns, gate_ns:Ns, '
                          'stop_deadline_ns:Ns, ready_deadline_ns:Ns, decision:"GRANT_ONCE"}',
 'CONSUMPTION': '{slot:Hash, transaction:Id, guard:Ref, claim:Ref, accepted:Ref, seal:Ref, owner_proof:Ref, '
                'certificate:Ref, prepared:Ref, ack:Ref, observation:Ref, exit_proof:Ref, intent:Ref, '
                'child_started:Ref, composition_authority:Ref, authority_bytes:HexBytes, '
                'authority_received_ns:Ns, authority_verified_ns:Ns, consumer:Process, child_nonce:Hash, '
                'checkpoint:Checkpoint, consumed_ns:Ns, ready_deadline_ns:Ns, source:Evidence, '
                'capability:Evidence, execution_owner:Id}',
 'CUSTODY': '{lineage:Lineage, checkpoint_hash:Hash, checkpoint_bytes:Count, controller:Process, '
            'controller_capability:Evidence, live_control:Evidence, process_binding:Evidence, '
            'verified_ns:Ns, execution_owner:Id}',
 'EXECUTOR': '{lineage:Lineage, original:Ref, executor:Id, previous:?Ref, state:"OWNED"|"TERMINATED", '
             'original_controller:?Evidence, no_child_start:?Evidence, no_consumption:?Evidence, '
             'completion:?Evidence}',
 'EXIT_PROOF': '{slot:Hash, transaction:Id, observation:Ref, predecessor:Process, exited_ns:Ns, '
               'listener_absent_ns:Ns, process_evidence:Evidence, listener_evidence:Evidence, limits:Limits, '
               'execution_owner:Id}',
 'FAILURE': '{slot:Hash, transaction:Id, phase:Kind, code:FailureCode, earlier:?Ref, observed_ns:Ns, '
            'evidence:Evidence, outstanding_owners:Count}',
 'GUARD': '{slot:Hash, service:Id, binding:OriginalBinding, transaction:Id, authorization:Evidence, '
          'limits:Limits, scope:Evidence, artifacts:Evidence}',
 'OBLIGATION': '{predecessor:Process, obligation:Id, previous:?Ref, '
               'state:"ACCEPTED"|"STARTED"|"COMPLETE"|"FAILED", owner:Owner, owner_instance:Id, '
               'operation:Id, relation:Relation, effect:Effect, listener:?Evidence, ticket:Id, '
               'admission:Evidence, owner_scope:Evidence, parent:?Ref, required_children:Id[], '
               'notices:Notice[], owner_result:?Evidence, failure:?FailureCode}',
 'OBSERVATION': '{slot:Hash, transaction:Id, claim:Ref, ack:Ref, ack_bytes:HexBytes, launcher:Process, '
                'received_ns:Ns, verified_ns:Ns, limits:Limits, execution_owner:Id}',
 'ORIGINAL': '{lineage:Lineage, custody:Ref, source:Evidence, capability:Evidence, control:Evidence, '
             'authorization:Evidence, reservation:Evidence, attempt:Id, '
             'original_kind:"ORDINARY"|"FAILED_ACTIVE", original_limits:Limits, '
             'original_drain_deadline_ns:Ns, owner_scope:Evidence, scope_approvals:Evidence[], '
             'accepted_roots:Ref[], accepted_heads:Ref[], ticket_roster:Evidence}',
 'OWNER_PROOF': '{slot:Hash, claim:Ref, seal:Ref, transaction:Id, binding:OriginalBinding, '
                'obligation_heads:Ref[], cleanup_heads:Ref[], owner_results:Evidence[], '
                'reconciliation:Evidence, checkpoint:Checkpoint, product_owners:Count, '
                'accepted_owners:Count, commit_owners:Count, publisher:Id}',
 'PREPARED_COMMIT': '{slot:Hash, transaction:Id, seal:Ref, owner_proof:Ref, certificate:Ref, publisher:Id, '
                    'product_owners:Count, accepted_owners:Count, commit_owners:Count}',
 'READY_RECEIPT': '{slot:Hash, transaction:Id, guard:Ref, intent:Ref, child_started:Ref, consumption:Ref, '
                  'startup:Ref, runtime:Process, ready_ns:Ns, restoration:Evidence, source:Evidence, '
                  'capability:Evidence, provider_absence:Evidence, transport_absence:Evidence, '
                  'execution_owner:Id}',
 'SEAL': '{slot:Hash, claim:Ref, accepted:Ref, transaction:Id, seal:Id, sealed_ns:Ns, '
         'obligation_heads:Ref[], cleanup_heads:Ref[], owner_scope:Evidence, checkpoint:Checkpoint, '
         'product_owners:Count, accepted_owners:Count, commit_owners:Count, publisher:Id, '
         'write_free_tail:Evidence, retained_control:Evidence}',
 'STARTUP_CONTEXT': '{slot:Hash, transaction:Id, original:Ref, terminal:Ref, consumption:Ref, '
                    'child_started:Ref, runtime:Process, checkpoint:Checkpoint, restoration_scope:Evidence, '
                    'ready_deadline_ns:Ns}',
 'TERMINAL': '{lineage:Lineage, original:Ref, first_failure:FailureCode, failure_evidence:Evidence, '
             'original_deadline_ns:Ns, failed_ns:Ns, obligations:Ref[], cleanup:Ref[], executor:Ref}'}

RECORD_ROLES = {'ACK': ('PREDECESSOR',),
 'CERTIFICATE': ('PREDECESSOR',),
 'CHILD_IDENTITY': ('SUCCESSOR',),
 'CHILD_INTENT': ('LAUNCHER',),
 'CHILD_STARTED': ('LAUNCHER',),
 'CLAIM': ('LAUNCHER',),
 'CLAIM_ACCEPTED': ('PREDECESSOR',),
 'CLEANUP': ('PREDECESSOR',),
 'COMPOSITION_AUTHORITY': ('LAUNCHER',),
 'CONSUMPTION': ('SUCCESSOR',),
 'CUSTODY': ('LAUNCHER',),
 'EXECUTOR': ('PREDECESSOR',),
 'EXIT_PROOF': ('LAUNCHER',),
 'FAILURE': ('PREDECESSOR', 'LAUNCHER', 'SUCCESSOR'),
 'GUARD': ('LAUNCHER',),
 'OBLIGATION': ('PREDECESSOR',),
 'OBSERVATION': ('LAUNCHER',),
 'ORIGINAL': ('PREDECESSOR',),
 'OWNER_PROOF': ('PREDECESSOR',),
 'PREPARED_COMMIT': ('PREDECESSOR',),
 'READY_RECEIPT': ('LAUNCHER',),
 'SEAL': ('PREDECESSOR',),
 'STARTUP_CONTEXT': ('SUCCESSOR',),
 'TERMINAL': ('PREDECESSOR',)}

PROOF_SCHEMAS = {'ABSENCE': '{identity:Id,process:Process,kind:"PROVIDER"|"MARKET_TRANSPORT",native:Blob,active:Count,retained_leases:Count,callbacks:Count,unresolved_cleanup:Count,cleanup:"COMPLETE",observed_ns:Ns}',
 'BOOTSTRAP_IDENTITY': '{identity:Id,process:Process,parent:Process,intent:Ref,child_nonce:Hash,startup:Blob,target:Blob,bootstrap_plan:Blob,loaded_bootstrap:BootstrapModule[],qualified_ns:Ns}',
 'CAPABILITY': '{identity:Id,process:Process,source:Blob,capability:"FAILED_FENCED_RECOVERY_V1",implementation:Blob,owner_scope:Blob,operation_manifest:Blob,tail_plan:Blob,qualified_artifact:Id}',
 'CLEANUP_APPLICABILITY': '{identity:Id,owner:Owner,owner_instance:Id,process:Process,action:Action,resource:Id,operation:Id,scope:Blob,composition:Blob,registered_ns:Ns,state:"APPLICABLE"|"NOT_APPLICABLE",predicate:CleanupPredicate}',
 'CLOCK_QUALIFICATION': '{identity:Id,approval:Id,platform:Blob,boot_id:Id,c_clock:"clock_gettime:CLOCK_MONOTONIC",python_clock:"time.clock_gettime_ns:CLOCK_MONOTONIC",unit:"NANOSECONDS",report:Blob,equivalent:Bool,nondecreasing:Bool,sleep_behavior_equal:Bool}',
 'COMPATIBILITY': '{identity:Id,predecessor:Blob,successor:Blob,configuration:Blob,epoch:Id,acceptance:Id,window:Blob,mode:"EXACT"|"DIRECT_APPROVED",relation:?Blob,verified_ns:Ns}',
 'COMPOSITION_INVENTORY': '{identity:Id,process:Process,source:Blob,scope:Blob,previous:?Blob,phase:"LIVE"|"ORIGINAL_FENCE",registered_ns:Ns,observed_ns:Ns,slots:OwnerSlot[],instances:InstanceRow[],resources:ResourceRow[],listeners:ListenerRow[],cleanup:CleanupTarget[]}',
 'CONTROLLER_ADMISSION': '{identity:Id,controller:Process,lineage:Lineage,attempt:Id,sequence:Count,previous:?Blob,operation:Id,action:ControllerAction,executor:Id,inputs:Blob[],accepted_ns:Ns}',
 'CONTROLLER_CAPABILITY': '{identity:Id,controller:Process,predecessor:Process,phase:"ORIGINAL"|"RECOVERY",source_inventory:Blob,executable:Blob,package:Blob,qualified_artifact:Id,execution_lock:Id,operations:ControllerOperation[],proof_publication:Blob,ledger_schema:"KRONOS-FAILED-FENCED-CONTROLLER-LEDGER/1.0.0",verified_ns:Ns}',
 'CONTROLLER_CLOSURE': '{identity:Id,controller:Process,lineage:Lineage,attempt:Id,capability:Blob,execution_lock:Id,admissions:Blob[],dispatch_heads:Blob[],rights:ControllerRight[],closed_ns:Ns,outstanding:Count,publisher:Id,publisher_owners:Count}',
 'CONTROLLER_DISPATCH': '{identity:Id,controller:Process,lineage:Lineage,attempt:Id,admission:Blob,previous:?Blob,state:"NOT_DISPATCHED"|"DISPATCHED"|"COMPLETED"|"FAILED_CLOSED"|"UNRESOLVED",helper:?Process,started_ns:?Ns,completed_ns:?Ns,outcome:"NONE"|"RETURNED"|"JOINED_SUCCESS"|"JOINED_FAILURE",outputs:Blob[],outstanding:Count}',
 'CONTROL_BINDING': '{identity:Id,process:Process,live_control:Blob,retained_control:Blob,schema:"KRONOS_BROWSER_BACKEND_CONTROL_V1",boot_id:Id,verified_ns:Ns}',
 'ENDPOINT_CONFIGURATION': '{identity:Id,service:Id,process:Process,host:"127.0.0.1",port:Count,configuration:Blob,source:Blob,listener:Blob}',
 'EXECUTOR_TERMINATION': '{identity:Id,process:Process,lineage:Lineage,executor:Id,original_controller:Process,original_attempt:Id,accepted_operations:Id[],completed_operations:Id[],owned_workers:Count,pending_callbacks:Count,pending_publications:Count,joined_ns:Ns,state:"TERMINATED"}',
 'FAILURE_FACT': '{identity:Id,process:Process,phase:Id,code:FailureCode,original_failure:?Blob,observed_ns:Ns,owner_facts:Blob[],outstanding_owners:Count}',
 'FENCE_ROSTER': '{identity:Id,process:Process,generation:Id,original_claim:Id,fenced_ns:Ns,admissions:Blob[],tickets:TicketState[]}',
 'GUARD_APPLICABILITY': '{identity:Id,approval:Id,service:Id,launcher:Blob,backend:Blob,source:Blob,classification:"LEGACY_UNENROLLED"|"MANDATORY",sentinel:?Blob,provisioning:?Blob}',
 'ISSUED_ADMISSION': '{identity:Id,process:Process,operation:Id,ticket:Id,parent:?Id,relation:Relation,accepted_ns:Ns,state:"OPEN_ACCEPTED",scope:Blob,input:Blob,effect:Blob,listener:?Blob}',
 'ORIGINAL_AUTHORITY': '{identity:Id,approval:Id,preparation:Blob,service:Id,process:Process,generation:Id,kind:"ORDINARY"|"FAILED_ACTIVE",source:Blob,control:Blob,package:Blob,reservation:Blob,valid_from_ns:Ns,valid_until_ns:Ns,clock:Clock}',
 'ORIGINAL_CONTROLLER': '{identity:Id,controller:Process,lineage:Lineage,original:Blob,reservation:Blob,admission_ledger:Blob[],dispatch_ledger:Blob[],executor:Blob,child_right:"CLOSED_UNUSED",consumption_right:"CLOSED_UNUSED",state:"TERMINAL_BEFORE_CHILD",sealed_ns:Ns,control_capability:Blob,execution_closure:Blob}',
 'OWNER_RESULT': '{identity:Id,owner:Owner,owner_instance:Id,process:Process,action:Action,resource:Id,operation:Id,scope:Blob,composition:Blob,peer_fulfillment:Blob[],callback_results:CallbackCompletion[],purpose:"EFFECT"|"REFERENCE"|"CLEANUP"|"ABSENCE"|"RECONCILIATION"|"CHECKPOINT",obligations:Id[],targets:Blob[],before:Blob[],after:Blob[],result:"COMPLETE"|"NOT_APPLICABLE"|"FAILED",owned_workers:Count,queued_items:Count,callbacks:Count,durable_writes:Count,notification_failure:Bool,durability_unproven:Bool,reason:OwnerReason}',
 'PACKAGE': '{identity:Id,manifest:Blob,executable:Blob,signature:Blob,artifact_approval:Id,role:"INSTALLED"|"ROLLBACK",verified_ns:Ns}',
 'PEER_FULFILLMENT': '{identity:Id,process:Process,registration:Blob,outcome:"COMPLETED"|"NOT_REQUIRED"|"FAILED",invoked_ns:?Ns,returned_ns:?Ns,recorded_ns:Ns,execution_owner:Id,release_state:"HELD",outputs:PeerOutput[],failure:Bool}',
 'PEER_REGISTRATION': '{identity:Id,process:Process,operation:Id,ticket:Id,producer:Owner,producer_instance:Id,source_kind:"SELECTION"|"ACTION"|"TRACK"|"COMPARISON"|"UNAVAILABLE",source_identity:SourceIdentity,source_input:Blob,previous_source:?Blob,peer:"JOURNAL"|"BOOKS",peer_slot:Id,peer_instance:?Id,listener:?Id,composition:Blob,predicate:PeerPredicate,registered_ns:Ns}',
 'PLATFORM_OBSERVATION': '{identity:Id,observer:Process,subject:Process,kind:"PROCESS_BIRTH"|"PROCESS_EXIT"|"LISTENER_ABSENT"|"CANONICAL_PARENT",adapter:"DARWIN_KERNEL_V1",boot_id:Id,observed_ns:Ns,raw:Blob,result:"MATCH"|"EXITED"|"ABSENT"}',
 'RECOVERY_AUTHORITY': '{identity:Id,approval:Id,preparation:Blob,service:Id,lineage:Lineage,slot:Hash,transaction:Id,original_reservation:Blob,terminal:Blob,journal_heads:Blob[],predecessor_source:Blob,predecessor_capability:Blob,successor_source:Blob,successor_capability:Blob,installed_package:Blob,rollback_package:Blob,compatibility:Blob,diagnosis:Blob,interface:Blob,scope:Blob,valid_from_ns:Ns,valid_until_ns:Ns,clock:Clock}',
 'RESTORATION': '{identity:Id,process:Process,startup_context:Ref,owners:RestorationRow[],native_runtime:Blob,source:Blob,window:Blob,provider:Blob,transport:Blob,completed_ns:Ns,result:"READY"|"BLOCKED"}',
 'RESTORATION_PLAN': '{identity:Id,approval:Id,service:Id,revision:Revision,source_inventory:Blob,configuration:Blob,owners:PlannedOwner[]}',
 'SOURCE': '{identity:Id,process:Process,revision:Revision,repository:Id,startup:Blob,runtime_manifest:Blob,source_inventory:Blob,canonical_parent:Blob,publication:Blob,package:Blob,verified_ns:Ns}',
 'TAIL': '{identity:Id,process:Process,source:Blob,approval:Id,entry:Id,allowed:["CONTROL_RESPONSE","CLOSE_DESCRIPTORS","PROCESS_EXIT"],forbidden_hooks:Id[],required_cleanup:Id[],completed_cleanup:Id[],product_owners:Count,recovery_executor_owners:Count,executor:Id}',
 'TARGET_ARTIFACT': '{identity:Id,approval:Id,service:Id,revision:Revision,source_inventory:Blob,capability_manifest:Blob,configuration:Blob,package:Blob,interface:Blob,scope:Blob,restoration_plan:Blob,bootstrap_plan:Blob}'}

TYPE_SCHEMAS = {'ApprovalCatalogue': '{schema:"KRONOS-RECOVERY-APPROVAL-CATALOGUE/1.0.0",identity:Id,service:Id,package_manifest:Blob,interface:Blob,scope:Blob,appendix:Blob,rows:ApprovalRow[]}',
 'ApprovalRow': '{identity:Id,authority:"SPONSOR"|"CA"|"PCP"|"EA-SWING"|"EA-INTRADAY",purpose:"ORIGINAL_OPERATION"|"RECOVERY_OPERATION"|"ARCHITECTURE"|"OWNER_SCOPE"|"ARTIFACT"|"CLOCK"|"TAIL"|"GUARD",artifact:Blob,attribution:Blob,bindings:ApprovalBindings}',
 'Blob': '{identity:Id,hash:Hash,bytes:U64}',
 'BootstrapModule': '{name:Id,digest:Hash}',
 'BootstrapPlan': '{schema:"KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0",identity:Id,source_inventory:Blob,modules:BootstrapModule[],qualification:Blob}',
 'CallbackCompletion': '{listener:Id,operation:Id,state:"RETURNED"|"NOT_REQUIRED",completed_ns:Ns}',
 'Checkpoint': '{state:"EMPTY"|"VALID_PENDING",pending:Count,digest:Hash,evidence:Evidence}',
 'CleanupPredicate': '{kind:"REGISTERED_TARGET"|"OWNER_SLOT_NOT_INSTALLED",inventory:Blob,slot:Id,target:?Id}',
 'CleanupTarget': '{step:Id,owner:Owner,owner_instance:Id,action:Action,resource:Id,nested:Id[]}',
 'Clock': '{type:"CLOCK_MONOTONIC",boot_id:Id,qualification:Evidence}',
 'ControlPreparation': '{schema:"KRONOS-FAILED-FENCED-CONTROL-PREPARATION/1.0.0",identity:Id,mode:"ORIGINAL"|"RECOVERY",service:Id,installation:Id,controller:Process,lineage:Lineage,attempt:Id,control_hash:Hash,catalogue:Blob,original_preparation:?Blob,launcher_source:Blob,launcher_package:Blob,clock:Clock,prepared_ns:Ns}',
 'ControllerOperation': '{action:ControllerAction,implementation:Blob}',
 'ControllerRight': '{kind:"CHILD_INTENT"|"CHILD_FORK"|"CONSUME"|"RELEASE_COMPOSITION",state:"CLOSED_UNUSED"}',
 'Effect': '{kind:Relation,identity:SourceIdentity,source:Evidence,input:Evidence,target:SourceIdentity,expected:Hash,transition:?Evidence}',
 'Endpoint': '{host:"127.0.0.1",port:Count,configuration:Evidence}',
 'Evidence': '{authority:Id,contract:Id,identity:Id,hash:Hash,bytes:U64}',
 'GuardProvisioning': '{schema:"KRONOS-FAILED-FENCED-GUARD-PROVISIONING/1.0.0",identity:Id,service:Id,installation:Id,launcher:Blob,backend:Blob,source:Blob,sentinel:Blob,lock_scope:Id,before_first_capable_start:Bool,fsync_verified:Bool,readback_verified:Bool}',
 'GuardScope': '{schema:"KRONOS_FAILED_FENCED_GUARD_SCOPE_V1",version:"1.0.0",service:Id,installation:Id,policy:"MANDATORY"}',
 'InstanceRow': '{identity:Id,owner:Owner,slot:Id,implementation:Blob,constructed_ns:Ns}',
 'KernelBirth': '{seconds:U64,microseconds:Count}',
 'Limits': '{clock:Clock,origin_ns:Ns,stop_deadline_ns:Ns}',
 'Lineage': '{predecessor:Process,generation:Id}',
 'ListenerRow': '{identity:Id,producer_instance:Id,consumer_instance:Id,implementation:Blob,registered_ns:Ns,retired_ns:?Ns}',
 'Notice': '{identity:SourceIdentity,state:"PENDING"|"DONE",evidence:Evidence}',
 'OriginalBinding': '{lineage:Lineage,original:Ref,terminal:Ref,obligations:Ref[],cleanup:Ref[],executor:Ref}',
 'OwnerSlot': '{owner:Owner,slot:Id,presence:"INSTALLED"|"NOT_INSTALLED",instances:Id[]}',
 'PeerOutput': '{adapter:"JOURNAL_REVISION_V1"|"BOOKS_FACTUAL_ROW_V1",identity:SourceIdentity,bytes:Blob,pointer:?Blob}',
 'PlannedOwner': '{owner:Owner,contract:Id,validator:Blob,applicability:Blob}',
 'PreparationApproval': '{schema:"KRONOS-FAILED-FENCED-PREPARATION-APPROVAL/1.0.0",pin:Blob,preparation:Blob,attributions:PreparationAttribution[]}',
 'PreparationAttribution': '{authority:"CA"|"PCP"|"SPONSOR",decision:Blob}',
 'PreparationPin': '{schema:"KRONOS-FAILED-FENCED-PREPARATION-PIN/1.0.0",mode:"ORIGINAL"|"RECOVERY",service:Id,installation:Id,lineage:Lineage,attempt:Id,preparation:Blob,catalogue:Blob}',
 'Process': '{pid:U64,kernel_birth:KernelBirth,runtime:Id}',
 'Ref': '{kind:Kind,hash:Hash}',
 'ResourceRow': '{identity:Id,owner_instance:Id,kind:"OWNER"|"BINDING"|"REGISTRATION"|"TIMER"|"WORKER"|"LEASE"|"CALLBACK"|"TRANSPORT"|"CONTROL_FILE"|"QUEUE",parent:?Id,aliases:Id[],registered_ns:Ns}',
 'RestorationRow': '{owner:Owner,contract:Id,native:Blob}',
 'SourceIdentity': '{encoding:"UTF-8",bytes:HexBytes}',
 'TicketState': '{ticket:Id,operation:Id,parent:?Id,state:"OWNED"|"RELEASED",admission:Blob}'}

APPROVAL_BINDINGS = {'ARCHITECTURE': '{kind:"ARCHITECTURE",interface:Blob,scope:Blob,appendix:Blob,contract:Blob,adr:Blob}',
 'ARTIFACT': '{kind:"ARTIFACT",revision:Revision,source_inventory:Blob,capability_manifest:Blob,executable:Blob,package:Blob,configuration:Blob,bootstrap_plan:?Blob,qualification:Blob}',
 'CLOCK': '{kind:"CLOCK",root:Blob,report:Blob,boot_id:Id}',
 'GUARD': '{kind:"GUARD",service:Id,installation:Id,classification:"MANDATORY"|"LEGACY_UNENROLLED",launcher:Blob,backend:Blob,source_inventory:Blob,sentinel:?Blob,provisioning:?Blob}',
 'ORIGINAL_OPERATION': '{kind:"ORIGINAL_OPERATION",service:Id,controller:Process,predecessor:Process,generation:Id,attempt:Id,operation_kind:"ORDINARY"|"FAILED_ACTIVE",control:Hash,source:Blob,package:Blob,permission:Blob,clock:Clock,valid_from_ns:Ns,valid_until_ns:Ns}',
 'OWNER_SCOPE': '{kind:"OWNER_SCOPE",interface:Blob,scope:Blob,owner:"CA"|"PCP"|"EA-SWING"|"EA-INTRADAY",implementation:Blob,qualification:Blob}',
 'RECOVERY_OPERATION': '{kind:"RECOVERY_OPERATION",service:Id,controller:Process,lineage:Lineage,slot:Hash,transaction:Id,original_preparation:Blob,original_reservation:Blob,terminal:Blob,journal_heads:Blob[],predecessor_source:Blob,predecessor_capability:Blob,target:Blob,installed_package:Blob,rollback_package:Blob,compatibility:Blob,diagnosis:Blob,interface:Blob,scope:Blob,clock:Clock,valid_from_ns:Ns,valid_until_ns:Ns}',
 'TAIL': '{kind:"TAIL",source_inventory:Blob,entry:Id,callgraph:Blob,qualification:Blob,cleanup_actions:Action[],allowed:["CONTROL_RESPONSE","CLOSE_DESCRIPTORS","PROCESS_EXIT"]}'}

FAILURE_CODES = frozenset('AUTHORITY IDENTITY PROVENANCE ACCOUNTING CLEANUP NOTIFICATION DURABILITY TIMEOUT PROTOCOL CHILD RESTORATION INTERRUPTED'.split())
RELATIONS = frozenset('WO11_PUBLICATION WO17_PUBLICATION WO09_READINESS_EFFECT WO09_CURRENTNESS_EFFECT WO10_COMPARISON_EFFECT WO10_UNAVAILABLE_EFFECT WO09_READINESS_REFERENCE WO09_CURRENTNESS_REFERENCE WO10_COMPARISON_REFERENCE WO10_UNAVAILABLE_REFERENCE WO11_TRACK_REFERENCE'.split())
CLEANUP_ACTIONS = {
    'APPLICATION': ('CLOSE_APPLICATION',), 'LOCAL_ANALYSIS': ('CLOSE_LOCAL',),
    'APPLICATION_LOCAL_BINDING': ('CLEAR_LOCAL_BINDING',), 'NATIVE_LOCAL_BINDING': ('CLEAR_LOCAL_BINDING',),
    'RESEARCH': ('QUIESCE_DAILY', 'CLOSE_RESEARCH'), 'RESEARCH_CAPTURE_BINDING': ('CLEAR_RESEARCH_CAPTURE',),
    'WO11': ('STOP_WO11', 'DETACH_REGISTRATION'), 'WO17': ('STOP_WO17', 'DETACH_REGISTRATION'),
    'EXPERIMENTAL': ('STOP_EXPERIMENTAL', 'DETACH_REGISTRATION'), 'PROGRESSION': ('CLOSE_PROGRESSION', 'DETACH_REGISTRATION'),
    'NATIVE': ('CLOSE_NATIVE', 'DETACH_REGISTRATION'), 'TRADE_WINDOW': ('CLOSE_TRADE_WINDOW', 'DETACH_REGISTRATION'),
    'PAPER_OBSERVATION': ('DETACH_REGISTRATION',), 'MONITORING_HUB': ('CLOSE_HUB', 'DETACH_REGISTRATION'),
    'STEP32': ('CLOSE_STEP32',), 'MCX': ('CLOSE_MCX',), 'PROVIDER': ('END_SESSION',),
    'PROVIDER_FACADE': ('RELEASE_PRODUCT_LEASE',), 'PROVIDER_LEASE': ('REVOKE_LEASE',),
    'HOUSEKEEPING': ('STOP_HOUSEKEEPING',), 'BULK': ('CLOSE_BULK',), 'WO13': ('CLOSE_NOTIFICATIONS',),
    'UX10': ('CLOSE_UX10', 'CANCEL_TIMER'), 'REMINDERS': ('CLOSE_REMINDERS', 'CANCEL_TIMER'),
    'WO08': ('CLOSE_COLLECTOR',), 'CONTROL': ('REMOVE_CONTROL',),
}
EFFECT_ACTIONS = {'WO09': ('WO09_READINESS_EFFECT', 'WO09_CURRENTNESS_EFFECT'),
                  'WO10': ('WO10_COMPARISON_EFFECT', 'WO10_UNAVAILABLE_EFFECT'),
                  'WO11': ('WO11_PUBLICATION',), 'WO17': ('WO17_PUBLICATION',)}
REFERENCE_ACTIONS = tuple(sorted(r for r in RELATIONS if r.endswith('_REFERENCE')))
OWNERS = frozenset(CLEANUP_ACTIONS) | frozenset(EFFECT_ACTIONS) | {'BROWSER', 'SWING_ANALYSIS', 'JOURNAL', 'BOOKS'}
ACTIONS = frozenset(x for v in CLEANUP_ACTIONS.values() for x in v) | RELATIONS | {'PROVE_QUIESCENT', 'PROVE_NOT_INSTALLED', 'RECONCILE_NOTICES', 'CERTIFY_CHECKPOINT'}
CONTROLLER_ACTIONS = frozenset('AUTHORIZE VERIFY_SOURCE VERIFY_PACKAGE VERIFY_STATUS VERIFY_CONTINUITY RESERVE_ORIGINAL DISPATCH_SHUTDOWN WAIT_DRAIN VERIFY_HANDOFF VERIFY_EXIT CHILD_INTENT CHILD_FORK CONSUME RELEASE_COMPOSITION'.split())
OWNER_REASONS = frozenset('EFFECT_COMPLETE REFERENCE_COMPLETE CLEANUP_COMPLETE QUIESCENT NOT_INSTALLED NOT_REQUIRED RECONCILED CHECKPOINT_COMPLETE UNPROVEN'.split())
PEER_PREDICATES = frozenset('REQUIRED OWNER_SLOT_NOT_INSTALLED JOURNAL_TRACK_UNCHANGED JOURNAL_UNSUPPORTED_KIND BOOKS_NO_SOURCE_EDGE SELECTION_NO_OUTPUT ACTION_NO_OUTPUT'.split())
SCALAR_ENUMS = {'Kind': frozenset(RECORD_SCHEMAS), 'Owner': OWNERS, 'Action': ACTIONS,
                'Relation': RELATIONS, 'FailureCode': FAILURE_CODES, 'OwnerReason': OWNER_REASONS,
                'ControllerAction': CONTROLLER_ACTIONS, 'PeerPredicate': PEER_PREDICATES}
_TOKEN = re.compile(r'\s*("[^"\\]*"|[A-Za-z_][A-Za-z_0-9]*|[][{}:,?|])')

class SchemaError(ValueError):
    pass

class _Parser:
    def __init__(self, text):
        self.tokens = []; self.position = 0; pos = 0
        while pos < len(text):
            match = _TOKEN.match(text, pos)
            if match is None: raise SchemaError('schema syntax')
            self.tokens.append(match[1]); pos = match.end()
    def take(self, value=None):
        if self.position >= len(self.tokens): raise SchemaError('schema ended')
        result = self.tokens[self.position]; self.position += 1
        if value is not None and result != value: raise SchemaError('schema token')
        return result
    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None
    def type(self):
        if self.peek() == '?':
            self.take(); node = ('nullable', self.type())
        elif self.peek() == '{':
            self.take(); fields = {}
            while self.peek() != '}':
                key = self.take(); self.take(':'); fields[key] = self.type()
                if self.peek() != '}': self.take(',')
            self.take('}'); node = ('object', fields)
        elif self.peek() == '[':
            self.take(); values = []
            while self.peek() != ']':
                values.append(self.type())
                if self.peek() != ']': self.take(',')
            self.take(']'); node = ('tuple', values)
        else:
            name = self.take()
            node = ('literal', name[1:-1]) if name.startswith('"') else ('name', name)
        if self.peek() == '[':
            self.take('['); self.take(']'); node = ('array', node)
        if self.peek() == '|':
            self.take(); node = ('union', (node, self.type()))
        return node

_CACHE = {}
def _parse(text):
    if text not in _CACHE:
        parser = _Parser(text); node = parser.type()
        if parser.peek() is not None: raise SchemaError('trailing schema')
        _CACHE[text] = node
    return _CACHE[text]

def _integer(value, maximum):
    if type(value) is not str or re.fullmatch(r'0|[1-9][0-9]{0,19}', value) is None or int(value) > maximum:
        raise SchemaError('noncanonical unsigned integer')

def _validate(node, value, depth):
    if depth > 64: raise SchemaError('schema nesting')
    kind, rule = node
    if kind == 'object':
        if type(value) is not dict or set(value) != set(rule): raise SchemaError('closed object fields')
        for k, v in rule.items(): _validate(v, value[k], depth+1)
    elif kind == 'array':
        if type(value) is not list or len(value) > 4096: raise SchemaError('array bound')
        for item in value: _validate(rule, item, depth+1)
    elif kind == 'tuple':
        if type(value) is not list or len(value) != len(rule): raise SchemaError('fixed array')
        for a,b in zip(rule,value): _validate(a,b,depth+1)
    elif kind == 'nullable':
        if value is not None: _validate(rule,value,depth+1)
    elif kind == 'literal':
        if value != rule or type(value) is not str: raise SchemaError('literal')
    elif kind == 'union':
        for alternative in rule:
            try: _validate(alternative,value,depth+1); return
            except SchemaError: pass
        raise SchemaError('union')
    elif rule in SCALAR_ENUMS:
        if type(value) is not str or value not in SCALAR_ENUMS[rule]: raise SchemaError('closed enum')
    elif rule == 'ApprovalBindings':
        if type(value) is not dict or value.get('kind') not in APPROVAL_BINDINGS: raise SchemaError('approval purpose')
        _validate(_parse(APPROVAL_BINDINGS[value['kind']]),value,depth+1)
    elif rule in TYPE_SCHEMAS:
        _validate(_parse(TYPE_SCHEMAS[rule]),value,depth+1)
        if rule == 'Process' and int(value['pid']) == 0: raise SchemaError('zero PID')
        if rule == 'KernelBirth' and int(value['microseconds']) > 999999: raise SchemaError('kernel birth')
        if rule == 'Endpoint' and not 0 < int(value['port']) <= 65535: raise SchemaError('port')
        if rule == 'SourceIdentity':
            try: bytes.fromhex(value['bytes']).decode('utf-8',errors='strict')
            except (UnicodeError,ValueError) as exc: raise SchemaError('source identity') from exc
    elif rule in ('U64','Ns','Count'):
        _integer(value,4294967295 if rule=='Count' else 18446744073709551615)
    elif rule == 'Bool':
        if type(value) is not bool: raise SchemaError('boolean')
    elif rule in ('Id','Hash','Revision','HexBytes'):
        pattern={'Id':r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}','Hash':r'[0-9a-f]{64}',
                 'Revision':r'[0-9a-f]{40}','HexBytes':r'(?:[0-9a-f]{2}){1,131072}'}[rule]
        if type(value) is not str or re.fullmatch(pattern,value) is None: raise SchemaError(rule)
    else: raise SchemaError('unknown schema name '+rule)

def validate_type(name, value):
    _validate(('name', name),value,0)

def validate_payload(kind,value,*,proof=False):
    schemas = PROOF_SCHEMAS if proof else RECORD_SCHEMAS
    if kind not in schemas: raise SchemaError('unknown record kind')
    _validate(_parse(schemas[kind]),value,0)

def owner_tuple(owner,purpose,action):
    if owner not in OWNERS: return False
    return (purpose == 'ABSENCE' and action in {'PROVE_QUIESCENT','PROVE_NOT_INSTALLED'}
            or purpose == 'EFFECT' and action in EFFECT_ACTIONS.get(owner,())
            or purpose == 'REFERENCE' and owner == 'WO13' and action in REFERENCE_ACTIONS
            or purpose == 'CLEANUP' and action in CLEANUP_ACTIONS.get(owner,())
            or purpose == 'RECONCILIATION' and owner == 'WO13' and action == 'RECONCILE_NOTICES'
            or purpose == 'CHECKPOINT' and owner == 'WO13' and action == 'CERTIFY_CHECKPOINT')
