# 社媒评论分析工程替身

名称：社媒评论分析工程替身
适用范围：仅本地替身；不得替代真实工程
版本：1.2.0
负责人：Ada 项目维护方（模拟岗位；正式责任人待业务方指定）
状态：本地模拟采用，不能据此认定生产已上线。

执行顺序：复用核验→AC-04 合并→AC-01 校验→AC-02 去重→AC-03 分地区 count→AC-05 SVG→阶段报告→PM 分派 validator→PM 分派 s→PM 交付。每个产物形成就调用保存和本地复制。原子方法与支持参数见 atomic-ops；专业准确性另行验收。

真实调用入口：由t Agent在自身执行域读取已保存Context，调用挂载work-item的scripts/run.py（--role t --context <本次Context文件> --workspace <平台任务工作空间> --output <本次返回文件>）。脚本复用atomic-ops，逐阶段保存并返回实际产物；不创建或代替validator/s。PM收到后另行分派真实validator，检查通过后才交真实s。
