# 完整Topic加独立局部工作的t+g

名称：完整Topic加独立局部工作的t+g
适用范围：MA目录Demo的可复用合成样例与最低流程逻辑核对
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位，正式验收人待指定）
状态：静态合成测试材料及期望；不是运行日志或平台验收结论。

## DEMO-04 t+g
主输入采用 {{knowledge:examples/fixture.md}} 的social_event；同一事件额外设置 `data.action="aggregate"`，`data.extra_dataset` 使用fixture唯一registration_dataset。文字明确“完整评论报告，另外统计独立报名表的地区人数”。本例是两份不同来源表，不能用同一评论地区统计冒充独立剩余工作。

1. 原路由先识别完整社媒产品，再核对剩余独立地区统计，形成t+g。PM确认单逐项列明两份输入、两类产物、口径与整合责任，沿 {{knowledge:standards/confirmation.md}} 一次绑定当前版本。
2. 发起人确认后，PM沿 {{knowledge:standards/context.md}} 分别保存t和g的Context。t只拿评论表和社媒工程；g只拿独立报名表、地区count、id exact/first参数，不得重复t内部的评论地区计数。
3. t沿 {{knowledge:topics/social/engineering.md}} 返回完整阶段数据与报告；其必要validator由PM单独分派。g沿 {{knowledge:standards/atomic.md}} 返回报名表校验、去重与地区count。
4. 预期评论地区count华东2/华北1，报名表地区count华南2/华东1。两个分母分别标注，不能相加后称统一消费者分布。
5. 两项所需结果及t的必要检查都齐备前不得交s；缺一项先追索相应执行方，不由PM代算或跳过。s仅按 {{knowledge:standards/strategy.md}} 汇总已有证据与限制。
6. 最后PM按 {{knowledge:standards/delivery.md}} 对应两个工作项交付，保留各自数据来源、版本、口径、检查和分目标回执。

最低期望：t和g有独立范围及Context，s后置，交付不漏独立报名表。在MA中实际调用t/g，按依赖回收并另行调用validator/s；逐次或并行均须满足同一门槛，不以本地函数假扮角色。
