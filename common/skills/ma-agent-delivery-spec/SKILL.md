---
name: ma-agent-delivery-spec
description: 按《MA Agent 搭建交付规范》v1.5 新建、修改、检查、打包一个"智能体包"（数字员工的一个 main 或 sub 智能体）。当用户要搭建/新增/改动火山方舟 Managed Agents(MA) 底座上的数字员工或子智能体、要写 identity/knowledge/registry/change-set、要判断某个目录能不能交付、要把包打成压缩包并生成公网链接与 SHA-256、要准备验收用例与交付检查单、或问"规范里 X 该怎么写/允不允许"时使用。产出必须符合规范的目录结构、命名、增量登记与验收要求。
---

# ma-agent-delivery-spec：MA 智能体包交付规范

这是《MA Agent 搭建交付规范》v1.5 的**执行版**。规范原文是唯一事实源，本 skill 把它按主题拆成
`references/`，并给出按顺序执行的作业流程。**规则细节以 `references/` 为准；references 与规范原文
不一致时，以规范原文为准。**

## 能力边界（先读）

- 本 skill **只覆盖业务方要交付的东西**：目录、文件格式、命名、增量登记、压缩包、验收。
  平台如何在 MA 上落地（资源命名、元数据、构建流水线、注册表实现）见平台内部文档，
  **不要给业务用户展开**。
- 本 skill **不做**：调用 MA / 注册表 / Media Storage 的接口、上传文件、发布；
  这些由用户或平台执行，本 skill 只告诉他"要准备什么、怎么检查"。
- 规范里的**容量限制目前全部有效**（见 `references/07-capacity.md`），不要告诉用户"已经放开"。

## 什么时候用哪些文件

按任务类型只读需要的部分，不要一次读完：

| 任务 | 先读 | 再读（按需） |
|---|---|---|
| 从零搭一个智能体包 | `references/01-basics.md` | `02`（main/sub 划分）、`03`（各文件怎么写） |
| 新增一个子智能体、改 main 的引用 | `references/02-roles-and-increments.md` | `01`（标识规则） |
| 只改包里的某个文件（增量交付） | `references/02-roles-and-increments.md` 的 2.4 | — |
| 写提示词 / knowledge / environment / connections / memory / io | `references/03-formats.md` | `02`（占位符、角色） |
| 引用 Skill、工具、共享知识、查注册表 | `references/04-capabilities.md` | — |
| 准备验收用例、过交付检查单 | `references/05-acceptance.md` | `03`（io 契约） |
| 打包、生成链接、算 SHA-256 | `references/02-roles-and-increments.md` 的 2.6 | — |
| 判断目录结构、工作空间归属、安全红线 | `references/06-workspace-security.md` | — |
| 容量、能不能再拆、超过上限怎么办 | `references/07-capacity.md` | — |

## 作业流程

### A. 新建一个智能体包

0. **先明确业务架构背景**：这条业务线的数字员工有几个角色、谁当入口（`main`）、谁是被引用的子智能体（`sub`），先落到一份业务架构背景上（见 `references/01-basics.md` 的「0. 开发前」）。这决定有几个包、谁 main 谁 sub，是后续步骤的前提。业务架构背景的完整示例见 `examples/ADA-ARCHITECTURE-AI-v0.7.20.md`（ADA：PM 主 Agent + 领域/策略/通用三类子 Agent + Validator 作 Skill）。
1. **确认身份**：业务线 ID、数字员工 ID（3–24 位）、智能体 ID（1–24 位；均小写字母/数字/连字符）。
   用户没给就问，不要自己编。数字员工下**有且仅有一个 `role: main`**。
2. **建目录**：`<业务线ID>/<数字员工ID>/<智能体ID>/`，按 `references/01-basics.md` 的目录树建。
   必须有的是 `identity/identity.md` 和 `registry/agent.json`。
3. **写 `registry/agent.json`**：`id`、`version`、`role`、`visibility`、`owner`、`description`。
   `sub` 的 `visibility` 必须是 `internal`。
4. **写提示词**：`identity/identity.md` 必填，`orchestration.md`、`handoff.md` 按需。
   文件内标题从 `##` 开始；引用知识/记忆/输入/产物用占位符，**不要写真实路径**。
5. **写其余内容**：knowledge、skills、tools、io、memory、connections、environment、acceptance，
   各自格式见 `references/03-formats.md`。
6. **main 引用的子智能体**写在 `registry/agents.json`（`{id, range, alias}`），
   **不是** `registry/agent.json`。
7. **自检**：对着 `references/05-acceptance.md` 的交付检查单逐条过。
8. **打包交付**：按 2.6 命名压缩包、算 SHA-256、给公网链接。

### B. 增量修改（只交变化的部分）

1. 判断**在哪个包里改**：改哪个智能体的内容，就在**它自己的包**里交增量；
   改 main 引用了哪些 sub，在 **main 的包**里改 `registry/agents.json`。
2. 写 `change-set.yaml`：`change_id`、`base_version`（该包最新已发布版本）、`new_version`、
   以及 `add/update/remove_entries` 和 `add/update/remove_files`。**三类都要显式登记**，
   没变就写 `[]`。
3. **提示词要成套给**：登记了 `prompt:identity`，就把包里存在的全部提示词文件一起给出，
   没改的也原样给；没给的视为删除。
4. **不要手改 `agent.json` 的 `version`**：版本由 `change-set.yaml` 的 `new_version` 决定，
   平台合并时回填。
5. 自检：登记与包里实际内容必须完全一致（多、少、方向错都退回）。

### C. 检查一个已有目录 / 压缩包

按 `references/05-acceptance.md` 的检查单逐条核对，重点看：
- 三级目录与 `agent.json` 的 `id` 一致、`version` 与文件名版本一致；
- 角色：`main` 唯一、不被引用，`sub` 没有 `agents.json` 且 `visibility: internal`；
- 提示词标题从 `##` 起，`handoff.md` 提到的角色有定义；
- 占位符合法、被引用的条目真实存在；
- 脚本文件名不带 `_v1`、`_old` 这类后缀；
- 无密钥、无缓存、无符号链接。

## 常见的坑

| 坑 | 正确做法 |
|---|---|
| 把 `sub` 的内容放进了数字员工包 / main 的包 | `sub` 的内容只能在 `sub` 自己包里 |
| 在 `agents.json` 里写 `visibility`、`description` | 那两项在 `agent.json`；`agents.json` 只有 `id`、`range`、`alias` |
| 提示词里写了 `/mnt/...` 或记忆库编号 | 用 `{{knowledge:…}}`、`{{memory:…}}`、`{{input}}`、`{{output}}` |
| 增量只交了 `orchestration.md` | 提示词是整体，三个文件（存在的话）一起交 |
| 版本号只在 `agent.json` 里改 | 版本由 `change-set.yaml` 的 `new_version` 决定 |
| 说"容量限制已经放开" | 目前全部有效，见 `references/07-capacity.md` |
| 允诺"平台运行时会自动校验输入输出契约" | 平台只在**验收阶段**校验，运行时不校验 |
| Skill 脚本用 `../registry/`、`../io/` 或 `parents[3]` 回溯资源包布局 | Skill 脚本必须自包含，只读自己 `scripts/`/`references/`，定位用「相对 Skill 根」路径；平台运行时把 Skill 独立挂载、不保留资源包布局，`registry/`/`io/` 不挂载进沙箱 |
| 交接契约里 path 一会儿绝对一会儿相对 | 契约里"文件位置"字段统一口径（相对工作空间或绝对），产生方与消费方一致 |

## 维护本 skill

`references/` 由脚本从规范原文生成，**不要手改**：

```bash
python3 scripts/build_references.py          # 重新生成
python3 scripts/build_references.py --check  # 只校验是否与规范一致
```

规范改版后重新生成，并同步更新本文件里的版本号与章节描述；
如果规范改了章节结构，要同步修改 `scripts/build_references.py` 里的 `SPLIT`。
