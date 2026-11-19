"""reconcile：全资源「声明 vs 现状」比对的统一数据结构与报告渲染。

设计要点（见 common/docs/analyst-env/ma-agent-build-全资源声明式覆盖方案.md §3、§4）：
- 预览与执行共用同一个 compute_diff：只读、确定性，执行阶段重新计算，不落 plan 文件；
- 每类资源（agent / environment / vault / credential / memory_store / memory_entry）各自产出 Action 列表；
- 动作种类：create / update / delete / replace / adopt / noop。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# 动作含义
CREATE = "create"    # 声明有、MA 无 → 新建
UPDATE = "update"    # 声明与现状不一致 → 原地更新
DELETE = "delete"    # 台账有、声明无（孤儿 / 集合内元素被移除）→ 删除
REPLACE = "replace"  # 结构性字段变化，只能删旧建新（如凭证 secret_name）
ADOPT = "adopt"      # MA 上已存在、台账未记录 → 认领并补登台账（不改 MA 资源）
NOOP = "noop"        # 无变化

ACTION_LABEL = {
    CREATE: "新增", UPDATE: "修改", DELETE: "删除",
    REPLACE: "替换", ADOPT: "补登", NOOP: "无变化",
}


@dataclass
class Action:
    """一条资源动作。key 对应台账 resource_key；ma_id 为现状资源 ID（create 时为空）。"""

    kind: str                      # agent / environment / vault / credential / memory_store / memory_entry
    key: str                       # 台账 resource_key
    op: str                        # CREATE / UPDATE / ...
    name: str = ""                 # MA 上的资源名（便于阅读）
    ma_id: str = ""
    parent_ma_id: str = ""         # 下属关系：条目→知识库，凭证→vault
    detail: str = ""               # 变化摘要（如 "system, skills"）
    warnings: list[str] = field(default_factory=list)
    payload: dict = field(default_factory=dict)  # 执行所需数据（desired 配置等），不进报告
    group: str = ""                # 报告里的分组标题（如 "vault pm"）


@dataclass
class Diff:
    actions: list[Action] = field(default_factory=list)

    def add(self, action: Action) -> None:
        self.actions.append(action)

    def extend(self, actions: list[Action]) -> None:
        self.actions.extend(actions)

    def by_op(self, op: str) -> list[Action]:
        return [a for a in self.actions if a.op == op]

    def changes(self) -> list[Action]:
        """需要真正写 MA / 台账的动作（排除 noop）。"""
        return [a for a in self.actions if a.op != NOOP]

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for a in self.actions:
            c[a.op] = c.get(a.op, 0) + 1
        return c


def render_report(diff: Diff, header: str) -> str:
    """文本预览报告：按 kind 分组，变化项逐条列出，noop 只汇总数量。"""
    lines = [header]
    order = ["agent", "environment", "vault", "credential", "memory_store", "memory_entry"]
    kind_title = {
        "agent": "agent", "environment": "environment", "vault": "vault",
        "credential": "凭证", "memory_store": "知识库", "memory_entry": "知识库条目",
    }
    for kind in order:
        items = [a for a in diff.actions if a.kind == kind]
        if not items:
            continue
        for a in items:
            if a.op == NOOP:
                continue
            tail = f"  {a.detail}" if a.detail else ""
            lines.append(f"  {kind_title[kind]:<8} {a.name or a.key:<42} {ACTION_LABEL[a.op]}{tail}")
            for w in a.warnings:
                lines.append(f"             ⚠ {w}")
    noop = len(diff.by_op(NOOP))
    c = diff.counts()
    summary = " · ".join(f"{ACTION_LABEL[op]} {c[op]}" for op in (CREATE, UPDATE, REPLACE, DELETE, ADOPT) if c.get(op))
    lines.append(f"汇总：{summary or '无变更'} · 无变化 {noop}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 资源 reconciler 约定
# 每个资源模块（agent.py / environment.py / ...）导出两个函数：
#   plan(ctx) -> list[Action]     只读：读声明、台账、MA 现状，返回动作列表
#   apply(ctx, actions) -> dict   执行：按 actions 写 MA，并 upsert 台账，返回产出的资源 ID
# ctx 是一个 dict（Context），携带声明态、台账快照与共享配置，见 build.py。
PlanFn = Callable[[dict], "list[Action]"]
ApplyFn = Callable[[dict, "list[Action]"], dict]


def compute_diff(ctx: dict, planners: "list[PlanFn]") -> Diff:
    """预览与执行共用：依次调用各资源 plan，汇总成 Diff。必须只读、确定性。"""
    diff = Diff()
    for fn in planners:
        diff.extend(fn(ctx))
    return diff
