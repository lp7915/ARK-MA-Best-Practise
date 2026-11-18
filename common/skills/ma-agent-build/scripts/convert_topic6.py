#!/usr/bin/env python3
"""topic6 ma-resources（crazyworld/main 扁平烟囱结构）→ 交付规范 v1.5 三级声明目录。

输入：topic6 的 ma-resources 目录（agents/*.json + *.system.md、skills/、memory/、environment.json）
输出：<out>/<业务线>/<数字员工>/{coordinator,annotator,validator}/ + build-config.json

只做机械搬运与拆分，不改写业务内容：
- system.md 按「##」一级章节切分：身份类→identity.md，其余→orchestration.md，「关键引用」→handoff.md；
  文件内标题保持从「##」起（规范 5.1），原文顶部「# 标题」与引言引用块丢弃（重新由拼接生成「# 身份」等）。
- skills 目录按引用关系放进各包 skills/<id>/，registry/skills.json 声明引用。
- memory/ 三个文件 → coordinator/knowledge/（只读知识库，knowledge.yaml 声明 root）。
- environment.json → 各包 registry/environment.json（dependencies/env_vars）+ build-config.json.environment（type/networking/setup_script）。
- 平台侧字段（model/tools/stage）→ build-config.json，不进智能体包。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

LINE, EMP = "topic-lab", "topic6"
PKG = {"coordinator": "topic6-coordinator", "annotator": "topic6-annotator", "validator": "topic6-validator"}
# 共享/可复用 skill：按交付规范 6.3 登记到原子注册表，包内只引用、不内置源码。
# 注册表 id 形如 <业务线>.<name>；注册由用户在（冻结的）注册表里完成，这里只产出待登记清单。
REGISTRY_SKILLS = {"topic6-annotation": "topic6.annotation", "validator": "platform.validator"}
# 占位符 ${...} 在 environment.json 里代表密钥/地址，构建时从 secrets 取；声明包里只保留变量名
ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def split_system(text: str) -> dict[str, str]:
    """按 '## ' 一级章节切分；返回 {identity, orchestration, handoff}。"""
    lines = text.splitlines()
    # 丢弃首个 '# ' 标题与其后的引言（直到第一个 '## '）
    start = next((i for i, l in enumerate(lines) if l.startswith("## ")), 0)
    body = lines[start:]
    sections: list[tuple[str, list[str]]] = []
    for l in body:
        if l.startswith("## "):
            sections.append((l, [l]))
        elif sections:
            sections[-1][1].append(l)
    ident, orch, hand = [], [], []
    for title, ls in sections:
        block = "\n".join(ls).rstrip() + "\n"
        # 去掉章节前的 '---' 分隔线残留
        block = re.sub(r"\n---\s*\n$", "\n", block)
        if re.search(r"身份|角色", title) and not orch:
            ident.append(block)
        elif re.search(r"关键引用|交接|边界", title):
            hand.append(block)
        else:
            orch.append(block)
    return {
        "identity": "".join(ident) or "".join(orch[:1]),
        "orchestration": "".join(orch),
        "handoff": "".join(hand),
    }


def write(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def wj(p: Path, o) -> None:
    write(p, json.dumps(o, ensure_ascii=False, indent=2) + "\n")


def copy_skill(src_skills: Path, sid: str, dst_pkg: Path) -> None:
    # 内置到包：<pkg>/skills/<id>；注册表源码：<_registry_src>/<id>（dst_pkg 名为 _registry_src 时平铺）
    dst = (dst_pkg / sid) if dst_pkg.name == "_registry_src" else (dst_pkg / "skills" / sid)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_skills / sid, dst, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="topic6/ma-resources 目录（取自 crazyworld/main）")
    ap.add_argument("out", help="输出根目录，将生成 <out>/topic-lab/topic6/")
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out) / LINE / EMP
    for d in (out, out.parent.parent / "_registry_src"):  # 只清自己生成的目录，不碰输出根下的其他内容
        if d.exists():
            shutil.rmtree(d)

    agents = {n: json.loads((src / "agents" / f"{n}.json").read_text(encoding="utf-8")) for n in ("coordinator", "annotator", "validator")}
    env = json.loads((src / "environment.json").read_text(encoding="utf-8"))["config"]

    # —— skill 引用（从 ${skill_id.xxx} 取 id）——
    def skill_ids(a: dict) -> list[str]:
        return [re.search(r"\$\{skill_id\.([^}]+)\}", s["skill_id"]).group(1) for s in a.get("skills", [])]

    owner = {"team": "topic6 业务方", "primary": "待指定", "backup": "待指定"}
    desc = {n: agents[n]["description"] for n in agents}
    role = {"coordinator": ("main", "public"), "annotator": ("sub", "internal"), "validator": ("sub", "internal")}
    sk_owner: dict[str, str] = {}  # skill id → 放在哪个包

    for name, a in agents.items():
        pkg = out / PKG[name]
        r, vis = role[name]
        wj(pkg / "registry" / "agent.json", {
            "id": f"{LINE}.{EMP}.{PKG[name]}", "version": "1.0.0", "role": r, "visibility": vis,
            "owner": owner, "description": desc[name],
        })
        sj = []
        for sid in skill_ids(a):
            if sid in REGISTRY_SKILLS:  # 引用注册表能力：只写 id+range，不内置
                sj.append({"id": REGISTRY_SKILLS[sid], "range": "^1.0.0"})
                if sid not in sk_owner:
                    sk_owner[sid] = "registry"
                    copy_skill(src / "skills", sid, out.parent.parent / "_registry_src")
                continue
            sj.append({"id": sid, "range": "^1.0.0"})
            if sid not in sk_owner:
                sk_owner[sid] = name
                copy_skill(src / "skills", sid, pkg)
        wj(pkg / "registry" / "skills.json", sj)
        full = (src / "agents" / a["system_file"]).read_text(encoding="utf-8")
        # 不拆分（用户决策）：整份原文放 identity.md；orchestration.md / handoff.md 保持为空文件
        # 唯一改写：memory 路径 /{memstore_id}/topic6/x → {{knowledge:topic6/x}}（规范 5.7，构建器替换为真实库 ID）
        full = re.sub(r"/\{memstore_id\}/(topic6/[^\s`，,。)）]+)", r"{{knowledge:\1}}", full)
        write(pkg / "identity" / "identity.md", full)
        write(pkg / "identity" / "orchestration.md", "")
        write(pkg / "identity" / "handoff.md", "")
        write(pkg / "registry" / "version_mapping.md", f"# {name} 版本说明\n\n- 1.0.0：由 crazyworld/main 的 topic6 ma-resources 机械转换而来（convert_topic6.py）。\n")

        # connections.yaml：该智能体需要的外部凭证（api_key 型，只声明名称与用途）
        conns = []
        if name == "coordinator":
            conns = [
                {"name": "datahub", "kind": "api_key", "secret_name": "DATAHUB_API_KEY", "purpose": "DataHub 标注服务", "allowed_hosts": []},
                {"name": "llm-relay", "kind": "api_key", "secret_name": "LLM_RELAY_API_KEY", "purpose": "沙箱脚本直连 bmc-llm-relay", "allowed_hosts": []},
                {"name": "blueai", "kind": "api_key", "secret_name": "BLUEAI_API_KEY", "purpose": "blueai 模型资源", "allowed_hosts": []},
            ]
        write(pkg / "connections.yaml", ("connections:\n" + "".join(
            f"  - name: {c['name']}\n    kind: {c['kind']}\n    secret_name: {c['secret_name']}\n    purpose: {c['purpose']}\n" for c in conns)) if conns else "connections: []\n")

    # —— 子智能体引用 + self ——
    wj(out / PKG["coordinator"] / "registry" / "agents.json", [
        {"id": PKG["annotator"], "range": "^1.0.0", "alias": "annotator"},
        {"id": PKG["validator"], "range": "^1.0.0", "alias": "validator"},
        {"id": "self"},
    ])

    # —— 知识：memory/ 三个文件 → coordinator/knowledge/（只读知识库）——
    kdir = out / PKG["coordinator"] / "knowledge"
    for f in sorted((src / "memory" / "topic6").iterdir()):
        write(kdir / "topic6" / f.name, f.read_text(encoding="utf-8"))
    write(out / PKG["coordinator"] / "knowledge.yaml", "roots:\n  - path: knowledge\n    description: topic6 跨会话业务记忆（必读清单、版本状态、错误案例库），只读\n")
    for n in (PKG["annotator"], PKG["validator"]):
        write(out / n / "knowledge.yaml", "roots: []\n")

    # —— 环境：dependencies/env_vars 放 coordinator（沙箱脚本都在 coordinator 触发的会话里跑）——
    pip = env.get("packages", {}).get("pip", [])
    env_vars, plat_env = [], {}
    for k, v in (env.get("env") or {}).items():
        m = ENV_PLACEHOLDER.match(str(v))
        if m:  # 含密钥/地址占位：构建时由 secrets 提供，不进包
            plat_env[k] = str(v)
        else:
            env_vars.append({"name": k, "value": str(v), "purpose": "topic6 运行环境"})
    wj(out / PKG["coordinator"] / "registry" / "environment.json", {
        "dependencies": {"python": pip, "node": [], "system": []},
        "tools": [], "network": {"mode": "unrestricted", "allowed_hosts": []},
        "env_vars": env_vars,
        "runtime": {"max_task_minutes": 240, "notes": "topic6 Producer 长流水线；setup_script 装 lark-cli 由 build-config 提供。"},
    })
    for n in (PKG["annotator"], PKG["validator"]):
        wj(out / n / "registry" / "environment.json", {"dependencies": {"python": [], "node": [], "system": []}, "tools": [], "network": {"mode": "unrestricted", "allowed_hosts": []}, "env_vars": []})

    # —— 平台侧：build-config.json ——
    coord = agents["coordinator"]
    wj(out / "build-config.json", {
        "spec": "1.5", "stage": "mvp",
        "model": coord["model"],
        "tools": coord.get("tools", []),
        "mcp_servers": coord.get("mcp_servers", []),
        "environment": {
            "type": env.get("type", "cloud"), "networking": env.get("networking", {"type": "unrestricted"}),
            "setup_script": env.get("setup_script", ""),
            "env": plat_env,
        },
        "credentials": {},
        "_说明": "env 中的 ${VAR} 与 mcp_servers 的 ${HOT_TOPICS_MCP_URL} 在构建时由 secrets.env 替换；credentials 值同样来自 secrets.env，不入库。",
    })
    print(f"已生成 {out}")
    print("skill 归属:", json.dumps(sk_owner, ensure_ascii=False))
    todo = {k: v for k, v in REGISTRY_SKILLS.items()}
    wj(out.parent.parent / "REGISTRY_TODO.json", {"说明": "需要在原子能力注册表登记的 skill（注册表冻结，由负责人登记）；包内以引用方式使用", "skills": todo})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
