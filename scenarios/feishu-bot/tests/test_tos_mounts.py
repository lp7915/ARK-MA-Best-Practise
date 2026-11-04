import asyncio

import pytest

from arkagent.tos_mounts import build_output_storage, build_tos_resources, parse_tos_mounts
from arkagent.gateway.orchestrator import Gateway
from arkagent.store import GatewayStore
from test_gateway import FakeArk, message


def test_parse_single_mount_and_empty():
    assert parse_tos_mounts("tos://b1/a/") == (("b1", "a/"),)
    assert parse_tos_mounts("tos://b1/a/\ntos://b1/a/") == (("b1", "a/"),)  # 完全相同视为一个
    assert parse_tos_mounts("") == ()


@pytest.mark.parametrize("raw", ["b1/a/", "tos:///a/", "tos://b1", "tos://b1/a"])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_tos_mounts(raw)


def test_parse_allows_multiple_distinct_mounts():
    raw = "tos://b1/a/, tos://b1/b/\ntos://b2/c/"
    assert parse_tos_mounts(raw) == (("b1", "a/"), ("b1", "b/"), ("b2", "c/"))


def test_output_storage_requires_bucket_prefix_and_trailing_slash():
    assert build_output_storage("b", "x/") == {"bucket": "b", "prefix": "x/"}
    for bucket, prefix in (("", "x/"), ("b", ""), ("b", "x")):
        with pytest.raises(ValueError):
            build_output_storage(bucket, prefix)


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


async def test_gateway_passes_output_tos_to_create_session():
    ark = FakeArk()

    async def reply(chat_id, text):
        pass

    gw = Gateway(
        GatewayStore(":memory:"), ark, reply,
        agent_id="a", environment_id="e", vault_id="v", timeout_ms=5_000,
        output_tos={"bucket": "b", "prefix": "out/"},
    )
    gw.accept(message())
    await asyncio.sleep(0.05)
    assert ark.last_output_tos == {"bucket": "b", "prefix": "out/"}
