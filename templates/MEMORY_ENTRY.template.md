---
schema_version: "0.3"
record_type: memory_entry
memory_id: memory-example
topic_ref: topic-example
conclusion_state: candidate
evidence_state: unknown
current_loading_allowed: false
governance_effect: none
activation_state: not_active
---

# Memory Entry（记忆条目）

> Memory Candidate（记忆候选）不是正式记忆。只有完成来源核实、去重 / 冲突审查和晋升审查后，才可能成为当前有效结论。

## 候选结论

- 候选内容：
- 为什么跨任务仍有价值：
- 适用范围：
- 不适用范围：

## 来源核实

- 来源引用：
- 核实状态：`unknown`
- 最后核实时间：
- 环境类别：
- 核实方法引用：

## 去重与冲突

- 重复条目：无 / 填写引用
- 冲突条目：无 / 填写引用
- 处理状态：`needs_review`
- 处理原因：

## 晋升审查

- 审查状态：`pending`
- 审查类型：
- 审查时间：
- 原因代码：

## 证据状态

- 证据类别：
- 证据引用：
- Evidence State（证据状态）：`unknown`

证据状态与 Conclusion State（结论状态）必须分开。推断应标记为 `reasoned_inference`，未经必要审查不得晋升为 `active`。

## 生命周期与复审

- 替代：无 / 填写引用
- 被替代：无 / 填写引用
- 复审触发条件：

## 不应保存

不要保存聊天正文、临时报错、短期待办、未经核实的猜测、Secret、认证材料、私人载荷或不必要的绝对路径。
