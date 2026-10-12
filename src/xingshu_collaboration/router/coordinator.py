"""任务元数据与结果回路；发送沿用连接核心的快照、锁、去重和 UNKNOWN 停止。"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
import fcntl
import hashlib
import os
from xingshu_collaboration.connections.ports import PortConnection
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import SnapshotStore, digest


@dataclass(frozen=True)
class ReviewObservation:
    """可信宿主从复核端实际模型输出提取；仅上传、接受请求或令牌均不够。"""
    route_digest: str
    task_id: str
    endpoint: object
    version: str
    artifact_sha256: str
    decision: str
    native_turn_id: str
    native_output_id: str
    evidence_ref: str
    evidence_sha256: str


class TaskCoordinator:
    def __init__(self, router, ports, state_root):
        self.router, self.ports = router, ports
        self.state_root = Path(state_root)
        # 路径验证使用原存储；拒绝符号链接和正式 Runtime 目录。
        self.store = SnapshotStore(self.state_root / 'tasks', self.state_root.parent)

    @contextmanager
    def locked(self):
        fd = os.open(self.state_root / 'task.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CandidateError('CONCURRENT_TASK_DISPATCH_STOP')
            state = self.store.load() or {'protocol': 'xingshu-project-router/1', 'tasks': {}}
            if set(state) != {'protocol', 'tasks'} or state['protocol'] != 'xingshu-project-router/1':
                raise CandidateError('TASK_STATE_SCHEMA_CONFLICT')
            yield state
        finally:
            os.close(fd)

    def entry(self, state, route, *, mutating=True):
        self.router.validate_current(route)
        entry = state['tasks'].get(route.task_id)
        if not entry or entry['route_digest'] != route.route_digest:
            raise CandidateError('TASK_NOT_PREPARED_OR_ROUTE_CONFLICT')
        if mutating and entry.get('adoption_transition_id') and entry.get('last_transition_id') != entry['adoption_transition_id']:
            raise CandidateError('BUSINESS_ADOPTION_PENDING_RESUME_REQUIRED')
        return entry

    def prepare(self, invocation_port):
        route = self.router.plan(invocation_port)
        with self.locked() as state:
            previous = state['tasks'].get(route.task_id)
            if previous:
                if previous['route_digest'] != route.route_digest:
                    raise CandidateError('TASK_ID_OR_ORIGIN_CONFLICT')
                self.entry(state, route)
                return route
            state['tasks'][route.task_id] = {'route_digest': route.route_digest,
                'route': asdict(route), 'status': 'PLANNED', 'artifact': None, 'review': None,
                'return_message_id': None, 'return_payload_sha256': None}
            self.store.save(state)
        return route

    def status(self, route):
        with self.locked() as state:
            return dict(self.entry(state, route, mutating=False))

    def connection(self, route, binding):
        """外部复核发送入口，每次发送持业务锁；缓存对象也不能绕过采用冻结。"""
        if binding != route.review_binding():
            raise CandidateError('GUARDED_REVIEW_BINDING_REQUIRED')
        coordinator = self
        class GuardedReviewConnection:
            def send(self, *, message_id, source, target, payload):
                with coordinator.locked() as state:
                    coordinator.entry(state, route)
                    if source != route.channel.executor.endpoint_id or target != route.channel.reviewer.endpoint_id:
                        raise CandidateError('GUARDED_REVIEW_DIRECTION_REQUIRED')
                    coordinator.router.require_ready(route, route.channel.reviewer)
                    return coordinator._connection(route, binding).send(message_id=message_id,
                        source=source, target=target, payload=payload)
        return GuardedReviewConnection()

    def _connection(self, route, binding):
        # 每个任务连接命名来自完整路由，不能通过换目录躲开同一任务的不确定投递。
        key = route.route_digest[:32]
        return PortConnection(binding, self.ports, self.state_root / 'delivery' / key,
                              project=route.channel.logical_project_id, relay_id='PROJECT_TASK_HOST')

    def dispatch_goal(self, route, payload):
        if type(payload) is not bytes or hashlib.sha256(payload).hexdigest() != route.request_sha256:
            raise CandidateError('OWNER_GOAL_BYTES_CONFLICT')
        with self.locked() as state:
            entry = self.entry(state, route)
            if entry.get('continuation_only'):
                raise CandidateError('CONTINUATION_DOES_NOT_REDISPATCH_GOAL')
            binding = route.ingress_binding()
            if binding is None:
                return {'dispatch': 'CURRENT_EXECUTOR_INVOCATION', 'host_delivery_verified': False}
            self.router.require_ready(route, route.channel.executor)
            result = self._connection(route, binding).send(message_id='GOAL_' + route.route_digest[:48],
                source=route.origin.endpoint_id, target=route.channel.executor.endpoint_id, payload=payload)
            if entry['status'] == 'PLANNED':
                entry['status'] = 'GOAL_INPUT_OBSERVED'
                self.store.save(state)
            return result

    def set_artifact(self, route, version, artifact_sha256):
        if not identity(version) or not self.sha(artifact_sha256):
            raise CandidateError('ARTIFACT_VERSION_REQUIRED')
        with self.locked() as state:
            entry = self.entry(state, route)
            artifact = {'version': version, 'sha256': artifact_sha256}
            if entry['artifact'] == artifact:
                return
            if entry['status'] not in ('PLANNED', 'GOAL_INPUT_OBSERVED', 'REWORK_REQUIRED'):
                raise CandidateError('ARTIFACT_CHANGE_REQUIRES_REWORK')
            if entry['artifact'] and entry['artifact']['version'] == version:
                raise CandidateError('SAME_VERSION_CHANGED_ARTIFACT')
            entry.update(artifact=artifact, review=None, status='REVIEW_PENDING')
            self.store.save(state)

    @staticmethod
    def sha(value):
        return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

    def observe_review(self, route, review_port):
        with self.locked() as state:
            entry = self.entry(state, route)
            proof = review_port.observe_review(route)
            if (type(proof) is not ReviewObservation or proof.route_digest != route.route_digest
                    or proof.task_id != route.task_id or proof.endpoint != route.channel.reviewer
                    or entry['artifact'] != {'version': proof.version, 'sha256': proof.artifact_sha256}
                    or entry['status'] != 'REVIEW_PENDING'
                    or proof.decision not in ('PASS', 'REQUEST_CHANGES', 'BLOCK')
                    or not all(type(v) is str and 0 < len(v) <= 2048 for v in
                               (proof.native_turn_id, proof.native_output_id, proof.evidence_ref))
                    or not self.sha(proof.evidence_sha256)):
                raise CandidateError('ACTUAL_REVIEW_OBSERVATION_CONFLICT')
            entry['review'] = asdict(proof)
            entry['status'] = 'REVIEW_ACCEPTED' if proof.decision == 'PASS' else 'REWORK_REQUIRED'
            self.store.save(state)
            return entry['status']

    def return_result(self, route, *, version, artifact_sha256, message_id, payload):
        if (not identity(message_id) or message_id.startswith('GOAL_')
                or type(payload) is not bytes or len(payload) > 131072):
            raise CandidateError('RETURN_MESSAGE_INVALID')
        try:
            payload.decode('utf-8')
        except UnicodeError:
            raise CandidateError('RETURN_UTF8_REQUIRED')
        with self.locked() as state:
            entry = self.entry(state, route)
            if (entry['status'] not in ('REVIEW_ACCEPTED', 'RETURN_PREPARED', 'RETURN_INPUT_OBSERVED')
                    or entry['artifact'] != {'version': version, 'sha256': artifact_sha256}):
                raise CandidateError('EXACT_VERSION_REVIEW_REQUIRED')
            sha = hashlib.sha256(payload).hexdigest()
            if entry['return_message_id'] is not None and (entry['return_message_id'] != message_id
                    or entry['return_payload_sha256'] != sha):
                raise CandidateError('RETURN_ID_OR_PAYLOAD_CONFLICT')
            binding = route.return_binding()
            # 在宿主调用前固定返回 ID。中断恢复不能更换 ID 再投递。
            if entry['return_message_id'] is None:
                entry.update(return_message_id=message_id, return_payload_sha256=sha, status='RETURN_PREPARED')
                self.store.save(state)
            if binding is None:
                return {'dispatch': 'CURRENT_EXECUTOR_MUST_REPLY_IN_PLACE', 'host_delivery_verified': False,
                        'message_id': message_id, 'payload_sha256': sha}
            self.router.require_ready(route, route.origin)
            result = self._connection(route, binding).send(message_id=message_id,
                source=route.channel.executor.endpoint_id, target=route.origin.endpoint_id, payload=payload)
            entry['status'] = 'RETURN_INPUT_OBSERVED'
            self.store.save(state)
            # 仅证明原发起聊天收到输入，用户看见/已接受结果另需宿主实证。
            return result

    def _check_business_checkpoint(self, entry, old_route, row):
        from .continuity import doc
        packet = row['packet']
        if (packet['task_id'] != old_route.task_id or packet['request_sha256'] != old_route.request_sha256
                or packet['owner_trigger_ref'] != old_route.owner_trigger_ref or row['old'] != doc(old_route.channel)):
            raise CandidateError('BUSINESS_CONTINUITY_TASK_OR_ROUTE_CONFLICT')
        if not entry or entry['route_digest'] != old_route.route_digest:
            raise CandidateError('BUSINESS_CONTINUITY_OLD_TASK_MISSING')
        if entry.get('original_origin', asdict(old_route.origin)) != packet['original_origin']:
            raise CandidateError('BUSINESS_CONTINUITY_ORIGINAL_ORIGIN_CONFLICT')
        if (entry['artifact'] != {'version': packet['work_version'], 'sha256': packet['artifact_sha256']}
                or entry['status'] != packet['status']):
            raise CandidateError('BUSINESS_CONTINUITY_PROGRESS_CONFLICT')
        if entry['status'] not in ('REVIEW_PENDING', 'REVIEW_ACCEPTED', 'REWORK_REQUIRED'):
            raise CandidateError('BUSINESS_CONTINUITY_RETURN_ALREADY_STARTED')
        delivery = self.state_root / 'delivery' / old_route.route_digest[:32] / 'snapshots'
        if delivery.exists():
            old_messages = SnapshotStore(delivery, delivery.parent).load()
            if old_messages and any(v['status'] != 'ACKED' for v in old_messages['seen_events'].values()):
                raise CandidateError('BUSINESS_CONTINUITY_DELIVERY_UNCONFIRMED')

    def commit_verified(self, old_route, continuity_manager, transition_id, drain):
        """先在业务锁内验证进度/未确认投递，再提交；中断后按同一采用标记恢复。"""
        from .continuity import ContinuityManager
        if type(continuity_manager) is not ContinuityManager:
            raise CandidateError('TRUSTED_CONTINUITY_MANAGER_REQUIRED')
        with self.locked() as state:
            with continuity_manager.journal.locked() as lifecycle:
                row = dict(continuity_manager._proposal(lifecycle, transition_id))
            entry = state['tasks'].get(old_route.task_id)
            if row['status'] == 'CUTOVER_COMMITTED':
                if not entry or entry.get('adoption_transition_id') != transition_id:
                    raise CandidateError('BUSINESS_CUTOVER_WITHOUT_PREPARED_ADOPTION')
            else:
                self._check_business_checkpoint(entry, old_route, row)
                entry['adoption_transition_id'] = transition_id
                self.store.save(state)
            # 业务发送入口均使用同一业务锁；正式采用仍需宿主全局投递隔离。
            try:
                return continuity_manager.commit_candidate(transition_id, drain)
            except Exception:
                # 只有重新实读证明登记仍在旧页，才解除业务冻结；未知结果保留恢复标记。
                with continuity_manager.journal.locked() as lifecycle:
                    current = continuity_manager._proposal(lifecycle, transition_id)
                    from .continuity import registration_key
                    reg = lifecycle['registrations'][registration_key(old_route.channel)]
                    if current['status'] != 'CUTOVER_COMMITTED' and reg['channel'] == current['old']:
                        entry.pop('adoption_transition_id', None)
                        self.store.save(state)
                raise

    def resume_verified(self, old_route, continuity_manager, transition_id):
        """将已提交的候选接续接入同一业务任务；进度保留，旧目标不再派发。"""
        from .contracts import Route
        from .continuity import ContinuityManager, channel_from_dict, doc, registration_key
        if type(continuity_manager) is not ContinuityManager:
            raise CandidateError('TRUSTED_CONTINUITY_MANAGER_REQUIRED')
        with continuity_manager.journal.locked() as lifecycle:
            row = lifecycle['successors'].get(transition_id)
            if not row or row['status'] != 'CUTOVER_COMMITTED':
                raise CandidateError('COMMITTED_CONTINUITY_REQUIRED')
            registration = lifecycle['registrations'].get(registration_key(old_route.channel))
            if not registration or registration['channel'] != row['new']:
                raise CandidateError('CONTINUITY_REGISTRATION_DRIFT')
            # 拷贝独立值；后续业务锁不嵌套占用生命周期锁。
            row = dict(row)
        packet = row['packet']
        if (packet['task_id'] != old_route.task_id or packet['request_sha256'] != old_route.request_sha256
                or packet['owner_trigger_ref'] != old_route.owner_trigger_ref
                or row['old'] != doc(old_route.channel)):
            raise CandidateError('BUSINESS_CONTINUITY_TASK_OR_ROUTE_CONFLICT')
        original = Endpoint(**packet['original_origin']).validate()
        effective = continuity_manager.effective_return(old_route.channel.logical_project_id,
            old_route.task_id, original, old_route.request_sha256, channel=old_route.channel)
        channel = channel_from_dict(row['new'])
        origin_project = continuity_manager.catalog().chat(effective).project
        resumed = Route(old_route.task_id, old_route.request_sha256, channel, effective,
                        origin_project, old_route.owner_trigger_ref)
        self.router.validate_current(resumed)
        with self.locked() as state:
            entry = state['tasks'].get(old_route.task_id)
            if entry and entry.get('last_transition_id') == transition_id:
                if entry['route_digest'] != resumed.route_digest:
                    raise CandidateError('RESUMED_BUSINESS_ROUTE_DRIFT')
                return resumed
            self._check_business_checkpoint(entry, old_route, row)
            expected_original = entry.get('original_origin', asdict(old_route.origin))
            if expected_original != packet['original_origin']:
                raise CandidateError('BUSINESS_CONTINUITY_ORIGINAL_ORIGIN_CONFLICT')
            if (entry['artifact'] != {'version': packet['work_version'], 'sha256': packet['artifact_sha256']}
                    or entry['status'] != packet['status']):
                raise CandidateError('BUSINESS_CONTINUITY_PROGRESS_CONFLICT')
            if entry['status'] not in ('REVIEW_PENDING', 'REVIEW_ACCEPTED', 'REWORK_REQUIRED'):
                raise CandidateError('BUSINESS_CONTINUITY_RETURN_ALREADY_STARTED')
            delivery = self.state_root / 'delivery' / old_route.route_digest[:32] / 'snapshots'
            if delivery.exists():
                old_messages = SnapshotStore(delivery, delivery.parent).load()
                if old_messages and any(v['status'] != 'ACKED' for v in old_messages['seen_events'].values()):
                    raise CandidateError('BUSINESS_CONTINUITY_DELIVERY_UNCONFIRMED')
            history = entry.setdefault('continuity_history', [])
            history.append({'transition_id': transition_id, 'old_route': entry['route'],
                            'previous_status': entry['status'], 'previous_review': entry['review']})
            entry.update(route_digest=resumed.route_digest, route=asdict(resumed),
                original_origin=expected_original, last_transition_id=transition_id,
                continuation_only=True, review=None, status=('REWORK_REQUIRED' if entry['status'] == 'REWORK_REQUIRED' else 'REVIEW_PENDING'),
                progress_checkpoint_ref=packet['checkpoint_ref'], progress_summary=packet['summary'],
                next_step=packet['next_step'])
            self.store.save(state)
        return resumed
