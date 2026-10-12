"""接续提交、业务进度迁移、精确版本复核与真实假端口返回的贯通测试。"""
from dataclasses import asdict, replace
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
import hashlib
import sys
import unittest
sys.dont_write_bytecode = True
from . import test_current_chat as current_fixtures
from . import test_continuity as continuity_fixtures
from xingshu_collaboration.router.contracts import Chat, Invocation
from xingshu_collaboration.router.current_chat import CurrentChatRouter
from xingshu_collaboration.router.router import ProjectRouter
from xingshu_collaboration.router.coordinator import TaskCoordinator, ReviewObservation
from xingshu_collaboration.router.continuity import HandoffPacket, HandoffRead, DrainProof, ContinuityManager, ContextSignal, registration_key
from xingshu_collaboration.router.lifecycle import LifecycleJournal, CreationProof, ProjectLifecycle
from xingshu_collaboration.router.online_continuity import OnlineContinuity
from xingshu_collaboration.router.current_chat import current_channel
from xingshu_collaboration.router.handoff_transport import HandoffTransport
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.connections.ports import PortRegistry
from xingshu_collaboration.state import digest
from xingshu_collaboration.binding import CandidateError


class CoordinatorContinuationTests(unittest.TestCase):
    def setUp(self):
        h = current_fixtures.CurrentChatTests('test_no_current_codex_project_or_chat_created')
        h.setUp(); self.h = h
        self.payload = b'synthetic current task'
        h.invocation = replace(h.invocation,request_sha256=hashlib.sha256(self.payload).hexdigest())
        h.proof = replace(h.proof,invocation=h.invocation)
        self.old = h.ensure()
        self.nw = Endpoint('NEW_WEB_A','NEW_W_ACTOR','test://new-web-a',2)
        h.catalog = replace(h.catalog,chats=h.catalog.chats+(Chat('NEW_WEB_A',h.web_project,self.nw,'idle','A事情'),))
        self.new = replace(self.old,reviewer=self.nw,generation=2,registration_ref='test://new-topic-pair')
        self.registry = PortRegistry(); self.ports = {}
        for e in (h.origin,h.peer,self.nw):
            p = continuity_fixtures.FakeChatPort(e);self.ports[e.endpoint_id]=p;self.registry.register(p)
        self.coordinator = TaskCoordinator(h.mirror.router(h.proof,self.old),self.registry,h.root/'business')
        self.route = self.coordinator.prepare(Mock(current_invocation=lambda:h.invocation))
        self.coordinator.set_artifact(self.route,'V1','2'*64)
        self.review(self.coordinator,self.route,h.peer)
        self.manager = ContinuityManager(h.journal,h.cp,clock=lambda:h.now)
        self.manager.seed_candidate(self.old)
        self.packet = HandoffPacket(h.invocation.task_id,'PROGRAM',h.invocation.request_sha256,
            digest(asdict(self.old)),h.origin,h.origin,'V1','2'*64,'REVIEW_ACCEPTED',
            '模拟3步已完成2步','核对最后一步并向当前窗口返回','test://checkpoint-2',
            ('test://synthetic-source',),'test://owner-scope','3'*64,h.invocation.owner_trigger_ref)
        self.drain = DrainProof(digest(asdict(self.old)),(),True,h.now,'test://synthetic-drain')
        self.transport = HandoffTransport(self.registry,h.root)
    def tearDown(self):
        self.h.tearDown()
    def review(self,c,route,peer):
        proof = ReviewObservation(route.route_digest,route.task_id,peer,'V1','2'*64,'PASS',
            peer.endpoint_id+'_TURN',peer.endpoint_id+'_OUTPUT','test://synthetic-review','4'*64)
        c.observe_review(route,Mock(observe_review=lambda r:proof))
    def commit(self):
        tid = self.manager.propose(self.old,self.new,self.packet,self.drain)
        for e in (self.new.executor,self.new.reviewer):
            self.manager.observe_read(tid,HandoffRead(self.packet.task_id,self.packet.packet_sha256,e,self.packet.work_version,self.packet.artifact_sha256,
                '3'*64,e.endpoint_id+'_INPUT',e.endpoint_id+'_TURN',e.endpoint_id+'_OUTPUT','test://simulated-read'))
        for source,target in ((self.new.executor,self.new.reviewer),(self.new.reviewer,self.new.executor)):
            _,proof = self.transport.probe(self.packet,source,target)
            self.manager.observe_direction(tid,proof)
        self.coordinator.commit_verified(self.route,self.manager,tid,self.drain)
        return tid
    def restarted(self):
        return TaskCoordinator(CurrentChatRouter(self.h.cp,self.h.proof,self.new,clock=lambda:self.h.now),
                               self.registry,self.h.root/'business')
    def test_web_only_rollover_keeps_current_origin_and_progress(self):
        tid = self.commit(); restarted = self.restarted()
        resumed = restarted.resume_verified(self.route,self.manager,tid)
        state = restarted.status(resumed)
        self.assertEqual(resumed.task_id,self.route.task_id)
        self.assertEqual(resumed.origin,self.h.origin)
        self.assertEqual(state['artifact'],{'version':'V1','sha256':'2'*64})
        self.assertEqual(state['progress_summary'],self.packet.summary)
        self.assertEqual(state['next_step'],self.packet.next_step)
        self.assertEqual(state['original_origin'],asdict(self.h.origin))
        self.review(restarted,resumed,self.nw)
        result = restarted.return_result(resumed,version='V1',artifact_sha256='2'*64,
            message_id='SAME_TASK_RESULT',payload='模拟结果'.encode())
        self.assertEqual(result['dispatch'],'CURRENT_EXECUTOR_MUST_REPLY_IN_PLACE')
        self.assertEqual(restarted.status(resumed)['return_message_id'],'SAME_TASK_RESULT')
    def test_old_review_never_authorizes_new_pair(self):
        tid = self.commit(); restarted = self.restarted()
        resumed = restarted.resume_verified(self.route,self.manager,tid)
        self.assertIsNone(restarted.status(resumed)['review'])
        with self.assertRaisesRegex(CandidateError,'EXACT_VERSION_REVIEW_REQUIRED'):
            restarted.return_result(resumed,version='V1',artifact_sha256='2'*64,
                message_id='RESULT',payload=b'result')
    def test_resume_repeated_once_even_after_new_review(self):
        tid = self.commit(); restarted = self.restarted()
        resumed = restarted.resume_verified(self.route,self.manager,tid)
        self.review(restarted,resumed,self.nw)
        self.assertEqual(restarted.resume_verified(self.route,self.manager,tid),resumed)
        self.assertEqual(len(restarted.status(resumed)['continuity_history']),1)
        self.assertEqual(restarted.status(resumed)['status'],'REVIEW_ACCEPTED')
    def test_no_business_goal_redispatch_after_resume(self):
        tid = self.commit(); restarted = self.restarted()
        resumed = restarted.resume_verified(self.route,self.manager,tid)
        count = len(self.ports[self.nw.endpoint_id].sent)
        with self.assertRaisesRegex(CandidateError,'DOES_NOT_REDISPATCH'):
            restarted.dispatch_goal(resumed,self.payload)
        self.assertEqual(len(self.ports[self.nw.endpoint_id].sent),count)
    def test_wrong_progress_checkpoint_cannot_overwrite_business_state(self):
        self.packet = replace(self.packet,artifact_sha256='f'*64)
        with self.assertRaisesRegex(CandidateError,'PROGRESS_CONFLICT'):
            self.commit()
        self.manager.observe_channel(self.old)
        with self.h.journal.locked() as life:
            self.assertEqual(life['registrations'][registration_key(self.old)]['channel']['reviewer'],asdict(self.old.reviewer))
        restarted = self.coordinator
        with restarted.locked() as state:
            self.assertEqual(state['tasks'][self.route.task_id]['route_digest'],self.route.route_digest)
    def test_uncommitted_transition_never_migrates(self):
        tid = self.manager.propose(self.old,self.new,self.packet,self.drain)
        with self.assertRaisesRegex(CandidateError,'COMMITTED_CONTINUITY_REQUIRED'):
            self.restarted().resume_verified(self.route,self.manager,tid)
    def test_unknown_old_business_delivery_cannot_be_bypassed(self):
        self.ports[self.h.peer.endpoint_id].fail = True
        with self.assertRaises(CandidateError):
            self.coordinator.connection(self.route,self.route.review_binding()).send(message_id='OLD_PENDING',
                source=self.h.origin.endpoint_id,target=self.h.peer.endpoint_id,payload=b'synthetic review input')
        with self.assertRaisesRegex(CandidateError,'DELIVERY_UNCONFIRMED'):
            self.commit()
        with self.h.journal.locked() as life:
            self.assertEqual(life['registrations'][registration_key(self.old)]['channel']['reviewer'],asdict(self.old.reviewer))
    def test_web_successor_wrong_topic_stops_cutover(self):
        self.h.catalog = replace(self.h.catalog,chats=tuple(replace(c,title='B事情') if c.endpoint==self.nw else c for c in self.h.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'SUCCESSOR_TOPIC_CHANGED'):
            self.manager.propose(self.old,self.new,self.packet,self.drain)
    def test_current_return_cannot_be_arbitrary_projectless_chat(self):
        e = Endpoint('OTHER_ORIGIN','OTHER_ACTOR','test://other-origin')
        self.h.catalog = replace(self.h.catalog,chats=self.h.catalog.chats+(Chat('OTHER_ORIGIN',None,e,'idle','A事情'),))
        with self.assertRaisesRegex(CandidateError,'FOLLOW_VERIFIED_EXECUTOR'):
            self.manager.propose(self.old,self.new,self.packet,self.drain,new_origin=e)

    def test_cached_old_review_sender_cannot_bypass_adoption_freeze(self):
        connection=self.coordinator.connection(self.route,self.route.review_binding())
        before=len(self.ports[self.h.peer.endpoint_id].sent)
        self.commit()
        with self.assertRaisesRegex(CandidateError,'ADOPTION_PENDING'):
            connection.send(message_id='OLD_REVIEW',source=self.h.origin.endpoint_id,target=self.h.peer.endpoint_id,payload=b'old-review')
        self.assertEqual(len(self.ports[self.h.peer.endpoint_id].sent),before)

    def test_committed_adoption_freezes_old_business_until_resume(self):
        tid=self.commit()
        with self.assertRaisesRegex(CandidateError,'ADOPTION_PENDING'):
            self.coordinator.return_result(self.route,version='V1',artifact_sha256='2'*64,message_id='OLD_RETURN',payload=b'result')
        with self.assertRaisesRegex(CandidateError,'ADOPTION_PENDING'):
            self.coordinator.set_artifact(self.route,'V1','2'*64)
        self.assertEqual(self.coordinator.status(self.route)['artifact']['version'],'V1')
        restarted=self.restarted();resumed=restarted.resume_verified(self.route,self.manager,tid)
        self.review(restarted,resumed,self.nw)
        self.assertEqual(restarted.status(resumed)['status'],'REVIEW_ACCEPTED')
    def test_legacy_project_registration_does_not_override_current_mirror_return(self):
        # Keep a distinct legacy row under the same logical project to test exact-key selection.
        with self.h.journal.locked() as state:
            state['registrations']['PROGRAM']={'channel':{'legacy':True},'history':[], 'returns':{}}
            self.h.journal.store.save(state)
        tid=self.commit();restarted=self.restarted()
        resumed=restarted.resume_verified(self.route,self.manager,tid)
        self.assertEqual(resumed.origin,self.h.origin)

    def test_same_current_entry_after_rollover_uses_new_web(self):
        tid = self.commit(); restarted = self.restarted()
        resumed = restarted.resume_verified(self.route,self.manager,tid)
        ch = self.h.ensure()
        self.assertEqual(ch,self.new)
        self.assertEqual(TaskCoordinator(self.h.mirror.router(self.h.proof,ch),self.registry,self.h.root/'business').prepare(
            Mock(current_invocation=lambda:self.h.invocation)),resumed)
    def test_rework_after_rollover_can_submit_new_version(self):
        with self.coordinator.locked() as state:
            state['tasks'][self.route.task_id]['status']='REWORK_REQUIRED'
            self.coordinator.store.save(state)
        self.packet=replace(self.packet,status='REWORK_REQUIRED')
        tid=self.commit(); restarted=self.restarted()
        resumed=restarted.resume_verified(self.route,self.manager,tid)
        restarted.set_artifact(resumed,'V2','f'*64)
        self.assertEqual(restarted.status(resumed)['artifact']['version'],'V2')
    def test_crash_between_commit_and_business_resume_recovers_same_adoption(self):
        tid=self.commit()
        self.coordinator.commit_verified(self.route,self.manager,tid,self.drain)
        restarted=self.restarted(); resumed=restarted.resume_verified(self.route,self.manager,tid)
        self.assertEqual(restarted.status(resumed)['adoption_transition_id'],tid)
    def test_topic_drift_after_proof_prevents_commit(self):
        tid=self.manager.propose(self.old,self.new,self.packet,self.drain)
        self.h.catalog=replace(self.h.catalog,chats=tuple(replace(c,title='B事情') if c.endpoint==self.nw else c for c in self.h.catalog.chats))
        with self.assertRaisesRegex(CandidateError,'SUCCESSOR_TOPIC_CHANGED'):
            self.coordinator.commit_verified(self.route,self.manager,tid,self.drain)
    def test_actual_fake_creation_then_online_handoff_and_business_return(self):
        # Remove the hand-built successor: exercise the actual official-callback chain.
        h=self.h;h.catalog=replace(h.catalog,chats=tuple(c for c in h.catalog.chats if c.endpoint!=self.nw))
        calls=[]
        def create(op,project,title,sha):
            calls.append(op); chat=Chat('NEW_WEB_A',project,self.nw,'idle',title)
            h.catalog=replace(h.catalog,chats=h.catalog.chats+(chat,))
            return CreationProof(op,'SIM_NATIVE_NEW',chat,'test://synthetic-create')
        h.port.topic_chat_callback=create
        life=ProjectLifecycle(h.journal,h.cp,h.port,clock=lambda:h.now)
        drain=self.drain
        class Drain:
            def proof(self,ch):return drain
            @contextmanager
            def fenced(self,ch):yield drain
        online=OnlineContinuity(self.manager,{h.web_project:life},self.transport,Drain(),clock=lambda:h.now)
        signal=ContextSignal(self.old.reviewer,'OWNER_HANDOFF',h.now,'test://explicit-handoff')
        prepared=online.prepare_on_signal(self.old,self.packet,(signal,))
        self.new=current_channel(prepared['channel']);tid=prepared['transition_id']
        self.assertEqual(len(calls),1)
        self.assertEqual(online.prepare_on_signal(self.old,self.packet,(signal,))['transition_id'],tid)
        self.assertEqual(len(calls),1)
        online.send_checkpoint(tid,self.packet)
        reads=tuple(HandoffRead(self.packet.task_id,self.packet.packet_sha256,e,'V1','2'*64,'3'*64,
            e.endpoint_id+'_I',e.endpoint_id+'_T',e.endpoint_id+'_O','test://synthetic-read') for e in (self.new.executor,self.new.reviewer))
        online.complete_candidate(tid,self.packet,reads,business_coordinator=self.coordinator,old_route=self.route)
        restarted=self.restarted();resumed=restarted.resume_verified(self.route,self.manager,tid)
        self.assertEqual(h.ensure(),self.new)
        self.review(restarted,resumed,self.nw)
        result=restarted.return_result(resumed,version='V1',artifact_sha256='2'*64,message_id='RESULT',payload=b'synthetic-result')
        self.assertEqual(result['dispatch'],'CURRENT_EXECUTOR_MUST_REPLY_IN_PLACE')


class LegacyCoordinatorReturnTests(unittest.TestCase):
    def test_original_entry_rollover_delivers_result_to_verified_new_page_once(self):
        h = continuity_fixtures.LifecycleTests('test_origin_replaced_and_original_identity_preserved')
        h.setUp()
        try:
            for endpoint in (h.o,h.no):h.registry.register(continuity_fixtures.FakeChatPort(endpoint))
            old = TaskCoordinator(ProjectRouter(h.cp,(h.old,),clock=lambda:h.now),h.registry,h.root/'business')
            invocation = Invocation(h.packet.task_id,h.packet.request_sha256,h.o,h.packet.owner_trigger_ref,True)
            route = old.prepare(Mock(current_invocation=lambda:invocation))
            old.set_artifact(route,'V3','2'*64)
            review = ReviewObservation(route.route_digest,route.task_id,h.w,'V3','2'*64,'PASS',
                'OLD_TURN','OLD_OUTPUT','test://synthetic-review','4'*64)
            old.observe_review(route,Mock(observe_review=lambda r:review))
            h.packet = replace(h.packet,status='REVIEW_ACCEPTED')
            tid = h.proposal(new_origin=h.no);h.proven(tid);h.manager.commit_candidate(tid,h.drain)
            resumed_coordinator = TaskCoordinator(ProjectRouter(h.cp,(h.new,),clock=lambda:h.now),h.registry,h.root/'business')
            resumed = resumed_coordinator.resume_verified(route,h.manager,tid)
            self.assertEqual(resumed.origin,h.no)
            proof = replace(review,route_digest=resumed.route_digest,endpoint=h.nw,native_turn_id='NEW_TURN',native_output_id='NEW_OUTPUT')
            resumed_coordinator.observe_review(resumed,Mock(observe_review=lambda r:proof))
            args=dict(version='V3',artifact_sha256='2'*64,message_id='FINAL_RESULT',payload='模拟结果'.encode())
            resumed_coordinator.return_result(resumed,**args)
            restarted = TaskCoordinator(resumed_coordinator.router,h.registry,h.root/'business')
            restarted.return_result(resumed,**args)
            self.assertEqual(h.registry.resolve(h.no).sent,[args['payload']])
            self.assertEqual(h.registry.resolve(h.o).sent,[])
            self.assertEqual(restarted.status(resumed)['original_origin'],asdict(h.o))
        finally:
            h.tearDown()

if __name__=='__main__':unittest.main()
