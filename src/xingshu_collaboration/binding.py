"""上层显式预分配的固定端点任务；仅合成控制或本轮有界验收控制。"""
from dataclasses import dataclass,asdict
import hashlib,json,re
# 相同纯函数语义；解除当前入口对历史 StatefulRelay 的传递导入。
class CandidateError(Exception):pass
def identity(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value) is not None
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
SOURCE='CODEX_DESKTOP'
PEER='WEB_CHATGPT'
ROLE='RELAY_ONLY'
@dataclass(frozen=True)
class RuntimeTaskBinding:
    task_id:str
    original_codex_actor_id:str
    web_chatgpt_actor_id:str
    endpoint_registration:tuple
    source_endpoint:str=SOURCE
    peer_endpoint:str=PEER
    assigned_role:str=ROLE
    role_locked:bool=True
    route_locked:bool=True
    self_assignment:bool=False
    multi_role:bool=False
    business_reasoning:bool=False
    assigned_by:str='SYNTHETIC_XINGSHU_RUNTIME_CONTROL'
    def validate(self):
        if (type(self) is not RuntimeTaskBinding or not all(identity(x) for x in (self.task_id,self.original_codex_actor_id,self.web_chatgpt_actor_id))
            or self.original_codex_actor_id==self.web_chatgpt_actor_id
            or self.endpoint_registration!=((SOURCE,self.original_codex_actor_id),(PEER,self.web_chatgpt_actor_id))
            or self.source_endpoint!=SOURCE or self.peer_endpoint!=PEER or self.assigned_role!=ROLE
            or self.role_locked is not True or self.route_locked is not True or self.self_assignment is not False
            or self.multi_role is not False or self.business_reasoning is not False
            or self.assigned_by not in ('SYNTHETIC_XINGSHU_RUNTIME_CONTROL','BOUNDED_REAL_ACCEPTANCE_CONTROL','PROJECT_RELAY_CONTROL')):
            raise CandidateError('OWNER_REQUIRED_FIXED_RUNTIME_BINDING_UNCONFIRMED')
        return self
    @property
    def binding_digest(self):return digest(asdict(self.validate()))
    def actor_for(self,endpoint):
        return {SOURCE:self.original_codex_actor_id,PEER:self.web_chatgpt_actor_id}[endpoint]
def assign_fixed_task(task_id,original_codex_actor_id,web_chatgpt_actor_id,*,endpoint_registration,assigned_by='SYNTHETIC_XINGSHU_RUNTIME_CONTROL'):
    # 身份来源是上层显式登记，不从事件或业务内容自动选择端点/岗位。
    return RuntimeTaskBinding(task_id,original_codex_actor_id,web_chatgpt_actor_id,tuple(endpoint_registration),assigned_by=assigned_by).validate()
