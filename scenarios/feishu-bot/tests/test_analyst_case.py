import asyncio

import pytest

from cases.analyst.config import load_case_config
from cases.analyst.gateway import build_gateway
from test_gateway import FakeArk, message

BASE = {
    "ARK_API_KEY": "k", "FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "s",
    "ANALYST_AGENT_ID": "agent-1", "ANALYST_ENVIRONMENT_ID": "env-1",
}
MEM = {"ANALYST_MEMORY_STORES": "mem-1:read_only,mem-2:read_write,mem-3"}


def test_config_defaults():
    cfg = load_case_config(BASE)
    assert cfg.output_tos is None
    assert cfg.extra_headers is None


def test_config_byok_header_and_pairing():
    cfg = load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization",
                            "BYOK_MODEL_AUTH_HEADER_VALUE": "Bearer x"})
    assert cfg.extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}
    with pytest.raises(RuntimeError, match="同时填写"):
        load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization"})


def test_memory_stores_are_configured_per_store_and_default_read_only():
    cfg = load_case_config({**BASE, **MEM})
    assert cfg.memory_stores == (("mem-1", "read_only"), ("mem-2", "read_write"), ("mem-3", "read_only"))
    assert load_case_config({**BASE}).memory_stores == ()
    with pytest.raises(RuntimeError, match="ANALYST_MEMORY_STORES"):
        load_case_config({**BASE, "ANALYST_MEMORY_STORES": "mem-1:rw"})


def test_output_tos_requires_both_fields():
    cfg = load_case_config({**BASE, "ANALYST_OUTPUT_TOS_BUCKET": "b", "ANALYST_OUTPUT_TOS_PREFIX": "o/"})
    assert cfg.output_tos == {"bucket": "b", "prefix": "o/"}
    with pytest.raises(RuntimeError, match="ANALYST_OUTPUT_TOS"):
        load_case_config({**BASE, "ANALYST_OUTPUT_TOS_BUCKET": "b"})


def test_config_rejects_missing():
    with pytest.raises(RuntimeError, match="缺少环境变量"):
        load_case_config({})


async def test_gateway_mounts_memory_scopes_output_and_sends_byok_header(tmp_path, monkeypatch):
    monkeypatch.setenv("ARKAGENT_HOME", str(tmp_path))
    cfg = load_case_config({
        **BASE, **MEM,
        "ANALYST_OUTPUT_TOS_BUCKET": "ob", "ANALYST_OUTPUT_TOS_PREFIX": "out/",
        "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization", "BYOK_MODEL_AUTH_HEADER_VALUE": "Bearer x",
    })
    ark = FakeArk()
    replies = []

    class Sender:
        def send_to_chat(self, chat_id, text):
            replies.append(text)

        def download_resource(self, message_id, file_key, resource_type):
            return b""

    loop = asyncio.get_running_loop()
    gw = build_gateway(cfg, ark, Sender(), loop)
    gw.accept(message())
    await asyncio.sleep(0.1)
    assert ark.last_resources == [
        {"type": "memory_store", "memory_store_id": "mem-1", "access": "read_only"},
        {"type": "memory_store", "memory_store_id": "mem-2", "access": "read_write"},
        {"type": "memory_store", "memory_store_id": "mem-3", "access": "read_only"},
    ]
    assert ark.last_output_tos == {"bucket": "ob", "prefix": "out/users/user-1/chat-1/"}
    assert ark.last_extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}


async def test_analyst_gateway_does_not_cap_run_time(tmp_path, monkeypatch):
    monkeypatch.setenv("ARKAGENT_HOME", str(tmp_path))
    ark = FakeArk()
    seen = {}
    orig = ark.run

    async def run(session_id, text, timeout_ms, **kw):
        seen["timeout_ms"] = timeout_ms
        return await orig(session_id, text, timeout_ms, **kw)

    ark.run = run

    class Sender:
        def send_to_chat(self, chat_id, text):
            pass

        def download_resource(self, message_id, file_key, resource_type):
            return b""

    gw = build_gateway(load_case_config(BASE), ark, Sender(), asyncio.get_running_loop())
    gw.accept(message())
    await asyncio.sleep(0.1)
    assert seen["timeout_ms"] is None
