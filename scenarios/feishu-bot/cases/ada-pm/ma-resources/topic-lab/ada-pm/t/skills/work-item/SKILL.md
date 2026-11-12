---
name: work-item
description: 真实t/g/validator/s子Agent各自执行一个已确认工作项的文件操作；t/g计算合成Demo产物，validator检查实际产物，s核验依赖并保存本Agent整合草稿；不创建或扮演其他Agent。
---

# 单个真实子Agent的工作项执行

版本：1.2.0。仅在PM已经保存面向当前接收方的有效Context、确认版本和采用输入后调用。主子Agent由MA真实会话承载，PM负责分派；本Skill只执行当前角色，不调用MA API、不创建子Agent、不模拟其他角色。依赖同资源包atomic-ops、Python>=3.9、jsonschema>=4.20，环境统一声明于registry/environment.json。

## 固定调用接口

```sh
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role t --context contexts/t.json --workspace . --output results/t.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role g --context contexts/g.json --workspace . --output results/g.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role validator --context contexts/validator.json --workspace . --output results/validator.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role s --context contexts/s.json --workspace . --draft drafts/s.md --output results/s.json
```

部署工作目录下并列放置ma-resources/与task-workspace/；以上命令的当前目录为包外task-workspace/。--context相对路径按命令当前目录解析；Context内部inputs、产物path及--output/--draft相对路径按--workspace解析，绝对输入与产物路径也必须位于Workspace内。运行空间由宿主创建，不随稳定资源包交付，不能向稳定资源包写运行状态。Context文件本身可由宿主提供，内容按io/contracts/handoff.pm-worker.json验证；recipient须匹配--role，confirmation_version须为正整数。

Context.inputs[0]指向Workspace内已保存的adopted-input.json；内容为facts对象，或包含facts键的对象。事实含object、period、purpose、topic、action、human、dataset、extra_dataset。t支持topic=social/audience；g支持action=deduplicate/aggregate。t+g时g必须取独立extra_dataset，不能重做t覆盖的数据。具体原子参数读取atomic-ops/references/parameters.json；本Skill仅补入数据和Topic必需字段，保留原子动作回执。

Context.upstream_artifacts使用前序真实返回的artifacts对象，须含artifact_id、version、path、sha256、producer、run_id及confirmation_version（兼容plan_version）；task_id存在时也须匹配。脚本读取真实文件、核对摘要及当前运行/确认版本，不能仅凭“完成”文字启动后续阶段。s还必须通过Context.scope.upstream_results提供全部所需t/g以及必要validator的完整标准返回JSON路径数组；脚本逐份核对recipient、task_id、run_id、confirmation_version、status=complete及artifacts与Context逐对象一致。不能传自己的s返回，也不能用部分文件冒充上游已完整完成；validator返回checks须通过且与实际validation文件一致。

## 各角色行为

- t：合并、显式字段校验、id精确去重、地区count、适用时情绪标签count、SVG、合成阶段报告；逐节点保存。社媒情绪标签来自输入，不宣称真实模型标注。人群不臆造人口属性。
- g：只完成指定局部去重或地区count，保留校验、去重和适用的指标/图表；不扩成完整Topic。没有独立extra_dataset时不执行混合需求。
- validator：针对实际上游产物核验路径、摘要、同run/确认版本、必要报告和数据；保存validation.json，返回checks。失败返回status=failed，不能作为s的通过依据；本检查不等于专业判断正确。
- s：Context.scope.production_required列出必需t/g，require_validator布尔值说明必要检查（有t时不可关闭）。先核对真实依赖及检查覆盖。本s Agent应先阅读上游、依据业务规则撰写drafts/s.md，再提供--draft；脚本只保存真实稿件及来源清单，不用固定模板冒充专业整合。human=true的h最终整合路径禁止s。

## 返回与失败

--output保存io/contracts/output.worker-result.json结构：recipient、work_item、confirmation_version、artifacts、evidence、limitations、status；补充task_id、run_id、resource_version、checks、atomic_receipts。每个artifact有真实文件位置、内容版本、sha256、生产者、来源和确认版本，符合output.artifact契约。退出码0表示当前工作项操作完成；1表示失败，已形成阶段文件仍保留。Context本身无效而无法安全建立返回关联时仅打印错误，不伪造标准成功回执。

所有输出为包外Workspace的本轮角色专属目录；多次调用新建产物目录，不覆盖前次版本。复制到飞书、权限/所有权、PM最终交付接受均不由本Skill冒充完成。真实模型的专业输出及MA会话调用质量须另行验收。
