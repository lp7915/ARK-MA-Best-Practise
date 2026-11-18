<!-- 由 scripts/build_references.py 从《MA Agent 搭建交付规范》v1.5 生成，勿手改。 -->
> 来源：《MA Agent 搭建交付规范》v1.5。本文件只摘录该规范的对应章节，规则以规范原文为准；两者不一致时以规范为准。

## 2. 智能体包

**交付的基本单位是"智能体包"。** 一位**数字员工**由一个或多个智能体组成：对外有一个入口智能体（`main`），背后可以有若干被它引用的子智能体（`sub`）。每个智能体各交付一个独立的包；同一位数字员工的多个包放在同一个数字员工目录下：

```text
<业务线ID>/
└── <数字员工ID>/                       # 同一位数字员工的所有智能体
    ├── <智能体ID>/                    # 一个智能体包（可以是 main，也可以是 sub）
    │   ├── identity/
    │   │   ├── identity.md            #   角色、职责、边界（必须）
    │   │   ├── orchestration.md       #   工作流程与分工（可选）
    │   │   └── handoff.md             #   交接规则（可选）
    │   ├── knowledge/                 #   业务知识（目录名与内部结构为建议，可自定义，见 5.2）
    │   │   ├── standards/             #     生产与验收口径
    │   │   ├── templates/             #     业务内容模板
    │   │   ├── examples/              #     可复用案例（标准、边界、错误、回归）
    │   │   └── glossary.md            #     术语表
    │   ├── tools/                     #   外部能力契约：只写接口、用途、所需凭证类型
    │   ├── skills/                    #   可直接执行的封装能力
    │   │   └── <能力名>/
    │   │       ├── SKILL.md
    │   │       ├── prompts/
    │   │       ├── scripts/
    │   │       └── references/
    │   ├── io/                        #   输入输出契约（见 5.6）
    │   │   ├── README.md
    │   │   └── contracts/
    │   ├── memory/                    #   长期记忆（仅需要时设置，见 5.5）
    │   │   ├── stores.yaml
    │   │   └── <路径>/*.md
    │   ├── acceptance/                #   验收用例（见 9.2）
    │   │   └── cases.yaml
    │   ├── knowledge.yaml             #   声明哪些目录属于业务知识（见 5.2）
    │   ├── connections.yaml           #   外部系统与凭证声明（见 5.4），不含凭证值
    │   ├── change-set.yaml            #   仅增量交付时提供（见 2.4）
    │   └── registry/
    │       ├── agent.json             #   身份、版本、角色、可见范围（见 2.3）
    │       ├── agents.json            #   引用的子智能体，仅 role=main 才有（见 2.3）
    │       ├── skills.json            #   引用的可复用能力（见第 6 章）
    │       ├── knowledge.json         #   引用的共享知识与模板，有则放（见 6.3）
    │       ├── tools.json
    │       ├── environment.json       #   运行环境需求（见 5.3）
    │       └── version_mapping.md     #   人可读的版本说明
    └── <另一个智能体ID>/               # 同一位数字员工的其他智能体，结构相同
```

不适用的目录可以省略，但 `identity/identity.md` 与 `registry/agent.json` 必须存在。**所有智能体包结构完全相同**，没有"数字员工包"和"子智能体包"之分，区别只在 `registry/agent.json` 里的 `role` 和是否引用了别的智能体。

### 2.3 智能体的角色与引用

一位数字员工对外只有一个入口。每个智能体包在 `registry/agent.json` 里声明自己的**身份、角色**和**可见范围**：

```json
{
  "id": "zhilan.hotspot-team.pm",
  "version": "1.2.0",
  "role": "main",
  "visibility": "public",
  "owner": { "team": "智蓝数据服务部", "primary": "张三", "backup": "李四" },
  "description": "面向用户的入口：理解需求、分派任务、汇总结果"
}
```

| 字段 | 取值与规则 |
|---|---|
| `id` | 智能体完整标识（2.1），必须与路径一致 |
| `version` | 语义化版本，规则见 7.1；每个智能体包**独立版本** |
| `role` | `main`：数字员工的入口，**可以引用子智能体**，**不能被别的智能体引用**；`sub`：被引用的子智能体，**不能再引用别的智能体** |
| `visibility` | `public`：生产环境可以面向所有用户；`internal`：**生产环境只对内部指定范围开放**，不得配置成"不限使用范围"（见下）。**`role: sub` 必须是 `internal`**（子智能体在线上一定是内部的）；`role: main` 可以是 `public`，也可以是 `internal`（例如只面向内部员工的数字员工） |

#### 引用子智能体：`registry/agents.json`（仅 `main`）

`main` 引用哪些子智能体，写在 `registry/agents.json` 里。**它和引用 Skill 的 `registry/skills.json` 是同一种写法：指明引用谁、接受哪个版本范围**，只是多了一个别名：

```json
[
  { "id": "hotspot", "range": "^1.0.0", "alias": "hotspot" },
  { "id": "insight", "range": "^2.0.0", "alias": "insight" }
]
```

| 字段 | 说明 |
|---|---|
| `id` | 被引用的子智能体，同一位数字员工内的智能体 ID（2.1）；必须是 `role: sub` |
| `range` | 接受的版本范围，具体锁定到哪个版本由平台在发布时决定（与 6.3 的 Skill 引用一致） |
| `alias` | `main` 在 `orchestration.md` 里称呼它的名字 |

- 只有 `role: main` 的包才有这个文件；`sub` 不得有（不能再引用别人）；
- 对 Skill 和对子智能体的引用，增量时用同一套登记方式（见 2.4）：新增、修改版本范围、移除，都按"记录"处理；
- **`registry/agent.json` 只放身份信息**（`id`、`version`、`role`、`visibility`、`owner`、`description`），不放任何引用。

**一位数字员工里有且仅有一个 `role: main` 的智能体**（有多个对外入口的，请拆成多位数字员工）。

`role` 与 `visibility` 是两个独立的字段：

| | `visibility: public` | `visibility: internal` |
|---|---|---|
| `role: main` | 面向所有用户的数字员工 | 只面向内部指定人群的数字员工 |
| `role: sub` | **不允许** | 子智能体（线上一定是这一种） |

#### 为什么要显式声明 role 和 visibility

- **层数不会超限**：MA 的多智能体只展开一层。`main` 只能引用 `sub`、`sub` 不能再引用别的智能体，平台在**交付阶段**就能检查，不需要等到运行时出问题；
- **子智能体可以独立开发、调试**：`sub` 也是完整的智能体，可以单独配置一个 bot 用于对话和任务调试，验证没问题后，再被 `main` 引用并生效；
- **线上不暴露子智能体**：`sub` 的 `visibility` 固定为 `internal`，平台在交付阶段检查。用户只通过 `main` 触达 `sub`；
- **`internal` 在生产环境不得"不限使用范围"**：不论 `main` 还是 `sub`，`internal` 的智能体发布到生产前，平台检查它的 bot 可用范围（白名单）**不为空**，不满足则不予发布。`sub` 的 bot 只能面向研发人员，或者干脆不配对话入口；`internal` 的 `main` 则限定在内部指定的人群或部门；
- 开发和测试环境不受此限制，方便你们调试。

#### 开发流程

```text
sub 智能体：独立开发 → 用自己的 bot 调试 → 单独验收 → 发布（得到一个版本）
                                                         ↓
main 智能体：在 registry/agents.json 里引用这个版本 → 集成验收 → 发布 → 线上用户只通过 main 触达 sub
```

- 子智能体发布前，在 dev、staging 阶段可以被 main 引用它的"候选"版本，用于联调；**生产环境只能引用"已发布"的版本**（见 6.2、7.3）；
- main 引用子智能体时**固定版本**：子智能体之后发布新版本，不会自动改变已经发布的 main。要纳入新版本，按 2.4 的规则处理。

#### 资源怎么在运行时生效

资源按平台层级分两类，**构建时的处理不同**：

| 资源 | 属于哪一层 | 平台怎么处理 |
|---|---|---|
| Skill、外部工具（MCP）、提示词 | **智能体自己** | 各智能体各用各的，互不合并 |
| 业务知识、长期记忆库、外部系统凭证、运行环境 | **一次会话，整位数字员工共享** | 构建时，把 main 和它引用的全部 sub（已锁定版本）声明的这些资源**合并**到同一次会话里 |

合并规则：

- **并集，同名不覆盖**：不同包里同名的知识目录或记忆库各自独立，平台自动加所属智能体的前缀以区分；
- **凭证**：凭证值由提供人单独交给平台，存入这位数字员工自己的凭证库；包里只声明。同一个 `secret_name`、同样的域名在多个包里声明的，合并为一条；`secret_name` 相同但域名或类型不同，构建失败并指出冲突来源。**子智能体单独调试时用自己的凭证**，被 main 引用后用这位数字员工的凭证库，所以凭证值在 main 引用时需要确认一次；
- **运行环境**：各包的依赖合并成一份，合并后必须自洽（不能同时要求 `numpy<2` 与 `numpy>=2`），冲突时构建失败，并指出是哪两个包冲突；
- **容量**：合并后的总数计入平台限制（见《MA Agent 搭建容量限制说明》）。引用的子智能体越多，知识目录和记忆库的总数越容易触及上限，请在规划时一起计算；
- **不做按智能体的隔离**：知识、记忆库、凭证、文件系统属于整次会话，main 和 sub 都能访问；长期记忆库的读写权限对所有智能体一致。需要严格隔离的敏感内容，请拆成独立的数字员工；
- **提示词各自独立**：每个智能体的提示词单独拼接（见 5.1），不互相合并；子智能体的占位符只能引用**自己包里**声明的资源（见 5.7）。

### 2.4 增量交付：基线与最小增量

智能体上线后，业务会持续演进：新增一个子智能体、只调整某一个智能体的提示词、补几个知识文件。这类变更**不需要重新交付完整的包**，可以只交付变化的部分。首次交付必须是完整包。

**所有智能体包的增量机制相同，各自独立版本。** 改哪个智能体，就在哪个智能体的包里交付增量：

| 你想改的 | 在哪个包里交付增量 |
|---|---|
| 某个智能体（main 或 sub）自己的提示词、Skill、知识、记忆、连接、运行环境 | **该智能体的包** |
| main 引用了哪些子智能体、引用哪个版本范围 | **main 的包**的 `registry/agents.json` |
| 新增一个子智能体 | ① 先交付并发布新智能体的完整包（`role: sub`）；② main 的包里增加对它的引用 |

#### 增量包是什么

增量包使用与完整包相同的目录结构，**只包含本次新增、修改的内容**，另在根目录提供 `change-set.yaml`。**`change-set.yaml` 是本次变更的唯一清单：新增、修改、删除了什么，都要在这里显式登记**，不能靠"文件出现在包里"来暗示：

```yaml
# change-set.yaml：给 main 智能体 pm 新增引用子智能体 hotspot（版本范围 ^1.0.0），并更新提示词
change_id: 20261110-add-hotspot        # 本次变更的唯一编号，由业务方生成
base_version: 1.2.0                    # 本次变更基于的、平台已发布的版本
new_version: 1.3.0                     # 变更后的版本号，按 7.1 规则确定
note: 新增引用热点分析子智能体，并让主智能体分派热点类需求

add_entries:                           # 新增的记录
  - "agents:hotspot"                   # 新增引用子智能体 hotspot
update_entries:                        # 修改的记录（整条替换）
  - "prompt:identity"                  # 提示词有改动
remove_entries: []                     # 删除的记录

add_files: []                          # 新增的文件（相对包根的路径）
update_files:                          # 修改的文件
  - acceptance/cases.yaml
remove_files: []                       # 删除的文件
```

三类各有对应的"新增 / 修改 / 删除"，没有就写 `[]` 或省略。

#### 记录与文件怎么登记

**记录**：指一类内容里的一条条声明。写法是 `<类型>:<名称>`：

| 类型 | 对应的文件与键 | 说明 |
|---|---|---|
| `skills` | `registry/skills.json`，按能力 `id` | 引用的 Skill，要指明版本范围 |
| `tools` | `registry/tools.json`，按能力 `id` | 引用的外部工具，要指明版本范围 |
| `agents` | `registry/agents.json`，按子智能体 `id`（仅 `main`） | **引用的子智能体，要指明版本范围，和 `skills` 是同一种写法** |
| `knowledge` | `knowledge.yaml`，按 `path` | 自有知识目录 |
| `shared_knowledge` | `registry/knowledge.json`，按 `as` | 引用注册表里的共享知识、模板（6.3），要指明版本范围 |
| `connections` | `connections.yaml`，按连接 `name` | 外部连接 |
| `memory` | `memory/stores.yaml`，按记忆库 `name` | 长期记忆库 |
| `prompt` | `identity/` 下的提示词文件，**一个包只有一条**，名称固定为 `identity` | 提示词是一个整体，见下方说明 |

- `add_entries`：基线里**没有**的记录，增量里要写出这一条的完整内容；
- `update_entries`：基线里**已有**的记录，增量里写**整条**新内容，整条替换基线里那一条（不是只改其中一个字段）；
- `remove_entries`：删除基线里的记录，增量里不需要再写。

**提示词（`prompt:identity`）要特别注意：三个文件必须成套给出。** 提示词由 `identity.md`、`orchestration.md`、`handoff.md` 按固定顺序拼接成一份系统提示词（见 5.1），拼接时某一部分缺失，那一段就会消失。所以只要登记了 `prompt:identity`（不论新增还是修改），**增量里就要把包里存在的全部提示词文件一并给出，没有改动的文件也要原样给出**，不能只给改了的那一个。平台是用你们给出的这一套重新拼接，不会拿基线里的旧文件补进去。

- 原来没有 `handoff.md`、本次新增了：登记 `update_entries: ["prompt:identity"]`，并给出 `identity.md`、`orchestration.md`、`handoff.md` 三个文件；
- 原来有 `handoff.md`、本次要去掉：登记 `update_entries: ["prompt:identity"]`，只给 `identity.md`、`orchestration.md`，**缺了的 `handoff.md` 视为被删除**；
- `identity.md` 是必须的，不能缺。

**文件**：指除提示词、清单类内容以外的文件——知识文件、Skill 目录下的文件、`acceptance/cases.yaml`、`registry/environment.json`、`registry/agent.json` 等。上表里各类记录（含提示词）的变化已经由 `*_entries` 表达，**不需要再在 `*_files` 里登记**：

- `add_files`：基线里没有的文件，写出完整内容；
- `update_files`：基线里已有的文件，写**改动后的完整文件**，整个替换；
- `remove_files`：删除基线里的文件。

`registry/agent.json` 只放身份信息（`id`、`version`、`role`、`visibility`、`owner`、`description`），改它就是普通的 `update_files`，**不含任何引用**；引用都在 `registry/skills.json`、`registry/tools.json`、`registry/agents.json` 里，由 `*_entries` 登记。

增量包里的实际内容必须与这份登记**完全一致**：登记了但包里没有、包里有但没登记、登记的是新增而基线里已存在（或登记的是修改而基线里不存在），一律退回。

#### 规则

1. **省略不是删除**。增量里没有出现的文件、记录，沿用 `base_version` 的内容；**提示词除外**——提示词按套给出，没给出的提示词文件视为被删除（见上）；
2. **新增、修改、删除都要显式登记**，登记与增量包里的实际内容必须一致（见上）。移除子智能体引用（`remove_entries` 里有 `agents:<子智能体ID>`）时，必须同时更新 main 的提示词，去掉对它的分派说明（平台只检查提示词里是否还出现该别名，仍出现则退回）；新增子智能体引用时，同样必须在提示词里加上分派说明；
3. **删除资源声明时，用到它的地方要一并处理**：`remove_entries` 删掉一个 Skill、连接、知识目录或记忆库，而包里的提示词（占位符）或其他声明仍在使用它，则退回；
4. **基线必须是最新的已发布版本**。`base_version` 与该包当前最新已发布版本不一致（别人先发布了新版本），退回，请基于最新版本重新交付；平台会告知差异；
5. **同一次变更只生效一次**。`change_id` 相同、内容也相同的重复提交视为同一次变更，不会重复生效；`change_id` 相同但内容不同，退回；
6. **`role` 和 `visibility` 的变更要显式**：它们在 `registry/agent.json` 里，登记 `update_files: [registry/agent.json]`；修改 `role` 或 `visibility` 视为不兼容变更（升主版本），并须重新通过 2.3 的引用检查（尤其 `sub` 必须是 `internal`）；
7. **子智能体自己的变更不在 main 的增量里**：子智能体的内容（提示词、Skill、知识、连接等）变化，走**它自己包的增量**，发布后得到新版本；main 只通过 `agents.json` 的版本范围去引用它，不重复交付它的内容（见下）；
8. **影响范围由平台核算**：
   - 改了 **sub 智能体**：发布该智能体的新版本，然后找出引用它的 main，逐个评估；
   - 改了 **main 智能体**自己：只更新这个智能体；
   - 环境、凭证、知识、记忆库属于会话级资源，变化会影响整位数字员工（含它引用的全部 sub），平台会在回执中写明；
9. **提交、构建、接受、发布是四个动作**。提交增量不等于发布；发布沿用第 7.3 节的灰度流程，进行中的任务保持原版本。

#### 子智能体发布新版本后，main 怎么办

**子智能体自己的变更，永远走它自己包的增量**，发布后得到一个新版本。main 引用子智能体和引用 Skill 一样，是"引用谁 + 接受哪个版本范围"（`registry/agents.json`），main 的包里不会出现子智能体的内容。

main 引用时**固定了版本**，子智能体发布新版本不会自动影响已发布的 main。是否纳入新版本，按版本规则（同 6.2）：

| 子智能体的变更 | 对引用它的 main |
|---|---|
| 修订（行为兼容的修复） | 在 `range` 范围内，平台评估后可重新构建并锁定新版本，在回执中请你们确认；main 的包**不需要交付任何文件** |
| 次要（向后兼容的新增） | 在 `range` 范围内的，同上；是否纳入由你们在回执中决定 |
| 主要（不兼容） | **不会自动纳入**。main 的负责人评审后，把 `registry/agents.json` 里这条引用的版本范围改掉（登记 `update_entries: ["agents:<子智能体ID>"]`），作为 main 自己的一次增量交付 |

main 的版本随之变化，规则见 7.1。

#### 常见变更需要交付什么

每一行都写明**增量包里放什么**，以及 **`change-set.yaml` 里怎么登记**。下面以子智能体 `hotspot`、主智能体 `pm` 为例（`pm` 的提示词有 `identity.md`、`orchestration.md`、`handoff.md` 三个文件）：

| 你想做的事 | 在哪个包 | 增量包里放 | `change-set.yaml` 登记 |
|---|---|---|---|
| 改 `hotspot` 的提示词 | `hotspot` 的包 | `identity/` 下**全部**提示词文件（`identity.md` 等，没改的也原样给出） | `update_entries: ["prompt:identity"]` |
| 给 `hotspot` **新增**引用一个 Skill | `hotspot` 的包 | `registry/skills.json` 里这条新记录（含版本范围） | `add_entries: ["skills:platform.chart"]` |
| 给 `hotspot` **新增**一个自有 Skill | `hotspot` 的包 | `skills/<名>/` 下的全部文件；`registry/skills.json` 里这条新记录 | `add_entries: ["skills:<名>"]`；`add_files: [skills/<名>/SKILL.md, …]` |
| 改 `hotspot` 自有 Skill 的脚本 | `hotspot` 的包 | `skills/<名>/scripts/xxx.py`（完整文件） | `update_files: [skills/<名>/scripts/xxx.py]` |
| 调整 Skill 的版本范围 | 引用它的那个包 | `registry/skills.json` 里这条记录（整条） | `update_entries: ["skills:platform.chart"]` |
| **删除**一个 Skill 引用 | 引用它的那个包 | 不需要放文件 | `remove_entries: ["skills:old-skill"]`（自有 Skill 的文件另在 `remove_files` 列出） |
| **新增**一个连接 | 用它的那个包 | `connections.yaml` 里这条新记录 | `add_entries: ["connections:crm-api"]` |
| 改一个连接（如换域名） | 用它的那个包 | `connections.yaml` 里这条记录（整条） | `update_entries: ["connections:crm-api"]` |
| 改运行环境依赖 | 对应的包 | `registry/environment.json`（完整文件） | `update_files: [registry/environment.json]` |
| **新增**一个知识目录 | 对应的包 | 目录里的知识文件；`knowledge.yaml` 里这条新记录 | `add_entries: ["knowledge:业务口径"]`；`add_files: [业务口径/统计口径.md, …]` |
| 改一个知识文件 | 对应的包 | 该文件（完整文件） | `update_files: [业务口径/统计口径.md]` |
| 改 `pm` 的提示词 | `pm` 的包 | `identity/` 下**全部**提示词文件（三个都给，没改的原样给） | `update_entries: ["prompt:identity"]` |
| **新增**引用一个子智能体 | `pm` 的包 | ① 先交付并发布该子智能体的完整包；② `registry/agents.json` 里这条新记录（含版本范围）；**全部**提示词文件（加分派说明）；`acceptance/cases.yaml` | `add_entries: ["agents:insight"]`；`update_entries: ["prompt:identity"]`；`update_files: [acceptance/cases.yaml]` |
| **移除**一个子智能体引用 | `pm` 的包 | **全部**提示词文件（去掉分派说明）；`acceptance/cases.yaml`（去掉相关用例）；子智能体的包本身保留 | `remove_entries: ["agents:hotspot"]`；`update_entries: ["prompt:identity"]`；`update_files: [acceptance/cases.yaml]` |
| 让 `pm` 改用某子智能体的另一个版本范围 | `pm` 的包 | `registry/agents.json` 里这条记录（整条） | `update_entries: ["agents:hotspot"]` |
| 改 `role` 或 `visibility` | 对应的包 | `registry/agent.json`（完整文件） | `update_files: [registry/agent.json]`；升主版本 |

> 各类**记录**（含提示词）只用 `*_entries` 登记，不用重复写 `*_files`；`registry/agent.json` 只放身份信息，改它就是普通的 `update_files`。

**完整例子一：给子智能体 `hotspot` 新增引用 Skill `platform.chart`，同时调整另一个 Skill 的版本范围、并删除一个不再用的连接**

这是 `hotspot` **自己包**的增量，只有两个文件（删除 `old-crm` 连接不需要放内容，只在 `change-set.yaml` 里登记）：

```text
change-set.yaml
registry/skills.json        # 含 platform.chart（新增）和 platform.report-cover（修改）两条记录
```

```yaml
# change-set.yaml（hotspot 的包）
change_id: 20261112-hotspot-chart
base_version: 1.0.0
new_version: 1.1.0                     # 新增能力，次版本
note: 引用 platform.chart；report-cover 升级到 ^1.3.0；去掉不再使用的 old-crm 连接

add_entries:
  - "skills:platform.chart"            # 新增
update_entries:
  - "skills:platform.report-cover"     # 修改：版本范围 ^1.2.0 → ^1.3.0
remove_entries:
  - "connections:old-crm"              # 删除

add_files: []
update_files: []
remove_files: []
```

```json
// registry/skills.json —— 只写本次变化的两条记录，每条写完整
[
  { "id": "platform.chart",        "range": "^1.0.0" },
  { "id": "platform.report-cover", "range": "^1.3.0" }
]
```

这一次变更只动了记录（`registry/skills.json`、`connections.yaml` 里的条目），它们由 `*_entries` 覆盖，所以 `add_files`、`update_files`、`remove_files` 都是空的。具体来说：新增了 `platform.chart`（基线里不能已有）；修改了 `platform.report-cover`（基线里必须已有）；删除了 `old-crm`（基线里必须已有，且 `hotspot` 的提示词里不能还在使用它）。

发布后得到 `hotspot` 1.1.0。引用它的 `pm` 的 `range` 是 `^1.0.0`，在范围内，所以平台评估后重新构建并在回执里请你们确认，`pm` 的包不用交付文件。

**完整例子二：给主智能体 `pm` 新增引用一个子智能体 `insight`**

这个变更要分**两步**，涉及两个包：

**第 1 步：先交付并发布 `insight` 自己的完整包**（`insight` 是首次交付，不是增量，没有 `change-set.yaml`）。它的 `registry/agent.json`：

```json
{
  "id": "zhilan.hotspot-team.insight",
  "version": "1.0.0",
  "role": "sub",
  "visibility": "internal",
  "owner": { "team": "智蓝数据服务部", "primary": "张三", "backup": "李四" },
  "description": "洞察生成。适用：…；不适用：…"
}
```

`insight` 发布后，得到 `1.0.0`（`role: sub`，`visibility: internal`，没有 `registry/agents.json`，因为 `sub` 不能再引用别人）。

**第 2 步：在 `pm` 的包里增量交付**，让 `pm` 引用它。增量包有六个文件：

```text
change-set.yaml
registry/agents.json           # 只写新增的这一条引用记录
identity/identity.md           # 提示词三件套：没有改动，但必须原样给出
identity/orchestration.md      # 提示词：加了对 insight 的分派说明
identity/handoff.md            # 提示词三件套：没有改动，但必须原样给出
acceptance/cases.yaml          # 完整文件，加了分派到 insight 的用例
```

```yaml
# change-set.yaml（pm 的包）
change_id: 20261115-add-insight
base_version: 1.3.0
new_version: 1.4.0                     # 新增子智能体引用，次版本
note: 新增引用洞察生成子智能体 insight，并让 pm 分派洞察类需求

add_entries:
  - "agents:insight"                   # 新增：基线里 pm 还没有引用 insight
update_entries:
  - "prompt:identity"                  # 提示词整套更新（orchestration.md 有改动，另外两个原样带上）
remove_entries: []

add_files: []
update_files:
  - acceptance/cases.yaml              # 加分派用例
remove_files: []
```

`registry/agents.json` 里新增的这条记录，**指明引用谁、接受哪个版本范围**，和引用 Skill 的写法一致：

```json
[ { "id": "insight", "range": "^1.0.0", "alias": "insight" } ]
```

`identity/orchestration.md` 里要加上分派说明，平台会检查是否提到了别名 `insight`：

```text
## 分派规则
- 用户要生成洞察报告时，交给 insight；
```

**提示词三个文件都要给**：`identity.md` 和 `handoff.md` 这次没有改动，也必须原样放进增量包。平台是用你们给出的这一套重新拼接成系统提示词的，缺了哪一个，那一段就会从系统提示词里消失。

平台会检查：`insight` 存在、已发布、`role` 是 `sub`、范围内有已发布的版本；`pm` 的提示词里提到了 `insight`；`insight` 自己没有再引用别人。通过后 `pm` 发布 1.4.0，生产环境用户仍然只通过 `pm` 对话。

**完整例子三：给主智能体 `pm` 移除对子智能体 `hotspot` 的引用**

增量包在 `pm` 的包里，有五个文件：

```text
change-set.yaml
identity/identity.md           # 提示词三件套：没有改动，原样给出
identity/orchestration.md      # 提示词：去掉了对 hotspot 的分派说明
identity/handoff.md            # 提示词三件套：没有改动，原样给出
acceptance/cases.yaml          # 完整文件，去掉了分派到 hotspot 的用例
```

```yaml
# change-set.yaml（pm 的包）
change_id: 20261120-remove-hotspot
base_version: 1.4.0
new_version: 2.0.0                     # 移除子智能体引用，不兼容变更，主版本
note: 热点分析业务下线，移除对 hotspot 的引用

add_entries: []
update_entries:
  - "prompt:identity"                  # 提示词整套更新
remove_entries:
  - "agents:hotspot"                   # 删除：基线里 pm 已引用 hotspot；registry/agents.json 里不需要再写

add_files: []
update_files:
  - acceptance/cases.yaml              # 去掉分派到 hotspot 的用例
remove_files: []
```

平台会检查：提示词里**不能再出现** `hotspot` 这个别名，出现则退回（否则主智能体会继续把任务派给一个已经不引用的子智能体）。

另外，`acceptance/cases.yaml` 里 `agents` 写了 `hotspot` 的用例，**平台不会自动检查**，需要你们自己同步去掉，否则这些分派用例在验收时会失败。

注意几点：

- **移除的只是 `pm` 对 `hotspot` 的引用**。`hotspot` 自己的包和它在 MA 上的 Agent 都保留，不会被删除。想让 `hotspot` 彻底下线，要单独走"能力下线"流程（见 6.2），并且要求没有任何 `main` 还在引用它；
- 版本升**主版本**：因为 `pm` 对外能做的事变少了；
- `hotspot` 声明的知识、记忆库、连接、运行环境依赖，会随引用一起从这位数字员工的会话里移出，平台会在回执里列出。

### 2.5 平台的构建回执

每次构建（首次交付或增量）后，平台把结果回给你们确认。回执至少包含下面这些，**区分"你们写的"和"平台定的"**：

| 内容 | 说明 |
|---|---|
| 提交标识与版本 | 交付内容的摘要；增量的 `change_id`、`base_version`、`new_version`；提交的压缩包（链接、SHA-256 核对结果、解压与目录检查结果，见 2.6） |
| 智能体清单 | 数字员工的 `main` 与每个 `sub`（含它锁定的版本、`role`、`visibility`），以及各自的 Skill、工具；会话级的知识、记忆库、连接、运行环境按合并后的最终结果列出，并标明各自来自哪个包 |
| 完整系统提示词 | 每个智能体：你们写的原文、每个占位符替换后的结果、拼接后的完整提示词（见 5.7） |
| 依赖的实际版本 | `environment.json` 里的版本下限最终解析成的实际版本 |
| 可复用能力的锁定版本 | 每个智能体引用的每个能力（含子智能体）最终锁定到哪个版本 |
| 模型与环境 | 平台选定的模型、运行环境、任务时长与网络范围 |
| 知识与记忆库 | 各知识目录和记忆库的落地情况、读写权限 |
| 合并检查 | 会话级资源合并后的冲突检查结果（同名、凭证、依赖版本、容量） |
| 验收结果 | 每个用例的结论（见 9.2） |
| 状态 | 构建失败则给出失败原因和位置；成功则说明处于测试、灰度还是已发布 |

> 动态外部依赖（外部服务、可写记忆库、外部数据）无法完整冻结快照，回执会写明访问时点和限制，不保证事后可以完全重放同一次运行。

### 2.6 智能体包怎么交付：压缩包 + 公网链接

每个智能体包打成**一个压缩包**，把**公网可访问的下载链接**和它的 **SHA-256** 提交给平台。首次交付的完整包、增量交付的增量包（2.4）都一样。

#### 压缩包命名

```text
<业务线ID>-<数字员工ID>-<智能体ID>-<版本>.zip
例：zhilan-hotspot-team-pm-1.2.0.zip
```

- `<版本>` 是这次交付的版本：完整包取 `registry/agent.json` 的 `version`，增量包取 `change-set.yaml` 的 `new_version`；
- **一个版本只对应一个压缩包**。版本发布后内容不可变（6.2），要改就升版本、出新压缩包；
- ID 本身可以含连字符，平台**不靠文件名拆分**。完整包读取包内的 `registry/agent.json` 核对；增量包没有 `agent.json`（只交变化的文件），改为读取 `change-set.yaml` 并与基线核对（见下方"平台怎么处理"）。

#### 压缩包里是什么

解压后顶层是 `<业务线ID>/<数字员工ID>/<智能体ID>/` 三级目录，里面就是第 2 章描述的智能体包：

```text
zhilan-hotspot-team-pm-1.2.0.zip
└── zhilan/                          # 业务线 ID
    └── hotspot-team/                # 数字员工 ID
        └── pm/                      # 智能体 ID
            ├── identity/
            ├── registry/
            ├── knowledge/ …         # 其余内容见第 2 章
            └── change-set.yaml      # 仅增量包有（2.4）
```

- 压缩包里**只有这一个顶层目录**，三级目录名必须与 `registry/agent.json` 的 `id` 一致；
- **一个压缩包只放一个智能体**。同一位数字员工的多个智能体（`main` 和各 `sub`），各自一个压缩包、各自一个版本；
- 增量包的目录结构相同，只是里面只有本次变化的文件和 `change-set.yaml`；**增量包不需要包含 `registry/agent.json`**（没有改动身份信息时）；
- 不得包含：密钥与凭证、缓存与临时文件（如 `__pycache__`、`.DS_Store`、虚拟环境）、符号链接；
- 使用 ZIP 格式，文件名使用 UTF-8。

#### 提交什么

| 项 | 说明 |
|---|---|
| 压缩包的公网链接 | **不需要登录**就能下载，**永久有效**：不设有效期，也不要删除源文件 |
| SHA-256 | 压缩包的 SHA-256（十六进制）。生成方法：macOS 用 `shasum -a 256 <文件>`，Linux 用 `sha256sum <文件>` |

#### 平台怎么处理

检查分成两个阶段，**增量包和完整包的区别只在第二阶段**：

**第一阶段：形式检查**（对压缩包本身，完整包和增量包相同）

1. 按链接下载压缩包；
2. 核对 SHA-256，不一致则退回（说明下载内容与你们提交的不是同一份）；
3. 安全解压：不允许路径穿越（`..`）、绝对路径、符号链接，出现则退回；
4. 检查**压缩包文件名**与**顶层三级目录**是否一致，且文件名里的 `<业务线ID>-<数字员工ID>-<智能体ID>` 与三级目录拼起来相同；
5. 检查不含密钥、缓存与临时文件。

**第二阶段：内容检查**（对"完整的包"）

- **完整包**：直接对它做第 9 章的交付检查，其中 `registry/agent.json` 的 `id` 必须与三级目录一致，`version` 必须与文件名中的版本一致；
- **增量包**：先按 2.4 的规则与基线合并成**完整包**，**对合并后的完整包**做第 9 章的交付检查。增量包自己要核对的只有：`change-set.yaml` 存在，`base_version` 是该智能体最新已发布版本，`new_version` 与文件名中的版本一致，登记与包内内容一致（2.4）。

**版本号怎么回填**：增量包里的版本只写在 `change-set.yaml` 的 `new_version`。平台合并时**自动把合并后完整包的 `registry/agent.json` 里 `version` 更新为 `new_version`**，业务方不需要、也不应该手动改 `agent.json` 的 `version`。只有要改 `role`、`visibility`、`owner`、`description` 等其他字段时，才在增量包里带上 `registry/agent.json`（登记 `update_files`），此时包内的 `version` 字段如果写了，必须等于 `new_version`，不一致则退回。

任何一步失败都会退回并说明原因。通过后进入第 9 章的后续验收；平台会留存取回的压缩包（以及合并后的完整包），用于下一次增量交付时还原基线（2.4）。

同一个版本重复提交：该版本**已发布**的，内容必须与已发布的一致（SHA-256 相同），不一致则退回，请升版本；**尚未发布**的，以最新一次提交为准。

#### 暂时没有包管理平台时：用 Media Storage 生成公网链接

目前没有专门的包管理平台。可以先用中台的 **Media Storage** 能力把本地压缩包转成公网链接，对应的技能是 `blueai-media-storage-skill`（在技能市场里）：

1. 安装该技能，向平台申请 API Key（Key 只用于上传，**不要写进智能体包**）；
2. 用它的"本地文件上传"能力上传压缩包，返回结果里的 `file_url` 就是公网链接；
3. **上传后必须验证**：用不带任何登录信息的方式下载一次（例如浏览器无痕窗口，或 `curl -L -o test.zip "<链接>"`），确认能下载，并且下载文件的 SHA-256 与本地一致，再提交；
4. 链接的保留期以 Media Storage 团队的说明为准。**如果发现链接会过期，请联系平台，不要提交会过期的链接**。

> **注意：公网链接意味着知道链接的人都能下载。** 智能体包里有你们的提示词和业务知识，请不要把链接发到公开渠道；包里本来就不允许有密钥和凭证（第 8 章）。

以后有专门的包管理平台，会改成在平台上直接提交，命名规则不变，届时本节更新。

#### 其他需要公网链接的材料

除智能体包以外，如果还有材料**暂时没有平台管理、但需要先把本地文件转成公网链接**才能交给平台（例如较大的知识文件、验收样例附件），也可以暂时用同样的方式（Media Storage）转成公网链接，验证方法与注意事项同上。

---
