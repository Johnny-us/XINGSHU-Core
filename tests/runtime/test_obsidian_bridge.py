"""P5B 最小组合、笔记准入及真实 P4 委托证据；完整 Vault 矩阵留给 P5C。"""

import inspect
import sys
from pathlib import Path

import pytest

from xingshu_core import obsidian_bridge as bridge, runtime_host as host
from xingshu_core.decisions import Decision
from xingshu_core.local_filesystem_adapter import LocalFilesystemSourceAdapter
from xingshu_core.runtime_contracts import (
    RuntimeFailureCategory, RuntimeResultKind, SourceAdapterExecution,
)

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
import runtime_host_fixtures as cases


CONTENT = ("---\ntags: [synthetic]\naliases: [Example]\nxingshu_allow: true\n---\n"
           "[[Private]]\n![[Private]]\n[[Note#Heading]]\n[[Note#^block]]\n").encode()


class Delegate:
    def __init__(self):
        self.offered = {"synthetic": "unchanged"}
        self.result = SourceAdapterExecution(
            response={"object_kind": "source_adapter_result", "operation": "read",
                      "payload": {"text": CONTENT.decode()}},
            exact_content_bytes=CONTENT,
        )
        self.requests = []
        self.manifest_calls = 0

    def __repr__(self):
        return "SYNTHETIC_PRIVATE_DELEGATE_ROOT_BODY"

    def manifest(self):
        self.manifest_calls += 1
        return self.offered

    def execute(self, request):
        self.requests.append(request)
        return self.result


def test_wrapper_delegates_identity_without_content_semantics_or_retention():
    delegate = Delegate()
    wrapper = bridge._ObsidianNoteAdapter(delegate)
    query = {"target_locator": "notes/photo.md"}
    assert wrapper.manifest() is delegate.offered
    assert delegate.manifest_calls == 1
    assert wrapper.execute(query) is delegate.result
    assert delegate.requests == [query] and delegate.requests[0] is query
    assert query == {"target_locator": "notes/photo.md"}
    assert vars(wrapper) == {"_delegate": delegate}
    assert repr(wrapper) == "_ObsidianNoteAdapter()"
    assert "PRIVATE" not in repr(wrapper)


class StringSubclass(str):
    pass


@pytest.mark.parametrize("locator", [
    ".obsidian/config.md", ".hidden/note.md", "folder/.private.md",
    "note.MD", "image.png", "board.canvas", None, 1, b"note.md", StringSubclass("note.md"),
])
def test_admission_rejects_before_delegate_with_fixed_private_error(locator):
    delegate = Delegate()
    wrapper = bridge._ObsidianNoteAdapter(delegate)
    with pytest.raises(bridge._ObsidianAdmissionError) as caught:
        wrapper.execute({"target_locator": locator})
    assert str(caught.value) == "Obsidian note admission rejected."
    assert delegate.requests == []
    if type(locator) is str:
        assert locator not in str(caught.value)


@pytest.mark.parametrize("locator", ["/note.md", "a\\note.md", "a:note.md", "a%20b.md", "~note.md", "$note.md", "folder//note.md"])
def test_wrapper_leaves_other_path_checks_to_delegate(locator):
    delegate = Delegate()
    query = {"target_locator": locator}
    assert bridge._ObsidianNoteAdapter(delegate).execute(query) is delegate.result
    assert delegate.requests[0] is query


def test_delegate_exception_is_not_rewritten_or_retried():
    delegate = Delegate()
    failure = RuntimeError("synthetic delegate failure")
    calls = []

    def execute(request):
        calls.append(request)
        raise failure

    delegate.execute = execute
    with pytest.raises(RuntimeError) as caught:
        bridge._ObsidianNoteAdapter(delegate).execute({"target_locator": "note.md"})
    assert caught.value is failure and len(calls) == 1


def test_public_entry_always_uses_fixed_composer_once(monkeypatch):
    calls = []
    config, clock, factory, outcome = object(), object(), object(), object()

    def resolved(received, **kwargs):
        calls.append((received, kwargs))
        return outcome

    monkeypatch.setattr(bridge, "resolve_local", resolved)
    assert bridge.resolve_obsidian(config, clock=clock, observation_id_factory=factory) is outcome
    assert calls == [(config, {"clock": clock, "observation_id_factory": factory,
                              "adapter_composer": bridge._compose_obsidian_adapter})]
    delegate = Delegate()
    assert bridge._compose_obsidian_adapter(delegate)._delegate is delegate
    assert bridge.__all__ == ["resolve_obsidian"]
    assert list(inspect.signature(bridge.resolve_obsidian).parameters) == ["config", "clock", "observation_id_factory"]
    assert "SourceAdapterComposer" in host.__all__
    with pytest.raises(TypeError):
        bridge.resolve_obsidian(config, adapter_composer=lambda value: value)


def test_minimal_real_host_chain_preserves_content_and_authority_bytes(tmp_path, monkeypatch):
    case = cases.make_case(tmp_path, raw=CONTENT)
    trace = cases.instrument(monkeypatch)
    executions = []
    original = LocalFilesystemSourceAdapter.execute

    def execute(adapter, request):
        executions.append(request)
        return original(adapter, request)

    monkeypatch.setattr(LocalFilesystemSourceAdapter, "execute", execute)
    before = cases.snapshot(case["directory"])
    result = bridge.resolve_obsidian(case["config"])
    assert result.kind is RuntimeResultKind.SUCCESS
    assert len(executions) == 1 and trace["reads"] == [CONTENT]
    assert result.response["payload"][0]["text"] == CONTENT.decode()
    assert len(trace["contexts"]) == len(trace["outcomes"]) == 1
    wrapper = trace["contexts"][0].adapter
    assert type(wrapper) is bridge._ObsidianNoteAdapter
    assert type(wrapper._delegate) is LocalFilesystemSourceAdapter
    assert len(trace["loads"]) == 4
    for i, (name, attr) in enumerate((("reference", "reference_bytes"), ("profile", "client_profile_bytes"), ("binding", "runtime_binding_bytes"))):
        assert getattr(trace["contexts"][0], attr) is trace["loads"][i][1]
        assert getattr(trace["contexts"][0], attr) == case["blobs"][name]
    assert [r.decision for r in trace["authority"]] == [Decision.PASS] * 2
    assert trace["source"][0][1].status == "exchange_valid"
    assert trace["source"][0][0] is trace["reads"][0]
    assert trace["resolve"][0][1] is result.validation
    assert result.validation.status == "resolve_exchange_valid"
    assert cases.snapshot(case["directory"]) == before
    cases.assert_private(repr(result) + repr(wrapper), case)


def test_real_hidden_note_rejected_only_by_obsidian_route(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "ENTRY", ".obsidian/private.md")
    case = cases.make_case(tmp_path, raw=cases.BODY_PRIVATE.encode())
    assert case["target"].is_file()
    trace = cases.instrument(monkeypatch)
    original = LocalFilesystemSourceAdapter.execute
    executions = []

    def execute(adapter, request):
        executions.append(request)
        return original(adapter, request)

    monkeypatch.setattr(LocalFilesystemSourceAdapter, "execute", execute)
    result = bridge.resolve_obsidian(case["config"])
    assert result.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE
    assert result.local_failure.category is RuntimeFailureCategory.SOURCE_FAILURE
    assert result.local_failure.message == "Source operation could not be completed."
    assert result.response is None and result.validation is None
    assert executions == [] and trace["reads"] == []
    assert not trace["source"] and not trace["resolve"]
    cases.assert_private(repr(result) + str(result.local_failure.to_dict()), case)
    assert cases.ENTRY not in repr(result)
    # 普通 P4 对同一已授权隐藏笔记仍成功；根元数据访问没有被禁止。
    plain = host.resolve_local(case["config"])
    assert plain.kind is RuntimeResultKind.SUCCESS
    assert plain.response["payload"][0]["text"] == cases.BODY_PRIVATE
    assert len(executions) == 1
