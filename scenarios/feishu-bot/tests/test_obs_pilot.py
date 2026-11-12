"""方案 B 上报：事件流转规范记录、增量去重、Pilot 输入目录落盘。

夹具按 MA 事件流的真实字段构造，不含真实业务内容。
"""
import json

import pytest

from arkagent.obs_pilot.converter import convert
from arkagent.obs_pilot.reporter import PilotReporter
from arkagent.obs_pilot import sink


def _ev(id_, type_, at, **kw):
    e = {"id": id_, "type": type_, "processed_at": at}
    e.update(kw)
    return e


EVENTS = [
    _ev("e0", "user.message", "2026-11-09T10:00:00+00:00",
        content=[{"type": "text", "text": "跑个测试"}]),
    _ev("e1", "span.model_request_start", "2026-11-09T10:00:01+00:00"),
    _ev("e2", "agent.tool_use", "2026-11-09T10:00:02+00:00", name="bash",
        input={"command": "sleep 2; exit 3"}),
    _ev("e3", "span.model_request_end", "2026-11-09T10:00:03+00:00",
        model_usage={"input_tokens": 100, "output_tokens": 20,
                     "cache_read_input_tokens": 40}, is_error=False),
    _ev("e4", "agent.tool_result", "2026-11-09T10:00:05+00:00", tool_use_id="e2",
        content=[{"type": "text", "text": "exit_code: 3"}], is_error=False),
    _ev("e5", "session.status_idle", "2026-11-09T10:00:06+00:00",
        stop_reason={"type": "end_turn"}),
]


def test_convert_records_and_failure_detection():
    recs = convert(EVENTS, session_id="sesn-x", user_id="u1")
    names = [r["event.name"] for r in recs]
    assert names == ["llm.request", "tool.call", "llm.response", "tool.result"]

    result = next(r for r in recs if r["event.name"] == "tool.result")
    # is_error 为 False，但退出码非 0，必须判为失败
    assert result["tool.result.status"] == "failure"
    assert result["error.type"] == "exit_code"
    assert result["gen_ai.tool.call.duration"] == 3000

    resp = next(r for r in recs if r["event.name"] == "llm.response")
    assert resp["gen_ai.usage.input_tokens"] == 100
    # 收尾标记要落到最后一条 llm.response 上，Pilot 才会导出该 turn
    assert resp["gen_ai.response.finish_reasons"] == ["end_turn"]


def test_convert_is_deterministic():
    """同一批事件重复转换，记录内容与 id 必须一致，增量跳过才安全。"""
    first = convert(EVENTS, session_id="sesn-x", user_id="u1")
    second = convert(EVENTS, session_id="sesn-x", user_id="u1")
    assert [r["event.id"] for r in first] == [r["event.id"] for r in second]
    assert first == second


def test_convert_marks_truncated_tool_result():
    """结果被截断时必须留下标记与原长度，下游才能判断内容完整与否。"""
    long_text = "x" * 5000
    events = [
        _ev("e0", "user.message", "2026-11-09T10:00:00+00:00"),
        _ev("e1", "span.model_request_start", "2026-11-09T10:00:01+00:00"),
        _ev("e2", "agent.tool_use", "2026-11-09T10:00:02+00:00", name="bash", input={"command": "ls"}),
        _ev("e3", "agent.tool_result", "2026-11-09T10:00:03+00:00", tool_use_id="e2",
            content=[{"type": "text", "text": long_text}], is_error=False),
    ]
    result = next(r for r in convert(events, session_id="s") if r["event.name"] == "tool.result")
    assert result["tool.result.truncated"] is True
    assert result["tool.result.original_length"] == 5000
    assert len(result["gen_ai.tool.call.result"]) == 2000

    # 短结果不能被误标为截断
    short = next(r for r in convert(EVENTS, session_id="sesn-x", user_id="u1")
                 if r["event.name"] == "tool.result")
    assert short["tool.result.truncated"] is False
    assert short["tool.result.original_length"] == len("exit_code: 3")


def test_convert_assigns_turn_and_step():
    recs = convert(EVENTS, session_id="sesn-x", user_id="u1")
    assert all(r["gen_ai.turn.id"] == "turn-1" for r in recs)
    tool_call = next(r for r in recs if r["event.name"] == "tool.call")
    assert tool_call["gen_ai.step.id"] == "step-1"


# skill 工具返回值的真实形态：头部三行 + frontmatter 里的 base64 签名
SKILL_RESULT = """# Loaded Skill: blueai-universal-crawler

Version: 1

Skill directory: /mnt/skills/blueai-universal-crawler

通用爬虫。
    1\t---
    2\tname: blueai-universal-crawler
    5\tmeta:
    6\t  blueai_signature: eyJza2lsbE5hbWUiOiJibHVlYWktdW5pdmVyc2FsLWNyYXdsZXIiLCJza2lsbElkIjoiY210OXBuMTdiMDA0NDAxa2VmYzl5cmRkayIsInZlcnNpb24iOiIwLjAuMiIsImFsZyI6IkVkRFNBIn0=
    7\t---
"""


def test_convert_extracts_skill_metadata():
    """skill 的 id 与包版本只能从返回值的签名里解出来，这是主库要求的字段。"""
    events = [
        _ev("e0", "user.message", "2026-11-09T10:00:00+00:00"),
        _ev("e1", "span.model_request_start", "2026-11-09T10:00:01+00:00"),
        _ev("e2", "agent.tool_use", "2026-11-09T10:00:02+00:00", name="skill",
            input={"name": "blueai-universal-crawler"}),
        _ev("e3", "agent.tool_result", "2026-11-09T10:00:03+00:00", tool_use_id="e2",
            content=[{"type": "text", "text": SKILL_RESULT}], is_error=False),
    ]
    uses = [r for r in convert(events, session_id="s") if r["event.name"] == "skill.use"]
    # 一次调用只产一条，入参与结果的信息合并进去，不能重复成两条
    assert len(uses) == 1
    rec = uses[0]
    assert rec["gen_ai.skill.name"] == "blueai-universal-crawler"
    assert rec["gen_ai.skill.id"] == "cmt9pn17b004401kefc9yrddk"
    assert rec["gen_ai.skill.version"] == "0.0.2"  # 来自签名，不是头部的 Version: 1
    assert rec["gen_ai.skill.path"] == "/mnt/skills/blueai-universal-crawler"
    assert rec["bsm.skill.signature.state"] == "present"
    assert rec["bsm.skill.signature.alg"] == "EdDSA"


def test_convert_decodes_node_id_from_wrapper_command():
    """经 bsm-obs-run 包装的调用要从命令行解出 skill 身份与具体操作。"""
    node = "cmt9pn17b004401kefc9yrddk.c2NyaXB0cy9ydW4uc2g.c2tpbGwtbGlzdA"
    events = [
        _ev("e0", "user.message", "2026-11-09T10:00:00+00:00"),
        _ev("e1", "span.model_request_start", "2026-11-09T10:00:01+00:00"),
        _ev("e2", "agent.tool_use", "2026-11-09T10:00:02+00:00", name="bash",
            input={"command": f"node /mnt/skills/x/.blueai-skills-market/bsm-obs-run.cjs run {node} -- x"}),
    ]
    uses = [r for r in convert(events, session_id="s") if r["event.name"] == "skill.use"]
    assert len(uses) == 1
    rec = uses[0]
    assert rec["agent.ma.skill.operation"] == "skill-list"
    assert rec["agent.ma.skill.script_path"] == "scripts/run.sh"
    assert rec["gen_ai.skill.id"] == "cmt9pn17b004401kefc9yrddk"


def test_convert_ignores_skill_markers_in_plain_bash():
    """普通 bash 命令里没有包装器调用时，不能凭空产出 skill.use。"""
    events = [
        _ev("e0", "user.message", "2026-11-09T10:00:00+00:00"),
        _ev("e1", "span.model_request_start", "2026-11-09T10:00:01+00:00"),
        _ev("e2", "agent.tool_use", "2026-11-09T10:00:02+00:00", name="bash",
            input={"command": "ls -la /tmp"}),
    ]
    assert [r for r in convert(events, session_id="s") if r["event.name"] == "skill.use"] == []


class _FakeArk:
    def __init__(self, events):
        self.events = events
        self.calls = 0

    async def list_session_events(self, session_id, limit=200):
        self.calls += 1
        return self.events


@pytest.mark.asyncio
async def test_reporter_writes_once_then_skips(tmp_path):
    ark = _FakeArk(EVENTS)
    reporter = PilotReporter()

    def write(records):
        return sink.write_records(records, data_dir=tmp_path)

    # 用临时目录，避免写到真实 Pilot 输入目录
    import arkagent.obs_pilot.reporter as mod

    original = mod.write_records
    mod.write_records = write
    try:
        first = await reporter.report(ark, "sesn-x", user_id="u1")
        second = await reporter.report(ark, "sesn-x", user_id="u1")
    finally:
        mod.write_records = original

    assert first == 4
    assert second == 0  # 同一批事件不重复上报
    files = list((tmp_path / "logs" / "claude-code").glob("claude-code-*.jsonl"))
    assert len(files) == 1
    lines = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(lines) == 4


@pytest.mark.asyncio
async def test_reporter_swallows_event_fetch_failure(tmp_path):
    class Boom:
        async def list_session_events(self, session_id, limit=200):
            raise RuntimeError("网络断了")

    reporter = PilotReporter()
    # 观测是旁路：拉取失败必须返回 0 而不是抛出，不能影响用户拿回复
    assert await reporter.report(Boom(), "sesn-x") == 0


def test_sink_creates_dir_and_skips_empty(tmp_path):
    assert sink.write_records([], data_dir=tmp_path) == 0
    assert not (tmp_path / "logs").exists()

    n = sink.write_records([{"event.name": "llm.request"}], data_dir=tmp_path)
    assert n == 1
    files = list((tmp_path / "logs" / "claude-code").glob("*.jsonl"))
    assert files[0].name.startswith("claude-code-")
    assert files[0].name.endswith(".jsonl")
