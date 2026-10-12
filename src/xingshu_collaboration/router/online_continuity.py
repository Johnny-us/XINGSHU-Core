"""当前获授权在线回合的接续调度。没有后台，没有正式配置自动写入。"""
from dataclasses import asdict, replace
from .continuity import continuation_action, channel_from_dict, doc, registration_key
from .lifecycle import require
from .contracts import CurrentChatChannel
from xingshu_collaboration.state import digest


class OnlineContinuity:
    def __init__(self, manager, lifecycle_by_project, transport, drain_port, *, clock):
        self.manager, self.lifecycle_by_project, self.transport = manager, lifecycle_by_project, transport
        self.drain_port, self.clock = drain_port, clock

    def prepare_on_signal(self, channel, packet, signals, *, compact_supported=False):
        """只处理宿主证明的当前项目事件。由宿主调用，不轮询其他聊天。"""
        packet.validate()
        require(type(signals) is tuple and len(signals) in (1, 2), 'CURRENT_HOST_SIGNALS_REQUIRED')
        require(len({s.endpoint for s in signals}) == len(signals) and all(s.endpoint in (
            channel.executor, channel.reviewer) for s in signals), 'CONTEXT_SIGNAL_CHANNEL_CONFLICT')
        actions = {s.endpoint: continuation_action(s, now=self.clock(), compact_supported=compact_supported) for s in signals}
        self.manager.observe_channel(channel)
        with self.manager.journal.locked() as state:
            committed = [r for r in state['successors'].values() if r['packet_sha256'] == packet.packet_sha256
                and r['status'] == 'CUTOVER_COMMITTED' and r['old'] == doc(channel)]
            require(len(committed) <= 1, 'COMMITTED_HANDOFF_AMBIGUOUS')
            if committed:
                row = committed[0]
                require(state['registrations'][registration_key(channel)]['channel'] == row['new'],
                        'COMMITTED_REGISTRATION_DRIFT')
                return dict(status='CANDIDATE_CUTOVER_COMMITTED', channel=row['new'],
                    task_id=packet.task_id, formal_activation=False, execute_business_goal=False, duplicate=True)
        checkpoint_id = 'CHECKPOINT_' + packet.packet_sha256[:48]
        with self.manager.journal.locked() as state:
            reg = state['registrations'].get(registration_key(channel))
            require(reg is not None and reg['channel'] == doc(channel)
                    and packet.old_channel_sha256 == digest(asdict(channel)), 'ONLINE_HANDOFF_OLD_BINDING_CONFLICT')
            old = state['operations'].get(checkpoint_id)
            require(old is None or old['resource'] == doc(packet), 'ONLINE_CHECKPOINT_CONFLICT')
            if old is None:
                state['operations'][checkpoint_id] = dict(spec=dict(kind='HANDOFF_CHECKPOINT',
                    logical_project_id=channel.logical_project_id), status='APPLIED_VERIFIED', resource=doc(packet),
                    proof=dict(scope='LOCAL_CANDIDATE_CHECKPOINT_ONLY'))
                self.manager.journal.store.save(state)
        if 'COMPACT_THEN_VERIFY' in actions.values():
            return dict(status='NATIVE_COMPACTION_COMPLETION_REQUIRED', candidate_only=True)
        affected = {e for e, a in actions.items() if a == 'PREPARE_SUCCESSOR'}
        if not affected:
            return dict(status='CHECKPOINT_ONLY' if 'SAVE_CHECKPOINT_CONTEXT_UNKNOWN' in actions.values() else 'CONTINUE_CURRENT',
                        candidate_only=True)
        self.manager.observe_channel(channel, ready=True)
        self.manager._drained(self.drain_port.proof(channel), channel)
        with self.manager.journal.locked() as state:
            self.manager._confirmed_operations(state, channel)
        successors = []
        for endpoint, project in zip((channel.executor, channel.reviewer), channel.projects):
            if endpoint not in affected:
                successors.append(endpoint)
                continue
            lifecycle = self.lifecycle_by_project.get(project)
            require(lifecycle is not None, 'SUCCESSOR_PROJECT_ADAPTER_UNAVAILABLE')
            topic_args = dict(topic_name=channel.topic_name) if type(channel) is CurrentChatChannel else {}
            new = lifecycle.create_successor(project=project, predecessor=endpoint,
                handoff_sha256=packet.packet_sha256, owner_trigger_ref=packet.owner_trigger_ref, **topic_args)
            successors.append(new.endpoint)
        new_channel = replace(channel, executor=successors[0], reviewer=successors[1],
            generation=channel.generation + 1, registration_ref='candidate-handoff:' + packet.packet_sha256)
        tid = self.manager.propose(channel, new_channel, packet, self.drain_port.proof(channel))
        return dict(status='SUCCESSORS_PREPARED', transition_id=tid, channel=doc(new_channel),
                    handoff_sha256=packet.packet_sha256, candidate_only=True)

    def send_checkpoint(self, transition_id, packet):
        with self.manager.journal.locked() as state:
            row = self.manager._proposal(state, transition_id)
            require(row['packet_sha256'] == packet.packet_sha256, 'ONLINE_HANDOFF_PACKET_CONFLICT')
            old, new = channel_from_dict(row['old']), channel_from_dict(row['new'])
            required = self.manager.required_reads(row)
        self.manager.observe_channel(new, ready=True)
        results = []
        for previous, target, peer in ((old.executor, new.executor, new.reviewer), (old.reviewer, new.reviewer, new.executor)):
            # 未换页的一端也需读同一交接版本；不能给自己发消息。
            source = previous if previous != target else peer
            results.append(self.transport.send_packet(packet, source, target))
        for target in required - {new.executor, new.reviewer}:
            results.append(self.transport.send_packet(packet, new.executor, target))
        return dict(status='CHECKPOINT_INPUT_OBSERVED_MODEL_READ_REQUIRED', deliveries=results, candidate_only=True)

    def complete_candidate(self, transition_id, packet, actual_model_reads, *, business_coordinator=None, old_route=None):
        require(type(actual_model_reads) is tuple and len(actual_model_reads) in (2, 3), 'BOTH_ACTUAL_MODEL_READS_REQUIRED')
        with self.manager.journal.locked() as state:
            row = self.manager._proposal(state, transition_id)
            require(row['packet_sha256'] == packet.packet_sha256, 'ONLINE_HANDOFF_PACKET_CONFLICT')
            old, new = channel_from_dict(row['old']), channel_from_dict(row['new'])
            require({read.endpoint for read in actual_model_reads} == self.manager.required_reads(row),
                    'ALL_SUCCESSOR_READS_REQUIRED')
            if row['status'] == 'CUTOVER_COMMITTED':
                require(all(row['reads'].get(read.endpoint.endpoint_id) == asdict(read) for read in actual_model_reads),
                        'COMMITTED_HANDOFF_READ_PROOF_CHANGED')
                reg = state['registrations'][registration_key(new)]
                require(reg['channel'] == row['new'], 'COMMITTED_REGISTRATION_DRIFT')
                return dict(status='CANDIDATE_CUTOVER_COMMITTED', channel=doc(new), task_id=packet.task_id,
                    execute_business_goal=False, formal_activation=False, duplicate=True)
        for read in actual_model_reads:
            self.manager.observe_read(transition_id, read)
        self.manager.observe_channel(new, ready=True)
        for source, target in ((new.executor, new.reviewer), (new.reviewer, new.executor)):
            _, proof = self.transport.probe(packet, source, target)
            self.manager.observe_direction(transition_id, proof)
        # DrainPort 必须在共享宿主暂停旧投递的互斥区内提供最新全量证据。
        # 当前只提交候选登记；正式采用和全局投递隔离不由本模块冒充。
        with self.drain_port.fenced(old) as latest_drain:
            if business_coordinator is not None:
                require(old_route is not None and old_route.channel == old, 'BUSINESS_OLD_ROUTE_REQUIRED')
                result = business_coordinator.commit_verified(old_route, self.manager, transition_id, latest_drain)
            else:
                require(type(old) is not CurrentChatChannel, 'BUSINESS_CONTINUITY_ADOPTION_REQUIRED')
                result = self.manager.commit_candidate(transition_id, latest_drain)
        return dict(status='CANDIDATE_CUTOVER_COMMITTED', channel=doc(result), task_id=packet.task_id,
                    execute_business_goal=False, formal_activation=False)
