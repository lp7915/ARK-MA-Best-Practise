from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

from .node import RoutingNode
from .replay import run_cases, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="PM 路由单元：离线原始中文输入、多轮反问和覆盖判断")
    sub = parser.add_subparsers(dest="command", required=True)
    route = sub.add_parser("route", help="处理一条消息；--state 保存/恢复同一需求")
    route.add_argument("--text", required=True)
    route.add_argument("--user", default="u1")
    route.add_argument("--event", default=None)
    route.add_argument("--state", type=Path)
    replay = sub.add_parser("replay", help="回放全部模拟用户对话并检查期望")
    replay.add_argument("--cases", type=Path)
    replay.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "route":
        state = json.loads(args.state.read_text(encoding="utf-8")) if args.state and args.state.exists() else None
        output = RoutingNode().handle({"event_id": args.event or "demo_event_" + uuid.uuid4().hex, "user_id": args.user, "text": args.text}, state)
        if args.state:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text(json.dumps(output["state"], ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(output["result"], ensure_ascii=False, indent=2))
        return 0
    report = run_cases(args.cases)
    if args.output:
        write_report(report, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False))
    for case in report["cases"]:
        for turn in case["turns"]:
            for failure in turn["failures"]:
                print(case["case_id"], failure)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
