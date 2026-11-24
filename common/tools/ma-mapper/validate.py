#!/usr/bin/env python3
"""ma-mapper 接收校验器原型（探测 1 · 阶段 A）

目的：实证《MA Agent 搭建映射规范（平台内部）》§3 的 20 项接收校验里，
哪些能**纯静态自动化**、哪些需平台查询、哪些需人工。用真实包（ada-pm）跑一遍看结果。

用法：python3 validate.py <数字员工目录>   # 例 .../topic-lab/ada-pm
输出：每项 --> [静态/需平台/需人工] PASS / FAIL / SKIP，附证据。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 智能体 ID：1–24 位小写字母/数字/连字符
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
# 脚本文件名禁用后缀
BAD_SUFFIX = re.compile(r"(_v\d+|_old|_new|_copy|_final|_bak)(\.|$)", re.I)
# 疑似密钥
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
]
MAX_KB = 100 * 1024  # 100 KiB
MAX_FILES_PER_DIR = 1990
MAX_MEM_STORES = 10  # 知识目录数 + 长期记忆库数

STATUS = {"static": "静态", "platform": "需平台", "manual": "需人工"}


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_packages(root: Path) -> dict[str, Path]:
    """数字员工目录下的智能体包目录（含 registry/agent.json 的）。"""
    out: dict[str, Path] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if (d / "registry" / "agent.json").exists():
            out[d.name] = d
    return out


def check_secret_scan(pkgs: dict[str, Path], results: list):
    hits = []
    for name, root in pkgs.items():
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix in (".pyc",):
                continue
            if "__pycache__" in f.parts:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in SECRET_PATTERNS:
                for m in pat.finditer(text):
                    hits.append(f"{name}/{f.relative_to(root)}: {m.group(0)[:60]}")
    results.append(("静态", "FAIL" if hits else "PASS", "密钥明文扫描", f"{len(hits)} 处疑似" if hits else "无"))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    pkgs = find_packages(root)
    if not pkgs:
        print(f"[错误] 未在 {root} 找到含 registry/agent.json 的智能体包")
        return 1
    print(f"== 数字员工目录 {root}  · 智能体包 {len(pkgs)} 个：{', '.join(pkgs)} ==")

    R: list[tuple[str, str, str, str]] = []  # (类型, 结果, 项, 证据)

    # 1. 三级目录 & agent.json id 一致 & 必需文件
    bad = []
    for name, p in pkgs.items():
        ag = load_json(p / "registry" / "agent.json")
        need_id = (p / "identity" / "identity.md").exists() and ag is not None
        if ag is None:
            bad.append(f"{name}: agent.json 缺失/非法")
        elif not ID_RE.match(name) or ag.get("id") != f"topic-lab.ada-pm.{name}":
            bad.append(f"{name}: id 不一致/非法 ({ag.get('id')})")
        elif not need_id:
            bad.append(f"{name}: 缺 identity/identity.md")
    R.append(("静态", "FAIL" if bad else "PASS", "1 三级目录/id 一致/必需文件", "; ".join(bad) or "全部通过"))

    # 2. 唯一归属（静态难判）——跳过
    R.append(("需人工", "SKIP", "2 信息唯一归属", "需语义判断，静态不可靠"))

    # 3. 密钥扫描（含 environment.json 环境变量值）
    check_secret_scan(pkgs, R)

    # 4. environment.json 依赖带版本下限
    nover = []
    for name, p in pkgs.items():
        env = load_json(p / "registry" / "environment.json")
        deps = (env or {}).get("dependencies", {})
        for manager, items in deps.items():
            for it in items or []:
                s = str(it)
                # 包名后必须跟版本约束（==/>=/<=/~=/>/<）
                if not re.search(r"[<>=~!]", s):
                    nover.append(f"{name}: {manager}/{s}")
    R.append(("静态", "FAIL" if nover else "PASS", "4 依赖带版本下限", "; ".join(nover[:5]) or "全部有版本约束"))

    # 5. connections.yaml 无凭证值、字段齐全
    conn_bad = []
    for name, p in pkgs.items():
        cf = p / "connections.yaml"
        if not cf.exists():
            continue
        text = cf.read_text(encoding="utf-8", errors="ignore")
        # 简单判：不在 connections.yaml 里出现长 token/secret 值；drop 掉空 connections: []
        if re.search(r"(?i)(secret|token|password|api_key|access_key|client_secret)\s*:\s*['\"]?[^\s'\"]{12,}", text):
            conn_bad.append(name)
    R.append(("静态", "FAIL" if conn_bad else "PASS", "5 connections 无凭证值", "; ".join(conn_bad) or "无凭证值（或空）"))

    # 6. 记忆库逐个决策 —— 需人工（本包无 memory/，跳过）
    has_mem = any((p / "memory" / "stores.yaml").exists() for p in pkgs.values())
    R.append(("需人工", "SKIP" if not has_mem else "需人工", "6 记忆库决策", "本数字员工未设长期记忆（无 memory/）" if not has_mem else "需人工核对"))

    # 7. 引用能力已登记 —— 需平台（查注册表）
    R.append(("需平台", "SKIP", "7 可复用能力已登记", "需查原子能力注册表，静态无法判定"))

    # 8. acceptance/cases.yaml
    acc_bad = []
    for name, p in pkgs.items():
        ag = load_json(p / "registry" / "agent.json")
        role = (ag or {}).get("role")
        cf = p / "acceptance" / "cases.yaml"
        if not cf.exists():
            acc_bad.append(f"{name}({role}): 缺 acceptance/cases.yaml")
            continue
        txt = cf.read_text(encoding="utf-8", errors="ignore")
        for k in ["category", "route", "agents", "input", "expected", "acceptor"]:
            if k not in txt:
                acc_bad.append(f"{name}: cases.yaml 缺字段 {k}")
    R.append(("静态", "FAIL" if acc_bad else "PASS", "8 验收用例（字段/存在性）", "; ".join(acc_bad[:6]) or "齐全"))

    # 9. 提示词标题从二级起 & handoff 角色定义
    h1 = []
    for name, p in pkgs.items():
        for f in (p / "identity").glob("*.md"):
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"^# ", line):  # 一级标题
                    h1.append(f"{name}/{f.name}:{i}")
    R.append(("静态", "FAIL" if h1 else "PASS", "9 提示词文件内标题从二级起", "; ".join(h1[:5]) or "全部从 ## 起"))

    # 10. knowledge.yaml 目录存在
    ky_bad = []
    for name, p in pkgs.items():
        ky = p / "knowledge.yaml"
        if not ky.exists():
            continue
        roots = re.findall(r"path:\s*(\S+)", ky.read_text(encoding="utf-8"))
        for rel in roots:
            if not (p / rel).is_dir():
                ky_bad.append(f"{name}: knowledge/{rel} 不存在")
    R.append(("静态", "FAIL" if ky_bad else "PASS", "10 knowledge.yaml 目录存在", "; ".join(ky_bad) or "目录均存在"))

    # 11. 容量：知识文件 ≤100KiB、每个知识目录（knowledge.yaml 声明的 root）文件数 ≤1990、知识目录数+记忆库数 ≤10
    cap_bad = []
    kdir_count = 0
    for name, p in pkgs.items():
        ky = p / "knowledge.yaml"
        roots = re.findall(r"path:\s*(\S+)", ky.read_text(encoding="utf-8")) if ky.exists() else []
        if not roots and (p / "knowledge").is_dir():
            roots = ["knowledge"]
        for rel in roots:
            d = p / rel
            if not d.is_dir():
                continue
            kdir_count += 1
            files = [f for f in d.rglob("*") if f.is_file()]
            if len(files) > MAX_FILES_PER_DIR:
                cap_bad.append(f"{name}/{rel}: {len(files)} 文件 > {MAX_FILES_PER_DIR}")
            for f in files:
                if f.stat().st_size > MAX_KB:
                    cap_bad.append(f"{name}/{f.relative_to(p)}: {f.stat().st_size} > 100KiB")
    if kdir_count > MAX_MEM_STORES:
        cap_bad.append(f"知识目录数+记忆库数 {kdir_count} > {MAX_MEM_STORES}")
    R.append(("静态", "FAIL" if cap_bad else "PASS", "11 容量（100KiB/1990/10）", "; ".join(cap_bad[:4]) or f"通过（知识目录 {kdir_count} 个）"))

    # 12. role/visibility/agents.json 约束
    role_bad = []
    mains = [n for n, p in pkgs.items() if (load_json(p / "registry" / "agent.json") or {}).get("role") == "main"]
    if len(mains) != 1:
        role_bad.append(f"main 数量 = {len(mains)}（应=1）")
    for name, p in pkgs.items():
        ag = load_json(p / "registry" / "agent.json") or {}
        if ag.get("role") not in ("main", "sub"):
            role_bad.append(f"{name}: role 非法 {ag.get('role')}")
        if ag.get("role") == "sub" and ag.get("visibility") != "internal":
            role_bad.append(f"{name}(sub): visibility={ag.get('visibility')}（应 internal）")
        if ag.get("role") == "sub" and (p / "registry" / "agents.json").exists():
            role_bad.append(f"{name}(sub): 不得有 agents.json")
    main = pkgs.get(mains[0]) if mains else None
    if main:
        ags = load_json(main / "registry" / "agents.json")
        refs = {a.get("id") for a in (ags or [])}
        for rid in refs:
            if rid not in pkgs or (load_json(pkgs[rid] / "registry" / "agent.json") or {}).get("role") != "sub":
                role_bad.append(f"main 引用 {rid} 非法（不存在或非 sub）")
    R.append(("静态", "FAIL" if role_bad else "PASS", "12 角色与引用（main 唯一/sub 约束）", "; ".join(role_bad) or "通过"))

    # 13. 增量 change-set —— 本目录无 change-set.yaml，跳过
    R.append(("静态", "SKIP", "13 增量 change-set", "非增量交付，无 change-set.yaml"))

    # 14. sub 提示词不含具体 main/数字员工名
    sub_leak = []
    emp = "ada-pm"
    for name, p in pkgs.items():
        ag = load_json(p / "registry" / "agent.json") or {}
        if ag.get("role") != "sub":
            continue
        for f in (p / "identity").glob("*.md"):
            txt = f.read_text(encoding="utf-8")
            if emp in txt or "main" in txt.lower() and "pm" in txt.lower():
                # 粗判：出现 "ada-pm" 或 "pm" 角色名
                if re.search(rf"\b{emp}\b|\bpm\b", txt):
                    sub_leak.append(f"{name}/{f.name}")
    R.append(("静态", "WARN" if sub_leak else "PASS", "14 sub 提示词不嵌入 main/员工名", "; ".join(sub_leak) or "未见明显泄漏"))

    # 15. 脚本文件名后缀
    suffix_bad = []
    for name, p in pkgs.items():
        for f in p.rglob("*.py"):
            if BAD_SUFFIX.search(f.stem):
                suffix_bad.append(f"{name}/{f.relative_to(p)}")
    R.append(("静态", "FAIL" if suffix_bad else "PASS", "15 脚本文件名无版本后缀", "; ".join(suffix_bad[:5]) or "通过"))

    # 16. 会话级资源合并冲突（静态：同名声明 + environment 版本冲突）
    merge_bad = []
    envs = [load_json(p / "registry" / "environment.json") for p in pkgs.values()]
    pyvers = {str(e.get("dependencies", {}).get("python")) for e in envs if e}
    if len(pyvers) > 1:
        merge_bad.append(f"python 依赖声明不一致：{pyvers}")
    R.append(("静态", "FAIL" if merge_bad else "PASS", "16 会话级合并无冲突（粗判）", "; ".join(merge_bad) or "environment 声明一致"))

    # 17. internal 白名单 —— 需平台（查飞书应用）
    R.append(("需平台", "SKIP", "17 internal 渠道白名单非空", "需查飞书应用可用范围"))

    # 18. 压缩包完整性 —— 需平台/网络
    R.append(("需平台", "SKIP", "18 压缩包下载/SHA-256/解压安全", "需压缩包产物，静态目录态不适用"))

    # 19. 版本身份核对 —— 对目录态：agent.json version vs version_mapping
    ver_bad = []
    for name, p in pkgs.items():
        ag = load_json(p / "registry" / "agent.json") or {}
        if not re.match(r"^\d+\.\d+\.\d+$", str(ag.get("version", ""))):
            ver_bad.append(f"{name}: version 非法 {ag.get('version')}")
    R.append(("静态", "FAIL" if ver_bad else "PASS", "19 版本号语义化", "; ".join(ver_bad) or "均为语义化版本"))

    # 20. Skill 脚本自包含（../ 或绝对路径引用 & 读 registry/io）
    self_bad = []
    for name, p in pkgs.items():
        sk = p / "skills"
        for f in (sk.rglob("*.py") if sk.exists() else []):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\.\./|/registry/|/io\.?/|/mnt/", txt):
                self_bad.append(f"{name}/{f.relative_to(p)}")
    R.append(("静态", "WARN" if self_bad else "PASS", "20 Skill 脚本自包含", f"{len(self_bad)} 处疑似越界引用" if self_bad else "未见 ../ 或 registry/io 引用"))

    # ---- 输出 ----
    print(f"\n{'类型':<6} {'结果':<8} {'项':<34} 证据")
    print("-" * 96)
    n_static = n_platform = n_manual = 0
    n_fail = n_warn = 0
    for typ, res, item, ev in R:
        print(f"{typ:<6} {res:<8} {item:<34} {ev}")
        if typ == "静态":
            n_static += 1
            if res in ("FAIL", "WARN"):
                n_fail += 1
        elif typ == "需平台":
            n_platform += 1
        else:
            n_manual += 1
    print("-" * 96)
    print(f"合计：静态可自动化 {n_static} 项（其中 FAIL/WARN {n_fail}）、需平台 {n_platform} 项、需人工 {n_manual} 项")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main())