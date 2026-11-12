import asyncio

from arkagent.ark import InterruptResult, RunResult
from arkagent.gateway.orchestrator import Gateway
from arkagent.store import GatewayStore
from test_gateway import FakeArk, message


class BlockingArk(FakeArk):
    """run() 会一直阻塞到 release；send_interrupt 后放行并返回 idle（与真实中断后事件流行为一致）。"""

    def __init__(self, interrupt_terminal="stopped"):
        super().__init__(RunResult(terminal="idle", messages=[]))
        self.release = asyncio.Event()
        self.interrupts = 0
        self._terminal = interrupt_terminal

    async def run(self, session_id, text, timeout_ms, **kw):
        self.runs += 1
        await self.release.wait()
        return self._run_result

    async def send_interrupt(self, session_id):
        self.interrupts += 1
        self.release.set()
        return object()

    async def wait_for_interrupt(self, session_id, boundary, **kw):
        return InterruptResult(terminal=self._terminal, error="boom")


def _gw(ark, replies):
    async def reply(chat_id, text):
        replies.append(text)

    return Gateway(GatewayStore(":memory:"), ark, reply,
                   agent_id="a", environment_id="e", vault_id="v", timeout_ms=None)


async def test_stop_interrupts_running_task_and_suppresses_failure():
    ark, replies = BlockingArk(), []
    gw = _gw(ark, replies)
    gw.accept(message(event_id="e1", text="跑个大任务"))
    await asyncio.sleep(0.05)
    gw.accept(message(event_id="e2", text="/stop"))  # 同会话，不能排在 e1 后面
    await asyncio.sleep(0.1)
    assert ark.interrupts == 1
    assert any("已中断" in r for r in replies)
    assert not any("执行失败" in r for r in replies)
    assert gw._stopped_runs == set() and gw._active_runs == set()


async def test_stop_without_running_task():
    ark, replies = BlockingArk(), []
    gw = _gw(ark, replies)
    gw.accept(message(event_id="e1", text="/stop"))
    await asyncio.sleep(0.05)
    assert replies == ["当前没有正在执行的任务。"]
    assert ark.interrupts == 0


async def test_stop_reports_session_error_after_interrupt():
    ark, replies = BlockingArk("failed"), []
    gw = _gw(ark, replies)
    gw.accept(message(event_id="e1", text="任务"))
    await asyncio.sleep(0.05)
    gw.accept(message(event_id="e2", text="/stop"))
    await asyncio.sleep(0.1)
    assert any("Session 随后出错" in r for r in replies)


async def test_next_message_works_after_stop():
    ark, replies = BlockingArk(), []
    gw = _gw(ark, replies)
    gw.accept(message(event_id="e1", text="任务"))
    await asyncio.sleep(0.05)
    gw.accept(message(event_id="e2", text="/stop"))
    await asyncio.sleep(0.1)
    ark._run_result = RunResult(terminal="idle", messages=["新回复"])
    gw.accept(message(event_id="e3", text="继续"))
    await asyncio.sleep(0.1)
    assert replies[-1] == "新回复"
    assert ark.creates == 1  # 沿用同一 Session
