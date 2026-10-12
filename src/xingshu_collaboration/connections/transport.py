"""应用无关的不透明投递核心；沿用原快照、锁和去重语义。"""
import fcntl
import hashlib
import json
import os
import re
import select
import sys
from datetime import datetime, timezone
from pathlib import Path
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import SnapshotStore, digest

MAX_BYTES = 131072
ACK_KEYS = {'type','project_instance_id','message_id','task_id','output_to','target_actor','endpoint_uri','message','message_sha256','observed_delivery','evidence_ref'}

def now():
    return datetime.now(timezone.utc).isoformat()

def connection_identity(binding, endpoint_uris, project, relay_id):
    descriptors=[]
    for endpoint_id,actor_id in binding.endpoint_registration:
        if hasattr(binding,'endpoint_for'):
            endpoint=binding.endpoint_for(endpoint_id)
            if endpoint.resource_uri != endpoint_uris[endpoint_id]:
                raise CandidateError('ENDPOINT_URI_BINDING_CONFLICT')
            generation=endpoint.generation
        else:
            generation=1
        descriptors.append({'endpoint_id':endpoint_id,'actor_id':actor_id,
                            'resource_uri':endpoint_uris[endpoint_id],'generation':generation})
    return {'protocol':'xingshu-connection/1','project_instance_id':project,'relay_id':relay_id,
            'endpoints':sorted(descriptors,key=lambda e:e['endpoint_id'])}

class OpaqueDelivery:
    """一个已登记连接内的原文投递；应用宿主负责提交和观察。"""
    def __init__(self, message_id, source, output_to, binding, endpoint_uris, state_root,
                 *, project, relay_id, input_stream=None, output_stream=None):
        binding.validate()
        endpoints = dict(binding.endpoint_registration)
        if (not identity(message_id) or type(project) is not str
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', project)
                or not identity(relay_id)):
            raise CandidateError('CONNECTION_IDENTITY_REQUIRED')
        if (source not in endpoints or output_to not in endpoints or source == output_to
                or set(endpoint_uris) != set(endpoints)
                or any(type(uri) is not str or not uri for uri in endpoint_uris.values())):
            raise CandidateError('FIXED_ROUTE_CONFLICT')
        self.message_id = message_id
        self.source, self.output_to = source, output_to
        self.binding = binding
        self.endpoint_uris = dict(endpoint_uris)
        self.project, self.relay_id = project, relay_id
        self.connection_identity=connection_identity(binding,self.endpoint_uris,project,relay_id)
        self._used, self.records = False, []
        self.state_root = Path(state_root)
        self.store = SnapshotStore(self.state_root / 'snapshots', self.state_root.parent)
        self._input = sys.stdin if input_stream is None else input_stream
        self._output = sys.stdout if output_stream is None else output_stream

    def deliver(self,endpoint,actor,payload):
        if self._used:raise CandidateError('DELIVERY_ALREADY_CONSUMED')
        self._used=True
        if endpoint!=self.output_to or actor!=self.binding.actor_for(endpoint):raise CandidateError('DESTINATION_BINDING_CONFLICT')
        if type(payload) is not bytes or len(payload)>MAX_BYTES:raise CandidateError('TRANSPORT_SIZE_OR_TYPE_LIMIT')
        message=payload.decode('utf-8')
        sha=hashlib.sha256(payload).hexdigest()
        event_digest=digest({'project':self.project,'binding':self.binding.binding_digest,'task':self.binding.task_id,'source':self.source,'destination':endpoint,'payload_sha256':sha})
        lock=os.open(self.state_root/'relay.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise CandidateError('CONCURRENT_DISPATCH_STOP')
            state=self.store.load() or {'project_instance_id':self.project,'binding_digest':self.binding.binding_digest,'connection_identity':self.connection_identity,'connection_digest':digest(self.connection_identity),'seen_events':{},'outbox':[],'total_hops':0,'consecutive_mechanical_failures':0}
            # 一个项目锁串行发送；复用 seen_events 和已有快照 index，不新造 wire sequence。
            if state['project_instance_id']!=self.project:raise CandidateError('STATE_PROJECT_CONFLICT')
            if 'connection_identity' not in state:raise CandidateError('LEGACY_STATE_EXPLICIT_MIGRATION_REQUIRED')
            if (state['connection_identity']!=self.connection_identity
                    or state.get('connection_digest')!=digest(self.connection_identity)):
                raise CandidateError('STATE_CONNECTION_BINDING_CONFLICT')
            previous=state['seen_events'].get(self.message_id)
            if previous:
                if previous['event_digest']!=event_digest:raise CandidateError('EVENT_ID_CONFLICT')
                if previous['status']!='ACKED':raise CandidateError('UNCERTAIN_DELIVERY_STOP')
                return {'delivered':False,'duplicate':True,'original_receipt':previous}
            if state['outbox']:raise CandidateError('UNCERTAIN_DELIVERY_STOP')
            entry={'message_id':self.message_id,'event_id':self.message_id,'task_id':self.binding.task_id,'event_digest':event_digest,'source_endpoint':self.source,'source_actor':self.binding.actor_for(self.source),'destination_endpoint':endpoint,'target_actor':actor,'binding_digest':self.binding.binding_digest,'message_sha256':sha,'bytes':len(payload),'status':'IN_FLIGHT','issued_at':now(),'acked_at':None,'evidence_ref':None}
            destination=next(e for e in self.connection_identity['endpoints'] if e['endpoint_id']==endpoint)
            entry.update(destination_resource_uri=self.endpoint_uris[endpoint],
                         destination_generation=destination['generation'],connection_digest=state['connection_digest'],
                         submission_known=False,observation_known=False)
            state['seen_events'][self.message_id]=entry;state['outbox']=[self.message_id]
            self._active_state=state
            self.store.save(state)
            uri=self.endpoint_uris[endpoint]
            intent={'type':'DELIVERY_INTENT','robot_id':self.relay_id,'project_instance_id':self.project,'message_id':self.message_id,'task_id':self.binding.task_id,'source':self.source,'source_actor':self.binding.actor_for(self.source),'output_to':endpoint,'target_actor':actor,'endpoint_uri':uri,'message':message,'message_sha256':sha,'payload_bytes':len(payload),'delivery_attempt':1,'deadline_seconds':120,'requires_actual_endpoint_ack':True}
            print(json.dumps(intent,ensure_ascii=False),file=self._output,flush=True)
            try:
                ready,_,_=select.select([self._input],[],[],120)
                if not ready:raise CandidateError('ACTUAL_ENDPOINT_ACK_TIMEOUT')
                raw=self._input.readline(MAX_BYTES*3+8193)
                if not raw or len(raw.encode())>MAX_BYTES*3+8192:raise CandidateError('ACK_MISSING_OR_BOUND')
                ack=json.loads(raw)
                expected={'type':'ACTUAL_ENDPOINT_ACK','project_instance_id':self.project,'message_id':self.message_id,'task_id':self.binding.task_id,'output_to':endpoint,'target_actor':actor,'endpoint_uri':uri,'message':message,'message_sha256':sha,'observed_delivery':True}
                if type(ack) is not dict or set(ack)!=ACK_KEYS or any(ack[k]!=v or type(ack[k]) is not type(v) for k,v in expected.items()) or type(ack['evidence_ref']) is not str or not ack['evidence_ref']:
                    raise CandidateError('ACTUAL_ENDPOINT_ACK_CONFLICT')
            except Exception:
                entry['status']='UNCERTAIN';state['consecutive_mechanical_failures']+=1
                self.store.save(state)
                raise
            entry.update(status='ACKED',acked_at=now(),evidence_ref=ack['evidence_ref'],
                         observation_known=True,observation_evidence_ref=ack['evidence_ref'])
            state['outbox']=[];state['total_hops']+=1;state['consecutive_mechanical_failures']=0
            self.store.save(state)
            receipt={'delivered':True,'duplicate':False,'intent':intent,'actual_endpoint_ack':ack}
            self.records.append(receipt)
            return receipt
        finally:
            self._active_state=None
            os.close(lock)

    def record_submission(self, submission):
        """仅持锁投递调用内留证；提交证据先于宿主实读，正文不复制进账本。"""
        state=getattr(self,'_active_state',None)
        if state is None:raise CandidateError('SUBMISSION_RECORD_REQUIRES_ACTIVE_DISPATCH')
        entry=state['seen_events'][self.message_id]
        endpoint=submission.endpoint
        if (entry['status']!='IN_FLIGHT' or endpoint.endpoint_id!=entry['destination_endpoint']
                or endpoint.actor_id!=entry['target_actor'] or endpoint.resource_uri!=entry['destination_resource_uri']
                or endpoint.generation!=entry['destination_generation']):
            raise CandidateError('SUBMISSION_RECORD_IDENTITY_CONFLICT')
        entry.update(status='SUBMITTED',submission_known=True,native_submission_id=submission.native_id,
                     submission_evidence_ref=submission.evidence_ref,submitted_at=now())
        self.store.save(state)

    def record_host_acceptance(self, evidence_ref):
        """宿主确认已接受、但还没有原生消息标识；保留这一步，不能冒充实读。"""
        state=getattr(self,'_active_state',None)
        if state is None or type(evidence_ref) is not str or not evidence_ref:
            raise CandidateError('SUBMISSION_RECORD_REQUIRES_ACTIVE_DISPATCH')
        entry=state['seen_events'][self.message_id]
        if entry['status']!='IN_FLIGHT':raise CandidateError('SUBMISSION_RECORD_IDENTITY_CONFLICT')
        entry.update(submission_known=True,host_acceptance_ref=evidence_ref,host_accepted_at=now())
        self.store.save(state)
