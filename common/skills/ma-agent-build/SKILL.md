---
name: ma-agent-build
description: 把一份按《MA Agent 搭建交付规范》组织好的「数字员工声明目录（业务线/数字员工/智能体）」映射成火山方舟 MA 上的真实资源（Environment / Vault / 知识记忆库 / Agent / Skill 引用），并落回执与台账。当研发者说「生效到 MA / 构建这个包 / 部署到测试环境 / apply 这个数字员工」时使用。
---

# MA Agent 构建（声明目录 → MA 资源）

把业务方按交付规范准备好的**三级声明目录**，编译成火山方舟 MA 侧的 Environment、只读知识记忆库、Agent（含 main→sub 的 multiagent 展开）与 Skill 引用。规则唯一事实源是《MA Agent 搭建交付规范》与《MA Agent 搭建映射规范（平台内部）》；本 skill 只做"声明 → 资源"的机械翻译，不改写业务内容。

## 何时用

- 研发者给出一份形如 `<业务线>/<数字员工>/<智能体>/` 的三级目录（每个智能体目录里有 `registry/agent.json`、`identity/` 三件套、`knowledge.yaml` 等），说"把这些生效到 MA 测试环境 / 构建 / deliver / apply"。
- 声明文件改了（提示词、知识、skill、引用），要把变更推上 MA。

## 前置

- `ARK_API_KEY` 已导出（或存在于约定的 `.env`）。`ARK_BASE_URL` 默认 `https://ark.cn-beijing.volces.com/api/v3`。
- 目录满足交付规范第 2 章的结构（完整包），每个智能体目录含 `registry/agent.json`（声明 `role`/`visibility`/`version`/`description`），`role: main` 的目录额外含 `registry/agents.json`（引用 sub）。
- 数字员工根目录（`<业务线>/<数字员工>/`）放一份 `build-config.json`：声明 `stage`、`model`、`tools`、可选 `environment`（只 `type`/`networking`/`env` 补充；`packages`/`env` 主值从各包 `environment.json` 合并）、可选 `credentials`（凭证密钥值，key = `secret_name`）。

## 执行步骤

1. 定位三级目录，确认根目录下有 `build-config.json` 且其 `model`/`tools` 齐全。
2. 只读预览（不建任何资源、不写台账）：
   ```bash
   python3 scripts/build.py <数字员工目录> --plan
   ```
   核对预览里的 agent 清单、Vault 清单、知识库序号、skill 清单是否符合预期、有无冲突（如 sub 未在 main 的 agents.json 引用、占位符未替换干净）。
3. 真实构建（自动先上传缺失/变更的 skill，再创建/更新 Environment、知识库、Agent；幂等，重复运行无变更不写）：
   ```bash
   python3 scripts/build.py <数字员工目录> [--stage dev] [--update-memory] [--update-env] [--rebuild-agents]
   ```
4. 读取产出的 `created_ids.json` 与构建回执（脚本 stdout），把 Environment/Agent/Memory Store ID 回写到调用方配置（Gateway 的 `config.env` 或 analyst-env 的资源清单）。

## 输出

- `created_ids.json`：environment_id、各 vault_id、各 memory_store_id、各 agent_id、skill_id，供 Gateway/analyst-env 引用。
- 台账（`.test-resources/<runId>.jsonl`）：每个创建/删除资源按精确 ID 记录，`--stage` 为测试名后缀时纳入清理范围。
- 构建回执：stdout 输出每个资源的"已创建/已复用/已更新"与冲突结果。

## 关键映射规则（速查）

- Agent 名 = `<业务线>-<数字员工>-<智能体ID>`；metadata 带 `role`/`visibility`/`stage`。
- system = `identity/identity.md`→`orchestration.md`→`handoff.md` 按「# 身份 / # 编排 / # 交接」拼接，`{{knowledge:路径}}`、`{{memory:库/路径}}`、`{{input}}`、`{{output}}` 由构建器替换，替换完不得残留 `{{`。
- 知识库命名 `<业务线>-<数字员工>-mem-knowledge-<序号>`，序号在数字员工内统一分配：先 main，再按 `registry/agents.json` 声明顺序，每个 `knowledge.yaml` 的 root 一个库，只读。
- `skills[].version` 是字符串；`multiagent.agents[].version` 是 int32（两处类型相反，写错 400）。
- main 的 `multiagent` 只展开一层、显式写 sub 的 id+version；允许 `type:self`（`agents.json` 里写 `{"id":"self"}`，仅 main）。
- **Vault**：每智能体一个（`<业务线>-<数字员工>-vault-<智能体>`），读 `connections.yaml`，凭证值取 `build-config.json.credentials`，不跨智能体合并。
- **Environment**：`packages`/`env` 从各包 `environment.json` 合并（冲突阻断），`type`/`networking`/`env` 补充取 `build-config.json`。

其余细节见 `references/mapping.md` 与映射规范原文。