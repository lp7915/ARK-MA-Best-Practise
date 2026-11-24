# 真实子Agent最少调用约定

版本：1.2.0。此文件是调用说明，不是已经发生的运行记录。

PM先确认业务版本，再将采用输入保存到包外Workspace的 `adopted-input.json`，其中为 `{ "facts": { ... } }` 或直接facts对象；可同时冻结run_id、confirmation_version，脚本存在这些字段时会核对。facts含对象、周期、用途、Topic/局部动作、人工路径以及实际采用的数据。合成数据取本资源包knowledge/examples/fixture.md的固定样例，不以不存在的占位符当文件。

PM针对每个真实接收方分别保存Context，结构采用io/contracts/handoff.pm-worker.json。最少引用关系如下：

|接收方|inputs[0]|upstream_artifacts|scope中的依赖|
|---|---|---|---|
|t|已保存的采用输入|无上游时空数组|本Topic和有效版本|
|g|同一采用输入；混合工作读取其中extra_dataset|无上游时空数组|明确action，不重复Topic覆盖|
|validator|同一采用输入|本轮需要检查的t/g返回artifacts|应检查的实际工作范围|
|s|同一采用输入|全部所需t/g产物及validator的validation产物|production_required=[t,g]或对应子集，require_validator=true/false，upstream_results=[各完整返回JSON路径]|

`upstream_artifacts`逐项保留前序真实返回的对象，不自行拼接假摘要；run_id、task_id、confirmation_version须一致。validator要求明确的合并、校验、去重、报告，以及适用的指标、图表与情绪统计文件。失败检查会保存validation.json并返回status=failed。s核对当前通过检查对真实产物编号、内容版本与摘要的覆盖；有t时不能关闭必要validator。s的scope.upstream_results是必填路径数组，例如["results/t.json","results/validator.json"]；混合t+g加入results/g.json。每份返回须为complete、匹配任务/运行/确认版本，其artifacts必须与Context对应角色的全部产物对象一致；validator的checks必须与真实validation文件逐项一致且通过。不得把s自己的返回或历史/部分返回当上游依赖。

部署工作目录下并列放置ma-resources/与task-workspace/，当前目录进入包外task-workspace/。每个真实子Agent仅运行自己的命令：

```sh
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role t --context contexts/t.json --workspace . --output results/t.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role g --context contexts/g.json --workspace . --output results/g.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role validator --context contexts/validator.json --workspace . --output results/validator.json
python3 ../ma-resources/topic-lab/ada-pm/skills/work-item/scripts/run.py --role s --context contexts/s.json --workspace . --draft drafts/s.md --output results/s.json
```

`--context`由命令行按实际文件路径定位；Context内部inputs、产物path，以及--output/--draft的相对路径按--workspace解析。相对Context按命令cwd解析；运行空间由宿主创建，不随稳定资源包交付，资源包内不放这些已填写实例。

s Agent必须先读取上游报告、数据口径和检查，依自身身份与知识撰写非空Markdown草稿，再提供--draft。脚本只保存这份真实稿件和来源关系；缺草稿返回失败，不会生成固定文案冒充模型分析。h路径交人工完成最终整合，禁止调用s重复整合。

成功返回符合output.worker-result，artifacts逐项符合output.artifact；checks使用通过/失败和明确受检产物。成功退出仅表示本角色文件操作完成，不代表PM最终交付或业务接受。PM必须核对标准返回status=complete后，才组装下一角色Context。失败返回仍列出已保存的阶段文件，不能删除证据后伪称从未执行。
