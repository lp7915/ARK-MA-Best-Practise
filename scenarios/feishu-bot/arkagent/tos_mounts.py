"""Session 级 TOS 目录挂载：解析 ``tos://bucket/prefix/`` 列表并生成 ``resources`` 条目。

挂载后文件出现在沙箱 ``/mnt/session/storage/``。与 Environment 的 ``config.tos``
（产物存储）是两回事，见方舟 Managed Agents 文档「区分产物存储与 TOS 资源挂载」。
"""
from __future__ import annotations

from typing import Iterable

# 方舟限制：单个 Session 最多挂载 100 个文件资源，TOS 目录同样计入。
MAX_SESSION_RESOURCES = 100
_SCHEME = "tos://"


def parse_tos_mounts(raw: str) -> tuple[tuple[str, str], ...]:
    """把逗号/换行分隔的 ``tos://bucket/dir/`` 解析为 ``((bucket, key), ...)``，去重并保序。

    ``tos_key`` 必须是以 ``/`` 结尾的目录，不合法直接抛 ValueError，避免带病创建 Session。
    """
    mounts: list[tuple[str, str]] = []
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if not item.startswith(_SCHEME):
            raise ValueError(f"TOS 挂载项必须以 {_SCHEME} 开头：{item!r}")
        bucket, _, key = item[len(_SCHEME):].partition("/")
        if not bucket:
            raise ValueError(f"TOS 挂载项缺少 bucket：{item!r}")
        if not key or not key.endswith("/"):
            raise ValueError(f"TOS 挂载项必须是以 / 结尾的目录：{item!r}")
        if (bucket, key) not in mounts:
            mounts.append((bucket, key))
    if len(mounts) > MAX_SESSION_RESOURCES:
        raise ValueError(f"TOS 挂载目录不能超过 {MAX_SESSION_RESOURCES} 个，当前 {len(mounts)}")
    return tuple(mounts)


def build_tos_resources(mounts: Iterable[tuple[str, str]]) -> list[dict]:
    """生成 ``create_session(resources=...)`` 所需的 ``type: tos`` 条目。"""
    return [{"type": "tos", "tos_bucket": bucket, "tos_key": key} for bucket, key in mounts]
