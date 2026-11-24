# 完整Topic正常路径：社媒与人群

名称：完整Topic正常路径：社媒与人群
适用范围：MA目录Demo的可复用合成样例与最低流程逻辑核对
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位，正式验收人待指定）
状态：静态合成测试材料及期望；不是运行日志或平台验收结论。

## DEMO-01 社媒t
输入采用 {{knowledge:examples/fixture.md}} 的 `social_event`；先按 {{knowledge:topics/social/input.md}} 核对对象、周期、用途、材料与列。

1. 原版路由识别完整社媒产品，形成t方案；用户看见确认单及plan的同一版本。规则沿 {{knowledge:standards/routing.md}} 和 {{knowledge:standards/confirmation.md}}，本例不调用g重复计算。
2. 请求者对当前版本明确确认。确认前不分派；周期或数据缺失可先形成t方案，仍不可启动。
3. PM按 {{knowledge:standards/context.md}}、{{knowledge:templates/context.md}} 保存只面向t的Context；列出社媒input/output/interaction/engineering契约、唯一采用样本、期望文件和限制，再交t。
4. 真实t Agent沿 {{knowledge:topics/social/engineering.md}} 调用work-item，并用atomic-ops合成工程子集依次产出复用依据、合并/校验/去重数据、地区及情绪count、SVG与阶段报告；形成即保存，各版本不覆盖。预期数值见fixture。
5. t通过 `io/contracts/output.worker-result.json` 回PM，携带文件、摘要、来源、限制。PM随后为validator组装新的Context，只引用本轮指定产物和检查要求；t不自行创建子Agent。
6. 真实validator Agent调用work-item的validator入口，按明确产物核验存在性、内容摘要与必需文件，返回检查记录。未通过时停止后续整合。
7. 所需生产结果和必要检查齐备后，PM才实际调用s按 {{knowledge:standards/strategy.md}} 整合。s模型读取真实报告后撰写整合稿，并用work-item的s入口核验保存；不能生成未有依据的专业判断。
8. PM沿 {{knowledge:standards/delivery.md}} 回收并形成 `io/contracts/output.delivery.json` 交付清单；本地可读副本与飞书/所有权目标分别记录，未发生的外部动作写未执行。要求显式接受时保持待接受直到请求者回应。

最低期望：角色顺序t→validator→s→PM；有效4行、去重3行；Context、阶段数据、产物检查、交付清单相互可追溯。专业报告和真实模型质量另验。

## DEMO-02 人群t变体
采用同一fixture的评论数据只投影id、region两列作为显式合成人群表，保留原5行、重复a2和空id；数据源注明是fixture投影，不是采集的消费者数据。将事件 `data.topic` 改为audience，文字明确“完整人群洞察报告”，其余对象/周期/用途不变。

读取 {{knowledge:topics/audience/input.md}}、{{knowledge:topics/audience/output.md}}、{{knowledge:topics/audience/interaction.md}}、{{knowledge:topics/audience/engineering.md}}，仍按t→validator→s→PM。预期地区count华东2、华北1，不产出缺数据支撑的年龄、性别、消费意图、总体偏好或市场规模。该变体与社媒结果不能冒充两个真实客户样本。
