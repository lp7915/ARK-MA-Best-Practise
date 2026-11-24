"""ada-pm case 的 Gateway:复用通用 Gateway,挂载 5 个只读知识库,带 BYOK 鉴权头。"""
from __future__ import annotations

import asyncio

from arkagent.gateway.orchestrator import Gateway
from arkagent.memory_mounts import build_memory_resources
from arkagent.paths import get_case_paths
from arkagent.store import GatewayStore

from config import AdaPmConfig  # legacy loader:config.py 已注册到 sys.modules["config"]


def build_gateway(config: AdaPmConfig, ark, sender, loop: asyncio.AbstractEventLoop):
    case_paths = get_case_paths("ada-pm")
    store = GatewayStore(case_paths.database_path)

    async def reply(chat_id: str, text: str) -> None:
        await loop.run_in_executor(None, sender.send_to_chat, chat_id, text)

    static_resources = tuple(build_memory_resources(config.memory_stores))
    return Gateway(
        store,
        ark,
        reply,
        agent_id=config.agent_id,
        environment_id=config.environment_id,
        vault_id="",
        timeout_ms=None,  # 等 Session 自身终态，不截断
        authorized_open_ids=config.authorized_open_ids,
        loop=loop,
        extra_headers=config.extra_headers,
        static_resources=static_resources,
        output_tos=config.output_tos,
        scope_output_by_user_topic=True,  # 产物按 users/<open_id>/<topic>/ 隔离，对齐 analyst
    )