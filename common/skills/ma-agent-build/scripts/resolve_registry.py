#!/usr/bin/env python3
"""过渡：把包内以注册表 atomic_id 引用的 skill 解析成 MA skill_id 并锁定。

正式形态是中台在构建/升级时查原子能力注册表（address.ma_skill_id + 版本锁定，映射规范 7.5）。
注册表当前冻结且无此记录，所以这里用 `<根>/_registry_src/<本地名>/`（模拟注册表 address 指向的仓库）
上传 skill，产出 `<数字员工>/registry_resolved.json`（atomic_id → {skill_id, version}），供 build.py 读取。

用法：python3 resolve_registry.py <根目录> <数字员工目录>
  根目录含 REGISTRY_TODO.json 与 _registry_src/；ARK_API_KEY 需已导出。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pack_skills


def main() -> int:
    root, emp = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    todo = json.loads((root / "REGISTRY_TODO.json").read_text(encoding="utf-8"))["skills"]
    src_root = root / "_registry_src"
    resolved = {}
    for local_name, atomic_id in todo.items():
        entry = pack_skills.upload(src_root, local_name, src_root / local_name, force=False)
        resolved[atomic_id] = {"skill_id": entry["skill_id"], "version": entry["version"], "source": f"_registry_src/{local_name}"}
    out = emp / "registry_resolved.json"
    out.write_text(json.dumps({"note": "过渡：模拟注册表解析+锁定；正式由中台写入", "skills": resolved}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
