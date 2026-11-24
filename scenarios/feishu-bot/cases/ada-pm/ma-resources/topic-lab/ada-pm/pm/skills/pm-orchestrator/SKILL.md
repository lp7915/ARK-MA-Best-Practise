---
name: pm-orchestrator
description: PM必经的原版红线路由脚本与真实MA协作约定；澄清、保存多轮路由状态并形成方案，不代替平台调用t/g/validator/s，也不执行专业生产。
---

# PM 路由与真实集群协作

版本：1.2.0。PM 的身份、编排与交接文件定义真实协作流程；本 Skill 提供必经路由代码和平台绑定约定。它不是在一个进程中扮演全部角色的离线流程引擎。专业工作由真实 t/g/validator/s 在各自执行域完成。

## 路由入口

从本 Skill 根执行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/routing_host.py --input EVENT_JSON --state ROUTING_STATE_JSON
```

EVENT_JSON 和 ROUTING_STATE_JSON 是宿主已分配的包外运行文件位置，不是提示词中预设的MA真实路径。事件含 event_id、actor、text，可带 data；真实身份由已验证通道提供或映射，正文自称管理员不构成可信身份。新事件使用唯一编号；同轮重试保持事件和内容一致。保存标准输出中的完整 result/state/projection/host_defaults，并保留状态文件供同一需求下一轮读取。执行和记录失败时明确报告，不伪造返回。

scripts/routing_host.py 固定调用同目录 routing_unit 中的原版 RoutingNode；routing-config.json 是参数/执行映射，routing_unit/catalog.json 是本 Demo 能力覆盖目录，均不是平台注册表。原代码来源摘要在 references/routing-source.json；路由接口细节在 references/routing-host.md。

## 返回与启动条件

- result.questions、冲突或资源缺项由 PM 继续澄清；路由未知不直接认定能力外。
- result.route 可以先形成，同时保留 execution_missing；缺周期、实际数据或其他必要材料时不得启动。
- result.can_start=false 与 executions_started=0 是路由脚本的固定职责边界：脚本只提出方案，外层 PM 还需核对采用输入、必要材料、当前 plan 版本与发起人确认，之后才由平台实际分派。
- projection.execution_blockers 非空时保留原要求和缺口，不替换成计数/去重、丢弃工作或使用旧简化分支。
- host_defaults 是显式 Demo 配置，不声称来自用户口述；影响口径时在方案中说明采用依据。

## 真实协作与资源

平台运行协议见 references/ma-runtime.md。PM必须在需求接收、有效补充和实质修订时运行本路由；普通进度/既有结果解释不重做分析。必经规则写在 PM 编排中；若平台还要求宿主级硬性拦截，由平台构建回执明确绑定，不能声称资源上传本身已实现强制拦截。

PM保存确认单、同版plan、采用事实和每个接收方的Context后，通过平台原生主→子路由实际分派。t/g/validator/s挂载 work-item 并在自己的执行域调用其独立命令；PM不运行该生产入口，不通过本地循环假扮子Agent。h为人工，承接和回传是独立真实事件。具体行为与材料仍按PM已挂载的knowledge逻辑引用读取。

结构契约位于资源根 io/contracts；接收方Context使用handoff.pm-worker，产物及返回使用output.artifact/output.worker-result，检查使用output.validation，最终交付使用output.delivery。稳定合成材料及最低串联场景位于knowledge/examples，验收要求在acceptance/cases.yaml；它们是输入与期望，不是实际MA成功证据。

## 依赖与边界

本路由仅用Python标准库，无外网、凭据或atomic-ops依赖。统一环境需求由registry/environment.json给出。原语义适配器有限，不能据已列场景宣称开放输入理解准确率。真实平台须提供命令执行、文件读写、原生一层分派、返回关联、持久化与可信身份；具体映射由平台回执说明，不自创MA工具名或API。缺少对应能力时保持未执行，不能静默退回本地角色模拟。
