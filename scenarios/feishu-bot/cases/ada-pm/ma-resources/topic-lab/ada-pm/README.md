# Ada PM 数字员工 · v1.3 迁移后交付物

> 来源：`~/Downloads/MA规范目录Demo-2026-11-10.zip`（业务方交付的 v1.1 单目录 Demo）
> 业务线 `topic-lab` / 数字员工 `ada-pm`（沿用业务方建议值，待平台确认）
> 迁移时间：2026-11-10 · 迁移依据：《MA Agent 搭建交付规范》v1.3 +《MA Agent 搭建映射规范（平台内部）》v1.3

---

## 一、这是什么

「Ada PM」是一个演示 **MA 上一主多子 + 必经路由脚本 + 文件交接 + 人工关卡** 的数字员工：唯一入口 `pm`，分派给 `t`（完整 Topic 报告）/ `g`（局部原子动作）/ `s`（整合稿）/ `validator`（工程检查）；`h` 为人工角色，不是子智能体。无外部 MCP、无连接、无长期记忆库、无 TOS。

## 二、v1.1 → v1.3 迁移对应

v1.1 是「单目录承载主 + 全部子」（`identity/pm/` + `subagent/<x>/` + 员工级 `registry/agents.json`、`employee.json`），本目录已迁成 v1.3 的「每个智能体独立包」：

| v1.1 位置 | v1.3 位置 |
|---|---|
| `identity/pm/` | `pm/identity/`（main） |
| `subagent/t|g|s|validator/` | `t|g|s|validator/identity/`（sub） |
| `registry/agents.json`（`role: entry/subagent` + `mounts`） | 每包 `registry/agent.json`（`role: main/sub` + `visibility`）+ pm 的 `registry/agents.json`（引用 t/g/s/validator） |
| `registry/employee.json` | 每包 `registry/agent.json` 的 `owner` + `version` |
| `registry/skills.json`（`source: local` + `path`） | 每包 `registry/skills.json`（`[{id, range}]`） |
| 员工级 `knowledge/`（全员挂载） | 每包 `knowledge/`（完整副本）+ `knowledge.yaml`（占位符只能引用自己包，见下） |
| 员工级 `skills/` | pm 挂 `pm-orchestrator`；t/g/s/validator 挂 `work-item` + `atomic-ops`（副本） |
| 员工级 `io/contracts/` | 每包 `io/contracts/`（work-item 脚本依赖） |
| 员工级 `acceptance/cases.yaml` | `pm/acceptance/cases.yaml`（员工级验收，含分层分派用例，保留在 main 包） |
| `connections.yaml`/`knowledge.yaml`（实际为 JSON） | 已转 YAML |

## 三、脚本适配（迁移时的一处必要改动）

`work-item/scripts/run.py` 顶部用 `Path(__file__).resolve().parents[3]` 定位「资源根」，v1.1 里是员工根、v1.3 里恰好回到**智能体包根**，因此 `parents[3]` 不变；只需把读取对象从 `registry/employee.json` 改为 `registry/agent.json`（一处改动，已同步 4 个 sub 包）。`skills/atomic-ops` 与 `io/contracts` 通过「每个 sub 包复制一份」满足。`pm-orchestrator` 脚本只依赖自身目录，完整复制即可，无需改。

## 四、待补项（构建前必填）

| 项 | 状态 |
|---|---|
| BYOK 模型配置（`model` 字段 5 项：id/provider/base_url/protocol/token_limits） | **待业务方/平台提供** |
| 请求级鉴权头（是否复用 analyst 的 `BYOK_MODEL_AUTH_HEADER_*`） | **待确认** |
| `owner` 实名（`primary`/`backup` 现为「待指定」） | 待指定 |
| 3 个自有 Skill 打包上传（pack_skills + upload_skills，得 skill_id） | 待执行 |
| 业务线 ID 全局唯一性平台侧确认 | 待平台确认 |

## 五、目录结构

```text
topic-lab/ada-pm/
├── pm/                       # main · visibility: public
│   ├── identity/  knowledge/  skills/pm-orchestrator/  io/  acceptance/
│   ├── knowledge.yaml  connections.yaml
│   └── registry/{agent.json, agents.json, skills.json, environment.json, version_mapping.md}
├── t/    g/    s/    validator/   # sub · visibility: internal，结构同 pm，无 agents.json
└── README.md（本文件）
```