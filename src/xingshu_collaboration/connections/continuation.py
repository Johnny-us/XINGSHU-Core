"""通用结果续接状态；复用原日志，不以唤醒请求冒充模型已运行。"""
import fcntl
import hashlib
import os
import secrets
import time
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from xingshu_collaboration.binding import CandidateError, identity
from xingshu_collaboration.state import SnapshotStore
from .contracts import Endpoint, PROTOCOL, ConsumptionObservation

STATES = {'PENDING', 'DISPATCH_PREPARED', 'DISPATCH_ACCEPTED', 'DELIVERY_UNKNOWN', 'CONSUMED'}

class Continuations:
    """显式调用、一个消息一个事件；无线程、定时器、模型或任务调度器。"""
    def __init__(self, state_root, *, endpoint, clock=time.time):
        self.root = Path(state_root)
        self.endpoint = endpoint.validate()
        self.clock = clock
        self.store = SnapshotStore(self.root / 'snapshots', self.root.parent)

    def _mutate(self, callback):
        fd = os.open(self.root / 'relay.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CandidateError('CONCURRENT_DISPATCH_STOP') from exc
            state = self.store.load()
            if state is None:
                raise CandidateError('CONTINUATION_REQUIRES_EXISTING_DELIVERY')
            events = state.setdefault('continuations', {})
            value = callback(state, events)
            self.store.save(state)
            return value
        finally:
            os.close(fd)

    def _exact(self, state, events, message_id):
        event = events.get(message_id)
        if (type(event) is not dict or event.get('endpoint_id') != self.endpoint.endpoint_id
                or event.get('actor_id') != self.endpoint.actor_id
                or event.get('resource_uri') != self.endpoint.resource_uri
                or event.get('generation') != self.endpoint.generation):
            raise CandidateError('CONTINUATION_IDENTITY_OR_GENERATION_CONFLICT')
        if event.get('state') not in STATES:
            raise CandidateError('CONTINUATION_STATE_INVALID')
        entry=state.get('seen_events',{}).get(message_id,{})
        if (entry.get('status')!='ACKED' or event.get('connection_digest')!=state.get('connection_digest')
                or event.get('binding_digest')!=entry.get('binding_digest')
                or event.get('message_sha256')!=entry.get('message_sha256')
                or event.get('task_id')!=entry.get('task_id')
                or entry.get('destination_resource_uri')!=event['resource_uri']
                or entry.get('destination_generation')!=event['generation']):
            raise CandidateError('CONTINUATION_ORIGINAL_DELIVERY_CONFLICT')
        return event

    def enqueue(self, message_id):
        if not identity(message_id):
            raise CandidateError('CONTINUATION_MESSAGE_ID_INVALID')
        def update(state, events):
            entry = state.get('seen_events', {}).get(message_id)
            if (type(entry) is not dict or entry.get('status') != 'ACKED'
                    or entry.get('destination_endpoint') != self.endpoint.endpoint_id
                    or entry.get('target_actor') != self.endpoint.actor_id):
                raise CandidateError('CONTINUATION_REQUIRES_ACKED_EXACT_DELIVERY')
            if (entry.get('destination_resource_uri')!=self.endpoint.resource_uri
                    or entry.get('destination_generation')!=self.endpoint.generation
                    or entry.get('connection_digest')!=state.get('connection_digest')
                    or not entry.get('binding_digest')):
                raise CandidateError('CONTINUATION_IDENTITY_OR_GENERATION_CONFLICT')
            if message_id in events:
                return {'state': self._exact(state,events, message_id)['state'], 'replayed': True}
            events[message_id] = {'message_id': message_id, 'task_id': entry['task_id'],
                                 'endpoint_id': self.endpoint.endpoint_id, 'actor_id': self.endpoint.actor_id,
                                 'resource_uri': self.endpoint.resource_uri, 'generation': self.endpoint.generation,
                                 'message_sha256': entry['message_sha256'], 'state': 'PENDING',
                                 'binding_digest':entry['binding_digest'],'connection_digest':entry['connection_digest']}
            return {'state': 'PENDING', 'replayed': False}
        return self._mutate(update)

    def prepare(self, message_id):
        def update(_state, events):
            event = self._exact(_state,events, message_id)
            if event['state'] != 'PENDING':
                raise CandidateError('CONTINUATION_ALREADY_PREPARED_NO_RESEND')
            token = secrets.token_urlsafe(32)
            event.update(state='DISPATCH_PREPARED',
                         token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                         expires_at=self.clock() + 120)
            # 此 envelope（信封）仅交给获授权宿主，不写普通日志或产品界面。
            return {'protocol': PROTOCOL, 'event': 'RESULT_READY',
                    'message_id': message_id, 'task_id': event['task_id'],
                    'endpoint_id': event['endpoint_id'], 'actor_id': event['actor_id'],
                    'resource_uri': event['resource_uri'], 'generation': event['generation'],
                    'message_sha256':event['message_sha256'],'binding_digest':event['binding_digest'],
                    'connection_digest':event['connection_digest'],
                    'consume_token': token}
        return self._mutate(update)

    def finish(self, message_id, *, dispatch_accepted):
        if type(dispatch_accepted) is not bool:
            raise CandidateError('CONTINUATION_HOST_OUTCOME_INVALID')
        def update(_state, events):
            event = self._exact(_state,events, message_id)
            if event['state'] == 'CONSUMED':
                return {'state': 'CONSUMED', 'model_turn_consumed': True,
                        'consumption_observation':event['consumption_observation']}
            if event['state'] not in {'DISPATCH_PREPARED', 'DISPATCH_ACCEPTED', 'DELIVERY_UNKNOWN'}:
                raise CandidateError('CONTINUATION_NOT_PREPARED')
            requested = 'DISPATCH_ACCEPTED' if dispatch_accepted else 'DELIVERY_UNKNOWN'
            # 未知结果不可被后来的普通 ACK 擅自清除。
            if event['state'] != 'DELIVERY_UNKNOWN':
                event['state'] = requested
            return {'state': event['state'], 'model_turn_consumed': False}
        return self._mutate(update)

    def consume(self, message_id, token, observation=None):
        if type(observation) is not ConsumptionObservation:
            raise CandidateError('CONSUMPTION_OBSERVATION_REQUIRED')
        observation.validate()
        if observation.endpoint!=self.endpoint:
            raise CandidateError('CONSUMPTION_IDENTITY_OR_GENERATION_CONFLICT')
        if type(token) is not str or len(token) > 128:
            raise CandidateError('CONTINUATION_TOKEN_INVALID')
        token_sha = hashlib.sha256(token.encode()).hexdigest()
        def update(_state, events):
            event = self._exact(_state,events, message_id)
            if (observation.message_id!=message_id or observation.task_id!=event['task_id']
                    or observation.message_sha256!=event['message_sha256']
                    or observation.binding_digest!=event['binding_digest']
                    or observation.connection_digest!=event['connection_digest']):
                raise CandidateError('CONSUMPTION_ORIGINAL_EVENT_CONFLICT')
            if not secrets.compare_digest(event.get('token_sha256', ''), token_sha):
                raise CandidateError('CONTINUATION_TOKEN_INVALID')
            if event['state'] == 'CONSUMED':
                if event.get('consumption_observation')!=asdict(observation):
                    raise CandidateError('CONSUMPTION_REPLAY_EVIDENCE_CONFLICT')
                return {'state': 'CONSUMED', 'replayed': True, 'model_turn_consumed': True,
                        'execution_completed':False,'independent_review_accepted':False}
            if self.clock() >= event.get('expires_at', 0):
                raise CandidateError('CONTINUATION_TOKEN_EXPIRED')
            if event['state'] not in {'DISPATCH_PREPARED', 'DISPATCH_ACCEPTED', 'DELIVERY_UNKNOWN'}:
                raise CandidateError('CONTINUATION_NOT_PREPARED')
            event['state'] = 'CONSUMED'
            event.update(consumption_known=True,model_turn_native_id=observation.native_turn_id,
                         consumption_evidence_ref=observation.evidence_ref,consumption_evidence_sha256=observation.evidence_sha256,
                         consumed_at=datetime.now(timezone.utc).isoformat(),consumption_observation=asdict(observation))
            return {'state': 'CONSUMED', 'replayed': False, 'model_turn_consumed': True,
                    'execution_completed': False, 'independent_review_accepted': False}
        return self._mutate(update)
