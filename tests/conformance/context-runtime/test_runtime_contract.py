"""P4A 合成共享合同测试；不执行来源 I/O、权限编排或真实 Resolve。

协议对象和 P2E 回执是显式合成的容器样本，不声称完成了证据验证。
"""

import ast
import copy
import dataclasses
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from xingshu_core import runtime_contracts as contracts
from xingshu_core.decisions import Decision, ValidationIssue, ValidationResult
from xingshu_core.runtime_contracts import (
    RuntimeContext, RuntimeExecutionResult, RuntimeFailureCategory,
    RuntimeLocalFailure, RuntimeResultKind, SourceAdapter,
)


SENTINEL = "SYNTHETIC_P4_PRIVATE_SENTINEL"
STAMP = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))


class FakeAdapter:
    """仅实现 read 的假适配器；没有来源读取或业务逻辑。"""

    def manifest(self):
        return {
            "schema_version": "context-bridge-candidate",
            "object_kind": "source_adapter_manifest",
            "adapter_id": "synthetic-p4-adapter", "adapter_contract_version": "0.1",
            "supported_operations": ["read"], "supported_content_types": ["text/markdown"],
            "default_encoding": "utf-8", "binary_supported": False,
            "hard_limits": {"max_items": 1, "max_bytes": 1024, "max_depth": 0},
        }

    def execute(self, request):
        return {
            "schema_version": "context-bridge-candidate", "object_kind": "source_adapter_error",
            "request_id": request["request_id"], "adapter_id": "synthetic-p4-adapter",
            "operation": "read", "error_code": "not_found", "retryable": False,
            "observed_at": "2026-01-01T00:00:00Z",
        }


def context_arguments():
    # 原始字节由测试显式提供；空白和键顺序不是生产序列化规则。
    return {
        "reference": {"reference_id": "synthetic-reference", "nested": {"value": 1}},
        "reference_bytes": b'{ "nested": {"value":1}, "reference_id":"synthetic-reference" }\n',
        "client_profile": {"client_id": "synthetic-client"},
        "client_profile_bytes": b'{ "client_id" : "synthetic-client" }\n',
        "runtime_binding": {"binding_id": "synthetic-binding"},
        "runtime_binding_bytes": b'{"binding_id":"synthetic-binding"}\n\n',
        "selected_client_id": "synthetic-client", "source_id": "synthetic-source",
        "scope_id": "synthetic-scope", "adapter_id": "synthetic-p4-adapter",
        "selected_transport_binding_id": "synthetic-transport",
        "selected_transport_class": "in_process", "adapter": FakeAdapter(),
        "clock": lambda: STAMP,
    }


def protocol_arguments(kind):
    route, status = {
        RuntimeResultKind.SUCCESS: ("resolve_context_result", "resolve_exchange_valid"),
        RuntimeResultKind.PROTOCOL_ERROR: ("resolve_context_error", "resolve_error_valid"),
    }[kind]
    return {
        "kind": kind,
        "response": {"object_kind": route},
        "validation": ValidationResult(
            Decision.PASS, status, route, "context-bridge-candidate",
            "schemas/candidate/context-bridge/resolve-context.schema.json",
        ),
    }


def test_adapter_protocol_accepts_read_only_fake_without_optional_operations():
    adapter = FakeAdapter()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.manifest()["supported_operations"] == ["read"]
    request = {"request_id": "synthetic-request", "operation": "read"}
    before = copy.deepcopy(request)
    assert adapter.execute(request)["object_kind"] == "source_adapter_error"
    assert request == before
    assert not any(hasattr(adapter, name) for name in ("list", "stat", "capabilities"))
    assert {name for name in SourceAdapter.__dict__ if not name.startswith("_")} == {"manifest", "execute"}


def test_contract_module_has_only_provider_neutral_dependencies():
    # 只回读本仓库合同源码做依赖审查，不读取来源定位符或用户目录。
    source = Path(contracts.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported == {"__future__", "collections.abc", "dataclasses", "datetime", "enum", "typing", "decisions"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert names.isdisjoint({"Path", "open", "local_filesystem_adapter", "context_runtime", "LocalFilesystemSourceAdapter", "dir_fd", "O_NOFOLLOW", "fstat"})
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name) and node.func.value.id == "datetime"
                   and node.func.attr == "now" for node in ast.walk(tree))


def test_context_retains_separate_exact_original_bytes_without_serialization():
    args = context_arguments()
    with patch.object(json, "dumps", side_effect=AssertionError("unexpected serialization")):
        context = RuntimeContext(**args)
    for name in ("reference", "client_profile", "runtime_binding"):
        assert getattr(context, name) is args[name]
        assert getattr(context, name + "_bytes") is args[name + "_bytes"]
        assert json.loads(getattr(context, name + "_bytes")) == args[name]
    assert context.reference_bytes.endswith(b" }\n")
    assert context.runtime_binding_bytes.endswith(b"\n\n")


@pytest.mark.parametrize("name", ["reference_bytes", "client_profile_bytes", "runtime_binding_bytes"])
@pytest.mark.parametrize("value", [None, SENTINEL, bytearray(b"synthetic")])
def test_original_bytes_cannot_be_omitted_or_replaced_by_non_native_bytes(name, value):
    args = context_arguments()
    args[name] = value
    with pytest.raises(TypeError, match="original record bytes must be native bytes"):
        RuntimeContext(**args)
    del args[name]
    with pytest.raises(TypeError):
        RuntimeContext(**args)


def test_context_does_not_repair_or_validate_supplied_records():
    args = context_arguments()
    args["reference_bytes"] = b"synthetic deliberately inconsistent original bytes"
    context = RuntimeContext(**args)
    assert context.reference_bytes is args["reference_bytes"]
    assert context.reference is args["reference"]
    # 接受容器不是接受记录；后续 P2D 门禁必须拒绝不一致证据。


def test_context_has_explicit_host_fields_and_no_request_conversion_or_root():
    expected = set(context_arguments())
    assert {f.name for f in dataclasses.fields(RuntimeContext)} == expected
    assert not any(hasattr(RuntimeContext, name) for name in ("from_request", "from_dict", "from_json"))
    with pytest.raises(TypeError):
        RuntimeContext(**{"object_kind": "resolve_context_request", "reference_id": "synthetic-reference"})
    for name in ("request", "root", "root_path", "authorization", "containment_proof", "client_id"):
        with pytest.raises(TypeError):
            RuntimeContext(**context_arguments(), **{name: SENTINEL})
    # 可信宿主可以显式调用构造器；同进程恶意伪装不在本阶段隔离承诺内。


@pytest.mark.parametrize("name", ["reference", "client_profile", "runtime_binding"])
def test_context_requires_record_mappings(name):
    args = context_arguments()
    args[name] = None
    with pytest.raises(TypeError):
        RuntimeContext(**args)


@pytest.mark.parametrize("name", ["selected_client_id", "source_id", "scope_id", "adapter_id", "selected_transport_binding_id", "selected_transport_class"])
def test_context_requires_explicit_nonempty_host_selection(name):
    args = context_arguments()
    args[name] = ""
    with pytest.raises(TypeError):
        RuntimeContext(**args)


def test_context_requires_adapter_and_clock_interfaces_without_invoking_them():
    args = context_arguments()
    adapter = Mock(spec=SourceAdapter)
    clock = Mock(return_value=STAMP)
    RuntimeContext(**dict(args, adapter=adapter, clock=clock))
    adapter.manifest.assert_not_called()
    adapter.execute.assert_not_called()
    clock.assert_not_called()
    for override in ({"adapter": object()}, {"clock": None}):
        with pytest.raises(TypeError):
            RuntimeContext(**dict(args, **override))


@pytest.mark.parametrize("kind", [RuntimeResultKind.SUCCESS, RuntimeResultKind.PROTOCOL_ERROR])
def test_protocol_outcomes_require_matching_receipts(kind):
    args = protocol_arguments(kind)
    result = RuntimeExecutionResult(**args)
    assert result.kind is kind
    assert result.response is args["response"]
    assert result.validation is args["validation"]
    assert result.local_failure is None


def test_local_failure_has_no_protocol_response_or_validation_receipt():
    failure = RuntimeLocalFailure(category=RuntimeFailureCategory.SOURCE_FAILURE)
    result = RuntimeExecutionResult(kind=RuntimeResultKind.LOCAL_EXECUTION_FAILURE, local_failure=failure)
    assert result.response is None and result.validation is None
    assert result.local_failure is failure
    assert {f.name for f in dataclasses.fields(result)} == {"kind", "response", "local_failure", "validation"}


@pytest.mark.parametrize("kind", list(RuntimeResultKind))
def test_neither_response_nor_failure_is_rejected(kind):
    with pytest.raises(ValueError):
        RuntimeExecutionResult(kind=kind)


@pytest.mark.parametrize("kind", list(RuntimeResultKind))
def test_response_and_local_failure_together_are_rejected(kind):
    args = protocol_arguments(RuntimeResultKind.SUCCESS)
    args.update(kind=kind, local_failure=RuntimeLocalFailure(category=RuntimeFailureCategory.SOURCE_FAILURE))
    with pytest.raises(ValueError):
        RuntimeExecutionResult(**args)


@pytest.mark.parametrize("kind", [RuntimeResultKind.SUCCESS, RuntimeResultKind.PROTOCOL_ERROR])
@pytest.mark.parametrize("override", [
    {"decision": Decision.REJECT}, {"decision": Decision.ERROR}, {"decision": Decision.NEEDS_REVIEW},
    {"status": "object_valid"}, {"record_type": "source_adapter_result"},
    {"schema_version": "synthetic-other"}, {"schema_ref": "synthetic-other"},
    {"errors": (ValidationIssue("synthetic", "$", "synthetic"),)},
])
def test_nonmatching_validation_receipts_cannot_mark_a_protocol_outcome(kind, override):
    args = protocol_arguments(kind)
    args["validation"] = dataclasses.replace(args["validation"], **override)
    with pytest.raises(ValueError):
        RuntimeExecutionResult(**args)


@pytest.mark.parametrize("kind", [RuntimeResultKind.SUCCESS, RuntimeResultKind.PROTOCOL_ERROR])
def test_protocol_outcome_rejects_missing_receipt_wrong_route_and_wrong_state(kind):
    args = protocol_arguments(kind)
    for change in ({"validation": None}, {"response": []}, {"response": {"object_kind": "source_adapter_error"}},
                   {"kind": RuntimeResultKind.PROTOCOL_ERROR if kind is RuntimeResultKind.SUCCESS else RuntimeResultKind.SUCCESS}):
        with pytest.raises(ValueError):
            RuntimeExecutionResult(**dict(args, **change))


def test_no_fourth_kind_and_no_receipt_on_local_failure():
    with pytest.raises(TypeError):
        RuntimeExecutionResult(kind="synthetic-fourth-state")
    with pytest.raises(ValueError):
        RuntimeExecutionResult(kind=RuntimeResultKind.LOCAL_EXECUTION_FAILURE,
                               local_failure=RuntimeLocalFailure(category=RuntimeFailureCategory.SOURCE_FAILURE),
                               validation=protocol_arguments(RuntimeResultKind.SUCCESS)["validation"])
    assert {k.value for k in RuntimeResultKind} == {"success", "protocol_error", "local_execution_failure"}


@pytest.mark.parametrize("category,message", [
    (RuntimeFailureCategory.INVALID_INPUT, "Runtime input could not be accepted."),
    (RuntimeFailureCategory.EXECUTION_UNAVAILABLE, "Runtime execution is unavailable."),
    (RuntimeFailureCategory.SOURCE_FAILURE, "Source operation could not be completed."),
    (RuntimeFailureCategory.VALIDATION_FAILURE, "Runtime evidence validation did not succeed."),
])
def test_failure_public_shape_has_only_fixed_category_and_message(category, message):
    failure = RuntimeLocalFailure(category=category)
    assert failure.to_dict() == {"category": category.value, "message": message}
    assert {f.name for f in dataclasses.fields(failure)} == {"category"}
    assert not isinstance(failure, (ValidationResult, Decision))
    forbidden = {"body", "content", "locator", "absolute_path", "credential", "exception", "traceback", "raw_bytes", "errno"}
    assert forbidden.isdisjoint(failure.to_dict())
    for name in forbidden | {"message", "authority"}:
        with pytest.raises(TypeError):
            RuntimeLocalFailure(category=category, **{name: SENTINEL})


def test_failure_rejects_arbitrary_categories_without_echo():
    with pytest.raises(TypeError) as caught:
        RuntimeLocalFailure(category=SENTINEL)
    assert SENTINEL not in str(caught.value)


class NoOffset(tzinfo):
    def utcoffset(self, value):
        return None


@pytest.mark.parametrize("value", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=NoOffset()), None, SENTINEL])
def test_clock_rejects_naive_or_invalid_values_without_normalizing(value):
    context = RuntimeContext(**dict(context_arguments(), clock=lambda: value))
    with pytest.raises(ValueError, match="offset-aware datetime") as caught:
        context.now()
    assert SENTINEL not in str(caught.value)


def test_clock_is_deterministic_offset_aware_and_sanitizes_failure():
    clock = Mock(return_value=STAMP)
    context = RuntimeContext(**dict(context_arguments(), clock=clock))
    assert context.now() is STAMP and context.now() is STAMP
    assert clock.call_count == 2
    assert STAMP.utcoffset() == timedelta(hours=8)
    context = dataclasses.replace(context, clock=Mock(side_effect=RuntimeError(SENTINEL)))
    with pytest.raises(ValueError) as caught:
        context.now()
    assert SENTINEL not in str(caught.value)
    assert caught.value.__context__ is None


def test_frozen_direct_attributes_and_safe_representations():
    context = RuntimeContext(**context_arguments())
    args = protocol_arguments(RuntimeResultKind.SUCCESS)
    args["response"]["synthetic_private_value"] = SENTINEL
    result = RuntimeExecutionResult(**args)
    failure = RuntimeLocalFailure(category=RuntimeFailureCategory.INVALID_INPUT)
    for value, name in ((context, "reference"), (result, "response"), (failure, "category")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, name, None)
        assert SENTINEL not in repr(value)
    assert repr(context) == "RuntimeContext()"
    assert not hasattr(result, "to_dict")


def test_shared_contract_does_not_perform_io_or_validation_or_mutate_inputs():
    from xingshu_core import authority_validation, context_bridge_validation, resolve_context_validation, source_adapter_validation, validator
    args = context_arguments()
    result_args = protocol_arguments(RuntimeResultKind.SUCCESS)
    records = [args[name] for name in ("reference", "client_profile", "runtime_binding")] + [result_args["response"]]
    before = copy.deepcopy(records)
    with ExitStack() as stack:
        guards = [stack.enter_context(patch(target, side_effect=AssertionError("unexpected I/O")))
                  for target in ("builtins.open", "io.open", "os.open")]
        for module in (authority_validation, context_bridge_validation, resolve_context_validation, source_adapter_validation, validator):
            for name in vars(module):
                if name.startswith("validate_"):
                    guards.append(stack.enter_context(patch.object(module, name, side_effect=AssertionError("unexpected validation"))))
        context = RuntimeContext(**args)
        assert context.now() is STAMP
        RuntimeExecutionResult(**result_args)
        RuntimeLocalFailure(category=RuntimeFailureCategory.INVALID_INPUT).to_dict()
        for guard in guards:
            guard.assert_not_called()
    assert records == before
