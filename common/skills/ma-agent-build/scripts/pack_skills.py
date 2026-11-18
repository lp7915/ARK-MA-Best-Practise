#!/usr/bin/env python3
"""泛化：把数字员工声明目录里各智能体包 `registry/skills.json` 引用的 Skill 打包并上传到方舟 SkillHub。

与原 ada-pm 的 tools/pack_upload_skills.py 等价，但不再硬编码 skill 清单：
- 扫描 `<数字员工>/<各智能体>/registry/skills.json`，聚合所有被引用的 skill id（去重）；
- 对每个 id，取第一个包含 `skills/<id>/SKILL.md` 的智能体包作为源码（同名 skill 多个包引用时只打包一份）；
- 按内容 sha256 去重（内容不变不重传），结果回写 `<数字员工>/skill_ids.json`。

使用：
    export ARK_API_KEY=...  [ARK_BASE_URL=...]
    python3 pack_skills.py <数字员工目录> [--force] [--only <skill id>]
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

_raw_base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
BASE_URL = _raw_base if _raw_base.endswith("/api/v3") else f"{_raw_base}/api/v3"
ARK_BETA_HEADER = {"X-Ark-Beta": "agentic-2026-06-01"}

MAX_UNPACKED = 120 * 1024 * 1024  # 解包体量上限（字节）
MAX_FILES = 500
MAX_ZIP = 30 * 1024 * 1024  # 上传单包上限（字节）


def discover_skills(emp_dir: Path) -> list[tuple[str, Path]]:
    """返回有序去重后的 (skill_id, 源码目录)。按智能体目录名序、包内 skills.json 顺序聚合，id 首次出现则取其源码目录。"""
    seen: dict[str, Path] = {}
    for pkg in sorted(p for p in emp_dir.iterdir() if p.is_dir()):
        sj = pkg / "registry" / "skills.json"
        if not sj.exists():
            continue
        for ref in json.loads(sj.read_text(encoding="utf-8")):
            sid = ref.get("id")
            if not sid or sid in seen:
                continue
            src = pkg / "skills" / sid
            if (src / "SKILL.md").exists():
                seen[sid] = src
    return list(seen.items())


def load_state(emp_dir: Path) -> dict:
    f = emp_dir / "skill_ids.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"note": "由 pack_skills.py 上传成功后回填", "skills": {}}


def save_state(emp_dir: Path, state: dict) -> None:
    (emp_dir / "skill_ids.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def skill_name_from_md(skill_dir: Path) -> str:
    md = skill_dir / "SKILL.md"
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def pack(skill_dir: Path, top_name: str) -> tuple[str, str]:
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
            if not f.is_file() or f.name == ".DS_Store" or "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            data = f.read_bytes()
            zf.writestr(f"{top_name}/{f.relative_to(skill_dir).as_posix()}", data)
            total += len(data)
            count += 1
    size = os.path.getsize(zip_path)
    if total > MAX_UNPACKED or count > MAX_FILES or size > MAX_ZIP:
        os.remove(zip_path)
        raise RuntimeError(f"{top_name} 超 Skill 体量上限（files={count}, unpacked={total}, zip={size}）")
    sha = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    return zip_path, sha


def upload(emp_dir: Path, sid: str, src: Path, force: bool) -> dict | None:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ARK_API_KEY")
    state = load_state(emp_dir)
    zip_path, sha = pack(src, sid)
    existing = state["skills"].get(sid)
    if existing and existing.get("skill_id") and not force and existing.get("source_sha256") == sha:
        print(f"  [跳过] {sid} 内容未变（sha256={sha[:12]}…）skill_id={existing.get('skill_id')} v{existing.get('version')}")
        return existing

    headers = {"Authorization": f"Bearer {api_key}", **ARK_BETA_HEADER}
    if existing and existing.get("skill_id"):
        # 内容变化 -> 创建新版本：skill_id 不变，version 递增（方舟 POST /skills/{id}/versions）
        skill_id = existing["skill_id"]
        print(f"=== 更新 {sid} → 新版本（skill_id={skill_id}，原 v{existing.get('version')}）===")
        with open(zip_path, "rb") as fh:
            resp = requests.post(
                f"{BASE_URL}/skills/{skill_id}/versions",
                headers=headers,
                files={"files": (f"{sid}.zip", fh, "application/zip")},
                data={"display_title": sid},
                timeout=300,
            )
        os.remove(zip_path)
        if not resp.ok:
            raise RuntimeError(f"更新失败 status={resp.status_code} body={resp.text[:600]}")
        record = (resp.json() or {}).get("data") or resp.json()
        new_version = record.get("version")
        if not new_version:
            raise RuntimeError(f"更新成功但响应无 version: {json.dumps(resp.json(), ensure_ascii=False)[:600]}")
        entry = {
            "skill_id": skill_id,
            "version": new_version,
            "uploaded_at": int(time.time()),
            "source_sha256": sha,
            "display_title": sid,
        }
    else:
        print(f"=== 创建 {sid}（首次上传）===")
        with open(zip_path, "rb") as fh:
            resp = requests.post(
                f"{BASE_URL}/skills",
                headers=headers,
                files={"files": (f"{sid}.zip", fh, "application/zip")},
                data={"display_title": sid},
                timeout=300,
            )
        os.remove(zip_path)
        if not resp.ok:
            raise RuntimeError(f"上传失败 status={resp.status_code} body={resp.text[:600]}")
        record = (resp.json() or {}).get("data") or resp.json()
        skill_id = record.get("id")
        if not skill_id:
            raise RuntimeError(f"上传成功但响应无 id: {json.dumps(resp.json(), ensure_ascii=False)[:600]}")
        entry = {
            "skill_id": skill_id,
            "version": record.get("latest_version", "1"),
            "uploaded_at": int(time.time()),
            "source_sha256": sha,
            "display_title": sid,
        }
    state["skills"][sid] = entry
    save_state(emp_dir, state)
    print(f"  ok · skill_id={entry['skill_id']} · version={entry['version']}")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("emp_dir", help="数字员工目录（<业务线>/<数字员工>/）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="只上传指定 skill id")
    args = ap.parse_args()
    emp_dir = Path(args.emp_dir).resolve()
    if not (emp_dir / "build-config.json").exists():
        print(f"提示：{emp_dir} 下无 build-config.json，仍继续上传 skill。", file=sys.stderr)
    for sid, src in discover_skills(emp_dir):
        if args.only and args.only != sid:
            continue
        upload(emp_dir, sid, src, args.force)
    print(f"\n完成 → {emp_dir / 'skill_ids.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())