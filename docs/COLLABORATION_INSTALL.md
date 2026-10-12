# 星枢主动协作 v0.1.0 安装

本组件提取通用连接与项目接续实现。安装代码与获得客户端工具是两件事。支持的在线路线由已登录、具备官方聊天读取/发送工具的本地智能端主持；普通 Web GPT 的本地工具权限不会随 GitHub 下载而出现。

## 状态与适用范围

本版采用的使用范围是前台主动协作：由具备官方聊天工具的 Codex 主持送审，Web GPT 在现有对话独立复核，Codex 从原入口读取结果。源码、公私边界、wheel 与源码包安装已经过独立复核，安装版完成过一次真实闭环。详见 [协作范围](COLLABORATION_SCOPE.md)。

自动换窗、普通 Web 直接调用 Codex、私人正式路由切换和另一台实体机器实测仍未完成。换窗库可供开发，但不能当成已完成的自动产品。公开组件采用不改变 Core 治理或任何既有私人配置。

支持 Python 3.11+ 的 macOS/Linux。Windows 的文件锁和前台桥接尚未实现。使用独立虚拟环境，避免替换已有 XINGSHU Core 安装。本组件没有后台服务、公开监听、API Key、自动导入私人记录或隐式触发。

## 从 GitHub 安装

建议固定协作组件发布标签 `collaboration-v0.1.0` 安装；未发布的分支只用于开发。Python 命令可以换成机器上实际安装的 Python 3.11 及以上版本。

```sh
git clone --branch collaboration-v0.1.0 --depth 1 https://github.com/Johnny-us/XINGSHU-Core.git
cd XINGSHU-Core
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/xingshu-collab --version
.venv/bin/xingshu-collab doctor
```

最后一个命令会报告未绑定/缺宿主工具并返回退出码 2。这是首次安装的正常状态。完成下面的技能安装、本机绑定和真实 Doctor 后，才在该机器上使用。发行包名为 `xingshu-core`（Core 版本 `0.4.0.dev0`），本组件命令 `xingshu-collab --version` 返回 `0.1.0`；这两个版本分别描述仓库包和协作组件。Core 原有 `xingshu` 命令、治理与来源注册逻辑继续独立。

## 安装明确调用的技能

```sh
.venv/bin/xingshu-collab install-skill --destination "$PWD/.agents/skills/xingshu-collaborate"
```

在此仓库的 Codex 聊天明确调用 `$xingshu-collaborate`。需要用户级发现时，可自行指定用户 `.agents/skills/xingshu-collaborate`；已有同名目录会拒绝覆盖。技能不会自行取得官方连接器；缺少聊天工具时停止。

## 主动调用的提示词

完成本机绑定和真实 Doctor 检查后，可以在当前 Codex 聊天使用本发布包附带的入口：

```text
使用 $xingshu-collaborate。
接续我已授权的当前项目任务，承接上下文和已完成进度。
核对本机工具、两端绑定与恢复点，执行前台送审并从原入口读回结果。
默认不自动跳转；工具不足时保留恢复点并说明缺口。
```

当前客户端具备必要官方工具、完成本机绑定并取得当前任务授权后，这段提示词用于主动请求已验收范围内的前台协作。条件不足时停止，不保证自动完成。提示词不会补出普通 Web 建窗或普通 Web 直接调用 Codex 的工具权限，也不表示自动换窗已经完成。

如果当前机器**另外安装了** `$xingshu-switch-chat`，可使用它自己的换窗接续入口。独立技能的 GitHub 与 ZIP 安装见 [换窗接续技能安装](SWITCH_CHAT_SKILL_INSTALL.md)：

```text
使用 $xingshu-switch-chat。
把当前任务接续到 Codex 与普通 Web 的对应聊天窗口。
先保存恢复点，承接上下文和已完成进度，核验两端实际读取、链路与结果返回。
默认不自动跳转；缺少必要工具时保留原窗口与恢复点，并说明未完成项。
```

`$xingshu-switch-chat` 不是 `collaboration-v0.1.0` 附带的技能，而是另行发布、无需安装 Core 的独立技能包。另一台机器只安装本主动协作发布包，得到的是 `$xingshu-collaborate`；不能直接照抄前一台机器的技能文件绝对路径。换窗接续是否完成，须按该机器实际可用工具和真实证据判断。

“主动调用”是用户现在发起任务；“默认不自动跳转”是接续过程中界面仍留在原窗口。创建聊天、承接上下文和显示目标页面是不同步骤。需要显示目标页面时，再明确说“接续核验完成后，打开对应窗口”；未完成的接续不能因页面打开而视为成功。询问提示词的用法、引用示例或编辑说明，不是执行换窗的请求。

## 本机首次绑定

每台机器独立操作。先登录受支持的客户端，用实际 `list_projects`、`list_threads`、`read_thread` 核对用户所选两端。不要复制他人的配置、线程编号或凭据。应用主机编号也应实查。

```sh
.venv/bin/xingshu-collab init --directory "$PWD/local-collaboration"
.venv/bin/xingshu-collab bind --directory "$PWD/local-collaboration" \
  --project-id MY_PROJECT \
  --codex-uri 'codex://threads/<actual-codex-uuid>' \
  --web-uri 'https://chatgpt.com/c/<actual-web-uuid>' \
  --owner-ref '<current-human-authorization-reference>'
```

尖括号是必须替换的输入，不能直接运行示例。绑定只创建本组件的独立配置，不覆盖既有星枢正式端点。不可覆盖旧绑定；换窗应完成带代次与未确认消息检查的接续流程。

智能端将本回合实际工具名保存为 inventory JSON：

```json
{"tools":["read_thread","send_message_to_thread","list_projects","list_threads"]}
```

```sh
.venv/bin/xingshu-collab doctor --directory "$PWD/local-collaboration" --inventory "$PWD/inventory.json" --stdio-host
```

这一步必须由已授权智能端把前台程序请求桥接到真正的官方工具。仅填写工具名称没有连接验证作用。原始工具结果、正确两端身份和无系统错误是实际检查依据；本地 JSON 不是授权或官方签名。

正在执行的源窗口可以被检查。Doctor 只核对实际对话身份和执行状态，以较小的单项上限读取、不请求工具输出；不作为正文实读或投递证明。它分别报告两端的 `read_verified` 和 `ready_for_submission`，不能将源窗口可读当成目标可接收新消息。发送时会再次完整检查目标输入；忙碌的目标仍被拒绝。标准输入桥对整份宿主返回保留 1 MiB 上限，超限仍停止，不删改结果来绕过上限。

## 发送与证据

正文文件须为 UTF-8，最大 16384 字节。消息编号在同一登记内必须唯一，正文写明任务、版本、目的与停止条件。

官方聊天接口曾实际去掉末尾换行。此适配器在任何工具调用和日志创建之前拒绝开头/末尾空白及空正文，不会自动删改。写入文件时使用 `Path(...).write_bytes(text.encode('utf-8'))` 保存用户确认的正文；正文中间的换行继续原样保留。其他宿主是否支持边界空白需分别实测，通用投递核心不作此改写。

```sh
.venv/bin/xingshu-collab send --directory "$PWD/local-collaboration" \
  --task-id TASK_001 --message-id MESSAGE_001 --source CODEX_DESKTOP \
  --payload-file "$PWD/request.txt" --stdio-host
.venv/bin/xingshu-collab status --directory "$PWD/local-collaboration"
```

标准输入桥见随包 `SKILL.md`。桥只允许所登记目标的两个官方方法，不发明新工具或持有凭据。CLI 不会自己登录 ChatGPT、读取浏览器 Cookie 或直接调用私有聊天接口。

`HOST_OBSERVED_INPUT` 表示精确观察到新增原文，不表示模型接受任务或独立审查通过。模型实读与阶段审查采用连接/路由契约的 ConsumptionObservation 和 ReviewObservation；须从实际模型回合提取原始编号、精确版本、资料摘要和证据。离线传入对象只是在验证协议结构，不能成为真实宿主证据。

UNKNOWN/UNCERTAIN、身份冲突、截断、忙碌或系统错误都停止当前流程。先核对已有原生输入与日志，再决定恢复；禁止自动重试或另造编号绕过不确定状态。

## 换窗接续接口

公共模块 `xingshu_collaboration.router` 包含项目目录、当前聊天证明、宿主生命周期、ContinuityManager、OnlineContinuity 与 TaskCoordinator。宿主回调由当前已授权客户端注入，没有内置私人端点或账号。

完整流程见 [PROJECT_CONVERSATION_CONTINUITY.md](PROJECT_CONVERSATION_CONTINUITY.md)。必须先保存交接包、观察旧链路未解决消息、核验两端新聊天的实际身份、取得两端同版本模型实读与双向投递证据，然后提交路由并恢复业务。CLI 的 `checkpoint` 只保存已校验的 HandoffPacket，不创建聊天或宣称接续完成。客户端不支持 Web 建窗时必须保留缺口。

## 禁用与卸载

```sh
.venv/bin/xingshu-collab uninstall-skill \
  --destination "$PWD/.agents/skills/xingshu-collaborate" \
  --archive-directory "$PWD/disabled-skills/xingshu-collaborate"
```

归档目录应位于技能发现路径之外。保留本机配置和日志作为恢复证据；程序没有后台服务需要卸载。独立虚拟环境可用 pip 卸载 xingshu-core，或在确认不需要其中其他包后移除整个环境。卸载不删除聊天、原正式登记或其他项目资料。

## 可验证性

运行 `python -m pytest tests/collaboration --import-mode=importlib` 与 `node --test tests/collaboration/test_continuation_driver.cjs`。这些使用合成数据验证契约，不是账户或跨机器真实协作验收。

技能发现位置与明确调用策略参考 [官方技能文档](https://learn.chatgpt.com/docs/build-skills)；不同客户端的连接器范围参考 [官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。
