"""P4D：真实临时 Markdown + 冻结 Runtime/LocalFS + 原 P2D/P2C/P2E。

只对测试主动创建的本地 Source 读写；不接触真实 Vault、账号或项目文档。
"""

import ast
import copy
import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

from xingshu_core import context_runtime as runtime
from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeContext, SourceAdapterExecution
from xingshu_core.runtime_contracts import RuntimeFailureCategory as Category, RuntimeResultKind as Kind

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from context_runtime_localfs_fixtures import ENTRY, RAW, SENTINEL, build_case, fixtures, instrument, resolve_unchanged


def assert_private(case, outcome):
    rendered = repr(outcome)
    if outcome.local_failure is not None:
        rendered += json.dumps(outcome.local_failure.to_dict())
    if outcome.kind is not Kind.SUCCESS:
        rendered += json.dumps(outcome.response)
    ctx = case["context"]
    for private in (str(case["root"]), str(case["root"].resolve()), str(case["target"]),
                    SENTINEL, "UnicodeDecodeError", "Traceback", "credential-synthetic",
                    ctx.reference_bytes.decode(), ctx.client_profile_bytes.decode(), ctx.runtime_binding_bytes.decode()):
        assert private not in rendered


def assert_local(case, outcome, category):
    assert outcome.kind is Kind.LOCAL_EXECUTION_FAILURE
    assert outcome.local_failure.category is category
    assert outcome.response is None and outcome.validation is None
    assert_private(case, outcome)


def assert_payload(outcome, raw, entry=ENTRY):
    assert outcome.kind is Kind.SUCCESS
    assert outcome.validation.decision is Decision.PASS
    assert outcome.validation.status == "resolve_exchange_valid"
    expected = "sha256:" + hashlib.sha256(raw).hexdigest()
    payload = outcome.response["payload"][0]
    assert payload["entry_point"] == entry
    assert payload["text"] == raw.decode("utf-8")
    assert payload["byte_count"] == outcome.response["applied_limits"]["returned_bytes"] == len(raw)
    assert payload["content_fingerprint"] == outcome.response["provenance"]["content_fingerprint"] == expected
    assert outcome.response["minimum_disclosure"] is True
    assert outcome.response["payload_persistence"] == "transient_only"


@pytest.mark.parametrize("raw", [RAW, RAW + b"x" * 70000 + b"\r\n"], ids=["bom_crlf_utf8", "multiple_read_chunks"])
def test_real_localfs_full_chain_preserves_exact_bytes(tmp_path, monkeypatch, raw):
    case = build_case(tmp_path, raw=raw)
    assert type(case["adapter"]) is LocalFilesystemSourceAdapter
    assert type(case["context"]) is RuntimeContext
    assert case["context"].adapter is case["adapter"]
    assert case["context"].clock is case["adapter"]._clock
    assert case["context"].reference["source_entry_points"] == [ENTRY]
    assert case["context"].runtime_binding["bound_entry_points"] == [ENTRY]
    disk_bytes = case["target"].read_bytes()
    assert disk_bytes == raw
    trace = instrument(case, monkeypatch)
    outcome = resolve_unchanged(case)
    assert_payload(outcome, disk_bytes)
    assert_private(case, outcome)
    assert case["events"] == ["clock", "authority", "manifest", "execute", "clock", "p2c", "clock", "authority", "p2e"]
    assert case["times"] == [fixtures.utc_timestamp(t) for t in (6, 7, 8)]
    assert len(trace["executions"]) == len(trace["buffers"]) == len(trace["source"]) == len(trace["resolve"]) == 1
    execution = trace["executions"][0]
    assert type(execution) is SourceAdapterExecution
    observed_bytes = trace["buffers"][0]
    assert observed_bytes == disk_bytes
    assert execution.exact_content_bytes is observed_bytes
    assert trace["source"][0][0] is observed_bytes
    assert any(blob is observed_bytes for blob in trace["fingerprint_bytes"])
    resolution_context, receipt = trace["resolve"][0]
    assert resolution_context["source_exchanges"][0]["exact_content_bytes"] is observed_bytes
    assert resolution_context["authority_context"] is trace["authority"][0][0]
    assert outcome.validation is receipt
    assert [result.decision for _, result in trace["authority"]] == [Decision.PASS, Decision.PASS]
    assert [result.status for _, result in trace["authority"]] == ["authority_context_eligible"] * 2
    assert trace["source"][0][1].decision is Decision.PASS
    assert trace["source"][0][1].status == "exchange_valid"
    assert receipt.decision is Decision.PASS and receipt.status == "resolve_exchange_valid"
    assert [ctx["evaluated_at"] for ctx, _ in trace["authority"]] == [case["times"][0], case["times"][2]]
    assert execution.response["provenance"]["observed_at"] == case["times"][1]
    assert outcome.response["freshness"]["verified_at"] == resolution_context["resolved_at"] == case["times"][2]


def test_same_adapter_reads_live_version_b_without_reregistering(tmp_path, monkeypatch):
    version_a, version_b = RAW + b"Version A\r\n", RAW + "Version B 新版本\r\n".encode("utf-8")
    case = build_case(tmp_path, raw=version_a)
    ctx = case["context"]
    assert "content_fingerprint" not in ctx.reference
    original = copy.deepcopy((ctx.reference, ctx.client_profile, ctx.runtime_binding, case["request"]))
    original_bytes = (ctx.reference_bytes, ctx.client_profile_bytes, ctx.runtime_binding_bytes)
    trace = instrument(case, monkeypatch)
    first = resolve_unchanged(case)
    assert_payload(first, case["target"].read_bytes())
    case["target"].write_bytes(version_b)  # 唯一主动更新；不更新授权、登记或缓存。
    second = resolve_unchanged(case)
    assert_payload(second, case["target"].read_bytes())
    assert first.response["payload"][0]["text"] == version_a.decode("utf-8")
    assert second.response["payload"][0]["text"] == version_b.decode("utf-8")
    assert first.response["provenance"]["content_fingerprint"] != second.response["provenance"]["content_fingerprint"]
    assert first.response["provenance"]["observation_id"] != second.response["provenance"]["observation_id"]
    assert [execution.exact_content_bytes for execution in trace["executions"]] == [version_a, version_b]
    assert len(trace["executions"]) == case["events"].count("manifest") == 2
    assert case["context"] is ctx and ctx.adapter is case["adapter"]
    assert (ctx.reference, ctx.client_profile, ctx.runtime_binding, case["request"]) == original
    assert (ctx.reference_bytes, ctx.client_profile_bytes, ctx.runtime_binding_bytes) == original_bytes
    assert case["times"] == [fixtures.utc_timestamp(t) for t in (6, 7, 8, 10, 11, 12)]


@pytest.mark.parametrize("status", ["paused", "revoked"])
def test_real_adapter_not_executed_when_reference_inactive(tmp_path, monkeypatch, status):
    case = build_case(tmp_path, status=status, raw=SENTINEL.encode())
    trace = instrument(case, monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Pre-read authority must prevent real adapter calls")

    monkeypatch.setattr(case["adapter"], "manifest", forbidden)
    monkeypatch.setattr(case["adapter"], "execute", forbidden)
    outcome = resolve_unchanged(case)
    assert_local(case, outcome, Category.INVALID_INPUT)
    assert len(trace["authority"]) == 1 and trace["authority"][0][1].decision is Decision.REJECT
    assert not trace["source"] and not trace["resolve"]


def test_private_neighbor_outside_authority_is_never_read(tmp_path, monkeypatch):
    case = build_case(tmp_path, entry="notes/allowed.md")
    (case["root"] / "notes/private.md").write_bytes((SENTINEL + " credential-synthetic").encode())
    case["request"]["entry_selection"] = ["notes/private.md"]
    trace = instrument(case, monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Out-of-scope entry must not reach LocalFS execute")

    monkeypatch.setattr(case["adapter"], "execute", forbidden)
    outcome = resolve_unchanged(case)
    assert_local(case, outcome, Category.INVALID_INPUT)
    assert trace["authority"][0][1].decision is Decision.PASS
    assert "execute" not in case["events"] and "manifest" not in case["events"]
    assert not trace["source"] and not trace["resolve"]


@pytest.mark.parametrize("entry,raw,source_code,category", [
    ("notes/missing.md", None, "not_found", Category.SOURCE_FAILURE),
    ("notes/bad.md", b"\xff\xfe" + SENTINEL.encode(), "unsupported_encoding", Category.SOURCE_FAILURE),
    ("empty.md", b"", None, Category.VALIDATION_FAILURE),
])
def test_real_source_local_failure_boundaries(tmp_path, monkeypatch, entry, raw, source_code, category):
    case = build_case(tmp_path, entry=entry, raw=raw)
    trace = instrument(case, monkeypatch)
    outcome = resolve_unchanged(case)
    assert_local(case, outcome, category)
    assert len(trace["executions"]) == len(trace["source"]) == 1
    source_execution = trace["executions"][0]
    if source_code:
        assert source_execution.response["object_kind"] == "source_adapter_error"
        assert source_execution.response["error_code"] == source_code
        assert source_execution.exact_content_bytes is None
        assert trace["source"][0][1].status == "exchange_error_valid"
    else:
        assert source_execution.response["object_kind"] == "source_adapter_result"
        assert source_execution.exact_content_bytes == b""
        assert source_execution.response["payload"]["text"] == ""
        assert source_execution.response["payload"]["byte_count"] == 0
        assert trace["source"][0][1].status == "exchange_valid"
    assert trace["source"][0][1].decision is Decision.PASS
    assert len(trace["authority"]) == 2
    assert not trace["resolve"]
    assert repr(raw) not in repr(outcome)


def test_real_limit_exceeded_requires_p2e_error_receipt(tmp_path, monkeypatch):
    case = build_case(tmp_path, raw=(SENTINEL * 8).encode())
    case["request"]["requested_limits"]["max_bytes"] = 32
    trace = instrument(case, monkeypatch)
    outcome = resolve_unchanged(case)
    assert outcome.kind is Kind.PROTOCOL_ERROR
    assert outcome.response["error_code"] == "limit_exceeded"
    assert "payload" not in outcome.response
    assert_private(case, outcome)
    assert len(trace["executions"]) == 1
    source_execution = trace["executions"][0]
    assert source_execution.response["error_code"] == "limit_exceeded"
    assert source_execution.exact_content_bytes is None
    assert trace["source"][0][1].decision is Decision.PASS
    assert trace["source"][0][1].status == "exchange_error_valid"
    assert outcome.validation is trace["resolve"][0][1]
    assert outcome.validation.decision is Decision.PASS and outcome.validation.status == "resolve_error_valid"
    assert [receipt.decision for _, receipt in trace["authority"]] == [Decision.PASS, Decision.PASS]


@pytest.mark.parametrize("expiry", [7, 8])
def test_real_read_is_not_disclosed_after_authority_expires(tmp_path, monkeypatch, expiry):
    raw = (SENTINEL + " credential-synthetic").encode()
    case = build_case(tmp_path, raw=raw, expiry=expiry)
    trace = instrument(case, monkeypatch)
    outcome = resolve_unchanged(case)
    assert_local(case, outcome, Category.INVALID_INPUT)
    assert len(trace["executions"]) == 1 and trace["executions"][0].exact_content_bytes == raw
    assert trace["source"][0][1].decision is Decision.PASS
    assert [receipt.decision for _, receipt in trace["authority"]] == [Decision.PASS, Decision.REJECT]
    assert "authority_profile_expired" in {issue.code for issue in trace["authority"][1][1].errors}
    assert not trace["resolve"] and "p2e" not in case["events"]
    assert case["times"] == [fixtures.utc_timestamp(t) for t in (6, 7, 8)]


def test_frozen_runtime_has_no_localfs_branch_or_source_persistence():
    tree = ast.parse(inspect.getsource(runtime))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "local_filesystem_adapter" not in imports
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "LocalFilesystemSourceAdapter" not in names
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {"write", "write_bytes", "write_text", "open", "mkdir", "dump", "encode"}
    assert not names & {"open", "print"}
