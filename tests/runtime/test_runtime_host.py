"""P4E 宿主原始字节、信任隔离、严格输入及只读证据。"""

import builtins
import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from xingshu_core import runtime_host as host
from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeContext, RuntimeResultKind

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from runtime_host_fixtures import AUTH_PRIVATE, BODY_PRIVATE, RAW, assert_private, format_json, instrument, make_case, snapshot


def test_exact_authority_files_read_once_and_preserved_through_real_validators(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    original_open = builtins.open
    file_reads = []

    def opened(path, mode="r", *args, **kwargs):
        if path in case["files"].values():
            assert mode == "rb"
            file_reads.append(path)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", opened)
    before = snapshot(case["directory"])
    result = host.resolve_local(case["config"])
    assert snapshot(case["directory"]) == before
    assert result.kind is RuntimeResultKind.SUCCESS
    assert file_reads == list(case["files"].values())
    assert len(trace["contexts"]) == 1
    ctx = trace["contexts"][0]
    assert type(ctx) is RuntimeContext and type(ctx.adapter) is LocalFilesystemSourceAdapter
    assert ctx.clock is ctx.adapter._clock
    for i, (name, attribute) in enumerate((("reference", "reference_bytes"), ("profile", "client_profile_bytes"), ("binding", "runtime_binding_bytes"))):
        raw = getattr(ctx, attribute)
        assert raw == case["files"][name].read_bytes() == case["blobs"][name]
        assert raw is trace["loads"][i][1]
        assert raw != json.dumps(case["records"][name], sort_keys=True).encode()
        assert raw.endswith(b"\n\n")
    assert result.response["reference_fingerprint"] == "sha256:" + hashlib.sha256(case["blobs"]["reference"]).hexdigest()
    assert [r.decision for r in trace["authority"]] == [Decision.PASS] * 2
    assert trace["source"][0][1].status == "exchange_valid"
    assert trace["resolve"][0][1] is result.validation
    assert result.validation.decision is Decision.PASS
    assert trace["source"][0][0] is trace["reads"][0]
    assert trace["resolve"][0][0]["source_exchanges"][0]["exact_content_bytes"] is trace["reads"][0]
    assert trace["reads"] == [RAW]


@pytest.mark.parametrize("blob", [
    b'{"value":"private-first","value":"private-last"}',
    b'{"nested":{"value":1,"value":2}}',
    b'{"items":[{"value":1,"value":2}]}',
    b'{"value":1,"\\u0076alue":2}',
    b'{"private":', b'\xff\xfeprivate', b'[]', b'null', b'"private"',
    b'{"number":NaN}', b'{"number":Infinity}', b'\xef\xbb\xbf{}',
])
@pytest.mark.parametrize("name", ["reference", "profile", "binding", "request"])
def test_strict_input_rejection_precedes_adapter_and_runtime(tmp_path, monkeypatch, name, blob):
    case = make_case(tmp_path)
    case["files"][name].write_bytes(blob)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid JSON must not construct the adapter or invoke Runtime")

    monkeypatch.setattr(host, "LocalFilesystemSourceAdapter", forbidden)
    monkeypatch.setattr(host, "resolve_registered_context", forbidden)
    with pytest.raises(host.HostInputError) as caught:
        host.resolve_local(case["config"])
    assert str(caught.value) == "Runtime host input could not be accepted."
    assert caught.value.__context__ is None
    assert "private" not in repr(caught.value)


@pytest.mark.parametrize("name", ["reference", "profile", "binding", "request"])
def test_missing_explicit_input_is_private(tmp_path, name):
    case = make_case(tmp_path)
    case["files"][name].unlink()
    with pytest.raises(host.HostInputError) as caught:
        host.resolve_local(case["config"])
    assert_private(str(caught.value), case)


@pytest.mark.parametrize("field", ["root", "adapter_id", "source_id", "scope_id", "client_id", "transport_class", "authority", "containment_proof", "trusted", "clock"])
def test_request_never_supplies_host_selection(tmp_path, monkeypatch, field):
    case = make_case(tmp_path, raw=BODY_PRIVATE.encode())
    query = case["records"]["request"]
    query[field] = str(case["directory"]) + "/override"
    case["files"]["request"].write_bytes(format_json(query))
    trace = instrument(monkeypatch)
    result = host.resolve_local(case["config"])
    assert result.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE
    ctx = trace["contexts"][0]
    assert ctx.source_id == case["records"]["reference"]["source_id"]
    assert ctx.selected_client_id == case["records"]["profile"]["client_id"]
    assert ctx.selected_transport_binding_id == case["records"]["binding"]["transport_binding_id"]
    assert ctx.selected_transport_class == case["records"]["binding"]["transport_class"]
    assert ctx.adapter_id == case["config"].adapter_id and ctx.scope_id == case["config"].scope_id
    assert ctx.adapter._root == str(case["root"])
    assert not trace["reads"] and not trace["source"]
    assert_private(repr(result), case)


def test_no_discovery_or_write_and_live_read_without_reregistration(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    before = snapshot(case["directory"])

    def forbidden(*args, **kwargs):
        pytest.fail("Host must not scan directories or discover Source")

    with monkeypatch.context() as patch:
        patch.setattr(os, "scandir", forbidden)
        patch.setattr(os, "listdir", forbidden)
        first = host.resolve_local(case["config"])
    assert snapshot(case["directory"]) == before
    assert first.kind is RuntimeResultKind.SUCCESS
    case["target"].write_bytes(RAW + b"Version B\r\n")
    second_before = snapshot(case["directory"])
    second = host.resolve_local(case["config"])
    assert snapshot(case["directory"]) == second_before
    assert second.kind is RuntimeResultKind.SUCCESS
    assert first.response["payload"][0]["text"] == RAW.decode()
    assert second.response["payload"][0]["text"] == (RAW + b"Version B\r\n").decode()
    assert len(trace["contexts"]) == 2 and trace["contexts"][0] is not trace["contexts"][1]
    assert trace["contexts"][0].adapter is not trace["contexts"][1].adapter
    for name, raw in case["blobs"].items():
        assert case["files"][name].read_bytes() == raw


def test_host_config_is_frozen_private_and_defaults_are_host_owned(tmp_path):
    case = make_case(tmp_path)
    assert repr(case["config"]) == "LocalRuntimeHostConfig()"
    with pytest.raises(dataclasses.FrozenInstanceError):
        case["config"].source_root = "/"
    now = host._utc_now()
    assert now.tzinfo is not None and now.utcoffset().total_seconds() == 0
    first, second = host._observation_id(), host._observation_id()
    assert first.startswith("p4e-localfs-") and first != second
    assert len(first.removeprefix("p4e-localfs-")) == 32


@pytest.mark.parametrize("root", [".", "relative", "/", "~/synthetic", "${SYNTHETIC_ROOT}"])
def test_root_must_be_explicit_physical_binding(tmp_path, root):
    case = make_case(tmp_path)
    with pytest.raises(host.HostInputError):
        host.resolve_local(dataclasses.replace(case["config"], source_root=root))


def test_host_never_resolves_a_symlink_root_into_an_accepted_path(tmp_path):
    case = make_case(tmp_path)
    alias = case["directory"] / "root-alias"
    alias.symlink_to(case["root"], target_is_directory=True)
    with pytest.raises(host.HostInputError):
        host.resolve_local(dataclasses.replace(case["config"], source_root=alias))


def test_host_loader_does_not_repair_unknown_fields(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    ref = case["records"]["reference"]
    ref["unknown_private"] = AUTH_PRIVATE
    case["files"]["reference"].write_bytes(format_json(ref))
    trace = instrument(monkeypatch)
    result = host.resolve_local(case["config"])
    assert trace["contexts"][0].reference["unknown_private"] == AUTH_PRIVATE
    assert result.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE
    assert not trace["reads"]


@pytest.mark.parametrize("compose", [False, True])
def test_composition_preserves_single_load_exact_bytes_and_runtime_call(tmp_path, monkeypatch, compose):
    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    calls, opened_files = [], []
    original_open = builtins.open

    class ForwardingAdapter:
        def __init__(self, delegate):
            self.delegate = delegate

        def manifest(self):
            return self.delegate.manifest()

        def execute(self, request):
            return self.delegate.execute(request)

    def composer(delegate):
        assert type(delegate) is LocalFilesystemSourceAdapter
        assert len(trace["loads"]) == 4 and not trace["contexts"]
        wrapper = ForwardingAdapter(delegate)
        calls.append((delegate, wrapper))
        return wrapper

    def opened(path, mode="r", *args, **kwargs):
        if path in case["files"].values():
            assert mode == "rb"
            opened_files.append(path)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", opened)
    result = host.resolve_local(case["config"], adapter_composer=composer if compose else None)
    assert result.kind is RuntimeResultKind.SUCCESS
    assert opened_files == list(case["files"].values())
    assert len(trace["loads"]) == 4
    assert len(trace["contexts"]) == len(trace["outcomes"]) == 1
    ctx = trace["contexts"][0]
    if compose:
        assert len(calls) == 1 and ctx.adapter is calls[0][1]
    else:
        assert calls == [] and type(ctx.adapter) is LocalFilesystemSourceAdapter
    for i, (name, attr) in enumerate((("reference", "reference_bytes"), ("profile", "client_profile_bytes"), ("binding", "runtime_binding_bytes"))):
        assert getattr(ctx, attr) is trace["loads"][i][1]
        assert getattr(ctx, attr) == case["blobs"][name]
    assert trace["reads"] == [RAW]
    assert [r.decision for r in trace["authority"]] == [Decision.PASS] * 2
    assert trace["resolve"][0][1] is result.validation


@pytest.mark.parametrize("fault", ["not_callable", "raises", "none", "object", "noncallable_methods"])
def test_composer_failure_is_private_host_error_without_fallback(tmp_path, monkeypatch, fault):
    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    calls = []

    def composer(delegate):
        calls.append(delegate)
        if fault == "raises":
            raise RuntimeError(str(case["root"]) + BODY_PRIVATE)
        if fault == "none":
            return None
        if fault == "noncallable_methods":
            return type("InvalidAdapter", (), {"manifest": 1, "execute": 2})()
        return object()

    def forbidden(*args, **kwargs):
        pytest.fail("Composition failure must not enter Runtime or execute LocalFS")

    monkeypatch.setattr(host, "resolve_registered_context", forbidden)
    monkeypatch.setattr(LocalFilesystemSourceAdapter, "execute", forbidden)
    with pytest.raises(host.HostInputError) as caught:
        host.resolve_local(case["config"], adapter_composer=42 if fault == "not_callable" else composer)
    assert len(calls) == (0 if fault == "not_callable" else 1)
    assert len(trace["loads"]) == 4 and not trace["reads"]
    assert str(caught.value) == "Runtime host input could not be accepted."
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert_private(repr(caught.value), case)


@pytest.mark.parametrize("name", ["reference", "profile", "binding", "request"])
def test_json_cannot_select_composer(tmp_path, monkeypatch, name):
    case = make_case(tmp_path)
    case["records"][name]["adapter_composer"] = "synthetic-policy-override"
    case["files"][name].write_bytes(format_json(case["records"][name]))
    trace = instrument(monkeypatch)
    result = host.resolve_local(case["config"])
    assert result.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE
    assert type(trace["contexts"][0].adapter) is LocalFilesystemSourceAdapter
    assert not trace["reads"]
    assert "adapter_composer" not in {f.name for f in dataclasses.fields(host.LocalRuntimeHostConfig)}
    with pytest.raises(TypeError):
        dataclasses.replace(case["config"], adapter_composer=lambda value: value)


def test_existing_cli_has_no_composer_selection(tmp_path, monkeypatch, capsys):
    from xingshu_core import runtime_cli as cli

    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    original = host.resolve_local
    calls = []

    def resolved(config, **kwargs):
        calls.append(kwargs)
        assert "adapter_composer" not in kwargs
        return original(config, **kwargs)

    monkeypatch.setattr(cli, "resolve_local", resolved)
    assert cli.main(case["args"]) == 0
    assert calls == [{}]
    assert type(trace["contexts"][0].adapter) is LocalFilesystemSourceAdapter
    capsys.readouterr()
    assert cli.main(case["args"] + ["--adapter-composer", "synthetic-override"]) == 4
    assert calls == [{}]
    assert "synthetic-override" not in capsys.readouterr().err
