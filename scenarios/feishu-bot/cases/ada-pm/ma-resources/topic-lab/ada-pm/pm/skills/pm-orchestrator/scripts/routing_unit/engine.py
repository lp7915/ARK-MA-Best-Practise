"""Deterministic product/contract coverage routing; no text classification here."""

from __future__ import annotations

from .registry import Registry


class AssessmentError(ValueError):
    pass


class DecisionEngine:
    def __init__(self, registry: Registry):
        self.registry = registry

    def decide(self, items: list[dict], fields: dict, source_ids: set[str]) -> dict:
        if not isinstance(items, list) or not items:
            raise AssessmentError("必须至少有一个具备来源的明确交付项")
        path = []
        topics = []
        covered = set()
        missing = set()
        evidence = []
        for item in items:
            if not item.get("source_refs") or not set(item["source_refs"]) <= source_ids:
                raise AssessmentError(f"交付项 {item.get('id')} 缺少有效消息来源")
            if not item.get("requested_output"):
                raise AssessmentError("交付项缺少明确产出要求")
            if item.get("kind") not in ("topic_product", "analysis"):
                raise AssessmentError("未知交付项类型")
        reports = [i for i in items if i["kind"] == "topic_product"]
        path.append({"node": "contains_complete_topic", "answer": bool(reports)})
        for item in reports:
            topic = self.registry.topics.get(item.get("resource_id"))
            if not topic or not topic.get("enabled"):
                return self._resource_error(item, path, "Topic 卡缺失或未启用，不能据此判断能力外")
            if item["requested_output"] != topic["product"]:
                raise AssessmentError("报告请求与 Topic 完整产品契约不符")
            topics.append(topic["id"])
            covered.update(topic["outputs"])
            evidence.append(self.registry.evidence(topic))
            missing.update(k for k in topic["required_execution_fields"] if not fields.get(k))
        remainder = [i for i in items if i["kind"] == "analysis" and i["requested_output"] not in covered]
        if reports:
            path.append({"node": "topics_cover_all_deliverables", "answer": not remainder})
        g_items = []
        h_gaps = []
        unknowns = []
        for item in remainder:
            method = item.get("method")
            if method in self.registry.unsupported_methods:
                h_gaps.append({"item_id": item["id"], "method": method, "reason": self.registry.unsupported_methods[method]})
                evidence.append(f"{self.registry.version}/unsupported_methods/{method}")
                continue
            capability = self.registry.capabilities.get(item.get("resource_id"))
            if not capability or not capability.get("enabled"):
                unknowns.append({"item_id": item["id"], "reason": "缺少有效能力卡，尚不能判断支持范围"})
                continue
            if capability["method"] != method or item.get("input_type") != capability["input_type"]:
                raise AssessmentError("分析要求与能力方法/输入契约不一致")
            if item["requested_output"] not in capability["outputs"]:
                raise AssessmentError("能力输出契约不能支撑请求产出")
            evidence.append(self.registry.evidence(capability))
            g_items.append({"item_id": item["id"], "capability_id": capability["id"], "requested_output": item["requested_output"]})
            missing.update(k for k in capability["required_execution_fields"] if not fields.get(k))
            if not capability.get("available", True):
                missing.add(f"capability_available:{capability['id']}")
        if remainder:
            path.append({"node": "remaining_atomic_coverage" if reports else "whole_request_atomic_coverage", "answer": None if unknowns else not bool(h_gaps)})
        if unknowns:
            return {"status": "needs_resource", "route": None, "topic_ids": list(dict.fromkeys(topics)), "g_items": g_items, "h_gaps": h_gaps, "unknowns": unknowns, "decision_path": path, "resource_evidence": evidence, "execution_missing": sorted(missing), "future_stages": []}
        if h_gaps:
            route = "h"
            stages = [{"role": "h", "gate": "human_acceptance_and_scope_required"}]
        else:
            route = "t+g" if reports and remainder else "t" if reports else "g"
            production = (["t"] if reports else []) + (["g"] if g_items else [])
            stages = [{"role": role, "gate": "requester_confirmation_and_execution_inputs"} for role in production]
            stages.append({"role": "s", "gate": "all_required_t_g_results_ready"})
        return {"status": "needs_human" if h_gaps else "ready_for_confirmation", "route": route, "topic_ids": list(dict.fromkeys(topics)), "g_items": g_items, "h_gaps": h_gaps, "unknowns": [], "decision_path": path, "resource_evidence": evidence, "execution_missing": sorted(missing), "future_stages": stages}

    @staticmethod
    def _resource_error(item: dict, path: list, reason: str) -> dict:
        return {"status": "needs_resource", "route": None, "topic_ids": [], "g_items": [], "h_gaps": [], "unknowns": [{"item_id": item["id"], "reason": reason}], "decision_path": path, "resource_evidence": [], "execution_missing": [], "future_stages": []}
