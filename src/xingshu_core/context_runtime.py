"""P4C Candidate（候选）：单入口、提供方中立的权限门禁与瞬时读取编排。

宿主提供 RuntimeContext；P2D/P2C/P2E 分别验证权限、来源交换和最终证据。
只支持 verify_before_use / locator_and_verification 的本轮直接 read 观察。
不认证宿主或提供方，不实现来源发现、文件系统、传输、缓存或权限登记。
输入遵循冻结合同的只读所有权约定；不提供恶意同进程代码隔离。
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from datetime import timezone
from typing import Any
from uuid import uuid4

from .authority_validation import validate_reference_authority
from .decisions import Decision
from .resolve_context_validation import validate_resolve_context_exchange, validate_resolve_context_object
from .runtime_contracts import (
    RuntimeContext, RuntimeExecutionResult, RuntimeFailureCategory, RuntimeLocalFailure,
    RuntimeResultKind, SourceAdapterExecution,
)
from .schema_registry import SchemaRegistry
from .source_adapter_validation import validate_source_adapter_exchange, validate_source_adapter_object

__all__ = ["resolve_registered_context"]
_VERSION = "context-bridge-candidate"


def _new_id() -> str:
    """内部 ID 独立于 caller；测试可替换本私有 helper，不新增可信配置字段。"""
    return "p4c-" + uuid4().hex


def _fingerprint(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _failure(category: RuntimeFailureCategory) -> RuntimeExecutionResult:
    return RuntimeExecutionResult(kind=RuntimeResultKind.LOCAL_EXECUTION_FAILURE,
                                  local_failure=RuntimeLocalFailure(category=category))


def _now(context: RuntimeContext) -> str:
    return context.now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_registered_context(request: Mapping[str, Any], *, context: RuntimeContext,
                               registry: SchemaRegistry | None = None) -> RuntimeExecutionResult:
    """先验证权限再接触 Adapter；仅 P2E 正式 PASS 回执允许返回协议结果。

不保存正文、不修改输入、不重试。所有本地失败只携带冻结分类和固定消息，
不转发 provider（提供方）异常、验证诊断、定位符或权限字节。
"""
    category = RuntimeFailureCategory.INVALID_INPUT
    try:
        checked = validate_resolve_context_object(request, "resolve_context_request", registry)
        if checked.decision is not Decision.PASS:
            return _failure(RuntimeFailureCategory.EXECUTION_UNAVAILABLE
                            if checked.decision is Decision.ERROR else category)
        query = copy.deepcopy(dict(request))
        if type(context) is not RuntimeContext:
            return _failure(category)
        category = RuntimeFailureCategory.EXECUTION_UNAVAILABLE
        evaluated_at = _now(context)
        reference = copy.deepcopy(dict(context.reference))
        profile = copy.deepcopy(dict(context.client_profile))
        binding = copy.deepcopy(dict(context.runtime_binding))
        authority_context = {
            "object_bytes": {"registered_context_reference": context.reference_bytes,
                             "trusted_client_profile": context.client_profile_bytes,
                             "runtime_binding": context.runtime_binding_bytes},
            "control_plane_selection": {
                "client_id": context.selected_client_id,
                "binding_fingerprint": _fingerprint(context.runtime_binding_bytes),
                "transport_binding_id": context.selected_transport_binding_id,
                "transport_class": context.selected_transport_class,
            },
            "operation": "resolve_context", "evaluated_at": evaluated_at,
        }
        authority = validate_reference_authority(
            reference, profile, binding, authority_context=authority_context, registry=registry,
        )
        if authority.decision is not Decision.PASS or authority.status != "authority_context_eligible":
            return _failure(RuntimeFailureCategory.EXECUTION_UNAVAILABLE
                            if authority.decision is Decision.ERROR else RuntimeFailureCategory.INVALID_INPUT)

        # P2D 检查冻结权限链；以下只收窄本 Runtime 支持范围和请求选择。
        category = RuntimeFailureCategory.INVALID_INPUT
        if query["reference_id"] != reference["reference_id"] or context.source_id != reference["source_id"]:
            return _failure(category)
        if (reference["freshness_policy"] != "verify_before_use"
                or reference["provenance_policy"] != "locator_and_verification"):
            return _failure(category)
        if "query_hint" in query or "disclosure_hints" in query:
            # P2E unsupported_request 只支持 binding operation 拒绝证据，不能
            # 将未实现的语义提示伪装成该原因，亦不能忽略提示后披露全文。
            return _failure(category)
        entries = query.get("entry_selection", reference["source_entry_points"])
        if len(entries) != 1:
            return _failure(category)
        entry = entries[0]
        if (entry not in reference["source_entry_points"] or entry not in binding["bound_entry_points"]
                or any(char in entry for char in ("*", "?", "[", "]"))):
            return _failure(category)

        category = RuntimeFailureCategory.SOURCE_FAILURE
        offered = context.adapter.manifest()
        category = RuntimeFailureCategory.VALIDATION_FAILURE
        checked = validate_source_adapter_object(offered, "source_adapter_manifest", registry)
        if checked.decision is not Decision.PASS:
            return _failure(category)
        manifest = copy.deepcopy(dict(offered))
        if manifest["adapter_id"] != context.adapter_id or "read" not in manifest["supported_operations"]:
            return _failure(category)
        # Manifest 的 UTF-8 / 非二进制 / 内容类型约束由既有 Schema 检查。
        # Reference/Binding 没有数字限额字段；其精确入口和 scope 已经 P2D 验证。
        hard = manifest["hard_limits"]
        limit = min(query["requested_limits"]["max_bytes"], hard["max_bytes"])
        source_request = {
            "schema_version": _VERSION, "object_kind": "source_adapter_request",
            "request_id": _new_id(), "adapter_id": context.adapter_id, "operation": "read",
            "source_id": context.source_id, "scope_id": context.scope_id, "target_locator": entry,
            "requested_limits": {"max_items": 1, "max_bytes": limit},
        }
        if "max_depth" in hard:
            source_request["requested_limits"]["max_depth"] = hard["max_depth"]
        checked = validate_source_adapter_object(source_request, "source_adapter_request", registry)
        if checked.decision is not Decision.PASS:
            return _failure(category)
        sent = copy.deepcopy(source_request)
        category = RuntimeFailureCategory.SOURCE_FAILURE
        execution = context.adapter.execute(sent)
        category = RuntimeFailureCategory.VALIDATION_FAILURE
        if type(execution) is not SourceAdapterExecution or sent != source_request:
            return _failure(category)
        # 快照响应而不修改借用映射；原始 bytes 不复制、不重新编码。
        source_response = copy.deepcopy(dict(execution.response))
        raw = execution.exact_content_bytes
        checked = validate_source_adapter_exchange(
            manifest, source_request, source_response, exact_content_bytes=raw, registry=registry,
        )
        if checked.decision is not Decision.PASS:
            return _failure(category)
        exchange = {"manifest": manifest, "request": source_request, "response": source_response,
                    "expected_scope_id": context.scope_id}
        if raw is not None:
            exchange["exact_content_bytes"] = raw
        category = RuntimeFailureCategory.EXECUTION_UNAVAILABLE
        verified_at = _now(context)
        resolution_context = {
            "reference": reference, "client_profile": profile, "runtime_binding": binding,
            "authority_context": authority_context, "resolved_at": verified_at,
            "source_exchanges": [exchange],
        }
        category = RuntimeFailureCategory.VALIDATION_FAILURE
        common = {"schema_version": _VERSION, "request_id": query["request_id"],
                  "reference_id": reference["reference_id"]}
        if source_response["object_kind"] == "source_adapter_error":
            if checked.status != "exchange_error_valid":
                return _failure(category)
            code = source_response["error_code"]
            if code not in ("source_unavailable", "limit_exceeded"):
                return _failure(RuntimeFailureCategory.SOURCE_FAILURE)
            response = {**common, "object_kind": "resolve_context_error", "error_code": code,
                        "retryable": source_response["retryable"], "observed_at": source_response["observed_at"]}
            kind, status = RuntimeResultKind.PROTOCOL_ERROR, "resolve_error_valid"
        else:
            if (checked.status != "exchange_valid" or source_response["operation"] != "read"
                    or type(raw) is not bytes or not raw):
                return _failure(category)
            payload, applied = source_response["payload"], source_response["applied_limits"]
            if payload["truncated"] or applied["truncated"]:
                return _failure(category)
            fingerprint = _fingerprint(raw)
            if "content_fingerprint" in reference and reference["content_fingerprint"] != fingerprint:
                return _failure(category)
            observed = source_response["provenance"]
            event = {"observation_id": observed["observation_id"], "observed_at": observed["observed_at"],
                     "verification_evidence_id": _new_id(), "verified_at": verified_at}
            resolution_context["resolution_event"] = event
            response = {
                **common, "object_kind": "resolve_context_result",
                "reference_fingerprint": _fingerprint(context.reference_bytes), "binding_id": binding["binding_id"],
                "trust_label": "authoritative_source_observation",
                "freshness": {"status": "current", "verified_at": verified_at,
                              "verification_evidence_id": event["verification_evidence_id"]},
                "provenance": {"source_id": context.source_id, "entry_points": [entry],
                               "observation_id": event["observation_id"], "observed_at": event["observed_at"],
                               "content_fingerprint": fingerprint},
                "applied_limits": {"max_items": 1, "max_bytes": applied["max_bytes"],
                                   "returned_items": 1, "returned_bytes": len(raw)},
                "minimum_disclosure": True, "payload_persistence": "transient_only",
                "payload": [{"entry_point": entry, "content_type": payload["content_type"],
                             "encoding": payload["encoding"], "byte_count": len(raw),
                             "text": payload["text"], "content_fingerprint": fingerprint}],
            }
            kind, status = RuntimeResultKind.SUCCESS, "resolve_exchange_valid"
        receipt = validate_resolve_context_exchange(query, response, resolution_context=resolution_context, registry=registry)
        if receipt.decision is not Decision.PASS or receipt.status != status:
            return _failure(category)
        return RuntimeExecutionResult(kind=kind, response=response, validation=receipt)
    except Exception:
        return _failure(category)
