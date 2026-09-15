"""P4E 独立候选命令行：显式本地输入、单次解析、固定脱敏错误。

通过 python -m xingshu_core.runtime_cli 运行；不注册现有 xingshu 入口。
成功正文属于明确交付边界；失败不打印验证诊断、路径或异常详情。
"""

from __future__ import annotations

import argparse
import json
import sys

from .runtime_contracts import RuntimeExecutionResult, RuntimeResultKind
from .runtime_host import HostInputError, LocalRuntimeHostConfig, resolve_local


class _InvocationError(Exception):
    pass


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _InvocationError()


def _parser() -> argparse.ArgumentParser:
    parser = _SafeParser(prog="python -m xingshu_core.runtime_cli", allow_abbrev=False,
                         description="候选本地只读解析；所有输入由所有者显式提供。")
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve-local", allow_abbrev=False,
                                  help="单次读取已授权的本地 Markdown")
    for flag in ("reference", "client-profile", "runtime-binding", "request"):
        resolve.add_argument("--" + flag, required=True, metavar="FILE")
    resolve.add_argument("--root", required=True, metavar="DIR", help="显式绝对物理来源目录")
    resolve.add_argument("--scope-id", required=True, metavar="ID")
    resolve.add_argument("--adapter-id", required=True, metavar="ID")
    resolve.add_argument("--max-bytes", type=int, default=1048576, metavar="N",
                         help="适配器硬上限（1 至 1048576）；不改写请求限额")
    resolve.add_argument("--json", action="store_true", help="仅输出协议或固定本地错误 JSON")
    return parser


def _host_error(json_mode: bool, *, invocation: bool = False) -> int:
    message = ("Invalid runtime host invocation." if invocation
               else "Runtime host input could not be accepted.")
    try:
        if json_mode:
            print(json.dumps({"kind": "runtime_host_error",
                              "category": "invalid_invocation" if invocation else "invalid_host_input",
                              "message": message}))
        else:
            print("RUNTIME_HOST_ERROR\nmessage: " + message, file=sys.stderr)
    except (Exception, KeyboardInterrupt):
        pass  # 输出通道本身不可用时，仅返回退出码，不回显底层错误。
    return 4


def _render(result: RuntimeExecutionResult, json_mode: bool) -> int:
    if result.kind is RuntimeResultKind.LOCAL_EXECUTION_FAILURE:
        safe = result.local_failure.to_dict()
        if json_mode:
            print(json.dumps({"kind": "local_execution_failure", **safe}))
        else:
            print("LOCAL_EXECUTION_FAILURE\ncategory: " + safe["category"]
                  + "\nmessage: " + safe["message"], file=sys.stderr)
        return 3
    if json_mode:
        print(json.dumps(dict(result.response), ensure_ascii=True, allow_nan=False))
    elif result.kind is RuntimeResultKind.SUCCESS:
        # 正文不 strip、不重排换行，不附加内部身份、路径或指纹。
        text = "\n".join(item["text"] for item in result.response["payload"])
        sys.stdout.write("SUCCESS\nstatus: resolved\n\n--- 正文 ---\n" + text)
    else:
        print("PROTOCOL_ERROR\ncode: " + result.response["error_code"])
    return 0 if result.kind is RuntimeResultKind.SUCCESS else 2


def main(argv: list[str] | None = None) -> int:
    json_mode = False
    try:
        arguments = list(sys.argv[1:] if argv is None else argv)
        json_mode = "--json" in arguments
        try:
            args = _parser().parse_args(arguments)
            if not 1 <= args.max_bytes <= 1048576:
                raise _InvocationError()
        except _InvocationError:
            return _host_error(json_mode, invocation=True)
        except SystemExit as exc:
            if exc.code == 0:  # argparse 的静态帮助，无用户值插入。
                return 0
            return _host_error(json_mode, invocation=True)
        config = LocalRuntimeHostConfig(
            reference_file=args.reference, client_profile_file=args.client_profile,
            runtime_binding_file=args.runtime_binding, request_file=args.request,
            source_root=args.root, scope_id=args.scope_id, adapter_id=args.adapter_id,
            hard_max_bytes=args.max_bytes,
        )
        return _render(resolve_local(config), args.json)
    except HostInputError:
        return _host_error(json_mode)
    except (Exception, KeyboardInterrupt):
        # 包括输出/宿主故障；不将原始异常传给终端。
        return _host_error(json_mode)


if __name__ == "__main__":
    raise SystemExit(main())
