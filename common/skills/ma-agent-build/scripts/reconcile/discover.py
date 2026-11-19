"""声明态收集与 MA 现状发现（reconcile 各资源共用）。

Context（dict）字段：
  business_line / employee / emp_dir / stage
  order / packages            智能体包顺序与 agent.json
  cfg                         build-config.json（已展开变量）
  ledger_rows                 台账快照 {resource_key: ledger.Row}
  build_id                    本次构建时间戳
  ma                          现状缓存：{"agent": {name:item}, "environment": {...}, ...}（只读，plan 阶段填充）
"""
from __future__ import annotations

import time

import ma_api
import ledger


def build_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def names(business_line: str, employee: str, order: list[str], knowledge_stores: list[tuple[str, str]]) -> dict:
    """声明态里各资源在 MA 上的期望名字（映射规范 4.3）。

    knowledge_stores: [(pkg_name, root)] 已按全局序号分配的顺序。
    """
    p = f"{business_line}-{employee}"
    return {
        "agent": {pkg: f"{p}-{pkg}" for pkg in order},
        "environment": f"{p}-env",
        "vault": {pkg: f"{p}-vault-{pkg}" for pkg in order},
        "memory_store": {
            (pkg, root): f"{p}-mem-knowledge-{i:02d}"
            for i, (pkg, root) in enumerate(knowledge_stores, start=1)
        },
    }


def fetch_ma_snapshot() -> dict:
    """一次性拉取 MA 上相关集合的全量列表，按 name 建索引（MA 不支持 metadata 过滤，只能全量比对）。"""
    snap: dict[str, dict[str, dict]] = {}
    for coll, key in (("agents", "agent"), ("environments", "environment"),
                      ("vaults", "vault"), ("memory_stores", "memory_store")):
        idx: dict[str, dict] = {}
        for it in ma_api.list_all(coll):
            nm = it.get("name") or it.get("display_name") or ""
            if nm:
                idx[nm] = it
        snap[key] = idx
    return snap


def prefix_of(business_line: str, employee: str) -> str:
    return f"{business_line}-{employee}-"


def adopt_candidates(ctx: dict) -> list[dict]:
    """首次认领：声明态里有、MA 上已按名字存在、但台账没有记录的资源。

    返回 [{"kind","key","name","ma_id","agent","parent_ma_id"}...]，用于预览「补登台账」。
    不修改任何 MA 资源。
    """
    bl, emp = ctx["business_line"], ctx["employee"]
    rows = ctx["ledger_rows"]
    snap = ctx["ma"]
    nm = ctx["names"]
    out: list[dict] = []

    def add(kind, name_key, ma_name, agent=""):
        key = ledger.make_key(bl, emp, kind, name_key)
        row = rows.get(key)
        if row and row.status == "active":
            return
        item = snap.get(kind, {}).get(ma_name)
        if item:
            out.append({"kind": kind, "key": key, "name": ma_name, "ma_id": str(item.get("id") or ""),
                        "agent": agent, "ma_version": str(item.get("version") or "")})

    for pkg in ctx["order"]:
        add("agent", pkg, nm["agent"][pkg], pkg)
        add("vault", pkg, nm["vault"][pkg], pkg)
    add("environment", "", nm["environment"])
    for (pkg, root), ma_name in nm["memory_store"].items():
        add("memory_store", f"{pkg}:{root}", ma_name, pkg)
    return out
