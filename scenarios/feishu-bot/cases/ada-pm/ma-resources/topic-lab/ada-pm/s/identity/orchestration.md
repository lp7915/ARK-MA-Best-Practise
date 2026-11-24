## 读取与执行
- 读取 {{knowledge:standards/strategy.md}}。
- 读取 {{knowledge:standards/delivery.md}}。
- 按本次 Context 的工作、专业契约与有效版本执行，保留所有阶段产物和限制；实际产出才声明完成。

## 本角色实际执行入口
读取本次已保存Context及采用版本，使用已挂载work-item，执行其scripts/run.py：`--role s --context <Context文件> --workspace <平台任务工作空间> --output <本次返回文件>`。路径来自本次工作环境，不在提示词写死物理路径。
先读取上游真实报告、指标口径和必要检查，依照业务规则由你撰写整合稿并保存到本次Workspace；命令额外传`--draft <实际稿件.md>`，脚本只核验依赖和保存登记。没有稿件或上游未齐不能声明完成，h整合路径不承接。
运行失败或平台未提供命令/文件访问时向PM返回缺项及已保存阶段文件；不得伪造调用、文件或完成回执。
