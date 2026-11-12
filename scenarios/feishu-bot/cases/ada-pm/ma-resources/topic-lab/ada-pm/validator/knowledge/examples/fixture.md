# 合成输入、Context与返回结构样例

名称：合成输入、Context与返回结构样例
适用范围：MA目录Demo的可复用合成样例与最低流程逻辑核对
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位，正式验收人待指定）
状态：静态合成测试材料及期望；不是运行日志或平台验收结论。

## 材料约定
本文件集中保存可复用的合成材料。`fixture-message`、`task-reference`、`run-reference`、`artifact-reference` 是固定样例符号，不是某次运行产生的编号；执行时由宿主分配真实对象并保存在资源包外 Workspace。包内只保存本模板，不能把运行输出回填本文件。

以下命名JSON块分别用 `input.event`、`input.envelope`、`handoff.pm-worker`、`output.worker-result` 契约核对；契约在 `io/contracts/`。结构正确不代表其中的期望已经执行。

## social_event
完整结构化接收事件；唯一评论样本位于 `data.dataset`，其对象同时满足标准数据信封契约。

```json
{
  "event_id": "fixture-message",
  "actor": "requester",
  "kind": "message",
  "text": "对合成品牌做完整评论报告，只复用本次给定合成样本。",
  "data": {
    "object": "合成品牌",
    "period": "2026-10",
    "purpose": "验证PM最低流程与文件引用",
    "topic": "social",
    "action": null,
    "human": false,
    "dataset": {
      "schema": [
        {
          "name": "id",
          "type": "string",
          "nullable": true
        },
        {
          "name": "region",
          "type": "string",
          "nullable": true
        },
        {
          "name": "text",
          "type": "string",
          "nullable": true
        },
        {
          "name": "sentiment",
          "type": "string",
          "nullable": true
        }
      ],
      "rows": [
        {
          "id": "a1",
          "region": "华东",
          "text": "合成评论一",
          "sentiment": "positive"
        },
        {
          "id": "a2",
          "region": "华北",
          "text": "合成评论二",
          "sentiment": "neutral"
        },
        {
          "id": "a2",
          "region": "华北",
          "text": "合成重复评论",
          "sentiment": "neutral"
        },
        {
          "id": "a3",
          "region": "华东",
          "text": "合成评论三",
          "sentiment": "negative"
        },
        {
          "id": "",
          "region": "华南",
          "text": "合成缺ID评论",
          "sentiment": "unknown"
        }
      ],
      "meta": {
        "source": "synthetic:social-demo",
        "scope": "虚构样本，不对应真实品牌或用户"
      }
    }
  }
}
```

按已声明的模拟参数：id必填校验剔除空id，exact按id保留首条。预期原始5行→有效4行→去重3行；地区count为华东2、华北1；情绪count为positive1、neutral1、negative1。unknown所在行因id无效已剔除，不能计入有效样本。不得外推总体、因果或购买意图。

## registration_dataset
独立局部报名表；与评论表使用不同id。用于t+g的额外地区统计或纯g演示。exact按id保留首条，预期4行→4行有效→3行去重，地区count为华南2、华东1。统计不能与评论表拼成一个分母。

```json
{
  "schema": [
    {
      "name": "id",
      "type": "string",
      "nullable": true
    },
    {
      "name": "region",
      "type": "string",
      "nullable": true
    }
  ],
  "rows": [
    {
      "id": "b1",
      "region": "华南"
    },
    {
      "id": "b2",
      "region": "华东"
    },
    {
      "id": "b2",
      "region": "华东"
    },
    {
      "id": "b3",
      "region": "华南"
    }
  ],
  "meta": {
    "source": "synthetic:independent-registration-demo",
    "scope": "独立虚构报名表，不与评论表合并样本分母"
  }
}
```

## context_example
只有发起人确认当前方案且必填材料已读取后，才将下列结构实例化到运行空间并交t。来源、读取状态和保存位置必须以执行事实填写；不能照抄示例宣称已经读取或交接。

```json
{
  "task_id": "task-reference",
  "run_id": "run-reference",
  "work_item": "social-report-reference",
  "recipient": "t",
  "confirmation_version": 1,
  "context_version": 1,
  "sources": [
    {
      "ref": "fixture-message",
      "read_status": "complete",
      "note": "仅在真实读取本样例内容后可采用此状态"
    }
  ],
  "rule_reads": [
    "knowledge/standards/context.md"
  ],
  "scope": {
    "object": "合成品牌",
    "period": "2026-10",
    "topic": "social",
    "purpose": "验证PM最低流程与文件引用"
  },
  "inputs": [
    "本任务已采用的social_event.data.dataset版本"
  ],
  "upstream_artifacts": [],
  "expected": "合并/校验/去重数据、地区和情绪count口径、SVG、阶段报告和限制；逐节点保存后回PM。",
  "memory": []
}
```

## worker_result_example
以下只演示回传结构，不提供假文件或成功回执。真正执行时 `artifacts` 必须指向已存在的产物，摘要、复制结果和证据取实际值，不能使用本例的全0摘要。必要Validator由PM另行分派；本段不能替代检查结果。

```json
{
  "recipient": "t",
  "work_item": "social-report-reference",
  "confirmation_version": 1,
  "artifacts": [
    {
      "artifact_id": "artifact-reference",
      "version": "1.0.0",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "path": "当前运行的artifacts/阶段报告.md",
      "producer": "t",
      "run_id": "run-reference",
      "kind": "report",
      "source_refs": [
        "fixture-message"
      ],
      "copies": []
    }
  ],
  "evidence": [
    "artifact-reference"
  ],
  "limitations": [
    "结构示例；摘要0只是示意，执行时必须取真实文件摘要",
    "合成输入中显式给定情绪标签，不代表真实模型标注"
  ],
  "status": "complete"
}
```

角色及状态语义见 {{knowledge:glossary.md}}；确认、Context、交付分别沿 {{knowledge:standards/confirmation.md}}、{{knowledge:standards/context.md}}、{{knowledge:standards/delivery.md}}。

### 运行时装配要求

上面的Context是结构模板。实际执行前，PM必须将采用facts保存为包外adopted-input.json，inputs[0]改为该文件的实际路径，再分别保存t/g/validator/s的Context。s的scope还必须含production_required、require_validator，以及upstream_results（所需t/g和必要validator完整返回JSON的实际路径）；upstream_artifacts取相应真实返回对象。结构示例中的占位产物不能用于实际检查。
