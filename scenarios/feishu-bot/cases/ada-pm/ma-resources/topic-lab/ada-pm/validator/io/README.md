# 输入输出契约导航

契约供结构校验与系统对接，不当作提示词注入。所有文件为 JSON Schema 2020-12，版本 1.2.0。

- handoff.pm-worker.json
- input.envelope.json
- input.event.json
- input.request.json
- output.artifact.json
- output.delivery.json
- output.state.json
- output.validation.json
- output.worker-result.json

材料字段、Scope 与专业口径仍需业务校验；结构正确不等于分析正确。

validator返回统一的output.worker-result：artifacts中登记实际validation.json，checks中携带其相同检查对象；该文件的内容使用output.validation。PM必须保留完整返回，并把需要的t/g/validator结果文件路径放入s的Context.scope.upstream_results。
