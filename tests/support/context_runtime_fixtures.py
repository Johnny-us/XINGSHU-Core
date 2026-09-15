"""P4C 纯内存合成对象；不读取 Source、不构造 LocalFS，不证明现实授权。"""

import copy
from datetime import datetime

import context_bridge_fixtures as fixtures
from xingshu_core.runtime_contracts import RuntimeContext, SourceAdapterExecution


ENTRY = "synthetic:entry:alpha"
SECOND = "synthetic:entry:beta"
SENTINEL = "SYNTHETIC_P4C_PRIVATE_BODY"
RAW = b"\xef\xbb\xbfSynthetic\r\n\xe4\xb9\x99\n"


class FakeAdapter:
    """只在 execute 被调用时用显式原始 bytes 生成本次合成观察。"""

    def __init__(self, events):
        self.events = events
        self.manifest_calls = self.execute_calls = 0
        self.raw = RAW
        self.code = None
        self.transform = None
        self.requests = []
        self.last_execution = None
        self.observed_at = fixtures.utc_timestamp(7)
        self.manifest_object = {
            "schema_version": fixtures.SCHEMA_VERSION, "object_kind": "source_adapter_manifest",
            "adapter_id": "synthetic-adapter", "adapter_contract_version": "synthetic-v1",
            "supported_operations": ["read"], "supported_content_types": ["text/plain", "text/markdown"],
            "default_encoding": "utf-8", "binary_supported": False,
            "hard_limits": {"max_items": 1, "max_bytes": 256, "max_depth": 0},
        }

    def manifest(self):
        self.manifest_calls += 1
        self.events.append("manifest")
        return self.manifest_object

    def execute(self, request):
        self.execute_calls += 1
        self.events.append("execute")
        self.requests.append(copy.deepcopy(request))
        if self.code is not None:
            response = fixtures.build_source_adapter_error(request)
            response.update(error_code=self.code, observed_at=self.observed_at)
            raw = None
        else:
            raw = self.raw
            response = {
                "schema_version": fixtures.SCHEMA_VERSION, "object_kind": "source_adapter_result", "ok": True,
                **{key: request[key] for key in ("request_id", "adapter_id", "operation", "source_id", "scope_id")},
                "provenance": {
                    **{key: request[key] for key in ("adapter_id", "operation", "source_id", "scope_id")},
                    "observed_at": self.observed_at, "observation_id": f"synthetic-observation-{self.execute_calls}",
                    "content_fingerprint": fixtures.fingerprint(raw),
                },
                "applied_limits": {"max_items": 1, "max_bytes": request["requested_limits"]["max_bytes"],
                                   "observed_items": 1, "observed_bytes": len(raw), "truncated": False},
                "payload": {"payload_kind": "read", "locator": request["target_locator"],
                            "content_type": "text/markdown", "encoding": "utf-8", "text": raw.decode("utf-8"),
                            "byte_count": len(raw), "content_fingerprint": fixtures.fingerprint(raw), "truncated": False},
            }
        if self.transform:
            response, raw = self.transform(response, raw)
        self.last_execution = SourceAdapterExecution(response=response, exact_content_bytes=raw)
        return self.last_execution


def make_case():
    events = []
    reference = fixtures.build_registered_context_reference({
        "authorization_id": "synthetic-authorization", "context_type": "document", "source_id": "synthetic-source",
        "final_canonical_name": "Synthetic P4C document", "final_source_locator": "synthetic:root",
        "final_source_entry_points": [ENTRY], "final_access_scope": "private",
        "final_allowed_clients": [fixtures.SYNTHETIC_CLIENT_ID], "final_freshness_policy": "verify_before_use",
        "final_provenance_policy": "locator_and_verification", "retrieval_hint": "Synthetic entry only",
        "initial_status": "active",
    })
    profile = {
        "schema_version": fixtures.SCHEMA_VERSION, "object_kind": "trusted_client_profile",
        "profile_id": "synthetic-profile", "client_id": fixtures.SYNTHETIC_CLIENT_ID, "profile_version": 1,
        "identity_origin": "owner_controlled", "client_class": "local_tool", "profile_status": "active",
        "created_at": fixtures.utc_timestamp(),
    }
    profile_bytes, reference_bytes = fixtures.encode_test_object(profile), fixtures.encode_test_object(reference)
    binding = fixtures.build_runtime_binding(profile, reference, profile_bytes=profile_bytes, reference_bytes=reference_bytes)
    moments = iter((fixtures.utc_timestamp(6), fixtures.utc_timestamp(8)))

    def clock():
        events.append("clock")
        return datetime.fromisoformat(next(moments).replace("Z", "+00:00"))

    adapter = FakeAdapter(events)
    arguments = dict(reference=reference, reference_bytes=reference_bytes,
                     client_profile=profile, client_profile_bytes=profile_bytes,
                     runtime_binding=binding, runtime_binding_bytes=fixtures.encode_test_object(binding),
                     selected_client_id=profile["client_id"], source_id=reference["source_id"], scope_id="synthetic-scope",
                     adapter_id="synthetic-adapter", selected_transport_binding_id=binding["transport_binding_id"],
                     selected_transport_class=binding["transport_class"], adapter=adapter, clock=clock)
    return {"arguments": arguments, "request": fixtures.build_resolve_context_request(reference),
            "adapter": adapter, "events": events}


def rebind(case):
    """测试显式重绑已修改合成对象的 bytes；不修改业务字段或判断授权。"""
    arguments = case["arguments"]
    for name in ("reference", "client_profile"):
        arguments[name + "_bytes"] = fixtures.encode_test_object(arguments[name])
    binding = arguments["runtime_binding"]
    binding["reference_fingerprint"] = fixtures.fingerprint(arguments["reference_bytes"])
    binding["trusted_client_profile_fingerprint"] = fixtures.fingerprint(arguments["client_profile_bytes"])
    arguments["runtime_binding_bytes"] = fixtures.encode_test_object(binding)


def context(case):
    return RuntimeContext(**case["arguments"])
