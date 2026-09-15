"""P4C 仅用内存 Fake Adapter 证明权限顺序；不接入真实 Source 或 LocalFS。"""

import ast
import copy
import dataclasses
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from xingshu_core import context_runtime as runtime
from xingshu_core.decisions import Decision, ValidationIssue
from xingshu_core.runtime_contracts import RuntimeFailureCategory as Category, RuntimeResultKind as Kind
from xingshu_core.source_adapter_validation import validate_source_adapter_object

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from context_runtime_fixtures import ENTRY, RAW, SECOND, SENTINEL, context, fixtures, make_case, rebind


def assert_local(outcome, category=None):
    assert outcome.kind is Kind.LOCAL_EXECUTION_FAILURE
    assert outcome.response is None and outcome.validation is None
    if category is not None:
        assert outcome.local_failure.category is category
    rendered = repr(outcome) + json.dumps(outcome.local_failure.to_dict())
    for secret in (SENTINEL, "/synthetic/private", "credential-synthetic", ENTRY):
        assert secret not in rendered


def test_happy_path_order_exact_bytes_and_real_validation(monkeypatch):
    case = make_case()
    ctx, query, events = context(case), case["request"], case["events"]
    original_query = copy.deepcopy(query)
    original_records = [copy.deepcopy(getattr(ctx, key)) for key in ("reference", "client_profile", "runtime_binding")]
    captured = {"authority_contexts": [], "authority_objects": []}
    ids = iter(("synthetic-new-source-id", "synthetic-new-verification-id"))
    monkeypatch.setattr(runtime, "_new_id", lambda: next(ids))
    originals = {name: getattr(runtime, name) for name in (
        "validate_resolve_context_object", "validate_reference_authority",
        "validate_source_adapter_exchange", "validate_resolve_context_exchange",
    )}

    def request_check(*args, **kwargs):
        events.append("request_validation")
        return originals["validate_resolve_context_object"](*args, **kwargs)

    def authority_check(*args, **kwargs):
        index = len(captured["authority_contexts"])
        events.append("authority_pre_read" if index == 0 else "authority_post_read")
        assert case["adapter"].manifest_calls == case["adapter"].execute_calls == index
        captured["authority_contexts"].append(kwargs["authority_context"])
        captured["authority_objects"].append(args)
        blobs = kwargs["authority_context"]["object_bytes"]
        assert blobs["registered_context_reference"] is ctx.reference_bytes
        assert blobs["trusted_client_profile"] is ctx.client_profile_bytes
        assert blobs["runtime_binding"] is ctx.runtime_binding_bytes
        result = originals["validate_reference_authority"](*args, **kwargs)
        assert result.decision is Decision.PASS and result.status == "authority_context_eligible"
        return result

    def source_check(*args, **kwargs):
        events.append("p2c")
        assert kwargs["exact_content_bytes"] is case["adapter"].raw
        before = copy.deepcopy(args)
        result = originals["validate_source_adapter_exchange"](*args, **kwargs)
        assert result.decision is Decision.PASS and result.status == "exchange_valid"
        assert args == before
        captured["source_response"] = copy.deepcopy(args[2])
        return result

    def final_check(*args, **kwargs):
        events.append("p2e")
        captured["resolution_context"] = kwargs["resolution_context"]
        assert kwargs["resolution_context"]["authority_context"] is captured["authority_contexts"][0]
        assert set(kwargs["resolution_context"]) == {
            "reference", "client_profile", "runtime_binding", "authority_context",
            "resolved_at", "source_exchanges", "resolution_event",
        }
        assert kwargs["resolution_context"]["source_exchanges"][0]["exact_content_bytes"] is case["adapter"].raw
        result = originals["validate_resolve_context_exchange"](*args, **kwargs)
        assert result.decision is Decision.PASS and result.status == "resolve_exchange_valid", result
        captured["receipt"] = result
        return result

    for name, func in zip(originals, (request_check, authority_check, source_check, final_check)):
        monkeypatch.setattr(runtime, name, func)
    outcome = runtime.resolve_registered_context(query, context=ctx)
    assert outcome.kind is Kind.SUCCESS
    assert outcome.validation is captured["receipt"]
    assert events == ["request_validation", "clock", "authority_pre_read", "manifest", "execute",
                      "p2c", "clock", "authority_post_read", "p2e"]
    first, second = captured["authority_contexts"]
    assert first is not second
    assert first["evaluated_at"] == fixtures.utc_timestamp(6)
    assert second["evaluated_at"] == fixtures.utc_timestamp(8)
    for key in ("object_bytes", "control_plane_selection"):
        assert first[key] is second[key]
    assert first["operation"] == second["operation"] == "resolve_context"
    assert {**first, "evaluated_at": second["evaluated_at"]} == second
    assert all(left is right for left, right in zip(*captured["authority_objects"], strict=True))
    assert case["adapter"].manifest_calls == case["adapter"].execute_calls == 1
    assert query == original_query
    assert [getattr(ctx, key) for key in ("reference", "client_profile", "runtime_binding")] == original_records
    assert case["adapter"].last_execution.response == captured["source_response"]
    response = outcome.response
    assert response["payload"][0]["entry_point"] == ENTRY
    assert response["payload"][0]["text"] == RAW.decode("utf-8")
    assert response["payload"][0]["content_fingerprint"] == fixtures.fingerprint(RAW)
    assert response["minimum_disclosure"] is True and response["payload_persistence"] == "transient_only"
    assert response["freshness"]["verified_at"] == fixtures.utc_timestamp(8)
    assert response["freshness"]["verification_evidence_id"] == "synthetic-new-verification-id"
    assert response["provenance"]["observed_at"] == fixtures.utc_timestamp(7)
    assert response["provenance"]["observation_id"] == "synthetic-observation-1"
    assert case["adapter"].requests[0]["request_id"] == "synthetic-new-source-id"


@pytest.mark.parametrize("scenario", [
    "invalid_request", "wrong_client", "revoked_profile", "expired_profile", "paused", "revoked", "archived",
    "binding_bytes", "reference_bytes", "reference_fingerprint", "profile_fingerprint", "binding_client",
    "wrong_transport", "wrong_transport_class", "operation", "access_scope", "source_identity", "reference_identity",
    "entry_outside_reference", "entry_outside_binding", "binding_outside_reference", "wildcard", "unreviewed",
    "parent", "ambiguous", "multiple", "immutable", "manual_verification", "provenance_policy",
    "query_hint", "disclosure_hints", "zero_bytes", "broadened_bytes", "zero_items", "unknown_limit",
])
def test_pre_read_rejections_never_call_manifest_or_execute(scenario):
    case = make_case()
    args, query = case["arguments"], case["request"]
    ref, profile, binding = args["reference"], args["client_profile"], args["runtime_binding"]
    if scenario == "invalid_request":
        query["authority"] = {"allow": True}
    elif scenario == "wrong_client":
        args["selected_client_id"] = "synthetic_other_client"
    elif scenario == "revoked_profile":
        profile.update(profile_status="revoked", revoked_at=fixtures.utc_timestamp(5))
    elif scenario == "expired_profile":
        profile["expires_at"] = fixtures.utc_timestamp(6)
    elif scenario in ("paused", "revoked", "archived"):
        ref["status"] = scenario
    elif scenario == "binding_client":
        binding["trusted_client_profile_id"] = "synthetic-other-profile"
    elif scenario == "wrong_transport":
        args["selected_transport_binding_id"] = "synthetic-other-transport"
    elif scenario == "wrong_transport_class":
        args["selected_transport_class"] = "stdio"
    elif scenario == "operation":
        binding["allowed_operations"] = ["get_reference"]
    elif scenario == "access_scope":
        binding["bound_access_scope"] = "shared"
    elif scenario == "source_identity":
        args["source_id"] = "synthetic-other-source"
    elif scenario == "reference_identity":
        query["reference_id"] = "synthetic-other-reference"
    elif scenario in ("entry_outside_reference", "entry_outside_binding", "unreviewed", "parent", "wildcard"):
        query["entry_selection"] = [{"parent": "synthetic:root", "wildcard": "*"}.get(scenario, SECOND)]
        if scenario == "entry_outside_binding":
            ref["source_entry_points"].append(SECOND)
    elif scenario == "binding_outside_reference":
        binding["bound_entry_points"] = [SECOND]
    elif scenario in ("ambiguous", "multiple"):
        ref["source_entry_points"].append(SECOND)
        binding["bound_entry_points"].append(SECOND)
        if scenario == "ambiguous":
            del query["entry_selection"]
        else:
            query["entry_selection"] = [ENTRY, SECOND]
            query["requested_limits"]["max_items"] = 2
    elif scenario in ("immutable", "manual_verification"):
        ref["freshness_policy"] = scenario
    elif scenario == "provenance_policy":
        ref["provenance_policy"] = "locator_only"
    elif scenario == "query_hint":
        query["query_hint"] = SENTINEL
    elif scenario == "disclosure_hints":
        query["disclosure_hints"] = ["summary_only"]
    elif scenario == "zero_bytes":
        query["requested_limits"]["max_bytes"] = 0
    elif scenario == "broadened_bytes":
        query["requested_limits"]["max_bytes"] = 1048577
    elif scenario == "zero_items":
        query["requested_limits"]["max_items"] = 0
    elif scenario == "unknown_limit":
        query["requested_limits"]["max_depth"] = 99
    rebind(case)
    if scenario == "binding_bytes":
        args["runtime_binding_bytes"] = b"{}"
    elif scenario == "reference_bytes":
        args["reference_bytes"] = b"{}"
    elif scenario in ("reference_fingerprint", "profile_fingerprint"):
        key = "reference_fingerprint" if scenario == "reference_fingerprint" else "trusted_client_profile_fingerprint"
        binding[key] = "sha256:" + "0" * 64
        args["runtime_binding_bytes"] = fixtures.encode_test_object(binding)
    before = copy.deepcopy(query)
    outcome = runtime.resolve_registered_context(query, context=context(case))
    assert_local(outcome)
    assert case["adapter"].manifest_calls == case["adapter"].execute_calls == 0
    assert query == before


@pytest.mark.parametrize("field,value", [
    ("adapter_id", "synthetic-wrong"), ("supported_operations", ["stat"]),
    ("default_encoding", "latin1"), ("binary_supported", True),
    ("hard_limits", {"max_items": 1, "max_bytes": 0}), ("supported_content_types", ["image/png"]),
])
def test_manifest_rejection_prevents_execution(field, value):
    case = make_case()
    case["adapter"].manifest_object[field] = value
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert_local(outcome, Category.VALIDATION_FAILURE)
    assert case["adapter"].manifest_calls == 1 and case["adapter"].execute_calls == 0


@pytest.mark.parametrize("caller,hard,expected", [(1024, 256, 256), (32, 256, 32), (128, 64, 64)])
def test_limits_legally_narrow_generated_source_request(caller, hard, expected):
    case = make_case()
    case["request"]["requested_limits"] = {"max_items": 128, "max_bytes": caller}
    case["adapter"].manifest_object["hard_limits"]["max_bytes"] = hard
    before = copy.deepcopy(case["request"])
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert outcome.kind is Kind.SUCCESS
    assert case["adapter"].requests[0]["requested_limits"] == {"max_items": 1, "max_bytes": expected, "max_depth": 0}
    assert outcome.response["applied_limits"]["max_bytes"] == expected
    assert case["request"] == before


def test_no_selection_single_reference_and_independent_source_id():
    case = make_case()
    del case["request"]["entry_selection"]
    case["request"]["request_id"] = "resolve/" + "a" * 200  # 合法 Resolve ID，不能当作 Source ID。
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert outcome.kind is Kind.SUCCESS
    source_query = case["adapter"].requests[0]
    assert source_query["request_id"] != case["request"]["request_id"]
    assert validate_source_adapter_object(source_query, "source_adapter_request").decision is Decision.PASS


@pytest.mark.parametrize("code", ["source_unavailable", "limit_exceeded"])
def test_supported_source_errors_require_real_p2e_receipt(code, monkeypatch):
    case = make_case()
    case["adapter"].code = code
    original = runtime.validate_resolve_context_exchange
    receipts = []

    def final(*args, **kwargs):
        assert "resolution_event" not in kwargs["resolution_context"]
        result = original(*args, **kwargs)
        receipts.append(result)
        return result

    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", final)
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert outcome.kind is Kind.PROTOCOL_ERROR
    assert len(receipts) == 1 and outcome.validation is receipts[0]
    assert receipts[0].decision is Decision.PASS and receipts[0].status == "resolve_error_valid"
    assert outcome.response["error_code"] == code
    assert "payload" not in outcome.response
    assert case["adapter"].execute_calls == 1


@pytest.mark.parametrize("source_code", [None, "source_unavailable", "limit_exceeded"])
@pytest.mark.parametrize("expiry", [7, 8, 9])
def test_post_read_expiry_gates_success_and_source_errors(monkeypatch, source_code, expiry):
    """读取前时间为 6，披露检查为 8；真实 P2D 判断中途/恰好/稍后到期。"""
    case = make_case()
    case["arguments"]["client_profile"]["expires_at"] = fixtures.utc_timestamp(expiry)
    case["adapter"].raw = SENTINEL.encode()
    case["adapter"].code = source_code
    rebind(case)
    ctx = context(case)
    original_authority = runtime.validate_reference_authority
    original_source = runtime.validate_source_adapter_exchange
    original_final = runtime.validate_resolve_context_exchange
    authorities, source_checks, finals = [], [], []

    def authority(*args, **kwargs):
        result = original_authority(*args, **kwargs)
        authorities.append((kwargs["authority_context"], result))
        return result

    def source(*args, **kwargs):
        result = original_source(*args, **kwargs)
        assert result.decision is Decision.PASS
        assert result.status == ("exchange_valid" if source_code is None else "exchange_error_valid")
        source_checks.append(result)
        return result

    def final(*args, **kwargs):
        assert expiry > 8, "Expired authority must stop before P2E"
        assert kwargs["resolution_context"]["authority_context"] is authorities[0][0]
        result = original_final(*args, **kwargs)
        finals.append(result)
        return result

    monkeypatch.setattr(runtime, "validate_reference_authority", authority)
    monkeypatch.setattr(runtime, "validate_source_adapter_exchange", source)
    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", final)
    outcome = runtime.resolve_registered_context(case["request"], context=ctx)
    assert len(authorities) == 2 and len(source_checks) == 1
    assert authorities[0][0]["evaluated_at"] == fixtures.utc_timestamp(6)
    assert authorities[1][0]["evaluated_at"] == fixtures.utc_timestamp(8)
    assert authorities[0][1].decision is Decision.PASS
    assert case["events"].count("clock") == 2
    assert case["adapter"].manifest_calls == case["adapter"].execute_calls == 1
    if expiry <= 8:
        assert authorities[1][1].decision is Decision.REJECT
        assert "authority_profile_expired" in {issue.code for issue in authorities[1][1].errors}
        assert_local(outcome, Category.INVALID_INPUT)
        assert not finals
        rendered = repr(outcome) + json.dumps(outcome.local_failure.to_dict())
        for private in (fixtures.utc_timestamp(expiry), ctx.selected_client_id,
                        ctx.reference["source_locator"], ctx.reference_bytes.decode(),
                        "authority_profile_expired", SENTINEL):
            assert private not in rendered
    else:
        assert authorities[1][1].decision is Decision.PASS
        assert len(finals) == 1 and finals[0].decision is Decision.PASS
        assert outcome.validation is finals[0]
        assert outcome.kind is (Kind.SUCCESS if source_code is None else Kind.PROTOCOL_ERROR)


@pytest.mark.parametrize("source_code", [None, "source_unavailable", "limit_exceeded"])
@pytest.mark.parametrize("post_decision", [Decision.ERROR, Decision.REJECT, Decision.NEEDS_REVIEW, Decision.PASS, "exception"])
def test_post_read_authority_noneligible_is_sanitized_without_retry(monkeypatch, source_code, post_decision):
    case = make_case()
    case["adapter"].code = source_code
    case["adapter"].raw = SENTINEL.encode()
    original_authority = runtime.validate_reference_authority
    original_source = runtime.validate_source_adapter_exchange
    calls, source_checks = [], []

    def source(*args, **kwargs):
        result = original_source(*args, **kwargs)
        assert result.decision is Decision.PASS
        source_checks.append(result)
        return result

    def authority(*args, **kwargs):
        result = original_authority(*args, **kwargs)
        assert result.decision is Decision.PASS
        calls.append(kwargs["authority_context"])
        if len(calls) == 1:
            return result
        assert len(source_checks) == 1
        if post_decision == "exception":
            raise RuntimeError(SENTINEL + " /synthetic/private credential-synthetic")
        # PASS 但非 eligible 同样不能放行；诊断哨兵不能进入本地失败。
        return dataclasses.replace(result, decision=post_decision, status="synthetic-ineligible",
                                   errors=(ValidationIssue("synthetic-diagnostic", "/synthetic/private", SENTINEL),))

    def forbidden_final(*_args, **_kwargs):
        pytest.fail("Second authority gate must prevent P2E")

    monkeypatch.setattr(runtime, "validate_reference_authority", authority)
    monkeypatch.setattr(runtime, "validate_source_adapter_exchange", source)
    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", forbidden_final)
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    expected = Category.EXECUTION_UNAVAILABLE if post_decision in (Decision.ERROR, "exception") else Category.INVALID_INPUT
    assert_local(outcome, expected)
    assert len(calls) == 2
    assert case["events"].count("clock") == 2
    assert case["adapter"].manifest_calls == case["adapter"].execute_calls == 1
    rendered = repr(outcome) + json.dumps(outcome.local_failure.to_dict())
    assert "synthetic-diagnostic" not in rendered


@pytest.mark.parametrize("code", ["not_found", "containment_failed", "unsupported_encoding", "provenance_unavailable"])
def test_unrepresentable_source_error_stays_local(code):
    case = make_case()
    case["adapter"].code = code
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert_local(outcome, Category.SOURCE_FAILURE)
    assert case["adapter"].execute_calls == 1


def test_valid_source_error_envelope_with_rejected_exchange_never_reaches_p2e(monkeypatch):
    case = make_case()
    case["adapter"].code = "source_unavailable"

    def wrong_id(response, raw):
        response["request_id"] = "synthetic-unrelated"
        assert validate_source_adapter_object(response, "source_adapter_error").decision is Decision.PASS
        return response, raw

    case["adapter"].transform = wrong_id
    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", lambda *_a, **_k: pytest.fail("P2C must gate P2E"))
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.VALIDATION_FAILURE)


@pytest.mark.parametrize("tamper", ["bytes", "fingerprint", "provenance", "byte_count", "locator", "truncated", "empty"])
def test_source_tampering_or_unsupported_payload_cannot_succeed(tamper):
    case = make_case()
    if tamper == "empty":
        case["adapter"].raw = b""
    else:
        def transform(response, raw):
            if tamper == "bytes":
                raw = b"tampered"
            elif tamper == "fingerprint":
                response["payload"]["content_fingerprint"] = "sha256:" + "0" * 64
            elif tamper == "provenance":
                response["provenance"]["source_id"] = "synthetic-other"
            elif tamper == "byte_count":
                response["payload"]["byte_count"] += 1
            elif tamper == "locator":
                response["payload"]["locator"] = SECOND
            elif tamper == "truncated":
                response["payload"]["truncated"] = response["applied_limits"]["truncated"] = True
            return response, raw
        case["adapter"].transform = transform
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.VALIDATION_FAILURE)
    assert case["adapter"].execute_calls == 1


@pytest.mark.parametrize("phase", ["manifest", "execute"])
def test_provider_exception_is_sanitized_without_localfs_coupling(monkeypatch, phase):
    case = make_case()
    calls = []

    def fail(*_args):
        calls.append(phase)
        raise OSError(5, SENTINEL + " credential-synthetic", "/synthetic/private")

    monkeypatch.setattr(case["adapter"], phase, fail)
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.SOURCE_FAILURE)
    assert calls == [phase]


@pytest.mark.parametrize("mode", ["bare_mapping", "mutated_request"])
def test_invalid_adapter_handoff_is_not_accepted(monkeypatch, mode):
    case = make_case()
    original = case["adapter"].execute

    def execute(query):
        result = original(query)
        if mode == "bare_mapping":
            return result.response
        query["target_locator"] = SECOND
        return result

    monkeypatch.setattr(case["adapter"], "execute", execute)
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.VALIDATION_FAILURE)
    assert case["adapter"].execute_calls == 1


@pytest.mark.parametrize("when", [5, 9])
def test_historical_or_future_source_observation_rejected_by_p2e(when):
    case = make_case()
    case["adapter"].observed_at = fixtures.utc_timestamp(when)
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.VALIDATION_FAILURE)


@pytest.mark.parametrize("phase", ["before", "after"])
def test_clock_failure_is_sanitized_and_never_retried(phase):
    case = make_case()
    calls = []

    def clock():
        calls.append("clock")
        if phase == "after" and len(calls) == 1:
            return datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc)
        raise ValueError(SENTINEL)

    case["arguments"]["clock"] = clock
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.EXECUTION_UNAVAILABLE)
    assert case["adapter"].execute_calls == (0 if phase == "before" else 1)


@pytest.mark.parametrize("protocol_error", [False, True])
def test_final_validation_rejection_cannot_issue_receipt(monkeypatch, protocol_error):
    case = make_case()
    if protocol_error:
        case["adapter"].code = "source_unavailable"
    original = runtime.validate_resolve_context_exchange

    def reject(*args, **kwargs):
        valid = original(*args, **kwargs)
        assert valid.decision is Decision.PASS
        return dataclasses.replace(valid, decision=Decision.REJECT, status="rejected")

    monkeypatch.setattr(runtime, "validate_resolve_context_exchange", reject)
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)), Category.VALIDATION_FAILURE)


def test_private_authority_and_source_body_are_absent_from_repr_and_local_failure():
    case = make_case()
    case["arguments"]["reference"]["canonical_name"] = SENTINEL + " credential-synthetic"
    rebind(case)
    case["adapter"].raw = SENTINEL.encode()
    outcome = runtime.resolve_registered_context(case["request"], context=context(case))
    assert outcome.kind is Kind.SUCCESS
    assert SENTINEL in outcome.response["payload"][0]["text"]
    assert SENTINEL not in repr(outcome)
    case = make_case()
    case["arguments"]["reference_bytes"] = (SENTINEL + " /synthetic/private credential-synthetic").encode()
    assert_local(runtime.resolve_registered_context(case["request"], context=context(case)))


def test_runtime_has_no_source_filesystem_or_reencoding_calls():
    tree = ast.parse(inspect.getsource(runtime))
    attrs = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not attrs & {"encode", "read_bytes", "write_bytes", "write_text", "open", "resolve"}
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "local_filesystem_adapter" not in imports
