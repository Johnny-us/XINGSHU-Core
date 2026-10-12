"""项目误认、作用域变化、重复、中断、精确复核和返回原窗口的隔离验收。"""
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import hashlib
import json
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
from xingshu_collaboration.connections.contracts import Endpoint, Capabilities, Observation, Submission
from xingshu_collaboration.connections.ports import PortRegistry
from xingshu_collaboration.state import SnapshotStore
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.router.contracts import Catalog, Chat, Invocation, Project, ProjectChannel, ProjectRef
from xingshu_collaboration.router.router import ProjectRouter
from xingshu_collaboration.router.coordinator import ReviewObservation, TaskCoordinator
from xingshu_collaboration.router.mirror import ProjectCapabilities, mirror_report
from xingshu_collaboration.router.codex_app_catalog import CodexAppCatalog


class FakePort:
    def __init__(self, endpoint):
        self.endpoint, self.sent, self.fail = endpoint, [], False
    def capabilities(self): return Capabilities('ISOLATED_TEST', True, True)
    def preflight(self): pass
    def checkpoint(self): return 'BASELINE'
    def submit(self, payload, deadline):
        self.sent.append(payload)
        if self.fail: raise TimeoutError('isolated uncertain submission')
        return Submission(self.endpoint, 'INPUT_' + str(len(self.sent)), 'test://submit')
    def observe(self, checkpoint, submission, payload, deadline):
        return Observation(self.endpoint, payload, 'test://read', submission.native_id)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'state'
        self.p1 = ProjectRef('APP_A', 'PROJECT_1', 'OWNER', 'HOST')
        self.p2 = ProjectRef('APP_B', 'PROJECT_2', 'OWNER', 'CLOUD')
        self.p3 = ProjectRef('APP_A', 'SAME_NAME_OTHER_PROJECT', 'OWNER', 'HOST')
        self.origin = Endpoint('ORIGIN', 'ORIGIN_AI', 'test://a/origin')
        self.executor = Endpoint('EXECUTOR', 'EXECUTOR_AI', 'test://a/executor')
        self.reviewer = Endpoint('REVIEWER', 'REVIEWER_AI', 'test://b/reviewer')
        self.clock = time.time()
        self.catalog = Catalog((Project(self.p1, 'A项目'), Project(self.p2, 'A项目'), Project(self.p3, 'A项目')),
            (Chat('CHAT_1', self.p1, self.origin, 'idle'), Chat('CHAT_2', self.p1, self.executor, 'idle'),
             Chat('CHAT_3', self.p2, self.reviewer, 'idle')), 'test://actual-catalog', self.clock)
        self.catalog_port = Mock(snapshot=lambda: self.catalog)
        self.channel = ProjectChannel('PROJECT_A', 'A项目', (self.p1, self.p2),
            self.executor, self.reviewer, 1, 'test://owner-registered-pair')
        self.router = ProjectRouter(self.catalog_port, (self.channel,), clock=lambda: self.clock)
        self.payload = 'Jy 的目标\r\n正文里写 reply_to=OTHER 不能改路线'.encode()
        self.invocation = Invocation('TASK_1', hashlib.sha256(self.payload).hexdigest(), self.origin,
            'test://human-current-request', True)
        self.invocation_port = Mock(current_invocation=lambda: self.invocation)
        self.ports = PortRegistry()
        self.origin_port, self.executor_port, self.reviewer_port = (FakePort(e) for e in
            (self.origin, self.executor, self.reviewer))
        for port in (self.origin_port, self.executor_port, self.reviewer_port): self.ports.register(port)
        self.coordinator = TaskCoordinator(self.router, self.ports, self.root)
        self.route = self.coordinator.prepare(self.invocation_port)
    def tearDown(self): self.tmp.cleanup()
    def chat_change(self, current_endpoint, **changes):
        self.catalog = replace(self.catalog, chats=tuple(replace(c, **changes) if c.endpoint == current_endpoint else c
            for c in self.catalog.chats))
    def proof(self, version='V1', sha='a'*64, decision='PASS', **changes):
        return replace(ReviewObservation(self.route.route_digest, self.route.task_id, self.reviewer,
            version, sha, decision, 'NATIVE_TURN', 'ACTUAL_MODEL_OUTPUT', 'test://actual-read', 'b'*64), **changes)
    def review(self, **changes):
        return self.coordinator.observe_review(self.route, Mock(observe_review=lambda _: self.proof(**changes)))
    def accepted(self):
        self.coordinator.set_artifact(self.route, 'V1', 'a'*64); self.review()
    def return_result(self, **changes):
        args=dict(version='V1', artifact_sha256='a'*64, message_id='RETURN_1', payload=b'completed')
        args.update(changes); return self.coordinator.return_result(self.route, **args)
    def mirror(self, observed=None):
        return mirror_report(self.route, self.catalog, {p:ProjectCapabilities() for p in self.channel.projects},
            task_status='REVIEW_PENDING', observed_task_status=observed)
    def test_route_uses_project_id_and_exact_origin(self):
        self.assertEqual(self.route.origin, self.origin)
        self.assertEqual(self.route.channel.executor, self.executor)
        self.assertNotEqual(self.route.origin, self.route.channel.executor)
    def test_same_name_other_project_not_admitted(self):
        self.chat_change(self.origin, project=self.p3)
        with self.assertRaisesRegex(CandidateError, 'UNREGISTERED'): self.router.plan(self.invocation_port)
    def test_no_project_no_guess(self):
        self.chat_change(self.origin, project=None)
        with self.assertRaisesRegex(CandidateError, 'PROJECTLESS'): self.router.plan(self.invocation_port)
    def test_account_scope_not_inherited(self):
        other=replace(self.p1, account_scope='OTHER_OWNER')
        self.catalog=replace(self.catalog, projects=self.catalog.projects+(Project(other,'A项目'),))
        self.chat_change(self.origin, project=other)
        with self.assertRaisesRegex(CandidateError, 'UNREGISTERED'): self.router.plan(self.invocation_port)
    def test_same_project_host_change_not_inherited(self):
        other=replace(self.p1, host_id='OTHER_HOST')
        self.catalog=replace(self.catalog, projects=self.catalog.projects+(Project(other,'A项目'),))
        self.chat_change(self.origin, project=other)
        with self.assertRaisesRegex(CandidateError, 'UNREGISTERED'): self.router.plan(self.invocation_port)
    def test_ambiguous_channel_stops(self):
        router=ProjectRouter(self.catalog_port,(self.channel,replace(self.channel, logical_project_id='SECOND')),
                             clock=lambda:self.clock)
        with self.assertRaisesRegex(CandidateError,'AMBIGUOUS'):router.plan(self.invocation_port)
    def test_new_chat_in_same_project_keeps_its_return_address(self):
        other=Endpoint('NEW_CHAT','NEW_AI','test://a/new')
        self.catalog=replace(self.catalog,chats=self.catalog.chats+(Chat('NEW',self.p1,other,'idle'),))
        self.invocation=replace(self.invocation,task_id='TASK_2',origin=other)
        route=self.coordinator.prepare(self.invocation_port)
        self.assertEqual(route.return_binding().endpoint_for('NEW_CHAT'),other)
        self.assertEqual(route.channel,self.channel)
    def test_peer_project_origin_uses_same_registered_executor(self):
        self.invocation=replace(self.invocation, origin=self.reviewer, task_id='WEB_TASK')
        route=self.coordinator.prepare(self.invocation_port)
        self.assertEqual(route.channel.executor,self.executor)
        self.assertEqual(route.origin,self.reviewer)
    def test_executor_origin_does_not_send_to_itself(self):
        self.invocation=replace(self.invocation,origin=self.executor,task_id='DIRECT')
        route=self.coordinator.prepare(self.invocation_port)
        self.assertIsNone(route.ingress_binding())
        result=self.coordinator.dispatch_goal(route,self.payload)
        self.assertFalse(result['host_delivery_verified']);self.assertFalse(self.executor_port.sent)
    def test_robot_notification_not_owner_trigger(self):
        self.invocation=replace(self.invocation,authorized=False)
        with self.assertRaisesRegex(CandidateError,'OWNER_STARTED'):self.router.plan(self.invocation_port)
    def test_stale_catalog_stops(self):
        self.catalog=replace(self.catalog,observed_at=self.clock-121)
        with self.assertRaisesRegex(CandidateError,'STALE'):self.router.plan(self.invocation_port)
    def test_future_catalog_stops(self):
        self.catalog=replace(self.catalog,observed_at=self.clock+1)
        with self.assertRaisesRegex(CandidateError,'FUTURE'):self.router.plan(self.invocation_port)
    def test_nonfinite_time_stops(self):
        self.catalog=replace(self.catalog,observed_at=float('nan'))
        with self.assertRaisesRegex(CandidateError,'STALE'):self.router.plan(self.invocation_port)
    def test_missing_reviewer_not_fallback(self):
        self.catalog=replace(self.catalog,chats=self.catalog.chats[:-1])
        with self.assertRaisesRegex(CandidateError,'NOT_OBSERVED'):self.router.plan(self.invocation_port)
    def test_reviewer_in_wrong_project_stops(self):
        self.chat_change(self.reviewer,project=self.p3)
        with self.assertRaisesRegex(CandidateError,'PROJECT_CONFLICT'):self.router.plan(self.invocation_port)
    def test_execution_and_review_projects_cannot_swap(self):
        self.chat_change(self.executor,project=self.p2)
        self.chat_change(self.reviewer,project=self.p1)
        with self.assertRaisesRegex(CandidateError,'PROJECT_CONFLICT'):self.router.plan(self.invocation_port)
    def test_membership_swap_during_task_stops(self):
        self.chat_change(self.executor,project=self.p2)
        self.chat_change(self.reviewer,project=self.p1)
        with self.assertRaisesRegex(CandidateError,'MEMBERSHIP_CHANGED'):self.router.validate_current(self.route)
    def test_changed_origin_membership_stops_return(self):
        self.accepted();self.chat_change(self.origin,project=self.p3)
        with self.assertRaisesRegex(CandidateError,'ORIGIN_PROJECT_CHANGED'):self.return_result()
        self.assertFalse(self.origin_port.sent)
    def test_endpoint_generation_change_stops(self):
        self.chat_change(self.origin,endpoint=replace(self.origin,generation=2))
        with self.assertRaisesRegex(CandidateError,'GENERATION_CHANGED'):self.router.validate_current(self.route)
    def test_changed_registration_stops(self):
        self.router.channels=(replace(self.channel,generation=2),)
        with self.assertRaisesRegex(CandidateError,'REGISTRATION_CHANGED'):self.router.validate_current(self.route)
    def test_goal_bytes_preserved_and_deduped(self):
        self.coordinator.dispatch_goal(self.route,self.payload)
        self.coordinator.dispatch_goal(self.route,self.payload)
        self.assertEqual(self.executor_port.sent,[self.payload])
        self.assertFalse(self.reviewer_port.sent)
    def test_goal_body_cannot_change_request(self):
        with self.assertRaisesRegex(CandidateError,'GOAL_BYTES'):self.coordinator.dispatch_goal(self.route,b'other')
        self.assertFalse(self.executor_port.sent)
    def test_busy_executor_stops_before_send(self):
        self.chat_change(self.executor,status='active')
        with self.assertRaisesRegex(CandidateError,'HOST_NOT_READY'):self.coordinator.dispatch_goal(self.route,self.payload)
        self.assertFalse(self.executor_port.sent)
    def test_system_error_reviewer_stops(self):
        self.chat_change(self.reviewer,status='systemError')
        with self.assertRaisesRegex(CandidateError,'SYSTEMERROR'):self.router.require_ready(self.route,self.reviewer)
    def test_uncertain_goal_survives_restart_no_resend(self):
        self.executor_port.fail=True
        with self.assertRaises(CandidateError):self.coordinator.dispatch_goal(self.route,self.payload)
        restarted=TaskCoordinator(self.router,self.ports,self.root)
        route=restarted.prepare(self.invocation_port)
        with self.assertRaisesRegex(CandidateError,'UNCERTAIN'):restarted.dispatch_goal(route,self.payload)
        self.assertEqual(len(self.executor_port.sent),1)
    def test_duplicate_task_id_changed_origin_stops(self):
        self.invocation=replace(self.invocation,origin=self.executor)
        with self.assertRaisesRegex(CandidateError,'TASK_ID_OR_ORIGIN'):self.coordinator.prepare(self.invocation_port)
    def test_task_restart_keeps_same_route(self):
        coordinator=TaskCoordinator(self.router,self.ports,self.root)
        self.assertEqual(coordinator.prepare(self.invocation_port),self.route)
        self.assertEqual(len(coordinator.store.records()[0]),1)
    def test_unknown_destination_stops(self):
        with self.assertRaisesRegex(CandidateError,'DESTINATION_CONFLICT'):
            self.router.require_ready(self.route,Endpoint('OTHER','OTHER_AI','test://other'))
    def test_local_mirror_without_task_observation_not_applied(self):
        self.assertFalse(self.mirror()['applied_verified'])
        self.assertEqual(self.mirror()['desired'][0]['rename_support'],'unsupported')
    def test_exact_observed_name_membership_status_matches(self):
        report=self.mirror({self.p1:'REVIEW_PENDING',self.p2:'REVIEW_PENDING'})
        self.assertTrue(report['applied_verified']);self.assertFalse(report['writes_performed'])
    def test_name_mismatch_not_hidden_by_binding(self):
        self.catalog=replace(self.catalog,projects=tuple(replace(p,name='不同名称') if p.ref==self.p2 else p
            for p in self.catalog.projects))
        self.assertFalse(self.mirror({self.p1:'REVIEW_PENDING',self.p2:'REVIEW_PENDING'})['applied_verified'])
    def test_wrong_version_review_cannot_complete(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        with self.assertRaisesRegex(CandidateError,'REVIEW_OBSERVATION'):self.review(version='V0')
    def test_wrong_artifact_review_cannot_complete(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        with self.assertRaisesRegex(CandidateError,'REVIEW_OBSERVATION'):self.review(sha='c'*64)
    def test_origin_cannot_approve_its_own_independent_review(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        with self.assertRaisesRegex(CandidateError,'REVIEW_OBSERVATION'):self.review(endpoint=self.origin)
    def test_host_acceptance_without_model_output_cannot_review(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        with self.assertRaisesRegex(CandidateError,'REVIEW_OBSERVATION'):self.review(native_output_id='')
    def test_old_task_proof_cannot_be_reused(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        with self.assertRaisesRegex(CandidateError,'REVIEW_OBSERVATION'):self.review(task_id='OLD_TASK')
    def test_rework_requires_new_version_and_new_review(self):
        self.coordinator.set_artifact(self.route,'V1','a'*64)
        self.assertEqual(self.review(decision='REQUEST_CHANGES'),'REWORK_REQUIRED')
        with self.assertRaisesRegex(CandidateError,'SAME_VERSION'):self.coordinator.set_artifact(self.route,'V1','c'*64)
        self.coordinator.set_artifact(self.route,'V2','c'*64)
        with self.assertRaisesRegex(CandidateError,'EXACT_VERSION_REVIEW'):self.return_result(version='V2',artifact_sha256='c'*64)
        self.review(version='V2',sha='c'*64)
        self.assertTrue(self.return_result(version='V2',artifact_sha256='c'*64)['result']['delivered'])
    def test_result_returns_exactly_to_origin(self):
        self.accepted();self.return_result()
        self.assertEqual(self.origin_port.sent,[b'completed'])
        self.assertFalse(self.executor_port.sent);self.assertFalse(self.reviewer_port.sent)
        self.assertEqual(self.coordinator.status(self.route)['status'],'RETURN_INPUT_OBSERVED')
    def test_repeat_return_same_message_no_second_submit(self):
        self.accepted();self.return_result();self.assertTrue(self.return_result()['result']['duplicate'])
        self.assertEqual(len(self.origin_port.sent),1)
    def test_uncertain_return_cannot_change_id_or_retry_after_restart(self):
        self.accepted();self.origin_port.fail=True
        with self.assertRaises(CandidateError):self.return_result()
        self.coordinator=TaskCoordinator(self.router,self.ports,self.root)
        with self.assertRaisesRegex(CandidateError,'RETURN_ID_OR_PAYLOAD'):self.return_result(message_id='RETURN_2')
        with self.assertRaisesRegex(CandidateError,'UNCERTAIN'):self.return_result()
        self.assertEqual(len(self.origin_port.sent),1)
    def test_return_changed_payload_not_replayed(self):
        self.accepted();self.return_result()
        with self.assertRaisesRegex(CandidateError,'RETURN_ID_OR_PAYLOAD'):self.return_result(payload=b'changed')
    def test_return_before_review_stops(self):
        with self.assertRaisesRegex(CandidateError,'EXACT_VERSION_REVIEW'):self.return_result()
    def test_reserved_goal_id_cannot_be_used_for_return(self):
        self.accepted()
        with self.assertRaisesRegex(CandidateError,'RETURN_MESSAGE_INVALID'):self.return_result(message_id='GOAL_COLLISION')
        self.assertIsNone(self.coordinator.status(self.route)['return_message_id'])
    def test_non_utf8_return_stops_before_saving_return_id(self):
        self.accepted()
        with self.assertRaisesRegex(CandidateError,'UTF8'):self.return_result(payload=b'\xff')
        self.assertIsNone(self.coordinator.status(self.route)['return_message_id'])
    def test_task_journal_contains_no_message_body(self):
        self.coordinator.dispatch_goal(self.route,self.payload)
        self.assertNotIn(self.payload.decode(),json.dumps(self.coordinator.store.load()))
        self.assertNotIn(self.payload.decode(),''.join(p.read_text() for p in (self.root/'delivery').rglob('snapshot-*.json')))
    def test_task_journal_tamper_stops(self):
        snapshot=next((self.root/'tasks').glob('*.json'));snapshot.write_text('{}')
        with self.assertRaisesRegex(CandidateError,'CHECKPOINT_SCHEMA'):self.coordinator.prepare(self.invocation_port)


class NativeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.chat_id='11111111-2222-4333-8444-555555555555'
        self.projects={'projects':[{'projectId':'LOCAL','projectKind':'local','label':'星枢','hostId':'local'}]}
        self.threads={'pinnedThreads':[],'threads':[{'id':self.chat_id,'kind':'codex','projectId':'LOCAL','hostId':'local','status':'idle'}]}
        self.calls=[]
        def call(method,args):
            self.calls.append((method,args));return {'content':[{'type':'text','text':json.dumps(self.projects if method=='list_projects' else self.threads)}]}
        self.call=call
        self.adapter=CodexAppCatalog(call,account_scope='OWNER')
    def test_only_metadata_tools_no_body_reads(self):
        catalog=self.adapter.snapshot()
        self.assertEqual([m for m,a in self.calls],['list_projects','list_threads'])
        self.assertEqual(catalog.chats[0].project.project_id,'LOCAL')
        self.assertFalse(self.adapter.capabilities().rename)
    def test_wrong_uri_override_rejected(self):
        self.adapter.endpoint_overrides={self.chat_id:Endpoint('X','Y','codex://threads/OTHER')}
        with self.assertRaisesRegex(CandidateError,'URI_IDENTITY'):self.adapter.snapshot()
    def test_partial_inventory_cannot_claim_all_chats(self):
        self.threads['unavailableSources']=['chatgpt']
        with self.assertRaisesRegex(CandidateError,'PARTIAL'):self.adapter.snapshot()
    def test_missing_project_membership_not_name_matched(self):
        self.threads['threads'][0]['projectId']='MISSING'
        with self.assertRaisesRegex(CandidateError,'PROJECT_NOT_OBSERVED'):self.adapter.snapshot()
    def test_duplicate_catalog_row_rejected(self):
        self.threads['pinnedThreads']=self.threads['threads']
        with self.assertRaisesRegex(CandidateError,'AMBIGUOUS'):self.adapter.snapshot()
    def test_wrong_provider_project_not_inherited(self):
        self.threads['threads'][0]['kind']='chatgpt'
        with self.assertRaisesRegex(CandidateError,'PROVIDER_OR_HOST'):self.adapter.snapshot()
    def test_tool_error_rejected(self):
        self.adapter.call=lambda *_:{'isError':True}
        with self.assertRaisesRegex(CandidateError,'REJECTED'):self.adapter.snapshot()


if __name__ == '__main__': unittest.main()
