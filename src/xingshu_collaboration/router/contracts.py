"""项目目录与聊天宿主契约。对象由可信宿主注入，不能从消息正文取得权限。"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Protocol
from xingshu_collaboration.connections.contracts import Endpoint, LinkBinding
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import digest


def bounded(value, limit=512):
    return type(value) is str and 0 < len(value) <= limit


@dataclass(frozen=True)
class ProjectRef:
    provider: str
    project_id: str
    account_scope: str
    host_id: str

    def validate(self):
        if not identity(self.provider) or not all(bounded(v) for v in
                (self.project_id, self.account_scope, self.host_id)):
            raise CandidateError('PROJECT_IDENTITY_INVALID')
        return self


@dataclass(frozen=True)
class Project:
    ref: ProjectRef
    name: str

    def validate(self):
        if type(self.ref) is not ProjectRef or not bounded(self.name, 160):
            raise CandidateError('PROJECT_METADATA_INVALID')
        self.ref.validate()
        return self


@dataclass(frozen=True)
class Chat:
    chat_id: str
    project: ProjectRef | None
    endpoint: Endpoint
    status: str
    title: str | None = None

    def validate(self):
        if not bounded(self.chat_id, 128) or type(self.endpoint) is not Endpoint or not bounded(self.status, 64):
            raise CandidateError('CHAT_METADATA_INVALID')
        self.endpoint.validate()
        if self.title is not None and not bounded(self.title, 160):
            raise CandidateError('CHAT_TITLE_INVALID')
        if self.project is not None:
            if type(self.project) is not ProjectRef:
                raise CandidateError('CHAT_PROJECT_INVALID')
            self.project.validate()
        return self


@dataclass(frozen=True)
class Catalog:
    projects: tuple
    chats: tuple
    evidence_ref: str
    observed_at: float

    def validate(self):
        if (type(self.projects) is not tuple or type(self.chats) is not tuple
                or not bounded(self.evidence_ref, 2048)
                or type(self.observed_at) not in (int, float)):
            raise CandidateError('CATALOG_INVALID')
        for p in self.projects:
            if type(p) is not Project:
                raise CandidateError('CATALOG_PROJECT_INVALID')
            p.validate()
        for c in self.chats:
            if type(c) is not Chat:
                raise CandidateError('CATALOG_CHAT_INVALID')
            c.validate()
        if (len({p.ref for p in self.projects}) != len(self.projects)
                or len({c.endpoint.resource_uri for c in self.chats}) != len(self.chats)
                or len({c.endpoint.actor_id for c in self.chats}) != len(self.chats)
                or len({c.endpoint.endpoint_id for c in self.chats}) != len(self.chats)):
            raise CandidateError('CATALOG_IDENTITY_AMBIGUOUS')
        if any(c.project is not None and c.project not in {p.ref for p in self.projects} for c in self.chats):
            raise CandidateError('CATALOG_PROJECT_MISSING')
        return self

    def project(self, ref):
        rows = [p for p in self.projects if p.ref == ref]
        if len(rows) != 1:
            raise CandidateError('PROJECT_NOT_OBSERVED')
        return rows[0]

    def chat(self, endpoint):
        rows = [c for c in self.chats if c.endpoint == endpoint]
        if len(rows) != 1:
            raise CandidateError('CHAT_NOT_OBSERVED_OR_GENERATION_CHANGED')
        return rows[0]


@dataclass(frozen=True)
class ProjectChannel:
    logical_project_id: str
    desired_name: str
    projects: tuple
    executor: Endpoint
    reviewer: Endpoint
    generation: int
    registration_ref: str

    def validate(self):
        if (not identity(self.logical_project_id) or not bounded(self.desired_name, 160)
                or type(self.projects) is not tuple or len(self.projects) != 2
                or any(type(p) is not ProjectRef for p in self.projects)
                or self.projects[0] == self.projects[1]
                or type(self.generation) is not int or self.generation < 1
                or not bounded(self.registration_ref, 2048)):
            raise CandidateError('PROJECT_CHANNEL_INVALID')
        for p in self.projects:
            p.validate()
        LinkBinding('CHANNEL_CHECK', (self.executor, self.reviewer)).validate()
        return self


@dataclass(frozen=True)
class CurrentChatChannel(ProjectChannel):
    """明确当前窗口的主题配对；允许本地没有项目，Web 必须有真实项目。"""
    current_scope: object
    topic_name: str
    mirror_id: str

    def validate(self):
        from .lifecycle import ProviderScope
        if (not identity(self.logical_project_id) or not bounded(self.desired_name, 160)
                or not bounded(self.topic_name, 160) or not identity(self.mirror_id) or type(self.projects) is not tuple
                or len(self.projects) != 2 or type(self.projects[1]) is not ProjectRef
                or self.projects[0] is not None and type(self.projects[0]) is not ProjectRef
                or type(self.current_scope) is not ProviderScope
                or type(self.generation) is not int or self.generation < 1
                or not bounded(self.registration_ref, 2048)):
            raise CandidateError('CURRENT_CHAT_CHANNEL_INVALID')
        self.current_scope.validate(); self.projects[1].validate()
        if self.projects[0] is not None:
            self.projects[0].validate()
            if not self.current_scope.contains(self.projects[0]):
                raise CandidateError('CURRENT_CHAT_SOURCE_SCOPE_CONFLICT')
        if self.current_scope.contains(self.projects[1]):
            raise CandidateError('CURRENT_CHAT_PEER_SCOPE_MUST_DIFFER')
        LinkBinding('CHANNEL_CHECK', (self.executor, self.reviewer)).validate()
        return self


@dataclass(frozen=True)
class Invocation:
    """当前人类目标的宿主证明；不接收正文提供的 project_id 或 reply_to。"""
    task_id: str
    request_sha256: str
    origin: Endpoint
    owner_trigger_ref: str
    authorized: bool

    def validate(self):
        if (not identity(self.task_id) or type(self.request_sha256) is not str
                or len(self.request_sha256) != 64
                or any(ch not in '0123456789abcdef' for ch in self.request_sha256)
                or not bounded(self.owner_trigger_ref, 2048) or self.authorized is not True):
            raise CandidateError('OWNER_STARTED_INVOCATION_REQUIRED')
        self.origin.validate()
        return self


@dataclass(frozen=True)
class Route:
    task_id: str
    request_sha256: str
    channel: ProjectChannel
    origin: Endpoint
    origin_project: ProjectRef | None
    owner_trigger_ref: str

    @property
    def route_digest(self):
        return digest(asdict(self))

    def ingress_binding(self):
        if self.origin == self.channel.executor:
            return None
        return LinkBinding(self.task_id, (self.origin, self.channel.executor)).validate()

    def review_binding(self):
        return LinkBinding(self.task_id, (self.channel.executor, self.channel.reviewer)).validate()

    def return_binding(self):
        return self.ingress_binding()


class CatalogPort(Protocol):
    def snapshot(self) -> Catalog: ...


class InvocationPort(Protocol):
    def current_invocation(self) -> Invocation: ...
