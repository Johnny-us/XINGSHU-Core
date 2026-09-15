"""P5C 合成 Vault 与真实执行证据；所有主动写入仅发生在 tmp_path。"""

import builtins
import copy
import hashlib
import io
import json
import os
from datetime import datetime
from itertools import count

import context_bridge_fixtures as contracts
import runtime_host_fixtures as host_cases
from xingshu_core import context_runtime as runtime, obsidian_bridge as bridge, runtime_host as host
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeResultKind


ENTRY = "Projects/XINGSHU.md"
BODY = "SYNTHETIC_P5C_AUTHORIZED_BODY"
NEIGHBOR = "SYNTHETIC_P5C_NEIGHBOR_PRIVATE"
HIDDEN = "SYNTHETIC_P5C_HIDDEN_PRIVATE"
RAW = ("\ufeff---\r\ntags: [synthetic]\r\naliases: [测试]\r\nxingshu_allow: true\r\n"
       "root: /synthetic-frontmatter-override\r\ntrusted: true\r\nscope: fake-scope\r\n"
       "client_id: fake-client\r\n---\r\n# 中文笔记\r\n" + BODY + "\r\n"
       "[[Private/Finance]]\r\n![[Private/Finance]]\r\n[[Note#Heading]]\r\n"
       "[[Note#^block]]\r\n![[Attachments/image.png]]\r\n").encode("utf-8")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def make_case(tmp_path, *, entry=ENTRY, raw=RAW, status="active", expiry=None,
              profile_status="active", fixed=False, limit=131072, materialize=True):
    case = host_cases.make_case(tmp_path, raw=None, status=status, expiry=expiry)
    records = case["records"]
    records["reference"]["source_entry_points"] = [entry]
    if fixed:
        records["reference"]["content_fingerprint"] = digest(raw)
    records["profile"]["profile_status"] = profile_status
    if profile_status == "revoked":
        records["profile"]["revoked_at"] = contracts.utc_timestamp(5)
    ref_bytes = host_cases.format_json(records["reference"], 1)
    profile_bytes = host_cases.format_json(records["profile"], 3)
    records["binding"] = contracts.build_runtime_binding(
        records["profile"], records["reference"], profile_bytes=profile_bytes, reference_bytes=ref_bytes,
    )
    records["request"] = contracts.build_resolve_context_request(records["reference"])
    records["request"]["requested_limits"]["max_bytes"] = limit
    case["blobs"] = dict(reference=ref_bytes, profile=profile_bytes,
                         binding=host_cases.format_json(records["binding"], 4),
                         request=host_cases.format_json(records["request"]))
    for name, path in case["files"].items():
        path.write_bytes(case["blobs"][name])
    case["entry"] = entry
    case["target"] = case["root"] / entry if materialize else None
    if materialize:
        assert not entry.startswith("/") and ".." not in entry.split("/")
        case["target"].parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            case["target"].write_bytes(raw)
    for name, content in [("Private/Finance.md", NEIGHBOR.encode()),
                          (".obsidian/config.md", HIDDEN.encode()),
                          (".hidden/neighbor.md", HIDDEN.encode()),
                          ("Attachments/image.png", b"synthetic-image")]:
        path = case["root"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return case


def instrument(monkeypatch):
    """所有包装调用原实现；只注入确定性宿主时间和观察 ID。"""
    trace = {name: [] for name in ["events", "loads", "contexts", "composers", "wrappers",
                                  "delegates", "executions", "read_attempts", "buffers",
                                  "authority", "source", "resolve", "times", "file_loads", "fs",
                                  "input_snapshots", "wrapper_snapshots"]}
    seconds, ids = count(6), count(1)

    def clock():
        stamp = contracts.utc_timestamp(next(seconds))
        trace["times"].append(stamp)
        trace["events"].append("clock")
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))

    monkeypatch.setattr(host, "_utc_now", clock)
    monkeypatch.setattr(host, "_observation_id", lambda: "synthetic-p5c-observation-" + str(next(ids)))
    original_load, original_run = host._load_json, host.resolve_registered_context
    original_compose = bridge._compose_obsidian_adapter
    original_wrapper = bridge._ObsidianNoteAdapter.execute
    original_delegate, original_read = LocalFilesystemSourceAdapter.execute, LocalFilesystemSourceAdapter._read

    def load(path):
        value = original_load(path)
        trace["loads"].append((path, value))
        return value

    def compose(adapter):
        trace["events"].append("compose")
        result = original_compose(adapter)
        trace["composers"].append((adapter, result))
        return result

    def run(request, *, context):
        trace["events"].append("runtime")
        trace["contexts"].append(context)
        objects = (request, context.reference, context.client_profile, context.runtime_binding)
        before = copy.deepcopy(objects)
        blobs = (context.reference_bytes, context.client_profile_bytes, context.runtime_binding_bytes)
        trace["input_snapshots"].append((objects, before, blobs, context))
        outcome = original_run(request, context=context)
        assert objects == before
        assert blobs == (context.reference_bytes, context.client_profile_bytes, context.runtime_binding_bytes)
        return outcome

    def wrapper(adapter, request):
        trace["events"].append("wrapper")
        trace["wrappers"].append(request)
        before = copy.deepcopy(request)
        trace["wrapper_snapshots"].append((request, before))
        try:
            return original_wrapper(adapter, request)
        finally:
            assert request == before

    def delegate(adapter, request):
        trace["events"].append("localfs")
        trace["delegates"].append(request)
        value = original_delegate(adapter, request)
        trace["executions"].append(value)
        return value

    def read(adapter, *args):
        trace["events"].append("read")
        trace["read_attempts"].append(args)
        value = original_read(adapter, *args)
        trace["buffers"].append(value)
        return value

    monkeypatch.setattr(host, "_load_json", load)
    monkeypatch.setattr(host, "resolve_registered_context", run)
    monkeypatch.setattr(bridge, "_compose_obsidian_adapter", compose)
    monkeypatch.setattr(bridge._ObsidianNoteAdapter, "execute", wrapper)
    monkeypatch.setattr(LocalFilesystemSourceAdapter, "execute", delegate)
    monkeypatch.setattr(LocalFilesystemSourceAdapter, "_read", read)
    for name, stage in [("validate_reference_authority", "authority"),
                        ("validate_source_adapter_exchange", "source"),
                        ("validate_resolve_context_exchange", "resolve")]:
        original = getattr(runtime, name)

        def checked(*args, _original=original, _stage=stage, **kwargs):
            trace["events"].append(_stage)
            result = _original(*args, **kwargs)
            trace[_stage].append((args, kwargs, result))
            return result

        monkeypatch.setattr(runtime, name, checked)
    return trace


def run_unchanged(case, trace, monkeypatch, *, route="obsidian"):
    """每次执行都禁止枚举/邻居探测，并检查整个合成目录无写回。"""
    before = host_cases.snapshot(case["directory"])
    records = copy.deepcopy(case["records"])
    opened, statted, lstatted, file_open, path_open = os.open, os.stat, os.lstat, builtins.open, io.open
    forbidden_names = {"Private", "Finance", "Finance.md", "B.md", "neighbor.md"}
    violations = []

    def guard(name):
        if isinstance(name, (str, os.PathLike)):
            value = os.fspath(name)
            trace["fs"].append(value)
            if value.rsplit("/", 1)[-1] in forbidden_names:
                violations.append("neighbor probe")
                raise AssertionError("Neighbor must not be probed")

    def guarded_open(name, *args, **kwargs):
        guard(name)
        return opened(name, *args, **kwargs)

    def guarded_stat(name, *args, **kwargs):
        guard(name)
        return statted(name, *args, **kwargs)

    def guarded_lstat(name, *args, **kwargs):
        guard(name)
        return lstatted(name, *args, **kwargs)

    def guarded_path_open(name, *args, **kwargs):
        guard(name)
        return path_open(name, *args, **kwargs)

    def loaded(path, mode="r", *args, **kwargs):
        guard(path)
        if path in case["files"].values():
            assert mode == "rb"
            trace["file_loads"].append(path)
        return file_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        violations.append("directory enumeration")
        raise AssertionError("Production must not enumerate directories")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", guarded_open)
        patch.setattr(os, "stat", guarded_stat)
        patch.setattr(os, "lstat", guarded_lstat)
        patch.setattr(builtins, "open", loaded)
        patch.setattr(io, "open", guarded_path_open)
        patch.setattr(os, "listdir", forbidden)
        patch.setattr(os, "scandir", forbidden)
        if route == "obsidian":
            result = bridge.resolve_obsidian(case["config"])
        elif route == "local":
            result = host.resolve_local(case["config"])
        else:
            raise AssertionError("Unknown test route")
    assert violations == []
    for objects, saved, blobs, context in trace["input_snapshots"]:
        assert objects == saved
        assert blobs == (context.reference_bytes, context.client_profile_bytes, context.runtime_binding_bytes)
    for request, saved in trace["wrapper_snapshots"]:
        assert request == saved
    assert case["records"] == records
    assert host_cases.snapshot(case["directory"]) == before
    for name, path in case["files"].items():
        assert path.read_bytes() == case["blobs"][name]
    output = repr(result) + "".join(repr(ctx.adapter) for ctx in trace["contexts"])
    if result.kind is not RuntimeResultKind.SUCCESS:
        output += repr(result.response) + repr(result.local_failure)
        for sentinel in [BODY, HIDDEN, case["entry"]]:
            assert sentinel not in output
    else:
        output += json.dumps(dict(result.response), ensure_ascii=False)
    for sentinel in [NEIGHBOR, str(case["root"]), host_cases.AUTH_PRIVATE,
                     "UnicodeDecodeError", "Traceback", "FileNotFoundError"]:
        assert sentinel not in output
    for raw in case["blobs"].values():
        assert raw.decode() not in output
    return result
