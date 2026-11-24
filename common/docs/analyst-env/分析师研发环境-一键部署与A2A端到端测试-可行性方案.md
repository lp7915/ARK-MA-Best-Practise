# 分析师研发环境扩展：一键部署 + A2A 端到端测试 · 可行性方案

> 版本：v0.1（草案，探测中）· 2026-11-16
> 状态：**关键点已本地实测；飞书平台层 3 个未知项待真实环境实测，未实测的不下结论**
> 依据：《MA Agent 搭建映射规范（平台内部）》v1.5、《MA Agent 资源包映射与生效工作指导》、《排障 Bot 方案》（OBSERVABILITY_PLAN §11）

---

## 0. 结论先行

| 探测 | 结论 |
|---|---|
| 1. 映射 spec 集成研发环境 + 一键部署 | **可行，但要新建 `ma-mapper` 工具，不复用 `analyst-env`**。当前 `create_all.py` 是 demo 硬编码，未做"泛化读包 + 会话级合并"。 |
| 2. A2A 三 bot 拉群端到端测试 | **机制上可行，但有一个飞书平台层闸门必须先实测**（bot→bot 消息是否回传）。"驱动产物迭代"的闭环依赖探测 1 的一键部署。 |

---

## 一、探测 1：映射 spec 集成研发环境 + 一键部署

### 1.1 结论

- 能做成"类似一键部署"的能力：输入一份符合交付规范的资源包（zip 或目录），输出 MA 上的 Agent ×N + Environment + 知识库 + Skill + 飞书入口，幂等、可 `plan` 预览后 `apply`。
- **关键是它不能塞进 `analyst-env`**：`analyst-env` 的语义是"从一组 Session 合并出研发环境"（输入 Session、输出开发环境）；而映射构建是"从交付包构建数字员工资源"（输入 zip、输出 MA 资源）。两者输入输出、幂等语义、锁定清单都不同，硬合会破坏 `analyst-env` 已确定的确定性语义。
- 应新建一个 `ma-mapper`（建议与 `analyst-env` 同仓、同风格：`plan` / `apply` / `sync` / `reset`）。

### 1.2 实测证据（本地已确认，非推测）

对着 `cases/ada-pm/create_all.py` 与 `ma-resources/topic-lab/ada-pm/{pm,t,g,s,validator}/` 实测：

| # | 实测事实 | 说明 |
|---|---|---|
| 1 | `AGENT_ORDER` / `KNOWLEDGE_NO` / `SUB_ALIASES` / `TOPIC` / `EMP` 全部写死 | Agent 清单、知识库序号、sub 别名都是硬编码，换一个数字员工就得改脚本 |
| 2 | `ensure_environment` 的 `config` 硬编码，**未读** `registry/environment.json` | 泛化合并未实现 |
| 3 | **声明与脚本自相矛盾**：5 个包 `environment.json` 都写 `network.mode: restricted`，但脚本写死 `networking.type: unrestricted`（为了 pip 出网） | 正是"没读包声明、脚本拍脑袋"的直接后果 |
| 4 | `build_system` 只替换 `{{knowledge:}}`，不处理 `{{memory:}}` / `{{input}}` / `{{output}}` | 占位符替换未覆盖全 |
| 5 | `metadata.spec` 写死 `"1.3"`（现行已 v1.5） | 版本漂移 |
| 6 | 5 个包的 `environment.json` / `knowledge.yaml` **内容完全相同**（`python>=3.9`+`jsonschema`+`PyYAML`，5 份重复）；`connections.yaml` **全部为空** | 历史包袱（用户已定性"业务方包不规范，不归平台侧"）；**且意味着"会话级合并的冲突场景"当前没有真实样本可验证**（尤其 Vault 合并，连接全空从未被构建过） |

**结论支撑**：`ma-mapper` 要补的正是这几处——读包声明的泛化合并、占位符全覆盖、spec 版本随规范走。其中"泛化合并"在 demo 包上被"5 份相同 + 连接为空"掩盖了，需要用一个**带真实差异的包**（不同 environment、非空 connections）做合并测试，否则合并器不经真冲突样本验证不能宣称可用。

### 1.3 待定 / 需进一步确认

- `ma-mapper` 做 npm 工具（对齐 `analyst-env`）还是做成 Skill（给分析师研发 bot 调用）：见 1.4 的"形态"。
- 20 项接收校验哪些能静态自动化：**已实测，见 1.4A**。
- 一键部署"生效到测试环境"的目标环境：`dev` 阶段（`stage: dev` 元数据）还是独立测试 MA 项目。

### 1.4 建议落地路径（分阶段）

1. **阶段 A：接收校验器**（纯静态、只读、本地可跑）——把映射规范 §3 里可静态化的校验项实现为 Python（对齐本仓 `python3` 生态），对 ada-pm 包跑通并出报告。这一步回答"20 项里哪些能机器校验"。
2. **阶段 B：泛化合并器**——读各包 `agent.json` / `agents.json` / `skills.json` / `knowledge.yaml` / `stores.yaml` / `connections.yaml` / `environment.json`，实现 6.2.4 会话级合并（并集 + 冲突检查 + 冲突指出来源包）。**必须用一个带真实差异的样本包验证冲突检测**（现 demo 包无冲突、连接为空）。
3. **阶段 C：构建器**——把 `create_all.py` 泛化：从"读合并结果"生成资源，先子后主、幂等、落 `created_ids.json`；替换 `create_all.py` 里 1.2 节的全部硬编码。
4. **阶段 D：接飞书入口 + `plan`/`apply` 命令**——收敛成 `ma-mapper` 一条命令，输出与 `analyst-env` 一致的"计划报告 + 台账"。

> 阶段 A、B 都是本地纯静态，可立即做、可离线验收；阶段 C 需真实 MA 项目（写操作），阶段 D 需打通飞书。

### 1.4A 阶段 A 实测结论（2026-11-17）

已实现校验器原型 `common/tools/ma-mapper/validate.py`（Python、标准库、无第三方依赖），对 ada-pm 真实包跑通。

**20 项接收校验的可自动化性：**
- **15 项纯静态可自动化**：目录/ID/必需文件、密钥明文扫描、依赖版本下限、connections 无凭证值、验收用例字段、提示词标题二级、knowledge 目录存在、容量、角色与引用约束、脚本文件名后缀、会话级合并冲突、版本号、Skill 脚本自包含……
- **3 项需平台查询**：7「可复用能力已登记」（查注册表）、17「internal 白名单非空」（查飞书应用）、18「压缩包完整性」（查压缩包产物）；
- **2 项需人工**：2「信息唯一归属」（语义判断）、6「记忆库逐个决策」（业务决策）。

**对 ada-pm 包实测捕获 3 处规范偏差**（均为既知"业务方包不规范"的直接体现，见 [[ada-pm-demo-v13-migration]]）：
1. 智能体 ID 过短：`g`/`s`/`t`（1 字符）、`pm`（2 字符），规范要求 3–24 位；
2. 4 个 `sub` 缺 `acceptance/cases.yaml`（只有 `pm` 有）；
3. 知识目录数 20 > 10（5 包 × examples/standards/templates/topics ＝ "员工级一套知识复制 5 份"的直接后果）。

---

## 二、探测 2：A2A —— 三 bot 拉群端到端测试

### 2.1 结论

- **机制上可行**：三 bot（排查 bot、分析师研发 bot、产物 bot）都是独立飞书应用 + 各自 gateway，同机部署、日志同机（`~/.arkagent/cases/<case>/`），排查 bot 可直读。
- **有一个平台层闸门必须先实测**：飞书是否把 bot→bot 的消息回传给接收方 bot。这一项不通过，整个"拉群自行对话"就断了，后续都不用做。
- **"驱动产物迭代"的闭环依赖探测 1**：端到端测出问题 → 排查 bot 给结论 → 分析师研发 bot 改包 → **重建资源**（现在靠 `create_all.py`，要 `ma-mapper` 才能自动化）。

### 2.2 实测证据（代码事实，本地已确认）

- **消息是否处理**：`orchestrator.should_handle_message` = `chat_type == "p2p" 或 mentioned_bot`。**不因 `sender_type == "app"` 拒绝**——即 bot 发出的消息，只要满足"私聊"或"被 @"，接收方 bot 就会处理。
- **bot 消息只在历史注入时被过滤**：`normalize_history_item` 里 `is_from_bot = sender_type == "app"`，仅用于切窗口/过滤回复历史，不影响对"当前触发消息"的响应。
- **当前出站 @ 主动跳过机器人**：`list_chat_members` 注释明写"非 open_id 的成员（机器人等）跳过——名册只服务'把回复里 @人名 变成可点击 <at>'"。即**现在的 bot 无法主动 @ 另一个 bot**（群成员名册里没有机器人）。要 a2a 需要专门加"@ bot"的构造路径（直接按 bot 的 open_id 拼 mention）。
- **排查 bot 可读三 bot 数据**：三 bot 配置/日志均在 `~/.arkagent/cases/{analyst,ada-pm,…}/`，SQLite 日志在本机；排查 bot 同机部署方案（已定）直读即可，无跨机问题。

### 2.3 必须真实环境实测的 3 项（未实测，不推测）

这三项都只能在一个真实飞书环境里用探针验证，本地代码给不了答案：

| # | 待实测项 | 验证方法（探针设计） |
|---|---|---|
| 1 | 飞书是否接受"机器人 @ 另一个机器人"（mention 传另一个 bot 的 open_id） | 造一个最小应用 A，`im.v1.message.create` 给群里发带 mention（目标 = bot B 的 open_id）的 text，看飞书是否报错、B 是否收到 |
| 2 | bot→bot 消息（`sender.sender_type=app`）**会不会回调**给接收方 bot 的 `im.message.receive_v1` | 两个最小 bot A/B 同群，A 直发一条（不 @），看 B 的事件日志里有没有出现这条消息 |
| 3 | bot 能否给 bot 发 p2p 私聊，且触发对方回调 | A 用 `receive_id_type=open_id` 给 B 的 open_id 发 p2p text，看 B 是否收到并进入处理 |

**这三项只要有一项卡住，A2A 就得换实现**（例如不靠飞书 IM 互相 @，改成"控制台/脚本层直接调三 bot 的 MA Session"做端到端，绕开飞书平台闸门）。

### 2.4 依赖关系与建议路径

```text
端到端测试闭环：
  排查 bot（读三 bot 日志/会话，给结论）
      │ 结论（问题定位）
      ▼
  分析师研发 bot（有 ma-agent-delivery-spec skill，能改交付包）
      │ 改好的包
      ▼
  ma-mapper（探测 1）重建资源  ←── 当前是 create_all.py，需探测 1 打通
      │ 新资源
      ▼
  产物 bot 新版本 → 再测
```

建议顺序：
1. 先做 **2.3 的三项探针**（一个极小的 bot→bot 实测脚本，半小时级），拿到平台层结论；
2. 平台层通过 → 再做"三 bot 拉群" + 排查 bot 读三 bot 数据；平台层不通过 → 改走"脚本层直调 MA Session"的 a2a（不依赖飞书 IM）。
3. 闭环里的"重建资源"等探测 1 的 `ma-mapper` 就绪后再接上。

---

## 三、两个探测的关系

```text
探测 1（ma-mapper 一键部署）
        ▲
        │ 是"驱动产物迭代"闭环的最后一公里
        │
探测 2（A2A 拉群端到端测试）
        │ 依赖飞书平台层 3 项未知（先测这个，成本最低）
```

- **先做、且成本最低的是探测 2 的飞书探针**（2.3 三项）——它决定 A2A 走"IM 拉群"还是"脚本直调"。
- **本地可立即做的是探测 1 的阶段 A（接收校验器）**——纯静态、无写操作，能先产出"20 项哪些可机器校验"的确定性结论。