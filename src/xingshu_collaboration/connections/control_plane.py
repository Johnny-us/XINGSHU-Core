"""智能端的小型状态信封；正文资料走已授权来源，机器人不解析此内容。"""
import json
import re
from dataclasses import dataclass,asdict
from xingshu_collaboration.binding import CandidateError,identity
from xingshu_collaboration.state import strict_json

@dataclass(frozen=True)
class ControlMessage:
    message_id:str
    task_id:str
    stage:str
    version:str
    artifact_ref:str
    artifact_sha256:str
    protocol:str='xingshu-control/1'

    def encode(self):
        if (self.protocol!='xingshu-control/1' or not identity(self.message_id) or not identity(self.task_id)
                or self.stage not in {'REVIEW_REQUEST','REVIEW_DECISION','RESULT_READY','HANDOFF','STOP'}
                or not identity(self.version) or type(self.artifact_ref) is not str
                or not self.artifact_ref or len(self.artifact_ref)>400
                or type(self.artifact_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',self.artifact_sha256)):
            raise CandidateError('CONTROL_MESSAGE_CONTRACT_INVALID')
        raw=json.dumps(asdict(self),ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>1024:raise CandidateError('CONTROL_MESSAGE_SIZE_STOP')
        return raw

    @classmethod
    def decode(cls,raw):
        if type(raw) is not bytes or len(raw)>1024:raise CandidateError('CONTROL_MESSAGE_SIZE_STOP')
        try: message=cls(**strict_json(raw)); message.encode(); return message
        except (TypeError,ValueError) as exc:raise CandidateError('CONTROL_MESSAGE_CONTRACT_INVALID') from exc
