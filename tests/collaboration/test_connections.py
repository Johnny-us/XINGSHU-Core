"""通用接口、旧链路兼容与不确定发送的隔离验收。"""
import base64
import dataclasses
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
import sys
sys.dont_write_bytecode = True
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.connections.contracts import (Endpoint, LinkBinding, Capabilities, Submission,
                                    Observation, ConsumptionObservation, normalized_result)
from xingshu_collaboration.connections.ports import PortRegistry, PortConnection
from xingshu_collaboration.connections.jsonrpc_port import JsonRpcHostPort
from xingshu_collaboration.connections.continuation import Continuations
from xingshu_collaboration.state import SnapshotStore

class FakePort:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.sent = []
        self.submission_override = None
        self.observation_override = None
        self.limit = 131072
        self.fail = False
    def capabilities(self): return Capabilities('TEST_HOST', True, True, maximum_payload_bytes=self.limit)
    def preflight(self): pass
    def checkpoint(self): return 'BASELINE'
    def submit(self, payload, deadline):
        self.sent.append(payload)
        if self.fail: raise TimeoutError('simulated lost acknowledgement')
        return self.submission_override or Submission(self.endpoint, 'S_1', 'test://submit/S_1')
    def observe(self, checkpoint, submission, payload, deadline):
        return self.observation_override or Observation(self.endpoint, payload, 'test://read/S_1', submission.native_id)

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'state'
        self.a = Endpoint('LOCAL_AGENT', 'ACTOR_A', 'test://application-a/chat')
        self.b = Endpoint('OTHER_APP', 'ACTOR_B', 'test://application-b/chat')
        self.binding = LinkBinding('TASK_1', (self.a, self.b))
        self.a_port, self.b_port = FakePort(self.a), FakePort(self.b)
        self.registry = PortRegistry()
        self.registry.register(self.a_port)
        self.registry.register(self.b_port)
        self.connection = PortConnection(self.binding, self.registry, self.root,
                                         project='example.project', relay_id='GENERIC_RELAY')
    def tearDown(self): self.tmp.cleanup()
    def send(self, payload=b'original\r\n', message_id='M_1', source='LOCAL_AGENT', target='OTHER_APP'):
        return self.connection.send(message_id=message_id, source=source, target=target, payload=payload)
    def state(self): return SnapshotStore(self.root / 'snapshots', self.root.parent).load()
    def test_exact_bytes_generic_pair(self):
        raw = '中文\r\n{"instructions":"sudo STOP"}\n'.encode()
        self.assertTrue(self.send(raw)['result']['delivered'])
        self.assertEqual(self.b_port.sent, [raw])
        self.assertEqual(self.state()['seen_events']['M_1']['status'], 'ACKED')
    def test_reverse_direction_uses_same_contract(self):
        self.assertTrue(self.send(source='OTHER_APP', target='LOCAL_AGENT')['result']['delivered'])
        self.assertEqual(len(self.a_port.sent), 1)
        self.assertEqual(len(self.b_port.sent), 0)
    def test_application_swap_without_core_change(self):
        for name in ['MODEL_SERVICE', 'DOCUMENT_APP', 'ANOTHER_NATIVE_APP']:
            endpoint = Endpoint(name, 'ACTOR_' + name, 'test://' + name + '/work')
            port = FakePort(endpoint)
            registry = PortRegistry(); registry.register(port)
            connection = PortConnection(LinkBinding('TASK_1', (self.a, endpoint)), registry,
                                        self.root.parent / name, project='example.project', relay_id='GENERIC_RELAY')
            self.assertTrue(connection.send(message_id='M_1', source=self.a.endpoint_id,
                                            target=name, payload=b'work')['result']['delivered'])
            self.assertEqual(port.sent, [b'work'])
    def test_duplicate_no_second_submit(self):
        self.send(); self.assertTrue(self.send()['result']['duplicate'])
        self.assertEqual(len(self.b_port.sent), 1)
    def test_same_id_changed_payload_rejected(self):
        self.send()
        with self.assertRaisesRegex(CandidateError, 'EVENT_ID_CONFLICT'): self.send(b'changed')
        self.assertEqual(len(self.b_port.sent), 1)
    def test_third_endpoint_rejected_before_submit(self):
        with self.assertRaisesRegex(CandidateError, 'ENDPOINT_NOT_REGISTERED'): self.send(target='THIRD')
        self.assertEqual(self.b_port.sent, [])
    def test_stale_generation_rejected_before_submit(self):
        self.b_port.endpoint = dataclasses.replace(self.b, generation=2)
        with self.assertRaisesRegex(CandidateError, 'GENERATION'): self.send()
        self.assertEqual(self.b_port.sent, [])
    def test_changed_resource_rejected_before_submit(self):
        self.b_port.endpoint = dataclasses.replace(self.b, resource_uri='test://different/chat')
        with self.assertRaisesRegex(CandidateError, 'RESOURCE'): self.send()
    def test_preflight_cannot_change_registered_resource(self):
        self.b_port.preflight = lambda: setattr(self.b_port, 'endpoint', dataclasses.replace(self.b, resource_uri='test://wrong'))
        with self.assertRaisesRegex(CandidateError, 'RESOURCE'): self.send()
        self.assertEqual(self.b_port.sent, [])
    def test_capability_drift_cannot_fake_exact_observation(self):
        self.b_port.capabilities = lambda: Capabilities('INFERENCE_API', True, False)
        with self.assertRaisesRegex(CandidateError, 'EXACT_CHAT_TRANSPORT_REQUIRED'): self.send()
        self.assertEqual(self.b_port.sent, [])
    def test_unknown_transport_rejected(self):
        empty = PortConnection(self.binding, PortRegistry(), self.root, project='example', relay_id='R_1')
        with self.assertRaisesRegex(CandidateError, 'HOST_PORT_UNAVAILABLE'):
            empty.send(message_id='M_1', source=self.a.endpoint_id, target=self.b.endpoint_id, payload=b'x')
    def test_registration_duplicate_rejected(self):
        with self.assertRaisesRegex(CandidateError, 'ALREADY_REGISTERED'): self.registry.register(self.b_port)
    def test_inference_not_faked_as_existing_chat(self):
        self.b_port.capabilities = lambda: Capabilities('INFERENCE_API', True, False)
        with self.assertRaisesRegex(CandidateError, 'EXACT_CHAT_TRANSPORT_REQUIRED'):
            PortRegistry().register(self.b_port)
    def test_uncertain_submit_retained_no_resend(self):
        self.b_port.fail = True
        with self.assertRaises(CandidateError): self.send()
        self.assertEqual(self.state()['seen_events']['M_1']['status'], 'UNCERTAIN')
        with self.assertRaisesRegex(CandidateError, 'UNCERTAIN_DELIVERY_STOP'): self.send()
        self.assertEqual(len(self.b_port.sent), 1)
    def test_uncertain_old_item_blocks_next_item(self):
        self.b_port.fail = True
        with self.assertRaises(CandidateError): self.send()
        with self.assertRaisesRegex(CandidateError, 'UNCERTAIN_DELIVERY_STOP'): self.send(message_id='M_2')
        self.assertEqual(len(self.b_port.sent), 1)
    def test_changed_observation_does_not_ack(self):
        self.b_port.observation_override = Observation(self.b, b'wrong', 'test://read', 'S_1')
        with self.assertRaises(CandidateError): self.send()
        self.assertEqual(self.state()['seen_events']['M_1']['status'], 'UNCERTAIN')
    def test_wrong_submission_identity_no_ack(self):
        self.b_port.submission_override = Submission(self.a, 'S_1', 'test://submit')
        with self.assertRaises(CandidateError): self.send()
        self.assertEqual(self.state()['seen_events']['M_1']['status'], 'UNCERTAIN')
    def test_wrong_observation_submission_id_no_ack(self):
        self.b_port.observation_override = Observation(self.b, b'original\r\n', 'test://read', 'OTHER')
        with self.assertRaises(CandidateError): self.send()
    def test_unsupported_size_stops_before_submit(self):
        self.b_port.limit = 3
        with self.assertRaisesRegex(CandidateError, 'HOST_PAYLOAD_BOUND_STOP'): self.send(b'long')
        self.assertEqual(self.b_port.sent, [])
    def test_empty_payload_preserved(self): self.assertTrue(self.send(b'')['result']['delivered'])
    def test_invalid_utf8_rejected_before_submit(self):
        with self.assertRaises(UnicodeError): self.send(b'\xff')
        self.assertEqual(self.b_port.sent, [])
    def test_invalid_endpoint_contracts(self):
        for endpoint in [dataclasses.replace(self.b, generation=True), dataclasses.replace(self.b, generation=0),
                         dataclasses.replace(self.b, resource_uri='')]:
            with self.assertRaises(CandidateError): endpoint.validate()
    def test_binding_disallows_duplicate_actors(self):
        with self.assertRaises(CandidateError): LinkBinding('TASK_1', (self.a, dataclasses.replace(self.b, actor_id=self.a.actor_id))).validate()
    def test_delivery_not_model_execution_or_review(self):
        value = normalized_result({'result': {'delivered': True}})
        self.assertEqual(value['stage'], 'HOST_OBSERVED_INPUT')
        for key in ['model_turn_consumed', 'task_accepted', 'execution_completed', 'independent_review_accepted']:
            self.assertFalse(value[key])
    def test_connection_binding_change_same_store_stops(self):
        self.send()
        changed=dataclasses.replace(self.b,generation=2)
        registry=PortRegistry();port=FakePort(changed);registry.register(port)
        connection=PortConnection(LinkBinding('TASK_1',(self.a,changed)),registry,self.root,project='example.project',relay_id='GENERIC_RELAY')
        with self.assertRaisesRegex(CandidateError,'STATE_CONNECTION_BINDING_CONFLICT'):
            connection.send(message_id='M_2',source=self.a.endpoint_id,target=changed.endpoint_id,payload=b'x')
        self.assertEqual(port.sent,[])
    def test_relay_change_same_store_stops(self):
        self.send(); self.connection.relay_id='OTHER_RELAY'
        with self.assertRaisesRegex(CandidateError,'STATE_CONNECTION_BINDING_CONFLICT'): self.send(message_id='M_2')
        self.assertEqual(len(self.b_port.sent),1)
    def test_next_task_same_connection_remains_supported(self):
        self.send()
        connection=PortConnection(LinkBinding('TASK_2',(self.a,self.b)),self.registry,self.root,project='example.project',relay_id='GENERIC_RELAY')
        self.assertTrue(connection.send(message_id='M_2',source=self.a.endpoint_id,target=self.b.endpoint_id,payload=b'next task')['result']['delivered'])
        self.assertEqual(self.state()['seen_events']['M_2']['task_id'],'TASK_2')
    def test_uri_map_cannot_disagree_with_binding(self):
        from xingshu_collaboration.connections.transport import OpaqueDelivery
        with self.assertRaisesRegex(CandidateError,'URI_BINDING_CONFLICT'):
            OpaqueDelivery('M_1',self.a.endpoint_id,self.b.endpoint_id,self.binding,
                           {self.a.endpoint_id:self.a.resource_uri,self.b.endpoint_id:'test://wrong'},
                           self.root,project='example.project',relay_id='GENERIC_RELAY')
    def test_observation_failure_retains_known_submission(self):
        self.b_port.observation_override=Observation(self.b,b'wrong','test://read','S_1')
        with self.assertRaises(CandidateError):self.send()
        entry=self.state()['seen_events']['M_1']
        self.assertEqual(entry['status'],'UNCERTAIN');self.assertTrue(entry['submission_known'])
        self.assertFalse(entry['observation_known']);self.assertEqual(entry['native_submission_id'],'S_1')
        self.assertEqual(entry['submission_evidence_ref'],'test://submit/S_1')
    def test_legacy_state_needs_explicit_migration(self):
        self.send();store=SnapshotStore(self.root/'snapshots',self.root.parent);state=store.load()
        state.pop('connection_identity');state.pop('connection_digest');store.save(state)
        with self.assertRaisesRegex(CandidateError,'LEGACY_STATE_EXPLICIT_MIGRATION_REQUIRED'):self.send(message_id='M_2')
        self.assertEqual(len(self.b_port.sent),1)

# 独立 fixture（测试环境），避免把回归重复计入通过数量。
class WakeTests(unittest.TestCase):
    setUp = ConnectionTests.setUp
    tearDown = ConnectionTests.tearDown
    send = ConnectionTests.send
    state = ConnectionTests.state
    def manager(self, endpoint=None):
        return Continuations(self.root, endpoint=endpoint or self.b, clock=lambda:self.clock)
    def observation(self):
        entry=self.state()['seen_events']['M_1']
        return ConsumptionObservation(self.b,'M_1',entry['task_id'],'MODEL_TURN_1','test://actual-model-turn','a'*64,
                                      entry['message_sha256'],entry['binding_digest'],entry['connection_digest'])
    def ready(self):
        self.clock = 100
        self.send()
        manager = self.manager(); manager.enqueue('M_1')
        return manager, manager.prepare('M_1')
    def test_ack_not_resume(self):
        manager, envelope = self.ready()
        outcome = manager.finish('M_1', dispatch_accepted=True)
        self.assertEqual(outcome['state'], 'DISPATCH_ACCEPTED'); self.assertFalse(outcome['model_turn_consumed'])
    def test_exact_consume_then_ack_race(self):
        manager, envelope = self.ready()
        self.assertTrue(manager.consume('M_1', envelope['consume_token'],self.observation())['model_turn_consumed'])
        self.assertEqual(manager.finish('M_1', dispatch_accepted=True)['state'], 'CONSUMED')
    def test_repeated_consume_is_idempotent(self):
        manager, envelope = self.ready(); token = envelope['consume_token']
        manager.consume('M_1', token,self.observation())
        self.assertTrue(manager.consume('M_1', token,self.observation())['replayed'])
    def test_second_prepare_never_resends(self):
        manager, _ = self.ready()
        with self.assertRaisesRegex(CandidateError, 'NO_RESEND'): manager.prepare('M_1')
    def test_unknown_dispatch_is_not_cleared_by_late_ack(self):
        manager, _ = self.ready(); manager.finish('M_1', dispatch_accepted=False)
        self.assertEqual(manager.finish('M_1', dispatch_accepted=True)['state'], 'DELIVERY_UNKNOWN')
    def test_exact_late_consume_can_resolve_unknown(self):
        manager, envelope = self.ready(); manager.finish('M_1', dispatch_accepted=False)
        self.assertTrue(manager.consume('M_1', envelope['consume_token'],self.observation())['model_turn_consumed'])
    def test_wrong_token_no_consume(self):
        manager, _ = self.ready()
        with self.assertRaisesRegex(CandidateError, 'TOKEN_INVALID'): manager.consume('M_1', 'wrong',self.observation())
    def test_wrong_generation_no_consume(self):
        manager, envelope = self.ready()
        stale = self.manager(dataclasses.replace(self.b, generation=2))
        with self.assertRaisesRegex(CandidateError, 'GENERATION'): stale.consume('M_1', envelope['consume_token'],self.observation())
    def test_wrong_resource_no_consume(self):
        manager, envelope = self.ready()
        stale = self.manager(dataclasses.replace(self.b, resource_uri='test://another/chat'))
        with self.assertRaisesRegex(CandidateError, 'IDENTITY'): stale.consume('M_1', envelope['consume_token'],self.observation())
    def test_expired_token_no_consume(self):
        manager, envelope = self.ready(); self.clock = 220
        with self.assertRaisesRegex(CandidateError, 'TOKEN_EXPIRED'): manager.consume('M_1', envelope['consume_token'],self.observation())
    def test_restart_pending_survives_same_original_store(self):
        manager, envelope = self.ready()
        self.assertTrue(self.manager().consume('M_1', envelope['consume_token'],self.observation())['model_turn_consumed'])
    def test_body_and_plain_token_absent_from_event(self):
        manager, envelope = self.ready()
        event = self.state()['continuations']['M_1']
        text = json.dumps(event)
        self.assertNotIn(envelope['consume_token'], text)
        self.assertNotIn('original', text)
    def test_consumption_not_task_completion(self):
        manager, envelope = self.ready(); result = manager.consume('M_1', envelope['consume_token'],self.observation())
        self.assertFalse(result['execution_completed']); self.assertFalse(result['independent_review_accepted'])
    def test_unacked_event_cannot_be_created(self):
        self.send(); self.clock = 100
        with self.assertRaisesRegex(CandidateError, 'ACKED'): self.manager().enqueue('M_UNKNOWN')
    def test_enqueue_replay_no_duplicate_event(self):
        manager, _ = self.ready()
        self.assertTrue(manager.enqueue('M_1')['replayed'])
        self.assertEqual(len(self.state()['continuations']), 1)
    def test_old_ack_cannot_be_enqueued_for_new_generation(self):
        self.clock=100;self.send()
        with self.assertRaisesRegex(CandidateError,'GENERATION'):self.manager(dataclasses.replace(self.b,generation=2)).enqueue('M_1')
    def test_old_ack_cannot_be_enqueued_for_new_resource(self):
        self.clock=100;self.send()
        with self.assertRaisesRegex(CandidateError,'IDENTITY'):self.manager(dataclasses.replace(self.b,resource_uri='test://wrong')).enqueue('M_1')
    def test_changed_original_delivery_blocks_consume(self):
        manager,envelope=self.ready();observation=self.observation();store=SnapshotStore(self.root/'snapshots',self.root.parent);state=store.load()
        state['seen_events']['M_1']['binding_digest']='0'*64;store.save(state)
        with self.assertRaisesRegex(CandidateError,'ORIGINAL_DELIVERY_CONFLICT'):manager.consume('M_1',envelope['consume_token'],observation)
    def test_token_without_structured_observation_cannot_consume(self):
        manager,envelope=self.ready()
        with self.assertRaisesRegex(CandidateError,'OBSERVATION_REQUIRED'):manager.consume('M_1',envelope['consume_token'])
        self.assertEqual(self.state()['continuations']['M_1']['state'],'DISPATCH_PREPARED')
    def test_boolean_observation_cannot_consume(self):
        manager,envelope=self.ready()
        with self.assertRaisesRegex(CandidateError,'OBSERVATION_REQUIRED'):manager.consume('M_1',envelope['consume_token'],True)
    def test_structured_consumption_mismatches_stop(self):
        manager,envelope=self.ready();observation=self.observation()
        for change in [{'message_id':'OTHER'},{'task_id':'OTHER'},{'connection_digest':'0'*64},
                       {'message_sha256':'0'*64},{'native_turn_id':''},{'evidence_sha256':'invalid'}]:
            with self.assertRaises(CandidateError):manager.consume('M_1',envelope['consume_token'],dataclasses.replace(observation,**change))
        self.assertEqual(self.state()['continuations']['M_1']['state'],'DISPATCH_PREPARED')
    def test_consumption_evidence_is_persistent(self):
        manager,envelope=self.ready();manager.consume('M_1',envelope['consume_token'],self.observation())
        event=self.state()['continuations']['M_1'];self.assertTrue(event['consumption_known'])
        self.assertEqual(event['model_turn_native_id'],'MODEL_TURN_1')
        self.assertEqual(event['consumption_evidence_ref'],'test://actual-model-turn')
    def test_replay_cannot_change_consumption_turn(self):
        manager,envelope=self.ready();observation=self.observation();manager.consume('M_1',envelope['consume_token'],observation)
        with self.assertRaisesRegex(CandidateError,'REPLAY_EVIDENCE_CONFLICT'):
            manager.consume('M_1',envelope['consume_token'],dataclasses.replace(observation,native_turn_id='ANOTHER_TURN'))

class ControlTests(unittest.TestCase):
    def message(self,**changes):
        from xingshu_collaboration.connections.control_plane import ControlMessage
        return ControlMessage(**dict(message_id='M_1',task_id='TASK_1',stage='REVIEW_REQUEST',version='V_1',
                                     artifact_ref='private-source://package',artifact_sha256='a'*64,**changes))
    def test_control_roundtrip_small(self):
        from xingshu_collaboration.connections.control_plane import ControlMessage
        message=self.message();raw=message.encode();self.assertLessEqual(len(raw),1024)
        self.assertEqual(ControlMessage.decode(raw),message)
    def test_control_cannot_carry_arbitrary_body_or_authority(self):
        from xingshu_collaboration.connections.control_plane import ControlMessage
        value=json.loads(self.message().encode());value['execute_authority']=True
        with self.assertRaises(CandidateError):ControlMessage.decode(json.dumps(value).encode())
    def test_source_reference_still_bound_by_size(self):
        with self.assertRaises(CandidateError):dataclasses.replace(self.message(),artifact_ref='原文'*300).encode()
    def test_control_decode_oversized_stops(self):
        from xingshu_collaboration.connections.control_plane import ControlMessage
        with self.assertRaises(CandidateError):ControlMessage.decode(b'x'*1025)

class ReconcileTests(unittest.TestCase):
    setUp=ConnectionTests.setUp
    tearDown=ConnectionTests.tearDown
    send=ConnectionTests.send
    state=ConnectionTests.state
    def prepare(self):
        self.b_port.observation_override=Observation(self.b,b'wrong','test://wrong','S_1')
        with self.assertRaises(CandidateError):self.send()
    def reconcile(self,observation=None):
        from xingshu_collaboration.connections.reconcile import reconcile_observation
        return reconcile_observation(self.root,confirmed_identity=self.state()['connection_identity'],message_id='M_1',
                                     observation=observation or Observation(self.b,b'original\r\n','test://late-read','S_1'))
    def test_exact_late_observation_clears_unknown_without_resend(self):
        self.prepare();self.assertTrue(self.reconcile()['reconciled']);self.assertEqual(len(self.b_port.sent),1)
        self.assertEqual(self.state()['outbox'],[]);self.assertTrue(self.state()['seen_events']['M_1']['late_observation_reconciled'])
    def test_wrong_native_id_cannot_clear_unknown(self):
        self.prepare()
        with self.assertRaisesRegex(CandidateError,'ORIGINAL_SUBMISSION'):self.reconcile(Observation(self.b,b'original\r\n','test://read','WRONG'))
        self.assertEqual(self.state()['outbox'],['M_1'])
    def test_wrong_late_body_cannot_clear_unknown(self):
        self.prepare()
        with self.assertRaises(CandidateError):self.reconcile(Observation(self.b,b'wrong','test://read','S_1'))
    def test_reconcile_without_known_submission_stops(self):
        self.prepare();store=SnapshotStore(self.root/'snapshots',self.root.parent);state=store.load()
        state['seen_events']['M_1'].pop('native_submission_id');store.save(state)
        with self.assertRaises(CandidateError):self.reconcile()
    def test_reconcile_replay_is_idempotent(self):
        self.prepare();self.reconcile();self.assertTrue(self.reconcile()['duplicate'])
        self.assertEqual(self.state()['total_hops'],1)

class RpcTests(unittest.TestCase):
    def setUp(self): self.endpoint = Endpoint('APP', 'ACTOR', 'test://app/chat')
    def reply(self, **kwargs): return {'ok':True, 'endpoint':dataclasses.asdict(self.endpoint), **kwargs}
    def test_methods_are_mapped_outside_core(self):
        calls=[]
        def call(method, args): calls.append((method,args)); return self.reply(exact_observation=True)
        port=JsonRpcHostPort(self.endpoint,call,methods={k:'custom.'+k for k in ['preflight','checkpoint','submit','observe']})
        port.preflight(); self.assertEqual(calls[0][0],'custom.preflight')
        self.assertEqual(calls[0][1]['generation'],1)
    def test_rpc_uses_remaining_duration_not_local_absolute_clock(self):
        calls=[]
        port=JsonRpcHostPort(self.endpoint,lambda method,args:(calls.append(args) or self.reply(submission_id='S_1',evidence_ref='test://receipt')))
        port.submit(b'raw',time.monotonic()+120)
        self.assertNotIn('deadline',calls[0])
        self.assertGreater(calls[0]['timeout_ms'],0); self.assertLessEqual(calls[0]['timeout_ms'],120000)
    def test_expired_rpc_cannot_submit(self):
        callback=Mock(); port=JsonRpcHostPort(self.endpoint,callback)
        with self.assertRaisesRegex(CandidateError,'DEADLINE_EXPIRED'): port.submit(b'raw',time.monotonic()-1)
        callback.assert_not_called()
    def test_remote_identity_mismatch_rejected(self):
        port=JsonRpcHostPort(self.endpoint,lambda *_:{'ok':True,'endpoint':{}})
        with self.assertRaisesRegex(CandidateError, 'ENDPOINT_CONFLICT'): port.preflight()
    def test_exact_base64_observation(self):
        port=JsonRpcHostPort(self.endpoint,lambda *_:self.reply(payload_base64=base64.b64encode('原文'.encode()).decode(),submission_id='S_1',evidence_ref='test://receipt'))
        read=port.observe('BASELINE',Submission(self.endpoint,'S_1','test://submit'),b'',time.monotonic()+120)
        self.assertEqual(read.payload,'原文'.encode())
    def test_malformed_observation_rejected(self):
        port=JsonRpcHostPort(self.endpoint,lambda *_:self.reply(payload_base64='!'))
        with self.assertRaises(CandidateError): port.observe('BASELINE',Submission(self.endpoint,'S_1','test://submit'),b'',time.monotonic()+120)
    def test_host_rejection_stops(self):
        port=JsonRpcHostPort(self.endpoint,lambda *_:{'ok':False})
        with self.assertRaisesRegex(CandidateError, 'REJECTED'): port.preflight()
    def test_oversized_encoded_body_rejected(self):
        port=JsonRpcHostPort(self.endpoint,lambda *_:self.reply(payload_base64='A'*100),maximum_payload_bytes=3)
        with self.assertRaisesRegex(CandidateError, 'BOUND'): port.observe('BASELINE',Submission(self.endpoint,'S_1','test://submit'),b'',time.monotonic()+120)

if __name__ == '__main__': unittest.main()
