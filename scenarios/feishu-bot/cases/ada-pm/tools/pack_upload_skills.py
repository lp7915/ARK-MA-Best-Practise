#!/usr/bin/env python3
"""打包并上传 ada-pm 的 3 个自有 Skill 到方舟 SkillHub。

约定与 topic5 的 pack_skills.sh + upload_skills.py 一致：
- 每个 skill 目录打包成 zip，zip 内为唯一顶层目录 <skill_name>/，其下直接含唯一 SKILL.md；
- SKILL.md 的 name 须匹配 ^[a-z0-9-]{1,64}$；
- 上传 /skills，用 ARK_API_KEY + X-Ark-Beta 头；
- 按内容 sha256 去重（内容不变不重传），结果写入 skill_ids.json。

work-item 与 atomic-ops 在迁移后是 t/g/s/validator 四个子包的等值副本，任意取一份打包即可
（上传后得到的 skill_id 供 4 个子 Agent 共同引用）。

使用：
    export ARK_API_KEY=...  [ARK_BASE_URL=...]
    python3 pack_upload_skills.py [--force] [--only pm-orchestrator]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import tempfile
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]         # cases/ada-pm
RES = ROOT / "ma-resources" / "topic-lab" / "ada-pm"
SKILL_IDS_FILE = ROOT / "ma-resources" / "skill_ids.json"

_raw_base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
BASE_URL = _raw_base if _raw_base.endswith("/api/v3") else f"{_raw_base}/api/v3"
ARK_BETA_HEADER = {"X-Ark-Beta": "agentic-2026-06-01"}

# key -> （源目录相对 RES、打包顶层名、展示标题）
SKILLS = [
    ("pm-orchestrator", "pm/skills/pm-orchestrator", "pm-orchestrator", "Ada PM · 红线路由脚本与真实 MA 协作约定"),
    ("work-item",       "t/skills/work-item",        "work-item",      "Ada PM · 子 Agent 工作项执行入口（run.py）"),
    ("atomic-ops",      "t/skills/atomic-ops",       "atomic-ops",     "Ada PM · 六项确定性原子能力"),
]


def load_state() -> dict:
    if SKILL_IDS_FILE.exists():
        return json.loads(SKILL_IDS_FILE.read_text(encoding="utf-8"))
    return {"note": "由 pack_upload_skills.py 上传成功后回填", "skills": {}}


def save_state(state: dict) -> None:
    SKILL_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SKILL_IDS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def skill_name_from_md(skill_dir: Path) -> str:
    md = skill_dir / "SKILL.md"
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    # 兜底：第一个一级标题
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def pack(skill_dir: Path, top_name: str) -> tuple[str, str]:
    """打包 skill_dir 为 zip（顶层目录 top_name），返回 (zip 路径, sha256)。"""
    md = skill_dir / "SKILL.md"
    if not md.exists():
        raise RuntimeError(f"{skill_dir} 缺 SKILL.md")
    name = skill_name_from_md(skill_dir)
    if not name or not all(c.islower() or c.isdigit() or c == "-" for c in name) or len(name) > 64:
        raise RuntimeError(f"SKILL.md name 不合法: {name!r}")

    total = 0
    count = 0
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(skill_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.name in (".DS_Store",) or "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            arcname = f"{top_name}/{f.relative_to(skill_dir).as_posix()}"
            data = f.read_bytes()
            zf.writestr(arcname, data)
            total += len(data)
            count += 1
    sha = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    if total > 120 * 1024 * 1024 or count > 500 or os.path.getsize(zip_path) > 30 * 1024 * 1024:
        os.remove(zip_path)
        raise RuntimeError(f"{top_name} 超 Skill 体量上限（files={count}, unpacked={total}）")
    return zip_path, sha


def upload(key: str, src_rel: str, top_name: str, title: str, force: bool) -> dict | None:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ARK_API_KEY")
    skill_dir = RES / src_rel
    if not skill_dir.exists():
        print(f"  [跳过] {skill_dir} 不存在")
        return None
    zip_path, sha = pack(skill_dir, top_name)
    state = load_state()
    existing = state["skills"].get(key)
    if existing and not force and existing.get("source_sha256") == sha:
        print(f"  [跳过] {key} 内容未变（sha256={sha[:12]}…）skill_id={existing.get('skill_id')}")
        return existing
    print(f"=== 上传 {key}（{title}）===")
    with open(zip_path, "rb") as fh:
        resp = requests.post(
            f"{BASE_URL}/skills",
            headers={"Authorization": f"Bearer {api_key}", **ARK_BETA_HEADER},
            files={"files": (f"{top_name}.zip", fh, "application/zip")},
            data={"display_title": title},
            timeout=300,
        )
    os.remove(zip_path)
    if not resp.ok:
        raise RuntimeError(f"上传失败 status={resp.status_code} body={resp.text[:600]}")
    payload = resp.json()
    record = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    skill_id = record.get("id")
    if not skill_id:
        raise RuntimeError(f"上传成功但响应无 id: {json.dumps(payload, ensure_ascii=False)[:600]}")
    entry = {
        "skill_id": skill_id,
        "version": record.get("latest_version", "1"),
        "uploaded_at": int(time.time()),
        "source_sha256": sha,
        "display_title": title,
    }
    state["skills"][key] = entry
    save_state(state)
    print(f"  ok · skill_id={skill_id} · version={entry['version']}")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="只上传指定 key")
    args = ap.parse_args()
    for key, src_rel, top_name, title in SKILLS:
        if args.only and args.only != key:
            continue
        upload(key, src_rel, top_name, title, args.force)
    print(f"\n完成 → {SKILL_IDS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())