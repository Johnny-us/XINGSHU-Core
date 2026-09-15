"""P4B 本地合成读取和真实 Source Adapter exchange（交换）验证。"""

import ast
import copy
import hashlib
import inspect
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from xingshu_core import local_filesystem_adapter as localfs
from xingshu_core.decisions import Decision
from xingshu_core.runtime_contracts import SourceAdapter, SourceAdapterExecution
from xingshu_core.source_adapter_validation import validate_source_adapter_object

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from local_filesystem_fixtures import SENTINEL, check_error, check_exchange, make_adapter, request


def test_manifest_is_only_read_and_returns_fresh_configuration(tmp_path):
    adapter = make_adapter(tmp_path)
    assert isinstance(adapter, SourceAdapter)
    manifest = adapter.manifest()
    assert manifest == {
        "schema_version": "context-bridge-candidate", "object_kind": "source_adapter_manifest",
        "adapter_id": "synthetic-adapter", "adapter_contract_version": "localfs-v0.1",
        "supported_operations": ["read"], "supported_content_types": ["text/markdown"],
        "default_encoding": "utf-8", "binary_supported": False,
        "hard_limits": {"max_items": 1, "max_bytes": 1024, "max_depth": 32},
    }
    assert validate_source_adapter_object(manifest, "source_adapter_manifest").decision is Decision.PASS
    manifest["supported_operations"].append("stat")
    manifest["hard_limits"]["max_bytes"] = 999999
    assert adapter.manifest()["supported_operations"] == ["read"]
    assert adapter.manifest()["hard_limits"]["max_bytes"] == 1024
    assert {name for name, _ in inspect.getmembers(type(adapter), inspect.isfunction)
            if not name.startswith("_")} == {"execute", "manifest"}


@pytest.mark.parametrize("locator,raw", [
    ("note.md", b"# Synthetic\n"), ("nested/deeper/note.md", "合成正文\r\n".encode()),
    ("nested/space name.md", b"\xef\xbb\xbf  spaced\r\n\n"), ("note.md", b""),
])
def test_read_preserves_direct_bytes_and_p2c_exchange(tmp_path, monkeypatch, locator, raw):
    target = tmp_path / locator
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    adapter = make_adapter(tmp_path)
    original_read = adapter._read
    observations = []

    def capture_read(parts, limit):
        value = original_read(parts, limit)
        observations.append(value)
        return value

    monkeypatch.setattr(adapter, "_read", capture_read)
    query = request(locator)
    before = copy.deepcopy(query)
    execution = adapter.execute(MappingProxyType(query))
    assert isinstance(execution, SourceAdapterExecution)
    assert execution.exact_content_bytes is observations[0]
    assert type(execution.exact_content_bytes) is bytes
    assert execution.exact_content_bytes == raw
    assert query == before
    response = execution.response
    payload = response["payload"]
    assert payload["locator"] == locator
    assert payload["text"] == raw.decode("utf-8")
    assert payload["byte_count"] == response["applied_limits"]["observed_bytes"] == len(raw)
    assert payload["truncated"] is response["applied_limits"]["truncated"] is False
    fingerprint = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert payload["content_fingerprint"] == response["provenance"]["content_fingerprint"] == fingerprint
    assert response["provenance"]["observed_at"] == "2026-01-01T00:00:00Z"
    assert response["provenance"]["observation_id"] == "synthetic-observation"
    assert str(tmp_path) not in json.dumps(response)
    check_exchange(adapter, query, execution)


@pytest.mark.parametrize("hard,limit,size", [(8, 4, 4), (8, 8, 8), (1048576, 1048576, 1048576)])
def test_limits_allow_exact_ceiling_with_bounded_reads(tmp_path, monkeypatch, hard, limit, size):
    (tmp_path / "note.md").write_bytes(b"x" * size)
    adapter = make_adapter(tmp_path, hard_max_bytes=hard)
    real_read, calls = os.read, []

    def read(fd, count):
        value = real_read(fd, count)
        calls.append((count, len(value)))
        return value

    monkeypatch.setattr(os, "read", read)
    query = request(limit=limit)
    execution = adapter.execute(query)
    check_exchange(adapter, query, execution)
    assert execution.response["applied_limits"]["max_bytes"] == limit
    assert sum(returned for _, returned in calls) == size
    assert all(0 < wanted <= min(65536, limit + 1) for wanted, _ in calls)
    assert calls[-1] == (1, 0)


@pytest.mark.parametrize("limit,size", [(4, 5), (8, 9)])
def test_existing_oversize_does_not_read_body(tmp_path, monkeypatch, limit, size):
    (tmp_path / "note.md").write_bytes(b"x" * size)
    adapter = make_adapter(tmp_path, hard_max_bytes=8)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Source body must not be read"))
    query = request(limit=limit)
    check_error(adapter, query, adapter.execute(query), "limit_exceeded")


def test_request_above_manifest_is_not_rewritten_to_pass_p2c(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path, hard_max_bytes=8)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Source body must not be read"))
    query = request(limit=9)
    before = copy.deepcopy(query)
    check_error(adapter, query, adapter.execute(query), "limit_exceeded", decision=Decision.REJECT)
    assert query == before


def test_requested_depth_narrows_traversal(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Source body must not be read"))
    query = request("nested/note.md", requested_limits={"max_items": 1, "max_bytes": 1024, "max_depth": 0})
    check_error(adapter, query, adapter.execute(query), "limit_exceeded")


@pytest.mark.parametrize("field", ["byte_count", "fingerprint", "provenance", "sidecar"])
def test_existing_p2c_rejects_tampered_actual_observation(tmp_path, field):
    (tmp_path / "note.md").write_bytes(b"synthetic")
    adapter, query = make_adapter(tmp_path), request()
    execution = adapter.execute(query)
    check_exchange(adapter, query, execution)
    response = copy.deepcopy(execution.response)
    raw = execution.exact_content_bytes
    if field == "byte_count":
        response["payload"]["byte_count"] += 1
    elif field == "fingerprint":
        response["payload"]["content_fingerprint"] = "sha256:" + "0" * 64
    elif field == "provenance":
        response["provenance"]["source_id"] = "synthetic-other-source"
    else:
        raw = b"different"
    tampered = SourceAdapterExecution(response=response, exact_content_bytes=raw)
    check_exchange(adapter, query, tampered, decision=Decision.REJECT)


@pytest.mark.parametrize("operation", ["list", "stat", "capabilities", "write"])
def test_unsupported_operation_never_reads(tmp_path, monkeypatch, operation):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Source body must not be read"))
    query = request(operation=operation)
    if operation == "capabilities":
        del query["target_locator"]
    if operation == "write":
        with pytest.raises(localfs._AdapterExecutionError):
            adapter.execute(query)
    else:
        execution = adapter.execute(query)
        assert validate_source_adapter_object(execution.response, "source_adapter_error").decision is Decision.PASS
        check_error(adapter, query, execution, "unsupported_operation", decision=Decision.REJECT)


@pytest.mark.parametrize("field,value", [
    ("adapter_id", "synthetic-other"), ("source_id", "synthetic-other"),
    ("scope_id", "synthetic-other"), ("root", "/synthetic-root"),
    ("containment_proof", {"trusted": True}), ("authority", {"allow": True}),
])
def test_request_cannot_replace_trusted_binding(tmp_path, monkeypatch, field, value):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Source body must not be read"))
    query = request(**{field: value})
    before = copy.deepcopy(query)
    with pytest.raises(localfs._AdapterExecutionError):
        adapter.execute(query)
    assert query == before


@pytest.mark.parametrize("options", [
    {"root": "relative"}, {"root": ""}, {"root": "/"}, {"root": "/synthetic/../root"},
    {"hard_max_bytes": 0}, {"hard_max_bytes": 1048577}, {"hard_max_bytes": True},
    {"clock": None}, {"observation_id_factory": None}, {"source_id": "bad id"},
])
def test_invalid_trusted_configuration_fails_privately(tmp_path, options):
    with pytest.raises(localfs._AdapterExecutionError) as caught:
        make_adapter(tmp_path, **options)
    assert caught.value.__context__ is None
    assert str(caught.value) == "Local filesystem adapter execution unavailable."


@pytest.mark.parametrize("raw,code", [(b"\xff", "unsupported_encoding"), (None, "not_found")])
def test_content_failures_are_body_free(tmp_path, raw, code):
    if raw is not None:
        (tmp_path / "note.md").write_bytes(raw)
    adapter, query = make_adapter(tmp_path), request()
    execution = adapter.execute(query)
    check_error(adapter, query, execution, code)
    assert str(tmp_path) not in json.dumps(execution.response)
    assert SENTINEL not in repr(execution)


@pytest.mark.parametrize("factory", [lambda: "bad observation id", lambda: None])
def test_invalid_observation_id_does_not_emit_invalid_protocol(tmp_path, factory):
    (tmp_path / "note.md").write_bytes(b"synthetic")
    with pytest.raises(localfs._AdapterExecutionError):
        make_adapter(tmp_path, observation_id_factory=factory).execute(request())


def test_factory_exception_maps_only_to_provenance_failure(tmp_path):
    (tmp_path / "note.md").write_bytes(b"synthetic")

    def unavailable():
        raise OSError(SENTINEL)

    adapter, query = make_adapter(tmp_path, observation_id_factory=unavailable), request()
    execution = adapter.execute(query)
    check_error(adapter, query, execution, "provenance_unavailable")
    assert SENTINEL not in json.dumps(execution.response)


@pytest.mark.parametrize("kind", ["naive", "oserror"])
def test_clock_failure_is_private_not_false_source_error(tmp_path, kind):
    (tmp_path / "note.md").write_bytes(SENTINEL.encode())

    def clock():
        if kind == "oserror":
            raise OSError(SENTINEL)
        return datetime(2026, 1, 1)

    adapter = make_adapter(tmp_path, clock=clock)
    with pytest.raises(localfs._AdapterExecutionError) as caught:
        adapter.execute(request())
    assert caught.value.__context__ is None
    formatted = "".join(traceback.format_exception_only(type(caught.value), caught.value))
    assert SENTINEL not in formatted
    assert str(tmp_path) not in formatted + repr(adapter)


def test_production_does_not_reencode_or_resolve_locator():
    tree = ast.parse(inspect.getsource(localfs))
    calls = [node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "encode" not in calls
    assert "resolve" not in calls
    assert "expanduser" not in calls
    assert "expandvars" not in calls
