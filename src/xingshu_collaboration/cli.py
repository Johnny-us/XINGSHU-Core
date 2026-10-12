"""Explicit foreground CLI; an authorized agent supplies native tool results."""
import argparse
from dataclasses import asdict
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .binding import CandidateError
from .connections.contracts import Endpoint
from .connections.codex_app_host import create_codex_app_port
from .connections.stdio_host import StdioHostCall
from .installation import Installation, checked_path, doctor, native_id, read_json, write_new
from .state import digest


class OfficialToolCall:
    """Transport timing belongs to the bridge, never to the official tool schema."""
    def __init__(self, callback, *, endpoint, codex_host_id):
        self.callback, self.endpoint, self.host_id = callback, endpoint, codex_host_id

    def __call__(self, method, params):
        if method not in ('read_thread', 'send_message_to_thread') or params.get('threadId') != native_id(self.endpoint):
            raise CandidateError('OFFICIAL_TOOL_SCOPE_CONFLICT')
        params = dict(params)
        if self.endpoint.resource_uri.startswith('codex://'):
            params['hostId'] = self.host_id
        return self.callback(method, params)


def send(installation, task_id, message_id, source, payload, callback):
    from .connections.ports import PortConnection, PortRegistry
    config, binding = installation.binding(task_id)
    target = next(e for e in binding.endpoints if e.endpoint_id != source)
    if source not in [e.endpoint_id for e in binding.endpoints]:
        raise CandidateError('SOURCE_NOT_REGISTERED')
    registry = PortRegistry()
    call = OfficialToolCall(callback, endpoint=target, codex_host_id=config['codex_host_id'])
    registry.register(create_codex_app_port(target, native_id(target), call))
    connection = PortConnection(binding, registry, installation.root / 'delivery',
                                project=config['logical_project_id'], relay_id='ONLINE_PAIR')
    return connection.send(message_id=message_id, source=source, target=target.endpoint_id, payload=payload)


def install_skill(destination):
    target = checked_path(destination)
    if target.name != 'xingshu-collaborate' or target.exists():
        raise CandidateError('NEW_NAMED_SKILL_DIRECTORY_REQUIRED')
    resource = files('xingshu_collaboration') / 'skill'
    contents = {name: resource.joinpath(name).read_bytes() for name in ('SKILL.md', 'agents/openai.yaml')}
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.xingshu-skill-', dir=target.parent) as temporary:
        staging = Path(temporary)
        for name, content in contents.items():
            output = staging / name
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            output.write_bytes(content)
        write_new(staging / '.xingshu-installed.json', {'schema': 'xingshu-collaboration-skill/1', 'version': __version__})
        # Reserve the destination without replacing an existing directory. The final rename
        # replaces only our empty reservation; a populated destination makes rename fail.
        target.mkdir(mode=0o700)
        try:
            staging.rename(target)
        except OSError:
            try: target.rmdir()
            except OSError: pass
            raise
    return {'installed': str(target), 'implicit_invocation': False, 'native_tools_installed': False}


def archive_skill(destination, archive_directory):
    target, archive = checked_path(destination), checked_path(archive_directory)
    if (target.name != 'xingshu-collaborate' or archive.exists()
            or archive == target or archive.is_relative_to(target) or target.is_relative_to(archive)
            or read_json(target / '.xingshu-installed.json').get('schema') != 'xingshu-collaboration-skill/1'):
        raise CandidateError('OWNED_SKILL_ARCHIVE_SCOPE_REQUIRED')
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Reversible removal from discovery. User edits and all local journals remain recoverable.
    target.rename(archive)
    return {'archived': str(archive), 'local_state_removed': False}


def parser():
    root = argparse.ArgumentParser(description='星枢在线对话协作：明确调用、先检查、再绑定。')
    root.add_argument('--version', action='version', version=__version__)
    subs = root.add_subparsers(dest='command', required=True)
    p = subs.add_parser('init'); p.add_argument('--directory', required=True)
    p = subs.add_parser('doctor'); p.add_argument('--directory'); p.add_argument('--inventory')
    p.add_argument('--stdio-host', action='store_true')
    p = subs.add_parser('bind'); p.add_argument('--directory', required=True)
    for key in ('project-id', 'codex-uri', 'web-uri', 'owner-ref'): p.add_argument('--'+key, required=True)
    p.add_argument('--codex-host-id', default='local')
    p = subs.add_parser('send'); p.add_argument('--directory', required=True)
    for key in ('task-id', 'message-id', 'source', 'payload-file'): p.add_argument('--'+key, required=True)
    p.add_argument('--stdio-host', action='store_true', required=True)
    p = subs.add_parser('status'); p.add_argument('--directory', required=True)
    p = subs.add_parser('checkpoint'); p.add_argument('--directory', required=True); p.add_argument('--packet-file', required=True)
    p = subs.add_parser('install-skill'); p.add_argument('--destination', required=True)
    p = subs.add_parser('uninstall-skill'); p.add_argument('--destination', required=True); p.add_argument('--archive-directory', required=True)
    return root


def run(args):
    if args.command == 'init':
        installed = Installation.initialize(args.directory)
        return {'initialized': str(installed.root), 'bound': False, 'background': False}
    if args.command == 'doctor':
        report = doctor(args.directory, read_json(Path(args.inventory)) if args.inventory else None)
        if args.stdio_host:
            installation = Installation(args.directory)
            config, binding = installation.binding('DOCTOR')
            callback = StdioHostCall()
            for endpoint in binding.endpoints:
                port = create_codex_app_port(endpoint, native_id(endpoint),
                    OfficialToolCall(callback, endpoint=endpoint, codex_host_id=config['codex_host_id']))
                port.preflight()
            report['actual_host_connectivity'] = True
            report['account_login_verified'] = True
        return report
    if args.command == 'install-skill': return install_skill(args.destination)
    if args.command == 'uninstall-skill': return archive_skill(args.destination, args.archive_directory)
    installation = Installation(args.directory)
    if args.command == 'bind':
        endpoints = (Endpoint('CODEX_DESKTOP', 'CODEX_AGENT', args.codex_uri),
                     Endpoint('WEB_CHATGPT', 'WEB_REVIEWER', args.web_uri))
        return installation.bind(args.project_id, endpoints, args.owner_ref, codex_host_id=args.codex_host_id)
    if args.command == 'send':
        payload_path = checked_path(args.payload_file)
        if not payload_path.is_file() or payload_path.stat().st_size > 16384:
            raise CandidateError('NATIVE_HOST_PAYLOAD_FILE_BOUND')
        return send(installation, args.task_id, args.message_id, args.source,
                    payload_path.read_bytes(), StdioHostCall())
    if args.command == 'status':
        from .state import SnapshotStore
        snapshots = installation.root / 'delivery' / 'snapshots'
        value = SnapshotStore(snapshots, installation.root).load() if snapshots.exists() else None
        return {'state': value, 'background': False, 'automatic_retry': False}
    if args.command == 'checkpoint':
        from .router.continuity import HandoffPacket
        document = read_json(checked_path(args.packet_file))
        document = dict(document)
        for key in ('original_origin', 'effective_origin'): document[key] = Endpoint(**document[key])
        document['authorized_source_refs'] = tuple(document['authorized_source_refs'])
        packet = HandoffPacket(**document).validate()
        directory = installation.root / 'handoffs'
        directory.mkdir(mode=0o700, exist_ok=True)
        output = directory / (packet.packet_sha256 + '.json')
        if output.exists():
            if digest(read_json(output)) != packet.packet_sha256: raise CandidateError('HANDOFF_DIGEST_CONFLICT')
        else: write_new(output, asdict(packet))
        return {'checkpoint': str(output), 'packet_sha256': packet.packet_sha256,
                'new_chat_created': False, 'binding_changed': False, 'handoff_accepted': False}
    raise CandidateError('COMMAND_UNSUPPORTED')


def main(argv=None):
    args = parser().parse_args(argv)
    terminal = None
    try:
        if os.name != 'posix' and (args.command != 'doctor' or getattr(args, 'stdio_host', False)):
            raise CandidateError('POSIX_HOST_REQUIRED')
        if getattr(args, 'stdio_host', False) and sys.stdin.isatty():
            import termios
            terminal = termios.tcgetattr(sys.stdin.fileno())
            mode = list(terminal)
            mode[3] &= ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, mode)
        result = run(args)
        print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False))
        if args.command == 'doctor' and not result['ready_to_attempt_online_workflow']: return 2
        return 0
    except (CandidateError, OSError, ValueError, TypeError, KeyError) as error:
        # A failed call can already have crossed the host boundary. Never retry or infer non-delivery.
        print(json.dumps({'error': str(error), 'automatic_retry': False,
                          'instruction': '停止；读取本机日志核对。失败不等于未发送。'}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if terminal is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, terminal)
