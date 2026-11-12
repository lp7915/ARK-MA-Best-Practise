"""Replay Chinese conversations and independently check business expectations."""

from __future__ import annotations

import json
from pathlib import Path

from .node import RoutingNode


def check_expected(result: dict, expected: dict) -> list[str]:
    failures = []
    for key, value in expected.items():
        if key == "question_contains":
            actual = "\n".join(result.get("questions", []))
            ok = value in actual
        elif key in ("topic_count", "g_count", "conflict_count"):
            target = {"topic_count": "topic_ids", "g_count": "g_items", "conflict_count": "conflicts"}[key]
            actual = len(result.get(target, []))
            ok = actual == value
        elif key == "missing_execution":
            actual = result.get("execution_missing", [])
            ok = set(value) <= set(actual)
        elif key == "period":
            actual = result.get("normalized_request", {}).get("facts", {}).get("period", {}).get("value")
            ok = actual == value
        elif key == "revision":
            actual = result.get("request_version")
            ok = actual == value
        else:
            actual = result.get(key)
            ok = actual == value
        if not ok:
            failures.append(f"{key}: expected={value!r}, actual={actual!r}")
    if result.get("can_start") is not False or result.get("executions_started") != 0:
        failures.append("路由节点不得启动真实生产")
    stages = result.get("future_stages", [])
    if result.get("route") in ("t", "g", "t+g"):
        if not stages or stages[-1].get("role") != "s" or any(s.get("role") == "s" for s in stages[:-1]):
            failures.append("s 必须仅列在所有生产角色之后")
    return failures


def run_cases(path: str | Path | None = None, node_factory=RoutingNode) -> dict:
    path = Path(path) if path else Path(__file__).with_name("cases.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("simulation_only") is not True:
        raise ValueError("回放输入必须明确 simulation_only=true")
    cases = []
    for fixture in data["cases"]:
        node, state = node_factory(), None
        turns = []
        for turn in fixture["turns"]:
            # A JSON round trip verifies that next-turn behavior does not depend
            # on in-memory objects or process-local sessions.
            state = json.loads(json.dumps(state, ensure_ascii=False)) if state else None
            output = node.handle(turn["input"], state)
            state, result = output["state"], output["result"]
            failures = check_expected(result, turn["expected"])
            turns.append({"input": turn["input"], "expected": turn["expected"], "result": result, "failures": failures})
        cases.append({"case_id": fixture["case_id"], "description": fixture["description"], "passed": all(not t["failures"] for t in turns), "turns": turns})
    return {"simulation_only": True, "total": len(cases), "passed": sum(c["passed"] for c in cases), "failed": sum(not c["passed"] for c in cases), "turn_count": sum(len(c["turns"]) for c in cases), "cases": cases}


def write_report(report: dict, output_dir: str | Path):
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "对话回放报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 路由节点模拟对话回放", "", f"模拟案例：{report['total']}；通过：{report['passed']}；失败：{report['failed']}；输入轮数：{report['turn_count']}。", "", "全部为演示注册表与离线语义适配器的本地回放，没有执行真实分析或发送飞书消息。", ""]
    for case in report["cases"]:
        lines.extend([f"## {case['case_id']} {'PASS' if case['passed'] else 'FAIL'}：{case['description']}", ""])
        for index, turn in enumerate(case["turns"], 1):
            msg, result = turn["input"], turn["result"]
            lines.extend([f"**第 {index} 轮用户（{msg['user_id']}）**：{msg['text'] or '〈空输入〉'}", "", f"节点结果：`{result['status']}`；路由：`{result.get('route') or '未确定'}`；方案版本：{result.get('plan_version', 0)}。", ""])
            for question in result.get("questions", []):
                lines.extend([f"**PM 反问/提示**：{question}", ""])
            if result.get("execution_missing"):
                lines.extend(["执行前待补：" + "、".join(result["execution_missing"]) + "。", ""])
            if result.get("decision_path"):
                lines.extend(["判断路径：" + " → ".join(f"{n['node']}={n['answer']}" for n in result["decision_path"]), ""])
            for error in turn["failures"]:
                lines.extend(["断言失败：" + error, ""])
    (dest / "对话回放报告.md").write_text("\n".join(lines), encoding="utf-8")
