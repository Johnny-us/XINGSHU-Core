"""两端换页：检查点、同版本实读、双向实证、候选登记原子切换。"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import math
import hashlib
import time
from .contracts import ProjectChannel, CurrentChatChannel, ProjectRef, bounded
from .lifecycle import require, sha
from xingshu_collaboration.connections.contracts import Endpoint, LinkBinding
from xingshu_collaboration.binding import identity
from xingshu_collaboration.state import digest, encode, strict_json


def doc(obj):
    return strict_json(encode(asdict(obj)))


def registration_key(channel):
    return channel.mirror_id if type(channel) is CurrentChatChannel else channel.logical_project_id


def project_doc(project):
    return asdict(project) if project is not None else None


def probe_payload(task_id, packet_sha256, source, target):
    return encode(dict(kind='HANDOFF_DIRECTION_PROBE', task_id=task_id,
        packet_sha256=packet_sha256, source=asdict(source), target=asdict(target)))


@dataclass(frozen=True)
class ContextSignal:
    endpoint: Endpoint
    kind: str  # USAGE / CONTEXT_LIMIT / OWNER_HANDOFF / UNKNOWN
    observed_at: float
    evidence_ref: str
    used_tokens: int | None = None
    capacity_tokens: int | None = None


def continuation_action(signal, *, now, compact_supported=False):
    """没有真实容量时不猜剩余上下文；系统故障不是上下文已满。"""
    require(type(signal) is ContextSignal, 'HOST_CONTEXT_SIGNAL_REQUIRED')
    signal.endpoint.validate()
    require(type(signal.observed_at) in (int, float) and math.isfinite(signal.observed_at)
            and 0 <= now - signal.observed_at <= 120 and bounded(signal.evidence_ref, 2048), 'CONTEXT_SIGNAL_STALE_OR_INVALID')
    require(type(compact_supported) is bool, 'COMPACTION_CAPABILITY_INVALID')
    if signal.kind == 'UNKNOWN':
        return 'SAVE_CHECKPOINT_CONTEXT_UNKNOWN'
    if signal.kind == 'OWNER_HANDOFF':
        return 'PREPARE_SUCCESSOR'
    if signal.kind == 'CONTEXT_LIMIT':
        return 'COMPACT_THEN_VERIFY' if compact_supported else 'PREPARE_SUCCESSOR'
    require(signal.kind == 'USAGE' and type(signal.used_tokens) is int
            and type(signal.capacity_tokens) is int and 0 <= signal.used_tokens <= signal.capacity_tokens
            and signal.capacity_tokens > 0, 'CONTEXT_USAGE_UNVERIFIED')
    if signal.used_tokens / signal.capacity_tokens < 0.85:
        return 'CONTINUE_CURRENT'
    return 'COMPACT_THEN_VERIFY' if compact_supported else 'PREPARE_SUCCESSOR'


@dataclass(frozen=True)
class HandoffPacket:
    task_id: str
    logical_project_id: str
    request_sha256: str
    old_channel_sha256: str
    original_origin: Endpoint
    effective_origin: Endpoint
    work_version: str
    artifact_sha256: str
    status: str
    summary: str
    next_step: str
    checkpoint_ref: str
    authorized_source_refs: tuple
    authority_scope_ref: str
    protocol_sha256: str
    owner_trigger_ref: str

    def validate(self):
        require(identity(self.task_id) and identity(self.logical_project_id) and identity(self.work_version)
                and identity(self.status) and all(sha(v) for v in (self.request_sha256, self.old_channel_sha256,
                self.artifact_sha256, self.protocol_sha256)) and bounded(self.summary, 4096)
                and bounded(self.next_step, 1024) and bounded(self.checkpoint_ref, 2048)
                and bounded(self.authority_scope_ref, 2048) and bounded(self.owner_trigger_ref, 2048), 'HANDOFF_PACKET_INVALID')
        require(type(self.authorized_source_refs) is tuple and len(self.authorized_source_refs) <= 16
                and all(bounded(v, 2048) for v in self.authorized_source_refs), 'HANDOFF_SOURCE_SCOPE_INVALID')
        self.original_origin.validate(); self.effective_origin.validate()
        require(len(encode(asdict(self))) <= 16384, 'HANDOFF_PACKET_TOO_LARGE')
        return self

    @property
    def packet_sha256(self):
        return digest(asdict(self.validate()))


@dataclass(frozen=True)
class DrainProof:
    """宿主在旧消息存储锁内读取完整未确认列表；不是接收模型的自述。"""
    channel_sha256: str
    unresolved_message_ids: tuple
    complete: bool
    observed_at: float
    evidence_ref: str


@dataclass(frozen=True)
class HandoffRead:
    task_id: str
    packet_sha256: str
    endpoint: Endpoint
    work_version: str
    artifact_sha256: str
    protocol_sha256: str
    native_input_id: str
    native_turn_id: str
    native_output_id: str
    evidence_ref: str


@dataclass(frozen=True)
class DirectionProof:
    """两方向真实宿主投递与输入观测，绑定同一交接包和新端点。"""
    task_id: str
    packet_sha256: str
    source: Endpoint
    target: Endpoint
    message_id: str
    payload_sha256: str
    native_input_id: str
    evidence_ref: str


class ContinuityManager:
    """本实现只写候选登记；正式固定配置由单独验收／采用适配器负责。"""
    def __init__(self, journal, catalog_port, *, clock=time.time):
        self.journal, self.catalog_port, self.clock = journal, catalog_port, clock

    def catalog(self):
        c = self.catalog_port.snapshot().validate()
        age = self.clock() - c.observed_at
        require(math.isfinite(age) and 0 <= age <= 120, 'CONTINUITY_CATALOG_STALE')
        return c

    def observe_channel(self, channel, *, ready=False):
        channel.validate(); c = self.catalog()
        for p in channel.projects:
            if p is not None:
                c.project(p)
        for e, p in zip((channel.executor, channel.reviewer), channel.projects):
            chat = c.chat(e)
            require(chat.project == p, 'CONTINUITY_PROJECT_MEMBERSHIP_CONFLICT')
            if type(channel) is CurrentChatChannel and e == channel.reviewer:
                require(chat.title == channel.topic_name, 'CURRENT_CHAT_SUCCESSOR_TOPIC_CHANGED')
            if ready:
                current_owned = type(channel) is CurrentChatChannel and e == channel.executor
                require(chat.status in ('idle', 'completed') or current_owned and chat.status == 'active',
                        'SUCCESSOR_OR_OLD_HOST_NOT_QUIESCENT')
        return c

    def seed_candidate(self, channel):
        """从已验证原登记导入候选；不是修改正式端点。"""
        self.observe_channel(channel)
        with self.journal.locked() as state:
            prior = state['registrations'].get(registration_key(channel))
            require(prior is None or prior['channel'] == doc(channel), 'CANDIDATE_REGISTRATION_CONFLICT')
            if prior is None:
                state['registrations'][registration_key(channel)] = dict(channel=doc(channel), history=[], returns={})
                self.journal.store.save(state)

    def _drained(self, proof, channel):
        require(type(proof) is DrainProof and proof.channel_sha256 == digest(asdict(channel))
                and proof.complete is True and type(proof.unresolved_message_ids) is tuple
                and not proof.unresolved_message_ids and type(proof.observed_at) in (int, float)
                and math.isfinite(proof.observed_at) and 0 <= self.clock() - proof.observed_at <= 120
                and bounded(proof.evidence_ref, 2048), 'OLD_DELIVERIES_NOT_PROVEN_DRAINED')

    def _proposal(self, state, transition_id):
        entry = state['successors'].get(transition_id)
        require(entry is not None, 'SUCCESSOR_PROPOSAL_MISSING')
        return entry

    def _confirmed_operations(self, state, channel):
        refs = [asdict(p) for p in channel.projects if p is not None]
        require(not any(v['status'] != 'APPLIED_VERIFIED' and (
            v['spec'].get('logical_project_id') == channel.logical_project_id or v['spec'].get('project') in refs)
            for v in state['operations'].values()), 'LIFECYCLE_OPERATION_UNCONFIRMED')

    def required_reads(self, entry):
        endpoints = {Endpoint(**entry['new']['executor']), Endpoint(**entry['new']['reviewer'])}
        origin = Endpoint(**entry['new_origin'])
        if origin != Endpoint(**entry['packet']['effective_origin']):
            endpoints.add(origin)
        return endpoints

    def propose(self, old, new, packet, drain, *, new_origin=None):
        require(type(old) in (ProjectChannel, CurrentChatChannel) and type(new) is type(old)
                and type(packet) is HandoffPacket,
                'TRUSTED_SUCCESSOR_OBJECTS_REQUIRED')
        packet.validate(); self.observe_channel(old, ready=True); self.observe_channel(new, ready=True)
        self._drained(drain, old)
        require(new.logical_project_id == old.logical_project_id == packet.logical_project_id
                and new.projects == old.projects and new.desired_name == old.desired_name
                and new.generation == old.generation + 1 and new.registration_ref != old.registration_ref
                and packet.old_channel_sha256 == digest(asdict(old)), 'SUCCESSOR_CHANNEL_SCOPE_CONFLICT')
        pairs = ((old.executor, new.executor), (old.reviewer, new.reviewer))
        require(any(a != b for a, b in pairs) and all(a == b or b.resource_uri not in (
                old.executor.resource_uri, old.reviewer.resource_uri) for a, b in pairs), 'SUCCESSOR_ENDPOINT_MUST_BE_NEW')
        require(all(c.name == new.desired_name for c in (self.catalog().project(p) for p in new.projects if p is not None)),
                'SUCCESSOR_PROJECT_NAMES_NOT_MIRRORED')
        if type(old) is CurrentChatChannel:
            require(new.current_scope == old.current_scope and new.topic_name == old.topic_name and new.mirror_id == old.mirror_id,
                    'CURRENT_CHAT_SUCCESSOR_SCOPE_CHANGED')
            require(self.catalog().chat(new.reviewer).title == new.topic_name,
                    'CURRENT_CHAT_SUCCESSOR_TOPIC_CHANGED')
        if new_origin is None:
            new_origin = new.executor if packet.effective_origin == old.executor else (
                new.reviewer if packet.effective_origin == old.reviewer else packet.effective_origin)
        new_origin.validate()
        c = self.catalog()
        old_origin = c.chat(packet.effective_origin)
        if type(old) is CurrentChatChannel:
            require(packet.effective_origin == old.executor and new_origin == new.executor,
                    'CURRENT_CHAT_RETURN_MUST_FOLLOW_VERIFIED_EXECUTOR')
        require(c.chat(new_origin).project == old_origin.project and old_origin.project in old.projects,
                'SUCCESSOR_RETURN_PROJECT_CONFLICT')
        if packet.original_origin != packet.effective_origin:
            c.chat(packet.original_origin)  # 原始来源记录仍可观测，不删除旧聊天。
        retired = {a.resource_uri for a,b in pairs if a != b}
        require(new_origin.resource_uri not in retired,
                'RETURN_ADDRESS_STILL_POINTS_AT_RETIRED_ENDPOINT')
        transition_id = 'HANDOFF_' + digest(dict(packet=packet.packet_sha256, new=asdict(new), origin=asdict(new_origin)))[:48]
        with self.journal.locked() as state:
            self._confirmed_operations(state, old)
            registration = state['registrations'].get(registration_key(old))
            require(registration is not None and registration['channel'] == doc(old), 'OLD_REGISTRATION_CHANGED')
            previous_return = registration['returns'].get(packet.task_id)
            if previous_return:
                require(previous_return['original'] == asdict(packet.original_origin)
                        and previous_return['effective'] == asdict(packet.effective_origin)
                        and previous_return['request_sha256'] == packet.request_sha256, 'RETURN_LINEAGE_CONFLICT')
                require(previous_return['project'] == project_doc(old_origin.project), 'RETURN_LINEAGE_PROJECT_CHANGED')
            else:
                require(packet.original_origin == packet.effective_origin, 'ORIGINAL_ORIGIN_CANNOT_BE_INVENTED')
            entry = state['successors'].get(transition_id)
            if entry:
                require(entry['packet'] == doc(packet), 'HANDOFF_INTENT_CHANGED')
                return transition_id
            # 同一个旧登记只允许一个在途接续，防止两人同时建不同新页。
            require(not any(e['old'] == doc(old) and e['status'] != 'CUTOVER_COMMITTED'
                            for e in state['successors'].values()), 'OTHER_SUCCESSOR_IN_FLIGHT')
            state['successors'][transition_id] = dict(old=doc(old), new=doc(new), packet=doc(packet),
                packet_sha256=packet.packet_sha256, new_origin=asdict(new_origin),
                return_project=previous_return['project'] if previous_return else project_doc(old_origin.project),
                reads={}, directions={}, status='PREPARED')
            self.journal.store.save(state)
        return transition_id

    def observe_read(self, transition_id, proof):
        require(type(proof) is HandoffRead, 'ACTUAL_HANDOFF_READ_REQUIRED')
        with self.journal.locked() as state:
            e = self._proposal(state, transition_id); p = e['packet']
            require(e['status'] != 'CUTOVER_COMMITTED' and proof.endpoint in self.required_reads(e)
                and proof.task_id == p['task_id'] and proof.packet_sha256 == e['packet_sha256']
                and proof.work_version == p['work_version'] and proof.artifact_sha256 == p['artifact_sha256']
                and proof.protocol_sha256 == p['protocol_sha256']
                and all(bounded(v, 2048) for v in (proof.native_input_id, proof.native_turn_id,
                    proof.native_output_id, proof.evidence_ref)), 'HANDOFF_READ_VERSION_OR_ENDPOINT_CONFLICT')
            # 实读不自动升级为工作版本验收 PASS。
            e['reads'][proof.endpoint.endpoint_id] = asdict(proof)
            self.journal.store.save(state)

    def observe_direction(self, transition_id, proof):
        require(type(proof) is DirectionProof, 'ACTUAL_DIRECTION_PROOF_REQUIRED')
        with self.journal.locked() as state:
            e = self._proposal(state, transition_id)
            binding = LinkBinding(e['packet']['task_id'], (Endpoint(**e['new']['executor']), Endpoint(**e['new']['reviewer']))).validate()
            require(e['status'] != 'CUTOVER_COMMITTED' and proof.source in binding.endpoints and proof.target in binding.endpoints
                    and proof.source != proof.target and proof.task_id == e['packet']['task_id']
                    and proof.packet_sha256 == e['packet_sha256'] and proof.payload_sha256 == hashlib.sha256(
                        probe_payload(proof.task_id, proof.packet_sha256, proof.source, proof.target)).hexdigest()
                    and proof.message_id == 'PROBE_' + digest(dict(packet=proof.packet_sha256, source=asdict(proof.source), target=asdict(proof.target)))[:48]
                    and identity(proof.message_id) and bounded(proof.native_input_id, 256)
                    and bounded(proof.evidence_ref, 2048), 'SUCCESSOR_DIRECTION_CONFLICT')
            e['directions'][proof.source.endpoint_id] = asdict(proof)
            self.journal.store.save(state)

    def commit_candidate(self, transition_id, drain):
        with self.journal.locked() as state:
            e = self._proposal(state, transition_id)
            old = channel_from_dict(e['old']); new = channel_from_dict(e['new'])
            self._confirmed_operations(state, old)
            reg = state['registrations'][registration_key(old)]
            if e['status'] == 'CUTOVER_COMMITTED':
                require(reg['channel'] == e['new'], 'COMMITTED_REGISTRATION_DRIFT')
                return new
            require(reg['channel'] == e['old'], 'CUTOVER_COMPARE_AND_SWAP_FAILED')
            self._drained(drain, old)
            self.observe_channel(old, ready=True); self.observe_channel(new, ready=True)
            expected_return_project = ProjectRef(**e['return_project']) if e['return_project'] is not None else None
            require(self.catalog().chat(Endpoint(**e['new_origin'])).project == expected_return_project,
                    'RESULT_RETURN_PROJECT_CHANGED')
            require(set(e['reads']) == {r.endpoint_id for r in self.required_reads(e)}
                    and set(e['directions']) == {new.executor.endpoint_id, new.reviewer.endpoint_id},
                    'BOTH_READS_AND_DIRECTIONS_REQUIRED')
            require(len({r['native_input_id'] for r in e['reads'].values()}) == len(self.required_reads(e))
                    and len({r['native_input_id'] for r in e['directions'].values()}) == 2
                    and len({r['message_id'] for r in e['directions'].values()}) == 2, 'HANDOFF_RECEIPTS_AMBIGUOUS')
            p = e['packet']
            # 一个追加快照同时提交登记、返回地址和历史，防止只切一端。
            reg['history'].append(dict(channel=e['old'], transition_id=transition_id, packet_sha256=e['packet_sha256']))
            reg['channel'] = e['new']
            reg['returns'][p['task_id']] = dict(original=p['original_origin'], effective=e['new_origin'],
                request_sha256=p['request_sha256'], work_version=p['work_version'], artifact_sha256=p['artifact_sha256'],
                checkpoint_ref=p['checkpoint_ref'], transition_id=transition_id, project=e['return_project'])
            e['status'] = 'CUTOVER_COMMITTED'
            self.journal.store.save(state)
            return new

    def effective_return(self, logical_project_id, task_id, original_origin, request_sha256, *, channel=None):
        from .contracts import ProjectRef
        require(identity(task_id) and sha(request_sha256), 'RESULT_TASK_IDENTITY_INVALID')
        with self.journal.locked() as state:
            if channel is not None:
                channel.validate()
                require(channel.logical_project_id == logical_project_id, 'RESULT_CHANNEL_PROJECT_CONFLICT')
            reg = state['registrations'].get(registration_key(channel) if channel is not None else logical_project_id)
            if reg is None:
                matches = [r for r in state['registrations'].values() if r.get('kind') == 'CURRENT_CHAT_MIRROR'
                    and r['channel']['logical_project_id'] == logical_project_id
                    and task_id in r.get('task_intents', {})
                    and (r['channel']['executor'] == asdict(original_origin) or
                         r.get('returns', {}).get(task_id, {}).get('original') == asdict(original_origin))]
                require(len(matches) == 1, 'CURRENT_CHAT_RETURN_LINEAGE_AMBIGUOUS')
                reg = matches[0]
            require(reg is not None, 'PROJECT_CANDIDATE_REGISTRATION_MISSING')
            row = reg['returns'].get(task_id)
            if row is None:
                require(self.catalog().chat(original_origin).project in channel_from_dict(reg['channel']).projects,
                        'RESULT_RETURN_PROJECT_CONFLICT')
                return original_origin
            require(row['original'] == asdict(original_origin) and row['request_sha256'] == request_sha256,
                    'RESULT_ORIGINAL_TASK_CONFLICT')
            endpoint = Endpoint(**row['effective'])
            expected_project = ProjectRef(**row['project']) if row['project'] is not None else None
            require(self.catalog().chat(endpoint).project == expected_project,
                    'RESULT_RETURN_PROJECT_CHANGED')
            return endpoint


def channel_from_dict(doc):
    from .contracts import ProjectRef
    if 'current_scope' in doc:
        from .current_chat import current_channel
        return current_channel(doc)
    return ProjectChannel(doc['logical_project_id'], doc['desired_name'], tuple(ProjectRef(**p) for p in doc['projects']),
        Endpoint(**doc['executor']), Endpoint(**doc['reviewer']), doc['generation'], doc['registration_ref']).validate()
