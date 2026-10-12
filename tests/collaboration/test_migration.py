"""旧记录必须有逐条实读凭据才可显式追加迁移，原封印快照不改写。"""
import dataclasses
import tempfile
import unittest
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from xingshu_collaboration.connections.contracts import Endpoint,LinkBinding
from xingshu_collaboration.connections.migration import migrate_legacy_state
from xingshu_collaboration.connections.transport import connection_identity
from xingshu_collaboration.state import SnapshotStore,digest
from xingshu_collaboration.binding import CandidateError

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()/'state'
        self.store=SnapshotStore(self.root/'snapshots',self.root.parent)
        a=Endpoint('A','ACTOR_A','test://a');b=Endpoint('B','ACTOR_B','test://b')
        self.binding=LinkBinding('TASK_1',(a,b))
        self.identity=connection_identity(self.binding,{'A':a.resource_uri,'B':b.resource_uri},'project','RELAY')
        self.state={'project_instance_id':'project','binding_digest':self.binding.binding_digest,'outbox':[],
                    'seen_events':{'M_1':{'status':'ACKED','message_id':'M_1','message_sha256':'1'*64,
                    'source_endpoint':'A','source_actor':'ACTOR_A','destination_endpoint':'B','target_actor':'ACTOR_B',
                    'binding_digest':self.binding.binding_digest,'task_id':'TASK_1','evidence_ref':'test://receipt'}},'total_hops':1}
        self.store.save(self.state)
        self.receipts={'M_1':{'message_id':'M_1','message_sha256':'1'*64,'source_actor':'ACTOR_A','target_actor':'ACTOR_B',
                       'destination_resource_uri':'test://b','destination_generation':1,'binding_digest':self.binding.binding_digest,
                       'evidence_ref':'test://receipt','actual_input_verified':True,'evidence_sha256':'a'*64}}
    def tearDown(self):self.tmp.cleanup()
    def migrate(self,**changes):
        args=dict(confirmed_identity=self.identity,expected_state_digest=digest(self.state),receipts=self.receipts);args.update(changes)
        return migrate_legacy_state(self.root,**args)
    def test_append_only_migration_preserves_original_record(self):
        first=self.root/'snapshots/snapshot-000001.json';raw=first.read_bytes()
        self.migrate();self.assertEqual(first.read_bytes(),raw)
        state=self.store.load();self.assertEqual(state['total_hops'],1)
        self.assertEqual(state['seen_events']['M_1']['binding_digest'],self.binding.binding_digest)
        self.assertEqual(state['seen_events']['M_1']['destination_resource_uri'],'test://b')
        self.assertEqual(len(self.store.records()[0]),2)
    def test_missing_exact_receipt_stops(self):
        with self.assertRaisesRegex(CandidateError,'COVERAGE'):self.migrate(receipts={})
        self.assertEqual(len(self.store.records()[0]),1)
    def test_state_drift_stops_before_append(self):
        with self.assertRaisesRegex(CandidateError,'STATE_UNPROVEN'):self.migrate(expected_state_digest='0'*64)
    def test_wrong_old_uri_stops(self):
        self.receipts['M_1']['destination_resource_uri']='test://different'
        with self.assertRaisesRegex(CandidateError,'EXACT_RECEIPT'):self.migrate()
    def test_unknown_old_delivery_cannot_be_migrated(self):
        self.state['seen_events']['M_1']['status']='UNCERTAIN';self.state['outbox']=['M_1'];self.store.save(self.state)
        with self.assertRaisesRegex(CandidateError,'STATE_UNPROVEN'):self.migrate()
    def test_migration_cannot_upgrade_generation(self):
        self.identity['endpoints'][1]['generation']=2
        with self.assertRaisesRegex(CandidateError,'ENDPOINT_UNPROVEN'):self.migrate()
    def test_repeated_migration_is_not_silently_reapplied(self):
        self.migrate()
        with self.assertRaisesRegex(CandidateError,'STATE_UNPROVEN'):self.migrate(expected_state_digest=digest(self.store.load()))

if __name__=='__main__':unittest.main()
