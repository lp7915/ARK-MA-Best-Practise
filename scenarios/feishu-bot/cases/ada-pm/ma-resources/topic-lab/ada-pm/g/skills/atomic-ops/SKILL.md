---
name: atomic-ops
description: 对标准数据信封执行显式校验、exact 去重、count/sum/avg 指标、union 合并、bar SVG 和本地回执保存；不支持抓取或开放式分析。
---

# 原子动作模拟实现

版本 1.2.0，仅本员工本地模拟。实现入口 scripts/atomic.py，Python 3.9+，只使用标准库；从命令行读取一个 JSON 文件并输出 JSON，或作为模块调用 execute(action, payload)。输入输出均返回 status、output、receipt；标准信封保留 schema/rows/meta。

支持：AC-01 required 与 string/integer/number/enum、reject_row/annotate_only，不做 normalize、跨字段表达式；AC-02 exact + first/last，不做 fuzzy/merge；AC-03 dimensions 与 count/sum/avg、caliber 必填、null_policy=skip，不做 ratio/加权；AC-04 union+type_conflict=fail，不隐式去重；AC-05 bar/svg，数值 y、960×540 默认；AC-06 fs/append 保存回执、脱敏常见秘密字段，不支持云存储、overwrite 或自动删除。超范围参数明确失败。原规格全集在 references，仅作对照，未支持项不能宣称已实现。

各动作可直接采用的参数片段见 references/parameters.json；补入dataset/batches或receipts/output_root，不把参数片段误当完整输入。无外网和凭据。AC-01—05 纯变换，不落盘；AC-06 只能在调用者明确给出的运行输出根内保存，禁止路径逃逸。脚本不处理任何 MA 提示词占位符。
