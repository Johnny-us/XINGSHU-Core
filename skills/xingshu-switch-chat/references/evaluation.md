# 评测范围

本包保持 experimental / scaffold（实验流程），不作生产就绪声明。`context_budget_tier=production` 只选择入口文字预算，不能升级成熟度。owner（维护者）、review cadence（复查时机）、output contract（输出约定）和 rollback boundary（回退边界）见 manifest.json。

`scripts/validate_run.py --cases evals/run-cases.json` 检查23个合成状态记录；包含编号、版本、进度、停止点缺失/删改、UNKNOWN、普通 Web/Work、越权导航、旧记录隔离和在线辅助返回。只证明状态约定，不证明真实投递、来源真实性或授权。

`evals/trigger-cases.json` 与 semantic-config.json 是22条启发式触发夹具，供维护者评测误触发；不是模型驱动盲测，不是建窗实证。eval 文件全部为合成数据，不包含实际项目、聊天或私人路径。

正式现场验收必须在该用户/该客户端授权范围内重新核对真实编号、归属、输入、模型实读、进度/停止点、接受与源入口返回。一次在线辅助闭环不能证明长期稳定、后台回调、Web自主返回、其他通道恢复或另一台机器可用。

打包/安装检查运行仓库的 scripts/check_switch_chat_skill.py：固定提交字节、摘要、可重现 ZIP、隔离安装和移出发现目录、包内帮助程序与23个状态夹具。辅助脚本无第三方依赖；执行它需要已有 Python，普通使用本技能无需安装 Python。模型盲测、无技能基线、长期成功率等未提供时明确 missing evidence（证据缺失），不生成假结果。

通用品质状态见 reports/output_quality_scorecard.md。实际用户记录、截图、授权正文、账号和聊天编号只留在本机，不能用于公开包。
