"""通用项目补建、实际投递、中断去重、原子接续与来源隔离。仅合成数据。"""
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock
import hashlib
import json
import sys
import tempfile
import unittest
sys.dont_write_bytecode = True
from xingshu_collaboration.router.contracts import Catalog, Project, ProjectRef, Chat, ProjectChannel
from xingshu_collaboration.router.lifecycle import (ProviderScope, LifecycleCapabilities, CreationProof,
    EnsureProject, LifecycleJournal, ProjectLifecycle)
from xingshu_collaboration.router.continuity import (ContextSignal, continuation_action, HandoffPacket, DrainProof,
    HandoffRead, ContinuityManager, doc)
from xingshu_collaboration.router.handoff_transport import HandoffTransport
from xingshu_collaboration.router.host_lifecycle import OfficialHostLifecyclePort
from xingshu_collaboration.router.online_continuity import OnlineContinuity
from contextlib import contextmanager
from xingshu_collaboration.connections.contracts import Endpoint, Capabilities, Observation, Submission
from xingshu_collaboration.connections.ports import PortRegistry
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.state import digest


class FakeChatPort:
    def __init__(self, endpoint):
        self.endpoint, self.sent, self.fail = endpoint, [], False
    def capabilities(self): return Capabilities('ISOLATED_TEST', True, True)
    def preflight(self): pass
    def checkpoint(self): return 'BASELINE'
    def submit(self, payload, deadline):
        self.sent.append(payload)
        if self.fail: raise TimeoutError('uncertain fake submission')
        return Submission(self.endpoint, self.endpoint.endpoint_id + '_INPUT_' + str(len(self.sent)), 'test://submit')
    def observe(self, checkpoint, submission, payload, deadline):
        return Observation(self.endpoint, payload, 'test://actual-input', submission.native_id)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve() / 'candidate'
        self.journal = LifecycleJournal(self.root)
        self.now = 1000.0
        self.p1 = ProjectRef('APP_A', 'P1', 'OWNER', 'LOCAL')
        self.p2 = ProjectRef('APP_B', 'P2', 'OWNER', 'CLOUD')
        self.scope = ProviderScope('APP_B', 'OWNER', 'CLOUD')
        self.o = Endpoint('ORIGIN', 'ORIGIN_AI', 'test://origin')
        self.x = Endpoint('X', 'X_AI', 'test://x')
        self.w = Endpoint('W', 'W_AI', 'test://w')
        self.nx = Endpoint('NEW_X', 'NEW_X_AI', 'test://newx', 2)
        self.nw = Endpoint('NEW_W', 'NEW_W_AI', 'test://neww', 2)
        self.no = Endpoint('NEW_ORIGIN', 'NEW_ORIGIN_AI', 'test://neworigin', 2)
        self.catalog = Catalog((Project(self.p1, 'PROJECT'), Project(self.p2, 'PROJECT')),
            tuple(Chat(e.endpoint_id, p, e, 'idle') for e,p in ((self.o,self.p1),(self.x,self.p1),
                (self.w,self.p2),(self.nx,self.p1),(self.nw,self.p2),(self.no,self.p1))), 'test://catalog', self.now)
        self.cp = Mock(snapshot=lambda: self.catalog)
        self.old = ProjectChannel('PROGRAM', 'PROJECT', (self.p1,self.p2), self.x,self.w,1,'test://old-register')
        self.new = replace(self.old, executor=self.nx, reviewer=self.nw, generation=2, registration_ref='test://new-register')
        self.manager = ContinuityManager(self.journal,self.cp,clock=lambda:self.now)
        self.manager.seed_candidate(self.old)
        self.packet = HandoffPacket('TASK_1','PROGRAM','1'*64,digest(asdict(self.old)),self.o,self.o,
            'V3','2'*64,'WAITING_REVIEW','finished one step','review exact V3','test://checkpoint',
            ('test://authorized-candidate',),'test://limited-owner-scope','3'*64,'test://human-request')
        self.drain = DrainProof(digest(asdict(self.old)),(),True,self.now,'test://complete-old-outbox')
        self.registry = PortRegistry(); self.chat_ports = {}
        for endpoint in (self.x,self.w,self.nx,self.nw):
            port=FakeChatPort(endpoint); self.chat_ports[endpoint.endpoint_id]=port; self.registry.register(port)
        self.transport=HandoffTransport(self.registry,self.root)
    def tearDown(self): self.tmp.cleanup()
    def assertOld(self):
        with self.journal.locked() as state:
            self.assertEqual(state['registrations']['PROGRAM']['channel'],doc(self.old))
    def proposal(self, **kw): return self.manager.propose(self.old,self.new,self.packet,self.drain,**kw)
    def read(self,e):
        return HandoffRead(self.packet.task_id,self.packet.packet_sha256,e,'V3','2'*64,'3'*64,
            e.endpoint_id+'_PACKET_INPUT',e.endpoint_id+'_TURN',e.endpoint_id+'_OUTPUT','test://native-model-read')
    def proven(self, tid):
        with self.journal.locked() as state:
            required=self.manager.required_reads(state['successors'][tid])
        for e in required: self.manager.observe_read(tid,self.read(e))
        for s,t in ((self.nx,self.nw),(self.nw,self.nx)):
            _, proof=self.transport.probe(self.packet,s,t); self.manager.observe_direction(tid,proof)
    def lifecycle(self, *, create=True, chat=True):
        port=OfficialHostLifecyclePort(self.scope,implementation='OFFICIAL_TOOL',
            create_project=self.create_project if create else None, create_chat=self.create_chat if chat else None)
        return ProjectLifecycle(self.journal,self.cp,port,clock=lambda:self.now)
    def create_project(self,op,scope,name):
        self.project_calls.append(op)
        p=Project(ProjectRef(scope.provider,'CREATED',scope.account_scope,scope.host_id),name)
        self.catalog=replace(self.catalog,projects=self.catalog.projects+(p,))
        proof=CreationProof(op,'PROJECT_NATIVE',p,'test://creation')
        self.creation_proof=proof
        if getattr(self,'unknown_create',False): raise TimeoutError('after actual creation')
        return proof
    def create_chat(self,op,project,sha):
        self.chat_calls.append(op)
        endpoint=Endpoint('CREATED_CHAT','CREATED_AI','test://created-chat',2)
        chat=Chat('CREATED_CHAT',project,endpoint,'idle')
        self.catalog=replace(self.catalog,chats=self.catalog.chats+(chat,))
        return CreationProof(op,'CHAT_NATIVE',chat,'test://chat-created')
    def missing_request(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],),chats=tuple(c for c in self.catalog.chats if c.project==self.p1))
        self.project_calls=[]
        return EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human-owner',True)

    def test_existing_registered_project_reused(self):
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2)
        self.assertEqual(self.lifecycle(create=False).ensure_project(r).ref,self.p2)
    def test_same_name_without_binding_never_adopted(self):
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True)
        with self.assertRaisesRegex(CandidateError,'SAME_NAME'): self.lifecycle().ensure_project(r)
    def test_missing_project_created_and_repeated_only_once(self):
        r=self.missing_request(); l=self.lifecycle(); p=l.ensure_project(r)
        self.assertEqual(l.ensure_project(r),p); self.assertEqual(len(self.project_calls),1)
    def test_missing_project_unsupported_no_intent_or_write(self):
        r=self.missing_request()
        with self.assertRaisesRegex(CandidateError,'UNSUPPORTED'): self.lifecycle(create=False).ensure_project(r)
        with self.journal.locked() as s: self.assertFalse(s['operations'])
    def test_creation_interrupt_no_resubmit_and_explicit_reconcile(self):
        r=self.missing_request(); self.unknown_create=True; l=self.lifecycle()
        with self.assertRaises(TimeoutError): l.ensure_project(r)
        l= self.lifecycle()  # 模拟重新启动宿主。
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'): l.ensure_project(r)
        self.assertEqual(len(self.project_calls),1)
        l.reconcile_creation(self.creation_proof.operation_id,self.creation_proof)
        self.assertEqual(l.ensure_project(r).ref,self.creation_proof.resource.ref)
        self.assertEqual(len(self.project_calls),1)
    def test_creation_wrong_native_operation_rejected(self):
        r=self.missing_request(); self.unknown_create=True; l=self.lifecycle()
        with self.assertRaises(TimeoutError): l.ensure_project(r)
        with self.assertRaises(CandidateError): l.reconcile_creation(self.creation_proof.operation_id,
            replace(self.creation_proof,operation_id='WRONG'))
    def test_creation_wrong_account_rejected(self):
        r=self.missing_request(); r=replace(r,target_scope=ProviderScope('APP_B','OTHER','CLOUD'))
        with self.assertRaisesRegex(CandidateError,'SCOPE_CONFLICT'): self.lifecycle().ensure_project(r)
    def test_creation_readback_required(self):
        r=self.missing_request(); l=self.lifecycle()
        l.port.project_callback=lambda op,s,n: CreationProof(op,'NATIVE',Project(self.p2,n),'test://create')
        with self.assertRaisesRegex(CandidateError,'PROJECT_NOT_OBSERVED'): l.ensure_project(r)
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'): l.ensure_project(r)
    def test_external_payload_is_not_trusted_project_intent(self):
        with self.assertRaises(CandidateError): self.lifecycle().ensure_project({'authorized':True})
    def test_project_name_drift_stops(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(self.p2,'OTHER')))
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2)
        with self.assertRaisesRegex(CandidateError,'NAME_DRIFT'): self.lifecycle().ensure_project(r)
    def test_project_rename_supported_and_identity_preserved(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(self.p2,'OLD')))
        def rename(op,p,n):
            self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(p,n)))
            return CreationProof(op,'RENAME_NATIVE',Project(p,n),'test://rename')
        port=OfficialHostLifecyclePort(self.scope,implementation='OFFICIAL_TOOL',rename_project=rename)
        l=ProjectLifecycle(self.journal,self.cp,port,clock=lambda:self.now)
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2)
        self.assertEqual(l.ensure_project(r),Project(self.p2,'PROJECT'))
    def test_project_rename_unknown_not_retried(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(self.p2,'OLD')))
        calls=[]
        def rename(op,p,n):
            calls.append(op); raise TimeoutError('rename may have happened')
        port=OfficialHostLifecyclePort(self.scope,implementation='OFFICIAL_TOOL',rename_project=rename)
        l=ProjectLifecycle(self.journal,self.cp,port,clock=lambda:self.now)
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2)
        with self.assertRaises(TimeoutError): l.ensure_project(r)
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'): l.ensure_project(r)
        self.assertEqual(len(calls),1)
    def test_rename_apparently_applied_does_not_clear_unknown(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(self.p2,'OLD')))
        def rename(op,p,n):
            self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(p,n)))
            raise TimeoutError('actual rename response lost')
        l=ProjectLifecycle(self.journal,self.cp,OfficialHostLifecyclePort(self.scope,implementation='OFFICIAL_TOOL',rename_project=rename),clock=lambda:self.now)
        r=EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2)
        with self.assertRaises(TimeoutError): l.ensure_project(r)
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'): l.ensure_project(r)
        with self.assertRaisesRegex(CandidateError,'OPERATION_UNCONFIRMED'): self.proposal()
    def test_successor_created_once_even_catalog_changed(self):
        self.chat_calls=[]; l=self.lifecycle()
        args=dict(project=self.p2,predecessor=self.w,handoff_sha256=self.packet.packet_sha256,owner_trigger_ref='test://human')
        p=l.create_successor(**args); self.assertEqual(l.create_successor(**args),p)
        self.assertEqual(len(self.chat_calls),1)
    def test_successor_completed_status_does_not_block_identity_recovery(self):
        self.chat_calls=[]; l=self.lifecycle()
        args=dict(project=self.p2,predecessor=self.w,handoff_sha256=self.packet.packet_sha256,owner_trigger_ref='test://human')
        chat=l.create_successor(**args)
        self.catalog=replace(self.catalog,chats=tuple(replace(c,status='completed') if c.endpoint==chat.endpoint else c for c in self.catalog.chats))
        recovered=l.create_successor(**args)
        self.assertEqual(recovered.endpoint,chat.endpoint); self.assertEqual(recovered.status,'completed')
        self.assertEqual(len(self.chat_calls),1)
    def test_successor_wrong_parent_project_stops(self):
        with self.assertRaises(CandidateError): self.lifecycle().create_successor(project=self.p2,predecessor=self.x,
            handoff_sha256=self.packet.packet_sha256,owner_trigger_ref='test://human')
    def test_successor_reusing_old_chat_rejected(self):
        l=self.lifecycle(); l.port.chat_callback=lambda op,p,h: CreationProof(op,'NATIVE',self.catalog.chat(self.w),'test://create')
        with self.assertRaisesRegex(CandidateError,'IS_NOT_NEW'): l.create_successor(project=self.p2,predecessor=self.w,
            handoff_sha256=self.packet.packet_sha256,owner_trigger_ref='test://human')
    def test_catalog_stale_stops(self):
        self.catalog=replace(self.catalog,observed_at=1)
        with self.assertRaisesRegex(CandidateError,'STALE'): self.lifecycle().ensure_project(
            EnsureProject('PROGRAM',self.p1,'PROJECT',self.scope,'test://human',True,self.p2))
    def test_context_unknown_does_not_assume_full(self):
        sig=ContextSignal(self.x,'UNKNOWN',self.now,'test://native')
        self.assertEqual(continuation_action(sig,now=self.now),'SAVE_CHECKPOINT_CONTEXT_UNKNOWN')
    def test_context_actual_usage_threshold(self):
        sig=ContextSignal(self.x,'USAGE',self.now,'test://usage',850,1000)
        self.assertEqual(continuation_action(sig,now=self.now),'PREPARE_SUCCESSOR')
        self.assertEqual(continuation_action(replace(sig,used_tokens=849),now=self.now),'CONTINUE_CURRENT')
    def test_context_compaction_requires_completion_before_resumption(self):
        sig=ContextSignal(self.x,'CONTEXT_LIMIT',self.now,'test://limit')
        self.assertEqual(continuation_action(sig,now=self.now,compact_supported=True),'COMPACT_THEN_VERIFY')
    def test_context_system_error_not_limit_signal(self):
        with self.assertRaises(CandidateError): continuation_action(ContextSignal(self.x,'SYSTEM_ERROR',self.now,'test://error'),now=self.now)
    def test_context_usage_capacity_unknown_rejected(self):
        with self.assertRaises(CandidateError): continuation_action(ContextSignal(self.x,'USAGE',self.now,'test://usage',850,None),now=self.now)
    def test_context_stale_rejected(self):
        with self.assertRaises(CandidateError): continuation_action(ContextSignal(self.x,'OWNER_HANDOFF',1,'test://old'),now=self.now)
    def test_context_boolean_usage_rejected(self):
        with self.assertRaises(CandidateError): continuation_action(ContextSignal(self.x,'USAGE',self.now,'test://usage',True,1000),now=self.now)
    def test_proposal_does_not_change_registration(self):
        self.proposal(); self.assertOld()
    def test_unknown_delivery_blocks_even_with_new_pages(self):
        with self.assertRaisesRegex(CandidateError,'NOT_PROVEN_DRAINED'): self.manager.propose(self.old,self.new,self.packet,
            replace(self.drain,unresolved_message_ids=('OLD_UNKNOWN',)))
        self.assertOld()
    def test_incomplete_old_message_catalog_blocks(self):
        with self.assertRaises(CandidateError): self.manager.propose(self.old,self.new,self.packet,replace(self.drain,complete=False))
    def test_context_limit_does_not_bypass_old_endpoint_system_error(self):
        self.catalog=replace(self.catalog,chats=tuple(replace(c,status='systemError') if c.endpoint==self.w else c for c in self.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'QUIESCENT'): self.proposal()
    def test_one_new_page_wrong_project_blocks(self):
        self.catalog=replace(self.catalog,chats=tuple(replace(c,project=self.p1) if c.endpoint==self.nw else c for c in self.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'MEMBERSHIP'): self.proposal()
    def test_generation_must_increment_once(self):
        with self.assertRaises(CandidateError): self.manager.propose(self.old,replace(self.new,generation=4),self.packet,self.drain)
    def test_old_page_cannot_be_successor(self):
        with self.assertRaises(CandidateError): self.manager.propose(self.old,replace(self.new,executor=self.x,reviewer=self.w),self.packet,self.drain)
    def test_only_full_side_can_rotate(self):
        new=replace(self.new,reviewer=self.w)
        tid=self.manager.propose(self.old,new,self.packet,self.drain)
        for e in (self.nx,self.w): self.manager.observe_read(tid,self.read(e))
        for s,t in ((self.nx,self.w),(self.w,self.nx)):
            _,p=self.transport.probe(self.packet,s,t); self.manager.observe_direction(tid,p)
        self.assertEqual(self.manager.commit_candidate(tid,self.drain),new)
    def test_names_must_be_mirrored_before_switch(self):
        self.catalog=replace(self.catalog,projects=(self.catalog.projects[0],Project(self.p2,'OTHER')))
        with self.assertRaisesRegex(CandidateError,'NAMES_NOT_MIRRORED'): self.proposal()
    def test_no_acks_blocks_commit(self):
        tid=self.proposal()
        with self.assertRaisesRegex(CandidateError,'BOTH_READS'): self.manager.commit_candidate(tid,self.drain)
        self.assertOld()
    def test_one_way_does_not_commit(self):
        tid=self.proposal()
        for e in (self.nx,self.nw): self.manager.observe_read(tid,self.read(e))
        _,pr=self.transport.probe(self.packet,self.nx,self.nw); self.manager.observe_direction(tid,pr)
        with self.assertRaises(CandidateError): self.manager.commit_candidate(tid,self.drain)
        self.assertOld()
    def test_wrong_handoff_version_not_accepted(self):
        tid=self.proposal()
        with self.assertRaises(CandidateError): self.manager.observe_read(tid,replace(self.read(self.nx),work_version='V2'))
    def test_host_submission_without_model_output_not_read(self):
        tid=self.proposal()
        with self.assertRaises(CandidateError): self.manager.observe_read(tid,replace(self.read(self.nx),native_output_id=''))
    def test_wrong_probe_payload_digest_not_accepted(self):
        tid=self.proposal(); _,p=self.transport.probe(self.packet,self.nx,self.nw)
        with self.assertRaises(CandidateError): self.manager.observe_direction(tid,replace(p,payload_sha256='f'*64))
    def test_probe_replay_deduplicated(self):
        self.transport.probe(self.packet,self.nx,self.nw); self.transport.probe(self.packet,self.nx,self.nw)
        self.assertEqual(len(self.chat_ports['NEW_W'].sent),1)
    def test_probe_uncertain_no_resend_after_restart(self):
        self.chat_ports['NEW_W'].fail=True
        with self.assertRaises(CandidateError): self.transport.probe(self.packet,self.nx,self.nw)
        self.transport=HandoffTransport(self.registry,self.root)
        with self.assertRaises(CandidateError): self.transport.probe(self.packet,self.nx,self.nw)
        self.assertEqual(len(self.chat_ports['NEW_W'].sent),1)
    def test_handoff_packet_is_continuation_not_new_goal(self):
        self.transport.send_packet(self.packet,self.x,self.nx)
        payload=json.loads(self.chat_ports['NEW_X'].sent[0])
        self.assertFalse(payload['execute_business_goal']); self.assertEqual(payload['packet']['task_id'],'TASK_1')
        self.transport.send_packet(self.packet,self.x,self.nx); self.assertEqual(len(self.chat_ports['NEW_X'].sent),1)
    def test_full_cutover_and_result_returns_to_original_if_not_changed(self):
        tid=self.proposal(); self.proven(tid); self.assertEqual(self.manager.commit_candidate(tid,self.drain),self.new)
        self.assertEqual(self.manager.effective_return('PROGRAM','TASK_1',self.o,'1'*64),self.o)
        self.assertEqual(self.manager.commit_candidate(tid,self.drain),self.new)
    def test_origin_replaced_and_original_identity_preserved(self):
        tid=self.proposal(new_origin=self.no); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        self.assertEqual(self.manager.effective_return('PROGRAM','TASK_1',self.o,'1'*64),self.no)
        with self.assertRaises(CandidateError): self.manager.effective_return('PROGRAM','TASK_1',self.no,'1'*64)
    def test_new_return_origin_must_itself_read_handoff(self):
        tid=self.proposal(new_origin=self.no)
        for e in (self.nx,self.nw): self.manager.observe_read(tid,self.read(e))
        for s,t in ((self.nx,self.nw),(self.nw,self.nx)):
            _,p=self.transport.probe(self.packet,s,t); self.manager.observe_direction(tid,p)
        with self.assertRaisesRegex(CandidateError,'BOTH_READS'): self.manager.commit_candidate(tid,self.drain)
        self.assertOld()
    def test_return_origin_changed_project_after_cutover_stops(self):
        tid=self.proposal(new_origin=self.no); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        other=ProjectRef('APP_A','UNRELATED','OWNER','LOCAL')
        self.catalog=replace(self.catalog,projects=self.catalog.projects+(Project(other,'OTHER'),),
            chats=tuple(replace(c,project=other) if c.endpoint==self.no else c for c in self.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'RETURN_PROJECT_CHANGED'):
            self.manager.effective_return('PROGRAM','TASK_1',self.o,'1'*64)
    def test_return_origin_changed_project_before_cutover_stops(self):
        tid=self.proposal(new_origin=self.no); self.proven(tid)
        self.catalog=replace(self.catalog,chats=tuple(replace(c,project=self.p2) if c.endpoint==self.no else c for c in self.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'RETURN_PROJECT_CHANGED'): self.manager.commit_candidate(tid,self.drain)
        self.assertOld()
    def test_later_handoff_cannot_rebase_return_project_after_drift(self):
        tid=self.proposal(new_origin=self.no); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        x=Endpoint('THIRD_X','THIRD_X_AI','test://thirdx',3); w=Endpoint('THIRD_W','THIRD_W_AI','test://thirdw',3)
        self.catalog=replace(self.catalog,chats=tuple(replace(c,project=self.p2) if c.endpoint==self.no else c for c in self.catalog.chats)
            +(Chat('X3',self.p1,x,'idle'),Chat('W3',self.p2,w,'idle')))
        new=replace(self.new,executor=x,reviewer=w,generation=3,registration_ref='test://third')
        packet=replace(self.packet,old_channel_sha256=digest(asdict(self.new)),effective_origin=self.no)
        drain=replace(self.drain,channel_sha256=digest(asdict(self.new)))
        with self.assertRaisesRegex(CandidateError,'LINEAGE_PROJECT_CHANGED'):
            self.manager.propose(self.new,new,packet,drain)
        with self.journal.locked() as state:
            self.assertEqual(state['registrations']['PROGRAM']['channel'],doc(self.new))
            self.assertEqual(state['registrations']['PROGRAM']['returns']['TASK_1']['project'],asdict(self.p1))
    def test_origin_same_as_retired_executor_automatically_follows(self):
        self.packet=replace(self.packet,original_origin=self.x,effective_origin=self.x)
        tid=self.proposal(); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        self.assertEqual(self.manager.effective_return('PROGRAM','TASK_1',self.x,'1'*64),self.nx)
    def test_return_cannot_move_to_other_project(self):
        with self.assertRaises(CandidateError): self.proposal(new_origin=self.nw)
    def test_readback_membership_drift_at_commit_stops(self):
        tid=self.proposal(); self.proven(tid)
        self.catalog=replace(self.catalog,chats=tuple(replace(c,project=self.p2) if c.endpoint==self.nx else c for c in self.catalog.chats))
        with self.assertRaises(CandidateError): self.manager.commit_candidate(tid,self.drain)
        self.assertOld()
    def test_new_unknown_arrives_before_commit_stops(self):
        tid=self.proposal(); self.proven(tid)
        with self.assertRaises(CandidateError): self.manager.commit_candidate(tid,replace(self.drain,unresolved_message_ids=('NEW_UNKNOWN',)))
        self.assertOld()
    def test_competing_successor_proposals_stopped(self):
        self.proposal()
        with self.assertRaises(CandidateError): self.proposal(new_origin=self.no)
    def test_second_rollover_preserves_task_lineage(self):
        tid=self.proposal(new_origin=self.no); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        x2=Endpoint('THIRD_X','THIRD_X_AI','test://thirdx',3); w2=Endpoint('THIRD_W','THIRD_W_AI','test://thirdw',3)
        self.catalog=replace(self.catalog,chats=self.catalog.chats+(Chat('X3',self.p1,x2,'idle'),Chat('W3',self.p2,w2,'idle')))
        nextchannel=replace(self.new,executor=x2,reviewer=w2,generation=3,registration_ref='test://third-register')
        self.packet=replace(self.packet,old_channel_sha256=digest(asdict(self.new)),effective_origin=self.no)
        self.drain=replace(self.drain,channel_sha256=digest(asdict(self.new)))
        tid2=self.manager.propose(self.new,nextchannel,self.packet,self.drain)
        for e in (x2,w2):
            self.registry.register(FakeChatPort(e)); self.manager.observe_read(tid2,self.read(e))
        for s,t in ((x2,w2),(w2,x2)):
            _,p=self.transport.probe(self.packet,s,t); self.manager.observe_direction(tid2,p)
        self.manager.commit_candidate(tid2,self.drain)
        self.assertEqual(self.manager.effective_return('PROGRAM','TASK_1',self.o,'1'*64),self.no)
    def test_source_packet_oversized_rejected(self):
        with self.assertRaises(CandidateError): replace(self.packet,summary='x'*4097).validate()
    def test_packet_does_not_grant_independent_review_pass(self):
        tid=self.proposal(); self.proven(tid); self.manager.commit_candidate(tid,self.drain)
        with self.journal.locked() as state:
            self.assertNotIn('review',state['registrations']['PROGRAM']['returns']['TASK_1'])
    def test_online_auto_build_send_verify_and_switch_without_new_goal(self):
        def make_port(project, endpoint):
            scope=ProviderScope(project.provider,project.account_scope,project.host_id)
            def create(op,p,h):
                chat=Chat(endpoint.endpoint_id,p,endpoint,'idle')
                self.catalog=replace(self.catalog,chats=self.catalog.chats+(chat,))
                self.registry.register(FakeChatPort(endpoint))
                return CreationProof(op,endpoint.endpoint_id+'_CREATED',chat,'test://native-chat-create')
            return ProjectLifecycle(self.journal,self.cp,OfficialHostLifecyclePort(scope,
                implementation='OFFICIAL_TOOL',create_chat=create),clock=lambda:self.now)
        x=Endpoint('AUTO_X','AUTO_X_AI','test://autox',2); w=Endpoint('AUTO_W','AUTO_W_AI','test://autow',2)
        outer=self
        class Drain:
            entered=False
            def proof(self,ch): return outer.drain
            @contextmanager
            def fenced(self,ch):
                self.entered=True
                yield outer.drain
        drain=Drain()
        online=OnlineContinuity(self.manager,{self.p1:make_port(self.p1,x),self.p2:make_port(self.p2,w)},
            self.transport,drain,clock=lambda:self.now)
        signals=tuple(ContextSignal(e,'OWNER_HANDOFF',self.now,'test://human') for e in (self.x,self.w))
        prepared=online.prepare_on_signal(self.old,self.packet,signals)
        tid=prepared['transition_id']; self.assertOld()
        online.send_checkpoint(tid,self.packet)
        result=online.complete_candidate(tid,self.packet,tuple(self.read(e) for e in (x,w)))
        self.assertEqual(result['status'],'CANDIDATE_CUTOVER_COMMITTED'); self.assertTrue(drain.entered)
        self.assertFalse(result['formal_activation']); self.assertFalse(result['execute_business_goal'])
        repeated=online.complete_candidate(tid,self.packet,tuple(self.read(e) for e in (x,w)))
        self.assertTrue(repeated['duplicate'])
        prepared_again=online.prepare_on_signal(self.old,self.packet,signals)
        self.assertTrue(prepared_again['duplicate'])
        self.assertEqual(prepared_again['channel'],result['channel'])
        self.assertEqual(len(self.registry.resolve(x).sent),2)
        self.assertEqual(len(self.registry.resolve(w).sent),2)
    def test_online_context_unknown_does_not_create_pages(self):
        online=OnlineContinuity(self.manager,{},self.transport,Mock(),clock=lambda:self.now)
        result=online.prepare_on_signal(self.old,self.packet,(ContextSignal(self.x,'UNKNOWN',self.now,'test://unknown'),))
        self.assertEqual(result['status'],'CHECKPOINT_ONLY')
        with self.journal.locked() as state:
            checkpoint=state['operations']['CHECKPOINT_'+self.packet.packet_sha256[:48]]
            self.assertEqual(checkpoint['resource']['task_id'],'TASK_1')
    def test_online_compaction_does_not_claim_success(self):
        online=OnlineContinuity(self.manager,{},self.transport,Mock(),clock=lambda:self.now)
        result=online.prepare_on_signal(self.old,self.packet,(ContextSignal(self.x,'USAGE',self.now,'test://usage',900,1000),),compact_supported=True)
        self.assertEqual(result['status'],'NATIVE_COMPACTION_COMPLETION_REQUIRED')

if __name__=='__main__': unittest.main()
