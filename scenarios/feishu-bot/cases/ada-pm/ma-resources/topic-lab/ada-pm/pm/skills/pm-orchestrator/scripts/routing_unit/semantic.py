"""Replaceable semantic boundary with a deliberately limited offline Chinese adapter.

It extracts domain, requested product, method and evidence, not a final route.
Unrecognized professional work is preserved and asks for clarification.
"""

from __future__ import annotations

import re
from typing import Protocol


class SemanticAdapter(Protocol):
    def extract(self, message: dict, state: dict) -> dict:
        """Return facts/domains/mode/actions/unknown_work with source quotes."""
        ...


class DemoSemanticAdapter:
    DOMAIN_PATTERNS = {
        "audience": r"人群洞察|消费者|人群画像|用户画像|人群特征",
        "social": r"社媒|舆情|社交媒体|评论情感|情绪分布",
    }
    ACTION_PATTERNS = {
        "deduplicate": r"去重|移除重复|删除重复",
        "aggregate": r"计算|统计|汇总销量|平均销量|额外指标|求平均",
        "correlate": r"相关性|相关分析",
        "causal": r"证明.{0,8}因果|因果证明|因果结论|因果关系|因果推断",
        "forecast": r"预测|未来销量",
        "offline_interview": r"线下访谈|入户访谈|上门访谈",
    }

    def extract(self, message: dict, state: dict) -> dict:
        raw = message["text"].strip()
        # The explicit requested positive scope is kept after a negative clause.
        text = re.sub(r"(?:不要|不需要|不用|不做|不是|无需|不预测|不再预测)[^，,。；;]*(?:[，,。；;]|$)", "", raw)
        out = {
            "facts": {}, "domains": [], "mode": None, "actions": [],
            "unknown_work": [], "ambiguous_domains": [],
            "explicit_revision": bool(re.search(r"改为|改成|更正|写错|纠正|以.{0,12}为准|不是.*而是", raw)),
            "source": {"event_id": message["event_id"], "quote": raw},
        }
        facts = out["facts"]
        obj = re.search(r"(?:对象|品牌)[：:]\s*([^，,。；;\n]+)", raw)
        if obj:
            facts["object"] = obj.group(1).strip()
        else:
            obj = re.search(r"([甲乙丙丁戊己A-Z][A-Za-z0-9一二三四五六七八九十]*品牌)", raw)
            if obj:
                facts["object"] = obj.group(1)
        period = re.search(r"(20\d{2})[年\-/](\d{1,2})(?:月)?", raw)
        if period and 1 <= int(period.group(2)) <= 12:
            facts["period"] = f"{period.group(1)}-{int(period.group(2)):02d}"
        elif re.search(r"9月|九月|10月|十月", raw):
            # No invented year; preserve the user supplied business period.
            facts["period"] = "10月" if re.search(r"10月|十月", raw) else "9月"
        if re.search(r"(?:这份|这张|已有|现有|上传|已上传|给定).{0,12}(?:表|名单|数据|明细)", text) or message.get("attachments"):
            facts["dataset"] = "provided_reference"
            if "object" not in facts and not state.get("facts", {}).get("object"):
                facts["object"] = "用户提供的数据"
        key = re.search(r"按([^，,。；;]{1,16}?)(?:字段)?去重", text)
        if key:
            facts["dedup_key"] = key.group(1)
        if re.search(r"平均|均值", text):
            facts["metric"] = "mean"
        elif re.search(r"求和|合计|总销量", text):
            facts["metric"] = "sum"

        for domain, pattern in self.DOMAIN_PATTERNS.items():
            if re.search(pattern, text):
                out["domains"].append(domain)
        for method, pattern in self.ACTION_PATTERNS.items():
            if re.search(pattern, text):
                out["actions"].append(method)

        partial = bool(re.search(r"局部|只(?:要|需要|做).{0,14}(?:画像|指标|表格|名单|情绪分布)|仅需.{0,14}(?:画像|指标|表格|名单|情绪分布)", text))
        full = bool(re.search(r"完整报告|完整的.{0,12}报告|完整.{0,10}报告|整份报告|主题报告|完整人群洞察|完整社媒舆情|人群洞察报告|社媒舆情报告", text))
        if full:
            out["mode"] = "full"
        elif partial:
            out["mode"] = "partial"
        if "用户反馈" in text and not out["domains"]:
            out["ambiguous_domains"] = ["audience", "social"]

        pending = state.get("pending", {})
        if pending.get("field") == "domain":
            if re.search(r"两个都要|两种都要|都需要|都要", text):
                out["domains"] = list(pending.get("choices", ["audience", "social"]))
                out["ambiguous_domains"] = []
            elif "人群" in text or "消费者" in text:
                out["domains"] = ["audience"]
            elif "舆情" in text or "社媒" in text:
                out["domains"] = ["social"]
        if pending.get("field") == "mode":
            if raw in ("完整报告", "完整的报告", "要完整报告"):
                out["mode"] = "full"
            elif raw in ("只要局部", "局部", "只做局部分析", "只要局部分析"):
                out["mode"] = "partial"

        # Preserve extra requests that do not match supported semantic vocabulary.
        for clause in re.split(r"另外|另做|另需|还需要|还要|再做|同时还要", text)[1:]:
            clause = clause.strip(" ，,。；;")
            if clause and not self._recognized(clause) and not self._metadata_only(clause):
                out["unknown_work"].append(clause)
        if re.search(r"量子|神秘|特殊专业分析|不认识的专业分析|某种高级分析|贝叶斯|结构方程", text):
            out["unknown_work"].append(text)
        return out

    def _recognized(self, text: str) -> bool:
        return any(re.search(p, text) for p in [*self.DOMAIN_PATTERNS.values(), *self.ACTION_PATTERNS.values()])

    @staticmethod
    def _metadata_only(text: str) -> bool:
        return bool(re.match(r"(?:时间|周期|对象|品牌|数据|文件|采用|改为|改成|20\d{2})", text))
