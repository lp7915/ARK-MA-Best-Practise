# 局部去重与Topic误路由反例

名称：局部去重与Topic误路由反例
适用范围：MA目录Demo的可复用合成样例与最低流程逻辑核对
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位，正式验收人待指定）
状态：静态合成测试材料及期望；不是运行日志或平台验收结论。

## DEMO-03 只对评论去重
输入采用 {{knowledge:examples/fixture.md}} 的social_event材料，对象、周期、用途保留，文字改成“只对评论按id去重，不做完整报告”，`data.topic=null`、`data.action="deduplicate"`、`data.human=false`。

1. 按 {{knowledge:standards/routing.md}} 判断所求产物是局部去重表，不因“评论”命中完整Topic；预期g，不能派t。
2. 采用 {{knowledge:standards/atomic.md}} 的明确id键和exact/first模拟参数。缺键或材料时补问/明确采用配置，不能宣称用户说过默认值。
3. 发起人确认当前版本后，PM保存面向g的Context，限制为指定表的字段校验与去重；不套用完整Topic的专业产物要求。
4. g执行校验、去重并保存原始依据、剔除明细、去重表和回执，按 `output.worker-result` 回PM。预期5原始→4有效→3去重，只做去重不生成完整社媒报告。
5. 本例简单g按契约没有强制validator节点；若上层明确约定检查则先完成。PM在g完整回传后交s做相称的短结果整合，s不生成评论洞察或扩项。
6. PM按 {{knowledge:standards/delivery.md}} 交付局部结果及来源，外部目标未执行分别登记。

最低期望：g→s→PM，t从未承接；采用输入、参数、去重表和交付条目一致。已有结果的“这个数怎么算”沿原产物解释，不新增分析或重跑路由。
