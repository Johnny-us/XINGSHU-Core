"""Codex 桌面目录薄适配，仅调用受支持项目/聊天清单。核心不依赖应用名。"""
import time
from urllib.parse import urlsplit
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.connections.codex_app_host import tool_json
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.state import digest
from .contracts import Catalog, Chat, Project, ProjectRef
from .mirror import ProjectCapabilities


class CodexAppCatalog:
    def __init__(self, call, *, account_scope, endpoint_overrides=None, clock=time.time):
        self.call, self.account_scope, self.clock = call, account_scope, clock
        self.endpoint_overrides = endpoint_overrides or {}

    @staticmethod
    def project_ref(row, scope):
        kind = row.get('projectKind')
        if kind not in ('local', 'remote', 'chatgpt'):
            raise CandidateError('NATIVE_PROJECT_KIND_UNSUPPORTED')
        return ProjectRef('CHATGPT' if kind == 'chatgpt' else 'CODEX', row['projectId'], scope,
                          row.get('hostId') or 'cloud').validate()

    def snapshot(self):
        observed_at = self.clock()
        projects = tool_json(self.call('list_projects', {}))
        threads = tool_json(self.call('list_threads', {'limit': 50}))
        if (type(projects.get('projects')) is not list or type(threads.get('threads')) is not list
                or type(threads.get('pinnedThreads')) is not list):
            raise CandidateError('NATIVE_PROJECT_CATALOG_INVALID')
        if threads.get('unavailableHosts') or threads.get('unavailableSources'):
            raise CandidateError('NATIVE_CATALOG_PARTIAL_STOP')
        ps = tuple(Project(self.project_ref(p, self.account_scope), p['label']) for p in projects['projects'])
        refs = {p.ref.project_id: p.ref for p in ps}
        if len(refs) != len(ps):
            raise CandidateError('NATIVE_PROJECT_ID_AMBIGUOUS')
        chats = []
        for c in threads['pinnedThreads'] + threads['threads']:
            kind = c.get('kind')
            if kind not in ('codex', 'chatgpt'):
                continue
            chat_id = c['id']
            ref = refs.get(c.get('projectId'))
            if c.get('projectId') and ref is None:
                raise CandidateError('NATIVE_CHAT_PROJECT_NOT_OBSERVED')
            if ref is not None and (ref.provider != ('CODEX' if kind == 'codex' else 'CHATGPT')
                    or ref.host_id != (c.get('hostId') or 'cloud')):
                raise CandidateError('NATIVE_CHAT_PROVIDER_OR_HOST_CONFLICT')
            default_uri = ('codex://threads/' if kind == 'codex' else 'https://chatgpt.com/c/') + chat_id
            endpoint = self.endpoint_overrides.get(chat_id) or Endpoint('CHAT_' + chat_id, 'ACTOR_' + chat_id, default_uri)
            uri = urlsplit(endpoint.resource_uri)
            if (not uri.path.endswith('/' + chat_id) or uri.query or uri.fragment
                    or (kind == 'codex' and (uri.scheme != 'codex' or uri.netloc != 'threads'))
                    or (kind == 'chatgpt' and (uri.scheme != 'https' or uri.netloc != 'chatgpt.com'))):
                raise CandidateError('NATIVE_CHAT_URI_IDENTITY_CONFLICT')
            chats.append(Chat(chat_id, ref, endpoint, c.get('status') or 'unknown', c.get('title')))
        evidence = 'native-project-catalog-sha256:' + digest({'projects': projects, 'threads': threads})
        return Catalog(ps, tuple(chats), evidence, observed_at).validate()

    @staticmethod
    def capabilities():
        # 当前工具清单只提供目录读取及移入已存在项目，不提供创建、改名或任务状态写入。
        return ProjectCapabilities(read=True, move_chat=True)
