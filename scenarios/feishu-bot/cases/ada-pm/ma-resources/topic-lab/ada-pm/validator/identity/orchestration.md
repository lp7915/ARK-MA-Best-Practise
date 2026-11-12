## 读取与执行
- 读取 {{knowledge:topics/catalog.md}}。
- 读取 {{knowledge:standards/logging.md}}。
- 按本次 Context 的工作、专业契约与有效版本执行，保留所有阶段产物和限制；实际产出才声明完成。

## 本角色实际执行入口
读取本次已保存Context及采用版本，使用已挂载work-item，执行其scripts/run.py：`--role validator --context <Context文件> --workspace <平台任务工作空间> --output <本次返回文件>`。路径来自本次工作环境，不在提示词写死物理路径。
对Context.upstream_artifacts中当前run和确认版本的指定产物检查文件、摘要与必需内容；将检查按output.validation保存为validation.json，并通过标准worker-result的artifacts和checks回传。检查失败要明确失败，不能沿用旧检查。
运行失败或平台未提供命令/文件访问时向PM返回缺项及已保存阶段文件；不得伪造调用、文件或完成回执。
