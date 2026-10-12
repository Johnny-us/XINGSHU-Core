"""当前窗口入口、Web 主题镜像与不确定创建保护。全部为合成资料。"""
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock
import sys
import tempfile
import unittest
sys.dont_write_bytecode = True
from xingshu_collaboration.router.contracts import Catalog, Project, ProjectRef, Chat, Invocation
from xingshu_collaboration.router.current_chat import CurrentChatProof, CurrentChatMirror
from xingshu_collaboration.router.lifecycle import ProviderScope, LifecycleJournal, CreationProof
from xingshu_collaboration.router.host_lifecycle import OfficialHostLifecyclePort
from xingshu_collaboration.router.coordinator import TaskCoordinator, ReviewObservation
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.connections.ports import PortRegistry
from xingshu_collaboration.binding import CandidateError


class CurrentChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'candidate'
        self.now = 1000.0
        self.source = ProviderScope('APP_A', 'OWNER', 'LOCAL')
        self.target = ProviderScope('APP_B', 'OWNER', 'CLOUD')
        self.origin = Endpoint('CURRENT_A', 'A_ACTOR', 'test://current-a')
        self.peer = Endpoint('WEB_A', 'W_ACTOR', 'test://web-a')
        self.web_project = ProjectRef('APP_B', 'WEB_PROJECT', 'OWNER', 'CLOUD')
        self.catalog = Catalog((Project(self.web_project, '栏目'),),
            (Chat('CURRENT_A',None,self.origin,'active','A事情'),), 'test://catalog', self.now)
        self.cp = Mock(snapshot=lambda:self.catalog)
        self.invocation = Invocation('TASK_A','1'*64,self.origin,'test://direct-human-request',True)
        self.proof = CurrentChatProof(self.invocation,self.source,None,'PROGRAM','栏目','A事情',
                                      self.now,'test://current-host-proof')
        self.calls = []; self.project_calls = []; self.rename_calls = []
        self.journal = LifecycleJournal(self.root)
        self.port = OfficialHostLifecyclePort(self.target,implementation='OFFICIAL_TOOL',
            create_project=self.create_project,rename_project=self.rename,create_topic_chat=self.create_chat)
        self.mirror = CurrentChatMirror(self.journal,self.cp,self.port,clock=lambda:self.now)
    def tearDown(self):
        self.tmp.cleanup()
    def create_chat(self,op,project,name,sha):
        self.calls.append((op,project,name,sha))
        chat = Chat('WEB_A',project,self.peer,'idle',name)
        self.catalog = replace(self.catalog,chats=self.catalog.chats+(chat,))
        self.creation = CreationProof(op,'WEB_CREATED',chat,'test://native-create')
        if getattr(self,'uncertain',False):
            raise TimeoutError('created response lost')
        return self.creation
    def create_project(self,op,scope,name):
        self.project_calls.append(op)
        p = Project(ProjectRef(scope.provider,'NEW_PROJECT',scope.account_scope,scope.host_id),name)
        self.catalog = replace(self.catalog,projects=self.catalog.projects+(p,))
        return CreationProof(op,'PROJECT_CREATED',p,'test://native-project')
    def rename(self,op,project,name):
        self.rename_calls.append(op)
        p = Project(project,name)
        self.catalog = replace(self.catalog,projects=tuple(p if x.ref==project else x for x in self.catalog.projects))
        return CreationProof(op,'PROJECT_RENAMED',p,'test://native-rename')
    def ensure(self):
        return self.mirror.ensure(self.proof,target_project=self.web_project)
    def test_projectless_current_window_is_executor_and_return(self):
        ch = self.ensure(); route = self.mirror.router(self.proof,ch).plan(Mock(current_invocation=lambda:self.invocation))
        self.assertEqual(route.origin,self.origin); self.assertEqual(ch.executor,self.origin)
        self.assertIsNone(route.origin_project); self.assertIsNone(route.ingress_binding())
        self.assertIsNone(route.return_binding()); self.assertEqual(ch.reviewer,self.peer)
        self.assertEqual(self.calls[0][2],'A事情')
    def test_no_current_codex_project_or_chat_created(self):
        self.ensure()
        self.assertEqual(len(self.catalog.projects),1)
        self.assertEqual(self.catalog.chats[0].project,None)
        self.assertEqual(len(self.project_calls),0); self.assertEqual(len(self.calls),1)
    def test_same_intent_after_restart_does_not_recreate(self):
        ch = self.ensure()
        restarted = CurrentChatMirror(LifecycleJournal(self.root),self.cp,self.port,clock=lambda:self.now)
        self.assertEqual(restarted.ensure(self.proof,target_project=self.web_project),ch)
        self.assertEqual(len(self.calls),1)
    def test_changed_request_cannot_take_over_same_task(self):
        self.ensure(); changed = replace(self.proof,invocation=replace(self.invocation,request_sha256='2'*64))
        with self.assertRaisesRegex(CandidateError,'INTENT_CHANGED'):
            self.mirror.ensure(changed,target_project=self.web_project)
        self.assertEqual(len(self.calls),1)
    def test_no_trusted_proof_does_not_create(self):
        with self.assertRaises(CandidateError):self.mirror.ensure({'authorized':True})
        self.assertFalse(self.calls)
    def test_unauthorized_current_invocation_stops(self):
        p = replace(self.proof,invocation=replace(self.invocation,authorized=False))
        with self.assertRaises(CandidateError):self.mirror.ensure(p,target_project=self.web_project)
        self.assertFalse(self.calls)
    def test_stale_current_observation_stops(self):
        with self.assertRaisesRegex(CandidateError,'STALE'):
            self.mirror.ensure(replace(self.proof,observed_at=1),target_project=self.web_project)
        self.assertFalse(self.calls)
    def test_current_membership_changed_stops(self):
        p = ProjectRef('APP_A','UNRELATED','OWNER','LOCAL')
        self.catalog = replace(self.catalog,projects=self.catalog.projects+(Project(p,'OTHER'),),
            chats=(replace(self.catalog.chats[0],project=p),))
        with self.assertRaisesRegex(CandidateError,'PROJECT_CHANGED'):self.ensure()
        self.assertFalse(self.calls)
    def test_wrong_current_topic_stops(self):
        with self.assertRaisesRegex(CandidateError,'TOPIC_CHANGED'):
            self.mirror.ensure(replace(self.proof,topic_name='B事情'),target_project=self.web_project)
        self.assertFalse(self.calls)
    def test_wrong_web_account_stops(self):
        p = ProjectRef('APP_B','WEB_PROJECT','OTHER','CLOUD')
        with self.assertRaisesRegex(CandidateError,'SCOPE_CONFLICT'):
            self.mirror.ensure(self.proof,target_project=p)
        self.assertFalse(self.calls)
    def test_unregistered_same_name_never_guessed(self):
        with self.assertRaisesRegex(CandidateError,'SAME_NAME'):
            self.mirror.ensure(self.proof)
        self.assertFalse(self.calls); self.assertFalse(self.project_calls)
    def test_missing_web_project_created_and_repeated_once(self):
        self.catalog = replace(self.catalog,projects=())
        ch = self.mirror.ensure(self.proof)
        self.assertEqual(ch.projects[1].project_id,'NEW_PROJECT')
        self.assertEqual(self.mirror.ensure(self.proof),ch)
        self.assertEqual(len(self.project_calls),1); self.assertEqual(len(self.calls),1)
    def test_web_project_rename_preserves_id(self):
        self.catalog = replace(self.catalog,projects=(Project(self.web_project,'OLD'),))
        ch = self.ensure(); self.assertEqual(ch.projects[1],self.web_project)
        self.assertEqual(len(self.rename_calls),1)
    def test_unsupported_rename_preserves_project_and_stops(self):
        self.catalog = replace(self.catalog,projects=(Project(self.web_project,'OLD'),))
        self.port.rename_callback = None
        with self.assertRaisesRegex(CandidateError,'RENAME_UNAVAILABLE'):self.ensure()
        self.assertFalse(self.calls); self.assertEqual(self.catalog.projects[0].name,'OLD')
    def test_unsupported_chat_no_creation_intent(self):
        self.port.topic_chat_callback = None
        with self.assertRaisesRegex(CandidateError,'CHAT_CREATE_UNAVAILABLE'):self.ensure()
        with self.journal.locked() as state:self.assertFalse(state['operations'])
    def test_uncertain_creation_survives_restart_no_resend(self):
        self.uncertain = True
        with self.assertRaises(TimeoutError):self.ensure()
        self.mirror = CurrentChatMirror(LifecycleJournal(self.root),self.cp,self.port,clock=lambda:self.now)
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'):self.ensure()
        self.assertEqual(len(self.calls),1)
        self.mirror.lifecycle.reconcile_creation(self.creation.operation_id,self.creation)
        self.ensure(); self.assertEqual(len(self.calls),1)
    def test_native_wrong_title_rejected_and_not_recreated(self):
        original = self.port.topic_chat_callback
        def wrong(op,p,t,s):
            proof = original(op,p,'B事情',s)
            return proof
        self.port.topic_chat_callback = wrong
        with self.assertRaisesRegex(CandidateError,'TITLE_READBACK_CONFLICT'):self.ensure()
        with self.assertRaisesRegex(CandidateError,'UNCONFIRMED'):self.ensure()
        self.assertEqual(len(self.calls),1)
    def test_web_topic_changed_after_creation_stops(self):
        self.ensure()
        self.catalog = replace(self.catalog,chats=tuple(replace(c,title='B事情') if c.endpoint==self.peer else c for c in self.catalog.chats))
        with self.assertRaises(CandidateError):self.ensure()
        self.assertEqual(len(self.calls),1)
    def test_web_membership_changed_stops(self):
        self.ensure()
        self.catalog = replace(self.catalog,chats=tuple(replace(c,project=None) if c.endpoint==self.peer else c for c in self.catalog.chats))
        with self.assertRaises(CandidateError):self.ensure()
    def test_current_invocation_not_replaced_by_another_chat(self):
        ch = self.ensure(); router = self.mirror.router(self.proof,ch)
        other = replace(self.invocation,origin=self.peer)
        with self.assertRaisesRegex(CandidateError,'INVOCATION_CONFLICT'):
            router.plan(Mock(current_invocation=lambda:other))
    def test_current_business_result_replies_in_place_with_progress_saved(self):
        ch = self.ensure(); router = self.mirror.router(self.proof,ch)
        coordinator = TaskCoordinator(router,PortRegistry(),self.root/'business')
        route = coordinator.prepare(Mock(current_invocation=lambda:self.invocation))
        coordinator.set_artifact(route,'V1','2'*64)
        proof = ReviewObservation(route.route_digest,route.task_id,self.peer,'V1','2'*64,'PASS',
            'SIM_TURN','SIM_OUTPUT','test://simulated-review','3'*64)
        coordinator.observe_review(route,Mock(observe_review=lambda r:proof))
        result = coordinator.return_result(route,version='V1',artifact_sha256='2'*64,
            message_id='RESULT_A',payload='模拟结果'.encode())
        self.assertEqual(result['dispatch'],'CURRENT_EXECUTOR_MUST_REPLY_IN_PLACE')
        restarted = TaskCoordinator(router,PortRegistry(),self.root/'business')
        self.assertEqual(restarted.status(route)['status'],'RETURN_PREPARED')
        with self.assertRaisesRegex(CandidateError,'PAYLOAD_CONFLICT'):
            restarted.return_result(route,version='V1',artifact_sha256='2'*64,
                message_id='OTHER',payload='模拟结果'.encode())

    def test_next_task_same_window_reuses_same_web_window(self):
        original=self.ensure()
        new=replace(self.proof,invocation=replace(self.invocation,task_id='TASK_B',request_sha256='b'*64))
        self.assertEqual(self.mirror.ensure(new,target_project=self.web_project),original)
        self.assertEqual(len(self.calls),1)
    def test_two_current_windows_same_project_have_independent_continuity(self):
        from xingshu_collaboration.router.continuity import ContinuityManager, registration_key
        a=self.ensure()
        other=Endpoint('CURRENT_B','B_ACTOR','test://current-b')
        self.catalog=replace(self.catalog,chats=self.catalog.chats+(Chat('CURRENT_B',None,other,'active','B事情'),))
        p=replace(self.proof,invocation=replace(self.invocation,task_id='TASK_B',origin=other),topic_name='B事情')
        def create(op,project,name,sha):
            endpoint=Endpoint('WEB_B','WB_ACTOR','test://web-b')
            chat=Chat('WEB_B',project,endpoint,'idle',name)
            self.catalog=replace(self.catalog,chats=self.catalog.chats+(chat,))
            return CreationProof(op,'NATIVE_B',chat,'test://creation-b')
        self.port.topic_chat_callback=create
        b=self.mirror.ensure(p,target_project=self.web_project)
        manager=ContinuityManager(self.journal,self.cp,clock=lambda:self.now)
        manager.seed_candidate(a);manager.seed_candidate(b)
        self.assertNotEqual(registration_key(a),registration_key(b))


if __name__=='__main__':unittest.main()
