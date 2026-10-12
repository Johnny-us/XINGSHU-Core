"""当前人类窗口直接执行；Web 建立同主题栏目和窗口，不扫描猜测入口。"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
import time
from .contracts import (Invocation, ProjectRef, Project, Chat, Route, CurrentChatChannel, bounded)
from .lifecycle import ProviderScope, ProjectLifecycle, require
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.state import digest


def project_doc(project):
    return asdict(project) if project is not None else None


@dataclass(frozen=True)
class CurrentChatProof:
    """可信宿主当前回合的证明；不是从第三方正文提取的地址或权限。"""
    invocation: Invocation
    source_scope: ProviderScope
    source_project: ProjectRef | None
    logical_project_id: str
    menu_name: str
    topic_name: str
    observed_at: float
    evidence_ref: str

    def validate(self, catalog, now):
        from xingshu_collaboration.binding import identity
        require(type(self.invocation) is Invocation and type(self.source_scope) is ProviderScope,
                'TRUSTED_CURRENT_HOST_PROOF_REQUIRED')
        self.invocation.validate(); self.source_scope.validate()
        require(identity(self.logical_project_id) and bounded(self.menu_name, 160)
                and bounded(self.topic_name, 160) and bounded(self.evidence_ref, 2048)
                and type(self.observed_at) in (int, float) and math.isfinite(self.observed_at)
                and 0 <= now - self.observed_at <= 120, 'CURRENT_HOST_PROOF_STALE_OR_INVALID')
        current = catalog.chat(self.invocation.origin)
        require(current.project == self.source_project, 'CURRENT_HOST_PROJECT_CHANGED')
        if current.project is not None:
            require(self.source_scope.contains(current.project), 'CURRENT_HOST_SCOPE_CONFLICT')
            catalog.project(current.project)
        require(current.title == self.topic_name, 'CURRENT_HOST_TOPIC_CHANGED')
        return self


class CurrentChatMirror:
    """复用候选生命周期意图日志；只创建 Web 侧，不建立虚假的 Codex 项目。"""
    def __init__(self, journal, catalog_port, web_port, *, clock=time.time):
        self.journal, self.catalog_port, self.port, self.clock = journal, catalog_port, web_port, clock
        self.lifecycle = ProjectLifecycle(journal, catalog_port, web_port, clock=clock)

    def catalog(self):
        return self.lifecycle.catalog()

    def validate_current(self, proof):
        require(type(proof) is CurrentChatProof, 'TRUSTED_CURRENT_HOST_PROOF_REQUIRED')
        return proof.validate(self.catalog(), self.clock())

    def _project(self, proof, target_project):
        c = self.catalog(); caps = self.port.capabilities().validate()
        require(caps.read and self.port.scope != proof.source_scope, 'WEB_MIRROR_SCOPE_CONFLICT')
        stable = dict(logical_project_id=proof.logical_project_id,
            source_scope=asdict(proof.source_scope), target_scope=asdict(self.port.scope),
            desired_name=proof.menu_name)
        if target_project is not None:
            require(type(target_project) is ProjectRef and self.port.scope.contains(target_project),
                    'WEB_MIRROR_REGISTERED_PROJECT_SCOPE_CONFLICT')
            project = c.project(target_project)
            spec = dict(stable, kind='RENAME', project=asdict(project.ref))
            op = 'CREATE_' + digest(spec)[:48]
            with self.journal.locked() as state:
                prior = state['operations'].get(op)
            if prior:
                row = self.lifecycle._create(spec, lambda _: None)
                return Project(ProjectRef(**row['ref']), row['name'])
            if project.name == proof.menu_name:
                return project
            require(caps.rename_project, 'WEB_MIRROR_PROJECT_RENAME_UNAVAILABLE')
            row = self.lifecycle._create(spec, lambda op: self.port.rename_project(op, target_project, proof.menu_name))
        else:
            spec = dict(stable, kind='PROJECT')
            op = 'CREATE_' + digest(spec)[:48]
            with self.journal.locked() as state:
                prior = state['operations'].get(op)
            if not prior:
                require(not any(self.port.scope.contains(p.ref) and p.name == proof.menu_name for p in c.projects),
                        'SAME_NAME_REQUIRES_IDENTITY_BINDING')
                require(caps.create_project, 'WEB_MIRROR_PROJECT_CREATE_UNAVAILABLE')
            row = self.lifecycle._create(spec, lambda op: self.port.create_project(op, proof.menu_name))
        return Project(ProjectRef(**row['ref']), row['name'])

    def ensure(self, proof, *, target_project=None):
        self.validate_current(proof)
        invocation = proof.invocation
        key = 'MIRROR_' + digest(dict(origin=asdict(invocation.origin), logical_project_id=proof.logical_project_id, target_scope=asdict(self.port.scope)))[:48]
        task_intent = dict(request_sha256=invocation.request_sha256, owner_trigger_ref=invocation.owner_trigger_ref)
        intent = dict(origin=asdict(invocation.origin), source_scope=asdict(proof.source_scope),
            source_project=project_doc(proof.source_project), logical_project_id=proof.logical_project_id,
            menu_name=proof.menu_name, topic_name=proof.topic_name,
            target_scope=asdict(self.port.scope), registered_project=project_doc(target_project))
        with self.journal.locked() as state:
            prior = state['registrations'].get(key)
            related = [v for v in state['operations'].values() if v['spec'].get('mirror_key') == key]
        require(all(v['spec']['intent_sha256'] == digest(intent) for v in related)
                and (prior is None or prior['intent'] == intent), 'CURRENT_CHAT_MIRROR_INTENT_CHANGED')
        require(prior is None or prior.get('task_intents', {}).get(invocation.task_id, task_intent) == task_intent,
                'CURRENT_CHAT_MIRROR_INTENT_CHANGED')
        require(all(v['spec'].get('creation_task_id') != invocation.task_id or
                    v['spec']['creation_task_intent'] == task_intent for v in related),
                'CURRENT_CHAT_MIRROR_INTENT_CHANGED')
        project = self._project(proof, target_project)
        if prior:
            channel = current_channel(prior['channel'])
            self.router(proof, channel).validate_current(Route(invocation.task_id,
                invocation.request_sha256, channel, invocation.origin, proof.source_project,
                invocation.owner_trigger_ref))
            with self.journal.locked() as state:
                row = state['registrations'][key]
                require(digest(row['channel']) == digest(asdict(channel)), 'CURRENT_CHAT_MIRROR_REGISTRATION_CONFLICT')
                if invocation.task_id not in row['task_intents']:
                    row['task_intents'][invocation.task_id] = task_intent
                    self.journal.store.save(state)
            return channel
        # 缺官方聊天创建能力时在记录提交意图之前停止。
        require(getattr(self.port, 'topic_chat_callback', None) is not None,
                'WEB_MIRROR_TOPIC_CHAT_CREATE_UNAVAILABLE')
        c = self.catalog()
        spec = related[0]['spec'] if related else dict(kind='CHAT', mirror_key=key,
            intent_sha256=digest(intent), creation_task_id=invocation.task_id, creation_task_intent=task_intent, logical_project_id=proof.logical_project_id,
            project=asdict(project.ref), topic_name=proof.topic_name,
            origin=asdict(invocation.origin), request_sha256=invocation.request_sha256,
            baseline_chat_ids=[chat.chat_id for chat in c.chats],
            baseline_uris=[chat.endpoint.resource_uri for chat in c.chats])
        require(len(related) <= 1, 'MIRROR_CREATION_INTENT_AMBIGUOUS')
        resource = self.lifecycle._create(spec, lambda op: self.port.create_topic_chat(
            op, project.ref, proof.topic_name, invocation.request_sha256))
        peer = Chat(resource['chat_id'], ProjectRef(**resource['project']),
            Endpoint(**resource['endpoint']), resource['status'], resource.get('title'))
        channel = CurrentChatChannel(proof.logical_project_id, proof.menu_name,
            (proof.source_project, project.ref), invocation.origin, peer.endpoint, 1,
            'current-chat-mirror:' + digest(intent), proof.source_scope, proof.topic_name, key).validate()
        self.router(proof, channel).validate_current(Route(invocation.task_id,
            invocation.request_sha256, channel, invocation.origin, proof.source_project,
            invocation.owner_trigger_ref))
        with self.journal.locked() as state:
            existing = state['registrations'].get(key)
            require(existing is None or existing['intent'] == intent and digest(existing['channel']) == digest(asdict(channel)),
                    'CURRENT_CHAT_MIRROR_REGISTRATION_CONFLICT')
            if existing is None:
                state['registrations'][key] = dict(kind='CURRENT_CHAT_MIRROR', intent=intent,
                    channel=asdict(channel), scope='CANDIDATE_ONLY', task_intents={invocation.task_id:task_intent}, history=[], returns={})
                self.journal.store.save(state)
        return channel

    def router(self, proof, channel):
        return CurrentChatRouter(self.catalog_port, proof, channel, clock=self.clock)


def current_channel(row):
    return CurrentChatChannel(row['logical_project_id'], row['desired_name'],
        tuple(ProjectRef(**p) if p is not None else None for p in row['projects']),
        Endpoint(**row['executor']), Endpoint(**row['reviewer']), row['generation'],
        row['registration_ref'], ProviderScope(**row['current_scope']), row['topic_name'], row['mirror_id']).validate()


class CurrentChatRouter:
    """只有已核实当前人类调用能使用此入口；原按项目发现的路由器保持保守。"""
    def __init__(self, catalog_port, proof, channel, *, clock=time.time):
        require(type(proof) is CurrentChatProof and type(channel) is CurrentChatChannel,
                'CURRENT_CHAT_ROUTE_HOST_PROOF_REQUIRED')
        self.catalog_port, self.proof, self.channel, self.clock = catalog_port, proof, channel.validate(), clock

    def catalog(self):
        c = self.catalog_port.snapshot().validate()
        age = self.clock() - c.observed_at
        require(math.isfinite(age) and 0 <= age <= 120, 'CURRENT_CHAT_CATALOG_STALE')
        self.proof.validate(c, self.clock())
        return c

    def plan(self, invocation_port):
        invocation = invocation_port.current_invocation()
        require(type(invocation) is Invocation and invocation == self.proof.invocation,
                'CURRENT_CHAT_INVOCATION_CONFLICT')
        route = Route(invocation.task_id, invocation.request_sha256, self.channel,
                      invocation.origin, self.proof.source_project, invocation.owner_trigger_ref)
        self.validate_current(route)
        return route

    def validate_current(self, route):
        require(route.channel == self.channel and route.origin == self.channel.executor
                and route.task_id == self.proof.invocation.task_id
                and route.request_sha256 == self.proof.invocation.request_sha256
                and route.owner_trigger_ref == self.proof.invocation.owner_trigger_ref
                and route.origin_project == self.proof.source_project
                and self.channel.current_scope == self.proof.source_scope,
                'CURRENT_CHAT_ROUTE_IDENTITY_CHANGED')
        c = self.catalog()
        require(c.chat(route.origin).project == self.channel.projects[0], 'CURRENT_CHAT_PROJECT_CHANGED')
        peer = c.chat(self.channel.reviewer)
        require(peer.project == self.channel.projects[1] and peer.title == self.channel.topic_name
                and c.project(peer.project).name == self.channel.desired_name,
                'WEB_MIRROR_MEMBERSHIP_OR_TOPIC_CHANGED')
        return c

    def require_ready(self, route, target):
        c = self.validate_current(route)
        require(target in (route.origin, self.channel.reviewer), 'CURRENT_CHAT_DESTINATION_CONFLICT')
        status = c.chat(target).status
        require(status in ('idle', 'completed') or target == route.origin and status == 'active',
                'CURRENT_CHAT_HOST_NOT_READY_' + status.upper())
        return c
