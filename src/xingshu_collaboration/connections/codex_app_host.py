"""Codex 应用连接器的薄适配；工具回调由当前获授权宿主提供。"""
import json
import hashlib
import re
from urllib.parse import urlsplit
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.state import strict_json, Rejected
from .native_chat_port import NativeChatHostPort, ChatView, ChatRecord, HostAcceptance

def tool_json(result):
    if type(result) is not dict or result.get('isError') is True:
        raise CandidateError('NATIVE_APP_TOOL_REJECTED_OR_UNKNOWN')
    content = result.get('content', [])
    if type(content) is not list or any(type(c) is not dict for c in content):
        raise CandidateError('NATIVE_APP_TOOL_RESULT_INVALID')
    texts = [c.get('text') for c in content if c.get('type') == 'text']
    structured = result.get('structuredContent')
    try:
        if not texts and type(structured) is dict:
            return structured
        if len(texts) != 1 or type(texts[0]) is not str or len(texts[0].encode()) > 1048576:
            raise CandidateError('NATIVE_APP_TOOL_RESULT_INVALID')
        value = strict_json(texts[0])
        if type(value) is not dict or (structured is not None and structured != value):
            raise CandidateError('NATIVE_APP_TOOL_RESULT_INVALID')
        return value
    except (TypeError, ValueError, Rejected) as exc:
        raise CandidateError('NATIVE_APP_TOOL_RESULT_INVALID') from exc

def create_codex_app_port(endpoint, thread_id, call):
    """实际会话标识只由登记 URI 解析；独立传入值必须一致才可调用。"""
    uuid=r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
    uri=urlsplit(endpoint.resource_uri)
    if uri.scheme=='codex' and uri.netloc=='threads' and not uri.query and not uri.fragment:
        match=re.fullmatch('/('+uuid+')',uri.path);native_kind='codex'
    elif uri.scheme=='https' and uri.netloc=='chatgpt.com' and not uri.query and not uri.fragment:
        match=re.fullmatch('/(?:g/[A-Za-z0-9_-]+/)?c/('+uuid+')',uri.path);native_kind='chatgpt'
    else:match=None
    if match is None or thread_id!=match.group(1):raise CandidateError('NATIVE_APP_RESOURCE_BINDING_CONFLICT')
    native_id=match.group(1)

    def read(resource_uri, timeout_ms):
        if resource_uri!=endpoint.resource_uri:raise CandidateError('NATIVE_APP_RESOURCE_BINDING_CONFLICT')
        result = tool_json(call('read_thread', {'threadId':native_id,'turnLimit':1,
                                                'includeOutputs':native_kind=='codex','maxOutputCharsPerItem':20000,
                                                'timeout_ms':timeout_ms}))
        if (result.get('thread',{}).get('id')!=native_id or result['thread'].get('kind')!=native_kind
                or type(result.get('turns')) is not list):
            raise CandidateError('NATIVE_APP_THREAD_CONFLICT')
        status=result['thread'].get('status',{})
        if status.get('type') == 'systemError':
            raise CandidateError('NATIVE_HOST_SYSTEM_ERROR_STOP')
        records=[]
        for turn in result['turns']:
            for item in turn.get('items',[]):
                if (native_kind=='codex' and item.get('type')=='functionCallOutput'
                        and item.get('namespace')=='codex_app' and item.get('name')=='send_message_to_thread'):
                    output=item.get('output',{})
                    if type(output) is not dict or output.get('truncated') is not False:
                        raise CandidateError('NATIVE_APP_INPUT_TRUNCATED_OR_UNKNOWN')
                    # 原生跨聊天消息是有固定封套的宿主输入；不冒充用户直接输入。
                    text=output.get('text','')
                    envelope=re.fullmatch(r'<codex_delegation>\n  <source_thread_id>('+uuid+r')</source_thread_id>\n  <input>([\s\S]*)</input>\n</codex_delegation>',text)
                    if envelope is None:raise CandidateError('NATIVE_APP_DELEGATION_ENVELOPE_INVALID')
                    records.append(ChatRecord(item['id'],envelope.group(2).encode('utf-8')))
                    continue
                if item.get('type') != 'userMessage':
                    continue
                if item.get('truncated') is True:
                    raise CandidateError('NATIVE_APP_INPUT_TRUNCATED_OR_UNKNOWN')
                content=item.get('content')
                if (type(content) is not list or not content
                        or any(c.get('type')!='text' or type(c.get('text')) is not str for c in content)):
                    raise CandidateError('NATIVE_APP_TEXT_INPUT_REQUIRED')
                records.append(ChatRecord(item['id'], ''.join(c['text'] for c in content).encode('utf-8')))
        flags=result['thread'].get('status',{}).get('activeFlags',[])
        busy=status.get('type')=='active' or bool(flags) or any(t.get('status') not in {'completed','interrupted','failed'} for t in result['turns'])
        return ChatView(resource_uri,tuple(records),busy)

    def submit(resource_uri, payload, timeout_ms):
        if resource_uri!=endpoint.resource_uri:raise CandidateError('NATIVE_APP_RESOURCE_BINDING_CONFLICT')
        response=tool_json(call('send_message_to_thread', {'threadId':native_id,
                                                         'prompt':payload.decode('utf-8'),'timeout_ms':timeout_ms}))
        accepted=response=={'threadId':native_id}
        evidence={'response':response,'resource_uri':resource_uri,'payload_sha256':hashlib.sha256(payload).hexdigest()}
        ref='native-tool-response-sha256:'+hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
        return HostAcceptance(accepted,ref)

    # 回读上限 20000 个字符；字节上限更保守，防止截断正文后误认实读。
    return NativeChatHostPort(endpoint,read=read,submit=submit,maximum_payload_bytes=16384)
