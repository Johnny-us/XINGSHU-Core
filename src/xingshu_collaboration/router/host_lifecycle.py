"""官方宿主薄适配。只注入已启用操作；不读取凭据、不调用未公开接口。"""
from .lifecycle import LifecycleCapabilities, require


class OfficialHostLifecyclePort:
    def __init__(self, scope, *, implementation, create_project=None, create_chat=None, rename_project=None,
                 create_topic_chat=None):
        scope.validate()
        require(implementation in ('OFFICIAL_TOOL', 'OFFICIAL_API', 'OFFICIAL_UI'), 'OFFICIAL_HOST_IMPLEMENTATION_REQUIRED')
        require(all(cb is None or callable(cb) for cb in (create_project, create_chat, rename_project, create_topic_chat)), 'HOST_OPERATION_CALLBACK_INVALID')
        self.scope, self.implementation = scope, implementation
        self.project_callback, self.chat_callback = create_project, create_chat
        self.rename_callback = rename_project
        self.topic_chat_callback = create_topic_chat

    def capabilities(self):
        return LifecycleCapabilities(create_project=self.project_callback is not None,
            create_chat=self.chat_callback is not None, rename_project=self.rename_callback is not None, implementation=self.implementation)

    def create_project(self, operation_id, desired_name):
        require(self.project_callback is not None, 'OFFICIAL_PROJECT_CREATE_UNAVAILABLE')
        return self.project_callback(operation_id, self.scope, desired_name)

    def create_topic_chat(self, operation_id, project, topic_name, request_sha256):
        require(self.topic_chat_callback is not None and self.scope.contains(project),
                'OFFICIAL_TOPIC_CHAT_CREATE_UNAVAILABLE')
        return self.topic_chat_callback(operation_id, project, topic_name, request_sha256)

    def create_chat(self, operation_id, project, handoff_sha256):
        require(self.chat_callback is not None and self.scope.contains(project), 'OFFICIAL_CHAT_CREATE_UNAVAILABLE')
        return self.chat_callback(operation_id, project, handoff_sha256)

    def rename_project(self, operation_id, project, desired_name):
        require(self.rename_callback is not None and self.scope.contains(project), 'OFFICIAL_PROJECT_RENAME_UNAVAILABLE')
        return self.rename_callback(operation_id, project, desired_name)
