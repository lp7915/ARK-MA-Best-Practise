"""MA 事件流 → Pilot 规范记录(gen_ai.* 点分字段)。

只做格式转换,不做推断:拿不到的字段(模型名、thinking 内容)不填,保持缺失。
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from typing import Any, Optional

_EXIT = re.compile(r"exit_code:\s*(-?\d+)")
_SKILL_DIR = re.compile(r"/mnt/skills/([^/\s\"']+)/")
_NODE = re.compile(r"bsm-obs-run\.cjs\s+run\s+([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+){0,2})")

# skill 工具返回值的头部三行，形如：
#   # Loaded Skill: blueai-universal-crawler
#   Version: 1
#   Skill directory: /mnt/skills/blueai-universal-crawler
# 这三个都在正文前 100 字符内，不受 2000 字符截断影响。
_LOADED_SKILL = re.compile(r"^#\s*Loaded Skill:\s*(\S+)\s*$", re.M)
_SKILL_VERSION = re.compile(r"^Version:\s*(\S+)\s*$", re.M)
_SKILL_DIRECTORY = re.compile(r"^Skill directory:\s*(\S+)\s*$", re.M)
# 签名元数据是 base64 编码的 JSON，含 skillName / skillId / version / sig / alg。
# 这是唯一能直接拿到 skillId 与真实版本号的位置（头部 Version 是技能内的序号，不是包版本）。
_SKILL_SIGNATURE = re.compile(r"blueai_signature:\s*([A-Za-z0-9+/=_\-]+)")

# 工具结果正文的保留上限。事件流里单条结果可达数万字符，整条上报会撑爆单条日志上限，
# 因此截断；截断与否会写入 tool.result.truncated，下游据此判断内容是否完整。
_RESULT_LIMIT = 2000


def _ns(ts: str) -> int:
    return int(datetime.fromisoformat(ts).timestamp() * 1_000_000_000)


def _text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def _decode_skill_signature(text: str) -> dict:
    """从 skill 返回值里解出签名元数据。

    这是 MA 唯一直接给出 skillId 与真实包版本的位置。解不出就返回空 dict，
    不猜、不用别处的值顶替。
    """
    m = _SKILL_SIGNATURE.search(text)
    if not m:
        return {}
    raw = m.group(1)
    try:
        padded = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _skill_fields(text: str) -> dict:
    """从 skill 工具返回值里提取能直接对应主库 schema 的字段。

    只填能从文本里确证的值。头部三行给 skill 名与安装目录，签名给 skillId 与包版本。
    """
    out: dict[str, Any] = {}
    m = _LOADED_SKILL.search(text)
    if m:
        out["gen_ai.skill.name"] = m.group(1)
    m = _SKILL_DIRECTORY.search(text)
    if m:
        out["gen_ai.skill.path"] = m.group(1)
    sig = _decode_skill_signature(text)
    if sig:
        if isinstance(sig.get("skillId"), str) and sig["skillId"]:
            out["gen_ai.skill.id"] = sig["skillId"]
        if isinstance(sig.get("version"), str) and sig["version"]:
            # 签名里的 version 是 skills-market 的包版本，与头部 Version 的语义不同
            out["gen_ai.skill.version"] = sig["version"]
        out["bsm.skill.signature.state"] = "present"
        if isinstance(sig.get("alg"), str) and sig["alg"]:
            out["bsm.skill.signature.alg"] = sig["alg"]
    return out


def _node_fields(command: str) -> dict:
    """从 bsm-obs-run 命令行里解出 skill 身份与操作名。

    node_id 形如 <skill_id>.<base64url(脚本路径)>.<base64url(操作名)>，
    三段都是可解码的，不需要查 manifest。
    """
    m = _NODE.search(command)
    if not m:
        return {}
    parts = m.group(1).split(".")
    if len(parts) != 3:
        return {}
    out: dict[str, Any] = {"agent.ma.skill_node_id": m.group(1)}
    try:
        out["agent.ma.skill.script_path"] = base64.urlsafe_b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4)).decode("utf-8")
        out["agent.ma.skill.operation"] = base64.urlsafe_b64decode(
            parts[2] + "=" * (-len(parts[2]) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return {"agent.ma.skill_node_id": m.group(1)}
    if parts[0]:
        out.setdefault("gen_ai.skill.id", parts[0])
    return out


def convert(events: list[dict], *, session_id: str, user_id: str = "",
            model: Optional[str] = None, provider: Optional[str] = None) -> list[dict]:
    """返回按时间排序的规范记录。model/provider 事件里没有,由调用方在建 Session 时记录后传入。

    event.id 由「源事件 id + 记录名 + 同名序号」确定性派生,同一批事件重复转换结果一致,
    便于调用方按前缀跳过已上报的部分。
    """
    events = sorted(events, key=lambda e: _ns(e["processed_at"]))
    results = {e["tool_use_id"]: e for e in events if e["type"] == "agent.tool_result"}
    starts = {e["id"]: e for e in events if e["type"] == "span.model_request_start"}
    out: list[dict] = []
    turn_no, step_no, turn_id, step_id = 0, 0, "", ""
    base = {"user.id": user_id, "gen_ai.session.id": session_id}
    seq: dict[tuple[str, str], int] = {}
    seen_skill: dict[str, dict] = {}  # 调用编号 → 已产出的 skill.use 记录，供结果事件补充字段

    def rec(name: str, ts: str, *, src: str = "", **kw: Any) -> dict:
        key = (src, name)
        seq[key] = seq.get(key, 0) + 1
        rid = f"{src}:{name}" if seq[key] == 1 else f"{src}:{name}#{seq[key]}"
        r = {"time_unix_nano": str(_ns(ts)), "observed_time_unix_nano": str(_ns(ts)),
             "event.id": rid, "event.name": name, **base,
             "gen_ai.turn.id": turn_id}
        if user_id:
            # Pilot 归一化时会把 user.id 覆盖成「配置里的 userId」，未配置就是主机名，
            # 于是所有租户的记录都会变成同一个主机名。这个内部键优先级最高，
            # 且读完即删（不会落进 SLS），是保住真实用户标识的唯一入口。
            r["agent.pilot.invocation.user.id"] = user_id
        if step_id:
            r["gen_ai.step.id"] = step_id
        r.update({k: v for k, v in kw.items() if v is not None})
        return r

    for e in events:
        ty = e["type"]
        src = str(e.get("id") or "")
        if ty == "user.message":
            turn_no += 1; turn_id = f"turn-{turn_no}"; step_no = 0; step_id = ""
        elif ty == "span.model_request_start":
            step_no += 1; step_id = f"step-{step_no}"
            out.append(rec("llm.request", e["processed_at"], src=src, **{
                "gen_ai.request.model": model, "gen_ai.provider.name": provider}))
        elif ty == "span.model_request_end":
            u = e.get("model_usage") or {}
            failed = bool(e.get("is_error"))
            out.append(rec("llm.response", e["processed_at"], src=src, **{
                "gen_ai.response.model": model, "gen_ai.provider.name": provider,
                "gen_ai.usage.input_tokens": u.get("input_tokens"),
                "gen_ai.usage.output_tokens": u.get("output_tokens"),
                "gen_ai.usage.cache_read.input_tokens": u.get("cache_read_input_tokens"),
                "gen_ai.response.finish_reasons": ["error"] if failed else None,
                "error.type": "model_request_failed" if failed else None}))
        elif ty == "agent.tool_use":
            inp = e.get("input") or {}
            out.append(rec("tool.call", e["processed_at"], src=src, **{
                "gen_ai.tool.name": e.get("name"), "gen_ai.tool.call.id": e["id"],
                "gen_ai.tool.call.arguments": inp}))
            skill_fields: dict = {}
            if e.get("name") == "skill" and inp.get("name"):
                skill_fields["gen_ai.skill.name"] = inp["name"]
            # 工具名不是 skill 时，仍可能是经 bsm-obs-run 包装的技能内操作。
            # 从命令行解出 node_id 的三段，拿到 skill_id / 脚本路径 / 具体操作名。
            cmd = inp.get("command", "") if isinstance(inp, dict) else ""
            skill_fields.update(_node_fields(cmd))
            if skill_fields:
                r = rec("skill.use", e["processed_at"], src=src,
                        **{"gen_ai.tool.call.id": e["id"], **skill_fields})
                out.append(r)
                # 同一次调用稍后还会从结果里拿到更多字段，按调用编号合并进这条，
                # 而不是再产出第二条 skill.use（否则一次调用会出现重复记录）。
                seen_skill[e["id"]] = r
        elif ty == "agent.tool_result":
            use = next((x for x in events if x["id"] == e["tool_use_id"]), None)
            text = _text(e.get("content"))
            mm = _EXIT.search(text)
            code = int(mm.group(1)) if mm else None
            failed = bool(e.get("is_error")) or (code not in (None, 0))
            dur = None
            if use:
                dur = round((_ns(e["processed_at"]) - _ns(use["processed_at"])) / 1_000_000)
            # skill 工具的返回值里带 skill 名、版本、安装目录与签名元数据，
            # 都在正文前 2000 字符内，不受下面的截断影响。这些是主库要求的字段，
            # 且只有这一处能拿到（尤其是 skillId 与包版本）。
            skill_fields: dict = {}
            if (use or {}).get("name") == "skill":
                skill_fields = _skill_fields(text)
            if skill_fields:
                call_id = e["tool_use_id"]
                existing = seen_skill.get(call_id)
                if existing is not None:
                    # 合并进那次调用已产出的 skill.use，不重复产出记录
                    existing.update({k: v for k, v in skill_fields.items() if v is not None})
                else:
                    out.append(rec("skill.use", e["processed_at"], src=src,
                                   **{"gen_ai.tool.call.id": call_id, **skill_fields}))
            # 超过上限的结果会被截断。不标记的话，下游无法区分「本来就这么短」和
            # 「被截了」，会把不完整的内容当成全部内容。原长度一并留下，便于判断截了多少。
            truncated = len(text) > _RESULT_LIMIT
            out.append(rec("tool.result", e["processed_at"], src=src, **{
                "gen_ai.tool.name": (use or {}).get("name"), "gen_ai.tool.call.id": e["tool_use_id"],
                "gen_ai.tool.call.duration": dur,
                "tool.result.status": "failure" if failed else "success",
                "gen_ai.tool.call.result": text[:_RESULT_LIMIT],
                "tool.result.truncated": truncated,
                "tool.result.original_length": len(text),
                "error.type": "exit_code" if (failed and code not in (None, 0)) else ("tool_error" if failed else None),
                "error.message": f"exit_code {code}" if (failed and code not in (None, 0)) else None}))
        elif ty == "session.status_idle":
            sr = e.get("stop_reason") or {}
            # 以最后一条 llm.response 收尾:Pilot 需要 end_turn 才会导出该 turn
            for r in reversed(out):
                if r["event.name"] == "llm.response":
                    if not r.get("gen_ai.response.finish_reasons"):
                        r["gen_ai.response.finish_reasons"] = ["end_turn"] if sr.get("type") == "end_turn" else None
                    break
    return out
