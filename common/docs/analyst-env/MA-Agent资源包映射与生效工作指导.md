# MA Agent 资源包映射与生效 · 工作指导

> 版本：v1.0 · 2026-11-12 · 面向中台研发
> 来源：把 Ada PM Demo（`MA规范目录Demo-2026-11-10.zip`）从「业务交付包」一路做到「MA 上可对话的数字员工 + 飞书入口」的完整过程沉淀。后续处理同类资源包照此执行。
> 依据规范：《MA Agent 搭建交付规范》v1.4、《MA Agent 搭建映射规范（平台内部）》v1.4、《原子能力注册表设计》。

---

## 一、总览

| | |
|---|---|
| 输入 | 业务方交付的资源包（zip，含一个数字员工的智能体包目录） |
| 输出 | MA 上的 Agent ×N + Environment + 知识库 + Skill + 飞书 gateway 入口 |
| 六阶段 | 探测 → 对齐 → 迁移 → 构建 MA 资源 → 冒烟 → 打通飞书 |

**核心原则：先探测对齐再动手；每个外发/不可逆动作前跟用户确认；踩过的坑立即沉淀进规范或 memory。**

---

## 二、阶段 1：探测可行性（只读）

1. 解压 zip 到独立空目录（untrusted data），`unzip -l` 看目录树，读关键声明：
   - `registry/agent.json` / `registry/agents.json` / `registry/employee.json`（注意新旧格式差异）、`registry/skills.json`、`registry/environment.json`
   - `connections.yaml`、`knowledge.yaml`、`identity/`、`acceptance/cases.yaml`、`io/contracts/`
2. **判定规范版本**：业务包的 `spec_version` 可能是 v1.1 单目录（主+子混在一起）或 v1.3 独立包。与现行规范不一致就先记差异。
3. **探测 MA 现状**：只读 list agents/environments/memory_stores/vaults，确认业务线 ID 未被占用。
4. **盘点脚本路径依赖**：读 `skills/**/scripts/*.py`，找 `Path(__file__).parents[n]`、`registry/`、`io/`、跨 skill 引用——这些在 MA 运行时可能不成立（见坑 1/2）。

## 三、阶段 2：对齐决策（问用户）

必问五项（Ada PM 实例的答案在括号里）：

1. **规格版本**：迁到 v1.3？还是保旧格式？（迁 v1.3）
2. **业务线/员工 ID**：沿用业务建议还是平台重分？（`topic-lab`/`ada-pm` 沿用）
3. **模型**：方舟 / BYOK？（BYOK，复用 analyst 的 `gpt-6.1-sol`）
4. **资源命名/可见范围/飞书应用**：新建还是复用？（飞书独立应用，可见范围用户自控）
5. **产物存储**：bucket + prefix（含 `<topic>/<emp>/`，会话级覆写 + 按 user/topic 隔离，对齐 analyst）

## 四、阶段 3：迁移 / 规范化

- v1.1 单目录 → v1.3 独立包：拆 `<topic>/<emp>/{main,sub…}/`，每包 `registry/agent.json`（role/visibility/version/owner）+ main 的 `registry/agents.json` 引用 sub。
- 知识、Skill 按「占位符只能引用自己包」各放副本；`connections.yaml`/`knowledge.yaml` 转 YAML。
- **脚本适配**（关键，见坑）：work-item 类脚本 `parents[3]` 改 `parents[1]`（skill 根），自重包含依赖。
- 静态接收校验自检（agent 字段 / main-sub 约束 / 占位符引用 / skill 目录 / 密钥明文 / 知识容量）。

## 五、阶段 4：构建 MA 资源

顺序（先子后主、会话级资源合并）：

1. Skill 打包上传（内容变化=新 skill_id，`POST /skills/{id}/versions` 是同 id 新版本）
2. Environment（员工级 1 个；pip 装依赖需 networking unrestricted）
3. 知识库（每包声明各 1 个，read_only，写入知识文件 + `/_索引.md`）
4. sub Agent 先建 → main Agent 后建（multiagent 显式写 sub 的 id+version）
5. 幂等脚本落盘：`created_ids.json` 记录全部资源 ID

**字段类型坑**：`skills[].version` 是字符串、`multiagent.agents[].version` 是 int32，两处相反。

## 六、阶段 5：冒烟验收

- 建会话（挂知识库 read_only + BYOK 请求级鉴权头）→ 发消息 → 拉事件流核对：
  - `session.thread_created`（分派真实发生）、子 Agent `agent.tool_use`（bash 真实执行）、文件交接 `/workspace/…`
- 按 `acceptance/cases.yaml` 的 expected 逐项核对（数据结果 + 流程 + 产物）。

## 七、阶段 6：打通飞书 channel

case 三件套（`scenarios/feishu-bot/cases/<case>/`）：

- `config.py`：`load_case_config(env)` 返回 dataclass（ARK 凭据 + 资源 ID + 知识库 + BYOK + output_tos）。
- `gateway.py`：`build_gateway(config, ark, sender, loop)` 复用通用 `Gateway`，传 agent/env/知识库/BYOK/`output_tos` + `scope_output_by_user_topic=True`。
- `env.example`：配置模板。

启动：`cd scenarios/feishu-bot && conda run -n topic6 python -m arkagent run --case <case>`（**不能直接敲 `arkagent`**，PATH 上那个是旧 Node CLI）。飞书应用由 `arkagent init --case` 扫码建，或用户给现有凭据。日志 `~/.arkagent/cases/<case>/gateway.log`。

---

## 八、踩坑清单（均已沉淀到规范/memory，勿再犯）

| # | 坑 | 处置 |
|---|---|---|
| 1 | MA 运行时 skill 挂 `/mnt/skills/<名>/`，`parents[3]` 算成 `/mnt`，读 `/mnt/registry/agent.json` 404 | 脚本改 `parents[1]`（skill 根）+ 自包含依赖（见 [[ada-pm-demo-v13-migration]]） |
| 2 | Skill 脚本跨 skill 读文件 / 读 `registry`/`io`——这些不是沙箱资源 | Skill 必须自包含（映射规范 6.5/接收校验 20） |
| 3 | `skills[].version` 字符串 vs `multiagent.agents[].version` int32 两处相反 | 映射规范 6.2.2「字段类型」行 |
| 4 | 交接契约 `path` 绝对 vs 相对不一致 → s 严格校验阻塞 | 契约写死口径+产生方/消费方一致（交付规范 v1.4 5.6） |
| 5 | 升级 analyst 环境自写 tmp 脚本（造轮子） | 用 `ma_test/analyst-env` 的 `npm run apply/sync-sessions`（见 [[analyst-env-ma-test-tooling]]） |
| 6 | 媒体中心同名文件上传有覆盖歧义 | 文件名带版本号（见 [[media-storage-upload-versioned-name]]） |
| 7 | Environment `config.tos` 一旦设置只能改值不能删（null 忽略、`{}` 400） | 产物存储走会话级覆写，别挂 Environment 级 |

---

## 九、产物清单

每处理一个资源包，最终落在 `scenarios/feishu-bot/cases/<case>/`：

```
cases/<case>/
├── ma-resources/<topic>/<emp>/…      # 迁移后的 v1.3 交付包
│   └── created_ids.json              # 全部 MA 资源 ID
├── tools/pack_upload_skills.py       # Skill 打包上传
├── create_all.py                     # 幂等创建 MA 资源
├── smoke.py / multi_round.py         # 冒烟脚本
├── config.py / gateway.py / env.example  # 飞书 case 三件套
```

注册表同步：能力/版本/引用/引用历史四张表，新增版本 + 更新引用锁定 + 写引用历史 + 能力描述版本号。

相关 memory：[[ada-pm-demo-v13-migration]] [[ma-multiagent-resource-probe]] [[analyst-env-ma-test-tooling]] [[media-storage-upload-versioned-name]]