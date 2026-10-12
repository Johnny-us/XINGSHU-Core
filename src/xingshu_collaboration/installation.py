"""Machine-local opt-in configuration. Importing or installing never binds a chat."""
from dataclasses import asdict
import os
from pathlib import Path
import re
import stat
import uuid

from .binding import CandidateError, identity
from .connections.contracts import Endpoint, LinkBinding
from .connections.codex_app_host import create_codex_app_port
from .state import encode, strict_json

SCHEMA = 'xingshu-collaboration-installation/1'
BINDING_SCHEMA = 'xingshu-collaboration-binding/1'
REQUIRED_TOOLS = ('read_thread', 'send_message_to_thread', 'list_projects', 'list_threads')


def checked_path(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise CandidateError('ABSOLUTE_OWNED_DIRECTORY_REQUIRED')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise CandidateError('INSTALLATION_SYMLINK_REJECTED')
    return path


def read_json(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1048576:
        raise CandidateError('LOCAL_FILE_IDENTITY_OR_SIZE_REJECTED')
    return strict_json(path.read_bytes())


def write_new(path, value):
    checked_path(path)
    data = encode(value)
    if len(data) > 1048576:
        raise CandidateError('LOCAL_FILE_TOO_LARGE')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def native_id(endpoint):
    endpoint.validate()
    value = endpoint.resource_uri.rsplit('/', 1)[-1]
    # Reuse the adapter's exact URI/type binding check, without performing a tool call.
    create_codex_app_port(endpoint, value, lambda *_: None)
    return value


class Installation:
    def __init__(self, directory):
        self.root = checked_path(directory)
        marker = read_json(self.root / 'installation.json')
        if (type(marker) is not dict or set(marker) != {'schema', 'installation_id'}
                or marker['schema'] != SCHEMA
                or not re.fullmatch(r'[0-9a-f]{32}', str(marker['installation_id']))):
            raise CandidateError('INSTALLATION_MARKER_INVALID')
        self.installation_id = marker['installation_id']

    @classmethod
    def initialize(cls, directory):
        root = checked_path(directory)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise CandidateError('EMPTY_NEW_INSTALLATION_DIRECTORY_REQUIRED')
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_new(root / 'installation.json', {'schema': SCHEMA, 'installation_id': uuid.uuid4().hex})
        return cls(root)

    def bind(self, project_id, endpoints, owner_ref, *, codex_host_id='local'):
        binding = LinkBinding('BINDING_CHECK', tuple(endpoints)).validate()
        if (not identity(project_id) or type(owner_ref) is not str or not 0 < len(owner_ref) <= 2048
                or type(codex_host_id) is not str or not 0 < len(codex_host_id) <= 128):
            raise CandidateError('BINDING_SCOPE_REQUIRED')
        if tuple(e.endpoint_id for e in binding.endpoints) != ('CODEX_DESKTOP', 'WEB_CHATGPT'):
            raise CandidateError('EXPLICIT_CODEX_WEB_PAIR_REQUIRED')
        for endpoint in endpoints:
            native_id(endpoint)
        if not endpoints[0].resource_uri.startswith('codex://') or not endpoints[1].resource_uri.startswith('https://chatgpt.com/'):
            raise CandidateError('NATIVE_PROVIDER_PAIR_REQUIRED')
        document = {'schema': BINDING_SCHEMA, 'installation_id': self.installation_id,
                    'logical_project_id': project_id, 'endpoints': [asdict(e) for e in endpoints],
                    'codex_host_id': codex_host_id, 'owner_authorization_ref': owner_ref}
        # Existing registrations are never overwritten or silently advanced to a new generation.
        write_new(self.root / 'binding.json', document)
        return document

    def binding(self, task_id):
        value = read_json(self.root / 'binding.json')
        keys = {'schema', 'installation_id', 'logical_project_id', 'endpoints',
                'codex_host_id', 'owner_authorization_ref'}
        if (type(value) is not dict or set(value) != keys or value['schema'] != BINDING_SCHEMA
                or value['installation_id'] != self.installation_id
                or not identity(value['logical_project_id']) or type(value['endpoints']) is not list
                or len(value['endpoints']) != 2
                or type(value['codex_host_id']) is not str or not value['codex_host_id']
                or type(value['owner_authorization_ref']) is not str or not value['owner_authorization_ref']):
            raise CandidateError('LOCAL_BINDING_INVALID')
        try:
            endpoints = tuple(Endpoint(**e) for e in value['endpoints'])
        except (TypeError, ValueError):
            raise CandidateError('LOCAL_BINDING_INVALID')
        binding = LinkBinding(task_id, endpoints).validate()
        if tuple(e.endpoint_id for e in endpoints) != ('CODEX_DESKTOP', 'WEB_CHATGPT'):
            raise CandidateError('EXPLICIT_CODEX_WEB_PAIR_REQUIRED')
        for e in endpoints:
            native_id(e)
        if not endpoints[0].resource_uri.startswith('codex://') or not endpoints[1].resource_uri.startswith('https://chatgpt.com/'):
            raise CandidateError('NATIVE_PROVIDER_PAIR_REQUIRED')
        return value, binding


def doctor(directory=None, inventory=None):
    report = {'schema': 'xingshu-collaboration-doctor/1', 'platform_supported': os.name == 'posix',
              'bound': False, 'host_tools_reported': False, 'actual_host_connectivity': False,
              'ready_to_attempt_online_workflow': False, 'background': False,
              'account_login_verified': False, 'web_direct_dispatch_verified': False}
    if directory is not None:
        Installation(directory).binding('DOCTOR')
        report['bound'] = True
    names = inventory.get('tools', []) if type(inventory) is dict else []
    if type(names) is not list or any(type(n) is not str for n in names):
        raise CandidateError('HOST_TOOL_INVENTORY_INVALID')
    report['missing_tools'] = [name for name in REQUIRED_TOOLS
                               if not any(n == name or n.endswith('__' + name) for n in names)]
    report['host_tools_reported'] = not report['missing_tools']
    report['ready_to_attempt_online_workflow'] = report['platform_supported'] and report['bound'] and report['host_tools_reported']
    return report
