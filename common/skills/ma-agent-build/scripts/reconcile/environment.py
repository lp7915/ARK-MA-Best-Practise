"""Environment 的声明式 reconcile（映射规范 6.2.4 / 6.3）。

Environment 是唯一「只能有一个」的会话级资源 → 各包 registry/environment.json 需**合并**
（packages / env 并集，冲突阻断）；type / networking / setup_script 等平台侧决策来自 build-config.json。

diff 维度：packages / env / networking / setup_script / (type)。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import ledger
import ma_api
from reconcile import ADOPT, CREATE, NOOP, UPDATE, Action

_PACKAGE_MANAGER_MAP = {"python": "pip", "node": "npm", "system": "apt"}


def _pkg_name(spec: str) -> str:
    """从版本约束串取包名：'pandas>=2.0' -> 'pandas'，'requests[socks]==2' -> 'requests'。"""
    return re.split(r"[<>=!~;\[\s]", str(spec).strip())[0] or str(spec).strip()


def merge_environments(pkg_dirs: list[Path]) -> dict:
    """合并各包 registry/environment.json：dependencies→packages、env_vars→env。

    同包不同版本要求、同名 env 不同值 → 冲突阻断并指出两个来源包。
    """
    owner_spec: dict[str, tuple[str, str, str]] = {}  # 包名 -> (spec, owner, manager)
    env_owner: dict[str, tuple[str, str]] = {}       # env 名 -> (值, owner)
    for pkg_dir in pkg_dirs:
        ep = pkg_dir / "registry" / "environment.json"
        if not ep.exists():
            continue
        data = json.loads(ep.read_text(encoding="utf-8"))
        for manager, specs in (data.get("dependencies") or {}).items():
            ma_manager = _PACKAGE_MANAGER_MAP.get(manager)
            if not ma_manager or not specs:
                continue
            for s in specs:
                p = _pkg_name(str(s))
                if manager == "python" and p.lower() == "python":
                    # `python>=3.9` 是解释器版本约束，不是 pip 包；由 Environment 模板决定，不进 packages.pip
                    continue
                if p in owner_spec and owner_spec[p][0] != str(s):
                    raise RuntimeError(
                        f"依赖冲突：{owner_spec[p][1]} 要求 {owner_spec[p][0]}，{pkg_dir.name} 要求 {s}（包 {p}）"
                    )
                owner_spec[p] = (str(s), pkg_dir.name, ma_manager)
        for ev in data.get("env_vars") or []:
            if not isinstance(ev, dict):
                continue
            k, v = ev.get("name"), ev.get("value")
            if not k:
                continue
            if k in env_owner and env_owner[k][0] != v:
                raise RuntimeError(f"env 冲突：{env_owner[k][1]} 与 {pkg_dir.name} 对 {k} 取值不同")
            env_owner[k] = (v, pkg_dir.name)
    packages: dict[str, list[str]] = {}
    for p, (spec, _owner, manager) in owner_spec.items():
        packages.setdefault(manager, []).append(spec)
    return {"packages": packages, "env": {k: str(v[0]) for k, v in env_owner.items()}}


def desired_config(ctx: dict) -> dict:
    """期望的 Environment config：packages/env 来自各包合并，其余来自 build-config.json。"""
    base = ctx["cfg"].get("environment") or {}
    merged = merge_environments([ctx["emp_dir"] / p for p in ctx["order"]])
    config = {
        "type": base.get("type", "cloud"),
        "networking": base.get("networking", {"type": "restricted"}),
        "packages": merged.get("packages", {}),
        "env": {**merged.get("env", {}), **base.get("env", {})},
    }
    if base.get("setup_script"):
        config["setup_script"] = base["setup_script"]
    return config


def _norm_packages(p: dict | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in (p or {}).items():
        if isinstance(v, list):
            out[k] = sorted(str(x) for x in v)
    return out


def _changed_fields(current: dict, want: dict) -> list[str]:
    """对比现有 config 与期望 config，返回变化的字段名。忽略服务端补充的字段（只比期望里出现的）。"""
    cur = current or {}
    changed: list[str] = []
    if _norm_packages(cur.get("packages")) != _norm_packages(want.get("packages")):
        changed.append("packages")
    cur_env = {k: str(v) for k, v in (cur.get("env") or {}).items()}
    want_env = {k: str(v) for k, v in (want.get("env") or {}).items()}
    if any(cur_env.get(k) != v for k, v in want_env.items()):
        changed.append("env")
    if (cur.get("networking") or {}) != (want.get("networking") or {}):
        changed.append("networking")
    if (cur.get("setup_script") or "") != (want.get("setup_script") or "") and want.get("setup_script"):
        changed.append("setup_script")
    if cur.get("type") and want.get("type") and cur["type"] != want["type"]:
        changed.append("type")
    return changed


def plan(ctx: dict) -> list[Action]:
    """只读：对比期望与现状，产出 Environment 的动作。"""
    bl, emp = ctx["business_line"], ctx["employee"]
    name = ctx["names"]["environment"]
    key = ledger.make_key(bl, emp, "environment", "")
    want = desired_config(ctx)
    row = ctx["ledger_rows"].get(key)
    actual = ctx["ma"].get("environment", {}).get(name)

    if not actual:
        return [Action(kind="environment", key=key, op=CREATE, name=name, detail="新建",
                       payload={"config": want}, group="environment")]

    ma_id = str(actual.get("id") or "")
    if not row or row.status != "active":
        return [Action(kind="environment", key=key, op=ADOPT, name=name, ma_id=ma_id,
                       detail=f"MA 已存在 {ma_id}，台账未记录", group="environment")]

    changed = _changed_fields(actual.get("config") or {}, want)
    if not changed:
        return [Action(kind="environment", key=key, op=NOOP, name=name, ma_id=ma_id, group="environment")]
    warns = ["存量 Session 需 upgrade 才生效"]
    if "setup_script" in changed or "packages" in changed:
        warns.append("新 Session 可能复用旧镜像，必要时需新建 Environment")
    return [Action(kind="environment", key=key, op=UPDATE, name=name, ma_id=ma_id,
                   detail=", ".join(changed), warnings=warns,
                   payload={"config": want}, group="environment")]


def apply(ctx: dict, actions: list[Action]) -> dict:
    """执行 Environment 动作，返回 {"environment_id": ...}。"""
    out: dict = {}
    for a in actions:
        if a.op == CREATE:
            resp = ma_api.ark_post("/environments", {"name": a.name, "config": a.payload["config"]})
            a.ma_id = ma_api.unwrap_id(resp)
            print(f"  Environment 已创建: {a.name} -> {a.ma_id}")
            ledger.upsert(ctx["ledger_rows"], business_line=ctx["business_line"], employee=ctx["employee"],
                          kind="environment", name="", resource_name=a.name, ma_id=a.ma_id,
                          fingerprint=ledger.content_fingerprint(json.dumps(a.payload["config"], sort_keys=True)),
                          stage=ctx["stage"], build_id=ctx["build_id"])
        elif a.op == UPDATE:
            ma_api.ark_post(f"/environments/{a.ma_id}", {"config": a.payload["config"]})
            print(f"  Environment 已更新: {a.name} -> {a.ma_id}（{a.detail}）")
            ledger.upsert(ctx["ledger_rows"], business_line=ctx["business_line"], employee=ctx["employee"],
                          kind="environment", name="", resource_name=a.name, ma_id=a.ma_id,
                          fingerprint=ledger.content_fingerprint(json.dumps(a.payload["config"], sort_keys=True)),
                          stage=ctx["stage"], build_id=ctx["build_id"])
        elif a.op == ADOPT:
            ledger.upsert(ctx["ledger_rows"], business_line=ctx["business_line"], employee=ctx["employee"],
                          kind="environment", name="", resource_name=a.name, ma_id=a.ma_id,
                          stage=ctx["stage"], build_id=ctx["build_id"], note="首次认领")
            print(f"  台账补登: environment {a.name} -> {a.ma_id}")
        elif a.op == NOOP:
            placer = ctx["ma"].get("environment", {}).get(a.name)
            a.ma_id = str((placer or {}).get("id") or a.ma_id)
        if a.ma_id:
            out["environment_id"] = a.ma_id
    return out
