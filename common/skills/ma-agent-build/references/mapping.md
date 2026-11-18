# 映射规则速查

事实源是两份规范原文，本文件只列构建器落地的要点，冲突以规范为准：

- 《MA Agent 搭建交付规范》—— 目录结构、标识、增量、格式、验收
- 《MA Agent 搭建映射规范（平台内部）》—— 第 6 章「交付物 → MA 资源」总映射

## 标识与命名

| 项 | 规则 |
|---|---|
| 业务线 ID | 小写字母/数字/连字符 3–24 位，平台统一分配，`platform` 保留 |
| 数字员工 ID | 业务线内唯一 |
| 智能体 ID | 数字员工内唯一；完整标识 `<业务线>.<数字员工>.<智能体>` |
| MA Agent 名 | `<业务线>-<数字员工>-<智能体>` |
| 知识库名 | `<业务线>-<数字员工>-mem-knowledge-<序号>`（序号：main 先，再按 `registry/agents.json` 顺序，每个 `knowledge.yaml` root 一个库） |
| Vault 名 | `<业务线>-<数字员工>-vault-<智能体>`（**每智能体一个**，收集不合并） |
| Environment 名 | `<业务线>-<数字员工>-env`（唯一一个 Environment） |

## system 拼接

`identity/identity.md` → `orchestration.md` → `handoff.md`，按「# 身份 / # 编排 / # 交接」固定顺序拼接；缺段省略，其余顺序不变。业务文件内标题从 `##` 起。

## 占位符（构建时替换，替换后不得残留 `{{`）

| 占位符 | 替换结果 |
|---|---|
| `{{knowledge:路径}}` | `/<知识库ID>/<路径>（使用记忆工具读取）`；多 root 时首段为 root 名 |
| `{{memory:库/路径}}` | 同构（当前构建器未实现长期记忆库映射，保留原样会报错） |
| `{{input}}` | `/mnt/session/uploads/` |
| `{{output}}` | `/mnt/session/outputs/` |

## 类型易错点（映射规范 6.2.2）

- `skills[].version` 是**字符串**（如 `"1"`）
- `multiagent.agents[].version` 是 **int32**（如 `1`）
- 写反会 400 `InvalidPayload`（`Mismatch type string/int32`）

## multiagent

- 只展开一层；`main` 引用 `sub`，`sub` 不再引用别人
- `type: coordinator`，`agents[]` 显式写 `id` + `version`（int32），**不使用 `type:self`**
- 创建顺序：先 sub、后 main（子 Agent 版本须已存在）

## 平台侧字段（不进业务包）

`model`、`tools`、`stage` 属于构建配置（`build-config.json`），由中台/平台决定，不进智能体包的 registry。`environment.type`/`networking`/`env` 补充也取 `build-config.json`，但 `packages`/`env` 主值从各包 `registry/environment.json` 合并而来（见下）。业务包（`registry/agent.json` 等）只声明身份、引用、知识、连接。

## Environment（唯一做合并的会话级资源，6.3/6.2.4）

- 读各包 `registry/environment.json`：`dependencies.python/node/system` → `packages.pip/npm/apt`，`env_vars[]` → `env`；
- 同包不同版本要求、同名 `env` 不同值 → 冲突阻断并指出两个来源包；
- `type`/`networking` 及 `env` 补充（如 `PYTHONUNBUFFERED`）从 `build-config.json.environment` 取（platform 决策）。

## Vault（每智能体一个，收集不合并，6.4/6.2.4）

- 每个智能体包一个 Vault，命名 `<业务线>-<数字员工>-vault-<智能体>`；
- 读该包 `connections.yaml`，每条 `api_key` 连接生成一条 `environment_variable` 凭证（`secret_name` + `secret_value`）；
- 凭证密钥值从 `build-config.json.credentials` 取（key = `secret_name`），缺值则跳过并警告；
- `kind` 非 `api_key`（`oauth_token`/`mcp`）暂未实现，跳过并警告；
- 会话挂所有智能体的 Vault 集合（`vault_ids`），不跨智能体合并。

## 待接（当前构建器未实现，对应规范章节）

- 长期记忆库 `memory/stores.yaml` 与 `{{memory:…}}`（6.5）当前未实现。
- 会话创建参数、资源锁定清单、会话版本快照（6.6/7.5/7.6）由下游（analyst-env / gateway）承接。