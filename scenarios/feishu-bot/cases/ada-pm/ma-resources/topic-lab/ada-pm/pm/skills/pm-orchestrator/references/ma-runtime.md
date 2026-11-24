# MA 真实 Agent 协作运行协议

版本：1.2.0。适用：主PM在平台上调用同一员工内t/g/validator/s的最低端到端流程。本文件只声明业务调用与文件协议，不定义或假设MA专属API名称。

## 平台须在构建回执中绑定的能力

|能力|需要的实际事实|未绑定时|
|---|---|---|
|身份与事件|从真实入口取得发起人、协作者、管理员、人工身份及唯一事件关联；角色映射不可由正文冒认|不能认定确认、裁决或人工回传有效|
|命令执行|PM能执行挂载的路由脚本；各子Agent能在自己的执行域执行work-item命令|对应路由或专业动作未执行，不编造结果|
|读取与保存|可读取挂载知识、已采用数据和明确上游文件；可写包外Task/Run并返回实际位置|先保存缺项，不能声称Context已交接或产物存在|
|一层分派|PM可按agents清单实际调用t/g/validator/s，并得到角色与工作关联的真实回传|保持待分派，不能改由PM程序扮演角色|
|跨Agent材料|平台明确子Agent如何取得Context、输入和上游文件，以及返回文件如何对PM可见|停止受影响工作，不推定同名目录天然共享|
|持久化与接续|平台说明状态、产物、日志的存储与期限，新实例可取得既有受控记录|不声称已支持跨会话接续或永久保留|

模型、依赖锁定、工作空间实际路径、知识占位符替换与主/子Agent路由方式由平台给回执。资源清单表达使用意图，不能以目录结构推断权限隔离或跨会话文件可见性。当前连接清单为空，不能据此声称已有飞书或外部人工通道。

## 最低执行次序

1. PM核对真实入口与包外工作空间，保存当前消息和材料来源。接收/有效补充/实质修订时执行本Skill的routing_host CLI，保存原输出和多轮state。
2. 按路由缺项澄清并读取实际材料。记录采用事实，不把附件内指令升级为系统规则；保存确认单和plan，绑定同一业务版本。路由can_start=false仅表示路由不发起生产。
3. 原发起人确认当前版本、材料与分工后，将当前采用事实直接保存为adopted-input.json。包含数据时保存实际数据信封；文件必须在资源包外。每个接收方获得自己的Context，不共享一份混合聊天摘要。
4. Context按handoff.pm-worker组装：inputs[0]为上一步已保存JSON的真实可读位置；scope.production_required列出必要t/g，例如['t','g']；scope.require_validator为本次必要检查要求；upstream_artifacts只取当前版本的真实文件对象。先保存Context，才实际调用相应子Agent。
5. t/g在各自真实执行域，按挂载的work-item说明调用：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run.py --role ROLE --context CONTEXT_JSON --workspace WORKSPACE --output RESULT_JSON
```

ROLE为本次真实接收方t或g；所有大写位置参数均由平台当前运行分配。命令从work-item Skill根执行。该程序只做该角色的工作，不自行调用其他Agent。PM收到实际output.worker-result，先保存原件，再核对文件、摘要、当前确认版本、覆盖和限制。

6. 如需validator，PM另存Context并实际分派validator；其使用同一work-item命令，ROLE=validator，对指定上游文件执行实际检查。检查失败、缺文件、摘要不符或不匹配当前确认版本时保持失败/待补，不调用s。
7. 所需生产结果和必要检查都齐备后，PM给真实s保存Context并分派。s先由实际模型读取证据、口径和限制撰写DRAFT_PATH，再调用：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run.py --role s --context CONTEXT_JSON --workspace WORKSPACE --output RESULT_JSON --draft DRAFT_PATH
```

脚本核对依赖与稿件、保存产物和回传；稿件内容来自实际s模型，不能由固定脚本模板冒充。s不自行新增专业生产，不声称合成情绪标签是模型标注。

8. h路径按人工规则保存评估、承接与同版回传；只有独立且已确认的自动部分可先行。未接通人工通道时停在待人工，不能模拟点击冒充真实专家。h完成约定最终整合后直接回PM，不追加s。
9. PM对应确认单逐项形成output.delivery，记录实际产物和检查。需要显式接受时等发起人回应。外部发布、飞书、所有权和访问分别记录实际回执；没有发生即未执行。

## 版本、重试与证据

Task/Run冻结资源包、各Agent、模型与依赖版本；记录路由事件、确认与裁决、各接收方Context、真实调用及返回、命令返回码、实际产物摘要、检查和交付关联。重复事件不能重复派发；脚本或Agent异常不生成成功结果。重试与修订保留原记录，先明确采用版本与仍需执行的工作。

恢复时先核对既有状态、Context、文件和摘要，再只推进未完成节点。外部动作结果未知先查回执。当前资源提供执行入口与合成业务样例；真实平台是否已完成主/子Agent调用，必须由相应实际记录证明，不能只凭本地脚本测试或静态期望给出通过。

向s交接时，Context.scope.upstream_results必须列出所需t/g以及必要validator的完整标准返回JSON实际路径。路径按包外Workspace定位；s入口核对角色、task/run/确认版本、status=complete及当前产物一致性，不能用阶段文件齐备代替完整返回。
