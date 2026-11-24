#!/usr/bin/env python3
"""Ada PM 冒烟验收：建会话 → 发消息 → 观察回复/分派/子 Agent bash 是否真实发生。

验证目标（映射规范 10.3 的用例 1、2 的最小版）：
- 会话创建成功、BYOK 鉴权头生效（pm 能真实回复）
- pm 收到「帮我做个分析」后进入澄清（不直接分派），或触发 pm-orchestrator 路由脚本（bash）

用法：
    python3 smoke.py [--msg "帮我做个分析"] [--timeout 180]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/Users/lpll/Documents/code/ARK-MA-Best-Practise/scenarios/feishu-bot")
from arkagent.ark import ArkClient  # noqa: E402

ROOT = Path(__file__).resolve().parent


def read_env() -> dict:
    env = {}
    for line in open(os.path.expanduser("~/.arkagent/cases/analyst/config.env"), encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")
    return env


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--msg", default="帮我做个分析")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--session", default="", help="复用已有会话（跳过创建）")
    args = ap.parse_args()

    env = read_env()
    ids = json.loads((ROOT / "ma-resources" / "created_ids.json").read_text(encoding="utf-8"))

    client = ArkClient(env["ARK_API_KEY"], env.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3")

    # BYOK 请求级鉴权头：不写入 Agent，按请求携带
    hname = env.get("BYOK_MODEL_AUTH_HEADER_NAME", "")
    hval = env.get("BYOK_MODEL_AUTH_HEADER_VALUE", "")
    extra = {f"X-User-Model-Header-{hname}": hval} if hname and hval else None
    print(f"BYOK 鉴权头: X-User-Model-Header-{hname}" if extra else "BYOK 鉴权头: 未配置(可能无法回复)")

    # 会话级资源：5 个知识库，全部 read_only
    resources = [
        {"type": "memory_store", "memory_store_id": sid, "access": "read_only"}
        for _, sid in ids["memory_stores"].items()
    ]
    main_agent = ids["agents"]["pm"]["id"]
    env_id = ids["environment_id"]

    if args.session:
        session_id = args.session
        print(f"复用会话: {session_id}")
    else:
        session_id = await client.create_session(
            agent_id=main_agent,
            environment_id=env_id,
            resources=resources,
            title="topic-lab/ada-pm/smoke",
        )
        print(f"会话已创建: {session_id}")

    print(f"\n发送消息: {args.msg!r}")
    result = await client.run(
        session_id, args.msg, timeout_ms=args.timeout * 1000, extra_headers=extra
    )
    print(f"terminal: {result.terminal}")
    if result.error:
        print(f"error: {result.error}")
    if result.messages:
        print("回复:")
        for m in result.messages:
            print("  " + m.replace("\n", "\n  "))

    # 拉事件流，统计关键事件类型（分派/工具调用）
    events = await client.list_session_events(session_id, limit=500)
    types = Counter(e.get("type") for e in events)
    print("\n事件类型统计:")
    for t, c in types.most_common():
        print(f"  {t}: {c}")

    # 关键证据：子线程创建 / bash 工具调用
    threads = [e for e in events if e.get("type") == "session.thread_created"]
    tool_uses = [e for e in events if e.get("type") in ("tool_use", "agent.tool_use") or (e.get("type") or "").startswith("tool_use")]
    print(f"\n子线程创建: {len(threads)} 次")
    for t in threads:
        print("  thread_created:", json.dumps(t, ensure_ascii=False)[:200])
    print(f"工具调用(bash 等): {len(tool_uses)} 次")

    await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))