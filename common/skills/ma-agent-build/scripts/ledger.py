#!/usr/bin/env python3
"""资源映射台账读写（飞书多维表格「MA资源映射台账」）。

台账是「索引」、MA 是「事实」：记录每个数字员工在 MA 上的各个资源及其 ID，供 plan 阶段
按 ID 直接 GET 现状，并识别孤儿。唯一键 resource_key = `<业务线>/<员工>/<kind>/<稳定名>`。

约定：
- 台账表结构/字段冻结，记录由构建器写入；
- 删除不物理删行：status 置为 deleted 保留审计；
- fingerprint 只存内容指纹（凭证用加盐 sha256），绝不存明文。

身份复用 registry.py 的飞书应用（MA_REGISTRY_APP_ID / MA_REGISTRY_APP_SECRET）。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from registry import _api, get_token  # noqa: F401  复用飞书 token 与请求封装

LEDGER_APP_TOKEN = "R5HfbbwT7a3WMSs7pkjc8crvnnB"
LEDGER_TABLE = "tbl7BQiIiB8x9333"

KINDS = ("agent", "environment", "vault", "credential", "memory_store", "memory_entry", "skill")


def make_key(business_line: str, employee: str, kind: str, name: str) -> str:
    """台账唯一键。name 是稳定名：agent→智能体 ID；environment→空；memory_entry→`<库序号>:<path>` 等。"""
    base = f"{business_line}/{employee}/{kind}"
    return f"{base}/{name}" if name else base


def salted_fingerprint(business_line: str, employee: str, secret_name: str, value: str) -> str:
    """凭证值指纹：盐为 `业务线/员工/secret_name`，只存前 16 位，不可逆向还原明文。"""
    salt = f"{business_line}/{employee}/{secret_name}"
    return hashlib.sha256((salt + "\x00" + value).encode("utf-8")).hexdigest()[:16]


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Row:
    record_id: str
    key: str
    fields: dict

    @property
    def kind(self) -> str:
        return str(self.fields.get("kind") or "")

    @property
    def ma_id(self) -> str:
        return str(self.fields.get("ma_id") or "")

    @property
    def status(self) -> str:
        return str(self.fields.get("status") or "")

    @property
    def fingerprint(self) -> str:
        return str(self.fields.get("fingerprint") or "")


def _records_path() -> str:
    return f"/bitable/v1/apps/{LEDGER_APP_TOKEN}/tables/{LEDGER_TABLE}/records"


def _text(v) -> str:
    """多维表格文本字段读出可能是 str 或 [{"text":..}] 富文本，统一成 str。"""
    if isinstance(v, list):
        return "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in v)
    return "" if v is None else str(v)


def load_employee(business_line: str, employee: str) -> dict[str, Row]:
    """读某员工的全部台账行，返回 {resource_key: Row}。含 status=deleted 的行（用于识别需「复活」的键）。"""
    out: dict[str, Row] = {}
    page_token = ""
    while True:
        q = f"{_records_path()}?page_size=200" + (f"&page_token={page_token}" if page_token else "")
        d = _api("GET", q)
        if d.get("code") not in (0, None):
            raise RuntimeError(f"读取台账失败: {d.get('msg')}")
        data = d.get("data") or {}
        for r in data.get("items") or []:
            f = {k: (_text(v) if k not in ("updated_at",) else v) for k, v in (r.get("fields") or {}).items()}
            if f.get("business_line") == business_line and f.get("employee") == employee:
                key = f.get("resource_key", "")
                if key:
                    out[key] = Row(record_id=r["record_id"], key=key, fields=f)
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = data["page_token"]
    return out


def upsert(rows: dict[str, Row], *, business_line: str, employee: str, kind: str, name: str,
           resource_name: str, ma_id: str, agent: str = "", ma_version: str = "",
           fingerprint: str = "", parent_ma_id: str = "", stage: str = "dev",
           build_id: str = "", note: str = "") -> Row:
    """按 resource_key 新增或更新一行；status 置 active。更新后同步回传入的 rows 缓存。"""
    key = make_key(business_line, employee, kind, name)
    fields = {
        "resource_key": key,
        "business_line": business_line,
        "employee": employee,
        "agent": agent,
        "kind": kind,
        "resource_name": resource_name,
        "ma_id": ma_id,
        "ma_version": str(ma_version or ""),
        "fingerprint": fingerprint,
        "parent_ma_id": parent_ma_id,
        "stage": stage,
        "status": "active",
        "managed_by": "ma-build",
        "last_build_id": build_id,
        "updated_at": int(time.time() * 1000),
        "note": note,
    }
    existing = rows.get(key)
    if existing:
        d = _api("PUT", f"{_records_path()}/{existing.record_id}", {"fields": fields})
        rid = existing.record_id
    else:
        d = _api("POST", _records_path(), {"fields": fields})
        rid = ((d.get("data") or {}).get("record") or {}).get("record_id", "")
    if d.get("code") not in (0, None) or not rid:
        raise RuntimeError(f"写台账失败 {key}: {d.get('msg')}")
    row = Row(record_id=rid, key=key, fields={k: _text(v) if k != "updated_at" else v for k, v in fields.items()})
    rows[key] = row
    return row


def mark_deleted(rows: dict[str, Row], key: str, build_id: str = "", note: str = "") -> None:
    """资源已从 MA 删除：台账行 status→deleted，保留审计，不物理删除。"""
    row = rows.get(key)
    if not row:
        return
    fields = {"status": "deleted", "last_build_id": build_id, "updated_at": int(time.time() * 1000)}
    if note:
        fields["note"] = note
    d = _api("PUT", f"{_records_path()}/{row.record_id}", {"fields": fields})
    if d.get("code") not in (0, None):
        raise RuntimeError(f"标记删除失败 {key}: {d.get('msg')}")
    row.fields.update({"status": "deleted"})
