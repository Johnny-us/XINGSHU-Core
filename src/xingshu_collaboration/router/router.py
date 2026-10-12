"""按已登记项目编号路由；项目名只用于展示，不用于授权或猜测。"""
import math
import time
from .contracts import Invocation, ProjectChannel, Route
from xingshu_collaboration.binding import CandidateError


class ProjectRouter:
    def __init__(self, catalog_port, channels, *, clock=time.time, max_age=120):
        if type(channels) is not tuple or not channels or not 0 < max_age <= 120:
            raise CandidateError('ROUTER_REGISTRATION_REQUIRED')
        for ch in channels:
            if type(ch) is not ProjectChannel:
                raise CandidateError('ROUTER_CHANNEL_INVALID')
            ch.validate()
        self.catalog_port, self.channels = catalog_port, channels
        self.clock, self.max_age = clock, max_age

    def catalog(self):
        catalog = self.catalog_port.snapshot().validate()
        age = self.clock() - catalog.observed_at
        if not math.isfinite(age) or not 0 <= age <= self.max_age:
            raise CandidateError('CATALOG_STALE_OR_FUTURE')
        return catalog

    def plan(self, invocation_port):
        invocation = invocation_port.current_invocation()
        if type(invocation) is not Invocation:
            raise CandidateError('HOST_INVOCATION_REQUIRED')
        invocation.validate()
        catalog = self.catalog()
        origin = catalog.chat(invocation.origin)
        if origin.project is None:
            raise CandidateError('PROJECTLESS_ORIGIN_REQUIRES_EXPLICIT_BINDING')
        channels = [ch for ch in self.channels if origin.project in ch.projects]
        if len(channels) != 1:
            raise CandidateError('PROJECT_CHANNEL_UNREGISTERED_OR_AMBIGUOUS')
        ch = channels[0]
        for p in ch.projects:
            catalog.project(p)
        executor, reviewer = catalog.chat(ch.executor), catalog.chat(ch.reviewer)
        if (executor.project != ch.projects[0] or reviewer.project != ch.projects[1]):
            raise CandidateError('EXECUTOR_OR_REVIEWER_PROJECT_CONFLICT')
        route = Route(invocation.task_id, invocation.request_sha256, ch,
                      invocation.origin, origin.project, invocation.owner_trigger_ref)
        if invocation.origin != ch.executor:
            route.ingress_binding()
        return route

    def validate_current(self, route):
        if route.channel not in self.channels:
            raise CandidateError('ROUTE_REGISTRATION_CHANGED')
        catalog = self.catalog()
        if catalog.chat(route.origin).project != route.origin_project:
            raise CandidateError('ORIGIN_PROJECT_CHANGED')
        executor = catalog.chat(route.channel.executor)
        reviewer = catalog.chat(route.channel.reviewer)
        if (executor.project != route.channel.projects[0]
                or reviewer.project != route.channel.projects[1]):
            raise CandidateError('PROJECT_CHANNEL_MEMBERSHIP_CHANGED')
        return catalog

    def require_ready(self, route, target):
        catalog = self.validate_current(route)
        if target not in (route.origin, route.channel.executor, route.channel.reviewer):
            raise CandidateError('TASK_ROUTE_DESTINATION_CONFLICT')
        status = catalog.chat(target).status
        if status not in ('idle', 'completed'):
            raise CandidateError('HOST_NOT_READY_' + status.upper())
        return catalog
