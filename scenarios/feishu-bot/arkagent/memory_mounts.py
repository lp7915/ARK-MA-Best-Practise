"""Memory Store 的 Session 挂载：逐个记忆库配置读写权限，未配置时默认只读。

平台挂载时 ``access`` 缺省为 ``read_write``，这里始终显式下发，缺省按 ``read_only``。
"""
from __future__ import annotations

from typing import Iterable

ACCESS_MODES = ("read_only", "read_write")
DEFAULT_MEMORY_ACCESS = "read_only"


def parse_memory_stores(raw: str) -> tuple[tuple[str, str], ...]:
    """把逗号/换行分隔的 ``<store_id>[:read_only|read_write]`` 解析为 ``((store_id, access), ...)``。

    未写权限的按只读；同一记忆库重复出现时，权限必须一致，否则抛 ValueError。
    """
    stores: dict[str, str] = {}
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        store_id, sep, access = item.partition(":")
        store_id, access = store_id.strip(), access.strip()
        if not store_id:
            raise ValueError(f"记忆库配置缺少 ID：{item!r}")
        if not sep:
            access = DEFAULT_MEMORY_ACCESS
        if access not in ACCESS_MODES:
            raise ValueError(f"记忆库 {store_id} 的权限必须是 {' 或 '.join(ACCESS_MODES)}：{access!r}")
        if stores.setdefault(store_id, access) != access:
            raise ValueError(f"记忆库 {store_id} 重复配置且权限不一致")
    return tuple(stores.items())


def build_memory_resources(stores: Iterable[tuple[str, str]]) -> list[dict]:
    """生成 ``create_session(resources=...)`` 所需的 ``type: memory_store`` 条目（始终显式带 access）。"""
    return [
        {"type": "memory_store", "memory_store_id": store_id, "access": access}
        for store_id, access in stores
    ]
