"""P4B 合成文件树安全测试；用同步注入制造竞态，不使用 sleep。"""

import errno
import json
import os
import socket
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from xingshu_core import local_filesystem_adapter as localfs
from xingshu_core.decisions import Decision
from xingshu_core.source_adapter_validation import validate_source_adapter_object

sys.path.insert(0, str(Path(__file__).parents[1] / "support"))
from local_filesystem_fixtures import SENTINEL, check_error, check_exchange, make_adapter, request


@pytest.mark.parametrize("locator", [
    "", "/synthetic/note.md", "../note.md", "x/../note.md", "./note.md", "x/./note.md",
    "x//note.md", "x/note.md/", "x\\note.md", "note\0.md", "https://synthetic/note.md",
    "file:note.md", "C:note.md", "C:/note.md", "~/note.md", "$ROOT/note.md",
    "${ROOT}/note.md", "%2e%2e/note.md", "x%2fnote.md",
])
def test_invalid_locator_is_not_normalized_or_read(tmp_path, monkeypatch, locator):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "open", lambda *_args, **_kwargs: pytest.fail("No source open expected"))
    execution = adapter.execute(request(locator))
    assert execution.response["error_code"] == "invalid_locator"
    assert execution.exact_content_bytes is None
    assert "payload" not in execution.response
    assert validate_source_adapter_object(execution.response, "source_adapter_error").decision is Decision.PASS
    # 空串、NUL 等请求自身也可能违反冻结 Schema；不伪造 exchange PASS。


@pytest.mark.parametrize("locator", ["note.txt", "note.MD", "note", "image.png"])
def test_only_explicit_lowercase_markdown_is_accepted(tmp_path, monkeypatch, locator):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("No body expected"))
    query = request(locator)
    check_error(adapter, query, adapter.execute(query), "unsupported_content_type")


@pytest.mark.parametrize("where", ["final", "intermediate"])
def test_symlinks_never_followed(tmp_path, monkeypatch, where):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "note.md").write_bytes(SENTINEL.encode())
    if where == "final":
        (root / "note.md").symlink_to(outside / "note.md")
        locator = "note.md"
    else:
        (root / "link").symlink_to(outside, target_is_directory=True)
        locator = "link/note.md"
    adapter = make_adapter(root)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Symlink body must not be read"))
    query = request(locator)
    check_error(adapter, query, adapter.execute(query), "containment_failed")


@pytest.mark.parametrize("where", ["root", "ancestor"])
def test_constructor_refuses_symlink_root_components(tmp_path, where):
    real, alias = tmp_path / "real", tmp_path / "alias"
    real.mkdir()
    (real / "child").mkdir()
    alias.symlink_to(real, target_is_directory=True)
    physical_alias = tmp_path.resolve() / "alias"
    configured = physical_alias if where == "root" else physical_alias / "child"
    with pytest.raises(localfs._AdapterExecutionError):
        make_adapter(real, root=configured)


@pytest.mark.parametrize("kind", ["directory", "fifo", "socket"])
def test_special_entry_is_rejected_before_final_open(tmp_path, monkeypatch, kind):
    target = tmp_path / "note.md"
    sock = None
    if kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO creation unavailable")
        os.mkfifo(target)
    else:
        # 合成 socket 使用短相对路径，避免 macOS 的 socket 路径长度限制。
        # monkeypatch 在本例结束时恢复 cwd；适配器仍接收显式绝对 root。
        monkeypatch.chdir(tmp_path)
        sock = socket.socket(socket.AF_UNIX)
        sock.bind("note.md")
    try:
        adapter = make_adapter(tmp_path)
        real_open = os.open

        def guard_open(name, *args, **kwargs):
            assert name != "note.md", "Special file must be rejected before opening"
            return real_open(name, *args, **kwargs)

        monkeypatch.setattr(os, "open", guard_open)
        query = request()
        check_error(adapter, query, adapter.execute(query), "unsupported_content_type")
    finally:
        if sock is not None:
            sock.close()


def test_hardlink_rejected_before_body_read(tmp_path, monkeypatch):
    (tmp_path / "note.md").write_bytes(b"synthetic")
    os.link(tmp_path / "note.md", tmp_path / "alias.md")
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Hardlink body must not be read"))
    query = request()
    check_error(adapter, query, adapter.execute(query), "containment_failed")


def test_replaced_root_identity_rejected_before_body_read(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    adapter = make_adapter(root)
    root.rename(tmp_path / "old-root")
    root.mkdir()
    (root / "note.md").write_bytes(SENTINEL.encode())
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Replaced root must not be read"))
    query = request()
    check_error(adapter, query, adapter.execute(query), "containment_failed")


def replaced_stat(info, **changes):
    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
    fields.update(changes)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize("where", ["intermediate", "final"])
def test_cross_device_is_rejected_deterministically(tmp_path, monkeypatch, where):
    (tmp_path / "nested").mkdir()
    target = tmp_path / "nested" / "note.md"
    target.write_bytes(b"synthetic")
    adapter = make_adapter(tmp_path)
    selected = (tmp_path / "nested" if where == "intermediate" else target).stat().st_ino
    real_fstat = os.fstat

    def fstat(fd):
        info = real_fstat(fd)
        if info.st_ino == selected:
            return replaced_stat(info, st_dev=info.st_dev + 1)
        return info

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Cross-device body must not be read"))
    query = request("nested/note.md")
    check_error(adapter, query, adapter.execute(query), "containment_failed")


@pytest.mark.parametrize("change,code", [
    ("grow_over_limit", "limit_exceeded"), ("grow_under_limit", "source_unavailable"),
    ("rewrite", "source_unavailable"), ("truncate", "source_unavailable"),
    ("replace_entry", "source_unavailable"), ("replace_root", "containment_failed"),
])
def test_during_read_changes_abort_without_retry(tmp_path, monkeypatch, change, code):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "note.md"
    target.write_bytes(b"original")
    adapter = make_adapter(root, hard_max_bytes=16)
    real_read, real_open = os.read, os.open
    calls, chunks, read_fds, final_opens = [], [], [], []

    def open_fd(name, *args, **kwargs):
        fd = real_open(name, *args, **kwargs)
        if name == "note.md":
            final_opens.append(fd)
        return fd

    def read(fd, count):
        read_fds.append(fd)
        calls.append(count)
        chunk = real_read(fd, count)
        chunks.append(chunk)
        if len(calls) == 1:
            if change.startswith("grow"):
                with target.open("ab") as output:
                    output.write(b"x" * (30 if change == "grow_over_limit" else 1))
            elif change == "rewrite":
                stamp = target.stat()
                target.write_bytes(b"modified")
                os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1000000))
            elif change == "truncate":
                target.write_bytes(b"x")
            elif change == "replace_entry":
                target.rename(root / "old.md")
                target.write_bytes(SENTINEL.encode())
            else:
                root.rename(tmp_path / "old-root")
                root.mkdir()
                (root / "note.md").write_bytes(SENTINEL.encode())
        return chunk

    monkeypatch.setattr(os, "open", open_fd)
    monkeypatch.setattr(os, "read", read)
    query = request(limit=16)
    execution = adapter.execute(query)
    check_error(adapter, query, execution, code)
    assert sum(map(len, chunks)) <= 17
    assert SENTINEL.encode() not in b"".join(chunks)
    assert len(final_opens) == 1
    assert set(read_fds) == set(final_opens)  # 全程同一描述符，不重新打开重试。
    assert SENTINEL not in json.dumps(execution.response)


def test_replace_between_lstat_and_open_is_detected(tmp_path, monkeypatch):
    target = tmp_path / "note.md"
    target.write_bytes(b"original")
    adapter = make_adapter(tmp_path)
    real_open = os.open

    def open_replacement(name, *args, **kwargs):
        if name == "note.md":
            target.rename(tmp_path / "old.md")
            target.write_bytes(SENTINEL.encode())
        return real_open(name, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_replacement)
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("Replaced inode must not be read"))
    query = request()
    check_error(adapter, query, adapter.execute(query), "source_unavailable")


def track_descriptors(monkeypatch):
    real_open, real_close = os.open, os.close
    live, opened, closed = set(), [], []

    def open_fd(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        assert fd not in live
        live.add(fd)
        opened.append(fd)
        return fd

    def close_fd(fd):
        assert fd in live
        real_close(fd)
        live.remove(fd)
        closed.append(fd)

    monkeypatch.setattr(os, "open", open_fd)
    monkeypatch.setattr(os, "close", close_fd)
    return live, opened, closed


@pytest.mark.parametrize("failure", [
    "none", "open", "intermediate", "read_os", "read_private", "fstat", "utf8", "clock", "factory",
])
def test_all_descriptors_closed_on_success_error_and_exception(tmp_path, monkeypatch, failure):
    (tmp_path / "nested").mkdir()
    target = tmp_path / "nested" / "note.md"
    target.write_bytes(b"\xff" if failure == "utf8" else b"synthetic")
    live, opened, closed = track_descriptors(monkeypatch)
    adapter = make_adapter(tmp_path)
    assert opened and not live and len(opened) == len(closed)
    tracking_open, real_read, real_fstat = os.open, os.read, os.fstat

    def injected_open(name, *args, **kwargs):
        if (failure == "open" and name == "note.md") or (failure == "intermediate" and name == "nested"):
            raise OSError(errno.EACCES, SENTINEL, str(target))
        return tracking_open(name, *args, **kwargs)

    def injected_read(fd, count):
        if failure == "read_os":
            raise OSError(errno.EIO, SENTINEL, str(target))
        if failure == "read_private":
            raise RuntimeError(SENTINEL)
        return real_read(fd, count)

    def injected_fstat(fd):
        info = real_fstat(fd)
        if failure == "fstat" and stat.S_ISREG(info.st_mode):
            raise OSError(errno.EIO, SENTINEL, str(target))
        return info

    def unavailable():
        assert not live  # 返回文件读取阶段之后，时钟及工厂不能留下 fd。
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(os, "open", injected_open)
    monkeypatch.setattr(os, "read", injected_read)
    monkeypatch.setattr(os, "fstat", injected_fstat)
    if failure == "clock":
        monkeypatch.setattr(adapter, "_clock", unavailable)
    if failure == "factory":
        monkeypatch.setattr(adapter, "_id_factory", unavailable)
    query = request("nested/note.md")
    if failure in ("read_private", "clock"):
        with pytest.raises(localfs._AdapterExecutionError) as caught:
            adapter.execute(query)
        assert caught.value.__context__ is None
        assert SENTINEL not in str(caught.value)
        assert str(tmp_path) not in str(caught.value)
    else:
        execution = adapter.execute(query)
        check_exchange(adapter, query, execution)
        if failure != "none":
            code = {"utf8": "unsupported_encoding", "factory": "provenance_unavailable"}.get(
                failure, "source_unavailable")
            check_error(adapter, query, execution, code)
            assert SENTINEL not in json.dumps(execution.response)
            assert str(tmp_path) not in json.dumps(execution.response)
    assert not live and len(opened) == len(closed)


def test_failed_construction_closes_opened_ancestors(tmp_path, monkeypatch):
    live, opened, closed = track_descriptors(monkeypatch)
    with pytest.raises(localfs._AdapterExecutionError):
        make_adapter(tmp_path, root=tmp_path.resolve() / "missing")
    assert opened and not live and len(opened) == len(closed)


@pytest.mark.parametrize("phase", ["construct", "execute"])
def test_missing_security_primitive_fails_closed(tmp_path, monkeypatch, phase):
    adapter = make_adapter(tmp_path) if phase == "execute" else None
    monkeypatch.delattr(os, "O_NOFOLLOW")
    monkeypatch.setattr(os, "read", lambda *_: pytest.fail("No fallback read allowed"))
    with pytest.raises(localfs._AdapterExecutionError):
        if phase == "construct":
            make_adapter(tmp_path)
        else:
            adapter.execute(request())
