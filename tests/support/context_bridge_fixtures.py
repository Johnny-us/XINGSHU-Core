"""纯合成测试数据构造器；不判断合法性、授权、状态转换或执行结果。

所有关联均在调用时显式构造，返回值彼此独立。修改对象不会自动修复指纹；
调用方需要重新构造时须明确提供新的对象与字节。Schema 有效不产生真实权限。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/context-bridge"
SCHEMA_VERSION = "context-bridge-candidate"
# 登记合同的 client_id 只允许小写字母、数字、下划线和连字符。
SYNTHETIC_CLIENT_ID = "synthetic_p3_client_01"
SYNTHETIC_ENTRY = "synthetic:entry:alpha"
SYNTHETIC_TEXT = "Synthetic P3 content\n合成测试正文\n"


def synthetic_id(kind: str, number: int = 1) -> str:
    return f"synthetic:p3:{kind}:{number:02d}"


def utc_timestamp(seconds: int = 0) -> str:
    """固定合成时钟，与机器当前时间无关。"""
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return moment.isoformat().replace("+00:00", "Z")


def encode_test_object(record: Mapping[str, Any]) -> bytes:
    """THIS IS TEST DATA CONSTRUCTION ONLY.

    此确定性 UTF-8 编码仅用于合成样本，不定义任何公开规范序列化协议。
    """
    return json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def fingerprint(exact_bytes: bytes) -> str:
    """仅散列调用方明确给出的字节，不核验其与任何对象的关系。"""
    return "sha256:" + hashlib.sha256(exact_bytes).hexdigest()


def _load_seed(filename: str) -> dict[str, Any]:
    # 仅由下面四个固定入口调用，不接受来源定位符或遍历目录。
    return json.loads((FIXTURE_ROOT / filename).read_bytes().decode("utf-8"))


def load_context_candidate_seed() -> dict[str, Any]:
    return _load_seed("context-candidate-valid.json")


def load_source_adapter_manifest_seed() -> dict[str, Any]:
    return _load_seed("source-adapter-manifest-valid.json")


def load_trusted_client_profile_seed() -> dict[str, Any]:
    return _load_seed("trusted-client-profile-valid.json")


def load_derived_provider_metadata_seed() -> dict[str, Any]:
    return _load_seed("derived-provider-metadata-valid.json")


def build_registration_proposal(candidate: Mapping[str, Any], *, candidate_bytes: bytes) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "context_registration_proposal",
        "proposal_id": synthetic_id("proposal"),
        "candidate_id": candidate["candidate_id"],
        "candidate_fingerprint": fingerprint(candidate_bytes),
        "suggested_canonical_name": candidate["discovered_name"],
        "suggested_source_entry_points": [SYNTHETIC_ENTRY],
        "suggested_allowed_clients": [SYNTHETIC_CLIENT_ID],
        "suggested_access_scope": "private",
        "suggested_freshness_policy": "verify_before_use",
        "suggested_provenance_policy": "locator_and_verification",
        "retrieval_hint": "Synthetic P3 entry only",
        "last_verified_at": utc_timestamp(1),
        "verification_evidence_id": synthetic_id("observation"),
    }


def build_context_validation_artifact(
    candidate: Mapping[str, Any], proposal: Mapping[str, Any], *,
    candidate_bytes: bytes, proposal_bytes: bytes, review_evidence_bytes: bytes,
    snapshot_bytes: bytes, source_observation_bytes: Sequence[bytes],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "context_validation_artifact",
        "validation_artifact_id": synthetic_id("validation"),
        "candidate_id": candidate["candidate_id"],
        "candidate_fingerprint": fingerprint(candidate_bytes),
        "proposal_id": proposal["proposal_id"],
        "proposal_fingerprint": fingerprint(proposal_bytes),
        "review_evidence_fingerprint": fingerprint(review_evidence_bytes),
        "validation_policy_id": synthetic_id("policy"),
        "validation_policy_version": "synthetic-p3-v1",
        "existing_reference_snapshot_fingerprint": fingerprint(snapshot_bytes),
        "source_revalidated_at": utc_timestamp(1),
        "source_observation_fingerprints": [fingerprint(value) for value in source_observation_bytes],
        "validated_at": utc_timestamp(2),
        "validation_outcome": "pass",
        "issue_codes": [],
    }


def build_human_authorization_evidence(
    candidate: Mapping[str, Any], proposal: Mapping[str, Any],
    validation: Mapping[str, Any], *, validation_bytes: bytes,
) -> dict[str, Any]:
    """构造明确的合成正向投影；不代表发生了真实人类确认。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "human_authorization_evidence",
        "authorization_id": synthetic_id("authorization"),
        "validation_artifact_id": validation["validation_artifact_id"],
        "validation_artifact_fingerprint": fingerprint(validation_bytes),
        "candidate_id": validation["candidate_id"],
        "candidate_fingerprint": validation["candidate_fingerprint"],
        "proposal_id": validation["proposal_id"],
        "proposal_fingerprint": validation["proposal_fingerprint"],
        "user_authorized": True,
        "authorization_method": "explicit_human_confirmation",
        "authorized_at": utc_timestamp(3),
        "context_type": candidate["context_type"],
        "source_id": candidate["source_id"],
        "initial_status": "active",
        "retrieval_hint": proposal["retrieval_hint"],
        "final_canonical_name": proposal["suggested_canonical_name"],
        "final_source_locator": candidate["source_locator"],
        "final_source_entry_points": copy.deepcopy(proposal["suggested_source_entry_points"]),
        "final_access_scope": proposal["suggested_access_scope"],
        "final_allowed_clients": copy.deepcopy(proposal["suggested_allowed_clients"]),
        "final_freshness_policy": proposal["suggested_freshness_policy"],
        "final_provenance_policy": proposal["suggested_provenance_policy"],
    }


def build_registered_context_reference(authorization: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "registered_context_reference",
        "reference_id": synthetic_id("reference"),
        "context_type": authorization["context_type"],
        "canonical_name": authorization["final_canonical_name"],
        "source_id": authorization["source_id"],
        "source_locator": authorization["final_source_locator"],
        "source_entry_points": copy.deepcopy(authorization["final_source_entry_points"]),
        "access_scope": authorization["final_access_scope"],
        "allowed_clients": copy.deepcopy(authorization["final_allowed_clients"]),
        "freshness_policy": authorization["final_freshness_policy"],
        "provenance_policy": authorization["final_provenance_policy"],
        "retrieval_hint": authorization["retrieval_hint"],
        "status": authorization["initial_status"],
        "registration_authorization_id": authorization["authorization_id"],
        "registered_at": utc_timestamp(4),
        "last_verified_at": utc_timestamp(1),
        "verification_evidence_id": synthetic_id("observation"),
    }


def build_context_reference_transition(
    previous: Mapping[str, Any], new: Mapping[str, Any], *,
    previous_bytes: bytes, new_bytes: bytes,
) -> dict[str, Any]:
    """记录调用方提供的状态对，不判断转换是否允许或自动改变状态。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "context_reference_transition",
        "transition_id": synthetic_id("transition"),
        "reference_id": previous["reference_id"],
        "previous_reference_fingerprint": fingerprint(previous_bytes),
        "new_reference_fingerprint": fingerprint(new_bytes),
        "from_status": previous["status"],
        "to_status": new["status"],
        "transitioned_at": utc_timestamp(7),
    }


def build_source_adapter_request(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """只构造一个有界 read 样本，不访问定位符。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "source_adapter_request",
        "request_id": synthetic_id("source-request"),
        "adapter_id": manifest["adapter_id"],
        "operation": "read",
        "source_id": synthetic_id("source"),
        "scope_id": synthetic_id("scope"),
        "target_locator": SYNTHETIC_ENTRY,
        "requested_limits": {"max_items": 1, "max_bytes": 1024},
    }


def build_source_adapter_result(
    request: Mapping[str, Any], *, text: str = SYNTHETIC_TEXT,
) -> dict[str, Any]:
    exact_content_bytes = text.encode("utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "object_kind": "source_adapter_result",
        "ok": True,
        "request_id": request["request_id"],
        "adapter_id": request["adapter_id"],
        "operation": "read",
        "source_id": request["source_id"],
        "scope_id": request["scope_id"],
        "provenance": {
            "source_id": request["source_id"], "scope_id": request["scope_id"],
            "adapter_id": request["adapter_id"], "operation": "read",
            "observed_at": utc_timestamp(1), "observation_id": synthetic_id("observation"),
            "content_fingerprint": fingerprint(exact_content_bytes),
        },
        "applied_limits": {
            "max_items": request["requested_limits"]["max_items"],
            "max_bytes": request["requested_limits"]["max_bytes"],
            "observed_items": 1, "observed_bytes": len(exact_content_bytes), "truncated": False,
        },
        "payload": {
            "payload_kind": "read", "locator": request["target_locator"],
            "content_type": "text/plain", "encoding": "utf-8",
            "byte_count": len(exact_content_bytes), "truncated": False, "text": text,
            "content_fingerprint": fingerprint(exact_content_bytes),
        },
    }


def build_source_adapter_error(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "object_kind": "source_adapter_error",
        "request_id": request["request_id"], "adapter_id": request["adapter_id"],
        "operation": request["operation"], "error_code": "source_unavailable",
        "retryable": True, "observed_at": utc_timestamp(1),
    }


def build_runtime_binding(
    profile: Mapping[str, Any], reference: Mapping[str, Any], *,
    profile_bytes: bytes, reference_bytes: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "object_kind": "runtime_binding",
        "binding_id": synthetic_id("binding"),
        "trusted_client_profile_id": profile["profile_id"],
        "trusted_client_profile_fingerprint": fingerprint(profile_bytes),
        "reference_id": reference["reference_id"],
        "reference_fingerprint": fingerprint(reference_bytes),
        "bound_access_scope": reference["access_scope"],
        "bound_entry_points": copy.deepcopy(reference["source_entry_points"]),
        "allowed_operations": ["get_reference", "resolve_context"],
        "transport_binding_id": synthetic_id("transport"),
        "transport_class": "in_process", "created_at": utc_timestamp(5),
    }


def build_resolve_context_request(reference: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "object_kind": "resolve_context_request",
        "request_id": synthetic_id("resolve-request"), "reference_id": reference["reference_id"],
        "entry_selection": copy.deepcopy(reference["source_entry_points"]),
        "requested_limits": {"max_items": 1, "max_bytes": 1024},
    }


def build_resolve_context_result(
    request: Mapping[str, Any], reference: Mapping[str, Any],
    binding: Mapping[str, Any], source_result: Mapping[str, Any], *,
    reference_bytes: bytes, exact_content_bytes: bytes,
) -> dict[str, Any]:
    """单条合成 read 结果；不实现多条聚合或 Resolve 判断。"""
    source_payload = source_result["payload"]
    return {
        "schema_version": SCHEMA_VERSION, "object_kind": "resolve_context_result",
        "request_id": request["request_id"], "reference_id": reference["reference_id"],
        "reference_fingerprint": fingerprint(reference_bytes), "binding_id": binding["binding_id"],
        "trust_label": "authoritative_source_observation",
        "freshness": {"status": "current", "verified_at": utc_timestamp(6),
                      "verification_evidence_id": source_result["provenance"]["observation_id"]},
        "provenance": {
            "source_id": source_result["source_id"],
            "observation_id": source_result["provenance"]["observation_id"],
            "observed_at": source_result["provenance"]["observed_at"],
            "entry_points": [source_payload["locator"]],
            "content_fingerprint": fingerprint(exact_content_bytes),
        },
        "applied_limits": {
            "max_items": request["requested_limits"]["max_items"],
            "max_bytes": request["requested_limits"]["max_bytes"],
            "returned_items": 1, "returned_bytes": len(exact_content_bytes),
        },
        "minimum_disclosure": True, "payload_persistence": "transient_only",
        "payload": [{
            "entry_point": source_payload["locator"], "content_type": source_payload["content_type"],
            "encoding": "utf-8", "byte_count": len(exact_content_bytes),
            "text": source_payload["text"], "content_fingerprint": fingerprint(exact_content_bytes),
        }],
    }


def build_resolve_context_error(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "object_kind": "resolve_context_error",
        "request_id": request["request_id"], "reference_id": request["reference_id"],
        "error_code": "source_unavailable", "retryable": True, "observed_at": utc_timestamp(6),
    }
