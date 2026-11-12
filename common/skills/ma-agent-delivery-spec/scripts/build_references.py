#!/usr/bin/env python3
"""从《MA Agent 搭建交付规范》与《容量限制说明》生成 skill 的 references/。

规范是唯一事实源：本脚本按章节切分并写入 references/，不要手工编辑生成的文件。
规范改版后重新运行即可；SPLIT 里定义的章节映射必须跟着规范结构一起维护。

用法：python3 scripts/build_references.py [--check]
  --check  只比对生成的 references 与当前规范是否一致，不写文件；不一致退出码 1
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
REF_DIR = SKILL_DIR / "references"
DOCS = SKILL_DIR.parents[1] / "docs" / "analyst-env"

SPEC = DOCS / "MA-Agent搭建交付规范.md"
CAPACITY = DOCS / "MA-Agent搭建容量限制说明.md"

# 输出文件 -> (标题, 取哪些章节)
# 章节按二级标题的编号前缀匹配；子章节用 "2.3" 这样的编号精确匹配。
# 未列出的章节不会进入 skill（修订记录、占位示例等不包含）。
SPLIT: list[tuple[str, str, list[tuple[str, list[str] | None]]]] = [
    (
        "01-basics.md",
        "交付物与目录",
        [("1.", None), ("2.", ["2.1", "2.2"]), ("3.", None)],
    ),
    (
        "02-roles-and-increments.md",
        "角色、引用与增量交付",
        [("2.", ["2.3", "2.4", "2.5", "2.6"])],
    ),
    ("03-formats.md", "各类内容的格式要求", [("5.", None)]),
    ("04-capabilities.md", "可复用能力与版本", [("6.", None), ("7.", None)]),
    (
        "05-acceptance.md",
        "验收与检查单",
        [("9.", None), ("附录：收集表与交付物的对应", None), ("附录：配套文档", None)],
    ),
    ("06-workspace-security.md", "工作空间与安全", [("4.", None), ("8.", None)]),
]


def parse(md: Path) -> list[dict]:
    """切成块。返回 [{level, num, title, lines}]，只认围栏代码块之外的标题。"""
    blocks: list[dict] = []
    fence = False
    cur = {"level": 0, "num": "", "title": "", "lines": []}
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{2,3}) (.+)$", line)
        if m:
            blocks.append(cur)
            level = len(m.group(1))
            title = m.group(2).strip()
            num = (re.match(r"^(\d+(?:\.\d+)?)\.?\s", title) or [None, ""])[1]
            cur = {"level": level, "num": num, "title": title, "lines": [line]}
        else:
            cur["lines"].append(line)
    blocks.append(cur)
    return blocks


def compose(blocks: list[dict], picks: list[tuple[str, list[str] | None]], src_name: str, ver: str) -> str:
    """按 picks 取章节。blocks 是扁平列表，整章 = 从该二级标题切到下一个二级标题。"""
    idx2 = [i for i, b in enumerate(blocks) if b["level"] == 2]
    out: list[str] = []
    for key, subs in picks:
        hit = next((i for i in idx2 if blocks[i]["title"].startswith(key)), None)
        if hit is None:
            raise SystemExit(f"{src_name}: 找不到章节 {key}")
        end = next((j for j in idx2 if j > hit), len(blocks))
        if subs is None:
            for b in blocks[hit:end]:
                out.extend(b["lines"])
            continue
        # 只取指定子章节；保留章首导语（第一处 ### 之前的内容）
        seg = blocks[hit:end]
        out.extend(seg[0]["lines"])
        for b in seg[1:]:
            if b["level"] != 3:
                continue
            if any(b["title"].startswith(s) for s in subs):
                out.extend(b["lines"])
        # 保留章末、子章节之后的少量导语(如有)
    body = "\n".join(out).rstrip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    head = (
        f"<!-- 由 scripts/build_references.py 从《MA Agent 搭建交付规范》{ver} 生成，勿手改。 -->\n"
        f"> 来源：《MA Agent 搭建交付规范》{ver}。"
        f"本文件只摘录该规范的对应章节，规则以规范原文为准；两者不一致时以规范为准。\n\n"
    )
    return head + body + "\n"


def build() -> dict[str, str]:
    spec_text = SPEC.read_text(encoding="utf-8")
    m = re.search(r"^> 版本：(\S+)", spec_text, re.M)
    ver = m.group(1) if m else "(未知版本)"
    blocks = parse(SPEC)
    files: dict[str, str] = {}
    for name, _title, picks in SPLIT:
        files[name] = compose(blocks, picks, SPEC.name, ver)
    # 容量说明整篇（去掉一级标题，保留引用块）
    cap = CAPACITY.read_text(encoding="utf-8")
    cap_body = "\n".join(cap.splitlines()[1:]).lstrip("\n")
    cm = re.search(r"^> 版本：(\S+)", cap, re.M)
    cver = cm.group(1) if cm else "(未知版本)"
    files["07-capacity.md"] = (
        f"<!-- 由 scripts/build_references.py 从《MA Agent 搭建容量限制说明》{cver} 生成，勿手改。 -->\n"
        f"> 来源：《MA Agent 搭建容量限制说明》{cver}（随交付规范 {ver} 一并提供）。"
        f"本文件为全文摘录。\n\n{cap_body.rstrip()}\n"
    )
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()
    files = build()
    bad = 0
    for name, text in files.items():
        path = REF_DIR / name
        if args.check:
            disk = path.read_text(encoding="utf-8") if path.exists() else ""
            if disk != text:
                print(f"过期: {name}", file=sys.stderr)
                bad += 1
            continue
        REF_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        size = len(text.encode())
        flag = "  ⚠ 超过 100 KiB" if size > 102_400 else ""
        print(f"{name:32s} {size:7d} bytes  sha256={hashlib.sha256(text.encode()).hexdigest()[:12]}{flag}")
    if args.check:
        print("references 与规范一致" if not bad else f"{bad} 个文件过期", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
