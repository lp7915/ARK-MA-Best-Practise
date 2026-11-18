#!/usr/bin/env python3
"""通用声明式构建器：把「<业务线>/<数字员工>/」声明目录映射成火山方舟 MA 资源。

与 ada-pm 的 create_all.py 等价，但不再硬编码业务线/数字员工/智能体清单：
- 扫描子目录，凡含 `registry/agent.json` 的目录就是一个智能体包，按 `role` 分 main/sub；
- main 的 `registry/agents.json` 决定 sub 顺序与 multiagent 引用；
- model / tools / stage / environment 等平台侧字段从 `<数字员工>/build-config.json` 读取
  （映射规范 6.1「模型由中台选型」——不进业务包，进构建配置）；
- 知识库序号在数字员工内统一分配：先 main，再按 agents.json 声明顺序（映射规范 6.2.4）。

前置：先把 skill 打包上传（见 pack_skills.py），本脚本读取 `skill_ids.json`。

使用：
    export ARK_API_KEY=...  [ARK_BASE_URL=...]
    python3 build.py <数字员工目录> [--plan] [--stage dev] [--update-memory] [--update-env] [--rebuild-agents]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

try:
    import yaml  # connections.yaml 用（PyYAML）；不可用时退化到 json 解析
except ImportError:  # pragma: no cover
    yaml = None

_raw_base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
BASE_URL = _raw_base if _raw_base.endswith("/api/v3") else f"{_raw_base}/api/v3"
ARK_BETA = "agentic-2026-06-01"

# 默认工具集：与映射规范 6.2.2 实测一致，全部启用但关闭 web（demo 无外网）。
DEFAULT_TOOLS = [
    {
        "type": "agent_toolset_20260916",
        "default_config": {"enabled": True, "permission_policy": {"type": "always_allow"}},
        "configs": [
            {"name": "web_fetch", "enabled": False},
            {"name": "web_search", "enabled": False},
        ],
    }
]


_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def expand_vars(obj, missing: set):
    """递归展开 ${VAR}（取环境变量）；未设置的收集到 missing，由调用方统一报错。"""
    if isinstance(obj, str):
        def r(m):
            v = os.environ.get(m.group(1))
            if v is None:
                missing.add(m.group(1))
                return m.group(0)
            return v
        return _VAR.sub(r, obj)
    if isinstance(obj, dict):
        return {k: expand_vars(v, missing) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_vars(v, missing) for v in obj]
    return obj


# ---------------------------------------------------------------- HTTP 工具
def auth_headers() -> dict:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ARK_API_KEY")
    return {"Authorization": f"Bearer {api_key}", "X-Ark-Beta": ARK_BETA, "Accept": "application/json"}


def ark_get(path: str) -> dict:
    r = requests.get(BASE_URL + path, headers=auth_headers(), timeout=90)
    if r.status_code >= 400:
        return {"_err": r.status_code, "_body": r.text[:300]}
    return r.json()


def ark_post(path: str, body: dict) -> dict:
    r = requests.post(BASE_URL + path, headers=auth_headers(), data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=120)
    if r.status_code >= 400:
        print(f"  [HTTP {r.status_code}] POST {path}: {r.text[:500]}", file=sys.stderr)
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


def ark_delete(path: str) -> None:
    requests.delete(BASE_URL + path, headers=auth_headers(), timeout=60)


def unwrap_id(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return str(data.get("id") or data.get("agent_id") or data.get("environment_id") or "")


def payload_to_items(payload: dict) -> list:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(payload.get("items"), list):
        return payload["items"]
    return payload if isinstance(payload, list) else []


def find_by_name(collection: str, name: str) -> str | None:
    page = ""
    while True:
        q = f"?page_size=200" + (f"&page={page}" if page else "")
        body = ark_get(f"/{collection}{q}")
        if isinstance(body, dict) and "_err" in body:
            return None
        for it in payload_to_items(body):
            if it.get("name") == name or it.get("display_name") == name:
                return str(it.get("id") or "")
        nxt = body.get("next_page") if isinstance(body, dict) else None
        if not nxt:
            return None
        page = nxt


# ---------------------------------------------------------------- 目录发现
def discover(emp_dir: Path) -> tuple[str, str, dict[str, dict], list[str]]:
    """返回 (business_line, employee, packages{name:agent.json}, order[name,...])。

    order：main 在前，其余 sub 按 main 的 registry/agents.json 声明顺序；未被列出的 sub 兜底按名字序。
    """
    emp_dir = emp_dir.resolve()
    employee = emp_dir.name
    business_line = emp_dir.parent.name
    packages: dict[str, dict] = {}
    main_id: str | None = None
    for d in sorted(emp_dir.iterdir()):
        if not d.is_dir():
            continue
        aj = d / "registry" / "agent.json"
        if not aj.exists():
            continue
        meta = json.loads(aj.read_text(encoding="utf-8"))
        packages[d.name] = meta
        if meta.get("role") == "main":
            main_id = d.name
    if main_id is None:
        raise RuntimeError(f"{emp_dir} 下未找到 role=main 的智能体包")
    order = [main_id]
    sub_order: list[str] = []
    agents_json = emp_dir / main_id / "registry" / "agents.json"
    if agents_json.exists():
        for ref in json.loads(agents_json.read_text(encoding="utf-8")):
            rid = ref.get("id", "")
            if rid == "self":  # 保留 id：main 并发委派自身，不是智能体包
                continue
            if rid in packages and rid != main_id:
                sub_order.append(rid)
    for name in sorted(packages):
        if packages[name].get("role") == "sub" and name not in sub_order:
            sub_order.append(name)
    order += sub_order
    return business_line, employee, packages, order


def load_build_config(emp_dir: Path) -> dict:
    cfg_path = emp_dir / "build-config.json"
    if not cfg_path.exists():
        raise RuntimeError(f"缺少构建配置：{cfg_path}")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def knowledge_roots(pkg_dir: Path) -> list[str]:
    """读 knowledge.yaml 的 roots[].path；缺省回退为 knowledge/。"""
    ky = pkg_dir / "knowledge.yaml"
    if not ky.exists():
        return ["knowledge"] if (pkg_dir / "knowledge").is_dir() else []
    data = json.loads(ky.read_text(encoding="utf-8")) if ky.suffix == ".json" else _load_yaml_flat(ky)
    roots = [r.get("path", "") for r in data.get("roots", [])]
    return [r for r in roots if r] or (["knowledge"] if (pkg_dir / "knowledge").is_dir() else [])


def _load_yaml_flat(path: Path) -> dict:
    """极简 YAML：只解析 `roots:\n  - path: <v>` 这种平铺结构（避免引入 PyYAML 依赖）。"""
    roots: list[dict] = []
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- path:") or s.startswith("- path："):
            cur = {"path": s.split(":", 1)[1].strip().strip('"').strip("'")}
            roots.append(cur)
        elif s.startswith("path:") and cur is not None:
            cur["path"] = s.split(":", 1)[1].strip().strip('"').strip("'")
    return {"roots": roots}


# ---------------------------------------------------------------- 资源构建
def load_connections(pkg_dir: Path) -> list[dict]:
    """读 connections.yaml 的 connections 列表；缺失/空返回 []（映射规范 6.4）。"""
    cf = pkg_dir / "connections.yaml"
    if not cf.exists():
        return []
    text = cf.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = None
    if yaml is not None:
        try:
            data = yaml.safe_load(text)
        except Exception:
            data = None
    if data is None:
        try:
            data = json.loads(text)
        except Exception:
            raise RuntimeError(f"{pkg_dir.name}: connections.yaml 无法解析")
    conns = (data or {}).get("connections") or []
    return [c for c in conns if isinstance(c, dict)]


def ensure_vault(business_line: str, employee: str, agent: str, connections: list[dict], credential_values: dict) -> tuple[str, list[str]]:
    """每智能体一个 Vault；把 connections 声明成凭证（值从 credential_values 取）。

    不跨智能体合并（映射规范 6.2.4/6.4：每智能体一个 Vault，会话挂 vault_id 集合）。
    返回 (vault_id, credential_ids)。凭证密钥值由 build-config.json.credentials 提供（key = secret_name）。
    """
    name = f"{business_line}-{employee}-vault-{agent}"
    vault_id = find_by_name("vaults", name)
    if vault_id:
        print(f"  Vault 已存在(复用): {name} -> {vault_id}")
    else:
        resp = ark_post("/vaults", {"display_name": name})
        vault_id = unwrap_id(resp)
        print(f"  Vault 已创建: {name} -> {vault_id}")
    cred_ids: list[str] = []
    # 幂等：已存在同 secret_name 的凭证就复用（凭证值创建后不可回读，换值需删除重建）
    existing_creds = {
        (c.get("auth") or {}).get("secret_name"): c.get("id")
        for c in payload_to_items(ark_get(f"/vaults/{vault_id}/credentials"))
    }
    for conn in connections:
        kind = conn.get("kind", "")
        secret_name = str(conn.get("secret_name") or "")
        display = str(conn.get("name") or secret_name or "credential")
        if kind == "api_key":
            if not secret_name:
                print(f"  [warn] {agent}: api_key 连接缺 secret_name，跳过")
                continue
            if secret_name in existing_creds:
                cred_ids.append(existing_creds[secret_name])
                print(f"  凭证已存在(复用): {secret_name} -> {existing_creds[secret_name]}")
                continue
            value = credential_values.get(secret_name)
            if not value:
                print(f"  [warn] 凭证 {secret_name} 缺密钥值（build-config.json.credentials），跳过")
                continue
            resp = ark_post(
                f"/vaults/{vault_id}/credentials",
                {
                    "display_name": display,
                    "auth": {
                        "type": "environment_variable",
                        "secret_name": secret_name,
                        "secret_value": value,
                        "networking": {"type": "unrestricted"},
                    },
                },
            )
            cid = unwrap_id(resp)
            cred_ids.append(cid)
            print(f"  凭证已创建: {secret_name} -> {cid}")
        else:
            print(f"  [warn] 连接 kind={kind or '(空)'}（{agent}）暂未实现，跳过（当前仅支持 api_key）")
    return vault_id, cred_ids


_PACKAGE_MANAGER_MAP = {"python": "pip", "node": "npm", "system": "apt"}


def _pkg_name(spec: str) -> str:
    """从版本约束串取包名：'pandas>=2.0' -> 'pandas'，'requests[socks]==2' -> 'requests'。"""
    return re.split(r"[<>=!~;\[\s]", str(spec).strip())[0] or str(spec).strip()


def merge_environments(pkg_dirs: list[Path]) -> dict:
    """合并各包的 registry/environment.json（6.2.4/6.3 唯一做合并的资源）。

    返回 {"packages": {manager: [spec,...]}, "env": {key: 值}}。同包不同版本要求、
    同名 env 不同值 → 冲突阻断并指出两个来源包。
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
                if p in owner_spec and owner_spec[p][0] != str(s):
                    raise RuntimeError(
                        f"依赖冲突：{owner_spec[p][1]} 要求 {owner_spec[p][0]}，{pkg_dir.name} 要求 {s}（包 {p}）"
                    )
                owner_spec[p] = (str(s), pkg_dir.name, ma_manager)
        for ev in data.get("env_vars") or []:
            if not isinstance(ev, dict):
                continue
            k = ev.get("name"); v = ev.get("value")
            if not k:
                continue
            if k in env_owner and env_owner[k][0] != v:
                raise RuntimeError(f"env 冲突：{env_owner[k][1]} 与 {pkg_dir.name} 对 {k} 取值不同")
            env_owner[k] = (v, pkg_dir.name)
    packages: dict[str, list[str]] = {}
    for p, (spec, _owner, manager) in owner_spec.items():
        packages.setdefault(manager, []).append(spec)
    return {"packages": packages, "env": {k: str(v[0]) for k, v in env_owner.items()}}


def ensure_environment(cfg: dict, business_line: str, employee: str, update: bool, merged_env: dict) -> str:
    """Environment（唯一做合并的会话级资源）：packages/env 来自各包 environment.json 合并结果，
    type/networking 及 env 补充来自 build-config.json（platform 侧决策）。"""
    name = f"{business_line}-{employee}-env"
    base = cfg.get("environment") or {}
    config = {
        "type": base.get("type", "cloud"),
        "networking": base.get("networking", {"type": "restricted"}),
        "packages": merged_env.get("packages", {}),
        "env": {**merged_env.get("env", {}), **base.get("env", {})},
    }
    if base.get("setup_script"):  # 例如装 lark-cli；属平台侧环境配置
        config["setup_script"] = base["setup_script"]
    env_id = find_by_name("environments", name)
    if env_id:
        if update:
            ark_post(f"/environments/{env_id}", {"config": config})
            print(f"  Environment 已更新: {name} -> {env_id}")
        else:
            print(f"  Environment 已存在(复用): {name} -> {env_id}")
        return env_id
    resp = ark_post("/environments", {"name": name, "config": config})
    env_id = unwrap_id(resp)
    print(f"  Environment 已创建: {name} -> {env_id}")
    return env_id


def knowledge_entries(pkg_dir: Path, root: str) -> list[dict]:
    kdir = pkg_dir / root
    entries, rels = [], []
    for f in sorted(kdir.rglob("*")):
        if not f.is_file() or f.suffix not in (".md", ".txt"):
            continue
        rel = f.relative_to(kdir).as_posix()
        rels.append(rel)
        entries.append({"path": f"/{rel}", "content": f.read_text(encoding="utf-8")})
    idx = "# 索引\n\n" + "\n".join(f"- /{r}" for r in rels) + "\n"
    entries.append({"path": "/_索引.md", "content": idx})
    return entries


def ensure_memory_store(business_line: str, employee: str, name: str, pkg_dir: Path, root: str, update: bool) -> str:
    store_id = find_by_name("memory_stores", name)
    created = False
    if store_id:
        print(f"  知识库已存在(复用): {name} -> {store_id}")
    else:
        resp = ark_post("/memory_stores", {"name": name, "description": f"{business_line}/{employee} 知识库（只读）"})
        store_id = unwrap_id(resp)
        created = True
        print(f"  知识库已创建: {name} -> {store_id}")
    if created or update:
        for e in knowledge_entries(pkg_dir, root):
            ark_post(f"/memory_stores/{store_id}/memories", e)
        print(f"  已写入知识条目（{name}）")
    return store_id


def build_system(pkg_dir: Path, knowledge_map: dict[str, str]) -> str:
    """identity 三段拼接 + 占位符替换。knowledge_map: {root名: 知识库ID}，单 root 时填该 root 名。"""
    idir = pkg_dir / "identity"
    parts = []
    for file, title in [("identity.md", "身份"), ("orchestration.md", "编排"), ("handoff.md", "交接")]:
        f = idir / file
        if f.exists():
            parts.append(f"# {title}\n\n{f.read_text(encoding='utf-8').strip()}\n")
    system = "\n".join(parts)

    def repl(m):
        token = m.group(1)
        if len(knowledge_map) == 1:
            mem_id = next(iter(knowledge_map.values()))
            return f"/{mem_id}/{token}（使用记忆工具读取）"
        # 多 root：token 的第一段是 root 名
        root, _, rest = token.partition("/")
        if root in knowledge_map and rest:
            return f"/{knowledge_map[root]}/{rest}（使用记忆工具读取）"
        raise RuntimeError(f"{pkg_dir.name}: 知识占位符 {{knowledge:{token}}} 未匹配到已声明 root（可选：{list(knowledge_map)}）")

    system = re.sub(r"\{\{knowledge:([^}]+)\}\}", repl, system)
    system = system.replace("{{input}}", "/mnt/session/uploads/（使用文件读取）")
    system = system.replace("{{output}}", "/mnt/session/outputs/（可写产物目录）")
    leftover = re.findall(r"\{\{[^}]+\}\}", system)
    if leftover:
        raise RuntimeError(f"{pkg_dir.name}: 存在未替换/未知占位符 {leftover}")
    return system


def agent_config(cfg: dict, business_line: str, employee: str, pkg_name: str, system: str, skill_ids: dict) -> dict:
    meta = json.loads((cfg["_pkg_dirs"][pkg_name] / "registry" / "agent.json").read_text(encoding="utf-8"))
    out = {
        "name": f"{business_line}-{employee}-{pkg_name}",
        "description": meta.get("description", ""),
        "model": cfg["model"],
        "system": system,
        # 平台侧 tools 可按智能体覆写：build-config.json 的 agent_tools[<包名>]，未写则用统一的 tools
        "tools": (cfg.get("agent_tools") or {}).get(pkg_name) or cfg.get("tools", DEFAULT_TOOLS),
        **({"mcp_servers": cfg["mcp_servers"]} if cfg.get("mcp_servers") and meta.get("role") == "main" else {}),
        "metadata": {
            "managed_by": "ma-build",
            "topic": business_line,
            "employee": employee,
            "agent": pkg_name,
            "role": meta.get("role", ""),
            "visibility": meta.get("visibility", ""),
            "spec": cfg.get("spec", ""),
            "stage": cfg.get("stage", "dev"),
        },
    }
    sj = cfg["_pkg_dirs"][pkg_name] / "registry" / "skills.json"
    if sj.exists():
        refs = json.loads(sj.read_text(encoding="utf-8"))
        # skills[].version 必须是字符串（区别于 multiagent 的 int32）
        missing = [r["id"] for r in refs if not (skill_ids.get(r["id"]) or {}).get("skill_id")]
        if missing:
            raise RuntimeError(f"{pkg_name}: skills.json 引用了未解析的 skill {missing}（先上传，或在 registry_resolved.json 登记）")
        out["skills"] = [
            {"type": "custom", "skill_id": skill_ids[r["id"]]["skill_id"], "version": str(skill_ids[r["id"]]["version"])}
            for r in refs
        ]
    return out


def create_agent(cfg: dict, business_line: str, employee: str, pkg_name: str, system: str, skill_ids: dict, subs: dict | None, rebuild: bool, allow_self: bool = False) -> dict:
    name = f"{business_line}-{employee}-{pkg_name}"
    existing = find_by_name("agents", name)
    if existing and not rebuild:
        print(f"  Agent 已存在(复用): {name} -> {existing}")
        return {"id": existing, "version": 1}
    if existing and rebuild:
        ark_delete(f"/agents/{existing}")
        print(f"  删除旧 Agent {name} -> {existing} 以便重建")
    ac = agent_config(cfg, business_line, employee, pkg_name, system, skill_ids)
    if subs is not None:
        # multiagent.agents[].version 是 int32（区别于 skills[].version 的字符串）
        agents = [{"type": "agent", "id": subs[a]["id"], "version": subs[a]["version"]} for a in subs]
        if allow_self:  # main 的 registry/agents.json 声明了保留 id self
            agents.append({"type": "self"})
        ac["multiagent"] = {"type": "coordinator", "agents": agents}
    resp = ark_post("/agents", ac)
    aid = unwrap_id(resp)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    ver = int(data.get("version") or 1)
    print(f"  Agent 已创建: {name} -> {aid} (version={ver})")
    return {"id": aid, "version": ver}


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("emp_dir", help="数字员工目录（<业务线>/<数字员工>/）")
    ap.add_argument("--plan", action="store_true", help="只读预览，不创建任何资源")
    ap.add_argument("--stage", help="覆盖 build-config.json 的 stage（仅影响 metadata）")
    ap.add_argument("--update-memory", action="store_true", help="知识库强制覆盖条目")
    ap.add_argument("--update-env", action="store_true", help="Environment 原地刷新 config")
    ap.add_argument("--rebuild-agents", action="store_true", help="删同名旧 Agent 后重建")
    args = ap.parse_args()

    emp_dir = Path(args.emp_dir).resolve()
    business_line, employee, packages, order = discover(emp_dir)
    cfg = load_build_config(emp_dir)
    if args.stage:
        cfg["stage"] = args.stage
    cfg["_pkg_dirs"] = {name: emp_dir / name for name in order}
    missing: set = set()
    cfg["environment"] = expand_vars(cfg.get("environment", {}), missing)
    cfg["mcp_servers"] = expand_vars(cfg.get("mcp_servers", []), missing)
    if missing and not args.plan:
        raise RuntimeError(f"build-config 引用的变量未设置：{sorted(missing)}（导出到环境变量后重试；--plan 可忽略）")
    if missing:
        print(f"[plan] 以下变量尚未设置（真实构建会阻断）：{sorted(missing)}")
    credential_values = {**cfg.get("credentials", {}), **{k: os.environ[k] for k in ("DATAHUB_API_KEY", "LLM_RELAY_API_KEY", "BLUEAI_API_KEY") if os.environ.get(k)}}
    if not cfg.get("model"):
        raise RuntimeError("build-config.json 缺少 model 字段")

    skill_ids = {}
    sid_file = emp_dir / "skill_ids.json"
    if sid_file.exists():
        skill_ids = json.loads(sid_file.read_text(encoding="utf-8")).get("skills", {})
    # 引用注册表的可复用 skill：skills.json 里 id 是注册表 atomic_id（含 "."），由中台解析并锁定。
    # 过渡机制：读 registry_resolved.json（atomic_id → {skill_id, version}），等价于「构建时解析+锁定」。
    rr_file = emp_dir / "registry_resolved.json"
    if rr_file.exists():
        skill_ids.update(json.loads(rr_file.read_text(encoding="utf-8")).get("skills", {}))

    # 知识库序号：全局统一分配（先 main，再 order 顺序），每包每个 root +1
    memory_plan: list[tuple[str, str, Path, str]] = []  # (pkg_name, root, pkg_dir, store_name)
    no = 0
    for pkg_name in order:
        roots = knowledge_roots(emp_dir / pkg_name)
        for root in roots:
            no += 1
            store_name = f"{business_line}-{employee}-mem-knowledge-{no:02d}"
            memory_plan.append((pkg_name, root, emp_dir / pkg_name, store_name))

    if args.plan:
        print(f"[plan] {business_line}/{employee} · stage={cfg.get('stage')}")
        print(f"  agents({len(order)}): {', '.join(order)}")
        print(f"  vaults({len(order)}):")
        for pkg_name in order:
            conns = load_connections(emp_dir / pkg_name)
            print(f"    {business_line}-{employee}-vault-{pkg_name}  <- {pkg_name}（connections={len(conns)}）")
        print(f"  知识库({len(memory_plan)}):")
        for pkg_name, root, _, store_name in memory_plan:
            print(f"    {store_name}  <- {pkg_name}/{root}")
        print(f"  skills({len(skill_ids)}): {', '.join(skill_ids) or '(未上传)'}")
        for pkg_name in order:
            pkg_meta = packages[pkg_name]
            print(f"    {pkg_name}: role={pkg_meta.get('role')} visibility={pkg_meta.get('visibility')} version={pkg_meta.get('version')}")
        return 0

    # 1) Environment
    print("==== 1) Environment ====")
    merged_env = merge_environments([emp_dir / p for p in order])
    env_id = ensure_environment(cfg, business_line, employee, args.update_env, merged_env)

    # 2) Vault（每智能体一个，不合并）
    print("==== 2) Vault（每智能体一个）====")
    vault_ids: dict[str, str] = {}
    for pkg_name in order:
        conns = load_connections(emp_dir / pkg_name)
        vault_ids[pkg_name], _ = ensure_vault(business_line, employee, pkg_name, conns, credential_values)

    # 3) 知识记忆库（只读）
    print("==== 3) 知识记忆库 ====")
    mem_ids: dict[str, str] = {}
    knowledge_map_by_pkg: dict[str, dict[str, str]] = {p: {} for p in order}
    for pkg_name, root, pkg_dir, store_name in memory_plan:
        mem_id = ensure_memory_store(business_line, employee, store_name, pkg_dir, root, args.update_memory)
        mem_ids[store_name] = mem_id
        knowledge_map_by_pkg[pkg_name][root] = mem_id

    # 4) system 拼接 + 占位符替换
    print("==== 4) system 拼接 + 占位符替换 ====")
    systems = {p: build_system(emp_dir / p, knowledge_map_by_pkg[p]) for p in order}

    # 5) 创建 sub Agent（跳过 main）
    print("==== 5) 创建 sub Agent ====")
    subs = {}
    for pkg_name in order:
        if packages[pkg_name].get("role") == "main":
            continue
        subs[pkg_name] = create_agent(cfg, business_line, employee, pkg_name, systems[pkg_name], skill_ids, subs=None, rebuild=args.rebuild_agents)

    # 6) 创建 main Agent（multiagent 引用全部 sub）
    print("==== 6) 创建 main Agent ====")
    main_id_pkg = order[0]
    main_refs = json.loads((emp_dir / main_id_pkg / "registry" / "agents.json").read_text(encoding="utf-8")) if (emp_dir / main_id_pkg / "registry" / "agents.json").exists() else []
    allow_self = any(r.get("id") == "self" for r in main_refs)
    main_agent = create_agent(cfg, business_line, employee, main_id_pkg, systems[main_id_pkg], skill_ids, subs=subs, rebuild=args.rebuild_agents, allow_self=allow_self)

    result = {
        "business_line": business_line,
        "employee": employee,
        "stage": cfg.get("stage"),
        "environment_id": env_id,
        "vault_ids": vault_ids,
        "memory_stores": mem_ids,
        "agents": {main_id_pkg: main_agent, **subs},
        "skills": {k: v["skill_id"] for k, v in skill_ids.items() if v.get("skill_id")},
    }
    out = emp_dir / "created_ids.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成。ID 落盘: {out}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())