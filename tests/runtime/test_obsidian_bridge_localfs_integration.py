"""P5C 合成 Vault 完整验证；不修改冻结生产实现或访问私人来源。"""

import json
import os
import sys
from pathlib import Path

import pytest

from xingshu_core import obsidian_bridge as bridge, runtime_cli as cli, runtime_host as host
from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import RuntimeFailureCategory as Category, RuntimeResultKind as Kind

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from obsidian_bridge_fixtures import (
    BODY, ENTRY, HIDDEN, NEIGHBOR, RAW, digest, host_cases, instrument, make_case, run_unchanged,
)


def assert_local(result, category):
    assert result.kind is Kind.LOCAL_EXECUTION_FAILURE
    assert result.local_failure.category is category
    assert result.response is None and result.validation is None


def assert_success(result, raw):
    assert result.kind is Kind.SUCCESS
    payload = result.response["payload"][0]
    assert payload["text"] == raw.decode("utf-8")
    assert payload["byte_count"] == len(raw)
    assert payload["content_fingerprint"] == result.response["provenance"]["content_fingerprint"] == digest(raw)
    assert result.validation.decision is Decision.PASS
    assert result.validation.status == "resolve_exchange_valid"


def test_real_vault_success_exact_bytes_authority_and_zero_neighbor_probe(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    disk = case["target"].read_bytes()
    assert disk == RAW and disk.startswith(b"\xef\xbb\xbf") and disk.endswith(b"\r\n")
    assert (case["root"] / "Private/Finance.md").read_text() == NEIGHBOR
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_success(result, disk)
    assert trace["events"] == ["compose", "runtime", "clock", "authority", "wrapper", "localfs",
                               "read", "clock", "source", "clock", "authority", "resolve"]
    assert len(trace["wrappers"]) == len(trace["delegates"]) == len(trace["buffers"]) == 1
    assert trace["wrappers"][0] is trace["delegates"][0]
    assert trace["wrappers"][0]["target_locator"] == ENTRY
    raw = trace["buffers"][0]
    assert raw == disk and trace["executions"][0].exact_content_bytes is raw
    assert trace["source"][0][1]["exact_content_bytes"] is raw
    resolution = trace["resolve"][0][1]["resolution_context"]
    assert resolution["source_exchanges"][0]["exact_content_bytes"] is raw
    assert trace["source"][0][2].status == "exchange_valid"
    assert trace["resolve"][0][2] is result.validation
    assert [row[2].decision for row in trace["authority"]] == [Decision.PASS] * 2
    assert result.response["provenance"]["observed_at"] == trace["times"][1]
    assert result.response["freshness"]["verified_at"] == trace["times"][2]
    assert trace["file_loads"] == list(case["files"].values())
    assert len(trace["loads"]) == 4
    ctx = trace["contexts"][0]
    for i, (name, attr) in enumerate((("reference", "reference_bytes"), ("profile", "client_profile_bytes"), ("binding", "runtime_binding_bytes"))):
        blob = getattr(ctx, attr)
        assert blob is trace["loads"][i][1][1]
        assert blob == case["files"][name].read_bytes() == case["blobs"][name]
        assert blob.endswith(b"\n\n")
        assert blob != json.dumps(case["records"][name], sort_keys=True).encode()
    assert ctx.selected_client_id == case["records"]["profile"]["client_id"] != "fake-client"
    assert ctx.scope_id == case["config"].scope_id != "fake-scope"
    assert ctx.source_id == case["records"]["reference"]["source_id"]
    assert ctx.selected_transport_binding_id == case["records"]["binding"]["transport_binding_id"]
    assert ctx.selected_transport_class == case["records"]["binding"]["transport_class"]
    delegate, wrapper = trace["composers"][0]
    assert type(delegate) is LocalFilesystemSourceAdapter and ctx.adapter is wrapper
    assert delegate._root == str(case["root"]) != "/synthetic-frontmatter-override"
    assert repr(wrapper) == "_ObsidianNoteAdapter()"
    assert all("Finance.md" not in name for name in trace["fs"])


@pytest.mark.parametrize("entry", [".obsidian/private.md", ".hidden/private.md", "folder/.private.md"])
def test_hidden_admission_precedes_localfs_and_preserves_plain_p4(tmp_path, monkeypatch, entry):
    case = make_case(tmp_path, entry=entry, raw=HIDDEN.encode())
    assert case["target"].is_file()
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.SOURCE_FAILURE)
    assert len(trace["wrappers"]) == 1
    assert trace["delegates"] == trace["read_attempts"] == trace["executions"] == []
    assert trace["source"] == trace["resolve"] == []
    plain = run_unchanged(case, trace, monkeypatch, route="local")
    assert_success(plain, HIDDEN.encode())
    assert len(trace["composers"]) == len(trace["wrappers"]) == len(trace["delegates"]) == 1
    assert type(trace["contexts"][-1].adapter) is LocalFilesystemSourceAdapter


@pytest.mark.parametrize("entry", ["note.MD", "image.png", "document.pdf", "audio.mp3", "board.canvas"])
def test_real_media_never_read_or_repaired(tmp_path, monkeypatch, entry):
    case = make_case(tmp_path, entry=entry, raw=HIDDEN.encode())
    (case["root"] / "note.md").write_bytes(HIDDEN.encode())
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.SOURCE_FAILURE)
    assert len(trace["wrappers"]) == 1 and trace["wrappers"][0]["target_locator"] == entry
    assert trace["delegates"] == trace["buffers"] == []
    assert trace["source"] == trace["resolve"] == []


@pytest.mark.parametrize("entry,source_code", [
    ("../private.md", None), ("a%20b.md", "invalid_locator"),
    ("folder\\note.md", "invalid_locator"), ("/synthetic-outside/note.md", "invalid_locator"),
    ("Projects//XINGSHU.md", "invalid_locator"),
])
def test_path_protection_keeps_real_p4_error_semantics(tmp_path, monkeypatch, entry, source_code):
    case = make_case(tmp_path, entry=entry, materialize=False)
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.SOURCE_FAILURE)
    assert len(trace["wrappers"]) == 1 and not trace["buffers"]
    if source_code is None:
        assert not trace["delegates"] and not trace["source"]
    else:
        assert len(trace["delegates"]) == 1
        assert trace["executions"][0].response["error_code"] == source_code
        assert trace["source"][0][2].status == "exchange_error_valid"
    assert not trace["resolve"]


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_real_links_rejected_by_localfs(tmp_path, monkeypatch, link):
    case = make_case(tmp_path, raw=None)
    other = case["root"] / "private-target.md"
    other.write_bytes(HIDDEN.encode())
    if link == "symlink":
        case["target"].symlink_to(other)
    else:
        os.link(other, case["target"])
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.SOURCE_FAILURE)
    assert len(trace["wrappers"]) == len(trace["delegates"]) == 1
    assert not trace["buffers"]
    assert trace["executions"][0].response["error_code"] == "containment_failed"
    assert trace["source"][0][2].status == "exchange_error_valid"


def test_live_content_changes_observation_without_authority_changes(tmp_path, monkeypatch):
    first_raw, second_raw = RAW + b"Version A\r\n", RAW + b"Version B\r\n"
    case = make_case(tmp_path, raw=first_raw)
    trace = instrument(monkeypatch)
    first = run_unchanged(case, trace, monkeypatch)
    case["target"].write_bytes(second_raw)
    second = run_unchanged(case, trace, monkeypatch)
    assert_success(first, first_raw)
    assert_success(second, second_raw)
    assert trace["buffers"] == [first_raw, second_raw]
    assert len(trace["wrappers"]) == len(trace["delegates"]) == 2
    assert first.response["provenance"]["observation_id"] != second.response["provenance"]["observation_id"]
    assert first.response["provenance"]["content_fingerprint"] != second.response["provenance"]["content_fingerprint"]
    assert first.response["freshness"]["verified_at"] < second.response["provenance"]["observed_at"]


def test_fixed_fingerprint_blocks_new_content_with_frozen_semantics(tmp_path, monkeypatch):
    case = make_case(tmp_path, fixed=True)
    trace = instrument(monkeypatch)
    assert_success(run_unchanged(case, trace, monkeypatch), RAW)
    case["target"].write_bytes(RAW + b"changed")
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.VALIDATION_FAILURE)
    assert len(trace["buffers"]) == 2
    assert len(trace["resolve"]) == 1
    assert trace["source"][-1][2].status == "exchange_valid"


def test_rename_then_old_path_reuse_is_exact_path_authority(tmp_path, monkeypatch):
    case = make_case(tmp_path, entry="Projects/A.md")
    trace = instrument(monkeypatch)
    assert_success(run_unchanged(case, trace, monkeypatch), RAW)
    case["target"].rename(case["target"].with_name("B.md"))
    failed = run_unchanged(case, trace, monkeypatch)
    assert_local(failed, Category.SOURCE_FAILURE)
    assert trace["executions"][-1].response["error_code"] == "not_found"
    assert len(trace["buffers"]) == 1
    replacement = b"Replacement A\n"
    case["target"].write_bytes(replacement)
    assert_success(run_unchanged(case, trace, monkeypatch), replacement)
    assert trace["buffers"] == [RAW, replacement]
    assert len(trace["wrappers"]) == len(trace["delegates"]) == 3


@pytest.mark.parametrize("options", [{"status": "paused"}, {"status": "revoked"},
                                      {"expiry": 6}, {"profile_status": "revoked"}])
def test_lifecycle_denied_by_p2d_before_wrapper(tmp_path, monkeypatch, options):
    case = make_case(tmp_path, **options)
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.INVALID_INPUT)
    assert trace["authority"][0][2].decision is Decision.REJECT
    assert trace["wrappers"] == trace["delegates"] == trace["buffers"] == []


def test_post_read_expiry_prevents_disclosure_and_p2e(tmp_path, monkeypatch):
    case = make_case(tmp_path, expiry=8)
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.INVALID_INPUT)
    assert trace["buffers"] == [RAW]
    assert [row[2].decision for row in trace["authority"]] == [Decision.PASS, Decision.REJECT]
    assert trace["source"][0][2].status == "exchange_valid"
    assert not trace["resolve"]


def test_limit_error_preserves_real_p2c_and_p2e_receipts(tmp_path, monkeypatch):
    case = make_case(tmp_path, limit=16)
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert result.kind is Kind.PROTOCOL_ERROR
    assert result.response["error_code"] == "limit_exceeded" and "payload" not in result.response
    assert trace["executions"][0].response["error_code"] == "limit_exceeded"
    assert trace["executions"][0].exact_content_bytes is None
    assert trace["source"][0][2].status == "exchange_error_valid"
    assert [row[2].decision for row in trace["authority"]] == [Decision.PASS] * 2
    assert result.validation is trace["resolve"][0][2]
    assert result.validation.status == "resolve_error_valid"


@pytest.mark.parametrize("raw,category,source_code", [
    (b"\xff\xfe" + BODY.encode(), Category.SOURCE_FAILURE, "unsupported_encoding"),
    (b"", Category.VALIDATION_FAILURE, None),
])
def test_encoding_and_empty_note_keep_p4_behavior(tmp_path, monkeypatch, raw, category, source_code):
    case = make_case(tmp_path, raw=raw)
    trace = instrument(monkeypatch)
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, category)
    assert trace["buffers"] == [raw]
    assert not trace["resolve"]
    if source_code:
        assert trace["executions"][0].response["error_code"] == source_code
        assert trace["source"][0][2].status == "exchange_error_valid"
    else:
        assert trace["executions"][0].exact_content_bytes == b""
        assert trace["source"][0][2].status == "exchange_valid"


def test_cli_remains_plain_and_request_cannot_disable_obsidian_policy(tmp_path, monkeypatch, capsys):
    case = make_case(tmp_path, entry=".obsidian/private.md", raw=HIDDEN.encode())
    trace = instrument(monkeypatch)
    assert cli.main(case["args"]) == 0
    assert HIDDEN in capsys.readouterr().out
    assert not trace["composers"] and not trace["wrappers"]
    assert type(trace["contexts"][0].adapter) is LocalFilesystemSourceAdapter
    query = case["records"]["request"]
    query["adapter_composer"] = "disable_policy"
    case["blobs"]["request"] = host_cases.format_json(query)
    case["files"]["request"].write_bytes(case["blobs"]["request"])
    result = run_unchanged(case, trace, monkeypatch)
    assert_local(result, Category.INVALID_INPUT)
    assert len(trace["composers"]) == 1
    assert type(trace["contexts"][-1].adapter) is bridge._ObsidianNoteAdapter
    assert len(trace["delegates"]) == 1  # 仅第一次普通 CLI 读取。
