"""Synthetic malformed receipts/transcripts only. No tools or network."""
import copy,hashlib,importlib.util,json
from pathlib import Path
p=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('xs_public_probe_example',p/'protocol.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
nonce='E3D28F18-9CE5-4ABF-A47E-AC232F48C13A';uid='14d74189-05fc-437b-9663-7c39188f9441';aid='c08c2dce-7fea-4227-ab88-49e4aa8708d6'
event={'event':'XS_PUBLIC_PROBE_READY_TO_SEND','protocol_version':'xingshu-public-ai-probe/1','task_id':m.TASK,'synthetic_data':True,'request_id':nonce,'scope_digest':'1'*64,'challenge':nonce,'web_endpoint':m.ENDPOINT,'expected_reply':'XINGSHU_CONNECTION_OK::'+nonce,'host_assisted_only':True,'p5_authority':False}
prompt=m.message_for_ready(event)
baseline={'endpoint':m.ENDPOINT,'observed_at':100,'prior_ids':['d25e616a-67cd-4f1a-96f7-b269a946e9b3']}
receipt={'request_id':nonce,'scope_digest':'1'*64,'endpoint':m.ENDPOINT,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'begin_requested_at':110,'maximum_host_dispatch_seconds':2,'invoked_at':111,'returned_at':112,'raw_result':{'content':[{'type':'text','text':json.dumps({'threadId':m.ENDPOINT})}],'isError':False}}
read={'thread':{'id':m.ENDPOINT,'status':{'type':'idle'}},'turns':[{'id':uid,'status':'completed','startedAt':111,'completedAt':113,'items':[{'type':'userMessage','id':uid,'content':[{'type':'text','text':prompt}]},{'type':'agentMessage','id':aid,'text':event['expected_reply']}]}]}
checks=[]
receipt.update(begin_monotonic=110,dispatch_checked_monotonic=111)
def reject(name,fn):
 try:fn()
 except (ValueError,KeyError,TypeError):checks.append({'check':name,'pass':True})
 else:checks.append({'check':name,'pass':False})
def verify(r=read,rec=receipt,b=baseline):return m.ProbeReadback(event,b,rec).delivery(r,114)
def changed(name,change,target='read'):
 r,rec,b=copy.deepcopy(read),copy.deepcopy(receipt),copy.deepcopy(baseline);change({'read':r,'receipt':rec,'baseline':b}[target]);reject(name,lambda:verify(r,rec,b))
changed('wrong_send_request',lambda x:x.update(request_id=uid),'receipt')
changed('wrong_send_result_endpoint',lambda x:x['raw_result']['content'][0].update(text=json.dumps({'threadId':'other'})),'receipt')
changed('tool_error_denied',lambda x:x['raw_result'].update(isError=True),'receipt')
changed('actual_send_after_native_budget',lambda x:x.update(invoked_at=113,returned_at=114),'receipt')
changed('monotonic_dispatch_expired',lambda x:x.update(dispatch_checked_monotonic=113),'receipt')
changed('monotonic_evidence_missing',lambda x:x.pop('begin_monotonic'),'receipt')
changed('wrong_prompt_digest',lambda x:x.update(prompt_sha256='2'*64),'receipt')
changed('old_turn_id',lambda x:x['prior_ids'].append(uid),'baseline')
changed('old_agent_id',lambda x:x['prior_ids'].append(aid),'baseline')
changed('stale_turn_time',lambda x:x['turns'][0].update(startedAt=80,completedAt=81))
changed('extra_tool_item',lambda x:x['turns'][0]['items'].append({'type':'toolCall','id':'tool'}))
changed('wrong_window',lambda x:x['thread'].update(id='other'))
changed('wrong_nonce',lambda x:x['turns'][0]['items'][1].update(text='XINGSHU_CONNECTION_OK::other'))
changed('extra_text',lambda x:x['turns'][0]['items'][1].update(text=event['expected_reply']+' extra'))
changed('wrong_role',lambda x:x['turns'][0]['items'][1].update(type='userMessage'))
changed('user_echo',lambda x:x['turns'][0]['items'][1].update(id=uid))
changed('different_user_request',lambda x:x['turns'][0]['items'][0]['content'][0].update(text='other'))
changed('provided_message_id_mismatch',lambda x:x['raw_result']['content'][0].update(text=json.dumps({'threadId':m.ENDPOINT,'messageId':aid})),'receipt')
s=m.ProbeReadback(event,baseline,receipt);s.stop();reject('stop_matching_late_reply',lambda:s.delivery(read,114))
s=m.ProbeReadback(event,baseline,receipt);s.delivery(read,114);reject('duplicate_delivery_rejected',lambda:s.delivery(read,115))
reject('late_reply_rejected',lambda:m.ProbeReadback(event,baseline,receipt).delivery(read,291))
checks.append({'check':'exact_new_request_and_independent_reply','pass':verify()['agent_message_id']==aid})
import time
mono=time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
rec=copy.deepcopy(receipt);rec.update(begin_monotonic=mono-.5,dispatch_checked_monotonic=mono-.2)
old=baseline['prior_ids'][0];oldagent='e5cd9ab4-be61-434c-b50c-b6963add6a82';b=copy.deepcopy(baseline);b['prior_ids']=[old,old,oldagent]
stale={'thread':{'id':m.ENDPOINT,'status':{'type':'idle'}},'turns':[{'id':old,'status':'completed','startedAt':80,'completedAt':90,'items':[{'id':old,'type':'userMessage'},{'id':oldagent,'type':'agentMessage'}]}]}
req={'action':'readback','event':event,'baseline':b,'receipt':rec,'raw_read':{'isError':False,'content':[{'type':'text','text':json.dumps(stale)}]}}
checks.append({'check':'known_baseline_idle_is_wait_not_delivery','pass':m.bridge(req)=={'state':'WAIT','reason':'KNOWN_BASELINE_VIEW'}})
swapped=copy.deepcopy(req);r=json.loads(swapped['raw_read']['content'][0]['text']);r['turns'][0]['items'][0]['id']=oldagent;r['turns'][0]['items'][1]['id']=old;swapped['raw_read']['content'][0]['text']=json.dumps(r)
reject('stale_swapped_user_agent_ids',lambda:m.bridge(swapped))
expired=copy.deepcopy(req);expired['receipt'].update(begin_monotonic=mono-178,dispatch_checked_monotonic=mono-177)
reject('known_stale_view_still_times_out',lambda:m.bridge(expired))
extra=copy.deepcopy(req);r=json.loads(extra['raw_read']['content'][0]['text']);r['turns'][0]['items'].append({'type':'toolCall','id':'extra'});extra['raw_read']['content'][0]['text']=json.dumps(r)
reject('known_stale_extra_tool_still_rejected',lambda:m.bridge(extra))
result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks':checks,'actual_network_calls':0,'actual_owner_approval':False,'real_ai_reply':False,'source_sha256':hashlib.sha256((p/'protocol.py').read_bytes()).hexdigest()}
print(json.dumps(result,indent=2))
if result['status']!='PASS':raise SystemExit(1)
