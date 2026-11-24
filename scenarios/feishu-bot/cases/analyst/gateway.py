"""analyst case 的 Gateway:复用通用 Gateway,固定挂载共享 Memory Store,产物存储按分析师/Topic 隔离,带 BYOK 鉴权头。"""
from __future__ import annotations

import asyncio

from arkagent.gateway.orchestrator import Gateway
from arkagent.memory_mounts import build_memory_resources
from arkagent.obs_pilot.reporter import PilotReporter
from arkagent.paths import get_case_paths
from arkagent.store import GatewayStore

from .config import AnalystConfig


def build_gateway(config: AnalystConfig, ark, sender, loop: asyncio.AbstractEventLoop):
    case_paths = get_case_paths("analyst")
    store = GatewayStore(case_paths.database_path)

    async def reply(chat_id: str, text: str) -> None:
        await loop.run_in_executor(None, sender.send_to_chat, chat_id, text)

    static_resources = tuple(build_memory_resources(config.memory_stores))
    # 方案 B 观测上报默认关闭，由 config.env 的 OBS_PILOT_ENABLED 打开。
    pilot = PilotReporter() if config.obs_pilot_enabled else None
    return Gateway(
        store,
        ark,
        reply,
        agent_id=config.agent_id,
        environment_id=config.environment_id,
        vault_id=config.vault_id,
        timeout_ms=None,  # 不截断用户响应：等到 Session 自身终态或出错
        authorized_open_ids=config.authorized_open_ids,
        loop=loop,
        extra_headers=config.extra_headers,
        static_resources=static_resources,
        output_tos=config.output_tos,
        scope_output_by_user_topic=True,
        pilot_reporter=pilot,
        download_resource=sender.download_resource,
    )
