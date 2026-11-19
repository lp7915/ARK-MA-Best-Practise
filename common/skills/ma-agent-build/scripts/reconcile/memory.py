"""知识库（Memory Store）的声明式 reconcile：容器 + 条目（映射规范 6.8）。

对比方式（用户决策：台账每个知识库一行，存汇总指纹）：
- 台账行 kind=memory_store：
    fingerprint = 整库声明内容的汇总指纹（各文件指纹按 path 排序后再 sha256）
    note        = JSON {path: 文件指纹}，上次成功写入的逐文件指纹（供定位哪些文件变了）
- 文件新增 / 删除：以 MA `list memories` 的 path 集合为准（可靠，不依赖哈希）；
- 文件修改：本地指纹 ≠ 台账记录的该文件指纹；汇总指纹一致则整库跳过逐文件比对；
- 不与服务端 content_sha256 比对（实测对中文/带换行内容无法复现其算法）。

MA 行为（实测）：同 path 再 POST 返回 409，更新必须 POST /memories/{id}（id 不变）；
服务端会吞掉内容结尾的换行，因此本地指纹对「去掉结尾换行」后的内容计算，避免误判。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ledger
import ma_api
from reconcile import ADOPT, CREATE, DELETE, NOOP, UPDATE, Action


def knowledge_entries(pkg_dir: Path, root: str) -> dict[str, str]:
    """{path: content}。path 形如 `/standards/x.md`；索引条目 `/_索引.md` 由构建器生成。"""
    kdir = pkg_dir / root
    entries: dict[str, str] = {}
    rels: list[str] = []
    for f in sorted(kdir.rglob("*")):
        if not f.is_file() or f.suffix not in (".md", ".txt"):
            continue
        rel = f.relative_to(kdir).as_posix()
        rels.append(rel)
        entries[f"/{rel}"] = f.read_text(encoding="utf-8")
    entries["/_索引.md"] = "# 索引\n\n" + "\n".join(f"- /{r}" for r in rels) + "\n"
    return entries


def file_fp(content: str) -> str:
    """单文件内容指纹（我们自己算，口径永远一致）。对去掉结尾换行后的内容计算，规避服务端吞换行。"""
    return hashlib.sha256(content.rstrip("\n").encode("utf-8")).hexdigest()[:16]


def store_fp(file_fps: dict[str, str]) -> str:
    """整库汇总指纹：path 排序后拼接 `path:指纹`，再 sha256。任一文件增删改都会变化。"""
    blob = "\n".join(f"{p}:{fp}" for p, fp in sorted(file_fps.items()))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def list_remote_paths(store_id: str) -> dict[str, str]:
    """{path: memory_id}，只含 type=memory 的条目（跳过折叠目录项）。分页拉全。"""
    out: dict[str, str] = {}
    page = ""
    while True:
        q = f"/memory_stores/{store_id}/memories?limit=200" + (f"&page={page}" if page else "")
        body = ma_api.ark_get(q)
        if "_err" in body:
            raise RuntimeError(f"读取知识库 {store_id} 条目失败: {body}")
        for it in ma_api.payload_to_items(body):
            if it.get("type") == "memory" and it.get("path"):
                out[it["path"]] = it["id"]
        page = body.get("next_page") if isinstance(body, dict) else ""
        if not page:
            break
    return out


def _recorded_fps(row) -> dict[str, str]:
    """台账行 note 里记录的逐文件指纹；解析失败视为未记录（全部按修改处理）。"""
    if not row:
        return {}
    try:
        data = json.loads(row.fields.get("note") or "{}")
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def plan(ctx: dict) -> list[Action]:
    """只读：每个知识库产出 1 条容器动作（含条目变更计数）+ 逐条变更的条目动作（noop 条目不产出，避免报告膨胀）。"""
    bl, emp = ctx["business_line"], ctx["employee"]
    rows = ctx["ledger_rows"]
    actions: list[Action] = []
    declared: set[str] = set()

    for (pkg, root), name in ctx["names"]["memory_store"].items():
        skey = ledger.make_key(bl, emp, "memory_store", f"{pkg}:{root}")
        declared.add(skey)
        desired = knowledge_entries(ctx["emp_dir"] / pkg, root)
        want_fps = {p: file_fp(c) for p, c in desired.items()}
        want_store_fp = store_fp(want_fps)
        actual = ctx["ma"].get("memory_store", {}).get(name)
        row = rows.get(skey)

        if not actual:
            actions.append(Action(kind="memory_store", key=skey, op=CREATE, name=name, detail=f"新建，{len(desired)} 个文件",
                                  payload={"entries": desired, "fps": want_fps, "store_fp": want_store_fp,
                                           "pkg": pkg, "root": root}, group=name))
            continue

        store_id = str(actual.get("id") or "")
        tracked = bool(row and row.status == "active")
        remote = list_remote_paths(store_id)
        recorded = _recorded_fps(row) if tracked else {}

        # 逐文件判定
        add = [p for p in desired if p not in remote]
        remove = [p for p in remote if p not in desired]
        if tracked and row.fingerprint == want_store_fp and not add and not remove:
            changed: list[str] = []  # 汇总指纹一致 → 整库内容未变，跳过逐文件比对
        else:
            changed = [p for p in desired if p in remote and recorded.get(p) != want_fps[p]]

        if not tracked:
            op, detail = ADOPT, f"MA 已存在 {store_id}，台账未记录"
        elif add or remove or changed:
            op = UPDATE
            detail = f"新增 {len(add)} · 修改 {len(changed)} · 删除 {len(remove)}"
        else:
            op, detail = NOOP, ""
        actions.append(Action(kind="memory_store", key=skey, op=op, name=name, ma_id=store_id, detail=detail,
                              payload={"entries": desired, "fps": want_fps, "store_fp": want_store_fp,
                                       "add": add, "changed": changed, "remove": remove, "remote": remote,
                                       "pkg": pkg, "root": root}, group=name))
        # 首次认领时，台账没有逐文件指纹，无法区分「真变了」与「没记录」：认领只补登，不写条目；
        # 认领后的下一次构建才有基线。条目差异中仅 add/remove 在认领阶段就需要处理，故仍列出。
        if op == ADOPT and (add or remove):
            actions[-1].warnings.append(f"认领时发现 新增 {len(add)} · 删除 {len(remove)} 个文件差异，认领后下次构建处理")

    # 孤儿知识库：台账 active、声明里已无
    for key, row in rows.items():
        if row.kind == "memory_store" and row.status == "active" and key not in declared:
            actions.append(Action(kind="memory_store", key=key, op=DELETE, name=row.fields.get("resource_name", key),
                                  ma_id=row.ma_id, detail="声明已无该知识库（孤儿）", group=key))
    return actions


def _upsert_store(ctx: dict, a: Action, store_id: str, fps: dict, sfp: str, note_extra: str = "") -> None:
    pkg_root = a.key.split("/memory_store/", 1)[1]
    ledger.upsert(ctx["ledger_rows"], business_line=ctx["business_line"], employee=ctx["employee"],
                  kind="memory_store", name=pkg_root, resource_name=a.name, ma_id=store_id,
                  agent=pkg_root.split(":")[0], fingerprint=sfp,
                  stage=ctx["stage"], build_id=ctx["build_id"], note=json.dumps(fps, ensure_ascii=False, sort_keys=True))


def apply(ctx: dict, actions: list[Action]) -> dict:
    """执行。返回 {"memory_stores": {name: id}, "knowledge_map": {(pkg, root): id}}。"""
    bl, emp = ctx["business_line"], ctx["employee"]
    stores: dict[str, str] = {}
    kmap: dict[tuple[str, str], str] = {}

    for a in actions:
        if a.kind != "memory_store":
            continue
        pl = a.payload
        if a.op == DELETE:
            ma_api.ark_delete(f"/memory_stores/{a.ma_id}")
            ledger.mark_deleted(ctx["ledger_rows"], a.key, ctx["build_id"], "声明已移除")
            print(f"  知识库已删除: {a.name} -> {a.ma_id}")
            continue

        if a.op == CREATE:
            resp = ma_api.ark_post("/memory_stores", {"name": a.name, "description": f"{bl}/{emp} 知识库（只读）"})
            a.ma_id = ma_api.unwrap_id(resp)
            for path, content in sorted(pl["entries"].items()):
                ma_api.ark_post(f"/memory_stores/{a.ma_id}/memories", {"path": path, "content": content})
            print(f"  知识库已创建: {a.name} -> {a.ma_id}（{len(pl['entries'])} 个文件）")
            _upsert_store(ctx, a, a.ma_id, pl["fps"], pl["store_fp"])
        elif a.op == UPDATE:
            remote = pl["remote"]
            for path in pl["add"]:
                ma_api.ark_post(f"/memory_stores/{a.ma_id}/memories", {"path": path, "content": pl["entries"][path]})
            for path in pl["changed"]:
                ma_api.ark_post(f"/memory_stores/{a.ma_id}/memories/{remote[path]}", {"content": pl["entries"][path]})
            for path in pl["remove"]:
                ma_api.ark_delete(f"/memory_stores/{a.ma_id}/memories/{remote[path]}")
            print(f"  知识库已更新: {a.name}（{a.detail}）")
            _upsert_store(ctx, a, a.ma_id, pl["fps"], pl["store_fp"])
        elif a.op == ADOPT:
            # 只补登容器，不写条目，也不记汇总指纹（没有可信基线）；下次构建会因指纹不一致逐文件对比
            pkg_root = a.key.split("/memory_store/", 1)[1]
            ledger.upsert(ctx["ledger_rows"], business_line=bl, employee=emp, kind="memory_store", name=pkg_root,
                          resource_name=a.name, ma_id=a.ma_id, agent=pkg_root.split(":")[0],
                          stage=ctx["stage"], build_id=ctx["build_id"], note="{}")
            print(f"  台账补登: 知识库 {a.name} -> {a.ma_id}")

        if a.ma_id:
            stores[a.name] = a.ma_id
            kmap[(pl.get("pkg", ""), pl.get("root", ""))] = a.ma_id
    return {"memory_stores": stores, "knowledge_map": kmap}
