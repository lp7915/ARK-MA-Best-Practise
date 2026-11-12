"""Ada PM 端到端复验：自动推进 需求→采用样本→(匹配确认指令)→执行，重点看 s 是否完成。"""
import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/Users/lpll/Documents/code/ARK-MA-Best-Practise/scenarios/feishu-bot")
from arkagent.ark import ArkClient  # noqa: E402

ROOT = Path(__file__).resolve().parent

ROUND1 = "分析合成品牌消费者的评论，2026-10 期间，做完整社媒 Topic 报告"
ROUND2 = "使用内置样本，关注评论内容、情绪和地区差异，在当前对话交付"


def read_env() -> dict:
    env = {}
    for line in open(os.path.expanduser("~/.arkagent/cases/analyst/config.env"), encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")
    return env


async def main() -> int:
    env = read_env()
    ids = json.loads((ROOT / "ma-resources" / "created_ids.json").read_text(encoding="utf-8"))
    client = ArkClient(env["ARK_API_KEY"], env.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3")

    hname = env.get("BYOK_MODEL_AUTH_HEADER_NAME", "")
    hval = env.get("BYOK_MODEL_AUTH_HEADER_VALUE", "")
    extra = {f"X-User-Model-Header-{hname}": hval} if hname and hval else None

    resources = [{"type": "memory_store", "memory_store_id": sid, "access": "read_only"}
                 for _, sid in ids["memory_stores"].items()]
    session_id = await client.create_session(agent_id=ids["agents"]["pm"]["id"],
                                             environment_id=ids["environment_id"],
                                             resources=resources, title="topic-lab/ada-pm/e2e2")
    print(f"会话: {session_id}\n")

    msgs = [ROUND1, ROUND2]
    for i, msg in enumerate(msgs, 1):
        print(f"===== 第 {i} 轮: {msg!r} =====")
        result = await client.run(session_id, msg, timeout_ms=300000, extra_headers=extra)
        reply = "\n".join(result.messages)
        print(f"terminal={result.terminal}" + (f" error={result.error}" if result.error else ""))
        print("回复:")
        print("  " + reply.replace("\n", "\n  "))
        print()
        if i == 2:
            m = re.search(r"确认\s*(V\d+)\s*，?\s*开始执行", reply)
            if not m:
                print("!! 第二轮未匹配到「确认 Vx 开始执行」，改用「确认执行」尝试")
                confirm = "确认执行"
            else:
                confirm = f"确认 {m.group(1)}，开始执行"
            print(f"----- 第 3 轮（自动提取确认指令）: {confirm!r} -----")
            result = await client.run(session_id, confirm, timeout_ms=900000, extra_headers=extra)
            reply3 = "\n".join(result.messages)
            print(f"terminal={result.terminal}" + (f" error={result.error}" if result.error else ""))
            print("回复:")
            print("  " + reply3.replace("\n", "\n  "))

    events = await client.list_session_events(session_id, limit=3000)
    types = Counter(e.get("type") for e in events)
    threads = [e for e in events if e.get("type") == "session.thread_created"]
    sub_agents = sorted({t.get("agent_name") for t in threads})
    # s 是否 complete / 入口登记是否通过
    s_ok = any("integrated.md" in json.dumps(e, ensure_ascii=False) or "交付索引" in json.dumps(e, ensure_ascii=False) and "阻塞" not in json.dumps(e, ensure_ascii=False) for e in events)
    blocker = any("入口阻塞" in json.dumps(e, ensure_ascii=False) or "对象与Context不一致" in json.dumps(e, ensure_ascii=False) for e in events)
    print(f"\n===== 最终事件 =====")
    print(f"子线程 {len(threads)} 个: {sub_agents}")
    print(f"s 入口阻塞信号: {blocker}")
    print(f"事件类型 TOP: {types.most_common(8)}")

    await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))