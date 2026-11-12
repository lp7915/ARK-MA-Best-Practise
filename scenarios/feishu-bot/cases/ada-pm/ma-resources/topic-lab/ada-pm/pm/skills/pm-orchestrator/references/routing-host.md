# 路由宿主接口

版本：1.2.0。原版 RoutingNode 代码与 catalog/cases 随 scripts/routing_unit 一起交付；来源摘要清单在同Skill的references/routing-source.json。原项目保留为维护源，本包锁定此份快照，不通过父目录或 PYTHONPATH 偷读原项目。

调用关系：PM 在接收新需求、有效补充或实质修订后固定执行 routing_host.py → routing_host.call → 原版 RoutingNode.handle → 原版 DecisionEngine.decide；不是让模型选择是否调用一个独立的路由 Skill。

独立脚本：python3 scripts/routing_host.py --input event.json --state workspace/routing-state.json。event 为 event_id、actor、text，可带 data 表单；输出 result、state、projection、host_defaults。只产出方案或追问，不启动专业执行。状态文件须在资源包外。

routing-config.json 保存 Topic/动作执行映射和明确的模拟默认参数：去重键 id、地区计数 count。它们是宿主配置，不声称由用户口述。自然输入或表单明确提出其他键/均值/求和时，保留原要求并阻止不匹配的生产替身。原离线语义适配器保留，宿主仅补充已有网页标签和可信结构化字段；不宣称通用语义理解。

路由先于执行就绪判断：缺周期、材料可以有 t/g/h 方案，仍不得确认启动。原内核支持的多 Topic、相关分析、局部画像等尚无本包执行绑定时，明确报告缺口，不能换用计数或丢弃工作。局部动作只取原内核判定的 Topic 未覆盖部分。

每轮接收/补充/修订保存事件、原始路由结果和完整可恢复状态，位置在运行空间 attempts/routing；任务状态内有 routing_state/result/projection/events，确认快照冻结路由证据。进度/解释不重跑；事件幂等先于调用；修订新运行，旧记录保持。旧版本运行只读保留，不静默切换新内核。

本包验收入口为资源根 acceptance/cases.yaml，其中关联的业务知识样例定义最低串联要求。原有回归开发工程不进入交付包；routing_unit/cases.json仅为原内核随附可复用回归输入，不是运行记录。代码与配置交付完成不等于MA平台已经绑定宿主入口。
