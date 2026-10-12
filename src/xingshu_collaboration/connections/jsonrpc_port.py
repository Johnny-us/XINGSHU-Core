"""通用 JSON-RPC（结构化请求）宿主适配；不内置任何应用名或凭据。"""
import base64
import math
import time
from xingshu_collaboration.binding import CandidateError
from .contracts import Endpoint, Capabilities, Submission, Observation

class JsonRpcHostPort:
    """call 由已认证的 MCP／应用宿主提供；方法名可在适配层映射。"""
    def __init__(self, endpoint, call, *, methods=None, maximum_payload_bytes=131072):
        self.endpoint = endpoint.validate()
        self.call = call
        self.methods = dict(methods or {
            'preflight': 'connection.preflight', 'checkpoint': 'connection.checkpoint',
            'submit': 'connection.submit', 'observe': 'connection.observe'})
        if set(self.methods) != {'preflight', 'checkpoint', 'submit', 'observe'}:
            raise CandidateError('HOST_METHOD_MAPPING_INVALID')
        if any(type(v) is not str or not v or len(v) > 128 for v in self.methods.values()):
            raise CandidateError('HOST_METHOD_MAPPING_INVALID')
        self.maximum_payload_bytes = maximum_payload_bytes
        self.capabilities().validate()

    def capabilities(self):
        return Capabilities('JSON_RPC_HOST', True, True,
                            maximum_payload_bytes=self.maximum_payload_bytes)

    def _invoke(self, operation, *, timeout_ms=5000, **params):
        response = self.call(self.methods[operation], {
            'protocol': 'xingshu-connection/1', 'endpoint_id': self.endpoint.endpoint_id,
            'actor_id': self.endpoint.actor_id, 'resource_uri': self.endpoint.resource_uri,
            'generation': self.endpoint.generation, 'timeout_ms': timeout_ms, **params})
        if type(response) is not dict or response.get('ok') is not True:
            raise CandidateError('HOST_RPC_REJECTED_OR_UNKNOWN')
        actual = response.get('endpoint')
        if actual != self.endpoint.__dict__:
            raise CandidateError('HOST_RPC_ENDPOINT_CONFLICT')
        return response

    def preflight(self):
        response = self._invoke('preflight')
        if response.get('exact_observation') is not True:
            raise CandidateError('EXACT_CHAT_TRANSPORT_REQUIRED')

    def checkpoint(self):
        response = self._invoke('checkpoint')
        if type(response.get('checkpoint')) is not str or not response['checkpoint']:
            raise CandidateError('HOST_CHECKPOINT_INVALID')
        return response['checkpoint']

    def submit(self, payload, deadline):
        response = self._invoke('submit', payload_base64=base64.b64encode(payload).decode('ascii'),
                                timeout_ms=self._remaining_ms(deadline))
        return Submission(self.endpoint, response.get('submission_id'), response.get('evidence_ref'))

    def observe(self, checkpoint, submission, payload, deadline):
        response = self._invoke('observe', checkpoint=checkpoint,
                                submission_id=submission.native_id, timeout_ms=self._remaining_ms(deadline))
        encoded = response.get('payload_base64')
        if type(encoded) is not str or len(encoded) > 4 * ((self.maximum_payload_bytes + 2) // 3):
            raise CandidateError('HOST_OBSERVATION_BOUND_INVALID')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise CandidateError('HOST_OBSERVATION_ENCODING_INVALID') from exc
        return Observation(self.endpoint, raw, response.get('evidence_ref'), response.get('submission_id'))

    @staticmethod
    def _remaining_ms(deadline):
        remaining = deadline - time.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise CandidateError('HOST_RPC_DEADLINE_EXPIRED')
        # 不把本机的单调时钟数值传到另一台机器。
        return max(1, min(120000, math.ceil(remaining * 1000)))
