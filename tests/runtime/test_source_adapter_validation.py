"""P2C 合成声明回归：不读取来源，不证明来源可用或取得权限。"""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

from xingshu_core import source_adapter_validation as source
from xingshu_core.decisions import Decision
from xingshu_core.schema_registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/support"))
import context_bridge_fixtures as fixtures  # noqa: E402

SCHEMA_REF = "schemas/candidate/context-bridge/source-adapter-contract.schema.json"
SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)


def read_sample():
    manifest = fixtures.load_source_adapter_manifest_seed()
    request = fixtures.build_source_adapter_request(manifest)
    response = fixtures.build_source_adapter_result(request)
    return manifest, request, response


def non_read_sample(operation):
    """明确构造三个非 read 样本的载荷；不计算任何预期决定。"""
    manifest, request, response = read_sample()
    request["operation"] = response["operation"] = operation
    response["provenance"]["operation"] = operation
    del response["provenance"]["content_fingerprint"]
    response["applied_limits"]["observed_bytes"] = 0
    if operation == "capabilities":
        del request["target_locator"]
        response["payload"] = {"payload_kind": "capabilities", "operations": ["read"]}
    elif operation == "list":
        response["payload"] = {
            "payload_kind": "list",
            "items": [{"locator": fixtures.SYNTHETIC_ENTRY, "item_type": "text"}],
        }
    elif operation == "stat":
        response["payload"] = {
            "payload_kind": "stat", "locator": fixtures.SYNTHETIC_ENTRY,
            "item_type": "text", "byte_count": 8192,
        }
    else:
        raise ValueError("unknown synthetic case")
    return manifest, request, response


class SourceAdapterValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()

    def setUp(self):
        self.manifest, self.request, self.response = read_sample()

    def exchange(self, manifest=None, request=None, response=None, **kwargs):
        # 本辅助入口只使用完整正向默认值；缺失对象案例直接调用公开 API。
        return source.validate_source_adapter_exchange(
            self.manifest if manifest is None else manifest,
            self.request if request is None else request,
            self.response if response is None else response,
            registry=self.registry, **kwargs,
        )

    def assert_positive(self, result, route, status):
        self.assertEqual(Decision.PASS, result.decision)
        self.assertEqual(status, result.status)
        self.assertEqual(route, result.record_type)
        self.assertEqual("context-bridge-candidate", result.schema_version)
        self.assertEqual(SCHEMA_REF, result.schema_ref)
        self.assertEqual((), result.errors)

    def assert_failure(self, result, code, path=None, decision=Decision.REJECT, status="rejected"):
        self.assertEqual(decision, result.decision)
        self.assertEqual(status, result.status)
        self.assertIn(code, {issue.code for issue in result.errors})
        if path is not None:
            self.assertIn((code, path), {(issue.code, issue.path) for issue in result.errors})
        rendered = str(result) + json.dumps(result.to_dict(), ensure_ascii=False)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, rendered)

    def test_four_single_object_positive_results_and_immutability(self):
        objects = (
            (self.manifest, "source_adapter_manifest", "object_valid"),
            (self.request, "source_adapter_request", "object_valid"),
            (self.response, "source_adapter_result", "object_valid"),
            (fixtures.build_source_adapter_error(self.request), "source_adapter_error", "error_envelope_valid"),
        )
        for record, route, status in objects:
            with self.subTest(route=route):
                before = copy.deepcopy(record)
                self.assert_positive(source.validate_source_adapter_object(record, route, self.registry), route, status)
                self.assertEqual(before, record)

    def test_object_route_and_schema_failures(self):
        self.assert_failure(source.validate_source_adapter_object(self.request, "source_adapter_manifest", self.registry), "source_adapter_route_mismatch", "$/object_kind")
        result = source.validate_source_adapter_object(self.manifest, SENTINELS[2], self.registry)
        self.assert_failure(result, "source_adapter_unsupported_route", "$")
        self.assertIsNone(result.record_type)
        self.assertIsNone(result.schema_ref)
        for record in (self.manifest, self.request, self.response, fixtures.build_source_adapter_error(self.request)):
            with self.subTest(route=record["object_kind"]):
                mutated = copy.deepcopy(record)
                mutated["synthetic_extra"] = SENTINELS[0]
                self.assert_failure(source.validate_source_adapter_object(mutated, record["object_kind"], self.registry), "source_adapter_schema_invalid", "$")

    def test_non_json_and_cyclic_objects_are_rejected(self):
        cyclic = copy.deepcopy(self.request)
        cyclic["synthetic_cycle"] = cyclic
        for record in (None, [], {1: SENTINELS[0]}, cyclic):
            with self.subTest(kind=type(record).__name__):
                self.assert_failure(source.validate_source_adapter_object(record, "source_adapter_request", self.registry), "source_adapter_invalid_object", "$")

    def test_missing_context_short_circuits_malformed_objects(self):
        cases = (
            ({"object_kind": SENTINELS[2]}, None, self.response, "request"),
            (self.manifest, {"object_kind": SENTINELS[2]}, None, "response"),
            (None, self.request, self.response, "manifest"),
        )
        for manifest, request, response, missing in cases:
            with self.subTest(missing=missing), patch.object(source, "validate_source_adapter_object") as public_object, patch.object(self.registry, "validator_for") as strict:
                result = source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry)
                self.assert_failure(result, "source_adapter_missing_context", "$/" + missing, Decision.NEEDS_REVIEW, "incomplete_exchange")
                self.assertEqual(1, len(result.errors))
                self.assertIsNone(result.record_type)
                public_object.assert_not_called()
                strict.assert_not_called()

    def test_missing_context_never_constructs_registry(self):
        with patch.object(source, "SchemaRegistry", side_effect=MemoryError(SENTINELS[0])) as factory:
            result = source.validate_source_adapter_exchange(self.manifest, None, self.response)
        factory.assert_not_called()
        self.assert_failure(result, "source_adapter_missing_context", "$/request", Decision.NEEDS_REVIEW, "incomplete_exchange")

    def test_complete_context_returns_first_failure_in_order(self):
        routes = ["source_adapter_manifest", "source_adapter_request", "source_adapter_result"]
        for first_bad, label in enumerate(("manifest", "request", "response")):
            objects = [copy.deepcopy(x) for x in (self.manifest, self.request, self.response)]
            for index in ((0, 1), (1, 2), (2,))[first_bad]:
                objects[index]["synthetic_extra"] = SENTINELS[2]
            with self.subTest(first=label), patch.object(self.registry, "validator_for", wraps=self.registry.validator_for) as strict:
                result = source.validate_source_adapter_exchange(*objects, registry=self.registry)
                self.assert_failure(result, "source_adapter_schema_invalid", "$/" + label)
                self.assertEqual(1, len(result.errors))
                self.assertEqual([call(route) for route in routes[:first_bad + 1]], strict.call_args_list)

    def test_complete_context_registry_and_strict_unavailable(self):
        with patch.object(source, "SchemaRegistry", side_effect=RuntimeError(SENTINELS[0])) as factory:
            result = source.validate_source_adapter_exchange(self.manifest, self.request, self.response)
        factory.assert_called_once_with()
        self.assert_failure(result, "source_adapter_validation_unavailable", "$", Decision.ERROR, "validation_unavailable")
        with patch.object(self.registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
            self.assert_failure(self.exchange(), "source_adapter_validation_unavailable", "$/manifest", Decision.ERROR, "validation_unavailable")
            self.assert_failure(source.validate_source_adapter_object(self.manifest, "source_adapter_manifest", self.registry), "source_adapter_validation_unavailable", "$", Decision.ERROR, "validation_unavailable")

    def test_read_exchange_exact_utf8_and_input_immutability(self):
        before = copy.deepcopy((self.manifest, self.request, self.response))
        text = self.response["payload"]["text"]
        exact = text.encode("utf-8")
        self.assertGreater(len(exact), len(text))
        self.assertIn("\n", text)
        self.assert_positive(self.exchange(exact_content_bytes=exact), "source_adapter_result", "exchange_valid")
        self.assertEqual(before, (self.manifest, self.request, self.response))
        self.assertEqual(before[2]["payload"]["text"].encode("utf-8"), exact)

    def test_error_exchange_validates_only_error_declarations(self):
        error = fixtures.build_source_adapter_error(self.request)
        before = copy.deepcopy(error)
        self.assert_positive(self.exchange(response=error), "source_adapter_error", "exchange_error_valid")
        self.assertEqual(before, error)

    def test_exact_bytes_mismatch_and_not_applicable(self):
        exact = self.response["payload"]["text"].encode("utf-8")
        for wrong in (exact[:-1] + b"!", exact.decode("utf-8"), bytearray(exact)):
            with self.subTest(type=type(wrong).__name__):
                self.assert_failure(self.exchange(exact_content_bytes=wrong), "source_adapter_exact_bytes_mismatch", "$/exact_content_bytes")
        for operation in ("capabilities", "list", "stat"):
            with self.subTest(operation=operation):
                self.assert_failure(source.validate_source_adapter_exchange(*non_read_sample(operation), exact_content_bytes=b"", registry=self.registry), "source_adapter_exact_bytes_not_applicable", "$/exact_content_bytes")
        self.assert_failure(self.exchange(response=fixtures.build_source_adapter_error(self.request), exact_content_bytes=b""), "source_adapter_exact_bytes_not_applicable", "$/exact_content_bytes")

    def test_exchange_identity_linkage(self):
        for field, code in (
            ("request_id", "source_adapter_request_id_mismatch"),
            ("adapter_id", "source_adapter_adapter_id_mismatch"),
            ("source_id", "source_adapter_source_id_mismatch"),
            ("scope_id", "source_adapter_scope_id_mismatch"),
        ):
            with self.subTest(field=field):
                response = copy.deepcopy(self.response)
                response[field] = SENTINELS[2]
                # 显式同步局部 provenance，隔离响应与请求这一条关系。
                if field in response["provenance"]:
                    response["provenance"][field] = response[field]
                self.assert_failure(self.exchange(response=response), code, "$/response/" + field)
        manifest = copy.deepcopy(self.manifest)
        manifest["adapter_id"] = SENTINELS[2]
        self.assert_failure(self.exchange(manifest=manifest), "source_adapter_adapter_id_mismatch", "$/request/adapter_id")
        request = copy.deepcopy(self.request)
        request["operation"] = "stat"
        self.assert_failure(self.exchange(request=request), "source_adapter_operation_mismatch", "$/response/operation")

    def test_object_provenance_linkage(self):
        for field in ("source_id", "scope_id", "adapter_id", "operation"):
            with self.subTest(field=field):
                response = copy.deepcopy(self.response)
                response["provenance"][field] = "stat" if field == "operation" else SENTINELS[2]
                self.assert_failure(source.validate_source_adapter_object(response, "source_adapter_result", self.registry), "source_adapter_provenance_mismatch", "$/provenance/" + field)

    def test_opaque_locators_are_compared_exactly(self):
        for sample in (read_sample(), non_read_sample("stat")):
            manifest, request, response = sample
            response["payload"]["locator"] = "synthetic:entry:alpha-normalized"
            self.assert_failure(source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry), "source_adapter_target_locator_mismatch", "$/response/payload/locator")

    def test_requested_and_applied_limit_ceilings(self):
        for field, value in (("max_items", 9), ("max_bytes", 4097), ("max_depth", 2)):
            with self.subTest(requested=field):
                request = copy.deepcopy(self.request)
                request["requested_limits"][field] = value
                self.assert_failure(self.exchange(request=request), "source_adapter_requested_limit_exceeded", "$/request/requested_limits/" + field)
        for field, value in (("max_items", 2), ("max_bytes", 1025)):
            with self.subTest(applied=field):
                response = copy.deepcopy(self.response)
                response["applied_limits"][field] = value
                self.assert_failure(self.exchange(response=response), "source_adapter_applied_limit_exceeded", "$/response/applied_limits/" + field)
        manifest, request, response = read_sample()
        manifest["hard_limits"]["max_bytes"] = 512
        request["requested_limits"]["max_bytes"] = 512
        self.assert_failure(source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry), "source_adapter_applied_limit_exceeded", "$/response/applied_limits/max_bytes")
        request = copy.deepcopy(self.request)
        request["requested_limits"]["max_bytes"] = 1
        self.assert_failure(self.exchange(request=request), "source_adapter_returned_bytes_limit_exceeded", "$/response/payload/text")

    def test_local_counts_truncation_and_content_bytes(self):
        size = self.response["payload"]["byte_count"]
        rows = (
            ("payload", "byte_count", size - 1, "source_adapter_byte_count_mismatch"),
            ("payload", "truncated", True, "source_adapter_truncation_mismatch"),
            ("applied_limits", "observed_items", 2, "source_adapter_read_item_count_exceeded"),
            ("applied_limits", "observed_bytes", size - 1, "source_adapter_read_bytes_underreported"),
            ("applied_limits", "observed_bytes", 1025, "source_adapter_observed_limit_exceeded"),
            ("applied_limits", "max_bytes", size - 1, "source_adapter_returned_bytes_limit_exceeded"),
        )
        for section, field, value, code in rows:
            with self.subTest(section=section, field=field):
                response = copy.deepcopy(self.response)
                response[section][field] = value
                self.assert_failure(source.validate_source_adapter_object(response, "source_adapter_result", self.registry), code)
        # observed_bytes 可包括额外开销；冻结合同没有强制它等于正文大小。
        response = copy.deepcopy(self.response)
        response["applied_limits"]["observed_bytes"] += 1
        self.assert_positive(self.exchange(response=response), "source_adapter_result", "exchange_valid")

    def test_content_and_provenance_fingerprints(self):
        for section in ("payload", "provenance"):
            with self.subTest(section=section):
                response = copy.deepcopy(self.response)
                response[section]["content_fingerprint"] = fixtures.fingerprint(b"Synthetic P3 different bytes")
                self.assert_failure(self.exchange(response=response), "source_adapter_fingerprint_mismatch", "$/response/" + section + "/content_fingerprint")
        response = copy.deepcopy(self.response)
        response["payload"]["text"] = "\ud800"
        self.assert_failure(self.exchange(response=response), "source_adapter_invalid_utf8", "$/response/payload/text")

    def test_all_four_operations_and_declared_capabilities(self):
        self.assert_positive(self.exchange(), "source_adapter_result", "exchange_valid")
        for operation in ("capabilities", "list", "stat"):
            with self.subTest(operation=operation):
                self.assert_positive(source.validate_source_adapter_exchange(*non_read_sample(operation), registry=self.registry), "source_adapter_result", "exchange_valid")
        manifest, request, response = non_read_sample("capabilities")
        manifest["supported_operations"] = ["capabilities"]
        self.assert_failure(source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry), "source_adapter_capabilities_mismatch", "$/response/payload/operations")
        manifest = copy.deepcopy(self.manifest)
        manifest["supported_operations"] = ["stat"]
        self.assert_failure(self.exchange(manifest=manifest), "source_adapter_operation_unsupported", "$/request/operation")
        response = copy.deepcopy(self.response)
        response["payload"]["content_type"] = "text/markdown"
        self.assert_failure(self.exchange(response=response), "source_adapter_content_type_unsupported", "$/response/payload/content_type")

    def test_list_underreporting_and_stat_size_is_not_disclosure_size(self):
        manifest, request, response = non_read_sample("list")
        response["applied_limits"]["observed_items"] = 0
        self.assert_failure(source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry), "source_adapter_list_items_underreported", "$/response/applied_limits/observed_items")
        manifest, request, response = non_read_sample("stat")
        self.assertGreater(response["payload"]["byte_count"], response["applied_limits"]["max_bytes"])
        self.assert_positive(source.validate_source_adapter_exchange(manifest, request, response, registry=self.registry), "source_adapter_result", "exchange_valid")

    def test_supplied_registry_reused(self):
        with patch.object(source, "SchemaRegistry", side_effect=AssertionError("unexpected registry")) as factory, patch.object(self.registry, "validator_for", wraps=self.registry.validator_for) as strict:
            self.assert_positive(source.validate_source_adapter_object(self.manifest, "source_adapter_manifest", self.registry), "source_adapter_manifest", "object_valid")
            self.assert_positive(self.exchange(), "source_adapter_result", "exchange_valid")
        factory.assert_not_called()
        self.assertEqual([call("source_adapter_manifest"), call("source_adapter_manifest"), call("source_adapter_request"), call("source_adapter_result")], strict.call_args_list)

    def test_diagnostics_do_not_echo_text_locator_or_id(self):
        manifest, request, response = read_sample()
        response = fixtures.build_source_adapter_result(request, text=SENTINELS[0])
        response["payload"]["byte_count"] += 1
        self.assert_failure(self.exchange(response=response), "source_adapter_byte_count_mismatch")
        response = copy.deepcopy(self.response)
        response["payload"]["locator"] = SENTINELS[1]
        self.assert_failure(self.exchange(response=response), "source_adapter_target_locator_mismatch")
        response = copy.deepcopy(self.response)
        response["request_id"] = SENTINELS[2]
        self.assert_failure(self.exchange(response=response), "source_adapter_request_id_mismatch")


if __name__ == "__main__":
    unittest.main()
