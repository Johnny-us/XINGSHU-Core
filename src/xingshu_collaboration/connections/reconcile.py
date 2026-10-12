"""已知原生提交标识的迟到实读对账；没有提交、重发或后台能力。"""
import fcntl
import hashlib
import os
from datetime import datetime,timezone
from pathlib import Path
from xingshu_collaboration.binding import CandidateError,identity
from xingshu_collaboration.state import SnapshotStore,digest
from .contracts import Observation

def reconcile_observation(state_root, *, confirmed_identity, message_id, observation):
    if (not identity(message_id) or type(observation) is not Observation
            or type(observation.payload) is not bytes or len(observation.payload)>131072
            or type(observation.evidence_ref) is not str or not observation.evidence_ref):
        raise CandidateError('RECONCILE_EXACT_OBSERVATION_REQUIRED')
    observation.endpoint.validate()
    root=Path(state_root);store=SnapshotStore(root/'snapshots',root.parent)
    fd=os.open(root/'relay.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise CandidateError('CONCURRENT_DISPATCH_STOP') from exc
        state=store.load()
        if (not state or state.get('connection_identity')!=confirmed_identity
                or state.get('connection_digest')!=digest(confirmed_identity)):
            raise CandidateError('RECONCILE_CONNECTION_CONFLICT')
        entry=state.get('seen_events',{}).get(message_id,{})
        endpoint=observation.endpoint
        if (entry.get('destination_endpoint')!=endpoint.endpoint_id or entry.get('target_actor')!=endpoint.actor_id
                or entry.get('destination_resource_uri')!=endpoint.resource_uri
                or entry.get('destination_generation')!=endpoint.generation
                or not entry.get('submission_known') or not entry.get('native_submission_id')
                or entry['native_submission_id']!=observation.submission_id
                or entry.get('message_sha256')!=hashlib.sha256(observation.payload).hexdigest()
                or entry.get('bytes')!=len(observation.payload)
                or entry.get('connection_digest')!=state['connection_digest']):
            raise CandidateError('RECONCILE_ORIGINAL_SUBMISSION_CONFLICT')
        if entry.get('status')=='ACKED':return {'reconciled':True,'duplicate':True,'model_turn_consumed':False}
        if entry.get('status') not in {'UNCERTAIN','IN_FLIGHT','SUBMITTED'} or state.get('outbox')!=[message_id]:
            raise CandidateError('RECONCILE_UNCERTAIN_OUTBOX_REQUIRED')
        entry.update(status='ACKED',observation_known=True,observation_evidence_ref=observation.evidence_ref,
                     evidence_ref=observation.evidence_ref,acked_at=datetime.now(timezone.utc).isoformat(),
                     late_observation_reconciled=True,original_outcome='DELIVERY_UNKNOWN')
        state['outbox']=[];state['total_hops']+=1;state['consecutive_mechanical_failures']=0
        store.save(state)
        return {'reconciled':True,'duplicate':False,'original_outcome':'DELIVERY_UNKNOWN',
                'model_turn_consumed':False,'automatic_retry':False}
    finally:os.close(fd)
