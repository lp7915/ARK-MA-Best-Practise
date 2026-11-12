"""产物存储（Session 级 ``config.tos`` 覆写）：沙箱内写入 ``/mnt/session/outputs/`` 的文件落到指定 TOS 前缀。

不再使用 ``type: tos`` 资源挂载；工作区统一走产物存储，并按分析师、Topic 拆分前缀以避免互相覆盖。
"""
from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def build_output_storage(bucket: str, prefix: str) -> dict:
    """产物存储：Session 创建时覆写 Environment 的 ``config.tos``（bucket 与 prefix 必须同时提供）。"""
    if not bucket or not prefix:
        raise ValueError("产物存储必须同时提供 bucket 与 prefix")
    if not prefix.endswith("/"):
        raise ValueError(f"产物存储 prefix 必须以 / 结尾：{prefix!r}")
    return {"bucket": bucket, "prefix": prefix}


def _segment(value: str, label: str) -> str:
    """把身份标识规整为单层目录名；空值直接报错，避免落到上层目录造成串用。"""
    cleaned = _UNSAFE.sub("_", (value or "").strip())
    if not cleaned or set(cleaned) == {"."}:
        raise ValueError(f"{label} 不能为空")
    return cleaned


def scope_output_storage(base: dict, *, user: str, topic: str) -> dict:
    """在基础前缀下按 ``users/<分析师>/<Topic>/`` 切出独立工作区。

    - 不同分析师、同一分析师的不同 Topic 前缀互不重叠，不会互相覆盖；
    - 同一分析师同一 Topic 的前缀稳定（``/new`` 或重建 Session 后仍落同一目录），
      多个 Gateway 实例算出的前缀一致，无需共享本地状态。
    """
    prefix = f"{base['prefix']}users/{_segment(user, '分析师标识')}/{_segment(topic, 'Topic 标识')}/"
    return {"bucket": base["bucket"], "prefix": prefix}
