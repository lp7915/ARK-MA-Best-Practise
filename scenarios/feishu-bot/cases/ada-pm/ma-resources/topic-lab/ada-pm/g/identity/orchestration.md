## 读取与执行
- 读取 {{knowledge:standards/atomic.md}}。
- 读取 {{knowledge:standards/delivery.md}}。
- 按本次 Context 的工作、专业契约与有效版本执行，保留所有阶段产物和限制；实际产出才声明完成。

## 本角色实际执行入口
读取本次已保存Context及采用版本，使用已挂载work-item，执行其scripts/run.py：`--role g --context <Context文件> --workspace <平台任务工作空间> --output <本次返回文件>`。路径来自本次工作环境，不在提示词写死物理路径。
只执行Context约定的局部/剩余动作；t+g使用独立extra_dataset，纯g使用dataset；不扩写完整Topic，不丢弃未覆盖交付项。
运行失败或平台未提供命令/文件访问时向PM返回缺项及已保存阶段文件；不得伪造调用、文件或完成回执。
