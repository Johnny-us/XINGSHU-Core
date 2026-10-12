"""镜像对账：目标、观测与已应用分开；本地映射不能冒充菜单修改。"""
from dataclasses import asdict, dataclass
from xingshu_collaboration.binding import CandidateError


@dataclass(frozen=True)
class ProjectCapabilities:
    read: bool = True
    create: bool = False
    rename: bool = False
    move_chat: bool = False
    task_status: bool = False

    def validate(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise CandidateError('PROJECT_CAPABILITY_INVALID')
        return self


def mirror_report(route, catalog, capabilities, *, task_status, observed_task_status=None):
    """调用方提供宿主观察；此函数不执行任何外部写入。"""
    route.channel.validate()
    catalog.validate()
    observed_task_status = observed_task_status or {}
    rows = []
    for ref in route.channel.projects:
        project = catalog.project(ref)
        caps = capabilities.get(ref)
        if type(caps) is not ProjectCapabilities:
            raise CandidateError('PROJECT_ADAPTER_CAPABILITY_MISSING')
        caps.validate()
        observed = observed_task_status.get(ref)
        rows.append({'project': asdict(ref), 'desired_name': route.channel.desired_name,
                     'observed_name': project.name, 'name_matches': project.name == route.channel.desired_name,
                     'rename_support': 'automatic' if caps.rename else 'unsupported',
                     'desired_task_status': task_status, 'observed_task_status': observed,
                     'task_status_matches': observed == task_status,
                     'task_status_support': 'automatic' if caps.task_status else 'unsupported'})
    membership = (catalog.chat(route.origin).project == route.origin_project
                  and catalog.chat(route.channel.executor).project == route.channel.projects[0]
                  and catalog.chat(route.channel.reviewer).project == route.channel.projects[1])
    return {'scope': 'SAME_PROJECT_NAME_MEMBERSHIP_TASK_STATUS', 'desired': rows,
            'membership_matches': membership, 'catalog_evidence_ref': catalog.evidence_ref,
            'observed_at': catalog.observed_at,
            'applied_verified': membership and all(r['name_matches'] and r['task_status_matches'] for r in rows),
            'writes_performed': False, 'body_or_files_mirrored': False}
