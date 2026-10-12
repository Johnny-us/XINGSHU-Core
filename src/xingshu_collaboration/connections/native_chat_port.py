"""原生聊天宿主的通用适配；read/submit 由获授权应用注入。"""
import time
from dataclasses import dataclass
from xingshu_collaboration.binding import CandidateError
from .contracts import Capabilities, Submission, Observation

@dataclass(frozen=True)
class ChatRecord:
    record_id: str
    payload: bytes

@dataclass(frozen=True)
class ChatView:
    resource_id: str
    records: tuple
    busy: bool = False

@dataclass(frozen=True)
class HostAcceptance:
    accepted: bool
    evidence_ref: str

class NativeChatHostPort:
    """不解释正文。原生提交无消息 ID 时，须实际读到新增原文才返回身份。"""
    def __init__(self, endpoint, *, read, submit, maximum_payload_bytes=16384):
        self.endpoint = endpoint.validate()
        if not callable(read) or not callable(submit):
            raise CandidateError('NATIVE_HOST_BINDING_INVALID')
        self.read, self.submit_native = read, submit
        self.maximum_payload_bytes = maximum_payload_bytes
        self.capabilities().validate()
        self.baseline = None
        self.acceptance_sink = None
        self._observed = None

    def set_acceptance_sink(self, sink):
        self.acceptance_sink = sink

    def capabilities(self):
        return Capabilities('NATIVE_CHAT_HOST', True, True,
                            maximum_payload_bytes=self.maximum_payload_bytes)

    @property
    def resource_id(self):
        return self.endpoint.resource_uri

    def _view(self, timeout_ms=30000):
        view = self.read(self.resource_id, timeout_ms)
        if (type(view) is not ChatView or view.resource_id != self.resource_id
                or type(view.busy) is not bool or type(view.records) is not tuple
                or len(view.records) > 100
                or any(type(r) is not ChatRecord or type(r.record_id) is not str or not r.record_id
                       or type(r.payload) is not bytes or len(r.payload) > 131072 for r in view.records)
                or len({r.record_id for r in view.records}) != len(view.records)):
            raise CandidateError('NATIVE_HOST_VIEW_IDENTITY_INVALID')
        return view

    def preflight(self):
        if self._view().busy:
            raise CandidateError('NATIVE_HOST_BUSY_STOP')

    def inspect(self):
        """Readability does not require an idle source; this grants no submission readiness."""
        return self._view()

    def checkpoint(self):
        view = self._view()
        if view.busy:
            raise CandidateError('NATIVE_HOST_BUSY_STOP')
        self.baseline = frozenset(r.record_id for r in view.records)
        return self.baseline

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CandidateError('NATIVE_HOST_OBSERVATION_TIMEOUT')
        return max(1, min(120000, int(remaining * 1000)))

    def submit(self, payload, deadline):
        if self.baseline is None or type(payload) is not bytes or len(payload) > self.maximum_payload_bytes:
            raise CandidateError('NATIVE_HOST_CHECKPOINT_OR_BOUND_REQUIRED')
        accepted = self.submit_native(self.resource_id, payload, self._remaining(deadline))
        if (type(accepted) is not HostAcceptance or accepted.accepted is not True
                or type(accepted.evidence_ref) is not str or not accepted.evidence_ref):
            raise CandidateError('NATIVE_HOST_SUBMISSION_UNKNOWN')
        if self.acceptance_sink is not None:
            self.acceptance_sink(accepted.evidence_ref)
        # 仅本次显式调用内有限观察。没有后台、第二次提交或定时任务。
        while True:
            view = self._view(self._remaining(deadline))
            matches = [r for r in view.records if r.record_id not in self.baseline and r.payload == payload]
            if len(matches) > 1:
                raise CandidateError('NATIVE_HOST_NEW_RECORD_AMBIGUOUS')
            if matches:
                record = matches[0]
                self._remaining(deadline)
                self._observed = record
                return Submission(self.endpoint, record.record_id, self.endpoint.resource_uri + '#input=' + record.record_id)
            time.sleep(min(0.25, self._remaining(deadline) / 1000))

    def observe(self, checkpoint, submission, payload, deadline):
        if checkpoint != self.baseline or submission.native_id in checkpoint:
            raise CandidateError('NATIVE_HOST_CHECKPOINT_CONFLICT')
        self._remaining(deadline)
        record=self._observed
        if record is None or record.record_id!=submission.native_id or record.payload!=payload:
            raise CandidateError('NATIVE_HOST_EXACT_INPUT_NOT_OBSERVED')
        # 原生提交接口无消息 ID，submit 已用宿主实际回读取得新增 ID 和正文。
        # 使用这份同次调用的实际观察，不再等待另一轮云端缓存刷新。
        return Observation(self.endpoint, record.payload,
                           self.endpoint.resource_uri + '#observed=' + submission.native_id, submission.native_id)
