"""原生宿主身份、实际新增原文、错误响应及进程桥拒绝路径。"""
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import sys
sys.dont_write_bytecode=True
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.connections.contracts import Endpoint,Submission
from xingshu_collaboration.connections.native_chat_port import NativeChatHostPort,ChatView,ChatRecord,HostAcceptance
from xingshu_collaboration.connections.codex_app_host import create_codex_app_port
from xingshu_collaboration.connections.stdio_host import StdioHostCall

class NativeHostTests(unittest.TestCase):
    def setUp(self):
        self.endpoint=Endpoint('APP','ACTOR','test://app/chat')
        self.records=[ChatRecord('OLD',b'old')]
        self.submit=Mock(side_effect=self.accept)
        self.port=NativeChatHostPort(self.endpoint,read=lambda *_:ChatView(self.endpoint.resource_uri,tuple(self.records)),submit=self.submit)
    def accept(self,_resource,raw,_timeout):
        self.records.append(ChatRecord('NEW',raw)); return HostAcceptance(True,'test://accepted')
    def test_exact_new_input_and_native_id(self):
        self.port.preflight(); checkpoint=self.port.checkpoint(); payload='中文\r\n'.encode()
        submission=self.port.submit(payload,time.monotonic()+1)
        self.assertEqual(submission.native_id,'NEW')
        self.assertEqual(self.port.observe(checkpoint,submission,payload,time.monotonic()+1).payload,payload)
    def test_old_identical_text_cannot_be_used_as_new_delivery(self):
        self.records=[ChatRecord('OLD',b'raw')]; self.port.checkpoint()
        self.port.submit_native=lambda *_:HostAcceptance(True,'test://accepted')
        with self.assertRaisesRegex(CandidateError,'TIMEOUT'): self.port.submit(b'raw',time.monotonic()+0.01)
    def test_two_new_identical_inputs_are_ambiguous(self):
        self.port.checkpoint()
        def duplicate(*_):
            self.records.extend([ChatRecord('A',b'raw'),ChatRecord('B',b'raw')]); return HostAcceptance(True,'test://accepted')
        self.port.submit_native=duplicate
        with self.assertRaisesRegex(CandidateError,'AMBIGUOUS'): self.port.submit(b'raw',time.monotonic()+1)
    def test_wrong_resource_stops_before_submit(self):
        self.port.read=lambda *_:ChatView('OTHER',tuple(self.records))
        with self.assertRaisesRegex(CandidateError,'IDENTITY'): self.port.preflight()
        self.submit.assert_not_called()
    def test_busy_host_stops_before_submit(self):
        self.port.read=lambda *_:ChatView(self.endpoint.resource_uri,tuple(self.records),True)
        with self.assertRaisesRegex(CandidateError,'BUSY'): self.port.checkpoint()
        self.submit.assert_not_called()
    def test_payload_bound_before_native_submit(self):
        self.port.checkpoint()
        with self.assertRaisesRegex(CandidateError,'BOUND'): self.port.submit(b'x'*16385,time.monotonic()+1)
        self.submit.assert_not_called()
    def test_no_checkpoint_no_native_submit(self):
        with self.assertRaises(CandidateError): self.port.submit(b'raw',time.monotonic()+1)
        self.submit.assert_not_called()
    def test_submission_response_not_true_is_unknown(self):
        self.port.checkpoint(); self.port.submit_native=lambda *_:{'accepted':True}
        with self.assertRaisesRegex(CandidateError,'UNKNOWN'): self.port.submit(b'raw',time.monotonic()+1)
    def test_changed_observation_cannot_ack(self):
        checkpoint=self.port.checkpoint(); submission=self.port.submit(b'raw',time.monotonic()+1)
        self.port._observed=ChatRecord('NEW',b'changed')
        with self.assertRaisesRegex(CandidateError,'NOT_OBSERVED'): self.port.observe(checkpoint,submission,b'raw',time.monotonic()+1)
    def test_expired_deadline_no_native_submit(self):
        self.port.checkpoint()
        with self.assertRaisesRegex(CandidateError,'TIMEOUT'): self.port.submit(b'raw',time.monotonic()-1)
        self.submit.assert_not_called()

    def test_inspection_callback_is_validated_and_cannot_replace_delivery_read(self):
        inspector=Mock(return_value=ChatView(self.endpoint.resource_uri,(),True))
        port=NativeChatHostPort(self.endpoint,read=self.port.read,submit=self.submit,inspect_read=inspector)
        self.assertTrue(port.inspect().busy)
        port.preflight();self.assertEqual(port.checkpoint(),frozenset({'OLD'}))
        inspector.assert_called_once()
        inspector.return_value=ChatView('WRONG',())
        with self.assertRaisesRegex(CandidateError,'IDENTITY'):port.inspect()

    def test_inspector_must_be_callable(self):
        with self.assertRaisesRegex(CandidateError,'INSPECTOR_INVALID'):
            NativeChatHostPort(self.endpoint,read=self.port.read,submit=self.submit,inspect_read=True)

class AppCodecTests(unittest.TestCase):
    def setUp(self):
        self.thread_id='11111111-2222-4333-8444-555555555555'
        self.endpoint=Endpoint('APP','ACTOR','https://chatgpt.com/c/'+self.thread_id)
    def wrap(self,value): return {'content':[{'type':'text','text':json.dumps(value)}]}
    def view(self,thread=None,raw='原文\r\n'):
        return self.wrap({'thread':{'id':thread or self.thread_id,'kind':'chatgpt','status':{'activeFlags':[]}},'turns':[{'status':'completed','items':[
            {'type':'userMessage','id':'M_1','content':[{'type':'text','text':raw}]},
            {'type':'agentMessage','id':'A_1','text':'response is not input'}]}]})
    def test_mapping_preserves_raw_user_text(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:self.view())
        self.assertEqual(port._view().records[0].payload,'原文\r\n'.encode())
        self.assertEqual(len(port._view().records),1)
    def test_wrong_thread_read_cannot_be_bound(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:self.view('OTHER'))
        with self.assertRaisesRegex(CandidateError,'THREAD_CONFLICT'): port.preflight()
    def test_tool_error_cannot_be_a_submission_receipt(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:{'isError':True})
        with self.assertRaises(CandidateError): port.preflight()
    def test_wrong_submission_destination_is_not_acceptance(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:self.wrap({'threadId':'OTHER'}))
        self.assertFalse(port.submit_native(self.endpoint.resource_uri,b'raw',1000).accepted)
    def test_method_and_args_mapping_has_no_model_override(self):
        calls=[]
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda method,args:(calls.append((method,args)) or self.wrap({'threadId':self.thread_id})))
        self.assertTrue(port.submit_native(self.endpoint.resource_uri,b'raw',1000).accepted)
        self.assertEqual(calls[0][0],'send_message_to_thread'); self.assertNotIn('model',calls[0][1])
    def test_accepted_without_record_is_retained_by_sink(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda method,args:
                                  self.view() if method=='read_thread' else self.wrap({'threadId':self.thread_id}))
        port.checkpoint();sink=Mock();port.set_acceptance_sink(sink)
        with self.assertRaisesRegex(CandidateError,'TIMEOUT'):port.submit(b'new',time.monotonic()+0.01)
        sink.assert_called_once();self.assertTrue(sink.call_args.args[0].startswith('native-tool-response-sha256:'))
    def test_hidden_native_resource_mismatch_stops_before_read(self):
        callback=Mock()
        with self.assertRaisesRegex(CandidateError,'RESOURCE_BINDING_CONFLICT'):
            create_codex_app_port(self.endpoint,'00000000-0000-0000-0000-000000000000',callback)
        callback.assert_not_called()
    def test_codex_native_envelope_preserves_actual_input(self):
        endpoint=Endpoint('APP','ACTOR','codex://threads/'+self.thread_id)
        payload='原文\r\n<input>保持正文</input>\n'
        text='<codex_delegation>\n  <source_thread_id>'+self.thread_id+'</source_thread_id>\n  <input>'+payload+'</input>\n</codex_delegation>'
        view={'thread':{'id':self.thread_id,'kind':'codex','status':{'activeFlags':[]}},'turns':[{'status':'completed','items':[
            {'type':'functionCallOutput','id':'NATIVE_INPUT_ID','namespace':'codex_app','name':'send_message_to_thread',
             'output':{'text':text,'truncated':False}}]}]}
        port=create_codex_app_port(endpoint,self.thread_id,lambda *_:self.wrap(view))
        record=port._view().records[0];self.assertEqual(record.payload,payload.encode());self.assertEqual(record.record_id,'NATIVE_INPUT_ID')
        view['turns'][0]['items'][0]['output']['truncated']=True
        with self.assertRaisesRegex(CandidateError,'TRUNCATED'):port._view()
    def test_arbitrary_native_scheme_is_not_guessed(self):
        callback=Mock()
        with self.assertRaisesRegex(CandidateError,'RESOURCE_BINDING_CONFLICT'):
            create_codex_app_port(Endpoint('APP','ACTOR','test://not-native'),self.thread_id,callback)
        callback.assert_not_called()

    def test_diagnostic_reads_metadata_but_delivery_retains_complete_inputs(self):
        endpoint=Endpoint('APP','ACTOR','codex://threads/'+self.thread_id)
        calls=[]
        def call(method,args):
            calls.append((method,args))
            return self.wrap({'thread':{'id':self.thread_id,'kind':'codex','status':{'type':'active','activeFlags':[]}},
                              'turns':[{'status':'completed','items':[{'type':'userMessage','id':'I',
                                         'content':[{'type':'text','text':'完整原文'}]}]}]})
        port=create_codex_app_port(endpoint,self.thread_id,call)
        self.assertEqual(port.inspect(),ChatView(endpoint.resource_uri,(),True))
        self.assertFalse(calls[0][1]['includeOutputs']);self.assertEqual(calls[0][1]['maxOutputCharsPerItem'],1000)
        view=port._view();self.assertEqual(view.records[0].payload,'完整原文'.encode())
        self.assertTrue(calls[1][1]['includeOutputs']);self.assertEqual(calls[1][1]['maxOutputCharsPerItem'],20000)
        with self.assertRaisesRegex(CandidateError,'BUSY'):port.checkpoint()

    def test_metadata_inspection_still_rejects_wrong_identity_and_system_error(self):
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:self.view('OTHER'))
        with self.assertRaisesRegex(CandidateError,'THREAD_CONFLICT'):port.inspect()
        port=create_codex_app_port(self.endpoint,self.thread_id,lambda *_:self.wrap(
            {'thread':{'id':self.thread_id,'kind':'chatgpt','status':{'type':'systemError'}},'turns':[]}))
        with self.assertRaisesRegex(CandidateError,'SYSTEM_ERROR'):port.inspect()

class StdioBridgeTests(unittest.TestCase):
    def call(self,raw,params=None):
        read_fd,write_fd=os.pipe()
        try:
            os.write(write_fd,raw); os.close(write_fd); write_fd=None
            with os.fdopen(read_fd,'r') as stream:
                return StdioHostCall(stream,io.StringIO())('read_thread',params or {'timeout_ms':1000})
        finally:
            if write_fd is not None: os.close(write_fd)
    def test_response_id_must_match(self):
        with self.assertRaisesRegex(CandidateError,'CORRELATION'): self.call(b'{"jsonrpc":"2.0","id":2,"result":{}}\n')
    def test_exact_structured_response(self):
        self.assertEqual(self.call(b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n'),{'ok':True})
    def test_unsolicited_second_response_stops(self):
        with self.assertRaisesRegex(CandidateError,'UNSOLICITED'): self.call(b'{"jsonrpc":"2.0","id":1,"result":{}}\n{}\n')
    def test_eof_incomplete_reply_stops(self):
        with self.assertRaisesRegex(CandidateError,'EOF'): self.call(b'{')
    def test_unbounded_timeout_rejected(self):
        with self.assertRaisesRegex(CandidateError,'TIMEOUT_BOUND'): self.call(b'',{'timeout_ms':120001})

if __name__=='__main__': unittest.main()
