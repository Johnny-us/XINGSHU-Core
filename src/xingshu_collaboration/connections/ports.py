"""宿主端口：浏览器、MCP、原生应用均实现同一组方法。"""
import hashlib
import io
import json
import tempfile
import time
from typing import Protocol
from xingshu_collaboration.binding import CandidateError, identity
from .contracts import Capabilities, Endpoint, Observation, Submission
from .transport import OpaqueDelivery, MAX_BYTES

class HostPort(Protocol):
    endpoint: Endpoint
    def capabilities(self) -> Capabilities: ...
    def preflight(self) -> None: ...
    def checkpoint(self): ...
    def submit(self, payload: bytes, deadline: float) -> Submission: ...
    def observe(self, checkpoint, submission: Submission, payload: bytes, deadline: float) -> Observation: ...

class PortRegistry:
    """宿主显式注入适配模块；配置不能动态导入或运行任意代码。"""
    def __init__(self):
        self._ports = {}

    def register(self, port):
        endpoint = port.endpoint.validate()
        caps = port.capabilities().validate()
        if endpoint.endpoint_id in self._ports:
            raise CandidateError('ADAPTER_ALREADY_REGISTERED')
        if not caps.submission or not caps.exact_observation:
            raise CandidateError('EXACT_CHAT_TRANSPORT_REQUIRED')
        self._ports[endpoint.endpoint_id] = port

    def resolve(self, endpoint):
        port = self._ports.get(endpoint.endpoint_id)
        if port is None:
            raise CandidateError('HOST_PORT_UNAVAILABLE')
        if port.endpoint != endpoint:
            raise CandidateError('HOST_PORT_GENERATION_OR_RESOURCE_CONFLICT')
        caps = port.capabilities().validate()
        if not caps.submission or not caps.exact_observation:
            raise CandidateError('EXACT_CHAT_TRANSPORT_REQUIRED')
        return port

class _IntentBridge(io.StringIO):
    def __init__(self, handle, ack_stream):
        super().__init__()
        self.handle, self.ack_stream = handle, ack_stream
        self.used, self.failure = False, None

    def flush(self):
        if self.used:
            raise CandidateError('HOST_INTENT_ALREADY_CONSUMED')
        self.used = True
        try:
            ack = self.handle(json.loads(self.getvalue()))
            self.ack_stream.write(json.dumps(ack, ensure_ascii=False) + '\n')
        except Exception as exc:
            self.failure = str(exc) if isinstance(exc, CandidateError) else 'HOST_DISPATCH_UNKNOWN'
            self.ack_stream.seek(0)
            self.ack_stream.truncate(0)
        self.ack_stream.flush()
        self.ack_stream.seek(0)

class PortConnection:
    """任意应用对的显式连接；持久状态仍使用原 SnapshotStore。"""
    def __init__(self, binding, registry, state_root, *, project, relay_id):
        self.binding = binding.validate()
        self.registry, self.state_root = registry, state_root
        self.project, self.relay_id = project, relay_id

    def send(self, *, message_id, source, target, payload):
        if not identity(message_id) or type(payload) is not bytes or len(payload) > MAX_BYTES:
            raise CandidateError('MESSAGE_ID_OR_PAYLOAD_INVALID')
        payload.decode('utf-8')
        self.binding.endpoint_for(source)
        endpoint = self.binding.endpoint_for(target)
        if source == target:
            raise CandidateError('FIXED_ROUTE_CONFLICT')
        port = self.registry.resolve(endpoint)
        caps = port.capabilities().validate()
        if len(payload) > caps.maximum_payload_bytes:
            raise CandidateError('HOST_PAYLOAD_BOUND_STOP')
        port.preflight()
        self.registry.resolve(endpoint)
        uris = {e.endpoint_id: e.resource_uri for e in self.binding.endpoints}

        def handle(intent):
            expected = {'project_instance_id': self.project, 'message_id': message_id,
                        'task_id': self.binding.task_id, 'source': source, 'output_to': target,
                        'source_actor': self.binding.actor_for(source), 'target_actor': endpoint.actor_id,
                        'endpoint_uri': endpoint.resource_uri, 'message_sha256': hashlib.sha256(payload).hexdigest()}
            if any(intent.get(k) != v for k, v in expected.items()) or intent['message'].encode('utf-8') != payload:
                raise CandidateError('HOST_INTENT_BINDING_CONFLICT')
            deadline = time.monotonic() + 120
            self.registry.resolve(endpoint)
            checkpoint = port.checkpoint()
            self.registry.resolve(endpoint)
            if time.monotonic() >= deadline:
                raise CandidateError('HOST_CHECKPOINT_TIMEOUT')
            if hasattr(port,'set_acceptance_sink'):
                port.set_acceptance_sink(delivery.record_host_acceptance)
            submission = port.submit(payload, deadline)
            if (type(submission) is not Submission or submission.endpoint != endpoint
                    or type(submission.native_id) is not str or not submission.native_id
                    or type(submission.evidence_ref) is not str or not submission.evidence_ref):
                raise CandidateError('HOST_SUBMISSION_IDENTITY_UNCERTAIN')
            delivery.record_submission(submission)
            observation = port.observe(checkpoint, submission, payload, deadline)
            if (type(observation) is not Observation or observation.endpoint != endpoint
                    or type(observation.payload) is not bytes or observation.payload != payload
                    or observation.submission_id != submission.native_id
                    or type(observation.evidence_ref) is not str or not observation.evidence_ref
                    or time.monotonic() >= deadline):
                raise CandidateError('HOST_OBSERVATION_UNCERTAIN')
            ack = {k: intent[k] for k in ['project_instance_id', 'message_id', 'task_id',
                                        'output_to', 'target_actor', 'endpoint_uri', 'message', 'message_sha256']}
            ack.update(type='ACTUAL_ENDPOINT_ACK', observed_delivery=True,
                       evidence_ref=observation.evidence_ref)
            return ack

        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as ack_stream:
            bridge = _IntentBridge(handle, ack_stream)
            delivery = OpaqueDelivery(message_id, source, target, self.binding, uris, self.state_root,
                                      project=self.project, relay_id=self.relay_id,
                                      input_stream=ack_stream, output_stream=bridge)
            try:
                result = delivery.deliver(target, endpoint.actor_id, payload)
            except Exception as exc:
                if bridge.failure:
                    raise CandidateError(bridge.failure) from exc
                raise
            return {'protocol': 'xingshu-connection/1', 'result': result,
                    'model_turn_consumed': False, 'automatic_retry': False,
                    'background_started': False}
