import asyncio

import pytest

from arkagent.tos_mounts import MAX_SESSION_RESOURCES, build_tos_resources, parse_tos_mounts
from arkagent.gateway.orchestrator import Gateway
from arkagent.store import GatewayStore
from test_gateway import FakeArk, message


def test_parse_accepts_commas_newlines_and_dedupes():
    raw = "tos://b1/a/, tos://b2/x/y/\ntos://b1/a/"
    assert parse_tos_mounts(raw) == (("b1", "a/"), ("b2", "x/y/"))
    assert parse_tos_mounts("") == ()


@pytest.mark.parametrize("raw", ["b1/a/", "tos:///a/", "tos://b1", "tos://b1/a"])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_tos_mounts(raw)


def test_parse_rejects_over_limit():
    raw = ",".join(f"tos://b/d{i}/" for i in range(MAX_SESSION_RESOURCES + 1))
    with pytest.raises(ValueError, match="不能超过"):
        parse_tos_mounts(raw)


def test_build_resources_shape():
    assert build_tos_resources((("b1", "a/"),)) == [
        {"type": "tos", "tos_bucket": "b1", "tos_key": "a/"}
    ]


async def test_gateway_mounts_tos_on_create_session():
    ark = FakeArk()

    async def reply(chat_id, text):
        pass

    gw = Gateway(
        GatewayStore(":memory:"), ark, reply,
        agent_id="a", environment_id="e", vault_id="v", timeout_ms=5_000,
        tos_mounts=(("b1", "data/"),),
    )
    gw.accept(message())
    await asyncio.sleep(0.05)
    assert ark.last_resources == [{"type": "tos", "tos_bucket": "b1", "tos_key": "data/"}]
