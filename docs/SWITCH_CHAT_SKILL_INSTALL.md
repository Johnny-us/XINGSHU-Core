# 星枢换窗接续技能：独立安装

`xingshu-switch-chat` 是单独发布的 Codex 技能，无须先安装星枢 Core、Python 包或主动协作组件。它提供用户明确调用时的接续流程：保存进度、检查工具、准备同主题对应聊天、核验上下文和结果返回，默认留在原窗口。

本版为 `0.2.0` 实验流程预发布。修正维护/状态问题误建聊天、默认采用 Chrome 电脑操作、区分安全停止与无关通道故障，并补充进度、停止点及返回校验。打包、隔离安装和23个合成状态案例可验证；公开包在独立实体机器的完整双端验收与长期稳定性尚未证明。安装不会提供账号、聊天连接器或普通 Web 对 Codex 的工具权限。缺少必要宿主工具时停止，保留原聊天和恢复点。

## 方式一：让 Codex 从 GitHub 安装

在自己的 Codex 中发送：

```text
使用 $skill-installer 安装这个 GitHub 技能：
仓库：Johnny-us/XINGSHU-Core
版本：switch-chat-skill-v0.2.0
路径：skills/xingshu-switch-chat
安装到当前项目的 .agents/skills，只安装这个技能。
已有同名技能时停止，不覆盖；这次只安装，不执行换窗。
```

该入口使用客户端自带的技能安装器，只复制所选技能，不安装整个 Core。若客户端没有 `$skill-installer`，使用下面的 ZIP 方式。需要所有项目可见时，明确指定用户级 `.agents/skills`；先核对其他发现目录是否已存在同名技能，避免两个版本同时出现。

## 方式二：下载独立 ZIP

从 [技能发布页](https://github.com/Johnny-us/XINGSHU-Core/releases/tag/switch-chat-skill-v0.2.0) 下载：

- `xingshu-switch-chat-0.2.0.zip`：技能本体。
- `switch-chat-skill-build-info.json`：源码提交与逐文件摘要。
- `SHA256SUMS.txt`：前两个附件的校验值。

可使用本机校验工具核对 SHA-256；macOS/Linux 在这三个文件所在目录运行 `shasum -a 256 -c SHA256SUMS.txt`。校验不通过时不安装。

解压到新的临时目录，将其中整个 `xingshu-switch-chat` 文件夹移到当前项目的 `.agents/skills/`。目标应为 `.agents/skills/xingshu-switch-chat/SKILL.md`；已有同名文件夹或链接时先停止，不合并覆盖。`agents/openai.yaml` 是原生元数据；`agents/interface.yaml` 是评测兼容投影，不能覆盖原生显式调用策略。技能包包含以下文件；辅助校验器仅离线读取记录，不参与聊天操作：

```text
xingshu-switch-chat/
  SKILL.md
  agents/openai.yaml
  agents/interface.yaml
  LICENSE.txt
  manifest.json
  references/browser-channels.md
  references/handoff-contract.md
  references/evaluation.md
  scripts/validate_run.py
  evals/semantic-config.json
  evals/trigger-cases.json
  evals/run-cases.json
  reports/output_quality_scorecard.md
```

安装后，在下一轮核对客户端是否发现 `$xingshu-switch-chat`；未出现时重启客户端再检查。安装目录存在与技能实际被发现是不同证据。ZIP 安装和普通使用不需要运行 Python 或 shell 脚本；可选离线校验使用已有 Python，仅依赖标准库，不调用工具或网络。技能运行依赖当前客户端实际可用工具，不能仅凭操作系统名称保证支持。

发现位置与技能安装器参考 [官方技能文档](https://learn.chatgpt.com/docs/build-skills)。本包是 GitHub 独立技能分发，不代表已进入官方插件市场，也不会在普通 Web GPT 安装同名技能。

## 调用提示词

```text
使用 $xingshu-switch-chat。
把当前已授权任务接续到 Codex 与普通 Web 的新对应聊天。
先保存恢复点，承接上下文和已完成进度，核验两端实际读取、链路与结果返回。
默认不自动跳转；缺少必要工具时保留原窗口与恢复点，并说明未完成项。
```

只需要 Codex 一端时，明确写“只换 Codex”。需要显示新页面时，再明确写“接续核验完成后，打开对应窗口”。用法讨论、引用示例、询问检测状态、检查/审查/修改技能及安装本身不执行换窗。仅提到或选择技能也不等于授权创建。Web 默认通过 Chrome 原生电脑操作；扩展和内置浏览器各自核验，任一路线成功不证明另一条恢复。

首次调用从可信宿主核对当前聊天及所选对应 Web，不内置任何人的聊天编号。已有项目恢复记录优先；普通工作区没有星枢私人文件时，使用本工作区的 `.xingshu-chat-continuity/` 保存任务接续记录。记录含运行身份和进度，应留在本机，不上传到公共仓库。

## 禁用、卸载与更新

将安装的 `xingshu-switch-chat` 文件夹移到所有技能发现目录之外，保留备份；下一轮检查它不再被发现，必要时重启客户端。无需停后台服务，因为本包没有后台程序。移走技能不删除聊天、接续记录或已有项目绑定。

更新时先核对旧版本及进行中的接续记录，把旧技能归档到发现目录之外，再安装固定新版本。不要用更新清除 UNKNOWN 或重复创建聊天。已有私人同名技能的用户应先比较规则，选择一个版本；独立公开版不覆盖本机既有技能。

## 来源、范围与维护

公开版由获授权的接续流程抽象改写，经过 AI 辅助工程整理；不发布原私人技能文件、偏好记录、项目路径、端点、旧任务或审计正文。采用仓库 Apache-2.0 许可证，技能包内随附完整许可证。

`xingshu-collaborate` 主持已验收的前台送审与读回；`xingshu-switch-chat` 组织用户主动请求的换窗接续。两个技能分别安装，没有强制依赖，也不互相代替。

维护者使用 `python scripts/build_switch_chat_skill.py <输出目录>` 打包固定提交，使用 `python scripts/check_switch_chat_skill.py` 核对确定性归档、隔离安装与移出发现目录。构建器只用 Python 标准库；仓库检查工具还需要 `requirements-test.txt` 声明的 PyYAML。它与包内仅用标准库的可选 `scripts/validate_run.py` 是不同工具。上述打包检查不代表真实双端换窗验收。
