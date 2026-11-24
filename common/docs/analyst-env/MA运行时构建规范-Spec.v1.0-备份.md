# 基于 MA 的运行时构建规范（Spec）

> 版本：v1.0 · 适用对象：在方舟 Managed Agents（MA）上构建、交付、升级业务运行时的研发
> 配套文档：《能力需求收集表》（业务方填写）。收集表的每一项都能在本规范的清单里找到唯一位置，见[附录：收集表与清单的对应](#附录收集表与清单的对应)。
>
> 本规范分两层：**资源包层**（第 2 节）规定稳定资源怎样组织、信息归谁；**MA 资源层**（第 3 至 6 节）规定这些资源怎样落到 MA 并被升级。

---

## 1. 目标与原则

### 1.1 目标

研发交付的不是一组资源 ID，而是一份**构建文档**。任何人拿到它，不依赖作者记忆，就能：

1. **映射**：看清每项业务需求落在 MA 的哪类资源、哪个字段、哪个文件；
2. **重建**：在空账号或新环境里一次性重建同样的运行时；
3. **升级**：业务需求变化或 MA 平台升级时，知道改哪里、影响谁、怎么回滚。

### 1.2 原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | 以 MA 资源为骨架 | 清单的目录和字段就是 MA API 的资源和字段，不另造概念 |
| P2 | 声明式，单一事实源 | 期望状态只写在清单和它引用的文件里，平台资源是清单的结果 |
| P3 | 幂等 | 同一份清单重复执行，无变化时零写操作；资源按确定名称加 metadata 查找，不依赖记录下来的 ID |
| P4 | 密钥与配置分离 | 清单与仓库只出现凭证的名称、类型、提供人，不出现值 |
| P5 | 只读优先 | 初始化与启动阶段不修改已存在的资源，写入只发生在评审后的 `apply` |
| P6 | 平台漂移显式化 | 清单写明依赖的平台版本，平台升级时靠比对发现差异，不靠故障发现 |
| P7 | 信息唯一归属 | 每类信息只有一个事实源（见 2.2），其他位置只引用、不复制 |
| P8 | 稳定资源与运行实例分离 | 资源包只保存可复用的稳定资源；会话 ID、任务 ID 等运行实例信息不进资源包 |

---

## 2. 交付物：资源包

每个业务运行时交付一个**资源包**，目录名即逻辑名 `<logical_name>`（小写字母、数字、点、下划线、连字符）。资源包只保存**可跨会话复用的稳定资源**，不保存会话、任务等运行实例信息。

### 2.1 目录结构

```text
ma-build/<logical_name>/
├── README.md                    # 一页纸：做什么、谁负责、怎么 plan / apply / 回滚
├── registry/                    # 登记与版本：资源包的入口
│   ├── manifest.yaml            #   主清单：资源名、平台版本、业务版本、负责人（第 3 节）
│   ├── resources.lock.json      #   资源锁定清单：当前版本各资源的 ID 与版本、内容指纹
│   ├── version_mapping.md       #   人可读的版本映射（Skill、Agent、Environment 各自当前版本）
│   └── CHANGELOG.md             #   变更记录（第 6 节）
│
├── identity/                    # ① Agent：身份与行为
│   ├── agent.json               #   model / tools / mcp_servers / skills / context_management
│   ├── system.md                #   系统提示词正文
│   └── subagents/               #   子 Agent 定义（有则放，无则省略）
│
├── knowledge/                   # 业务知识：标准、口径、模板、案例、术语（可被 Skill 和提示词引用）
│   ├── standards/               #   生产与验收口径
│   ├── templates/               #   业务内容模板
│   ├── examples/                #   可复用案例（标准、边界、错误、回归）
│   └── glossary.md              #   术语表
│
├── tools/                       # 外部能力契约：只写接口、用途、所需凭证类型，不写凭证值
│   ├── _overview.md
│   └── <tool_name>.md
│
├── skills/                      # ② Skill：每个 Skill 一个目录（第 5 节）
│   └── <skill_name>/
│
├── environment/                 # ③ Environment
│   ├── environment.json         #   networking / packages / env（仅非敏感）
│   └── setup.sh                 #   初始化脚本（可选）
│
├── vault/                       # ④ Vault / Credential
│   └── credentials.spec.yaml    #   只写名称、类型、用途、提供人，不写值
│
├── memory/                      # ⑤ Memory Store
│   ├── memory-store.json
│   └── <路径>/*.md              #   一条记忆一个文件，目录结构即记忆路径
│
├── session/                     # ⑥ Session 创建参数
│   └── session.yaml             #   资源挂载与权限、固定的 Agent 版本、产物存储
│
├── io/                          # 输入输出契约
│   └── contracts/               #   机器可读的输入、产物结构定义
│
├── channel/                     # MA 之外：接入渠道与网关
│   ├── channels.yaml            #   渠道、可用范围、飞书权限与事件订阅登记
│   └── gateway.env.example      #   网关配置样板（无真实值）
│
└── verification/
    ├── smoke.md                 # 冒烟用例
    └── acceptance.md            # 业务验收用例
```

不适用的目录可以省略，但 `registry/`、`identity/`、`environment/`、`session/`、`verification/` 必须存在。

**判定规则：** 评审时若无法仅凭这个目录回答"某项需求在哪类资源的哪个字段里"，视为交付不合格。

### 2.2 信息唯一归属

每类信息只有一个事实源，其他位置只引用、不复制：

| 信息类型 | 唯一事实源 |
|---|---|
| Agent 的角色、行为边界、提示词 | `identity/` |
| 业务口径、标准、模板、案例、术语 | `knowledge/` |
| 外部能力的接口与所需凭证类型 | `tools/` |
| 可执行的封装能力（说明、脚本、参考资料） | `skills/<name>/` |
| 沙箱依赖、网络、非敏感环境变量 | `environment/` |
| 凭证的名称、类型、用途、提供人 | `vault/credentials.spec.yaml` |
| 凭证的真实值 | 外部密钥存储（Vault 或密钥管理系统），**不进入资源包** |
| 跨会话共享的长期知识 | `memory/` |
| 会话创建时的挂载、权限、产物存储 | `session/session.yaml` |
| 输入、产物的结构定义 | `io/contracts/` |
| 当前版本各资源的 ID、版本、指纹 | `registry/resources.lock.json` |
| 变更历史 | `registry/CHANGELOG.md` |

边界规则：

- `knowledge/` 保存可复用的稳定知识；某次任务的原始材料、聊天记录、失败文件不进入资源包。
- `knowledge/templates/` 保存业务内容模板；可执行的提示词和脚本随具体 Skill 保存在 `skills/<name>/`。
- `registry/` 只保存资源登记与版本引用，不保存会话 ID、任务 ID、工具调用产生的实例 ID。
- 提示词引用知识时，引用 `knowledge/` 中的文件，不在 `system.md` 里复制一份。

### 2.3 凭证引用

- `tools/<name>.md` 与 `environment/` 只声明**所需凭证的类型**，不保存凭证值。
- `vault/credentials.spec.yaml` 为每个凭证登记 `name`、`system`、`type`、`purpose`、`owner`，以及它在外部密钥存储中的引用标识 `secret_ref`。
- 凭证值只在运行时由 Vault 或网关解析，不得写入资源包、会话事件、产物、日志或回执。

### 2.4 资源锁定清单 `resources.lock.json`

锁定清单记录**当前发布版本**各资源的确切身份，是升级、回滚、`plan` 比对的依据：

```json
{
  "logical_name": "<logical_name>",
  "version": "1.0.0",
  "ma_runtime": { "docs_snapshot": "YYYY-MM-DD", "toolset_type": "agent_toolset_20260916" },
  "agent":       { "id": "agent-…", "version": 3, "system_sha256": "…", "model_fp": "…" },
  "environment": { "id": "env-…", "config_sha256": "…" },
  "vault":       { "id": "vlt-…", "credentials": ["<name>"] },
  "memory":      [ { "id": "memstore-…", "access": "read_only", "entries_sha256": "…" } ],
  "skills":      [ { "name": "<skill_name>", "skill_id": "skill-…", "fingerprint": "…" } ]
}
```

- 锁定清单由 `apply` 生成并随发布提交，**不得手工编辑**。
- 每次发布，锁定清单与 `CHANGELOG.md` 同步更新；`plan` 比对的是清单与锁定清单，再与平台现状三方对照。
- 资源 ID 允许出现在锁定清单里，不允许出现在其他文件里。

### 2.5 会话固定的版本快照

灰度、复现问题或事后审计时，需要知道**某个会话到底按什么版本运行**。创建会话时必须固定 Agent 版本，并把本次采用的资源版本记录下来：

```text
会话 = Agent 版本 + Environment + Vault + 记忆库及权限 + TOS 挂载 + 产物存储 + 模型鉴权 Header 名称
```

- 会话创建后，后续资源变更不影响既有会话对原版本的引用。
- 该记录保存在网关侧（会话映射），不写入资源包，不含凭证值。

### 2.6 产物与过程信息

- 沙箱里 `/workspace` 与 `/tmp` 是**过程信息**：可重新计算的加工数据、分析草稿、调试输出，不是交付物，会话结束即可丢弃。
- `/mnt/session/outputs/` 是**正式产物**：需要保留、复用、送检或交付的结果必须写到这里。
- 每个正式产物应能回答：它由哪次会话产生、依据什么输入、用的哪个版本的资源（见 2.5）。
- 产物是交付的事实源；对外导出、打包的版本由产物派生，修改应回到产物重新生成，不直接编辑导出件。

### 2.7 反馈与经验沉淀

交付后的确认、修改意见、效果反馈，按影响范围处理：

| 影响范围 | 处理 |
|---|---|
| 只影响本次会话 | 保留在该会话，不沉淀 |
| 对后续任务有价值的稳定结论 | 经整理后写入 `memory/`（须符合 4.5 的权限与审核要求） |
| 可跨场景复用的方法、标准、案例 | 作为 `knowledge/` 的更新候选，走第 6 节变更流程 |

原始聊天、日志、失败文件和含业务敏感信息的材料不直接进入 `memory/` 或 `knowledge/`。

---

## 3. 主清单 `registry/manifest.yaml`

```yaml
spec_version: 1                  # 本规范版本，不是业务版本
logical_name: <logical_name>
version: 1.0.0                   # 业务版本，语义化，见 6.3
owner: { team: "", primary: "", backup: "" }

ma_runtime:                      # 依赖的平台版本，升级时据此比对
  docs_snapshot: "YYYY-MM-DD"    # 最近一次同步 MA 文档合集的日期
  toolset_type: agent_toolset_20260916
  base_agent: ark_agent_preview
  api_base: https://ark.cn-beijing.volces.com/api/v3
  region: cn-beijing

resources:                       # 顶层资源：按确定名称加 metadata 定位
  agent:       { name: <logical_name>-agent,  file: identity/agent.json }
  environment: { name: <logical_name>-env,    file: environment/environment.json }
  vault:       { name: <logical_name>-vault,  spec: vault/credentials.spec.yaml }
  memory:      { name: <logical_name>-memory, file: memory/memory-store.json }
  skills:      [ { name: <skill_name>, dir: skills/<skill_name> } ]
  session:     { file: session/session.yaml }
  metadata_tags: { managed_by: <工具名>, logical_name: <logical_name> }
```

每个顶层资源必须带 `metadata`：`managed_by`、`logical_name`、`role`（agent / environment / vault / memory），用于按名称加标记查找，防止同名误删。

---

## 4. 各资源的字段规范

每节结构：**要收集什么 → 清单落点 → 规则**。"要收集什么"与收集表同一章节一一对应。

### 4.1 Agent（`identity/`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 名称、描述 | `identity/agent.json: name, description` | 名称确定、唯一 |
| 模型 | `identity/agent.json: model.*` | 见下方模型表 |
| 长对话压缩阈值 | `identity/agent.json: context_management` | 在 Session 创建时固定，修改只对新建的 Session 生效 |
| 系统提示词 | `identity/system.md` | 纯文本；摘要哈希写入锁定清单；不含密钥；引用业务口径时引用 `knowledge/`，不复制 |
| Skill 列表 | `identity/agent.json: skills[]` | 整体替换语义，必须写完整数组；单个 Agent 最多 50 个 |
| 外部服务（MCP） | `identity/agent.json: mcp_servers[]` 与 `tools[] mcp_toolset` | 整体替换语义；MCP 的鉴权凭证走 Vault（4.4） |
| 工具与权限 | `identity/agent.json: tools[]` | 工具集类型以 `ma_runtime.toolset_type` 为准；逐项登记 `permission_policy` |

**模型字段：**

| 字段 | 方舟模型 | BYOK Direct（自带模型） |
|---|---|---|
| `id` | 方舟模型目录 ID | 客户模型的实际模型 ID |
| `provider` | — | 必填，网关名称 |
| `base_url` | — | 必填，完整服务地址（到 `/v1/chat/completions`），公网可达 |
| `protocol` | — | 必填，仅 `openai_chat_completions` 或 `anthropic_messages` |
| `token_limits` | — | 必填，三个值均为大于 0 的整数：`context_window`、`max_input_token_length`、`max_output_token_length`，按模型真实能力填写 |
| 鉴权 | 方舟 Key | 请求级：每次发送事件时携带 `X-User-Model-Header-<原始 Header 名>`，不写入 Agent、Session 或清单 |

清单只登记 Header 名称，以及"值由谁提供、存在哪里"。

**更新规则：** Agent 是版本化资源，更新必须带当前 `version`。遇到 `version: conflict`，必须重新查询并合并最新配置后再提交，不得只自增本地版本号重试。只改部分字段时可只传该字段，但 `tools`、`mcp_servers`、`skills` 一旦传入即整体覆盖。

### 4.2 Skill（`skills/`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| Skill 名称、用途、负责人 | `manifest.resources.skills[]` | 展示名统一为 `<name>@<内容指纹前 12 位>` |
| Skill 内容（ZIP） | `skills/<name>/`（源码目录，可重新打包） | 见第 5 节 |

### 4.3 Environment（`environment/`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 网络 | `config.networking` | 默认 `unrestricted`；业务方要求白名单时写明域名，并走评审 |
| 预装依赖 | `config.packages` | 必须显式锁定版本下限，如 `pandas>=2.0`；未指定版本会装最新，构建不可重现 |
| 初始化脚本 | `setup.sh` 对应 `config.setup_script` | 以 `set -e` 开头；下载二进制必须校验 sha256；注明来源；多段脚本用子 shell 隔离 |
| 非敏感环境变量 | `config.env` | 只放非敏感配置：时区、模型 ID、开关、非密钥地址 |

**Key、Secret、Token、密码一律禁止放在 `env`**，应放 Vault（4.4）或由网关按请求注入。

### 4.4 Vault / Credential（`vault/`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 需要访问哪些外部系统、用什么凭证、谁提供 | `credentials.spec.yaml` | 每项写 `name`、`system`、`type`、`purpose`、`owner`；不写值 |

凭证类型：

| 类型 | 适用 | 特点 |
|---|---|---|
| `mcp_oauth`、`static_bearer`、`mcp_static` | 访问 MCP 服务 | 创建时立即与 MCP 服务握手，服务不可达则创建失败 |
| `environment_variable` | 命令行、SDK、直接 API 调用 | 沙箱内是不透明占位符，出口处替换为真实值，Agent 看不到密钥 |
| `env_oauth` | 环境变量型 OAuth | 同上，按 `secret_name` 注入 |

规则：

- 同一 Vault 内，`mcp_server_url`（MCP 类）与 `secret_name`（环境变量类）必须唯一，重复创建返回 409。
- 凭证密钥只写不读，创建后无法读回；`auth.type` 创建后不可修改。
- 已挂载 Vault 的既有 Session 感知不到之后新增的凭证，新增凭证后必须新建 Session。

### 4.5 Memory Store（`memory/`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 名称 | `memory-store.json: name` | |
| 每个记忆库的读写权限（业务决策） | `session.yaml: resources[].access` | **逐个记忆库**配置，`read_only` 或 `read_write`，未配置的默认 `read_only`；选 `read_write` 须同时收集「允许写入的内容类型」与「审核人、审核频率」，写入清单备注 |
| 记忆条目 | `memory/<路径>.md` | 一条一个文件；路径即记忆路径；单条不超过 100 KiB；单个 Store 不超过 2,000 条 |

规则：

- **`access` 按记忆库逐个配置，由业务方决策；未配置的记忆库一律按 `read_only`。** 平台自身的默认值是 `read_write`，因此挂载时必须**显式下发** `access`，不得省略。
- `read_only`：Agent 只能浏览、读取、搜索。`read_write`：Agent 还能创建、更新、删除、移动记忆，修改会保存并影响后续所有 Session。
- 共享规范、知识库、术语表类的 Store 使用 `read_only`。选 `read_write` 的，必须写明原因与审查方式，因为 Agent 处理的不可信内容（用户输入、网页、第三方工具返回）可能被写入记忆，并在后续 Session 中被当作可信信息读取。
- 单个 Session 最多挂载 10 个 Memory Store。
- 提示词里"不要写入记忆"只是文字约束，**平台不会据此拦截**，权限以 `access` 为准。

### 4.6 Session 创建参数（`session/session.yaml`）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 挂载的 Memory | `resources[] type: memory_store` 与 `access` | 见 4.5 |
| 挂载的共享数据（TOS） | `resources[] type: tos` | 见下 |
| 用户输入文件 | `resources[] type: file` | 单个 Session 最多 10 个；运行中可追加 |
| 绑定的 Vault | `vault_ids` | |
| 固定 Agent 版本（灰度） | `agent: {id, version}` | 固定后，Agent 发布新版本不影响该 Session |
| 产物存储 | `environment: {type: environment_with_overrides, config.tos}` | 见下 |

**TOS 挂载与产物存储是两个独立配置，不得混淆：**

| | 配置位置 | 沙箱路径 | 用途 |
|---|---|---|---|
| TOS 资源挂载 | Session `resources[] type: tos`：`tos_bucket`、`tos_key` | `/mnt/session/storage/` | 输入或共享数据，只读 |
| 产物存储 | `config.tos`：`bucket`、`prefix` | `/mnt/session/outputs/` | Agent 最终交付物的持久位置 |

**TOS 挂载规则：**

- 一个 Session 可挂载多个 TOS 目录，完全相同的目录不能重复。
- `tos_key` 必须是以 `/` 结尾的目录，且该前缀下已存在对象；前缀不存在则创建 Session 失败。
- TOS Bucket 必须与 MA 服务同地域，并已在方舟项目中完成授权。
- 预检按目录逐个进行，任一目录不可用，整个创建请求失败。
- `memory_store` 与 `tos` 资源只能在创建 Session 时挂载；`file` 资源可在运行中追加。

**产物存储规则：**

- 交付物需要长期保存时，**必须配置产物存储**；不配置则落在平台公共存储，到期被清理。
- 优先在创建 Session 时通过 `environment_with_overrides` 覆写 `config.tos`，不修改可复用的 Environment；产物存储对所有 Session 一致时，也可直接配置在 Environment 上（类别 B，须评审）。
- `bucket` 与 `prefix` 必须同时提供，`prefix` 以 `/` 结尾。
- Files API 的写入前缀为 `{prefix}outputs/{env-id}/{session-id}/`，最终对象路径以响应中的 `tos.object_key` 为准。
- 删除 Session 不会删除桶中的对象，对象生命周期在 TOS 中管理。

### 4.7 接入渠道与网关（`channel/`，MA 之外）

| 要收集的信息 | 清单落点 | 规则 |
|---|---|---|
| 入口形态（单聊、群聊） | `channels.yaml` | 群聊须 @ 机器人 |
| 可使用的人员范围 | `gateway.env.example: AUTHORIZED_OPEN_IDS` | 白名单，留空表示不限 |
| 飞书权限与事件订阅 | `channels.yaml`（登记） | 在开放平台人工配置，创建版本并发布后生效；需订阅 `im.message.receive_v1`（长连接） |
| 模型请求鉴权 Header | `gateway.env.example` | 只登记 Header 名与持有人 |
| 会话等待上限 | `gateway.env.example` | |

---

## 5. Skill 交付规范

| 项 | 要求 |
|---|---|
| 目录 | ZIP 内只有一个顶层目录 `<skill_name>/`，目录下直接包含且仅包含 1 个 `SKILL.md`；可选 `scripts/`、`references/` |
| `SKILL.md` | 写清何时触发、做什么、输入输出、限制；描述具体到模型能判断"该不该用我" |
| 通用性 | 定义可复用的能力，不写一次性任务的具体数据；具体任务由会话消息传入 |
| 体量 | 不超过 500 个文件；上传原始总大小不超过 30 MiB；解压后单文件不超过 30 MiB、总计不超过 120 MiB |
| 版本指纹 | 内容变化即生成新版本（同一 Skill ID）；重新打包同样内容不得产生新版本 |
| 禁止项 | 硬编码密钥、令牌、个人账号；`__pycache__`、`.DS_Store`、虚拟环境、临时输出 |
| 依赖声明 | Skill 需要的包与工具登记到 Environment 清单（类别 B），不得在 Skill 里用脆弱的绕法掩盖环境缺失 |
| 自检 | 打包后重新解压并实际运行一遍，保留输出 |

---

## 6. 变更、版本与升级

### 6.1 变更类别与对已有会话的影响

| 类别 | 变更内容 | 对已有 Session 的影响 | 上线方式 |
|---|---|---|---|
| A | Agent：模型、提示词、工具、MCP、Skill 引用 | 不自动切换。须对处于 `idle` 且上一轮以 `end_turn` 结束的 Session 调用升级会话，或新建 Session | 新建 Session 固定新版本灰度，再升级存量 |
| B | Environment：依赖、脚本、env、网络、产物存储 | 同 A | 同 A |
| C | Vault：新增或修改凭证 | 既有 Session 感知不到新增凭证 | 新建 Session |
| D | Session 资源：`memory_store`、`tos`（含 `access`） | 只能在创建时挂载 | 新建 Session |
| E | `file` 资源 | 运行中可追加 | 即时 |
| F | Skill 内容 | 不直接影响；须在 Agent `skills[]` 更新引用才生效 | 随 A 上线 |
| G | 网关配置（白名单、超时等） | 不影响 MA 资源 | 重启网关 |
| H | 模型请求鉴权 | 不影响 MA 资源 | 重启网关 |
| I | 飞书应用权限、事件订阅 | 无 | 创建版本并发布后生效 |

补充约束：

- 升级会话不能换绑其他 Agent 或 Environment；同一 Session 不能同时存在多个升级请求，且须先处于 `idle`。
- 平台上限：Skills 50、tools 128、环境变量 64。接近上限时先清理再新增。
- 不再使用的 Agent、Environment、Session 优先归档，归档后保留配置与历史，已有 Session 继续使用创建时的快照。删除前必须确认没有关联 Session。

### 6.2 变更流程

1. **变更说明**：PR 中写明类别（A 到 I）、涉及的清单位置、预期影响面。
2. **`plan`（只读）**：把清单、锁定清单、平台现状三方对照，产出差异；差异必须与变更说明一致，多出的差异视为漂移，先查明。
3. **评审**：至少一名非作者；涉及密钥、网络、外发、产物存储的变更须安全评审。
4. **`apply` 到研发环境**，不得直接修改正式环境。
5. **冒烟**：执行 `verification/smoke.md`，保留真实输出。
6. **灰度**：新建 Session 固定新版本验证，再升级存量的 `idle` Session；`running` 的 Session 记入待升级清单，不强行中断。
7. **回写**：`apply` 重新生成锁定清单，并更新清单、CHANGELOG、`version_mapping.md`。

**回滚：** 以上一发布版本的锁定清单为目标：Agent 回退到其记录的版本；Skill 把 `skills[]` 改回其记录的指纹；Environment 用上一版清单重新 `apply`。回滚同样走灰度。

### 6.3 版本与指纹

- 业务版本 `manifest.version` 采用语义化版本：A、B、C 类破坏性变更升主版本；新增能力升次版本；仅文案、记忆、修复升修订版本。
- 指纹：Agent 的 `metadata.model_fp`、Skill 的 `@<指纹>`、`system.md` 的摘要哈希，均写入锁定清单，`plan` 时比对。
- CHANGELOG 条目格式：

```markdown
## 1.1.0 — YYYY-MM-DD
- 类别：A, B
- 变更：<做了什么>
- 影响面：存量 idle Session 需升级；running Session 记入待升级
- 验证：smoke.md 用例 1-7 通过（见 PR 评论）
- 回滚：Agent 回退到上一版本；Environment 用上一版清单 apply
```

### 6.4 MA 平台升级流程

平台升级（文档合集变化、接口、字段、工具集类型更新、术语改名）时，不等故障出现，按以下步骤处理：

1. **同步文档**：执行 `common/skills/volc-docs-sync/update_docs.py`，在 PR 中贴出文档 diff 里标题、类型、字段名的变化。
2. **比对清单**：核对 `ma_runtime` 与各资源文件里出现的类型字符串、字段名、接口路径、Header，是否仍出现在最新文档中：
   ```bash
   grep -o 'agent_toolset_[0-9]*' common/docs/火山方舟_ManagedAgents_docs.md | sort -u
   grep -o 'agent_toolset_[0-9]*' ma-build/<name>/identity/agent.json | sort -u
   ```
3. **分级处理：**
   - **兼容**：与最新文档一致，只更新 `docs_snapshot`。
   - **漂移**：清单使用的类型或字段已不在最新文档中。在研发环境新建 Session 验证旧值是否仍可用、行为是否一致，再决定升级时机，不得凭文档推断。
   - **破坏**：旧值被拒绝或行为改变。按 A、B 类变更走完整流程。
4. 更新 `ma_runtime`，执行 6.2。
5. 评估 `common/docs/managed-agents-architecture-atlas.html` 是否需要同步更新。

---

## 7. 安全红线（违反即驳回）

1. 清单、仓库、PR、日志、Skill、产出文件中不得出现任何密钥明文，只写名称与类型。
2. Environment 的 `env` 不得存放密钥，密钥走 Vault 或请求级注入。
3. 初始化与启动阶段只读：不得更新、删除、重建已存在的 Agent、Environment、Vault、Memory Store。写入只发生在评审后的 `apply`。
4. 不得对生产资源先删后建；需要重建时，先归档、再新建、再切换。
5. Memory Store 的 `access` 按记忆库逐个声明、默认只读，且挂载时显式下发，不得依赖提示词约束读写权限。
6. 测试资源必须使用独立的测试逻辑名并登记台账，仅按台账中的精确 ID 清理；正式资源不进入清理范围。
7. 业务数据进入模型的范围必须与业务方确认的结论一致。
8. 文档与脚本里的启动命令必须写明解释器与环境，如 `<python> -m <模块> ...`，不得依赖全局安装的同名命令，避免被其他版本的同名命令抢占。

---

## 8. 验证与验收

**`plan` 报告必含：**

- 清单与平台现状的差异，按资源、字段列出；
- 漂移项（平台上有、清单里没有）；
- 缺失的凭证与待补充项，标 `ASK`，对应项不创建，不得用占位值替代；
- 对存量 Session 的影响清单：可升级、需新建、待升级。

**冒烟用例最低要求：**

| # | 用例 | 通过标准 |
|---|---|---|
| 1 | 单聊发一句话 | 收到回复，Session 创建成功 |
| 2 | 触发一次沙箱命令 | 真实命令输出，不是文字复述 |
| 3 | 读取 TOS 挂载目录 | `/mnt/session/storage/` 下能列出预期文件 |
| 4 | 读取 Memory，并尝试写入 | 能引用记忆；写入按 `access` 被允许或拒绝，与清单一致 |
| 5 | 调用每个已接入的 MCP 与外部系统 | 每个至少成功一次 |
| 6 | 产出一个文件到 `/mnt/session/outputs/` | 能取回；配置了产物存储后，桶中对应前缀下能找到对象 |
| 7 | 越界请求（索要密钥、无关泛聊） | 拒绝并引回职责 |

**合入前检查单：**

- [ ] 目录结构符合 2.1，清单字段齐全；`registry/resources.lock.json` 已随发布更新
- [ ] 信息只出现在 2.2 规定的唯一事实源，无重复副本；资源包内无会话 ID、任务 ID 等运行实例信息
- [ ] 每类资源的信息都落在第 4 节规定的位置
- [ ] 变更类别（A 到 I）已标注，影响面已写明
- [ ] 无密钥明文（含 Environment `env`、日志、截图）
- [ ] `packages` 已锁定版本下限；`setup_script` 带校验和
- [ ] 每个记忆库的 `access` 已逐个声明（未声明的为只读），挂载时已显式下发
- [ ] 交付物需要长期保存的，已配置产物存储
- [ ] `ma_runtime` 已更新到最近一次文档同步，漂移项已处理或登记
- [ ] `plan` 报告已附；`apply` 仅在研发环境执行
- [ ] 冒烟用例全部通过，附真实输出
- [ ] CHANGELOG 与版本号已更新；回滚方案已写
- [ ] 非作者评审通过

---

## 附录：收集表与清单的对应

| 收集表章节 | 清单位置 | 规范章节 |
|---|---|---|
| 基本信息 | `registry/manifest.yaml: owner`、`README.md` | 3 |
| Agent（模型、提示词、Skill、MCP、工具） | `identity/`、`skills/`、`tools/` | 4.1、4.2、5 |
| Environment（网络、依赖、脚本、环境变量） | `environment/` | 4.3 |
| Vault（外部系统凭证） | `vault/credentials.spec.yaml` | 4.4 |
| Memory Store（读写权限、条目） | `memory/`、`session/session.yaml: access` | 4.5 |
| Session 创建参数 | `session/session.yaml` | 4.6 |
| 接入渠道 | `channel/` | 4.7 |
| 业务口径、标准、模板、案例（如有） | `knowledge/`、`io/contracts/` | 2.1、2.2 |
| 补充 | 评审时归类到上述任一资源 | — |

TOS 挂载目录与产物存储由研发按 4.6 维护，不向业务方收集。
