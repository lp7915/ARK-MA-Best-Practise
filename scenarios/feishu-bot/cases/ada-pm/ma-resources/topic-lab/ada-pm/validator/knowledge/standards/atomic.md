# 原子能力边界与模拟参数

名称：原子能力边界与模拟参数
适用范围：MA中PM及所需子智能体；本包合成业务场景
版本：1.2.0
负责人：Ada 项目维护方（模拟岗位；正式责任人待业务方指定）
状态：MA集群Demo运行规则；尚待真实平台构建与验收。

## 来源和实现范围
沿用 AC-01 校验、AC-02 去重、AC-03 指标、AC-04 合并、AC-05 图表、AC-06 保存六个规格。包内 atomic-ops 是本员工自有模拟 Skill，不伪造 platform.* 发布能力或平台注册记录。
稳定规则参数在 atomic-ops 的 references/parameters.json，支持范围在 SKILL.md；六份原始规格供比对，原规格全集不等于本次实现全集。不支持的参数明确报错，不静默回退。
模拟默认：校验 reject_row、normalize=false；去重 exact、key_fields=[id]、survivor=first；指标 count 按 region 分组、口径必填、null_policy=skip；合并 union、type_conflict=fail、provenance_field=_batch；图表 bar/svg、960×540；保存本地 fs、append、无自动清理。参数是便于复现的模拟配置，不是已确认生产阈值。
每个动作产出标准回执，输入不被修改；保存由 AC-06 负责。业务标准与技术支持范围分别检查。真实取数/模型标注另需正式工程，不由这些纯变换推定已拥有。
