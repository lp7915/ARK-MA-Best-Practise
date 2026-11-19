# ma-agent-build · 全资源声明式覆盖（预览 → 确认 → 执行）方案

> 版本：v0.2 · 2026-11-19（v0.1 → v0.2：采纳「先预览后执行」简化执行模型；新增「资源映射台账」多维表格解决 ID 感知）
> 目标：让 `ma-agent-build` 对**所有 MA 资源**（Agent / Environment / Vault 容器与凭证 / 知识库容器与条目）统一做「声明 vs 现状」比对，分别判定 **新增 / 修改 / 删除 / 无变化**，一次跑完幂等，不再靠 `--update-env`、`--update-memory` 这类手动开关。
> 依据：映射规范 6.2.4（收集 vs 合并）、6.4/6.5/6.8；本地官方文档（Environment 不做版本化、凭证结构字段创建后锁定、Memory 条目可更新/删除、**所有资源的 metadata 列表过滤均被忽略**）。

---

## 0. 已定决策（用户 2026-11-19 确认）

| # | 决策 | 影响 |
|---|---|---|
| D1 | **skill 默认只预览**：输出本次资源变动（增/改/删/孤儿），用户确认后执行；执行时**重新计算 diff**（预览与执行是同一个确定性计算，正常情况下结果一致，**不落 plan 文件**）；不考虑并发，skill 的输入输出固定 | 去掉 `--prune`/`--yes`/现状指纹校验/plan 文件；删除（含顶层资源）作为预览中的一项，用户确认即执行 |
| D2 | **新建多维表格维护「员工 ↔ MA 资源 ID」映射**（资源映射台账） | skill 通过台账感知各员工的顶层资源及其下属 ID，不再靠命名前缀猜 |
| D3 | 环境/记忆/凭证**不进原子能力注册表**，走台账 + 声明式 diff | 注册表只管可复用能力（agent/skill 版本），台账管「这一位员工在 MA 上实际有哪些资源」 |

## 1. 现状与差距（已核对代码）

| 资源 | 新建 | 修改 | 删除 | 自动检测变化 | 持久记录 ID |
|---|---|---|---|---|---|
| Agent | ✅ | ✅ 原地更新 | ❌ | ✅ `_agent_changed` | ✅ 注册表（仅 agent） |
| Environment | ✅ | ⚠️ 仅 `--update-env` | ❌ | ❌ | ❌ |
| Vault 容器 | ✅ | — | ❌ | ❌ | ❌ |
| Vault 凭证 | ✅ | ❌（同名直接复用） | ❌ | ❌ | ❌ |
| 知识库容器 | ✅ | — | ❌ | ❌ | ❌ |
| 知识库条目 | ✅ | ⚠️ 仅 `--update-memory` | ❌ | ❌ | ❌ |

资源定位现状：`find_by_name` 拉全量列表按 `name`/`display_name` 比对。官方文档实测**所有资源的 metadata 过滤都被静默忽略**，所以这是唯一能在 MA 侧查的办法，但它：①只能找「声明里有的」，找不到孤儿；②`created_ids.json` 只落在临时沙箱，下次会话即丢；③只有 Agent 创建时写了 `managed_by` 等 metadata。

## 2. 资源映射台账（D2）

### 2.1 位置与结构

- Base：**MA资源映射台账** `R5HfbbwT7a3WMSs7pkjc8crvnnB`（https://bluefocus.feishu.cn/base/R5HfbbwT7a3WMSs7pkjc8crvnnB）
- 表：`资源映射` `tbl7BQiIiB8x9333`（已建、已验证注册表应用可写）
- 与原子能力注册表（`ZRg5bp8lZavDRPsq9eQcp32UniO`）**是两个独立的 Base**：注册表 = 可复用能力版本；台账 = 员工实例的资源 ID。

| 字段 | 类型 | 说明 |
|---|---|---|
| `resource_key` | 文本（首列，唯一键） | `<业务线>/<员工>/<kind>/<稳定名>`，如 `topic-lab/ada-pm/agent/t`、`topic-lab/ada-pm/memory_entry/mem-knowledge-02:/standards/routing.md`。**upsert 的唯一依据** |
| `business_line` / `employee` | 文本 | 归属 |
| `agent` | 文本 | 归属智能体（员工级资源如 Environment 留空） |
| `kind` | 单选 | `agent / environment / vault / credential / memory_store / memory_entry / skill` |
| `resource_name` | 文本 | MA 上的名字（`<业务线>-<员工>-…`） |
| `ma_id` | 文本 | MA 资源 ID（`agent-…`/`env-…`/`vlt-…`/`memstore-…`；条目为 memory id） |
| `ma_version` | 文本 | Agent 的 MA 版本（其他资源留空） |
| `fingerprint` | 文本 | 声明侧内容指纹（system/config/条目内容/凭证值指纹 sha256 前缀），用于判「是否修改」；**不存任何明文密钥** |
| `parent_ma_id` | 文本 | 下属关系：条目 → 知识库 id；凭证 → vault id |
| `stage` | 单选 | `dev / staging / prod / mvp` |
| `status` | 单选 | `active / orphan / deleted`（删除后保留一行作审计，不物理删） |
| `managed_by` | 文本 | 固定 `ma-build` |
| `last_build_id` | 文本 | 最近一次成功执行的构建时间戳（如 `20261119-1530`），仅作审计 |
| `updated_at` | 日期时间 | |
| `note` | 文本 | 备注 |

### 2.2 台账 vs MA 现状：谁是事实源

**台账是「索引」，MA 是「事实」**：

- plan 时：先读台账得到该员工的资源 ID 集合 → 用 ID 直接 `GET` MA 取现状（不再靠名字猜）；
- 台账里有但 MA 查不到（被人手动删了）→ plan 标 `missing`，用户确认后按声明重建并更新台账；
- 声明里有、台账没有 → 走**首次发现**：按命名约定在 MA 全量列表里按名字找（`find_by_name`，现有逻辑），找到则「认领」写入台账（plan 里列为「补登台账」），找不到则新建；
- 声明里没有、台账有且 `active` → **orphan 候选 / 删除项**，进入预览。

这样孤儿有据可查（台账记过的才是孤儿），**不会误伤**别的业务方的同前缀资源，也不再依赖 metadata 过滤（MA 不支持）。

### 2.3 与「每类资源创建时写 metadata」的关系

仍建议各资源创建时尽量写 `managed_by`/`business_line`/`employee` metadata（Agent/Environment/Vault/Credential/Memory Store 都支持），作为台账之外的**人工可见标记**；但**逻辑不依赖它**。

## 3. 执行模型（D1）

```text
┌─ 预览（skill 默认）──────────────────────────────────────┐
│ diff = compute_diff(声明, 台账, MA 现状)                   │
│ 输出变动清单（增/改/删/孤儿/补登），不写任何资源              │
└──────────────────────────────────────────────────────────┘
                          ↓ 用户在对话里确认
┌─ 执行 ──────────────────────────────────────────────────┐
│ diff = compute_diff(声明, 台账, MA 现状)   ← 重新计算       │
│ 按 diff 逐条执行（create/update/delete/补登）              │
│ 每条成功后立即 upsert 台账；输出 created_ids.json 与回执    │
└──────────────────────────────────────────────────────────┘
```

- **预览与执行共用同一个 `compute_diff`**，区别只是「算完是否执行」。执行时重新计算，不落 plan 文件、不记预览内容；skill 的输入输出固定，正常情况下两次计算结果一致，预览看到的就是将要执行的。
- 不做并发 / 现状指纹校验（D1）。
- 某条执行失败：停止后续、输出已完成/未完成清单，台账只记成功项；重跑预览会自然得到剩余变动（幂等）。
- 命令形态：`build.py <员工目录>`（默认预览）、`build.py <员工目录> --apply`（计算并执行）。`--update-env` / `--update-memory` 废弃。机读输出 `--json` 作为可选项，仅用于研发助手解析预览，不是执行依据。
- 实现上的约束：`compute_diff` 必须是**只读**且**确定性**的（同样的声明 + 同样的 MA/台账状态 → 同样的 diff），这是「预览即所执行」成立的前提。

### 3.1 预览报告样例（目标输出）

```text
[预览] topic-lab/ada-pm · stage=dev
  agent        t            无变化   (agent-…s1exx @v2)
  agent        pm           修改     system, multiagent
  environment  ada-pm-env   修改     packages(+packaging)      ⚠ 存量 Session 需 upgrade 才生效
  知识库 02    条目         修改 1 · 新增 1 · 删除 1
     /standards/routing.md  修改
     /standards/new.md      新增
     /examples/old.md       删除（声明已移除）
  vault pm     凭证         新增 1 · 修改 1
     LLM_RELAY_API_KEY      新增   ⚠ 既有 Session 需新建
     DATAHUB_API_KEY        修改   (secret_value 指纹变化)
  孤儿         agent ada-pm-old   （台账有、声明已无）→ 将删除
  补登台账     environment ada-pm-env（MA 上已存在，台账未记录）
汇总：新增 2 · 修改 4 · 删除 2 · 补登 1 · 无变化 9
确认后执行请说「确认」，或 `build.py … --apply`（执行时重新计算，结果应与此预览一致）。
```

## 4. 各类资源的 diff 维度

| 资源 | 台账 key | desired 来源 | actual 来源 | 判「修改」 | 判「删除」 |
|---|---|---|---|---|---|
| Agent | `agent/<智能体>` | `agent_config()` | `GET /agents/{ma_id}` | system / skills / multiagent / metadata（已实现） | 台账有、声明无该包 |
| Environment | `environment` | `merge_environments`+build-config | `GET /environments/{ma_id}` 的 `config` | packages / env / networking / setup_script（子集比较，忽略服务端补充字段） | 台账有、声明无（整员工下线） |
| 知识库容器 | `memory_store/<root 序号>` | `knowledge.yaml` roots | 台账 ma_id → `GET` | 容器无「修改」 | 台账有、声明无该 root |
| 知识库条目 | `memory_entry/<库>:<path>` | `knowledge_entries()` | `list memories` 对比 `content_sha256`；台账 `fingerprint` 兜底 | 逐条 sha256 不同 | 台账有、声明无该 path |
| Vault 容器 | `vault/<智能体>` | 每智能体一个 | 台账 ma_id → `GET` | 无「修改」 | 台账有、声明无该智能体 |
| Vault 凭证 | `credential/<智能体>:<secret_name>` | `connections.yaml` | `list credentials` | 声明侧值指纹≠台账 `fingerprint` | 台账有、声明无该 secret_name |

### 4.1 官方文档确认的特殊规则

- **凭证**：密钥只写不读 → 用台账 `fingerprint`（`sha256(secret_value)` 前缀，不含明文）判变化，变化则 `POST /credentials/{id}` 只改 `secret_value`；`secret_name`/`mcp_server_url` 等结构字段**创建后锁定**，变化只能「删旧建新」（预览标「替换」）；既有 Session 感知不到**新增**凭证 → 预览告警「需新建 Session」。
- **Environment**：不做版本化，变更只影响之后创建的 Session → 预览统一提示「存量 Session 需 upgrade」；`setup_script`/`packages` 变化提示「新 Session 可能复用旧镜像」，不自动重建 Environment。
- **知识库条目**：分页拉取；写入统一 `batch_create(on_conflict=overwrite)`（analyst-env 已验证），删除单条 `DELETE`；预览列出将删除的 path。

## 5. 代码落点

build.py 已 ~700 行，拆模块，build.py 只保留主流程：

```text
scripts/
├── build.py            # 主流程：预览 / --apply
├── ma_api.py           # 方舟 HTTP 封装（现 ark_get/post/delete、find_by_name、分页）
├── ledger.py           # 台账读写（飞书多维表格，复用 registry.py 的 token/bitable 封装）
├── reconcile/
│   ├── __init__.py     # Action/Diff 数据结构、报告渲染、compute_diff 入口
│   ├── agent.py  environment.py  memory.py  vault.py
├── registry.py         # 原子能力注册表（已有）
└── pack_skills.py      # 已有
```

每个 reconcile 模块：`plan(desired, ledger_rows, ctx) -> [Action]`（只读）与 `apply(actions, ctx)`（执行 + upsert 台账）。

## 6. 实施步骤与验收（均需实测）

| 步 | 内容 | 验收 |
|---|---|---|
| 1 | 抽 `ma_api.py`、`reconcile/__init__.py`、`ledger.py`；build.py 行为不变 | 对 ada-pm 重构前后 `--plan` 输出一致 |
| 2 | 台账接入：对 ada-pm 现有 Agent/Environment/Vault/知识库做**首次认领补登** | 台账出现 ada-pm 全部资源行，ID 与 `created_ids.json` 一致 |
| 3 | environment：自动 diff + 原地更新 | 改 1 个包版本 → 预览「修改 packages」；执行后回读一致；再预览为空 |
| 4 | memory 条目：增/改/删 | 改 1 删 1 增 1 → 预览精确 3 条；执行后回读集合一致；台账同步 |
| 5 | vault 凭证：指纹更新/删除/替换 | 换值→修改；删 connection→删除；改 secret_name→替换；全程无明文输出 |
| 6 | agent 迁入 + 孤儿删除 | 声明删一个 sub 包 → 预览显示孤儿删除；确认后 MA 与台账均同步 |
| 7 | `--apply`（计算并执行）+ 可选 `--json` + SKILL.md/mapping.md 同步 + 打包 apply 到研发环境 | 研发助手对话式走完「预览→确认→执行」，且执行结果与预览一致 |
| 8 | 端到端：飞书传包 → 构建 →（改包再传）→ 预览只含变化项 | 两次预览差异与实际改动一致 |

**测试资源规则**：破坏性用例用 `_ui_test_api` 后缀的临时员工（独立 `business_line/employee`），资源 ID 记录在案，测完按精确 ID 清理，**不拿 ada-pm 正式资源做删除类实验**；台账里的测试行测完也要删除。

## 7. 风险与待实测项

| # | 项 | 处理 |
|---|---|---|
| 1 | 凭证 `fingerprint` 为 `sha256(明文)` 前缀，存飞书表格有被彩虹表撞库的理论风险（弱口令） | 指纹加盐：`sha256(business_line/employee/secret_name + 值)`，盐不含密钥；步骤 5 落实 |
| 2 | `list memories` 是否直接带 `content_sha256`（决定条目对比成本） | 步骤 4 先实测；不带则用台账 `fingerprint` 做快速对比，仅对变更条目 GET 校验 |
| 3 | 台账与 MA 漂移（人工在控制台改/删资源） | 预览阶段用台账 ID 去 MA `GET`：查不到标 `missing`（可重建）、内容与声明不符则按「修改」处理 |
| 4 | 台账表被误改结构 | 与注册表一致：结构/字段冻结，记录由构建器写；在记忆里登记 |
| 5 | 首次认领时命名冲突（别的业务方同名） | 认领前校验 MA 资源 `metadata.business_line/employee` 或名称前缀完全匹配；不匹配则报错不认领 |

## 8. 不在本方案范围

- 长期记忆库（`memory/stores.yaml`，6.5）与 `{{memory:}}`：仍待接，后续按同接口加 `reconcile/longterm_memory.py`；
- 会话创建参数（`vault_ids` 集合、`resources` 挂载）：由 Gateway / analyst-env 承接，台账 `vault` 行的 `ma_id` 可作为其输入；
- 并发控制、多人同时构建（D1 明确不考虑）。
