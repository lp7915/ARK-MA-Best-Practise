# 同机部署 + 数据迁移操作指南

> 覆盖:分析师、ada-pm、排障 Bot 与 topic5/topic6/topicx 在同一台机器上的部署、启动后检测,
> 以及把本机已有的数据迁到目标部署机器。排障 Bot 自身的权限/配置细节见
> [`cases/diagnose/OPERATIONS.md`](../cases/diagnose/OPERATIONS.md)。

## 1. 部署形态

- **一套代码**:所有 bot 用同一个 fork main 检出(当前 `b49d9e6`),`scenarios/feishu-bot` 是根。
- **一个 bot 一个进程**:每个 bot 是独立飞书应用(`FEISHU_APP_ID` 互不重复)。同机可以并行跑多个,
  互不占端口、不抢 WS 长连接;但**同一个 App ID 只允许一个进程**(`GatewayLock` 按 App ID 加锁)。
- **排障靠「库路径」读别的 bot**:排障 Bot 不读别人的代码,只按 `config.env` 里的绝对路径打开
  各 bot 的 SQLite 库(只读 `mode=ro`)。所以要求:**排障与被排查 bot 同机、路径配得对**,与被排查
  bot 用哪套代码无关。

### 各 bot 的进程、库、环境变量

| bot | case 名 | 数据目录 / 库文件 | 排障侧识别它的环境变量 |
|---|---|---|---|
| 分析师 | `analyst` | `~/.arkagent/cases/analyst/gateway.db` | `ANALYST_GATEWAY_DB_PATH` |
| ada-pm | `ada-pm` | `~/.arkagent/cases/ada-pm/gateway.db` | `ADA_PM_GATEWAY_DB_PATH` |
| 排障 | `diagnose` | `~/.arkagent/cases/diagnose/gateway.db` + `session_docs.db` | — |
| topic5 | `topic5` | `cases/topic5/data/topic5_pipeline.db` | `TOPIC5_PIPELINE_DB_PATH` |
| topic6 | `topic6` | `scenarios/data/topic6_pipeline.db` | `TOPIC6_PIPELINE_DB_PATH` |
| topicx(统一入口) | `topicx` | `cases/topicx/data/topicx_control.db` | `TOPICX_CONTROL_DB_PATH` |
| 数字员工 | `digital-employee` | `~/.arkagent/employee/gateway.db`(本机现状) | `DIGITAL_EMPLOYEE_SESSION_DB_PATH` |

分析师的 `gateway.db` / topic5、topic6 的 `pipeline_jobs` 都已带 `user_id`、`chat_type`,排障靠它们
判断私聊「是不是本人」。topic5 的两个身份列是在老库上**首次打开时自动补**的(`ALTER TABLE`),无需手动建。

## 2. 部署步骤

### 2.1 环境准备(目标机器)

```bash
# 用 fork main 的干净检出;不要再装 editable 包指向别的目录
git clone https://github.com/lp7915/ARK-MA-Best-Practise.git
cd ARK-MA-Best-Practise
git checkout b49d9e6            # 或最新的 fork main
conda create -n topic6 python=3.11 -y && conda activate topic6
```

启动用 `PYTHONPATH` 指定代码根,不用 `pip install -e`(editable 会固定指向安装时的目录,
换目录后 `import arkagent` 仍 import 到旧路径):

```bash
cd /Users/<you>/ARK-MA-Best-Practise/scenarios/feishu-bot
export PYTHONPATH=$PWD:$PWD/cases
```

### 2.2 各 bot 的 config.env

每个 bot 一个 `~/.arkagent/cases/<case>/config.env`(权限 0600),首登用
`python -m arkagent init --case <case>` 生成骨架,再填密钥与 APP 信息。排障 `config.env` 里
**额外**填它要排查的库路径(见第 1 节表格最右列),路径用**绝对路径**,指向被排查 bot 实际落库的文件。

> 排障 `config.env` 校验规则:配了但文件不存在 → 启动直接报错;两个变量指向同一个文件 → 报错。
> 所以「排障能否正常启动」本身就是第一道库连通性检查。

### 2.3 启动顺序

1. 先起**被排查 bot**(分析师、ada-pm、topic5/topic6/topicx),等它把库建出来。
2. 再起**排障 Bot**。

```bash
# 每个 bot 一个终端 / 一个进程,分别:
python -m arkagent run --case analyst
python -m arkagent run --case ada-pm
python -m arkagent run --case topic5   # 首次打开会给老库补 user_id/chat_type 两列
python -m arkagent run --case topic6
python -m arkagent run --case topicx    # 统一入口,内部再路由 topic5/topic6
python -m arkagent run --case diagnose  # 排障,最后起
```

> 用 topicx 统一入口时,就不用单独起 topic5、topic6;两者只取其一,避免同一 bot 起两个进程。

## 3. 部署后检测

### 3.1 启动自检(每个 bot 都有)

启动日志里会打「权限自检」:缺飞书应用身份权限会醒目告警(不阻断启动)。排障 Bot 额外校验库路径:
`TOPIC5_PIPELINE_DB_PATH 指向的文件不存在` 这类报错的现场,就是路径没配对。

### 3.2 进程与日志

- 每个进程 `run --case <case>` 应常驻不退;`~/.arkagent/cases/<case>/gateway.log` 无异常堆栈。
- 用 `ps aux | grep "arkagent run"` 确认每个进程各一个、App ID 不重复。

### 3.3 排障读库的离线校验(topic 类)

排障的 `trace` 子命令不占飞书,适合确认 topic 库读得通(注意:它只覆盖 topic5/6/x,**不读分析师/ada-pm**):

```bash
cd scenarios/feishu-bot && export PYTHONPATH=$PWD:$PWD/cases
export TOPIC6_PIPELINE_DB_PATH=/abs/path/to/topic6_pipeline.db
python -m arkagent trace list --scenario topic6          # 列出任务
python -m arkagent trace show <task_id|job_id|session_id> --no-events
```

### 3.4 飞书端到端冒烟

1. 被排查 bot:在群里 @ 它发一条能触发任务的指令,确认正常回复。
2. 排障 Bot:在**同一个群** @ 它问「刚才那个任务为什么失败/卡在哪」,应给出结论;结论里带飞书文档链接则更佳。
3. 私聊:用发起任务的那个账号私聊排障,应能查到自己的私聊会话;换另一个账号问,应该回「没找到」。
4. topic5 私聊只在**升级后新建**的任务上可用,老任务私聊查不到(不回填身份)。

### 3.5 排查不到时的核对清单

- 排障与被排查 bot **是否同机**?库路径是否为**该机器上的绝对路径**?
- topic5 是否先于排障重启过(首次补列)?
- 被排查 bot 用的 App ID 是否和排障 `config.env` 里指向的 bot 一致?

## 4. 数据迁移(本机 → 目标机器)

### 4.1 迁移清单(以本机已核实为准)

| 位置 | 内容 | 必迁? |
|---|---|---|
| `~/.arkagent/cases/analyst/` | `gateway.db`(+`-wal`/`-shm`)、`config.env`、`gateway.log` | 会话映射;**必迁** |
| `~/.arkagent/cases/ada-pm/` | 同上 | **必迁** |
| `~/.arkagent/cases/diagnose/` | `gateway.db`、`session_docs.db`、`config.env` | `session_docs.db` 是文档同步进度,**必迁**,否则会重复建飞书文档 |
| `~/.arkagent/cases/topic6/` | 旧版 topic6 的 `gateway.db`、`config.env` | 视是否还用它 |
| `~/.arkagent/employee/` | 数字员工 `gateway.db`、`config.env` | 视是否迁数字员工 |
| `scenarios/data/topic6_pipeline.db`(+`-wal`) | topic6 任务流水 | **必迁** |
| `scenarios/data/digital_employee_admin.db` | 数字员工管理库 | 视需 |
| topic5 / topicx 库 | **本机尚未产生**(`cases/topic5/data/…`、`cases/topicx/data/…` 不存在) | 目标机上首跑即建 |

**不用迁**:**方舟云端的 session 事件**。排障/观测靠 `ARK_API_KEY` 实时拉取,`config.env` 里的 `ARK_*`
搬过去即可。已同步到飞书的 session 文档也不必迁(在云端)。

### 4.2 迁移步骤

1. **停旧机**所有 bot(避免迁库时还在写;同一 App ID 单进程,停了旧机才能在新机起)。
2. **安全导出 SQLite**:运行中的库直接 `cp` 会漏 `-wal`/`-shm`。逐个用 `.backup`(或先 `PRAGMA wal_checkpoint` 再连 `.db`+`-wal`+`-shm` 一起拷):

   ```bash
   for db in \
     ~/.arkagent/cases/analyst/gateway.db \
     ~/.arkagent/cases/ada-pm/gateway.db \
     ~/.arkagent/cases/diagnose/gateway.db \
     ~/.arkagent/cases/diagnose/session_docs.db \
     ~/.arkagent/employee/gateway.db \
     ~/ARK-MA-Best-Practise/scenarios/data/topic6_pipeline.db; do
     sqlite3 "$db" ".backup '/tmp/migrate/$(basename $db).backup'"
   done
   ```

3. **传输** `~/.arkagent/cases/**`(含 `config.env`)。`config.env` 有 `ARK_API_KEY`、`FEISHU_APP_SECRET`
   等密钥:用 `scp` / 加密压缩,不要进仓库、不要贴到聊天、落地后 `chmod 600`。
4. **改路径**:排障的 `config.env` 里 `ANALYST_GATEWAY_DB_PATH` / `ADA_PM_GATEWAY_DB_PATH` /
   `TOPIC6_PIPELINE_DB_PATH` 等是**旧机绝对路径**,改成新机路径;`topic6` 若走默认路径
   (`scenarios/data/`)则把库放到新机对应位置即可。
5. **恢复**:把导出的 `.db` 放回各 case 目录,恢复为原文件名(去掉 `.backup` 后缀)。
6. **校验**:`sqlite3 <db> "PRAGMA integrity_check; SELECT count(*) FROM conversations;"` 等,与旧机行数对照。
7. **启动**:按第 2.3 节顺序起,再走第 3 节检测。旧机备份保留几天再删。

### 4.3 迁移注意事项

- **排障与被排查 bot 必须一起迁、迁到同一台机**;只迁排障不迁库,排障拿到的是空库。
- 同机重启顺序不变:**先被排查 bot,后排障**;topic5 首启会补列。
- 旧会话迁过去后仍可续聊(session id 在方舟云端,库里的映射只是「哪个群/人对应哪个 session」)。

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 排障启动报「文件不存在」 | 库路径是旧机/错误的绝对路径;核对第 1 节表格最右列 |
| 同一个 App ID 起第二个进程被锁 | 每个 bot 独立飞书应用;同 App 只允许一个进程 |
| 私聊查不到话题任务 | 老任务无身份、或 topic5 没先重启补列 |
| 迁移后文档重复生成 | `session_docs.db` 没迁或没放对 |
| 换机器后 `import arkagent` 是旧代码 | 有 editable 安装指向了旧目录;用 `PYTHONPATH` 覆盖或重装 |