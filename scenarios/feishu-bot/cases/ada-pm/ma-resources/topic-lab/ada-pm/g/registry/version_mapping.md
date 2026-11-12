# 资源版本说明

## 1.2.0 — 2026-11-10
- 迁移：由 v1.1 单目录（business_line_id=topic-lab, employee_id=ada-pm）重组为 v1.3 独立智能体包。
- 本包：`g`，role=`sub`，visibility=`internal`，挂载 Skill：work-item、atomic-ops。
- 变更：`registry/employee.json` 拆为 `registry/agent.json`（id/version/role/visibility/owner/description）；sub 包无 `registry/agents.json`。
- 引用：`registry/skills.json` 由 `[id, source:local, version, path]` 改为 `[id, range]`。
- 脚本：work-item 的 `registry/employee.json` 引用适配为 `registry/agent.json`（parents[3] 定位在独立包下恰好回到包根）。
- 提示词、知识、Skill 内容、io 契约原文保留，仅按 v1.3 目录归位。
- 状态：BYOK 模型、owner 实名、Skill 上传、业务线 ID 全局唯一确认，均待平台处理。
