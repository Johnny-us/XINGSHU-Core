"""Source Adapter（来源适配器）的候选合同纯校验；默认不启用任何能力。

governance_effect=none; authorization_effect=none; activation_effect=none.
PASS 仅表示给定声明在本次检查范围内自洽，不证明权限、来源可用性、
定位符安全、实时性或提供方原生包含关系。不读取真实来源，不补用缓存。
唯一允许的文件读取由既有 SchemaRegistry 加载正式 Schema（数据模式）承担。
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry


# 仅限定本模块入口；文件映射、加载与严格校验仍由同一个 Registry 负责。
_ROUTES = (
    "source_adapter_manifest",
    "source_adapter_request",
    "source_adapter_result",
    "source_adapter_error",
)

__all__ = ["validate_source_adapter_object", "validate_source_adapter_exchange"]


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    # 调用点只传固定字段路径，绝不从未知输入键或原始异常生成诊断。
    return ValidationIssue(
        code=code,
        path=path,
        field=path.rsplit("/", 1)[-1] if "/" in path else None,
        message=message,
    )


def _report(
    route: str | None,
    decision: Decision,
    status: str,
    issues: Sequence[ValidationIssue] = (),
    schema_ref: str | None = None,
) -> ValidationResult:
    return ValidationResult(
        decision=decision,
        status=status,
        record_type=route if route in _ROUTES else None,
        # 这里标识所检查的合同，不能回显无效输入中的版本或类型值。
        schema_version="context-bridge-candidate" if route in _ROUTES else None,
        schema_ref=schema_ref,
        errors=tuple(issues),
    )


def _snapshot(value: Any, active: set[int]) -> Any:
    """将已解析的 Mapping / Sequence 复制为 JSON 容器，不修改输入。

    字符串保持原样；不解析其中的 JSON、定位符或正文指令。
    循环引用、非字符串键和非 JSON 值均拒绝，避免 Schema 库异常泄露值。
    """
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    ):
        identity = id(value)
        if identity in active:
            raise ValueError("cyclic input")
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(type(key) is not str for key in value):
                    raise ValueError("non-string key")
                return {key: _snapshot(child, active) for key, child in value.items()}
            return [_snapshot(child, active) for child in value]
        finally:
            active.remove(identity)
    raise ValueError("non-JSON value")


def _read_issues(record: dict[str, Any]) -> list[ValidationIssue]:
    payload, applied = record["payload"], record["applied_limits"]
    issues: list[ValidationIssue] = []
    if applied["observed_items"] > 1:
        issues.append(_issue(
            "source_adapter_read_item_count_exceeded", "$/applied_limits/observed_items",
            "read cannot report more than one observed item",
        ))
    if payload["truncated"] != applied["truncated"]:
        issues.append(_issue(
            "source_adapter_truncation_mismatch", "$/payload/truncated",
            "read and applied truncation flags do not agree",
        ))
    try:
        exact_bytes = payload["text"].encode("utf-8")
    except UnicodeEncodeError:
        issues.append(_issue(
            "source_adapter_invalid_utf8", "$/payload/text",
            "read text cannot be encoded as UTF-8",
        ))
        return issues
    size = len(exact_bytes)
    if payload["byte_count"] != size:
        issues.append(_issue(
            "source_adapter_byte_count_mismatch", "$/payload/byte_count",
            "read byte count does not match returned UTF-8 bytes",
        ))
    if size > applied["max_bytes"]:
        issues.append(_issue(
            "source_adapter_returned_bytes_limit_exceeded", "$/payload/text",
            "returned UTF-8 bytes exceed the applied byte limit",
        ))
    # 不假定 observed_bytes 只计正文，但它不能少于实际返回的正文字节。
    if size > applied["observed_bytes"]:
        issues.append(_issue(
            "source_adapter_read_bytes_underreported", "$/applied_limits/observed_bytes",
            "observed bytes underreport returned UTF-8 bytes",
        ))
    fingerprint = "sha256:" + hashlib.sha256(exact_bytes).hexdigest()
    for name in ("payload", "provenance"):
        supplied = record[name].get("content_fingerprint")
        if supplied is not None and supplied != fingerprint:
            issues.append(_issue(
                "source_adapter_fingerprint_mismatch", f"$/{name}/content_fingerprint",
                "fingerprint does not match exact returned UTF-8 bytes",
            ))
    return issues


def _local_issues(record: dict[str, Any], route: str) -> list[ValidationIssue]:
    if route != "source_adapter_result":
        return []
    issues: list[ValidationIssue] = []
    for field in ("source_id", "scope_id", "adapter_id", "operation"):
        if record["provenance"][field] != record[field]:
            issues.append(_issue(
                "source_adapter_provenance_mismatch", f"$/provenance/{field}",
                "provenance linkage does not match the result",
            ))
    applied = record["applied_limits"]
    for dimension in ("items", "bytes"):
        if applied[f"observed_{dimension}"] > applied[f"max_{dimension}"]:
            issues.append(_issue(
                "source_adapter_observed_limit_exceeded",
                f"$/applied_limits/observed_{dimension}",
                "observed count exceeds the applied limit",
            ))
    if record["operation"] == "list":
        # 冻结合同未定义精确计数口径；仅拒绝少报返回条目，不强加等号。
        if len(record["payload"]["items"]) > applied["observed_items"]:
            issues.append(_issue(
                "source_adapter_list_items_underreported", "$/applied_limits/observed_items",
                "observed items underreport returned list items",
            ))
    elif record["operation"] == "read":
        issues.extend(_read_issues(record))
    # stat 的源对象大小不等于披露字节数；不推断 stat/capabilities 条目口径。
    return issues


def _check_object(
    record: Any, expected_route: str, registry: SchemaRegistry | None,
) -> tuple[dict[str, Any] | None, ValidationResult]:
    if type(expected_route) is not str or expected_route not in _ROUTES:
        return None, _report(None, Decision.REJECT, "rejected", (_issue(
            "source_adapter_unsupported_route", "$", "unsupported source adapter route",
        ),))
    try:
        if not isinstance(record, Mapping):
            raise ValueError("object required")
        value = _snapshot(record, set())
    except Exception:
        # 也覆盖异常 Mapping/Sequence；不把异常字符串或输入内容带出边界。
        return None, _report(expected_route, Decision.REJECT, "rejected", (_issue(
            "source_adapter_invalid_object", "$", "input must be an acyclic JSON object",
        ),))
    if value.get("object_kind") != expected_route:
        return None, _report(expected_route, Decision.REJECT, "rejected", (_issue(
            "source_adapter_route_mismatch", "$/object_kind",
            "object kind does not match the expected route",
        ),))
    try:
        active_registry = registry if registry is not None else SchemaRegistry()
        schema_ref = active_registry.schema_ref_for(expected_route)
        validator = active_registry.validator_for(expected_route)
        invalid = next(validator.iter_errors(value), None) is not None
    except Exception:
        return None, _report(expected_route, Decision.ERROR, "validation_unavailable", (_issue(
            "source_adapter_validation_unavailable", "$", "strict contract validation is unavailable",
        ),))
    if invalid:
        # 包括 oneOf、额外字段、错误正文、日期和 operation/payload_kind 配对。
        # 不遍历 ValidationError 的动态路径、message、instance 或 context。
        return None, _report(expected_route, Decision.REJECT, "rejected", (_issue(
            "source_adapter_schema_invalid", "$", "object violates the frozen source adapter schema",
        ),), schema_ref)
    issues = _local_issues(value, expected_route)
    status = "error_envelope_valid" if expected_route == "source_adapter_error" else "object_valid"
    result = _report(
        expected_route, Decision.REJECT if issues else Decision.PASS,
        "rejected" if issues else status, issues, schema_ref,
    )
    return value, result


def validate_source_adapter_object(
    record: Mapping[str, Any],
    expected_route: str,
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """严格检查单对象及局部语义，不宣称已完成交换关联或取得权限。

    四种 expected_route 均通过既有 Registry 加载同一个冻结合同；入口额外
    精确匹配 object_kind，防止共享 oneOf 造成路线混淆。合法错误的状态是
    error_envelope_valid，其 PASS 只针对错误信封，不表示来源操作成功。
    """
    return _check_object(record, expected_route, registry)[1]


def _exchange_issues(
    manifest: dict[str, Any], request: dict[str, Any], response: dict[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if request["adapter_id"] != manifest["adapter_id"]:
        issues.append(_issue(
            "source_adapter_adapter_id_mismatch", "$/request/adapter_id",
            "request adapter does not match the manifest",
        ))
    if request["operation"] not in manifest["supported_operations"]:
        issues.append(_issue(
            "source_adapter_operation_unsupported", "$/request/operation",
            "request operation is not declared by the manifest",
        ))
    hard, requested = manifest["hard_limits"], request["requested_limits"]
    for field in ("max_items", "max_bytes", "max_depth"):
        # 省略 request.max_depth 时，已有 hard ceiling 仍有效；这里不执行遍历。
        # manifest 未声明深度时不发明无限值，也不据此拒绝合法请求。
        if field in hard and field in requested and requested[field] > hard[field]:
            issues.append(_issue(
                "source_adapter_requested_limit_exceeded", f"$/request/requested_limits/{field}",
                "requested limit exceeds the manifest hard ceiling",
            ))
    response_fields = (
        ("request_id", "source_adapter_request_id_mismatch"),
        ("adapter_id", "source_adapter_adapter_id_mismatch"),
        ("operation", "source_adapter_operation_mismatch"),
    )
    if response["object_kind"] == "source_adapter_result":
        response_fields += (
            ("source_id", "source_adapter_source_id_mismatch"),
            ("scope_id", "source_adapter_scope_id_mismatch"),
        )
    for field, code in response_fields:
        if response[field] != request[field]:
            issues.append(_issue(
                code, f"$/response/{field}", "response linkage does not match the request",
            ))
    if response["object_kind"] == "source_adapter_error":
        return issues
    applied = response["applied_limits"]
    for field in ("max_items", "max_bytes"):
        if applied[field] > requested[field] or applied[field] > hard[field]:
            issues.append(_issue(
                "source_adapter_applied_limit_exceeded", f"$/response/applied_limits/{field}",
                "applied limit exceeds the request or manifest ceiling",
            ))
    payload = response["payload"]
    # 只比较不透明定位符的精确值，不证明提供方原生包含关系或真实来源权限。
    if response["operation"] in ("stat", "read"):
        if payload["locator"] != request.get("target_locator"):
            issues.append(_issue(
                "source_adapter_target_locator_mismatch", "$/response/payload/locator",
                "response locator does not match the request target",
            ))
    if response["operation"] == "capabilities":
        if any(operation not in manifest["supported_operations"] for operation in payload["operations"]):
            issues.append(_issue(
                "source_adapter_capabilities_mismatch", "$/response/payload/operations",
                "capabilities advertise an operation absent from the manifest",
            ))
    elif response["operation"] == "read":
        if payload["content_type"] not in manifest["supported_content_types"]:
            issues.append(_issue(
                "source_adapter_content_type_unsupported", "$/response/payload/content_type",
                "read content type is not declared by the manifest",
            ))
        # 局部检查已核对实际 UTF-8 大小与 byte_count，再检查两个上游限额。
        if payload["byte_count"] > min(requested["max_bytes"], hard["max_bytes"]):
            issues.append(_issue(
                "source_adapter_returned_bytes_limit_exceeded", "$/response/payload/text",
                "returned UTF-8 bytes exceed the request or manifest byte ceiling",
            ))
    # 不解析或规范化 locator；不从 provider_metadata 读取任何语义覆盖值。
    return issues


def validate_source_adapter_exchange(
    manifest: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
    response: Mapping[str, Any] | None,
    *,
    exact_content_bytes: bytes | None = None,
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """检查完整 manifest/request/response 的声明关联，不执行来源操作。

    任一必要对象缺失时返回 NEEDS_REVIEW / incomplete_exchange，不把其余
    对象升级为完整交换通过。合法成功/错误分别使用 exchange_valid /
    exchange_error_valid；两者都不证明当前来源可用、权限或包含关系。

    exact_content_bytes 只适用于成功 read，必须是与原样 UTF-8 正文完全相同
    的 bytes。其他操作没有已定义的序列化口径，因此拒绝该附加输入。
    深度只比较显式声明：省略请求深度不移除 manifest 硬上限；此结果也不
    证明实际遍历遵守了深度。计数仅核对已定义关系，不猜测提供方统计口径。
    """
    missing = [name for name, value in (
        ("manifest", manifest), ("request", request), ("response", response),
    ) if value is None]
    if missing:
        return _report(None, Decision.NEEDS_REVIEW, "incomplete_exchange", tuple(
            _issue("source_adapter_missing_context", f"$/{name}", "required exchange context is missing")
            for name in missing
        ))
    try:
        active_registry = registry if registry is not None else SchemaRegistry()
    except Exception:
        return _report(None, Decision.ERROR, "validation_unavailable", (_issue(
            "source_adapter_validation_unavailable", "$", "strict contract validation is unavailable",
        ),))
    # response 的路线只从封闭枚举选择，不回显调用者提供的未知类型值。
    try:
        response_route = (
            "source_adapter_error"
            if isinstance(response, Mapping) and response.get("object_kind") == "source_adapter_error"
            else "source_adapter_result"
        )
    except Exception:
        response_route = "source_adapter_result"
    checked: list[dict[str, Any]] = []
    schema_ref: str | None = None
    for name, record, route in (
        ("manifest", manifest, "source_adapter_manifest"),
        ("request", request, "source_adapter_request"),
        ("response", response, response_route),
    ):
        value, result = _check_object(record, route, active_registry)
        if result.decision != Decision.PASS:
            prefixed = tuple(ValidationIssue(
                code=issue.code, path=f"$/{name}" + issue.path[1:],
                field=issue.field, message=issue.message,
            ) for issue in result.errors)
            return _report(response_route, result.decision, result.status, prefixed, result.schema_ref)
        assert value is not None
        checked.append(value)
        schema_ref = result.schema_ref
    manifest_value, request_value, response_value = checked
    issues = _exchange_issues(manifest_value, request_value, response_value)
    if exact_content_bytes is not None:
        if response_route != "source_adapter_result" or response_value["operation"] != "read":
            issues.append(_issue(
                "source_adapter_exact_bytes_not_applicable", "$/exact_content_bytes",
                "exact content bytes are only defined for a successful read envelope",
            ))
        elif type(exact_content_bytes) is not bytes or exact_content_bytes != response_value["payload"]["text"].encode("utf-8"):
            issues.append(_issue(
                "source_adapter_exact_bytes_mismatch", "$/exact_content_bytes",
                "exact content bytes do not match returned UTF-8 text",
            ))
    status = "exchange_error_valid" if response_route == "source_adapter_error" else "exchange_valid"
    return _report(
        response_route, Decision.REJECT if issues else Decision.PASS,
        "rejected" if issues else status, issues, schema_ref,
    )
