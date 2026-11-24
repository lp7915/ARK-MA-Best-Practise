#!/usr/bin/env python3
"""创建 Ada PM 数字员工的全部 MA 资源（dev 阶段首次搭建，幂等）。

资源清单：
- Environment ×1：topic-lab-ada-pm-env（pip: jsonschema/PyYAML，BYOK 沙箱与模型分离）
- 知识记忆库 ×5：topic-lab-ada-pm-mem-knowledge-01..05（对应 pm/t/g/s/validator 各自包的 knowledge/）
- Skill ×3：已由 tools/pack_upload_skills.py 上传，本脚本读取 skill_ids.json
- Agent ×5：4 个 sub（t/g/s/validator）先建，main（pm）后建并显式 multiagent 引用版本

用法：
    export ARK_API_KEY=... [ARK_BASE_URL=...]
    python3 create_all.py                    # 幂等：已存在则复用，不存在则创建
    python3 create_all.py --update-memory    # 已存在的知识库也强制覆盖条目
    python3 create_all.py --rebuild-agents   # 删同名旧 Agent 后重建（prompt/skill 变更驱动的重建）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
RES = ROOT / "ma-resources" / "topic-lab" / "ada-pm"
SKILL_IDS_FILE = ROOT / "ma-resources" / "skill_ids.json"

TOPIC, EMP = "topic-lab", "ada-pm"
ENV_NAME = f"{TOPIC}-{EMP}-env"
# 顺序：main 在前；知识库序号先 main(01)，再按 registry/agents.json 声明顺序 t/g/s/validator
AGENT_ORDER = ["pm", "t", "g", "s", "validator"]
KNOWLEDGE_NO = {"pm": 1, "t": 2, "g": 3, "s": 4, "validator": 5}
SUB_ALIASES = ["t", "g", "s", "validator"]

# ---- BYOK 模型（复用 analyst 的 gpt-6.1-sol 网关配置）----
MODEL = {
    "id": "gpt-6.1-sol",
    "provider": "bmc-llm-relay",
    "service_tier": "default",
    "base_url": "https://bmc-llm-relay.bluemediagroup.cn/v1/responses",
    "protocol": "openai_responses",
    "token_limits": {
        "context_window": 1050000,
        "max_input_token_length": 922000,
        "max_output_token_length": 128000,
    },
}

# ---- 基础工具集 20260916：全部启用 but 关闭 web（demo 无外网）----
TOOLS = [
    {
        "type": "agent_toolset_20260916",
        "default_config": {"enabled": True, "permission_policy": {"type": "always_allow"}},
        "configs": [
            {"name": "web_fetch", "enabled": False},
            {"name": "web_search", "enabled": False},
        ],
    }
]

_raw_base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
BASE_URL = _raw_base if _raw_base.endswith("/api/v3") else f"{_raw_base}/api/v3"


def auth_headers() -> dict:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ARK_API_KEY")
    return {"Authorization": f"Bearer {api_key}", "X-Ark-Beta": "agentic-2026-06-01"}


def ark_get(path: str) -> dict:
    r = requests.get(BASE_URL + path, headers=auth_headers(), timeout=60)
    if r.status_code >= 400:
        return {"_err": r.status_code, "_body": r.text[:300]}
    return r.json()


def ark_post(path: str, body: dict) -> dict:
    r = requests.post(BASE_URL + path, headers={**auth_headers(), "Content-Type": "application/json"},
                      data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=120)
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
    """按 name 在列表接口里分页查找，返回 id。"""
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


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Environment
def ensure_environment(update: bool) -> str:
    env_id = find_by_name("environments", ENV_NAME)
    config = {
        "type": "cloud",
        "networking": {"type": "unrestricted"},  # pip 装依赖需出网；业务脚本本身不外呼
        "packages": {"pip": ["jsonschema>=4.20", "PyYAML>=6.0"]},
        "env": {"TZ": "Asia/Shanghai", "PYTHONUNBUFFERED": "1"},
    }
    if env_id:
        if update:
            ark_post(f"/environments/{env_id}", {"config": config})
            print(f"  Environment 已更新: {ENV_NAME} -> {env_id}")
        else:
            print(f"  Environment 已存在(复用): {ENV_NAME} -> {env_id}")
        return env_id
    resp = ark_post("/environments", {"name": ENV_NAME, "config": config})
    env_id = unwrap_id(resp)
    print(f"  Environment 已创建: {ENV_NAME} -> {env_id}")
    return env_id


# ---------------------------------------------------------------- Memory stores
def knowledge_entries(agent: str) -> list[dict]:
    """agent 包 knowledge/ 下所有 .md/.txt -> 记忆条目（含 /_索引.md）。"""
    kdir = RES / agent / "knowledge"
    entries = []
    rels = []
    for f in sorted(kdir.rglob("*")):
        if not f.is_file() or f.suffix not in (".md", ".txt"):
            continue
        rel = f.relative_to(kdir).as_posix()
        rels.append(rel)
        entries.append({"path": f"/{rel}", "content": f.read_text(encoding="utf-8")})
    # 构建器生成索引条目（规范 6.8.2）
    idx = "# 索引\n\n" + "\n".join(f"- /{r}" for r in rels) + "\n"
    entries.append({"path": "/_索引.md", "content": idx})
    return entries


def ensure_memory_store(agent: str, update: bool) -> str:
    no = KNOWLEDGE_NO[agent]
    name = f"{TOPIC}-{EMP}-mem-knowledge-{no:02d}"
    store_id = find_by_name("memory_stores", name)
    created = False
    if store_id:
        print(f"  知识库已存在(复用): {name} -> {store_id}")
    else:
        resp = ark_post("/memory_stores", {"name": name, "description": f"Ada PM · {agent} 包业务知识(只读)"})
        store_id = unwrap_id(resp)
        created = True
        print(f"  知识库已创建: {name} -> {store_id}")
    if created or update:
        print(f"  写入知识条目...")
        for e in knowledge_entries(agent):
            ark_post(f"/memory_stores/{store_id}/memories", e)
        print(f"  已写入 {agent} 知识条目")
    else:
        print(f"  知识条目已存在，跳过写入（--update-memory 可覆盖）")
    return store_id


# ---------------------------------------------------------------- system prompt
def build_system(agent: str, mem_id: str) -> str:
    idir = RES / agent / "identity"
    parts = []
    for file, title in [("identity.md", "身份"), ("orchestration.md", "编排"), ("handoff.md", "交接")]:
        f = idir / file
        if f.exists():
            parts.append(f"# {title}\n\n{f.read_text(encoding='utf-8').strip()}\n")
    system = "\n".join(parts)
    # 替换 {{knowledge:X}} -> /<知识库ID>/X（使用记忆工具读取）
    def repl(m):
        return f"/{mem_id}/{m.group(1)}（使用记忆工具读取）"
    system = re.sub(r"\{\{knowledge:([^}]+)\}\}", repl, system)
    leftover = re.findall(r"\{\{[^}]+\}\}", system)
    if leftover:
        raise RuntimeError(f"{agent}: 存在未替换/未知占位符 {leftover}")
    return system


# ---------------------------------------------------------------- agents
def agent_config(agent: str, system: str, skill_ids: dict) -> dict:
    agent_meta = read_json(RES / agent / "registry" / "agent.json")
    cfg = {
        "name": f"{TOPIC}-{EMP}-{agent}",
        "description": agent_meta["description"],
        "model": MODEL,
        "system": system,
        "tools": TOOLS,
        "metadata": {
            "managed_by": "ma-build",
            "topic": TOPIC,
            "employee": EMP,
            "agent": agent,
            "role": agent_meta["role"],
            "visibility": agent_meta["visibility"],
            "spec": "1.3",
            "stage": "dev",
        },
    }
    # skills 引用
    skills = json.loads((RES / agent / "registry" / "skills.json").read_text(encoding="utf-8"))
    # 注意：skills[].version 必须是字符串（"1"）；multiagent.agents[].version 必须是 int32。两处类型相反，写反会 400。
    cfg["skills"] = [
        {"type": "custom", "skill_id": skill_ids[s["id"]]["skill_id"], "version": str(skill_ids[s["id"]]["version"])}
        for s in skills
    ]
    assert all(s["skill_id"] for s in cfg["skills"]), f"{agent} skill_id 缺失"
    return cfg


def create_agent(agent: str, system: str, skill_ids: dict, subs: dict | None, rebuild: bool) -> dict:
    name = f"{TOPIC}-{EMP}-{agent}"
    existing = find_by_name("agents", name)
    if existing and not rebuild:
        print(f"  Agent 已存在(复用): {name} -> {existing}")
        return {"id": existing, "version": 1}
    if existing and rebuild:
        ark_delete(f"/agents/{existing}")
        print(f"  删除旧 Agent {name} -> {existing} 以便重建")
    cfg = agent_config(agent, system, skill_ids)
    if subs is not None:  # main：显式写入 multiagent 引用 + 版本
        cfg["multiagent"] = {
            "type": "coordinator",
            # multiagent.agents[].version 是 int32（区别于 skills[].version 的字符串）
            "agents": [
                {"type": "agent", "id": subs[a]["id"], "version": subs[a]["version"]}
                for a in SUB_ALIASES
            ],
        }
    resp = ark_post("/agents", cfg)
    aid = unwrap_id(resp)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    ver = data.get("version")
    ver_int = int(ver) if ver is not None else 1
    print(f"  Agent 已创建: {name} -> {aid} (version={ver})")
    return {"id": aid, "version": ver_int}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-memory", action="store_true", help="知识库强制覆盖条目")
    ap.add_argument("--update-env", action="store_true", help="Environment 原地刷新 config")
    ap.add_argument("--rebuild-agents", action="store_true", help="删同名旧 Agent 后重建")
    args = ap.parse_args()

    skill_ids = json.loads(SKILL_IDS_FILE.read_text(encoding="utf-8"))["skills"]
    unfilled = [k for k, v in skill_ids.items() if not v.get("skill_id")]
    if unfilled:
        print(f"以下 skill 未上传: {unfilled}", file=sys.stderr)
        return 1

    print("==== 1) Environment ====")
    env_id = ensure_environment(args.update_env)

    print("==== 2) 知识记忆库（5 个，只读）====")
    mem_ids = {a: ensure_memory_store(a, args.update_memory) for a in AGENT_ORDER}

    print("==== 3) system prompt 拼接 + 占位符替换 ====")
    systems = {a: build_system(a, mem_ids[a]) for a in AGENT_ORDER}

    print("==== 4) 创建 sub Agent（t/g/s/validator）====")
    subs = {}
    for a in ["t", "g", "s", "validator"]:
        subs[a] = create_agent(a, systems[a], skill_ids, subs=None, rebuild=args.rebuild_agents)

    print("==== 5) 创建 main Agent（pm · multiagent 引用 4 个 sub）====")
    main_agent = create_agent("pm", systems["pm"], skill_ids, subs=subs, rebuild=args.rebuild_agents)

    result = {
        "environment_id": env_id,
        "memory_stores": {a: mem_ids[a] for a in AGENT_ORDER},
        "agents": {"pm": main_agent, **subs},
        "skills": {k: v["skill_id"] for k, v in skill_ids.items()},
    }
    out = ROOT / "ma-resources" / "created_ids.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成。ID 落盘: {out}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())