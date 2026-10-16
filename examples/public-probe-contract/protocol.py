"""Exact public probe correlation. Host transport is trusted; this does not issue P5."""
import hashlib,json,math,uuid
ENDPOINT='00000000-0000-4000-8000-000000000001'
TASK='XS-PUBLIC-PROBE-EXAMPLE'
MODE='HOST_ASSISTED_ON_DEMAND_PUBLIC_PROBE'
def required(condition,message):
 if not condition:raise ValueError(message)
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def valid_id(value):
 required(type(value) is str and str(uuid.UUID(value)).lower()==value.lower(),'INVALID_MESSAGE_ID')
def message_for_ready(event):
 keys={'event','protocol_version','task_id','synthetic_data','request_id','scope_digest','challenge','web_endpoint','expected_reply','host_assisted_only','p5_authority'}
 required(type(event) is dict and set(event)==keys,'UNEXPECTED_NATIVE_EVENT')
 required(event['event']=='XS_PUBLIC_PROBE_READY_TO_SEND' and event['protocol_version']=='xingshu-public-ai-probe/1' and event['task_id']==TASK,'WRONG_PROTOCOL')
 required(event['web_endpoint']==ENDPOINT and event['synthetic_data'] is True and event['host_assisted_only'] is True and event['p5_authority'] is False,'WRONG_BOUNDARY')
 nonce=event['challenge'];valid_id(nonce);required(nonce.upper()==nonce and event['request_id']==nonce,'WRONG_REQUEST_ID')
 required(type(event['scope_digest']) is str and len(event['scope_digest'])==64 and all(c in '0123456789abcdef' for c in event['scope_digest']),'INVALID_SCOPE_DIGEST')
 expected='XINGSHU_CONNECTION_OK::'+nonce;required(event['expected_reply']==expected,'WRONG_EXPECTED_REPLY')
 return ('MessageID: XS-PUBLIC-AI-PROBE-V1/'+nonce+'\nProtocol: xingshu-public-ai-probe/1\nTask: '+TASK+'\nSynthetic-Data: true\nRequest-ID: '+nonce+'\n这是一条公开连接测试。请不调用工具，不添加说明，只回复下一行：\n'+expected)
def unwrap(result):
 required(type(result) is dict and result.get('isError',False) is False,'TOOL_FAILED')
 content=result.get('content');required(type(content) is list and len(content)==1 and content[0].get('type')=='text','WRONG_TOOL_RESULT')
 return json.loads(content[0]['text'])
def baseline_from_read(read,observed_at):
 required(read.get('thread',{}).get('id')==ENDPOINT and read['thread'].get('status',{}).get('type')=='idle','BASELINE_WRONG_OR_BUSY')
 required(finite(observed_at),'INVALID_BASELINE_TIME')
 ids=[]
 for turn in read.get('turns',[]):
  ids.append(turn['id']);ids.extend(i['id'] for i in turn.get('items',[]) if 'id' in i)
 return {'endpoint':ENDPOINT,'observed_at':observed_at,'prior_ids':ids}
class ProbeReadback:
 def __init__(self,event,baseline,receipt):
  self.event=event;self.prompt=message_for_ready(event);self.baseline=baseline;self.receipt=receipt;self.used=False;self.stopped=False
  required(baseline['endpoint']==ENDPOINT,'WRONG_BASELINE')
  required(receipt.get('request_id')==event['request_id'] and receipt.get('scope_digest')==event['scope_digest'] and receipt.get('endpoint')==ENDPOINT,'WRONG_SEND_ASSOCIATION')
  required(receipt.get('prompt_sha256')==hashlib.sha256(self.prompt.encode()).hexdigest(),'WRONG_SENT_TEXT')
  start=receipt.get('invoked_at');end=receipt.get('returned_at');pre=receipt.get('begin_requested_at');budget=receipt.get('maximum_host_dispatch_seconds')
  required(all(finite(v) for v in (start,end,pre,budget)) and 0<budget<=2 and baseline['observed_at']<=pre<=start<=end and start-pre<budget,'EXPIRED_ACTUAL_DISPATCH')
  mono=receipt.get('begin_monotonic');checked=receipt.get('dispatch_checked_monotonic')
  required(finite(mono) and finite(checked) and 0<=checked-mono<budget,'EXPIRED_MONOTONIC_DISPATCH')
  result=unwrap(receipt.get('raw_result'));required(result.get('threadId')==ENDPOINT and set(result).issubset({'threadId','messageId'}),'WRONG_SEND_TOOL_RESULT')
  if 'messageId' in result:valid_id(result['messageId'])
  self.sent_message_id=result.get('messageId')
 def stop(self):self.stopped=True
 def delivery(self,read,now):
  # Every attempted delivery is terminal, including malformed readbacks.
  required(not self.used and not self.stopped,'STOPPED_OR_REPLAYED');self.used=True
  required(finite(now) and self.receipt['returned_at']<=now<self.receipt['invoked_at']+180,'REPLY_OUTSIDE_WINDOW')
  required(type(read) is dict and read.get('thread',{}).get('id')==ENDPOINT,'WRONG_READBACK_ENDPOINT')
  required(read['thread'].get('status',{}).get('type')=='idle','REPLY_NOT_FINISHED')
  turns=read.get('turns',[]);required(len(turns)==1,'AMBIGUOUS_TURN');turn=turns[0]
  required(turn.get('status')=='completed' and turn.get('id') not in self.baseline['prior_ids'],'OLD_OR_UNFINISHED_TURN');valid_id(turn['id'])
  started=turn.get('startedAt');completed=turn.get('completedAt')
  required(finite(started) and finite(completed) and self.receipt['invoked_at']-2<=started<=completed<=now+2,'STALE_OR_INVALID_TURN_TIME')
  items=turn.get('items');required(type(items) is list and len(items)==2 and [i.get('type') for i in items]==['userMessage','agentMessage'],'EXTRA_ITEM_OR_WRONG_ROLE')
  user,agent=items;valid_id(user['id']);valid_id(agent['id'])
  required(user['id']!=agent['id'] and not ({user['id'],agent['id']} & set(self.baseline['prior_ids'])),'OLD_OR_ECHO_MESSAGE_ID')
  if self.sent_message_id:required(user['id']==self.sent_message_id,'SENT_MESSAGE_ID_MISMATCH')
  content=user.get('content');required(type(content) is list and len(content)==1 and content[0].get('type')=='text' and content[0].get('text')==self.prompt,'WRONG_USER_REQUEST')
  required(agent.get('text')==self.event['expected_reply'] and not agent.get('truncated',False),'REPLY_NOT_EXACT')
  return {'action':'deliver','agent_message_id':agent['id'],'challenge':self.event['challenge'],'mode':MODE,'scope_digest':self.event['scope_digest'],'text':agent['text'],'web_endpoint':ENDPOINT}

# Fixed host adapter: JSON in one argument, bounded output, no network or credentials.
def bridge(request):
 import time
 action=request.get('action')
 # Python 3.9 monotonic() on macOS has a per-process origin. Use the kernel
 # clock directly so separate validator processes share one fixed time base.
 monotonic=lambda:time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
 if action=='clock':return {'monotonic':monotonic(),'wall':time.time()}
 if action=='prepare':
  prompt=message_for_ready(request['event']);return {'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
 if action=='baseline':return baseline_from_read(request['read'],time.time())
 if action=='preflight':
  now=monotonic();start=request['begin_monotonic'];budget=request['budget']
  required(finite(start) and finite(budget) and 0<budget<=2 and 0<=now-start<budget,'MONOTONIC_DISPATCH_EXPIRED')
  return {'dispatch_checked_monotonic':now,'wall':time.time()}
 if action=='readback':
  raw=unwrap(request['raw_read']);receipt=request['receipt'];baseline=request['baseline'];event=request['event']
  session=ProbeReadback(event,baseline,receipt)
  required(monotonic()<receipt['dispatch_checked_monotonic']+175,'READBACK_MONOTONIC_TIMEOUT')
  required(raw.get('thread',{}).get('id')==ENDPOINT,'WRONG_READBACK_ENDPOINT')
  for turn in raw.get('turns',[]):
   required(all(i.get('type') in ('userMessage','agentMessage') for i in turn.get('items',[])),'EXTRA_TOOL_ITEM')
  if raw['thread'].get('status',{}).get('type')=='active':return {'state':'WAIT','reason':'CURRENT_REQUEST_ACTIVE'}
  # The provider can briefly return the exact pre-send completed view as idle.
  # Only a proven baseline view is deferred, never accepted as a new reply.
  turns=raw.get('turns',[])
  if len(turns)==1:
   old=turns[0];items=old.get('items',[]);prior_ids=baseline['prior_ids'];start=old.get('startedAt');end=old.get('completedAt')
   exact_baseline_ids=(len(items)==2 and len(prior_ids)==3 and [old.get('id'),items[0].get('id'),items[1].get('id')]==prior_ids)
   known=(raw['thread'].get('status',{}).get('type')=='idle' and old.get('status')=='completed' and exact_baseline_ids and [i.get('type') for i in items]==['userMessage','agentMessage'] and finite(start) and finite(end) and start<=end<receipt['invoked_at'])
   if known:return {'state':'WAIT','reason':'KNOWN_BASELINE_VIEW'}
  return {'state':'DELIVER','command':session.delivery(raw,time.time())}
 raise ValueError('UNKNOWN_BRIDGE_ACTION')
if __name__=='__main__':
 import sys
 try:
  required(len(sys.argv)==3 and sys.argv[1]=='--request-json','WRONG_BRIDGE_ARGUMENT')
  required(len(sys.argv[2].encode())<=48000,'BRIDGE_PAYLOAD_TOO_LARGE')
  print(json.dumps(bridge(json.loads(sys.argv[2])),ensure_ascii=True,sort_keys=True))
 except (ValueError,KeyError,TypeError) as error:
  print(json.dumps({'error':str(error)}));raise SystemExit(1)
