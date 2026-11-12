# Demo交付范围与资源入口

名称：Demo交付范围与资源入口
适用范围：MA规范目录Demo、PM及各子角色的资源定位
版本：1.2.0
负责人：Ada 项目维护方（Demo岗位；正式责任人待指定）
状态：稳定资源与合成期望；正式平台执行未发生。

## 本次交付
主交付只有ma-resources内一位数字员工的资源目录。先创建原流程串联所需的岗位提示词、业务规则、模板、Topic输入/输出/交互/工程描述、原子动作参数、脚本、结构契约和可复用合成样例，支持平台构建后由真实PM和一层子Agent逐项调用、返回实际文件并完成交付，按最低用例验收。网页、独立模拟服务、构建工程、全量回放和历史备份均不属于本包。

## 唯一归属与阅读顺序
1. identity/pm及subagent内三份文件说明身份、编排与交接；registry/agents.json显式登记挂载，一位员工只有pm入口。
2. 知识只在knowledge.yaml声明的目录内。Topic契约见 {{knowledge:topics/catalog.md}}，原子边界见 {{knowledge:standards/atomic.md}}。
3. 合成输入、逐步期望从 {{knowledge:examples/index.md}} 进入；空模板在templates，填充件由运行空间承载。样例不会自动变成一次运行结果。
4. 代码、参数和宿主内部动作接口在对应skills目录。pm-orchestrator提供原版路由入口；t/g/validator/s各自在其真实Agent执行域调用work-item，原子动作依赖atomic-ops；不使用同进程假扮子角色的模拟引擎。
5. 输入、Context、阶段返回、产物和交付的结构在io/contracts；acceptance/cases.yaml列最低验收输入和预期，实际验收回执不回写资源包。
6. tools当前只说明“无外部工具”，registry/tools.json及connections.yaml为空。消息接收、路由、保存和回传是宿主内部动作，不用虚假的外部工具声明代替。

## 运行与待接入边界
当次输入、采用确认单、Context、阶段产物、日志和实际交付回执，在包外Agent Workspace的tasks/runs下创建；Team/Project共享按授权进行。个人/项目Memory有稳定模板及采用规则，本包不配置员工共享长期记忆库，不为凑目录创建memory空壳。
不引用未核实的平台注册能力；skills清单仅登记包内自有能力。业务线和员工ID为建议值，真实负责人、模型、正式宿主绑定、存储与容量上限由平台确认。本地结构/最低规则通过不等于MA构建、模型质量、飞书或业务接受已通过。

平台构建与真实调用要求见 {{knowledge:standards/platform.md}}；包内脚本可离线自检，实际子Agent创建、调用与回传必须在MA上按同一用例验收。
