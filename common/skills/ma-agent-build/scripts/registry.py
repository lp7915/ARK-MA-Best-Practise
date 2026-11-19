#!/usr/bin/env python3
"""原子能力注册表读写（MVP：飞书多维表格 via bitable API）。

用应用身份读写注册表 4 张表（能力/版本/引用/引用历史），为 ma-agent-build 提供
「登记版本 / 解析引用」能力。字段与 address 结构见《原子能力注册表设计》§3。

地址结构（address，JSON 字符串，存版本表的文本字段）：
  - agent: {"package_url","sha256","role","visibility","ma_agent_id","ma_agent_version"}
  - skill: {"repo","path","commit","ma_skill_id","ma_skill_version"}

身份从环境变量读，不硬编码敏感值：
  MA_REGISTRY_APP_ID / MA_REGISTRY_APP_SECRET
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

from packaging.version import Version
from packaging.specifiers import SpecifierSet

APP_TOKEN = "ZRg5bp8lZavDRPsq9eQcp32UniO"
TABLE_CAPABILITY = "tblUG358TWYdsnSi"
TABLE_VERSION = "tbld9ld6wFpNv0cR"
TABLE_REF = "tblH3dhx5UIhsfsr"
TABLE_REF_HISTORY = "tbl1xTG2Nr1L8a9S"

BASE = "https://open.feishu.cn/open-apis"

_token: str | None = None


def _app_id() -> str:
    v = os.environ.get("MA_REGISTRY_APP_ID", "")
    if not v:
        raise RuntimeError("缺少环境变量 MA_REGISTRY_APP_ID（注册表应用 app_id）")
    return v


def _app_secret() -> str:
    v = os.environ.get("MA_REGISTRY_APP_SECRET", "")
    if not v:
        raise RuntimeError("缺少环境变量 MA_REGISTRY_APP_SECRET（注册表应用 app_secret）")
    return v


def get_token() -> str:
    global _token
    if _token:
        return _token
    req = urllib.request.Request(
        f"{BASE}/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": _app_id(), "app_secret": _app_secret()}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if d.get("code") != 0:
        raise RuntimeError(f"换 tenant token 失败: {d.get('msg')}")
    _token = d["tenant_access_token"]
    return _token


def _api(method: str, path: str, body=None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"code": e.code, "msg": e.read().decode()[:300]}


def list_records(table_id: str, page_size: int = 200) -> list[dict]:
    """读整表记录（MVP 数据量小，分页拉全）。"""
    out: list[dict] = []
    page_token = ""
    while True:
        q = f"/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size={page_size}"
        if page_token:
            q += f"&page_token={page_token}"
        d = _api("GET", q)
        data = d.get("data") or {}
        out.extend(data.get("items") or [])
        if not data.get("has_more") or not data.get("page_token"):
            break
        page_token = data["page_token"]
    return out


def get_capability(atomic_id: str, type_: str | None = None) -> dict | None:
    """按 atomic_id 找能力记录（返回 {record_id, fields}）。"""
    for r in list_records(TABLE_CAPABILITY):
        f = r.get("fields", {})
        if f.get("atomic_id") == atomic_id and (type_ is None or f.get("type") == type_):
            return {"record_id": r["record_id"], "fields": f}
    return None


def list_versions(capability_record_id: str) -> list[dict]:
    """列某能力的全部版本记录。关联字段读出形如 [{"record_ids":[...], "text":...}]。"""
    out = []
    for r in list_records(TABLE_VERSION):
        f = r.get("fields", {})
        caps = f.get("capability") or []
        hit = any(
            isinstance(c, dict) and capability_record_id in (c.get("record_ids") or [])
            for c in caps
        )
        if hit:
            out.append({"record_id": r["record_id"], "fields": f})
    return out


def register_capability(atomic_id: str, owner_topic: str, type_: str, display_name: str, name_en: str = "", status: str = "active") -> str:
    """确保能力表有该原子能力，返回 record_id。"""
    existing = get_capability(atomic_id, type_)
    if existing:
        return existing["record_id"]
    body = {"fields": {
        "atomic_id": atomic_id,
        "owner_topic": owner_topic,
        "type": type_,
        "display_name": display_name,
        "name_en": name_en,
        "status": status,
    }}
    d = _api("POST", f"/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_CAPABILITY}/records", body)
    data = d.get("data") or {}
    rid = data.get("record", {}).get("record_id") or data.get("record_id")
    if not rid:
        raise RuntimeError(f"登记能力 {atomic_id} 失败: {d.get('msg')}")
    return rid


def register_version(capability_record_id: str, version: str, address: dict, fingerprint: str, status: str = "released") -> str:
    """版本表新增一条（append-only）。返回 version record_id。"""
    maj, minor, patch = _parse_semver(version)
    fields: dict = {
        "capability": [capability_record_id],  # 关联字段：record_id 列表
        "version": version,
        "ver_major": maj,
        "ver_minor": minor,
        "ver_patch": patch,
        "address": json.dumps(address, ensure_ascii=False),
        "fingerprint": fingerprint,
        "status": status,
    }
    d = _api("POST", f"/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_VERSION}/records", {"fields": fields})
    data = d.get("data") or {}
    rid = data.get("record", {}).get("record_id") or data.get("record_id")
    if not rid:
        raise RuntimeError(f"登记版本 {version} 失败: {d.get('msg')}")
    return rid


def _parse_semver(v: str) -> tuple[int, int, int]:
    ver = Version(v)
    return ver.major, ver.minor, ver.micro  # micro = patch


def _range_to_specifier(r: str) -> SpecifierSet:
    """业务版本范围 → packaging SpecifierSet。支持 ^ ~ >= <= > < == != 和逗号分隔。"""
    r = (r or "").strip()
    if not r or r == "*":
        return SpecifierSet("")
    if r.startswith("^"):
        base = r[1:].strip()
        ver = Version(base.split("-")[0])
        return SpecifierSet(f">={base},<{ver.major + 1}.0.0")
    if r.startswith("~"):
        base = r[1:].strip()
        ver = Version(base.split("-")[0])
        parts = base.split(".")
        if base.count(".") >= 2:
            upper = f"{ver.major}.{ver.minor + 1}.0"
        else:
            upper = f"{ver.major + 1}.0.0"
        return SpecifierSet(f">={base},<{upper}")
    # >= <= > < == != 或逗号组合或精确版本
    return SpecifierSet(r)


def resolve_version(capability_record_id: str, range_: str) -> dict | None:
    """从该能力的 released 版本里，取匹配 range 的最高语义版本，返回 {version, address, fingerprint, record_id}。"""
    best: dict | None = None
    spec = _range_to_specifier(range_)
    for v in list_versions(capability_record_id):
        f = v.get("fields", {})
        if f.get("status") != "released":
            continue
        ver = str(f.get("version") or "")
        if not ver:
            continue
        try:
            pv = Version(ver)
            if pv in spec and (best is None or pv > Version(best["version"])):
                addr_raw = f.get("address") or "{}"
                try:
                    addr = json.loads(addr_raw) if isinstance(addr_raw, str) else addr_raw
                except (TypeError, ValueError, json.JSONDecodeError):
                    addr = {}
                best = {"version": ver, "address": addr, "fingerprint": f.get("fingerprint", ""), "record_id": v["record_id"]}
        except Exception:
            continue
    return best


def register_agent_version(atomic_id: str, owner_topic: str, semver: str, role: str, visibility: str,
                            ma_agent_id: str, ma_agent_version: int, package_url: str, sha256: str, fingerprint: str) -> str:
    """登记一个 agent 语义版本：确保能力 + 版本表 append 一条（address 含 ma_agent_id/version）。

    幂等：同一语义版本 + 同一 fingerprint 且已 released 的不重复登记；同版本但内容变则提示业务方升版本。
    """
    cap_id = register_capability(atomic_id, owner_topic, "agent", atomic_id.split(".")[-1], atomic_id.split(".")[-1])
    address = {
        "package_url": package_url,
        "sha256": sha256,
        "role": role,
        "visibility": visibility,
        "ma_agent_id": ma_agent_id,
        "ma_agent_version": str(ma_agent_version),
    }
    same_ver = []
    for v in list_versions(cap_id):
        f = v.get("fields", {})
        if f.get("version") != semver:
            continue
        same_ver.append(v)
        if f.get("fingerprint") == fingerprint and f.get("status") == "released":
            return v["record_id"]  # 完全一致，幂等跳过
    if same_ver:
        print(f"  [warn] {atomic_id} v{semver} 内容变化但语义版本未升（已有 {len(same_ver)} 条同名记录），仍然登记新版本")
    return register_version(cap_id, semver, address, fingerprint)


def resolve_agent_ref(atomic_id: str, range_: str) -> tuple[str, int] | None:
    """解析 agent 引用 → (ma_agent_id, ma_agent_version)。"""
    cap = get_capability(atomic_id, "agent")
    if not cap:
        return None
    v = resolve_version(cap["record_id"], range_)
    if not v:
        return None
    addr = v["address"]
    return (addr.get("ma_agent_id"), int(addr.get("ma_agent_version") or 0)) if addr.get("ma_agent_id") else None


def resolve_skill_ref(atomic_id: str, range_: str) -> tuple[str, str] | None:
    """解析 skill 引用 → (skill_id, skill_version)。"""
    cap = get_capability(atomic_id, "skill")
    if not cap:
        return None
    v = resolve_version(cap["record_id"], range_)
    if not v:
        return None
    addr = v["address"]
    return (addr.get("ma_skill_id"), addr.get("ma_skill_version")) if addr.get("ma_skill_id") else None


if __name__ == "__main__":
    # 自检：读 ada-pm 的 agent 能力 + 版本
    import sys
    for aid in sys.argv[1:]:
        cap = get_capability(aid, "agent")
        print(f"能力 {aid}:", "找到" if cap else "未找到", cap["record_id"] if cap else "")
    cap = get_capability("platform.report-cover", "skill")
    if cap:
        vers = list_versions(cap["record_id"])
        print(f"skill platform.report-cover 版本数:", len(vers))