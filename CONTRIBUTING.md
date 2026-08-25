# Contributing to XINGSHU Core（参与 XINGSHU Core）

感谢为 XINGSHU Core 提供公共改进。本仓库只接受通用、可公开、可维护且不依赖任何 Personal Instance（私人实例）的贡献。

提交前请阅读：

- [Core / Personal Instance / Backup Boundary](CORE_PERSONAL_BOUNDARY.md)
- [Security Policy](SECURITY.md)
- [Governance Versioning](docs/GOVERNANCE_VERSIONING.md)

## Allowed Contributions（允许的贡献）

- 公共治理改进；
- 文档改进；
- 模板改进；
- 通用能力、稳定契约或架构提案。

贡献应保持 Provider-neutral（能力提供方中立），并能够由不同用户和 Personal Instance 独立采用。

## Prohibited Content（禁止内容）

不得提交：

- Personal Instance 数据或原文件；
- 个人身份、私人画像或联系人信息；
- 设备信息、本地绝对路径或私人环境状态；
- 密码、Token、Cookie、私钥、认证文件或其他 Secret（秘密值）；
- 私人项目、任务、资产、工作记录或运行状态；
- 无权公开、再授权或贡献的第三方内容。

技术上能够访问、复制或提交某项内容，不代表拥有公开权或贡献权。

## Contribution Process（贡献流程）

1. 确认内容具有跨实例的公共价值；
2. 完成抽象、去实例化、去身份化、去设备化、去账号化和去路径化；
3. 检查来源、版权、许可证、公开权与第三方处理限制；
4. 执行 Secret、Identity、Path、Device 和 Reference 检查；
5. 保持变更范围最小，并说明目的、影响、兼容性和必要回滚路径；
6. 通过 Pull Request（合并请求）提交为公共候选，接受维护者审查。

贡献进入仓库、通过技术检查或获得较新 Commit，不代表治理内容自动成为 `active`。治理状态、批准和发布继续遵守 Governance Versioning。

## Security Reports（安全问题）

真实漏洞、凭据暴露或其他敏感安全问题不得通过公开 Issue、Discussion 或 Pull Request 披露。请按 [SECURITY.md](SECURITY.md) 使用私密报告渠道。

## License & Provenance（许可证与来源）

提交贡献即表示贡献者有权提供该内容，并能够说明必要来源、许可证与 AI 参与方式。无法确认公开权、版权或许可证兼容性时，应停止提交并先完成复核。
