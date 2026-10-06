---
type: contract-candidate
status: proposed
scope: public-candidate-documentation
implementation_status: not-implemented-in-public-core
governance_effect: none
authorization_effect: none
activation_effect: none
visibility: public
---

# Context Metadata Lookup（上下文元数据查找）边界

本文细化 [Context Memory Bridge Architecture（上下文记忆桥架构）](CONTEXT_MEMORY_BRIDGE_ARCHITECTURE.md) 与 [Context Bridge Security Model（上下文桥安全模型）](CONTEXT_BRIDGE_SECURITY_MODEL.md) 的查找层。它描述候选契约，不随附 Gateway（客户端接入层）、客户端认证、Source Adapter（来源适配器）或真实来源读取实现。

## 1. 查找与解析分工

Metadata Lookup（元数据查找）只返回获准披露的定位线索。命中、Schema（结构契约）合法、digest（摘要）一致或快照中 `status=active`，均不能产生正文读取权，也不能证明当前来源、注册链或授权仍有效。

Authorized Resolve（获授权解析）是另一条受控路径：核对当前可信客户端及运行绑定、注册与授权链、生命周期、freshness（新鲜度）、精确来源范围和 provenance（溯源），再按既有契约有界读取。Lookup 不能跳过或替代这些检查。

## 2. 来源类别与使用范围

`authority_class`（来源权威类别）说明上游明确给出的来源分类；`usage_class`（结果使用范围）限制查找结果如何使用。两者不能互换，也不能从路径、URI（来源定位符）或命中状态推断权威。

查找结果必须保持以下边界：

| 字段 | 固定含义 |
|---|---|
| `usage_class=lookup_hint_only` | 只作定位提示 |
| `final_authority=false` | 不构成最终权威 |
| `authorization_granted=false` | 查找不签发授权 |
| `body_read=false` | 查找未读取来源正文 |
| `requires_authorized_resolve=true` | 正文仍须进入获授权解析 |

上游没有提供来源类别时，`authority_class=null` 表示未提供分类，不能自动升级为 `primary` 或 `authoritative`。这些输出约束也不能反向证明客户端身份或来源权限。

## 3. 登记元数据的客户端披露边界

对 Registered Context Reference（已登记上下文引用）的候选查找路径，客户端标识必须由可信宿主配置明确绑定；模型或请求不能自行声明、覆盖或推导身份。仅传入一个 `client_id`（客户端标识）字符串不等于认证成功。

按引用元数据披露定位线索前，必须检查既有引用状态及明确的 `allowed_clients`（允许的客户端集合）。仅 `active` 且当前绑定客户端精确列入时，才允许进入查找集合；空集合为 deny-all（全部拒绝）。不通过检查的引用不应泄露其是否存在，也不披露 allowlist（允许名单）、授权指针或私人位置。

无权查看的引用与不存在的引用应返回相同的最小未命中结果。按 ID（标识）和按 routing hint（路由提示）查询必须使用同一过滤后的集合。缺失或非法客户端绑定应在处理引用快照前拒绝；歧义不得由 AI 自行选择。以上过滤仍只约束元数据披露，不产生正文许可或实时有效性。

## 4. 快照与传输完整性

宿主应明确提供有界元数据及预期摘要。结构和摘要检查只能证明输入符合该契约及声明字节，不能把历史授权、历史 active 状态或旧验证时间转换为当前权限。

输入规模、引用数量、请求和输出上限属于机械完整性约束。超限应明确拒绝，不静默截断引用或扩展范围；接口不得接受来源路径覆盖、身份覆盖、授权值或执行回调。

协议封装与业务契约保持分离。真实进程或传输测试证明该测试路径的运行行为；合成引用、声明式客户端绑定和成功协议调用不能证明真实来源授权、可信客户端认证或生产就绪。

## 5. 可选派生提示

Derived Hint（派生提示）单独保持 `authority_class=derived`、`rebuildable=true`、`usage_class=lookup_hint_only`、`final_authority=false`、`mandatory_dependency=false`。它不向普通来源传播 derived 身份，也不替代授权或溯源。

OpenWiki 只能作为可替换、可移除的可选示例；查找和获授权解析不依赖它。上游契约没有派生提示字段时，不应自行发明、登记或附加派生引用。

## 6. 验收与公开范围

候选验证应覆盖精确客户端匹配、缺失或非法绑定、非 active 状态、空允许集合、隐藏存在性、请求覆盖拒绝、快照摘要、大小边界、歧义和无正文 I/O（输入输出）。真实客户端集成另须验证可信宿主绑定与实际传输，并保留合成与真实证据的区别。

公共例子和测试必须从零构造，不复制私人快照、来源正文、授权对象、位置、身份或运行日志。私人候选验证不使 Public Core（公开核心）自动获得该实现、默认激活或生产能力；采用与激活仍属独立门禁。
