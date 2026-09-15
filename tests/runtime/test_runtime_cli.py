"""P4E 独立 CLI：真实全链路、退出码及输出隐私。"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from xingshu_core import runtime_cli as cli, runtime_host as host
from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeResultKind

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from runtime_host_fixtures import AUTH_PRIVATE, BODY_PRIVATE, PATH_PRIVATE, RAW, assert_private, format_json, instrument, make_case, snapshot


@pytest.mark.parametrize("json_mode", [False, True])
def test_real_cli_success_and_validator_chain(tmp_path, monkeypatch, capsys, json_mode):
    case = make_case(tmp_path)
    trace = instrument(monkeypatch)
    before = snapshot(case["directory"])
    code = cli.main(case["args"] + (["--json"] if json_mode else []))
    output = capsys.readouterr()
    assert code == 0 and not output.err
    if json_mode:
        response = json.loads(output.out)
        assert response == trace["outcomes"][0].response
        assert response["object_kind"] == "resolve_context_result"
        assert response["payload"][0]["text"] == case["target"].read_bytes().decode("utf-8")
        assert response["payload"][0]["byte_count"] == response["applied_limits"]["returned_bytes"] == len(RAW)
        expected = "sha256:" + hashlib.sha256(case["target"].read_bytes()).hexdigest()
        assert response["payload"][0]["content_fingerprint"] == response["provenance"]["content_fingerprint"] == expected
    else:
        assert output.out == "SUCCESS\nstatus: resolved\n\n--- 正文 ---\n" + RAW.decode("utf-8")
        for private in (AUTH_PRIVATE, PATH_PRIVATE, "sha256:", "synthetic-localfs", "in_process"):
            assert private not in output.out
    assert str(case["root"]) not in output.out
    assert snapshot(case["directory"]) == before
    assert len(trace["contexts"]) == len(trace["read_attempts"]) == len(trace["resolve"]) == 1
    assert [receipt.decision for receipt in trace["authority"]] == [Decision.PASS, Decision.PASS]
    assert [receipt.status for receipt in trace["authority"]] == ["authority_context_eligible"] * 2
    assert trace["source"][0][1].decision is Decision.PASS
    assert trace["source"][0][1].status == "exchange_valid"
    assert trace["resolve"][0][1].decision is Decision.PASS
    assert trace["resolve"][0][1].status == "resolve_exchange_valid"
    assert trace["times"] == ["2026-01-01T00:00:06Z", "2026-01-01T00:00:07Z", "2026-01-01T00:00:08Z"]


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("scenario,exit_code,category", [
    ("malformed", 4, "invalid_host_input"), ("non_utf8_authority", 4, "invalid_host_input"),
    ("duplicate", 4, "invalid_host_input"), ("nested_duplicate", 4, "invalid_host_input"),
    ("schema_invalid", 3, "invalid_input"), ("paused", 3, "invalid_input"),
    ("wrong_reference_fingerprint", 3, "invalid_input"), ("wrong_profile_fingerprint", 3, "invalid_input"),
    ("missing_source", 3, "source_failure"), ("bad_source", 3, "source_failure"),
    ("limit", 2, "limit_exceeded"), ("empty", 3, "validation_failure"),
    ("post_expiry", 3, "invalid_input"), ("provider_exception", 3, "source_failure"),
    ("runtime_exception", 3, "execution_unavailable"),
    ("runtime_exception_after_read", 3, "execution_unavailable"),
])
def test_real_cli_failure_semantics_and_privacy(tmp_path, monkeypatch, capsys, json_mode, scenario, exit_code, category):
    raw = (BODY_PRIVATE * 10).encode()
    if scenario == "missing_source":
        raw = None
    elif scenario == "bad_source":
        raw = b"\xff\xfe" + raw
    elif scenario == "empty":
        raw = b""
    case = make_case(tmp_path, raw=raw, status="paused" if scenario == "paused" else "active",
                     expiry=8 if scenario == "post_expiry" else None, request_limit=32 if scenario == "limit" else 131072)
    if scenario in ("malformed", "non_utf8_authority", "duplicate", "nested_duplicate"):
        invalid = {
            "malformed": ('{"private":"' + AUTH_PRIVATE + '",').encode(),
            "non_utf8_authority": b"\xff\xfe" + AUTH_PRIVATE.encode(),
            "duplicate": ('{"private":"' + AUTH_PRIVATE + '","private":"again"}').encode(),
            "nested_duplicate": ('{"nested":{"private":"' + AUTH_PRIVATE + '","private":2}}').encode(),
        }[scenario]
        case["files"]["reference"].write_bytes(invalid)
    elif scenario == "schema_invalid":
        ref = case["records"]["reference"]
        ref["unknown_private"] = AUTH_PRIVATE
        case["files"]["reference"].write_bytes(format_json(ref))
    elif scenario.startswith("wrong_"):
        binding = case["records"]["binding"]
        key = "reference_fingerprint" if scenario == "wrong_reference_fingerprint" else "trusted_client_profile_fingerprint"
        binding[key] = "sha256:" + "0" * 64
        case["files"]["binding"].write_bytes(format_json(binding))
    trace = instrument(monkeypatch)
    if scenario in ("provider_exception", "runtime_exception", "runtime_exception_after_read"):
        original_run = host.resolve_registered_context
        def unavailable(*args, **kwargs):
            if scenario == "runtime_exception_after_read":
                original_run(*args, **kwargs)
            raise RuntimeError(BODY_PRIVATE + AUTH_PRIVATE + str(case["directory"]))
        if scenario == "provider_exception":
            monkeypatch.setattr(LocalFilesystemSourceAdapter, "execute", unavailable)
        else:
            monkeypatch.setattr(host, "resolve_registered_context", unavailable)
    before = snapshot(case["directory"])
    code = cli.main(case["args"] + (["--json"] if json_mode else []))
    output = capsys.readouterr()
    assert code == exit_code
    assert snapshot(case["directory"]) == before
    assert_private(output.out + output.err, case)
    if json_mode:
        assert not output.err
        result = json.loads(output.out)
        if exit_code == 2:
            assert result == trace["outcomes"][0].response
            assert result["error_code"] == category and "payload" not in result
        else:
            assert set(result) == {"kind", "category", "message"}
            assert result["category"] == category
            assert result["kind"] == ("runtime_host_error" if exit_code == 4 else "local_execution_failure")
    elif exit_code == 2:
        assert output.out == "PROTOCOL_ERROR\ncode: limit_exceeded\n" and not output.err
    else:
        assert not output.out
        if exit_code == 3:
            assert category in output.err
        assert "message: " in output.err
    if exit_code == 4:
        assert not trace["contexts"] and not trace["read_attempts"]
    if scenario in ("paused", "wrong_reference_fingerprint", "wrong_profile_fingerprint", "schema_invalid"):
        assert not trace["read_attempts"] and trace["authority"][0].decision is Decision.REJECT
    if scenario in ("missing_source", "bad_source", "limit", "empty", "post_expiry"):
        assert len(trace["read_attempts"]) == 1
        assert trace["source"][0][1].decision is Decision.PASS
    if scenario in ("missing_source", "bad_source"):
        assert trace["source_responses"][0]["error_code"] == ("not_found" if scenario == "missing_source" else "unsupported_encoding")
        assert not trace["resolve"]
    if scenario == "limit":
        assert trace["source_responses"][0]["error_code"] == "limit_exceeded"
        assert trace["resolve"][0][1].decision is Decision.PASS
        assert trace["resolve"][0][1].status == "resolve_error_valid"
    if scenario == "post_expiry":
        assert trace["reads"] == [raw]
        assert [r.decision for r in trace["authority"]] == [Decision.PASS, Decision.REJECT]
        assert not trace["resolve"]
    if scenario == "runtime_exception_after_read":
        assert trace["reads"] == [raw]
        assert trace["resolve"][0][1].decision is Decision.PASS


@pytest.mark.parametrize("name", ["reference", "profile", "binding", "request"])
def test_missing_input_files_never_leak_paths(tmp_path, monkeypatch, capsys, name):
    case = make_case(tmp_path)
    case["files"][name].unlink()
    trace = instrument(monkeypatch)
    assert cli.main(case["args"] + ["--json"]) == 4
    output = capsys.readouterr()
    assert_private(output.out + output.err, case)
    assert json.loads(output.out)["category"] == "invalid_host_input"
    assert not trace["contexts"] and not trace["read_attempts"]


@pytest.mark.parametrize("fault", ["missing", "unknown", "integer", "negative", "too_large", "command", "abbreviated", "bypass"])
@pytest.mark.parametrize("json_mode", [False, True])
def test_usage_errors_are_fixed_and_private(tmp_path, capsys, fault, json_mode):
    case = make_case(tmp_path)
    args = case["args"].copy()
    if fault == "missing":
        del args[args.index("--root"):args.index("--root") + 2]
    elif fault in ("integer", "negative", "too_large"):
        args[args.index("--max-bytes") + 1] = {"integer": str(case["directory"]), "negative": "-1", "too_large": "1048577"}[fault]
    elif fault == "command":
        args[0] = str(case["directory"])
    elif fault == "abbreviated":
        args[args.index("--reference")] = "--refer"
    else:
        args += ["--force" if fault == "bypass" else "--" + PATH_PRIVATE, str(case["directory"])]
    if json_mode:
        args.append("--json")
    assert cli.main(args) == 4
    output = capsys.readouterr()
    assert_private(output.out + output.err, case)
    if json_mode:
        assert not output.err
        assert json.loads(output.out) == {"kind": "runtime_host_error", "category": "invalid_invocation",
                                         "message": "Invalid runtime host invocation."}
    else:
        assert not output.out
        assert output.err == "RUNTIME_HOST_ERROR\nmessage: Invalid runtime host invocation.\n"


def test_permission_error_is_sanitized(tmp_path, monkeypatch, capsys):
    case = make_case(tmp_path)
    def denied(*args, **kwargs):
        raise PermissionError(13, AUTH_PRIVATE, str(case["directory"]))
    monkeypatch.setattr(host, "open", denied, raising=False)
    assert cli.main(case["args"] + ["--json"]) == 4
    output = capsys.readouterr()
    assert_private(output.out + output.err, case)
    assert json.loads(output.out)["category"] == "invalid_host_input"


@pytest.mark.parametrize("json_mode", [False, True])
def test_broken_error_output_channel_does_not_raise(tmp_path, monkeypatch, json_mode):
    case = make_case(tmp_path)
    case["files"]["reference"].unlink()

    class BrokenOutput:
        def write(self, value):
            raise OSError(str(case["directory"]) + AUTH_PRIVATE)

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout" if json_mode else "stderr", BrokenOutput())
        assert cli.main(case["args"] + (["--json"] if json_mode else [])) == 4


def test_interruption_does_not_print_traceback(tmp_path, monkeypatch, capsys):
    case = make_case(tmp_path)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt(str(case["directory"]))
    monkeypatch.setattr(cli, "resolve_local", interrupted)
    assert cli.main(case["args"]) == 4
    output = capsys.readouterr()
    assert_private(output.out + output.err, case)
    assert "KeyboardInterrupt" not in output.err


@pytest.mark.parametrize("args", [["--help"], ["resolve-local", "--help"]])
def test_module_invocation_static_help(args):
    result = subprocess.run([sys.executable, "-m", "xingshu_core.runtime_cli", *args],
                            capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 0 and not result.stderr
    assert "resolve-local" in result.stdout
    assert PATH_PRIVATE not in result.stdout and "--force" not in result.stdout
