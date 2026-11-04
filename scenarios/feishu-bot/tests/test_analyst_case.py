import asyncio

import pytest

from cases.analyst.config import load_case_config
from cases.analyst.gateway import build_gateway
from test_gateway import FakeArk, message

BASE = {
    "ARK_API_KEY": "k", "FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "s",
    "ANALYST_AGENT_ID": "agent-1", "ANALYST_ENVIRONMENT_ID": "env-1",
}
MEM = {"ANALYST_MEMORY_STORE_ID": "mem-1", "ANALYST_MEMORY_ACCESS": "read_only"}


def test_config_defaults_and_tos():
    cfg = load_case_config({**BASE, "ANALYST_TOS_MOUNTS": "tos://b/a/"})
    assert cfg.tos_mounts == (("b", "a/"),)
    assert cfg.output_tos is None
    assert cfg.session_timeout_ms == 600000
    assert cfg.extra_headers is None


def test_config_byok_header_and_pairing():
    cfg = load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization",
                            "BYOK_MODEL_AUTH_HEADER_VALUE": "Bearer x"})
    assert cfg.extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}
    with pytest.raises(RuntimeError, match="同时填写"):
        load_case_config({**BASE, "BYOK_MODEL_AUTH_HEADER_NAME": "Authorization"})


def test_memory_access_must_be_explicit_when_memory_configured():
    with pytest.raises(RuntimeError, match="ANALYST_MEMORY_ACCESS"):
        load_case_config({**BASE, "ANALYST_MEMORY_STORE_ID": "mem-1"})
    with pytest.raises(RuntimeError, match="ANALYST_MEMORY_ACCESS"):
        load_case_config({**BASE, "ANALYST_MEMORY_STORE_ID": "mem-1", "ANALYST_MEMORY_ACCESS": "rw"})
    assert load_case_config({**BASE}).memory_access == ""  # 未挂载 Memory 时无需配置


def test_output_tos_requires_both_fields():
    cfg = load_case_config({**BASE, "ANALYST_OUTPUT_TOS_BUCKET": "b", "ANALYST_OUTPUT_TOS_PREFIX": "o/"})
    assert cfg.output_tos == {"bucket": "b", "prefix": "o/"}
    with pytest.raises(RuntimeError, match="ANALYST_OUTPUT_TOS"):
        load_case_config({**BASE, "ANALYST_OUTPUT_TOS_BUCKET": "b"})


def test_config_rejects_missing_and_bad_tos():
    with pytest.raises(RuntimeError, match="缺少环境变量"):
        load_case_config({})
    with pytest.raises(RuntimeError, match="ANALYST_TOS_MOUNTS"):
        load_case_config({**BASE, "ANALYST_TOS_MOUNTS": "tos://b/a"})


async def test_gateway_mounts_memory_tos_and_sends_byok_header(tmp_path, monkeypatch):
    monkeypatch.setenv("ARKAGENT_HOME", str(tmp_path))
    cfg = load_case_config({
        **BASE, **MEM, "ANALYST_TOS_MOUNTS": "tos://b/a/",
        "ANALYST_OUTPUT_TOS_BUCKET": "ob", "ANALYST_OUTPUT_TOS_PREFIX": "out/",
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
        {"type": "memory_store", "memory_store_id": "mem-1", "access": "read_only"},
        {"type": "tos", "tos_bucket": "b", "tos_key": "a/"},
    ]
    assert ark.last_output_tos == {"bucket": "ob", "prefix": "out/"}
    assert ark.last_extra_headers == {"X-User-Model-Header-Authorization": "Bearer x"}
