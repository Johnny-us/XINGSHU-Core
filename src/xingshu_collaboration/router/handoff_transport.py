"""接续传递复用通用连接：交接包和两向探针固定 ID，不发送第二遍业务目标。"""
from dataclasses import asdict
from pathlib import Path
import hashlib
from xingshu_collaboration.connections.contracts import LinkBinding
from xingshu_collaboration.connections.ports import PortConnection
from xingshu_collaboration.state import SnapshotStore, digest, encode
from .continuity import DirectionProof, probe_payload
from .lifecycle import require


class HandoffTransport:
    def __init__(self, registry, state_root):
        self.registry, self.state_root = registry, Path(state_root)

    def _connection(self, packet, source, target):
        binding = LinkBinding(packet.task_id, (source, target)).validate()
        root = self.state_root / 'handoff_delivery' / digest(dict(task=packet.task_id,
            packet=packet.packet_sha256, source=asdict(source), target=asdict(target)))[:32]
        return PortConnection(binding, self.registry, root,
            project=packet.logical_project_id, relay_id='PROJECT_HANDOFF_HOST'), root

    def send_packet(self, packet, source, target):
        connection, _ = self._connection(packet, source, target)
        payload = encode(dict(kind='CONTINUE_EXISTING_TASK', packet=asdict(packet.validate()),
                              packet_sha256=packet.packet_sha256, execute_business_goal=False))
        return connection.send(message_id='PACKET_' + digest(dict(packet=packet.packet_sha256,
            source=asdict(source), target=asdict(target)))[:48], source=source.endpoint_id,
            target=target.endpoint_id, payload=payload)

    def probe(self, packet, source, target):
        connection, root = self._connection(packet, source, target)
        payload = probe_payload(packet.task_id, packet.packet_sha256, source, target)
        message_id = 'PROBE_' + digest(dict(packet=packet.packet_sha256, source=asdict(source), target=asdict(target)))[:48]
        result = connection.send(message_id=message_id, source=source.endpoint_id, target=target.endpoint_id, payload=payload)
        # 原存储中的实际新增输入证据，与业务 Review / 模型实读分别记录。
        state = SnapshotStore(root / 'snapshots', root.parent).load()
        entry = state['seen_events'][message_id]
        require(entry['status'] == 'ACKED' and entry.get('submission_known') is True,
                'PROBE_ACTUAL_INPUT_UNCONFIRMED')
        proof = DirectionProof(packet.task_id, packet.packet_sha256, source, target, message_id,
            hashlib.sha256(payload).hexdigest(), entry['native_submission_id'], entry['observation_evidence_ref'])
        return result, proof
