"""网关编排：飞书消息 → 方舟 Session。

移植自原 TS 项目 src/gateway.ts，用 asyncio 重写串行队列，并接入：
  - 卡点 B：创建 Session 时用 env_overrides 透传 FEISHU_USER_OPEN_ID。
  - 卡点 C：RoleManager 判是否挂 system.message（动态岗位注入）。
  - 卡点 D：MemoryManager 组装 resources（挂用户专属 Memory Store）。

聊天指令：/new 开新会话、/stop 中断当前任务、/remember <内容> 写入长期记忆、/role <描述> 模拟岗位调动、/whoami 查看当前岗位。
WS 回调（可能来自其它线程）只做去重与入队，满足飞书 3 秒处理约束。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable, Optional

from ..ark import ArkClient, RunResult
from ..attachments import Downloader, build_attachment_note, mount_message_attachments
from ..feishu import IncomingMessage
from ..memory import MemoryManager
from ..obs_pilot.reporter import PilotReporter
from ..role import RoleInfo, RoleManager
from ..store import ConversationKey, GatewayStore
from ..timing import Stopwatch, time_block
from ..tos_mounts import scope_output_storage

logger = logging.getLogger(__name__)

Reply = Callable[[str, str], Awaitable[None]]
DEFAULT_PROGRESS_DELAY_MS = 2_500


class KeyedQueue:
    """按 key 串行化协程：同一会话的消息按到达顺序依次处理，不同会话并行。

    所有方法都必须在事件循环线程内调用（由 Gateway 保证）。
    """

    def __init__(self) -> None:
        self._tails: dict[str, asyncio.Task] = {}

    def enqueue(self, key: str, task_factory: Callable[[], Awaitable[None]]) -> None:
        previous = self._tails.get(key)

        async def runner() -> None:
            if previous is not None:
                with contextlib.suppress(Exception):
                    await previous
            await task_factory()

        current = asyncio.get_event_loop().create_task(runner())
        self._tails[key] = current

        def _cleanup(done: asyncio.Task, k: str = key) -> None:
            if self._tails.get(k) is done:
                del self._tails[k]

        current.add_done_callback(_cleanup)


class Gateway:
    def __init__(
        self,
        store: GatewayStore,
        ark: ArkClient,
        reply: Reply,
        *,
        agent_id: str,
        environment_id: str,
        vault_id: str,
        timeout_ms: Optional[int],  # None=不设等待上限，只在 Session 终态/出错时返回
        authorized_open_ids: tuple[str, ...] = (),
        progress_delay_ms: int = DEFAULT_PROGRESS_DELAY_MS,
        role_manager: Optional[RoleManager] = None,
        memory_manager: Optional[MemoryManager] = None,
        before_create_session: Optional[Callable[[], Awaitable[None]]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        extra_headers: Optional[dict] = None,
        static_resources: tuple[dict, ...] = (),
        output_tos: Optional[dict] = None,
        scope_output_by_user_topic: bool = False,
        pilot_reporter: Optional[PilotReporter] = None,
        download_resource: Optional[Downloader] = None,
        after_turn: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> None:
        # 飞书附件下载函数(FeishuSender.download_resource);None 表示该 case 不支持附件,带附件的消息按原行为忽略。
        self._download_resource = download_resource
        self._store = store
        self._ark = ark
        self._reply = reply
        self._agent_id = agent_id
        self._environment_id = environment_id
        self._vault_id = vault_id
        self._timeout_ms = timeout_ms
        self._authorized_open_ids = set(authorized_open_ids)
        self._progress_delay_ms = progress_delay_ms
        self._role = role_manager
        self._memory = memory_manager
        self._before_create_session = before_create_session
        # 每轮结束后的可选钩子 (session_id, user_open_id):用于把该 session 的执行日志落成文档等。
        # 钩子的任何异常都不得影响本轮回复,见 _after_turn。
        self._after_turn = after_turn
        self._loop = loop
        self._queue = KeyedQueue()
        # BYOK Direct 模式：按请求动态附加的模型鉴权 Header；未配置时为 None（原豆包模式）。
        self._extra_headers = extra_headers
        # 每个 Session 固定追加的其它 resources（如全员共享的 Memory Store）。
        self._static_resources = list(static_resources)
        # 本 Gateway 创建的每个 Session 的产物存储（覆写 config.tos）；None 表示沿用 Environment 配置。
        self._output_tos = output_tos
        # True 时在 output_tos 前缀下再按 分析师/Topic 拆分，多人、多 Topic 的工作区互不覆盖。
        self._scope_output = scope_output_by_user_topic
        # 正在等待 Agent 回复的 session；/stop 只对这些 session 生效。
        self._active_runs: set[str] = set()
        # 已被 /stop 中断的 session：对应那一轮的回复由 /stop 负责，不再按正常结果/失败回复。
        self._stopped_runs: set[str] = set()
        # A′ 观测上报：None 表示关闭。开启后每轮结束把该 Session 的事件流转成 Pilot 记录落盘。
        self._pilot = pilot_reporter

    def accept(self, message: IncomingMessage) -> bool:
        """同步入口（可能被 WS 线程调用）：去重后把处理协程调度到事件循环。"""
        if not should_handle_message(message):
            return False
        if not message.text.strip() and self._download_resource is None:
            return False  # 纯附件消息但本 Gateway 不支持附件:没有可发给 Agent 的内容
        if not self._store.claim_event(message.event_id):
            return False
        key = to_conversation_key(message)
        conv_key = self._store.conversation_key(key)
        is_stop = message.text.strip() == "/stop"

        def _do_enqueue() -> None:
            if is_stop:
                # /stop 不进串行队列：同会话的上一条消息还在跑，排队会等到它结束才轮到中断。
                asyncio.get_event_loop().create_task(self._run_stop(message, key))
                return
            self._queue.enqueue(conv_key, lambda: self._run_task(message, key))

        running = None
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        target = self._loop or running
        if target is None:
            raise RuntimeError("Gateway.accept 需要一个运行中的事件循环")
        if running is target:
            _do_enqueue()
        else:
            target.call_soon_threadsafe(_do_enqueue)
        return True

    async def _run_task(self, message: IncomingMessage, key: ConversationKey) -> None:
        try:
            await self._process(message, key)
            self._store.complete_event(message.event_id, "completed")
        except Exception as error:  # noqa: BLE001 - 网关兜底，任何失败都要回执给用户
            self._store.complete_event(message.event_id, "failed")
            logger.exception(
                "处理消息失败 chat_id=%s event_id=%s", message.chat_id, message.event_id
            )
            reason = str(error)
            try:
                await self._reply(message.chat_id, f"执行失败：{reason[:240]}")
            except Exception:  # noqa: BLE001 - 兜底回执本身也可能失败（如飞书 API 异常），
                # 必须记录，否则用户和排查者都看不到任何痕迹，表现为「消息没发出去」。
                logger.exception(
                    "兜底回执也发送失败 chat_id=%s event_id=%s", message.chat_id, message.event_id
                )

    async def _run_stop(self, message: IncomingMessage, key: ConversationKey) -> None:
        try:
            await self._handle_stop(message, key)
            self._store.complete_event(message.event_id, "completed")
        except Exception as error:  # noqa: BLE001 - 与 _run_task 一致，失败要回执用户
            self._store.complete_event(message.event_id, "failed")
            logger.exception(
                "处理 /stop 失败 chat_id=%s event_id=%s", message.chat_id, message.event_id
            )
            try:
                await self._reply(message.chat_id, f"中断失败：{str(error)[:240]}")
            except Exception:  # noqa: BLE001 - 同上，兜底回执失败也要留痕
                logger.exception(
                    "/stop 兜底回执也发送失败 chat_id=%s event_id=%s",
                    message.chat_id,
                    message.event_id,
                )

    async def _handle_stop(self, message: IncomingMessage, key: ConversationKey) -> None:
        if self._authorized_open_ids and message.user_open_id not in self._authorized_open_ids:
            await self._reply(message.chat_id, "当前用户未授权。请联系管理员把你的 open_id 加入白名单。")
            return
        session_id = self._store.get_session(key)
        if not session_id or session_id not in self._active_runs:
            await self._reply(message.chat_id, "当前没有正在执行的任务。")
            return
        # 先登记再发中断：run() 收到 idle 后返回时，必须已能识别这是用户主动中断。
        self._stopped_runs.add(session_id)
        try:
            boundary = await self._ark.send_interrupt(session_id)
            result = await self._ark.wait_for_interrupt(session_id, boundary)
        except Exception:
            self._stopped_runs.discard(session_id)
            raise
        if result.terminal == "stopped":
            await self._reply(message.chat_id, "已中断当前任务。会话仍保留，可以继续发消息。")
        elif result.terminal == "failed":
            await self._reply(message.chat_id, f"已发送中断，但 Session 随后出错：{(result.error or '未知错误')[:200]}")
        else:
            await self._reply(message.chat_id, "已发送中断请求，但暂未确认 Agent 已停止，请稍后查看。")

    async def _process(self, message: IncomingMessage, key: ConversationKey) -> None:
        if self._authorized_open_ids and message.user_open_id not in self._authorized_open_ids:
            await self._reply(
                message.chat_id,
                "当前用户未授权。请联系管理员把你的 open_id 加入白名单。",
            )
            return

        text = message.text.strip()

        if not self._agent_id:
            await self._reply(
                message.chat_id,
                "当前 Bot 未配置 Agent。",
            )
            return

        if text == "/new":
            # 卡点 D：岗位调动开新 Session（下一条消息会挂同一 Memory Store）。
            self._store.reset_session(key)
            await self._reply(message.chat_id, "已开启新会话，下一条消息会创建新的 Agent Session（记忆延续）。")
            return
        if text == "/whoami":
            await self._reply(message.chat_id, self._describe_role(message.user_open_id))
            return
        if text.startswith("/remember"):
            await self._handle_remember_command(message, text)
            return
        if text.startswith("/role"):
            await self._handle_role_command(message, text)
            return

        if self._before_create_session:
            await self._before_create_session()

        sw = Stopwatch()
        session_id = self._store.get_session(key)
        progress_task: Optional[asyncio.Task] = None
        first_message = not session_id
        if not session_id:
            await self._reply(message.chat_id, "已收到，正在处理。首次启动可能需要几分钟。")
            with time_block("gateway.create_session", user=message.user_open_id, first=True):
                session_id = await self._create_session(message, key)
            self._store.save_session(key, session_id, self._agent_id, user_id=message.user_id, chat_type=message.chat_type)
        else:
            progress_task = asyncio.get_event_loop().create_task(self._delayed_progress(message.chat_id))

        # 卡点 C：仅在本 session 尚未注入过岗位时挂 system.message。
        system_message = None
        if self._role:
            with time_block("gateway.role_system_message", user=message.user_open_id):
                system_message = self._role.system_message_for(message.user_open_id, session_id)

        user_text = message.text
        if message.resources and self._download_resource is not None:
            # 附件挂到已存在的 Session(/mnt/session/uploads/),正文末尾告诉 Agent 路径;失败只出提示不中断。
            with time_block("gateway.mount_attachments", session=session_id, count=len(message.resources)):
                paths, notices = await mount_message_attachments(
                    self._ark, self._download_resource, session_id, message
                )
            note = build_attachment_note(paths, notices, attachments_only=not message.text.strip())
            user_text = f"{user_text}\n\n{note}".strip() if note else user_text

        self._active_runs.add(session_id)
        try:
            # 不传 on_progress：避免把 tool_use/tool_result 转成进度消息刷屏。
            with time_block("gateway.run", session=session_id, first=first_message):
                result = await self._ark.run(
                    session_id, user_text, self._timeout_ms, system_message=system_message,
                    extra_headers=self._extra_headers,
                )
        except Exception:
            if session_id in self._stopped_runs:
                self._stopped_runs.discard(session_id)
                return  # 用户已 /stop，由 /stop 的回执告知，不再报「执行失败」
            raise
        finally:
            self._active_runs.discard(session_id)
            if progress_task is not None:
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task
        if session_id in self._stopped_runs:
            self._stopped_runs.discard(session_id)
            return  # 被中断的这一轮只可能有半截回复，丢弃，不推给用户
        with time_block("gateway.reply", chat=message.chat_id):
            await self._reply(message.chat_id, result_to_reply(result))
        sw.mark("gateway.total", user=message.user_open_id, first=first_message)
        await self._report_observability(session_id, message.user_open_id)
        await self._run_after_turn(session_id, message.user_open_id)

    async def _run_after_turn(self, session_id: str, user_open_id: str) -> None:
        if self._after_turn is None:
            return
        try:
            await self._after_turn(session_id, user_open_id)
        except Exception:  # noqa: BLE001 - 旁路能力失败不能让用户收到\"执行失败\"
            logging.getLogger("arkagent.gateway").warning(
                "after_turn 钩子失败 session=%s", session_id, exc_info=True
            )

    async def _report_observability(self, session_id: str, user_open_id: str) -> None:
        """A′ 观测上报：旁路，任何失败都只记日志，不影响用户拿到的回复。"""
        if self._pilot is None:
            return
        with time_block("gateway.obs_report", session=session_id):
            await self._pilot.report(self._ark, session_id, user_id=user_open_id)

    async def _create_session(self, message: IncomingMessage, key: ConversationKey) -> str:
        resources: list[dict] = []
        role_info: Optional[RoleInfo] = None
        if self._role:
            with time_block("gateway.ensure_fresh_role", user=message.user_open_id):
                role_info = RoleInfo.from_dict(self._role.ensure_fresh_role(message.user_open_id))
        if self._memory:
            with time_block("gateway.build_session_resources", user=message.user_open_id):
                resources = await self._memory.build_session_resources(message.user_open_id, role_info)
        resources = [*resources, *self._static_resources]
        output_tos = self._output_tos
        if output_tos and self._scope_output:
            # Topic = 飞书话题；非话题消息（单聊/群主线）退化为 chat_id。
            output_tos = scope_output_storage(
                output_tos, user=key.user_open_id or "", topic=key.thread_id or key.chat_id
            )
        extra: dict = {"output_tos": output_tos} if output_tos else {}
        with time_block("gateway.ark_create_session", user=message.user_open_id):
            return await self._ark.create_session(
                self._agent_id,
                self._environment_id,
                vault_ids=[self._vault_id] if self._vault_id else [],
                env_overrides={"FEISHU_USER_OPEN_ID": message.user_open_id},  # 卡点 B
                resources=resources,  # 卡点 D
                **extra,
            )

    async def _handle_remember_command(self, message: IncomingMessage, text: str) -> None:
        # 卡点 D 写入链路：方舟不自动记忆，写记忆须应用侧调 API。/remember <内容> 把内容
        # 写入用户专属 Memory Store，下个 Session（含 /new 后）挂载同一 Store 即可读到。
        if not self._memory:
            await self._reply(message.chat_id, "当前未启用长期记忆功能。")
            return
        note = text[len("/remember"):].strip()
        if not note:
            await self._reply(
                message.chat_id,
                "用法：/remember <要记住的内容>，例如 /remember 我负责的重点客户是张先生，倾向 ET9，本周要跟进试驾。",
            )
            return
        role_info: Optional[RoleInfo] = None
        if self._role:
            role_info = RoleInfo.from_dict(self._role.ensure_fresh_role(message.user_open_id))
        path = await self._memory.remember(message.user_open_id, note, role_info)
        await self._reply(
            message.chat_id,
            f"已记住并写入长期记忆（{path}）。开新会话（/new）或以后再来，我都能读到这条笔记。",
        )

    async def _handle_role_command(self, message: IncomingMessage, text: str) -> None:
        if not self._role:
            await self._reply(message.chat_id, "当前未启用岗位注入功能。")
            return
        desc = text[len("/role"):].strip()
        if not desc:
            await self._reply(message.chat_id, "用法：/role 新岗位名称[/门店]，例如 /role 销售经理/上海浦东蔚来中心")
            return
        role_part, _, store_part = desc.partition("/")
        new_role = RoleInfo(role=role_part.strip(), store=store_part.strip() or "未知门店")
        self._role.on_role_change(message.user_open_id, new_role)
        await self._reply(
            message.chat_id,
            f"已更新岗位为「{new_role.role}」，下一轮对话会自动向 Agent 声明新岗位（无需新建 Session）。",
        )

    def _describe_role(self, open_id: str) -> str:
        if not self._role:
            return "当前未启用岗位注入功能。"
        role = self._role.ensure_fresh_role(open_id)
        return f"当前岗位：{role.get('role')}（{role.get('store')}）"

    async def _delayed_progress(self, chat_id: str) -> None:
        await asyncio.sleep(self._progress_delay_ms / 1000)
        await self._reply(chat_id, "已收到，正在处理，请稍候。")


def should_handle_message(message: IncomingMessage) -> bool:
    # 纯图片/文件消息没有正文,但带附件时也要处理(是否真能处理附件由 Gateway 是否配置下载器决定)。
    if not message.text.strip() and not message.resources:
        return False
    return message.chat_type == "p2p" or message.mentioned_bot


def to_conversation_key(message: IncomingMessage) -> ConversationKey:
    return ConversationKey(
        tenant_key=message.tenant_key,
        chat_id=message.chat_id,
        thread_id=message.thread_id,
        user_open_id=message.user_open_id,
    )


def result_to_reply(result: RunResult) -> str:
    if result.terminal == "failed":
        raise RuntimeError("Agent Session 执行失败")
    if not result.messages:
        raise RuntimeError("Agent Session 已结束，但没有产生回复")
    # 一个 run 可能产生多条 agent.message：前面通常是“让我先检查…”类播报，最后一条才是完整结果。
    return result.messages[-1]
