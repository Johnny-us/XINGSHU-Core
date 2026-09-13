"""P4A 共享 Python 合同；不执行来源读取、权限验证或上下文解析。

信任起点是 Owner-controlled Host（所有者控制的宿主），不是普通请求。
宿主提供已接受对象及其原始 bytes（字节）；本模块不序列化、规范化、修复
或认证这些记录。对象结构、跨证据资格和真实观察由后续执行层调用既有
验证器检查。此合同不提供操作系统身份认证或同进程/同用户攻击隔离。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .decisions import Decision, ValidationResult


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceAdapterExecution:
    """本地 Python sidecar（附带数据容器），不是 Schema 对象或新传输响应。

response 只承载既有 source_adapter_result / source_adapter_error，按
borrowed read-only（借用且只读）约定保存；不修改映射，不冻结其嵌套内容。
read 成功时，适配器必须提供同次真实来源观察直接取得的原生 bytes；
运行时原样传递，禁止将 payload.text 重新编码来制造观察证据。权限记录
原始字节、缓存或历史结果均不能替代来源观察字节。

本容器只检查交接形状，不解码、编码、规范化、修复、散列或比较字节。
Schema、身份、请求关联、计数、限额、指纹及 provenance（来源追溯）
仍由既有 P2C 验证器负责。构造成功不证明观察真实，也不隔离同进程突变。
错误和非 read 成功均不得携带正文 bytes。不提供公开 JSON 序列化入口。
"""

    response: Mapping[str, Any] = field(repr=False)
    exact_content_bytes: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.response, Mapping):
            raise TypeError("adapter response must be a mapping")
        kind = self.response.get("object_kind")
        if kind not in ("source_adapter_result", "source_adapter_error"):
            raise ValueError("adapter response must be an existing source result or error")
        if kind == "source_adapter_result" and self.response.get("operation") == "read":
            if type(self.exact_content_bytes) is not bytes:
                raise TypeError("successful read requires native observation bytes")
        elif self.exact_content_bytes is not None:
            raise ValueError("error or non-read response cannot carry observation bytes")


@runtime_checkable
class SourceAdapter(Protocol):
    """Provider-neutral（提供方中立）接口；结构匹配不认证适配器。

manifest 返回既有 source_adapter_manifest。execute 返回 SourceAdapterExecution，
其中 response 只承载既有 source_adapter_result 或 source_adapter_error；不得修改 request。
只有 manifest 声明的操作可执行，允许仅声明 read，不要求实现其他操作。
接口不解释定位符，也不规定文件系统类型或根目录字段。

适配器通过 sidecar 原样交接本轮实际观察的 Source content bytes（来源内容字节）。
不得以权限记录原始字节、历史结果或重编码文本冒充它们。本阶段不新增
wire response（传输响应），不实现真实观察获取。
"""

    def manifest(self) -> Mapping[str, Any]: ...

    def execute(self, request: Mapping[str, Any]) -> SourceAdapterExecution: ...


TrustedClock = Callable[[], datetime]


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeContext:
    """由可信宿主显式构建的上下文，不接收或转换普通 Resolve 请求。

reference/profile/binding 及对应原始 bytes 来自宿主已接受记录；身份、
传输选择、Source/scope/adapter 绑定和时钟也由宿主提供，不从请求推导。
source_id/scope_id/adapter_id 标识宿主选定的来源绑定；具体根目录由未来
适配器的可信构造负责，本上下文不解释或保存通用文件系统路径。

所有 Mapping（映射）均借用为只读输入，不复制、补全、重编码或修改。
frozen 只阻止直接属性赋值，不冻结嵌套映射。宿主须在调用期间保持输入
稳定；这是一项 API 所有权约定，不是针对恶意同进程代码的安全屏障。
构造成功只表示容器类型符合合同，不代表记录有效、身份可信或权限成立。
"""

    reference: Mapping[str, Any] = field(repr=False)
    reference_bytes: bytes = field(repr=False)
    client_profile: Mapping[str, Any] = field(repr=False)
    client_profile_bytes: bytes = field(repr=False)
    runtime_binding: Mapping[str, Any] = field(repr=False)
    runtime_binding_bytes: bytes = field(repr=False)
    selected_client_id: str = field(repr=False)
    source_id: str = field(repr=False)
    scope_id: str = field(repr=False)
    adapter_id: str = field(repr=False)
    selected_transport_binding_id: str = field(repr=False)
    selected_transport_class: str = field(repr=False)
    adapter: SourceAdapter = field(repr=False)
    clock: TrustedClock = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.reference, self.client_profile, self.runtime_binding):
            if not isinstance(value, Mapping):
                raise TypeError("runtime records must be mappings")
        for value in (self.reference_bytes, self.client_profile_bytes, self.runtime_binding_bytes):
            if type(value) is not bytes:
                raise TypeError("original record bytes must be native bytes")
        for value in (self.selected_client_id, self.source_id, self.scope_id, self.adapter_id,
                      self.selected_transport_binding_id, self.selected_transport_class):
            if type(value) is not str or not value:
                raise TypeError("trusted selections must be nonempty strings")
        if not callable(getattr(self.adapter, "manifest", None)) or not callable(getattr(self.adapter, "execute", None)):
            raise TypeError("adapter must provide manifest and execute methods")
        if not callable(self.clock):
            raise TypeError("trusted clock must be callable")

    def now(self) -> datetime:
        """读取注入的宿主时钟；不使用系统默认时钟，不静默补时区。"""
        try:
            value = self.clock()
            if type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None:
                return value
        except Exception:
            pass
        raise ValueError("trusted clock must return an offset-aware datetime")


class RuntimeFailureCategory(str, Enum):
    """本地执行失败分类；不是任何 Schema error_code 或 Reference 状态。"""

    INVALID_INPUT = "invalid_input"
    EXECUTION_UNAVAILABLE = "execution_unavailable"
    SOURCE_FAILURE = "source_failure"
    VALIDATION_FAILURE = "validation_failure"


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeLocalFailure:
    """仅容纳封闭分类；消息固定，不接受自由文本或异常详情。

分类只区分输入无法接受、执行设施不可用、来源操作失败和结果验证失败。
具体 Source 错误到分类的映射延后；不得为适配 Resolve 错误合同改变原因。
"""

    category: RuntimeFailureCategory

    def __post_init__(self) -> None:
        if type(self.category) is not RuntimeFailureCategory:
            raise TypeError("local failure category must be a RuntimeFailureCategory")

    @property
    def message(self) -> str:
        return {
            RuntimeFailureCategory.INVALID_INPUT: "Runtime input could not be accepted.",
            RuntimeFailureCategory.EXECUTION_UNAVAILABLE: "Runtime execution is unavailable.",
            RuntimeFailureCategory.SOURCE_FAILURE: "Source operation could not be completed.",
            RuntimeFailureCategory.VALIDATION_FAILURE: "Runtime evidence validation did not succeed.",
        }[self.category]

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category.value, "message": self.message}


class RuntimeResultKind(str, Enum):
    SUCCESS = "success"
    PROTOCOL_ERROR = "protocol_error"
    LOCAL_EXECUTION_FAILURE = "local_execution_failure"


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeExecutionResult:
    """三种互斥返回；不调用验证器，不创造第四状态。

协议响应必须附上既有 P2E 成功回执。执行层负责确保回执确实来自对同一
响应及本轮证据的验证；本容器只能检查回执类型/状态，不能认证回执来源
或防止借用映射随后被修改。普通请求不得构造可信执行结果。
response 是只读借用映射。repr 不输出响应/回执；没有隐式正文序列化。
local_failure 的安全表示由其固定分类和固定消息构成。
"""

    kind: RuntimeResultKind
    response: Mapping[str, Any] | None = field(default=None, repr=False)
    local_failure: RuntimeLocalFailure | None = None
    validation: ValidationResult | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.kind) is not RuntimeResultKind:
            raise TypeError("runtime result kind must be a RuntimeResultKind")
        if self.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE:
            if self.response is not None or type(self.local_failure) is not RuntimeLocalFailure or self.validation is not None:
                raise ValueError("local failure requires only a local failure value")
            return
        route, status = {
            RuntimeResultKind.SUCCESS: ("resolve_context_result", "resolve_exchange_valid"),
            RuntimeResultKind.PROTOCOL_ERROR: ("resolve_context_error", "resolve_error_valid"),
        }[self.kind]
        if self.local_failure is not None or not isinstance(self.response, Mapping):
            raise ValueError("protocol outcome requires only a protocol response")
        if self.response.get("object_kind") != route:
            raise ValueError("protocol response does not match result kind")
        checked = self.validation
        if (type(checked) is not ValidationResult or checked.decision is not Decision.PASS
                or checked.status != status or checked.record_type != route
                or checked.schema_version != "context-bridge-candidate"
                or checked.schema_ref != "schemas/candidate/context-bridge/resolve-context.schema.json"
                or checked.errors):
            raise ValueError("protocol outcome requires a matching successful P2E receipt")
