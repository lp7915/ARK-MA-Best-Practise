"""analyst case 的 Gateway:复用通用 Gateway,固定挂载共享 Memory Store 与 TOS 目录,带 BYOK 鉴权头。"""
from __future__ import annotations

import asyncio

from arkagent.gateway.orchestrator import Gateway
from arkagent.memory_mounts import build_memory_resources
from arkagent.paths import get_case_paths
from arkagent.store import GatewayStore

from .config import AnalystConfig


def build_gateway(config: AnalystConfig, ark, sender, loop: asyncio.AbstractEventLoop):
    case_paths = get_case_paths("analyst")
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
        vault_id=config.vault_id,
        timeout_ms=config.session_timeout_ms,
        authorized_open_ids=config.authorized_open_ids,
        loop=loop,
        extra_headers=config.extra_headers,
        tos_mounts=config.tos_mounts,
        static_resources=static_resources,
        output_tos=config.output_tos,
    )
