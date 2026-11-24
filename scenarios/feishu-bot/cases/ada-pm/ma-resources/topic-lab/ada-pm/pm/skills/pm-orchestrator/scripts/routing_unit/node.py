"""One PM routing node with JSON-serializable conversation state."""

from __future__ import annotations

import copy
import hashlib
import json

from .engine import AssessmentError, DecisionEngine
from .registry import Registry
from .semantic import DemoSemanticAdapter, SemanticAdapter


METHOD_CONTRACTS = {
    "audience_profile": ("demo_audience_profile", "table", "audience_profile"),
    "sentiment": ("demo_sentiment", "text_table", "sentiment_summary"),
    "deduplicate": ("demo_deduplicate", "table", "deduplicated_table"),
    "aggregate": ("demo_aggregate", "table", "aggregate_metrics"),
    "correlate": ("demo_correlate", "table", "correlation_result"),
    "causal": (None, "table", "causal_proof"),
    "forecast": (None, "table", "future_sales_prediction"),
    "offline_interview": (None, "fieldwork", "offline_interview_data"),
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class RoutingNode:
    def __init__(self, registry: Registry | None = None, semantic: SemanticAdapter | None = None, admin_user_ids: list[str] | None = None):
        self.registry = registry or Registry.load()
        self.semantic = semantic or DemoSemanticAdapter()
        self.engine = DecisionEngine(self.registry)
        self.admin_user_ids = set(admin_user_ids or ["admin"])

    def handle(self, message: dict, state: dict | None = None) -> dict:
        """Return {result, state}. Inputs are not mutated; state is plain JSON data."""
        for field in ("event_id", "user_id", "text"):
            if field not in message or not isinstance(message[field], str):
                raise ValueError(f"message.{field} 必须为字符串")
        if not message["event_id"] or not message["user_id"]:
            raise ValueError("event_id 和 user_id 不能为空")
        state = copy.deepcopy(state) if state is not None else self._new_state(message)
        event_id = message["event_id"]
        prior = state["events"].get(event_id)
        message_hash = _digest(message)
        if prior:
            if prior["message_hash"] != message_hash:
                result = self._base(state, "invalid_event")
                result["errors"] = ["同一 event_id 对应不同内容，拒绝覆盖原输入"]
                return {"result": result, "state": state}
            return {"result": copy.deepcopy(prior["result"]), "state": state}
        state["revision"] += 1
        state["messages"].append(copy.deepcopy(message))
        try:
            extraction = self.semantic.extract(message, state)
            self._validate_extraction(extraction, message)
            self._apply_extraction(state, extraction, message)
            result = self._evaluate(state)
        except AssessmentError as exc:
            result = self._base(state, "invalid_assessment")
            result["errors"] = [str(exc)]
        result["source_refs"] = [m["event_id"] for m in state["messages"]]
        result["initiator"] = state["initiator"]
        result["request_version"] = state["revision"]
        result["registry_version"] = self.registry.version
        result["rules_version"] = state["rules_version"]
        result["normalized_request"] = {"facts": copy.deepcopy(state["facts"]), "domains": copy.deepcopy(state["domains"]), "mode": copy.deepcopy(state["mode"]), "actions": copy.deepcopy(state["actions"])}
        result["plan_version"] = state["plan_version"]
        result["executions_started"] = 0
        result["can_start"] = False
        result["simulation_only"] = True
        state["last_result"] = copy.deepcopy(result)
        state["events"][event_id] = {"message_hash": message_hash, "result": copy.deepcopy(result)}
        return {"result": result, "state": state}

    @staticmethod
    def _new_state(message: dict) -> dict:
        return {"schema_version": 1, "request_id": "demo_req_" + _digest(message["event_id"])[:12], "revision": 0, "initiator": message["user_id"], "rules_version": "demo_topic_first_v1", "messages": [], "events": {}, "facts": {}, "domains": {}, "mode": None, "actions": {}, "unknown_work": [], "ambiguous_domains": [], "conflicts": [], "pending": {}, "revisions": [], "decisions": [], "plan_version": 0, "plan_fingerprint": None, "last_result": None}

    @staticmethod
    def _validate_extraction(extraction: dict, message: dict):
        if not isinstance(extraction, dict):
            raise AssessmentError("语义提取必须为结构化对象")
        source = extraction.get("source")
        if not isinstance(source, dict) or source.get("event_id") != message["event_id"]:
            raise AssessmentError("语义提取未关联当前来源")
        quote = source.get("quote")
        if not isinstance(quote, str) or quote not in message["text"]:
            raise AssessmentError("语义提取的原文证据不在消息中")
        if not isinstance(extraction.get("facts"), dict):
            raise AssessmentError("facts 必须为字段对象")
        allowed_facts = {"object", "period", "dataset", "dedup_key", "metric"}
        if set(extraction["facts"]) - allowed_facts or any(not isinstance(v, str) or not v for v in extraction["facts"].values()):
            raise AssessmentError("facts 存在未知字段或非法值")
        for key in ("domains", "actions", "unknown_work", "ambiguous_domains"):
            if not isinstance(extraction.get(key), list) or any(not isinstance(v, str) or not v for v in extraction[key]):
                raise AssessmentError(f"{key} 必须为字符串列表")
        if extraction.get("mode") not in (None, "full", "partial"):
            raise AssessmentError("未知产品范围，需澄清")
        if not isinstance(extraction.get("explicit_revision", False), bool):
            raise AssessmentError("explicit_revision 必须为布尔值")

    def _adopt(self, state: dict, field: str, old: dict | None, new: dict, explicit_revision: bool, message: dict) -> dict | None:
        active = [c for c in state["conflicts"] if c["field"] == field and c["status"] == "pending"]
        if active and message["user_id"] in self.admin_user_ids and ("采用" in message["text"] or "裁决" in message["text"]):
            for conflict in active:
                conflict["status"] = "resolved"
                conflict["resolution"] = copy.deepcopy(new)
            state["decisions"].append({"field": field, "adopted": copy.deepcopy(new), "actor": message["user_id"], "source_refs": new["source_refs"]})
            return new
        if not old:
            return new
        if old["value"] == new["value"]:
            merged = copy.deepcopy(old)
            merged["source_refs"] = list(dict.fromkeys(old["source_refs"] + new["source_refs"]))
            return merged
        if new["user_id"] != old.get("user_id", state["initiator"]):
            if not any(c["new"]["value"] == new["value"] and c["new"]["user_id"] == new["user_id"] for c in active):
                state["conflicts"].append({"field": field, "scope": "current_request", "old": copy.deepcopy(old), "new": copy.deepcopy(new), "status": "pending"})
            return old
        if explicit_revision:
            state["revisions"].append({"field": field, "old": copy.deepcopy(old), "new": copy.deepcopy(new), "source_refs": new["source_refs"]})
            state["pending"] = {}
            return new
        state["pending"] = {"field": "self_revision", "question": f"你先后给出的{field}不同，是否用 {new['value']} 替代 {old['value']}？", "candidate": {"field": field, "value": new["value"]}}
        return old

    def _apply_extraction(self, state: dict, extraction: dict, message: dict):
        actor, event = message["user_id"], message["event_id"]
        old_pending = copy.deepcopy(state.get("pending", {}))
        explicit = extraction.get("explicit_revision", False)
        if old_pending.get("field") == "self_revision" and message["text"].strip() in ("是", "确认替换", "是的", "替换"):
            candidate = old_pending.get("candidate")
            if candidate:
                if candidate["field"] in ("mode", "domains", "actions"):
                    key = {"domains": "domains", "actions": "actions", "mode": "mode"}[candidate["field"]]
                    extraction[key] = candidate["value"]
                else:
                    extraction["facts"][candidate["field"]] = candidate["value"]
                explicit = True
        for field, value in extraction["facts"].items():
            new = {"value": value, "user_id": actor, "source_refs": [event]}
            state["facts"][field] = self._adopt(state, field, state["facts"].get(field), new, explicit, message)
        if extraction.get("mode"):
            new = {"value": extraction["mode"], "user_id": actor, "source_refs": [event]}
            state["mode"] = self._adopt(state, "mode", state.get("mode"), new, explicit, message)
        if extraction["domains"]:
            old_domains = state.get("domain_record")
            proposed = list(extraction["domains"])
            if not explicit and not any(c["field"] == "domains" and c["status"] == "pending" for c in state["conflicts"]):
                proposed = list(dict.fromkeys(list(state["domains"]) + proposed))
            new = {"value": proposed, "user_id": actor, "source_refs": [event]}
            adopted = self._adopt(state, "domains", old_domains, new, explicit or bool(old_domains and set(proposed) >= set(old_domains["value"])), message)
            state["domain_record"] = adopted
            state["domains"] = {domain: list(dict.fromkeys(state["domains"].get(domain, []) + adopted["source_refs"])) for domain in adopted["value"]}
        if extraction["ambiguous_domains"]:
            state["ambiguous_domains"] = extraction["ambiguous_domains"]
        elif extraction["domains"]:
            state["ambiguous_domains"] = []
        scope_revision = explicit and bool(extraction["actions"] or extraction["domains"] or extraction.get("mode"))
        if extraction["actions"] or scope_revision:
            old_actions = state.get("action_record")
            proposed = list(extraction["actions"]) if scope_revision else list(dict.fromkeys(list(state["actions"]) + extraction["actions"]))
            new = {"value": proposed, "user_id": actor, "source_refs": [event]}
            additive = bool(old_actions and set(proposed) >= set(old_actions["value"]))
            adopted = self._adopt(state, "actions", old_actions, new, scope_revision or additive, message)
            state["action_record"] = adopted
            state["actions"] = {method: list(dict.fromkeys(state["actions"].get(method, []) + adopted["source_refs"])) for method in adopted["value"]}
        if extraction["unknown_work"]:
            state["unknown_work"] = [{"text": t, "source_refs": [event]} for t in extraction["unknown_work"]]
        elif (old_pending.get("field") == "analysis_method" and extraction["actions"]) or scope_revision:
            state["unknown_work"] = []

    def _evaluate(self, state: dict) -> dict:
        active = [c for c in state["conflicts"] if c["status"] == "pending"]
        if active:
            result = self._base(state, "needs_resolution")
            result["conflicts"] = copy.deepcopy(active)
            result["questions"] = ["同一需求的有效输入存在不同口径，请项目管理员明确采用哪一项。"]
            return result
        if state.get("pending", {}).get("field") == "self_revision":
            return self._ask(state, "self_revision", state["pending"]["question"])
        if not state["facts"].get("object"):
            return self._ask(state, "object", "你想分析或处理哪个品牌、对象或哪份数据？")
        if state["unknown_work"]:
            return self._ask(state, "analysis_method", "你提到的额外专业工作具体需要什么结果、依据什么数据和方法？目前无法确认它是否在已有能力范围内。")
        if state["ambiguous_domains"]:
            return self._ask(state, "domain", "你需要人群洞察报告，还是社媒舆情报告？如确实需要两份报告，可以回答“两个都要”。", state["ambiguous_domains"])
        if not state["domains"] and not state["actions"]:
            if (state.get("mode") or {}).get("value") == "full":
                return self._ask(state, "domain", "你需要哪一类完整报告：人群洞察还是社媒舆情？", ["audience", "social"])
            return self._ask(state, "objective", "你希望完成什么分析或处理，最终需要报告、局部结果还是一份处理后的表格？")
        if state["domains"] and state["mode"] is None:
            return self._ask(state, "mode", "你需要完整主题报告，还是只做局部分析？可以回答“完整报告”或“只要局部”。")
        state["pending"] = {}
        items = self._items(state)
        fields = {k: v["value"] for k, v in state["facts"].items()}
        result = self.engine.decide(items, fields, {m["event_id"] for m in state["messages"]})
        result["deliverables"] = items
        result.setdefault("questions", [])
        result.setdefault("routing_missing", [])
        if result["status"] == "needs_resource":
            result["questions"] = ["需要补充相关 Topic/能力注册信息或专业评估，当前不能确认覆盖范围。"]
        if result["route"]:
            fingerprint = _digest({"route": result["route"], "topics": result["topic_ids"], "g": result["g_items"], "h": result["h_gaps"], "facts": fields, "registry": self.registry.data, "rules": state["rules_version"]})
            if fingerprint != state["plan_fingerprint"]:
                state["plan_version"] += 1
                state["plan_fingerprint"] = fingerprint
            result["plan_id"] = "demo_plan_" + fingerprint[:12]
        return result

    def _items(self, state: dict) -> list[dict]:
        items = []
        for domain, refs in state["domains"].items():
            full = state["mode"]["value"] == "full"
            if full:
                matches = self.registry.topic_for_domain(domain)
                if len(matches) > 1:
                    raise AssessmentError("同一业务范围有多个 Topic 候选，需进一步澄清")
                # A missing registered card stays an explicit unresolved reference.
                resource = matches[0]["id"] if matches else f"demo_{domain}_report"
                items.append({"id": f"report_{domain}", "kind": "topic_product", "resource_id": resource, "requested_output": f"full_{domain}_report", "source_refs": list(dict.fromkeys(refs + state["mode"]["source_refs"]))})
            else:
                method = {"audience": "audience_profile", "social": "sentiment"}.get(domain, "unknown_" + domain)
                items.append(self._analysis_item(method, refs))
        for method, refs in state["actions"].items():
            items.append(self._analysis_item(method, refs))
        return items

    @staticmethod
    def _analysis_item(method: str, refs: list[str]) -> dict:
        resource, input_type, output = METHOD_CONTRACTS.get(method, ("demo_unknown_" + method, "unknown", "unknown_" + method))
        return {"id": "analysis_" + method, "kind": "analysis", "method": method, "resource_id": resource, "input_type": input_type, "requested_output": output, "source_refs": refs}

    @staticmethod
    def _base(state: dict, status: str) -> dict:
        return {"status": status, "route": None, "topic_ids": [], "g_items": [], "h_gaps": [], "questions": [], "routing_missing": [], "execution_missing": [], "decision_path": [], "resource_evidence": [], "future_stages": [], "conflicts": []}

    def _ask(self, state: dict, field: str, question: str, choices: list[str] | None = None) -> dict:
        prior_candidate = state.get("pending", {}).get("candidate")
        state["pending"] = {"field": field, "question": question, "choices": choices or []}
        if field == "self_revision" and prior_candidate:
            state["pending"]["candidate"] = prior_candidate
        result = self._base(state, "needs_clarification")
        result["routing_missing"] = [field]
        result["questions"] = [question]
        return result
