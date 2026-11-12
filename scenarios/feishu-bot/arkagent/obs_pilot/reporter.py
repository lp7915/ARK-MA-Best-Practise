"""方案 B 上报调度：每轮 Session 运行结束后，把事件流转换成 Pilot 规范记录并落盘。

为什么是「整段重转 + 跳过已发前缀」而不是「只转新增事件」：
  Pilot 只有在某个 turn 的最后一条 llm.response 带 `finish_reasons` 时才会导出该 turn，
  而这个标记要等 `session.status_idle` 事件到达后才能补上。只转新增事件的话，最后一条
  llm.response 早就发出去了，turn 永远不会被导出。整段重转能拿到最新的收尾状态，
  用「上次已发条数」跳过前缀即可避免重复上报。

前提：事件流只追加不改写，因此同一批事件重转出来的记录前缀是稳定的。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from .converter import convert
from .sink import write_records

logger = logging.getLogger(__name__)

# 事件流的保留期有限，单个 Session 的事件量以千计；每轮重拉全量在可接受范围内，
# 但超过这个上限就跳过上报，避免把网关拖慢。
_MAX_EVENTS = 5_000


@dataclass
class _SessionState:
    emitted: int = 0  # 已经写出的记录条数，用于跳过重转产生的前缀


@dataclass
class PilotReporter:
    """把一个 Session 的事件流上报到本机 Pilot 输入目录。"""

    model: Optional[str] = None
    provider: Optional[str] = None
    agent_id: str = "claude-code"
    _state: dict[str, _SessionState] = field(default_factory=dict)

    def _session(self, session_id: str) -> _SessionState:
        state = self._state.get(session_id)
        if state is None:
            state = self._state[session_id] = _SessionState()
        return state

    async def report(self, ark, session_id: str, *, user_id: str = "") -> int:
        """拉取该 Session 的全量事件，转换后写入尚未上报的部分，返回本次写入条数。

        任何异常都在此处吞掉并记日志：观测是旁路，不能影响用户拿回复。
        """
        try:
            events = await ark.list_session_events(session_id)
        except Exception:  # noqa: BLE001 - 观测失败不影响主流程
            logger.warning("obs: 拉取 Session %s 事件失败，跳过本次上报", session_id, exc_info=True)
            return 0

        if not events:
            return 0
        if len(events) > _MAX_EVENTS:
            logger.warning("obs: Session %s 事件数 %d 超过上限，跳过上报", session_id, len(events))
            return 0

        try:
            records = convert(
                events,
                session_id=session_id,
                user_id=user_id,
                model=self.model,
                provider=self.provider,
            )
        except Exception:  # noqa: BLE001
            logger.warning("obs: Session %s 转换失败，跳过本次上报", session_id, exc_info=True)
            return 0

        state = self._session(session_id)
        fresh = records[state.emitted:]
        if not fresh:
            return 0

        try:
            written = await asyncio.to_thread(write_records, fresh)
        except Exception:  # noqa: BLE001
            logger.warning("obs: Session %s 写入 Pilot 输入目录失败", session_id, exc_info=True)
            return 0

        state.emitted += written
        return written
