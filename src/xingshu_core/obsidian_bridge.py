"""P5B 候选桥接：显式宿主组合与精确笔记准入，不读取或解析来源。

权限、文件系统安全及最终证据完全复用 P4。普通请求无法选择组合函数；
本模块不提供恶意同进程隔离，也不产生采用或激活效力。
"""

from collections.abc import Callable, Mapping
from typing import Any

from .runtime_contracts import (
    RuntimeExecutionResult, SourceAdapter, SourceAdapterExecution, TrustedClock,
)
from .runtime_host import LocalRuntimeHostConfig, resolve_local

__all__ = ["resolve_obsidian"]


class _ObsidianAdmissionError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Obsidian note admission rejected.")


class _ObsidianNoteAdapter:
    """只保存委托适配器；不保留请求、结果或额外宿主配置。"""

    def __init__(self, delegate: SourceAdapter) -> None:
        self._delegate = delegate

    def __repr__(self) -> str:
        return "_ObsidianNoteAdapter()"

    def manifest(self) -> Mapping[str, Any]:
        return self._delegate.manifest()

    def execute(self, request: Mapping[str, Any]) -> SourceAdapterExecution:
        locator = request.get("target_locator")
        if (type(locator) is not str or not locator.endswith(".md")
                or any(part.startswith(".") for part in locator.split("/"))):
            raise _ObsidianAdmissionError()
        return self._delegate.execute(request)


def _compose_obsidian_adapter(delegate: SourceAdapter) -> SourceAdapter:
    return _ObsidianNoteAdapter(delegate)


def resolve_obsidian(
    config: LocalRuntimeHostConfig,
    *,
    clock: TrustedClock | None = None,
    observation_id_factory: Callable[[], str] | None = None,
) -> RuntimeExecutionResult:
    """单次调用公开 Host，固定安装准入策略，不预读或改写输入。"""
    return resolve_local(
        config,
        clock=clock,
        observation_id_factory=observation_id_factory,
        adapter_composer=_compose_obsidian_adapter,
    )
