"""通用项目补建与聊天创建。可信宿主注入能力，不解析业务正文取得权限。"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
import fcntl
import math
import os
import time
from .contracts import Project, ProjectRef, Chat, bounded
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import SnapshotStore, digest


def require(ok, reason):
    if not ok:
        raise CandidateError(reason)


def sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


@dataclass(frozen=True)
class ProviderScope:
    provider: str
    account_scope: str
    host_id: str

    def validate(self):
        require(identity(self.provider) and bounded(self.account_scope) and bounded(self.host_id),
                'PROVIDER_SCOPE_INVALID')
        return self

    def contains(self, ref):
        return type(ref) is ProjectRef and (ref.provider, ref.account_scope, ref.host_id) == (
            self.provider, self.account_scope, self.host_id)


@dataclass(frozen=True)
class LifecycleCapabilities:
    read: bool = True
    create_project: bool = False
    create_chat: bool = False
    rename_project: bool = False
    context_usage: bool = False
    compact: bool = False
    implementation: str = 'UNAVAILABLE'

    def validate(self):
        require(all(type(v) is bool for k, v in asdict(self).items() if k != 'implementation')
                and self.implementation in ('OFFICIAL_TOOL', 'OFFICIAL_API', 'OFFICIAL_UI', 'ISOLATED_TEST', 'UNAVAILABLE'),
                'LIFECYCLE_CAPABILITIES_INVALID')
        return self


@dataclass(frozen=True)
class CreationProof:
    """实际创建回执。宿主从官方操作返回提取，不从模型自述提取。"""
    operation_id: str
    native_id: str
    resource: object
    evidence_ref: str


@dataclass(frozen=True)
class EnsureProject:
    logical_project_id: str
    source_project: ProjectRef
    desired_name: str
    target_scope: ProviderScope
    owner_trigger_ref: str
    authorized: bool
    registered_peer: ProjectRef | None = None

    def validate(self):
        require(identity(self.logical_project_id) and bounded(self.desired_name, 160)
                and bounded(self.owner_trigger_ref, 2048) and self.authorized is True,
                'OWNER_PROJECT_INTENT_REQUIRED')
        require(type(self.source_project) is ProjectRef and type(self.target_scope) is ProviderScope,
                'PROJECT_PROVISION_SCOPE_INVALID')
        self.source_project.validate(); self.target_scope.validate()
        require(not self.target_scope.contains(self.source_project), 'PEER_SCOPE_MUST_DIFFER')
        if self.registered_peer is not None:
            self.registered_peer.validate()
            require(self.target_scope.contains(self.registered_peer), 'REGISTERED_PEER_SCOPE_CONFLICT')
        return self


class LifecycleJournal:
    """复用原追加快照；仅候选生命周期元数据，不成为第二套消息日志。"""
    def __init__(self, state_root):
        self.root = Path(state_root)
        self.store = SnapshotStore(self.root / 'lifecycle', self.root.parent)

    @contextmanager
    def locked(self):
        fd = os.open(self.root / 'lifecycle.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CandidateError('CONCURRENT_LIFECYCLE_STOP')
            state = self.store.load() or dict(protocol='xingshu-project-lifecycle/2', operations={}, registrations={}, successors={})
            require(set(state) == {'protocol', 'operations', 'registrations', 'successors'}
                    and state['protocol'] == 'xingshu-project-lifecycle/2'
                    and all(type(state[k]) is dict for k in ('operations', 'registrations', 'successors')),
                    'LIFECYCLE_STATE_SCHEMA_CONFLICT')
            yield state
        finally:
            os.close(fd)


class ProjectLifecycle:
    """官方工具/API/UI 都实现相同的 port 接口；缺能力时在写入前停止。"""
    def __init__(self, journal, catalog_port, operation_port, *, clock=time.time):
        self.journal, self.catalog_port, self.port, self.clock = journal, catalog_port, operation_port, clock

    def catalog(self):
        c = self.catalog_port.snapshot().validate()
        age = self.clock() - c.observed_at
        require(math.isfinite(age) and 0 <= age <= 120, 'LIFECYCLE_CATALOG_STALE')
        return c

    def _proof_resource(self, op, spec, proof):
        require(type(proof) is CreationProof and proof.operation_id == op
                and bounded(proof.native_id, 256) and bounded(proof.evidence_ref, 2048), 'ACTUAL_CREATION_PROOF_REQUIRED')
        c = self.catalog()
        if spec['kind'] in ('PROJECT', 'RENAME'):
            require(type(proof.resource) is Project, 'PROJECT_CREATION_RESOURCE_INVALID')
            p = proof.resource.validate()
            scope = ProviderScope(**spec['target_scope'])
            require(scope.contains(p.ref) and p.name == spec['desired_name'] and c.project(p.ref) == p,
                    'PROJECT_CREATION_READBACK_CONFLICT')
            if spec['kind'] == 'RENAME':
                require(p.ref == ProjectRef(**spec['project']), 'PROJECT_RENAME_IDENTITY_CONFLICT')
        else:
            require(type(proof.resource) is Chat, 'CHAT_CREATION_RESOURCE_INVALID')
            p = proof.resource.validate()
            require(p.project == ProjectRef(**spec['project']) and c.chat(p.endpoint) == p
                    and p.status in ('idle', 'completed'), 'CHAT_CREATION_READBACK_CONFLICT')
            require(p.chat_id not in spec['baseline_chat_ids'] and p.endpoint.resource_uri not in spec['baseline_uris'],
                    'SUCCESSOR_CHAT_IS_NOT_NEW')
            if 'topic_name' in spec:
                require(p.title == spec['topic_name'], 'MIRROR_TOPIC_TITLE_READBACK_CONFLICT')
        return asdict(p), c.evidence_ref

    def _create(self, spec, call):
        op = 'CREATE_' + digest(spec)[:48]
        with self.journal.locked() as state:
            prior = state['operations'].get(op)
            if prior:
                require(prior['spec'] == spec, 'CREATION_OPERATION_CONFLICT')
                require(prior['status'] == 'APPLIED_VERIFIED', 'CREATION_UNCONFIRMED_NO_RESUBMIT')
                resource = prior['resource']
                c = self.catalog()
                if spec['kind'] in ('PROJECT', 'RENAME'):
                    require(asdict(c.project(ProjectRef(**resource['ref']))) == resource, 'APPLIED_PROJECT_DRIFT')
                else:
                    current = c.chat(Endpoint(**resource['endpoint']))
                    require(current.chat_id == resource['chat_id']
                            and current.project is not None
                            and asdict(current.project) == resource['project'], 'APPLIED_CHAT_DRIFT')
                    if 'topic_name' in spec:
                        require(current.title == spec['topic_name'], 'MIRROR_TOPIC_TITLE_DRIFT')
                    resource = asdict(current)
                return resource
            # 先持久化意图。即使创建成功后进程中断，也不能盲目重复创建。
            entry = dict(spec=spec, status='SUBMITTING', resource=None, proof=None)
            state['operations'][op] = entry
            self.journal.store.save(state)
            try:
                proof = call(op)
                resource, readback = self._proof_resource(op, spec, proof)
            except Exception:
                entry['status'] = 'UNKNOWN'
                self.journal.store.save(state)
                raise
            entry.update(status='APPLIED_VERIFIED', resource=resource,
                         proof=dict(native_id=proof.native_id, evidence_ref=proof.evidence_ref, readback_ref=readback))
            self.journal.store.save(state)
            return resource

    def reconcile_creation(self, operation_id, proof):
        """原操作实证显式恢复；不按同名认领，不触发再次创建。"""
        with self.journal.locked() as state:
            entry = state['operations'].get(operation_id)
            require(entry is not None and entry['status'] in ('SUBMITTING', 'UNKNOWN'), 'UNKNOWN_CREATION_REQUIRED')
            resource, readback = self._proof_resource(operation_id, entry['spec'], proof)
            entry.update(status='APPLIED_VERIFIED', resource=resource,
                         proof=dict(native_id=proof.native_id, evidence_ref=proof.evidence_ref, readback_ref=readback))
            self.journal.store.save(state)
            return resource

    def ensure_project(self, request):
        require(type(request) is EnsureProject, 'TRUSTED_PROJECT_INTENT_REQUIRED')
        request.validate()
        caps = self.port.capabilities().validate()
        require(caps.read and self.port.scope == request.target_scope, 'PROJECT_OPERATION_PORT_SCOPE_CONFLICT')
        c = self.catalog(); c.project(request.source_project)
        spec = dict(kind='PROJECT', logical_project_id=request.logical_project_id,
                    source_project=asdict(request.source_project), desired_name=request.desired_name,
                    target_scope=asdict(request.target_scope), owner_trigger_ref=request.owner_trigger_ref)
        # 恢复同一创建意图优先于同名检查，否则成功后的重复调用会误判为同名冲突。
        op = 'CREATE_' + digest(spec)[:48]
        with self.journal.locked() as state:
            prior = state['operations'].get(op)
        if prior:
            resource = self._create(spec, lambda _: None)
            return Project(ProjectRef(**resource['ref']), resource['name'])
        if request.registered_peer is not None:
            peer = c.project(request.registered_peer)
            rename = dict(kind='RENAME', logical_project_id=request.logical_project_id,
                project=asdict(peer.ref), desired_name=request.desired_name, target_scope=asdict(request.target_scope),
                owner_trigger_ref=request.owner_trigger_ref)
            with self.journal.locked() as state:
                previous_rename = state['operations'].get('CREATE_' + digest(rename)[:48])
            if previous_rename:
                resource = self._create(rename, lambda _: None)
                return Project(ProjectRef(**resource['ref']), resource['name'])
            if peer.name != request.desired_name:
                require(caps.rename_project, 'REGISTERED_PROJECT_NAME_DRIFT_RENAME_UNSUPPORTED')
                resource = self._create(rename, lambda op: self.port.rename_project(op, peer.ref, request.desired_name))
                return Project(ProjectRef(**resource['ref']), resource['name'])
            return peer
        candidates = [p for p in c.projects if request.target_scope.contains(p.ref) and p.name == request.desired_name]
        require(not candidates, 'SAME_NAME_REQUIRES_IDENTITY_BINDING')
        require(caps.create_project, 'PROJECT_CREATE_UNSUPPORTED')
        resource = self._create(spec, lambda op: self.port.create_project(op, request.desired_name))
        return Project(ProjectRef(**resource['ref']), resource['name'])

    def create_successor(self, *, project, predecessor, handoff_sha256, owner_trigger_ref, topic_name=None):
        project.validate(); predecessor.validate()
        require(sha(handoff_sha256) and bounded(owner_trigger_ref, 2048), 'SUCCESSOR_INTENT_INVALID')
        caps = self.port.capabilities().validate()
        require(topic_name is None or bounded(topic_name, 160), 'SUCCESSOR_TOPIC_INVALID')
        can_create = caps.create_chat if topic_name is None else getattr(self.port, 'topic_chat_callback', None) is not None
        require(caps.read and can_create and self.port.scope.contains(project), 'CHAT_CREATE_UNSUPPORTED_OR_SCOPE_CONFLICT')
        c = self.catalog(); c.project(project)
        require(c.chat(predecessor).project == project, 'PREDECESSOR_PROJECT_CONFLICT')
        # 基线属于持久化意图，不随重复调用变化。
        with self.journal.locked() as state:
            candidates = [v for v in state['operations'].values() if v['spec']['kind'] == 'CHAT'
                and v['spec'].get('project') == asdict(project) and v['spec'].get('predecessor') == asdict(predecessor)
                and v['spec'].get('handoff_sha256') == handoff_sha256]
        require(len(candidates) <= 1, 'SUCCESSOR_INTENT_AMBIGUOUS')
        spec = candidates[0]['spec'] if candidates else dict(kind='CHAT', project=asdict(project),
            predecessor=asdict(predecessor), handoff_sha256=handoff_sha256, owner_trigger_ref=owner_trigger_ref,
            baseline_chat_ids=[x.chat_id for x in c.chats], baseline_uris=[x.endpoint.resource_uri for x in c.chats])
        require(spec['owner_trigger_ref'] == owner_trigger_ref, 'SUCCESSOR_OWNER_SCOPE_CHANGED')
        require(not candidates or spec.get('topic_name') == topic_name, 'SUCCESSOR_TOPIC_INTENT_CHANGED')
        if topic_name is not None:
            spec['topic_name'] = topic_name
        resource = self._create(spec, lambda op: self.port.create_chat(op, project, handoff_sha256)
            if topic_name is None else self.port.create_topic_chat(op, project, topic_name, handoff_sha256))
        return Chat(resource['chat_id'], ProjectRef(**resource['project']), Endpoint(**resource['endpoint']), resource['status'],resource.get('title'))
