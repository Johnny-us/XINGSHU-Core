# 交接契约与恢复步骤

本文件是本技能的 execution / output contract（执行与输出约定），继承主入口的来源与授权边界。

## 保存和创建

1. 使用项目已有的每任务运行记录；没有时采用授权工作区的 `.xingshu-chat-continuity/<safe_task_id>/<run_id>/`，由该任务的 `current.json` 明确指向当前运行。保存 `CURRENT_STATE.json`、`HANDOFF_CURRENT.md`，只更新本任务指针，不能覆盖无关任务；同任务并发修改先停止核对。最小交接包括任务与版本、源聊天、返回入口、来源范围及摘要、已完成、未完成、停止点、旧未知清单、本轮人类授权证据。
2. 外部动作前分别保存唯一 `operation_id`、目的、端、有效载荷摘要和 `INTENT`。宿主执行后分别记 `SUBMITTED`、`IDENTIFIED`、`READ_CONFIRMED`、`ACCEPTED`、`RETURN_READ`；不能由一个阶段推断后面的阶段。
3. Codex 先用 `list_projects` 核对原项目，再用 `create_thread`，默认本地环境，不创建工作树/分支。`clientThreadId` 是待就绪编号；实际 `threadId`、项目和任务回读后才成为接续页。按宿主要求返回创建指令。
4. 普通 Web 在已确认项目内点击新聊天并提交最小交接。记录实际地址中的聊天编号、项目归属与新页实读；不得把 ChatGPT Work 或同名旧聊天认领为新页。创建/提交结果未知记 `UNKNOWN`，先核对原操作；不重试、不换编号重发。已产生的新页保留为未采用页。
5. 两端按同一 `task_id/work_version` 回读已完成、下一步、原入口、停止点和对应页。第一端创建时另一端尚未产生编号，可记 `PENDING_COUNTERPART`；取得真实编号后仅发本轮对应关系补充，不重发原业务或旧复核。补充前也保存意图。

## 接受和返回

接续只接受本轮明确范围，不自动恢复旧业务执行。新聊天应说明实际读到的进度、保留的决定、下一步和停止点。独立业务复核仍另行取证。

返回可以是以下已获授权、实际可用的方式，必须写明是哪一种：

- 原生主动返回：接续端实际向源入口提交，源入口实读同一任务/版本回执。
- 在线宿主辅助返回：当前执行者通过官方 `wait_threads/read_thread` 实读新 Codex 回执，通过 Chrome 电脑操作实读新 Web 回执，保存原文/标识并在当前源聊天回传。只证明这次在线辅助闭环，不证明 Web 可自主控制 Codex、后台回调或正式专线上线。

仅有返回链接或新页自称“已返回”不足以完成。新 Codex 不因父端提示就自动获准向其他聊天发消息；需当前人类授权或既有可信授权。当前端自行读取并回传时，不需接续端代发。

## 候选运行路由

普通原生建窗不要求调用尚未接线的候选 API。只有本轮明确进入已获授权的 项目路由 候选业务采用时，才按现有 `项目已定义的验证采用/恢复接口` 规则核对并冻结待恢复业务，保留产物、返工状态和原入口。候选代码存在不等于适配器可用；不得用技能放行正式端点改绑、正式部署或来源扩权。

## 最小验收记录

`scripts/validate_run.py` 接收一个 JSON 记录，仅做离线检查。记录与正式业务状态分开：

- `task_id`、`work_version`、`source_thread_id`、`return_thread_id`、`mode`（`paired/codex_only`）；
- `expected_stops` 与两端 `stops`：明确停止点列表，必须存在且严格一致；无停止点时也要明确写空列表；
- `codex/web`：真实 `thread_id`、`project_verified`、`input_read`、`accepted`、`task_id/work_version`、`already_done/next_step`；Web `kind=ordinary_web`；
- `progress_preserved`、`same_task_version`、`return_read`、`return_mode`（`native/host_assisted`）；
- `current_unknown_operations`：本轮同一操作未知清单；`isolated_legacy_unknowns`：明确隔离旧记录，不覆盖或清除；
- `navigation_requested/navigated`、`formal_binding_changed`、`background`、`old_task_resent`。

校验器只接受严格布尔值，要求源/新页编号分离、两端编号分离、回到原入口，拒绝当前 UNKNOWN、跳转越权、Work 冒充普通 Web、形式改绑或后台。旧 UNKNOWN 是否影响本轮须先人工/智能端依据真实记录判明，校验器不替执行者作授权决定。

## 停止作用域与回滚

恢复定位顺序：先读当前任务规范记录的 `当前运行指针`，再读当前聊天最小交接中明确的 `run_path`，最后核对已知原 `operation_id` 的宿主记录；核对任务、源聊天、版本和原操作，不按日期或标题选记录。指针冲突、已知旧意图却找不到记录时停止，不另建运行。只有确认为首次运行，或已完成前序运行后的明确下一页请求，且没有旧未知创建时，才生成新 `run_id`。上一运行已完成、用户在验证过的接续聊天明确要求再次换窗时，用该聊天作新源，保留前序指针；不重复上一创建。

阶段性导航：执行者与 Web GPT 在已有授权范围内按任务阶段、上下文和实际能力协商；保存理由、双方意见、适用阶段、已验证目标和停止条件。未协商或缺实证时留在当前窗口。阶段决定仅适用该次，不改变长期默认，不放行正式改绑、来源扩权或后台。获准导航分别记录官方操作回执及实际结果。

被禁止的动作不再执行，不用替代通道绕过。坏掉的无关备选通道可以隔离；可用默认通道继续本轮允许步骤。当前 UNKNOWN 或依赖不清的旧 UNKNOWN 停止其受影响步骤，已隔离旧历史不重发、不清除。正式业务停止点仍独立保持。

rollback boundary（回滚边界）：技能文件可从修改前快照恢复；已经建立的聊天不随文件回滚自动删除，真实聊天编号、未知提交和证据保留。取消不等于永久删除。
