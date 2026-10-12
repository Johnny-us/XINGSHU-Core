"""平台无关的连接契约；标识和能力不等于授权。"""
from dataclasses import asdict, dataclass
from enum import Enum
import re
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import digest

PROTOCOL = 'xingshu-connection/1'

class Stage(str, Enum):
    NOT_SUBMITTED = 'NOT_SUBMITTED'
    SUBMITTED = 'SUBMITTED'
    HOST_OBSERVED_INPUT = 'HOST_OBSERVED_INPUT'
    MODEL_TURN_CONSUMED = 'MODEL_TURN_CONSUMED'
    DELIVERY_UNKNOWN = 'DELIVERY_UNKNOWN'
    DUPLICATE_SUPPRESSED = 'DUPLICATE_SUPPRESSED'

@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    actor_id: str
    resource_uri: str
    generation: int = 1

    def validate(self):
        if (not identity(self.endpoint_id) or not identity(self.actor_id)
                or type(self.resource_uri) is not str or not self.resource_uri
                or len(self.resource_uri) > 2048
                or type(self.generation) is not int or self.generation < 1):
            raise CandidateError('ENDPOINT_BINDING_INVALID')
        return self

@dataclass(frozen=True)
class LinkBinding:
    """由上层登记的两端；不自动发现第三端、不根据正文选择应用。"""
    task_id: str
    endpoints: tuple

    def validate(self):
        if (not identity(self.task_id) or type(self.endpoints) is not tuple
                or len(self.endpoints) != 2
                or any(type(e) is not Endpoint for e in self.endpoints)):
            raise CandidateError('LINK_BINDING_INVALID')
        for endpoint in self.endpoints:
            endpoint.validate()
        for field in ('endpoint_id', 'actor_id', 'resource_uri'):
            if len({getattr(e, field) for e in self.endpoints}) != 2:
                raise CandidateError('LINK_ENDPOINT_IDENTITY_CONFLICT')
        return self

    @property
    def endpoint_registration(self):
        return tuple((e.endpoint_id, e.actor_id) for e in self.endpoints)

    @property
    def binding_digest(self):
        return digest(asdict(self.validate()))

    def endpoint_for(self, endpoint_id):
        self.validate()
        for endpoint in self.endpoints:
            if endpoint.endpoint_id == endpoint_id:
                return endpoint
        raise CandidateError('ENDPOINT_NOT_REGISTERED')

    def actor_for(self, endpoint_id):
        return self.endpoint_for(endpoint_id).actor_id

@dataclass(frozen=True)
class Capabilities:
    transport: str
    submission: bool
    exact_observation: bool
    model_continuation: bool = False
    background: bool = False
    maximum_payload_bytes: int = 131072

    def validate(self):
        if (type(self.transport) is not str or not self.transport
                or any(type(getattr(self, key)) is not bool for key in
                       ('submission', 'exact_observation', 'model_continuation', 'background'))
                or self.background
                or type(self.maximum_payload_bytes) is not int
                or not 0 < self.maximum_payload_bytes <= 131072):
            raise CandidateError('ADAPTER_CAPABILITY_INVALID')
        return self

@dataclass(frozen=True)
class Submission:
    endpoint: Endpoint
    native_id: str
    evidence_ref: str

@dataclass(frozen=True)
class Observation:
    endpoint: Endpoint
    payload: bytes
    evidence_ref: str
    submission_id: str

@dataclass(frozen=True)
class ConsumptionObservation:
    endpoint: Endpoint
    message_id: str
    task_id: str
    native_turn_id: str
    evidence_ref: str
    evidence_sha256: str
    message_sha256: str
    binding_digest: str
    connection_digest: str

    def validate(self):
        if (type(self.endpoint) is not Endpoint or not identity(self.message_id) or not identity(self.task_id)
                or type(self.native_turn_id) is not str or not self.native_turn_id or len(self.native_turn_id)>128
                or type(self.evidence_ref) is not str or not self.evidence_ref or len(self.evidence_ref)>2048
                or any(type(getattr(self,k)) is not str or not re.fullmatch('[0-9a-f]{64}',getattr(self,k))
                       for k in ['evidence_sha256','message_sha256','binding_digest','connection_digest'])):
            raise CandidateError('CONSUMPTION_OBSERVATION_INVALID')
        self.endpoint.validate()
        return self


def normalized_result(reply):
    """保持原回执；不会把宿主记录当成 AI 接单、执行或独立验收。"""
    result = reply.get('result', reply)
    if result.get('duplicate'):
        stage = Stage.DUPLICATE_SUPPRESSED
    elif result.get('delivered'):
        stage = Stage.HOST_OBSERVED_INPUT
    elif result.get('delivery_attempts', 0):
        stage = Stage.DELIVERY_UNKNOWN
    else:
        stage = Stage.NOT_SUBMITTED
    return {'protocol': PROTOCOL, 'stage': stage.value,
            'model_turn_consumed': False, 'task_accepted': False,
            'execution_completed': False, 'independent_review_accepted': False,
            'automatic_retry': False, 'background_started': False,
            'legacy_result': reply}
