---
type: system-root-marker
system_id: xingshu-2.0
system_name: XINGSHU Personal Instance
instance_type: personal
status: candidate
marker_version: 0.1
primary_entry: AGENTS.md
core_adoption_state: not_configured
---

# XINGSHU Personal Instance Root（星枢私人实例根标识）

本模板用于创建独立 Personal Instance（私人实例）的 Root Identity（根身份标识）。它只声明“这里是一个待配置的 XINGSHU 私人实例”，不包含个人身份、账号、设备信息、Secret、本地绝对路径或运行状态。

## Root Marker Boundary（根标识边界）

本文件只承担实例根识别职责，不替代：

- Public Core 的公共治理；
- Personal Overlay（私人覆盖层）；
- 实例授权记录；
- 项目、环境、运行状态或 Backup（备份）记录。

发现本文件不代表 Agent 自动获得读取、写入、执行、治理修改或外部代表权限。

## Core / Personal Separation（公共核心与私人实例分离）

- Public Core 是公共规则、架构、治理、模板和使用说明的来源；
- Personal Instance 是用户私人配置、授权、项目和运行状态的来源；
- 本模板可以从 Core 显式复制到 Personal Instance，但不得与 Core 建立自动同步、目录镜像或符号链接；
- Personal Instance 中完成的配置不得回写或自动同步到 Public Core；
- Core 更新必须经过版本选择、差异检查和实例采用流程。

## Activation Conditions（激活条件）

私人实例将本文件重命名为 `XINGSHU_ROOT.md` 后，仍应保持 `candidate`，直到完成：

1. 选择并审查要采用的 Public Core 版本；
2. 建立独立的 `AGENTS.md` 入口；
3. 在私人配置层完成实例治理主体与授权关系；
4. 验证 Core、Personal Instance 与 Backup 的职责和物理边界；
5. 验证不存在 Secret、私人数据或实例状态向 Public Core 回流；
6. 由该实例按自身治理完成激活。

激活信息与私人配置只写入 Personal Instance，不修改 Public Core 中的本模板。
