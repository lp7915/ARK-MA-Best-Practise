"""Versioned demo contracts. Registry errors never mean professional inability."""

from __future__ import annotations

import copy
import json
from pathlib import Path


class RegistryError(ValueError):
    pass


class Registry:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.version = self.data.get("registry_version", "")
        if not self.version or self.data.get("simulation_only") is not True:
            raise RegistryError("需显式标注版本及 simulation_only=true 的演示注册表")
        self.topics = self._index(self.data.get("topics", []), "topic")
        self.capabilities = self._index(self.data.get("capabilities", []), "capability")
        self.unsupported_methods = self.data.get("unsupported_methods", {})
        for entry in self.topics.values():
            for field in ("domain", "product", "outputs", "required_execution_fields"):
                if field not in entry:
                    raise RegistryError(f"Topic {entry['id']} 缺少 {field}")
            if entry["product"] not in entry["outputs"]:
                raise RegistryError(f"Topic {entry['id']} 的产物契约不含完整产品")
        for entry in self.capabilities.values():
            for field in ("method", "input_type", "outputs", "required_execution_fields"):
                if field not in entry:
                    raise RegistryError(f"能力 {entry['id']} 缺少 {field}")

    @staticmethod
    def _index(entries: list, kind: str) -> dict:
        result = {}
        for entry in entries:
            key = entry.get("id", "")
            if not key.startswith("demo_") or not entry.get("version"):
                raise RegistryError(f"{kind} 必须使用 demo_ ID 并登记版本")
            if key in result:
                raise RegistryError(f"重复资源 ID: {key}")
            result[key] = entry
        return result

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Registry":
        path = Path(path) if path else Path(__file__).with_name("catalog.json")
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def topic_for_domain(self, domain: str) -> list[dict]:
        return [t for t in self.topics.values() if t["domain"] == domain and t.get("enabled")]

    def capability_for_method(self, method: str) -> list[dict]:
        return [c for c in self.capabilities.values() if c["method"] == method and c.get("enabled")]

    def evidence(self, entry: dict) -> str:
        return f"{entry['id']}@{entry['version']}"
