"""P4D 临时合成 Source 夹具；真实 LocalFS，只有测试主动写入文件。"""

import copy
import hashlib
from datetime import datetime
from itertools import count

import context_bridge_fixtures as fixtures
from xingshu_core import context_runtime as runtime
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeContext


ENTRY = "notes/photography.md"
SENTINEL = "SYNTHETIC_P4D_PRIVATE_BODY"
RAW = b"\xef\xbb\xbf# Synthetic photography\r\n\xe6\x9e\x84\xe5\x9b\xbe\r\n\r\n"


def build_case(tmp_path, *, entry=ENTRY, raw=RAW, status="active", expiry=None):
    root = tmp_path / "synthetic-vault"
    target = root / entry
    target.parent.mkdir(parents=True)
    if raw is not None:
        target.write_bytes(raw)
    events, times = [], []
    sequence = iter((6, 7, 8, 10, 11, 12))

    def clock():
        stamp = fixtures.utc_timestamp(next(sequence))
        times.append(stamp)
        events.append("clock")
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))

    observation_ids = count(1)
    adapter = LocalFilesystemSourceAdapter(
        root=root.resolve(), adapter_id="synthetic-localfs", source_id="synthetic-source",
        scope_id="synthetic-scope", clock=clock,
        observation_id_factory=lambda: f"synthetic-localfs-observation-{next(observation_ids)}",
        hard_max_bytes=131072,
    )
    reference = fixtures.build_registered_context_reference({
        "authorization_id": "synthetic-authorization", "context_type": "document",
        "source_id": "synthetic-source", "final_canonical_name": "Synthetic photography",
        "final_source_locator": "synthetic:root", "final_source_entry_points": [entry],
        "final_access_scope": "private", "final_allowed_clients": [fixtures.SYNTHETIC_CLIENT_ID],
        "final_freshness_policy": "verify_before_use", "final_provenance_policy": "locator_and_verification",
        "retrieval_hint": "Synthetic exact entry only", "initial_status": status,
    })
    profile = {
        "schema_version": fixtures.SCHEMA_VERSION, "object_kind": "trusted_client_profile",
        "profile_id": "synthetic-profile", "client_id": fixtures.SYNTHETIC_CLIENT_ID,
        "profile_version": 1, "identity_origin": "owner_controlled", "client_class": "local_tool",
        "profile_status": "active", "created_at": fixtures.utc_timestamp(),
    }
    if expiry is not None:
        profile["expires_at"] = fixtures.utc_timestamp(expiry)
    profile_bytes = fixtures.encode_test_object(profile)
    reference_bytes = fixtures.encode_test_object(reference)
    binding = fixtures.build_runtime_binding(profile, reference, profile_bytes=profile_bytes, reference_bytes=reference_bytes)
    ctx = RuntimeContext(
        reference=reference, reference_bytes=reference_bytes, client_profile=profile, client_profile_bytes=profile_bytes,
        runtime_binding=binding, runtime_binding_bytes=fixtures.encode_test_object(binding),
        selected_client_id=profile["client_id"], source_id=reference["source_id"], scope_id="synthetic-scope",
        adapter_id="synthetic-localfs", selected_transport_binding_id=binding["transport_binding_id"],
        selected_transport_class=binding["transport_class"], adapter=adapter, clock=clock,
    )
    query = fixtures.build_resolve_context_request(reference)
    query["requested_limits"]["max_bytes"] = 131072
    return dict(root=root, target=target, adapter=adapter, context=ctx, request=query, events=events, times=times)


def tree_snapshot(root):
    """仅扫描本测试的合成目录；忽略 atime，记录目录项、内容和其余稳定元数据。"""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.stat()
        result[path.relative_to(root).as_posix()] = (
            info.st_mode, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return result


def resolve_unchanged(case):
    """每次成功或失败均检查输入只读及 Source 树不变；本 helper 不判定结果。"""
    ctx = case["context"]
    records = [case["request"], ctx.reference, ctx.client_profile, ctx.runtime_binding]
    before = copy.deepcopy(records)
    blobs = (ctx.reference_bytes, ctx.client_profile_bytes, ctx.runtime_binding_bytes)
    tree = tree_snapshot(case["root"])
    result = runtime.resolve_registered_context(case["request"], context=ctx)
    assert records == before
    assert blobs == (ctx.reference_bytes, ctx.client_profile_bytes, ctx.runtime_binding_bytes)
    assert tree_snapshot(case["root"]) == tree
    return result


def instrument(case, monkeypatch):
    """只包裹原方法/验证器记录证据，绝不替换读取结果或验证判定。"""
    trace = dict(buffers=[], executions=[], source_requests=[], authority=[], source=[], resolve=[], fingerprint_bytes=[])
    adapter, events = case["adapter"], case["events"]
    read, execute, manifest = adapter._read, adapter.execute, adapter.manifest
    authority = runtime.validate_reference_authority
    source, final = runtime.validate_source_adapter_exchange, runtime.validate_resolve_context_exchange
    fingerprint = runtime._fingerprint

    def observed_read(*args, **kwargs):
        raw = read(*args, **kwargs)
        trace["buffers"].append(raw)
        return raw

    def observed_execute(query):
        events.append("execute")
        trace["source_requests"].append(copy.deepcopy(query))
        execution = execute(query)
        trace["executions"].append(execution)
        return execution

    def observed_manifest():
        events.append("manifest")
        return manifest()

    def observed_authority(*args, **kwargs):
        result = authority(*args, **kwargs)
        events.append("authority")
        trace["authority"].append((kwargs["authority_context"], result))
        return result

    def observed_source(*args, **kwargs):
        result = source(*args, **kwargs)
        events.append("p2c")
        trace["source"].append((kwargs.get("exact_content_bytes"), result))
        return result

    def observed_final(*args, **kwargs):
        result = final(*args, **kwargs)
        events.append("p2e")
        trace["resolve"].append((kwargs["resolution_context"], result))
        return result

    def observed_fingerprint(raw):
        trace["fingerprint_bytes"].append(raw)
        return fingerprint(raw)

    monkeypatch.setattr(adapter, "_read", observed_read)
    monkeypatch.setattr(adapter, "execute", observed_execute)
    monkeypatch.setattr(adapter, "manifest", observed_manifest)
    monkeypatch.setattr(runtime, "validate_reference_authority", observed_authority)
    monkeypatch.setattr(runtime, "validate_source_adapter_exchange", observed_source)
    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", observed_final)
    monkeypatch.setattr(runtime, "_fingerprint", observed_fingerprint)
    return trace
