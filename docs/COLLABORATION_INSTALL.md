# 星枢在线对话协作安装

本组件提取通用连接与项目接续实现。安装代码与获得客户端工具是两件事。支持的在线路线由已登录、具备官方聊天读取/发送工具的本地智能端主持；普通 Web GPT 的本地工具权限不会随 GitHub 下载而出现。

## 状态与适用范围

当前为待独立验收的公共实现候选。未声明正式私人配置采用、另一台实体机器实测或普通 Web 单入口直接调度完成。任何后续通过记录必须绑定精确提交/源码摘要与实际证据，不能根据测试数改写此状态。

支持 Python 3.11+ 的 macOS/Linux。Windows 的文件锁和前台桥接尚未实现。使用独立虚拟环境，避免替换已有 XINGSHU Core 安装。本组件没有后台服务、公开监听、API Key、自动导入私人记录或隐式触发。

## 从 GitHub 安装

完成审查并进入 main 后，才使用 main 安装。测试候选时改用经核验的精确提交；不要把未合并分支当正式发布。

```sh
git clone https://github.com/Johnny-us/XINGSHU-Core.git
cd XINGSHU-Core
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/xingshu-collab --version
.venv/bin/xingshu-collab doctor
```

最后一个命令会报告未绑定/缺宿主工具并返回退出码 2。这是首次安装的正常状态，不能称为协作已经可用。Core 原有 `xingshu` 命令、治理与来源注册逻辑继续独立。

## 安装明确调用的技能

```sh
.venv/bin/xingshu-collab install-skill --destination "$PWD/.agents/skills/xingshu-collaborate"
```

在此仓库的 Codex 聊天明确调用 `$xingshu-collaborate`。需要用户级发现时，可自行指定用户 `.agents/skills/xingshu-collaborate`；已有同名目录会拒绝覆盖。技能不会自行取得官方连接器；缺少聊天工具时停止。

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

## 发送与证据

正文文件须为 UTF-8，最大 16384 字节。消息编号在同一登记内必须唯一，正文写明任务、版本、目的与停止条件。

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
