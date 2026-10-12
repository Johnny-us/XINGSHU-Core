"""显式、先证据后追加的旧日志迁移；正常投递不自动调用。"""
import fcntl
import os
import re
from pathlib import Path
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.state import SnapshotStore,digest
from .contracts import Endpoint,LinkBinding

def migrate_legacy_state(state_root, *, confirmed_identity, expected_state_digest, receipts):
    """receipts 是上层逐条核对原实读凭据后提供的机械证据，不是正文授权。"""
    root=Path(state_root)
    if (type(confirmed_identity) is not dict or set(confirmed_identity)!={'protocol','project_instance_id','relay_id','endpoints'}
            or type(confirmed_identity['endpoints']) is not list or len(confirmed_identity['endpoints'])!=2
            or type(expected_state_digest) is not str or not re.fullmatch('[0-9a-f]{64}',expected_state_digest)):
        raise CandidateError('LEGACY_MIGRATION_ENDPOINT_UNPROVEN')
    try: LinkBinding('MIGRATION',tuple(Endpoint(**e) for e in confirmed_identity['endpoints'])).validate()
    except (TypeError,ValueError) as exc:raise CandidateError('LEGACY_MIGRATION_ENDPOINT_UNPROVEN') from exc
    store=SnapshotStore(root/'snapshots',root.parent)
    fd=os.open(root/'relay.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise CandidateError('CONCURRENT_DISPATCH_STOP') from exc
        state=store.load()
        if (type(state) is not dict or digest(state)!=expected_state_digest
                or 'connection_identity' in state or state.get('outbox')
                or state.get('project_instance_id')!=confirmed_identity.get('project_instance_id')
                or confirmed_identity.get('protocol')!='xingshu-connection/1'):
            raise CandidateError('LEGACY_MIGRATION_STATE_UNPROVEN')
        endpoints={e['endpoint_id']:e for e in confirmed_identity['endpoints']}
        if len(endpoints)!=2 or any(e.get('generation')!=1 for e in endpoints.values()):
            raise CandidateError('LEGACY_MIGRATION_ENDPOINT_UNPROVEN')
        entries=state.get('seen_events',{})
        if type(receipts) is not dict or not entries or set(receipts)!=set(entries):
            raise CandidateError('LEGACY_MIGRATION_RECEIPT_COVERAGE_REQUIRED')
        for mid,entry in entries.items():
            target=endpoints.get(entry.get('destination_endpoint'),{})
            source=endpoints.get(entry.get('source_endpoint'),{})
            expected={'message_id':mid,'message_sha256':entry['message_sha256'],
                      'target_actor':target.get('actor_id'),'source_actor':source.get('actor_id'),
                      'destination_resource_uri':target.get('resource_uri'),'destination_generation':1,
                      'binding_digest':entry['binding_digest'],'evidence_ref':entry['evidence_ref']}
            receipt=receipts[mid]
            if (entry.get('status')!='ACKED' or entry.get('target_actor')!=target.get('actor_id')
                    or entry.get('source_actor')!=source.get('actor_id') or source==target
                    or any(receipt.get(k)!=v for k,v in expected.items())
                    or receipt.get('actual_input_verified') is not True
                    or type(receipt.get('evidence_sha256')) is not str or not re.fullmatch('[0-9a-f]{64}',receipt['evidence_sha256'])):
                raise CandidateError('LEGACY_MIGRATION_EXACT_RECEIPT_REQUIRED')
        state.update(connection_identity=confirmed_identity,connection_digest=digest(confirmed_identity),
                     migration={'from':'legacy-fixed-route','receipt_digest':digest(receipts),'entry_count':len(entries)})
        for entry in entries.values():
            target=endpoints[entry['destination_endpoint']]
            entry.update(destination_resource_uri=target['resource_uri'],destination_generation=1,
                         connection_digest=state['connection_digest'],observation_known=True,
                         observation_evidence_ref=entry['evidence_ref'],submission_known=False)
        return store.save(state)
    finally: os.close(fd)
