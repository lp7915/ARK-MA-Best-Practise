# 最低Demo场景与阅读入口

名称：最低Demo场景与阅读入口
适用范围：MA目录Demo的可复用合成样例与最低流程逻辑核对
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位，正式验收人待指定）
状态：静态合成测试材料及期望；不是运行日志或平台验收结论。

本目录提供稳定的合成输入、结构样例和逐步期望，目的是让MA资源包中的角色、知识、脚本、契约与验收能够串联。这里没有实际运行记录，也不声称MA已执行。

1. 先读 {{knowledge:examples/fixture.md}}：唯一合成材料、Context与返回结构。
2. 完整Topic：{{knowledge:examples/normal.md}}，含社媒t与人群t变体。
3. 局部及误路由：{{knowledge:examples/boundary.md}}。
4. 完整Topic加独立局部：{{knowledge:examples/mixed.md}}。
5. 能力外人工：{{knowledge:examples/human.md}}。
6. 缺信息多轮澄清：{{knowledge:examples/clarification.md}}。
7. 无效确认、检查失败：{{knowledge:examples/failure.md}}。
8. 中断接续：{{knowledge:examples/resume.md}}。

各例对应 `acceptance/cases.yaml` 的固定用例。验收人按输入重复执行，核对指定的输出及门槛；结果、模型、环境和真实证据由平台或本地执行方写到包外。尚未运行的正式平台用例结论为“未执行”，不能把下文的预期当作通过。

规范化资源归属：身份/编排/交接在对应角色目录；规则、模板和本样例在knowledge；代码与参数在对应Skill；结构在io/contracts；挂载在registry/agents.json；验收要求在acceptance。样例只引用这些位置，不另建网页或独立模拟目录。

最终执行要求：上传资源经MA构建后，用真实PM和t/g/validator/s执行上述场景；专业输入可以合成，子Agent调用、命令执行和文件返回不能合成。平台前置条件见 {{knowledge:standards/platform.md}}。
