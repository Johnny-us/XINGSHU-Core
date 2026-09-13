"""P4B 仅用临时目录的合成绑定、请求和既有 P2C 验证入口。"""

from datetime import datetime, timedelta, timezone

from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.source_adapter_validation import validate_source_adapter_exchange


STAMP = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
SENTINEL = "SYNTHETIC_SOURCE_SECRET"


def make_adapter(root, /, **overrides):
    options = {
        # macOS 的临时目录别名可能经 /var 符号链接；仅在合成 fixture 中
        # 取得实际物理路径。生产适配器不执行路径正规化。
        "root": root.resolve(), "adapter_id": "synthetic-adapter",
        "source_id": "synthetic-source", "scope_id": "synthetic-scope",
        "clock": lambda: STAMP, "observation_id_factory": lambda: "synthetic-observation",
        "hard_max_bytes": 1024,
    }
    options.update(overrides)
    return LocalFilesystemSourceAdapter(**options)


def request(locator="note.md", *, limit=1024, **overrides):
    record = {
        "schema_version": "context-bridge-candidate", "object_kind": "source_adapter_request",
        "request_id": "synthetic-request", "adapter_id": "synthetic-adapter",
        "source_id": "synthetic-source", "scope_id": "synthetic-scope", "operation": "read",
        "target_locator": locator, "requested_limits": {"max_items": 1, "max_bytes": limit},
    }
    record.update(overrides)
    return record


def check_exchange(adapter, query, execution, *, decision=Decision.PASS):
    checked = validate_source_adapter_exchange(
        adapter.manifest(), query, execution.response,
        exact_content_bytes=execution.exact_content_bytes,
    )
    assert checked.decision is decision, checked
    return checked


def check_error(adapter, query, execution, code, *, decision=Decision.PASS):
    assert execution.response["object_kind"] == "source_adapter_error"
    assert execution.response["error_code"] == code
    assert execution.response["retryable"] is False
    assert "payload" not in execution.response
    assert execution.exact_content_bytes is None
    check_exchange(adapter, query, execution, decision=decision)
