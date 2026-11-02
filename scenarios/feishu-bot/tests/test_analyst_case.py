import asyncio

import pytest

from cases.analyst.config import load_case_config
from cases.analyst.gateway import build_gateway
from test_gateway import FakeArk, message

BASE = {
    "ARK_API_KEY": "k", "FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "s",
    "ANALYST_AGENT_ID": "agent-1", "ANALYST_ENVIRONMENT_ID": "env-1",
}


def test_config_defaults_and_tos():
    cfg = load_case_config({**BASE, "ANALYST_TOS_MOUNTS": "tos://b/a/, tos://b/c/"})
    assert cfg.tos_mounts == (("b", "a/"), ("b", "c/"))
    assert cfg.session_timeout_ms == 600000
    assert cfg.extra_headers is None


def test_config_byok_header_and_pairing():
    cfg = load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization",
                            "BYOK_MODEL_AUTH_HEADER_VALUE": "Bearer x"})
    assert cfg.extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}
    with pytest.raises(RuntimeError, match="同时填写"):
        load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization"})


def test_config_rejects_missing_and_bad_tos():
    with pytest.raises(RuntimeError, match="缺少环境变量"):
        load_case_config({})
    with pytest.raises(RuntimeError, match="ANALYST_TOS_MOUNTS"):
        load_case_config({**BASE, "ANALYST_TOS_MOUNTS": "tos://b/a"})


async def test_gateway_mounts_memory_tos_and_sends_byok_header(tmp_path, monkeypatch):
    monkeypatch.setenv("ARKAGENT_HOME", str(tmp_path))
    cfg = load_case_config({
        **BASE, "ANALYST_MEMORY_STORE_ID": "mem-1", "ANALYST_TOS_MOUNTS": "tos://b/a/",
        "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization", "BYOK_MODEL_AUTH_HEADER_VALUE": "Bearer x",
    })
    ark = FakeArk()
    replies = []

    class Sender:
        def send_to_chat(self, chat_id, text):
            replies.append(text)

    loop = asyncio.get_running_loop()
    gw = build_gateway(cfg, ark, Sender(), loop)
    gw.accept(message())
    await asyncio.sleep(0.1)
    assert ark.last_resources == [
        {"type": "memory_store", "memory_store_id": "mem-1"},
        {"type": "tos", "tos_bucket": "b", "tos_key": "a/"},
    ]
    assert ark.last_extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}
