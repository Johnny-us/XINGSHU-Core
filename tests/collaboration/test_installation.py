"""Synthetic host fixtures; none of these tests contact or authenticate a real account."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.cli import OfficialToolCall, archive_skill, install_skill, send
from xingshu_collaboration.connections.codex_app_host import create_codex_app_port, tool_json
from xingshu_collaboration.connections.contracts import Endpoint
from xingshu_collaboration.connections.stdio_host import StdioHostCall
from xingshu_collaboration.installation import Installation, doctor, native_id, read_json
from xingshu_collaboration.state import SnapshotStore

CODEX = '11111111-1111-1111-1111-111111111111'
WEB = '22222222-2222-2222-2222-222222222222'
PAIR = (Endpoint('CODEX_DESKTOP', 'CODEX_AGENT', 'codex://threads/' + CODEX),
        Endpoint('WEB_CHATGPT', 'WEB_REVIEWER', 'https://chatgpt.com/c/' + WEB))


class SyntheticHost:
    def __init__(self):
        self.sent = []
        self.records = []
        self.status = 'idle'
        self.fail_after_submission = False

    def __call__(self, method, params):
        if method == 'send_message_to_thread':
            self.sent.append(dict(params))
            if self.fail_after_submission:
                self.status = 'systemError'
            else:
                self.records.append({'type': 'userMessage', 'id': 'INPUT_' + str(len(self.sent)),
                    'content': [{'type': 'text', 'text': params['prompt']}]})
            return {'content': [{'type': 'text', 'text': json.dumps({'threadId': params['threadId']})}]}
        result = {'thread': {'id': params['threadId'], 'kind': 'chatgpt' if params['threadId'] == WEB else 'codex',
                             'status': {'type': self.status, 'activeFlags': []}},
                  'turns': [{'id': 'TURN_1', 'status': 'completed', 'items': self.records}]}
        return {'structuredContent': result}


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.installation = Installation.initialize(self.base / 'machine')

    def tearDown(self): self.tmp.cleanup()

    def bind(self): return self.installation.bind('MY_PROJECT', PAIR, 'test://human-authorization')

    def test_initialization_never_binds_or_starts_a_service(self):
        self.assertEqual({p.name for p in self.installation.root.iterdir()}, {'installation.json'})
        self.assertFalse(doctor()['actual_host_connectivity'])

    def test_initialization_cannot_overwrite_existing_material(self):
        with self.assertRaisesRegex(CandidateError, 'EMPTY_NEW'):
            Installation.initialize(self.installation.root)

    def test_relative_directory_rejected(self):
        with self.assertRaisesRegex(CandidateError, 'ABSOLUTE'):
            Installation.initialize(Path('relative'))

    def test_symlink_ancestor_rejected(self):
        link = self.base / 'link'; link.symlink_to(self.installation.root, target_is_directory=True)
        with self.assertRaisesRegex(CandidateError, 'SYMLINK'):
            Installation.initialize(link / 'child')

    def test_configuration_has_machine_specific_identity_and_no_credentials(self):
        config = self.bind()
        self.assertEqual(config['installation_id'], self.installation.installation_id)
        self.assertEqual(self.installation.binding('TASK')[1].endpoints, PAIR)
        self.assertNotIn('token', config)

    def test_existing_binding_is_never_overwritten(self):
        self.bind()
        original = (self.installation.root / 'binding.json').read_bytes()
        with self.assertRaises(FileExistsError): self.bind()
        self.assertEqual((self.installation.root / 'binding.json').read_bytes(), original)

    def test_uri_provider_swap_rejected(self):
        with self.assertRaisesRegex(CandidateError, 'PROVIDER_PAIR'):
            self.installation.bind('MY_PROJECT', (replace(PAIR[0], resource_uri=PAIR[1].resource_uri),
                replace(PAIR[1], resource_uri=PAIR[0].resource_uri)), 'test://human')

    def test_empty_authorization_reference_rejected(self):
        with self.assertRaisesRegex(CandidateError, 'SCOPE'):
            self.installation.bind('MY_PROJECT', PAIR, '')

    def test_copied_machine_config_rejected(self):
        self.bind()
        other = Installation.initialize(self.base / 'other')
        (other.root / 'binding.json').write_bytes((self.installation.root / 'binding.json').read_bytes())
        with self.assertRaisesRegex(CandidateError, 'LOCAL_BINDING'):
            other.binding('TASK')

    def test_extra_config_authority_rejected(self):
        value = self.bind(); value['execute_authority'] = True
        (self.installation.root / 'binding.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(CandidateError, 'LOCAL_BINDING'):
            self.installation.binding('TASK')

    def test_reported_tool_inventory_is_not_login_or_connectivity_proof(self):
        self.bind()
        report = doctor(self.installation.root, {'tools': ['mcp__app__' + n for n in
            ['read_thread', 'send_message_to_thread', 'list_projects', 'list_threads']]})
        self.assertTrue(report['ready_to_attempt_online_workflow'])
        self.assertFalse(report['actual_host_connectivity'])
        self.assertFalse(report['account_login_verified'])
        self.assertFalse(report['web_direct_dispatch_verified'])

    def test_missing_send_tool_is_reported(self):
        self.bind()
        self.assertIn('send_message_to_thread', doctor(self.installation.root, {'tools': ['read_thread']})['missing_tools'])

    def test_send_observes_input_but_does_not_claim_review(self):
        self.bind(); host = SyntheticHost()
        result = send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original\r\n', host)
        self.assertTrue(result['result']['delivered'])
        self.assertEqual(host.sent[0]['prompt'], 'synthetic original\r\n')
        self.assertFalse(result['model_turn_consumed'])

    def test_repeated_message_does_not_submit_twice(self):
        self.bind(); host = SyntheticHost()
        send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        result = send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        self.assertTrue(result['result']['duplicate']); self.assertEqual(len(host.sent), 1)

    def test_host_error_after_acceptance_is_persisted_and_not_retried(self):
        self.bind(); host = SyntheticHost(); host.fail_after_submission = True
        with self.assertRaisesRegex(CandidateError, 'SYSTEM_ERROR'):
            send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        state = SnapshotStore(self.installation.root / 'delivery/snapshots', self.installation.root).load()
        self.assertEqual(state['seen_events']['MESSAGE']['status'], 'UNCERTAIN')
        self.assertTrue(state['seen_events']['MESSAGE']['host_acceptance_ref'])
        host.status = 'idle'; host.fail_after_submission = False
        with self.assertRaisesRegex(CandidateError, 'UNCERTAIN'):
            send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        self.assertEqual(len(host.sent), 1)

    def test_active_host_with_old_completed_turn_blocks_before_submit(self):
        self.bind(); host = SyntheticHost(); host.status = 'active'
        with self.assertRaisesRegex(CandidateError, 'BUSY'):
            send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        self.assertEqual(host.sent, [])

    def test_host_system_error_blocks_before_submit(self):
        self.bind(); host = SyntheticHost(); host.status = 'systemError'
        with self.assertRaisesRegex(CandidateError, 'SYSTEM_ERROR'):
            send(self.installation, 'TASK', 'MESSAGE', 'CODEX_DESKTOP', b'synthetic original', host)
        self.assertEqual(host.sent, [])

    def test_official_callback_cannot_route_to_a_third_thread(self):
        callback = OfficialToolCall(lambda *_: self.fail('callback must not run'), endpoint=PAIR[0], codex_host_id='local')
        with self.assertRaisesRegex(CandidateError, 'SCOPE'):
            callback('read_thread', {'threadId': WEB})

    def test_codex_host_is_explicit_and_web_receives_no_codex_host_parameter(self):
        received = []
        for endpoint in PAIR:
            call = OfficialToolCall(lambda m, p: received.append(p), endpoint=endpoint, codex_host_id='HOST_A')
            call('read_thread', {'threadId': native_id(endpoint), 'timeout_ms': 1000})
        self.assertEqual(received[0]['hostId'], 'HOST_A')
        self.assertNotIn('hostId', received[1])

    def test_explicit_protected_root_rejected_before_mkdir(self):
        protected = self.base / 'protected'
        with self.assertRaisesRegex(CandidateError, 'PATH_REJECTED'):
            SnapshotStore(protected / 'state', self.base, protected_roots=(protected,))
        self.assertFalse(protected.exists())

    def test_ambiguous_allowed_root_rejected(self):
        with self.assertRaisesRegex(CandidateError, 'PATH_REJECTED'):
            SnapshotStore(self.base / 'state', self.base / 'untrusted' / '..')

    def test_skill_install_and_reversible_uninstall_preserve_edits(self):
        destination = self.base / '.agents/skills/xingshu-collaborate'
        install_skill(destination)
        self.assertIn('allow_implicit_invocation: false', (destination / 'agents/openai.yaml').read_text())
        edited = destination / 'owner-note.txt'; edited.write_text('synthetic note')
        archive = self.base / 'disabled/xingshu-collaborate'
        archive_skill(destination, archive)
        self.assertFalse(destination.exists()); self.assertEqual((archive / 'owner-note.txt').read_text(), 'synthetic note')

    def test_skill_install_does_not_overwrite_existing_skill(self):
        destination = self.base / 'xingshu-collaborate'; destination.mkdir()
        with self.assertRaisesRegex(CandidateError, 'NEW_NAMED'):
            install_skill(destination)

    def test_foreign_skill_directory_cannot_be_archived(self):
        destination = self.base / 'xingshu-collaborate'; destination.mkdir()
        with self.assertRaises(OSError): archive_skill(destination, self.base / 'archive')


class ToolResultTests(unittest.TestCase):
    def test_structured_only_result_supported(self):
        self.assertEqual(tool_json({'structuredContent': {'ok': True}}), {'ok': True})

    def test_conflicting_text_and_structured_result_rejected(self):
        with self.assertRaises(CandidateError):
            tool_json({'structuredContent': {'ok': False}, 'content': [{'type': 'text', 'text': '{"ok":true}'}]})

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(CandidateError):
            tool_json({'content': [{'type': 'text', 'text': '{"ok":true,"ok":false}'}]})

    def test_truncated_user_input_cannot_be_an_observation(self):
        host = SyntheticHost(); host.records = [{'type': 'userMessage', 'id': 'X', 'truncated': True,
            'content': [{'type': 'text', 'text': 'partial'}]}]
        port = create_codex_app_port(PAIR[1], WEB, host)
        with self.assertRaisesRegex(CandidateError, 'TRUNCATED'):
            port.preflight()

    def test_wire_timing_is_not_passed_to_native_tool(self):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b'{"jsonrpc":"2.0","id":1,"result":{}}\n'); os.close(write_fd)
        output = io.StringIO()
        with os.fdopen(read_fd) as stream:
            StdioHostCall(stream, output)('read_thread', {'threadId': WEB, 'timeout_ms': 1000})
        request = json.loads(output.getvalue())
        self.assertEqual(request['timeout_ms'], 1000)
        self.assertNotIn('timeout_ms', request['params'])
