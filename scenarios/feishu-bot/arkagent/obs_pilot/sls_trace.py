"""MA 事件流 / Pilot 事件记录 → 主库 logstore-tracing 的 span 结构。

对齐目标（`logstore-tracing` 实测 20 个顶层字段 + attributes + resources）：

    traceId / spanId / parentSpanId / kind / spanName
    startTime / endTime / duration / statusCode / statusMessage
    traceState / links / event / events / attributes / resources
    serviceName / hostname / pid / ip

层级：ENTRY(enter) → AGENT(invoke_agent) → STEP(react step) → {LLM(chat), TOOL(execute_tool)}

取数原则（严格）：**只搬运源数据里真实存在的值**。
  - 允许「算术」推导：duration = endTime - startTime；step 的起止取子节点的最小/最大时间。
  - 允许「计数」推导：轮次号、轮内第几轮 react。
  - 需要猜测语义的一律留空：模型名、system_instructions、tool.definitions、
    response.id、首 token 时长、process id 等源里没有的字段，值为空串，不做编造。
  - 标识符（traceId/spanId）由「源标识 + 结构位置」哈希派生，稳定可复现，不是随机数。

为什么标识符要自己生成：源数据里没有任何 trace/span 编号（MA 侧的 trace 能力尚未上线），
而目标 schema 要求 32/16 位 hex。用确定性哈希而非随机值，保证同一份源数据重复转换
得到同一套编号，重复上报不会产生无法对应的新节点。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

ROOT_PARENT = "0000000000000001"
SCOPE_NAME = "arkagent.obs_pilot"
# 我们不是用 OTel SDK 发出去的，sdk 版本等字段留空，不编造。
_SCOPE_VERSION = ""
_RESULT_LIMIT = 2000

_EXIT = re.compile(r"exit_code:\s*(-?\d+)")

# 各 span.kind 在目标 schema 里必须存在的 attributes（缺值也要留键，值为空串）。
_REQUIRED_ATTRS: dict[str, tuple[str, ...]] = {
    "ENTRY": ("gen_ai.operation.name", "gen_ai.session.id", "gen_ai.turn.id",
              "gen_ai.agent.name", "gen_ai.input.messages", "gen_ai.output.messages"),
    "AGENT": ("gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.request.model",
              "gen_ai.response.model", "gen_ai.system_instructions",
              "gen_ai.input.messages", "gen_ai.tool.definitions"),
    "STEP": ("gen_ai.operation.name", "gen_ai.react.round", "gen_ai.react.finish_reason"),
    "LLM": ("gen_ai.operation.name", "gen_ai.request.model", "gen_ai.response.model",
            "gen_ai.provider.name", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
            "gen_ai.usage.total_tokens", "gen_ai.response.finish_reasons",
            "gen_ai.response.id", "gen_ai.input.messages", "gen_ai.output.messages"),
    "TOOL": ("gen_ai.operation.name", "gen_ai.tool.name", "gen_ai.tool.call.id",
             "gen_ai.tool.type", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result"),
}

# span.kind → 顶层 kind 与 call.kind / call.type，取自目标库实测取值。
_KIND = {
    "ENTRY": ("2", "server", "server"),
    "AGENT": ("3", "client", "client"),
    "STEP": ("1", "internal", "local"),
    "LLM": ("3", "client", "client"),
    "TOOL": ("1", "internal", "local"),
}


def _ns(ts: str) -> int:
    return int(datetime.fromisoformat(ts).timestamp() * 1_000_000_000)


def _text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def _hex(seed: str, width: int) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:width]


@dataclass
class _Turn:
    """一个轮次内可观测到的全部动作。字段缺省即「源头没有」，不是「没解析出来」。"""
    turn_id: str
    order: int
    start_ns: int = 0
    end_ns: int = 0
    agent_name: str = ""
    user_text: str = ""
    reply_text: str = ""
    stop_reason: str = ""
    llms: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)

    def touch(self, start: int, end: int) -> None:
        self.start_ns = start if not self.start_ns else min(self.start_ns, start)
        self.end_ns = max(self.end_ns, end)


# --------------------------------------------------------------------------
# 源一：MA 事件流（方案 B 的取数口）
# --------------------------------------------------------------------------

def turns_from_ma_events(events: list[dict]) -> list[_Turn]:
    events = sorted(events, key=lambda e: _ns(e["processed_at"]))
    starts = {e["id"]: _ns(e["processed_at"]) for e in events
              if e["type"] == "span.model_request_start"}
    uses = {e["id"]: e for e in events if e["type"] == "agent.tool_use"}

    turns: list[_Turn] = []
    current: Optional[_Turn] = None

    def open_turn(ts: int) -> _Turn:
        t = _Turn(turn_id=f"turn-{len(turns) + 1}", order=len(turns) + 1, start_ns=ts)
        turns.append(t)
        return t

    for e in events:
        ty = e["type"]
        ts = _ns(e["processed_at"])
        if ty == "user.message":
            if current is not None:
                current.end_ns = max(current.end_ns, ts)
            current = open_turn(ts)
            current.user_text = _text(e.get("content"))
        elif ty == "span.model_request_end":
            if current is None:
                current = open_turn(starts.get(e.get("model_request_start_id"), ts))
            begin = starts.get(e.get("model_request_start_id"), ts)
            u = e.get("model_usage") or {}
            current.llms.append({
                "start": begin, "end": ts, "error": bool(e.get("is_error")),
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "cache_read": u.get("cache_read_input_tokens"),
                "cache_creation": u.get("cache_creation_input_tokens"),
            })
            current.touch(begin, ts)
        elif ty == "agent.tool_result":
            if current is None:
                current = open_turn(ts)
            use = uses.get(e.get("tool_use_id"))
            begin = _ns(use["processed_at"]) if use else ts
            text = _text(e.get("content"))
            mm = _EXIT.search(text)
            code = int(mm.group(1)) if mm else None
            failed = bool(e.get("is_error")) or code not in (None, 0)
            current.tools.append({
                "start": begin, "end": ts, "call_id": e.get("tool_use_id") or "",
                "name": (use or {}).get("name") or "",
                "arguments": (use or {}).get("input"),
                "result": text, "failed": failed, "exit_code": code,
            })
            current.touch(begin, ts)
        elif ty == "agent.message":
            if current is not None:
                current.reply_text = _text(e.get("content"))
        elif ty in ("session.thread_status_idle", "session.status_idle"):
            if current is not None:
                sr = e.get("stop_reason") or {}
                if sr.get("type"):
                    current.stop_reason = sr["type"]
                current.end_ns = max(current.end_ns, ts)
            if e.get("agent_name") and current is not None:
                current.agent_name = e["agent_name"]
    return turns


# --------------------------------------------------------------------------
# 源二：Pilot 事件记录（方案 A 的 SLS store 里就是这种形态）
# --------------------------------------------------------------------------

def turns_from_pilot_records(records: list[dict]) -> list[_Turn]:
    def num(rec: dict) -> int:
        m = re.search(r"(\d+)$", str(rec.get("gen_ai.turn.id") or ""))
        return int(m.group(1)) if m else 1

    ordered = sorted(records, key=lambda r: int(r.get("time_unix_nano") or 0))
    buckets: dict[int, _Turn] = {}
    for rec in ordered:
        n = num(rec)
        t = buckets.get(n)
        if t is None:
            t = buckets[n] = _Turn(turn_id=str(rec.get("gen_ai.turn.id") or f"turn-{n}"),
                                   order=n, start_ns=int(rec.get("time_unix_nano") or 0))
        ty = rec.get("event.name")
        ts = int(rec.get("time_unix_nano") or 0)
        if ty == "llm.request":
            t.llms.append({"start": ts, "end": 0, "error": False, "step": rec.get("gen_ai.step.id")})
        elif ty == "llm.response":
            step = rec.get("gen_ai.step.id")
            target = next((x for x in t.llms if x.get("step") == step and not x["end"]), None)
            if target is None:
                target = {"start": ts, "error": False, "step": step}
                t.llms.append(target)
            target["end"] = ts
            target["error"] = bool(rec.get("error.type"))
            target["input_tokens"] = _int(rec.get("gen_ai.usage.input_tokens"))
            target["output_tokens"] = _int(rec.get("gen_ai.usage.output_tokens"))
            target["cache_read"] = _int(rec.get("gen_ai.usage.cache_read.input_tokens"))
            target["cache_creation"] = None  # 事件记录里没有映射这个字段
            fr = rec.get("gen_ai.response.finish_reasons")
            if fr:
                try:
                    vals = json.loads(fr) if isinstance(fr, str) else fr
                except (ValueError, TypeError):
                    vals = None
                if isinstance(vals, list) and vals:
                    t.stop_reason = str(vals[0])
        elif ty == "tool.call":
            t.tools.append({"start": ts, "end": 0, "call_id": rec.get("gen_ai.tool.call.id") or "",
                            "name": rec.get("gen_ai.tool.name") or "",
                            "arguments": rec.get("gen_ai.tool.call.arguments"),
                            "result": "", "failed": False, "exit_code": None})
        elif ty == "tool.result":
            cid = rec.get("gen_ai.tool.call.id")
            target = next((x for x in t.tools if x["call_id"] == cid), None)
            if target is None:
                target = {"start": ts, "call_id": cid or "", "name": rec.get("gen_ai.tool.name") or "",
                          "arguments": None}
                t.tools.append(target)
            target["end"] = ts
            target["result"] = rec.get("gen_ai.tool.call.result") or ""
            target["failed"] = str(rec.get("tool.result.status") or "") == "failure"
        if ts:
            t.touch(ts, ts)
    for t in buckets.values():
        for x in t.llms:
            x["end"] = x["end"] or x["start"]
        for x in t.tools:
            x["end"] = x["end"] or x["start"]
        t.start_ns = min([t.start_ns] + [x["start"] for x in t.llms + t.tools])
        t.end_ns = max([t.end_ns] + [x["end"] for x in t.llms + t.tools])
    return [buckets[k] for k in sorted(buckets)]


def _int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# 共同：轮次 → span
# --------------------------------------------------------------------------

def _span(*, trace_id: str, span_id: str, parent: str, kind: str, span_name: str,
          start_ns: int, end_ns: int, status: int, attrs: dict, meta: dict) -> dict:
    """拼一条符合目标 schema 的记录。缺值的必填属性留空串，不做填充。"""
    kind_field, call_kind, call_type = _KIND[kind]
    a = {k: "" for k in _REQUIRED_ATTRS[kind]}
    a.update({
        "gen_ai.span.kind": kind,
        "otel.scope.name": SCOPE_NAME,
        # 不是经 OTel SDK 上报，SDK 版本无从得知，留空而非编造
        "otel.scope.version": _SCOPE_VERSION,
        # 目标库中 rpc 与 spanName 恒等（ENTRY/STEP/TOOL 有，LLM/AGENT 没有），照此对齐
        "rpc": span_name if kind in ("ENTRY", "STEP", "TOOL") else "",
        "call.kind": call_kind,
        "call.type": call_type,
        "ali.trace.flag": "x-trace",
    })
    a.update({k: v for k, v in attrs.items() if v not in (None, "")})
    # 空串占位的键也要保留，保证「字段存在」与「没有值」可区分
    for k in _REQUIRED_ATTRS[kind]:
        a.setdefault(k, "")

    resources = {
        "service.name": meta["service_name"],
        "host.name": meta.get("hostname") or "",
        "gen_ai.agent.type": meta.get("agent_type") or "",
        "gen_ai.framework": meta.get("framework") or "",
    }
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent,
        "kind": kind_field,
        "spanName": span_name,
        "startTime": start_ns,
        "endTime": end_ns,
        "duration": end_ns - start_ns,
        "statusCode": status,
        "statusMessage": "",
        "traceState": "",
        "links": "",
        "event": "",
        "events": "",
        "attributes": json.dumps(a, ensure_ascii=False, separators=(",", ":")),
        "resources": json.dumps(resources, ensure_ascii=False, separators=(",", ":")),
        "serviceName": meta["service_name"],
        "hostname": meta.get("hostname") or "",
        # 没有进程信息，pid 留空（目标 schema 的 ibdst@hex 是主库自己的格式，不能伪造）
        "pid": "",
        "ip": "",
    }


def build_spans(turns: Iterable[_Turn], *, session_id: str, user_id: str, meta: dict) -> list[dict]:
    """把轮次展开成 ENTRY → AGENT → STEP → {LLM, TOOL} 的记录列表。"""
    out: list[dict] = []
    for t in turns:
        if not (t.llms or t.tools):
            continue  # 没有任何可观测动作的轮次不产生节点，避免空壳 span
        trace_id = _hex(f"{session_id}|{t.turn_id}", 32)
        entry_id = _hex(f"{session_id}|{t.turn_id}|entry", 16)
        agent_id = _hex(f"{session_id}|{t.turn_id}|agent", 16)

        # STEP 划分：每次模型请求开启一轮 react；其后的工具调用归入该轮。
        rounds: list[dict] = []
        for llm in t.llms:
            rounds.append({"llm": llm, "tools": [], "start": llm["start"], "end": llm["end"]})
        if not rounds:
            rounds.append({"llm": None, "tools": [], "start": 0, "end": 0})
        # 没有模型请求时（方案 A 只有工具层），所有工具落在唯一一轮
        for tool in t.tools:
            target = next((r for r in reversed(rounds) if r["start"] <= tool["start"]), rounds[0])
            target["tools"].append(tool)
            target["start"] = min(target["start"] or tool["start"], tool["start"])
            target["end"] = max(target["end"], tool["end"])

        any_fail = any(x["failed"] for x in t.tools) or any(x["error"] for x in t.llms)
        entry_start = t.start_ns or min(r["start"] for r in rounds)
        entry_end = t.end_ns or max(r["end"] for r in rounds)

        input_messages = json.dumps([{"role": "user", "content": t.user_text}],
                                    ensure_ascii=False) if t.user_text else ""
        output_messages = json.dumps([{"role": "assistant", "content": t.reply_text}],
                                     ensure_ascii=False) if t.reply_text else ""
        common = {
            "gen_ai.session.id": session_id,
            # 目标库中 conversation.id 与 session.id 恒等，照此对齐
            "gen_ai.conversation.id": session_id,
            "gen_ai.turn.id": t.turn_id,
            "gen_ai.user.id": user_id,
            "gen_ai.agent.name": t.agent_name,
        }

        out.append(_span(trace_id=trace_id, span_id=entry_id, parent=ROOT_PARENT, kind="ENTRY",
                         span_name="enter_ai_application_system", start_ns=entry_start,
                         end_ns=entry_end, status=2 if any_fail else 0,
                         attrs={**common, "gen_ai.operation.name": "enter",
                                "gen_ai.input.messages": input_messages,
                                "gen_ai.output.messages": output_messages},
                         meta=meta))
        out.append(_span(trace_id=trace_id, span_id=agent_id, parent=entry_id, kind="AGENT",
                         span_name=f"invoke_agent {t.agent_name}".strip(), start_ns=entry_start,
                         end_ns=entry_end, status=2 if any_fail else 0,
                         attrs={**common, "gen_ai.operation.name": "invoke_agent",
                                "gen_ai.input.messages": input_messages},
                         meta=meta))

        for idx, rnd in enumerate(rounds, start=1):
            r_start = rnd["start"] or entry_start
            r_end = max([rnd["end"] or r_start] + [x["end"] for x in rnd["tools"]])
            step_id = _hex(f"{session_id}|{t.turn_id}|step|{idx}", 16)
            # finish_reason 只在最后一步、且源头确实给出了 stop_reason 时填
            finish = t.stop_reason if (idx == len(rounds) and t.stop_reason) else ""
            round_fail = any(x["failed"] for x in rnd["tools"]) or bool(
                rnd["llm"] and rnd["llm"].get("error"))
            out.append(_span(trace_id=trace_id, span_id=step_id, parent=agent_id, kind="STEP",
                             span_name="react step", start_ns=r_start, end_ns=r_end,
                             status=2 if round_fail else 0,
                             attrs={**common, "gen_ai.operation.name": "react",
                                    "gen_ai.react.round": str(idx),
                                    "gen_ai.react.finish_reason": finish},
                             meta=meta))

            llm = rnd["llm"]
            if llm:
                usage = {
                    "gen_ai.usage.input_tokens": _s(llm.get("input_tokens")),
                    "gen_ai.usage.output_tokens": _s(llm.get("output_tokens")),
                    "gen_ai.usage.cache_read.input_tokens": _s(llm.get("cache_read")),
                    "gen_ai.usage.cache_creation.input_tokens": _s(llm.get("cache_creation")),
                }
                out.append(_span(
                    trace_id=trace_id, span_id=_hex(f"{session_id}|{t.turn_id}|llm|{idx}", 16),
                    parent=step_id, kind="LLM",
                    # 模型名源头没有，spanName 只保留操作名，不编造 target
                    span_name="chat",
                    start_ns=llm["start"], end_ns=llm["end"],
                    status=2 if llm.get("error") else 0,
                    attrs={**common, "gen_ai.operation.name": "chat", **usage,
                           "gen_ai.response.finish_reasons":
                               "error" if llm.get("error") else t.stop_reason},
                    meta=meta))
            for j, tool in enumerate(rnd["tools"], start=1):
                result = tool.get("result") or ""
                out.append(_span(
                    trace_id=trace_id,
                    span_id=_hex(f"{session_id}|{t.turn_id}|tool|{idx}|{tool['call_id'] or j}", 16),
                    parent=step_id, kind="TOOL",
                    span_name=f"execute_tool {tool['name']}".strip(),
                    start_ns=tool["start"], end_ns=tool["end"],
                    status=2 if tool["failed"] else 0,
                    attrs={**common, "gen_ai.operation.name": "execute_tool",
                           "gen_ai.tool.name": tool["name"],
                           "gen_ai.tool.call.id": tool["call_id"],
                           "gen_ai.tool.type": "function",
                           "gen_ai.tool.call.arguments": _args(tool.get("arguments")),
                           "gen_ai.tool.call.result": result[:_RESULT_LIMIT],
                           "tool.result.status": "failure" if tool["failed"] else "success"},
                    meta=meta))
    return out


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _args(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def to_log_items(spans: Iterable[dict]) -> list[dict]:
    """转成 SLS 写入需要的字符串字典，时间戳取 startTime 的纳秒值。"""
    items = []
    for s in spans:
        contents = {k: ("" if v is None else str(v)) for k, v in s.items()}
        items.append({"contents": contents, "time": int(s["startTime"]) // 1_000_000_000})
    return items
