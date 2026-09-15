"""P4E 专用合成文件及证据包装；不接触真实 Source 或私人实例。"""

import copy
import hashlib
import json
from datetime import datetime
from itertools import count

import context_bridge_fixtures as fixtures
from xingshu_core import context_runtime as runtime, runtime_host as host
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter


AUTH_PRIVATE = "synthetic-p4e-authority-private"
BODY_PRIVATE = "SYNTHETIC_P4E_BODY_PRIVATE"
PATH_PRIVATE = "synthetic-p4e-private-absolute-path"
RAW = b"\xef\xbb\xbf# Synthetic P4E\r\n\xe6\x9e\x84\xe5\x9b\xbe\r\n\r\n"
ENTRY = "notes/photography.md"


def format_json(record, indent=2):
    """仅测试数据创建；刻意保留非规范顺序、空白、非 ASCII 及结尾换行。"""
    return (json.dumps(dict(reversed(list(record.items()))), ensure_ascii=False,
                       indent=indent, separators=(",", " : ")) + "\n\n").encode("utf-8")


def make_case(tmp_path, *, raw=RAW, status="active", expiry=None, request_limit=131072):
    directory = (tmp_path / PATH_PRIVATE).resolve()
    root = directory / "synthetic-vault"
    target = root / ENTRY
    target.parent.mkdir(parents=True)
    if raw is not None:
        target.write_bytes(raw)
    reference = fixtures.build_registered_context_reference({
        "authorization_id": "synthetic-authorization", "context_type": "document",
        "source_id": "synthetic-source", "final_canonical_name": AUTH_PRIVATE + " 合成",
        "final_source_locator": "synthetic:logical-root", "final_source_entry_points": [ENTRY],
        "final_access_scope": "private", "final_allowed_clients": [fixtures.SYNTHETIC_CLIENT_ID],
        "final_freshness_policy": "verify_before_use", "final_provenance_policy": "locator_and_verification",
        "retrieval_hint": "Synthetic entry only", "initial_status": status,
    })
    profile = {
        "schema_version": fixtures.SCHEMA_VERSION, "object_kind": "trusted_client_profile",
        "profile_id": AUTH_PRIVATE, "client_id": fixtures.SYNTHETIC_CLIENT_ID,
        "profile_version": 1, "identity_origin": "owner_controlled", "client_class": "local_tool",
        "profile_status": "active", "created_at": fixtures.utc_timestamp(),
    }
    if expiry is not None:
        profile["expires_at"] = fixtures.utc_timestamp(expiry)
    ref_bytes, profile_bytes = format_json(reference, 1), format_json(profile, 3)
    binding = fixtures.build_runtime_binding(profile, reference, profile_bytes=profile_bytes, reference_bytes=ref_bytes)
    binding["binding_id"] = AUTH_PRIVATE + "-binding"
    query = fixtures.build_resolve_context_request(reference)
    query["requested_limits"]["max_bytes"] = request_limit
    records = dict(reference=reference, profile=profile, binding=binding, request=query)
    blobs = dict(reference=ref_bytes, profile=profile_bytes, binding=format_json(binding, 4), request=format_json(query))
    files = {name: directory / (name + ".json") for name in records}
    for name, path in files.items():
        path.write_bytes(blobs[name])
    config = host.LocalRuntimeHostConfig(
        reference_file=files["reference"], client_profile_file=files["profile"],
        runtime_binding_file=files["binding"], request_file=files["request"],
        source_root=root, scope_id="synthetic-scope", adapter_id="synthetic-localfs", hard_max_bytes=131072,
    )
    args = ["resolve-local", "--reference", str(files["reference"]), "--client-profile", str(files["profile"]),
            "--runtime-binding", str(files["binding"]), "--request", str(files["request"]),
            "--root", str(root), "--scope-id", config.scope_id, "--adapter-id", config.adapter_id,
            "--max-bytes", str(config.hard_max_bytes)]
    return dict(directory=directory, root=root, target=target, files=files, records=records,
                blobs=blobs, config=config, args=args)


def snapshot(directory):
    """测试主动扫描自身临时目录，Resolve/Host 不参与；忽略 atime。"""
    result = {}
    for path in [directory, *sorted(directory.rglob("*"))]:
        info = path.stat()
        result[str(path.relative_to(directory))] = (
            info.st_mode, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return result


def instrument(monkeypatch):
    """所有包装均调用原实现；只替换宿主时钟与 ID 工厂为确定性输入。"""
    trace = dict(loads=[], contexts=[], queries=[], outcomes=[], reads=[], read_attempts=[],
                 source=[], source_responses=[], authority=[], resolve=[], times=[])
    seconds, ids = iter((6, 7, 8, 10, 11, 12)), count(1)

    def clock():
        stamp = fixtures.utc_timestamp(next(seconds))
        trace["times"].append(stamp)
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))

    monkeypatch.setattr(host, "_utc_now", clock)
    monkeypatch.setattr(host, "_observation_id", lambda: "synthetic-p4e-observation-" + str(next(ids)))
    load, run, read = host._load_json, host.resolve_registered_context, LocalFilesystemSourceAdapter._read
    authority, source, resolve = runtime.validate_reference_authority, runtime.validate_source_adapter_exchange, runtime.validate_resolve_context_exchange

    def loaded(path):
        value = load(path)
        trace["loads"].append(value)
        return value

    def running(query, *, context):
        trace["contexts"].append(context)
        trace["queries"].append(query)
        records = (query, context.reference, context.client_profile, context.runtime_binding)
        before = copy.deepcopy(records)
        result = run(query, context=context)
        assert records == before
        trace["outcomes"].append(result)
        return result

    def reading(adapter, *args):
        trace["read_attempts"].append(args)
        raw = read(adapter, *args)
        trace["reads"].append(raw)
        return raw

    def checked_authority(*args, **kwargs):
        receipt = authority(*args, **kwargs)
        trace["authority"].append(receipt)
        return receipt

    def checked_source(*args, **kwargs):
        receipt = source(*args, **kwargs)
        trace["source"].append((kwargs.get("exact_content_bytes"), receipt))
        trace["source_responses"].append(args[2])
        return receipt

    def checked_resolve(*args, **kwargs):
        receipt = resolve(*args, **kwargs)
        trace["resolve"].append((kwargs["resolution_context"], receipt))
        return receipt

    monkeypatch.setattr(host, "_load_json", loaded)
    monkeypatch.setattr(host, "resolve_registered_context", running)
    monkeypatch.setattr(LocalFilesystemSourceAdapter, "_read", reading)
    monkeypatch.setattr(runtime, "validate_reference_authority", checked_authority)
    monkeypatch.setattr(runtime, "validate_source_adapter_exchange", checked_source)
    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", checked_resolve)
    return trace


def assert_private(output, case):
    for private in (AUTH_PRIVATE, BODY_PRIVATE, PATH_PRIVATE, str(case["directory"]),
                    "Traceback", "FileNotFoundError", "PermissionError", "OSError", "RuntimeError",
                    "UnicodeDecodeError", "JSONDecodeError", "synthetic:logical-root"):
        assert private not in output
    for blob in case["blobs"].values():
        assert blob.decode("utf-8") not in output
