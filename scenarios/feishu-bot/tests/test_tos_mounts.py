import asyncio

import pytest

from arkagent.tos_mounts import build_output_storage, scope_output_storage
from arkagent.gateway.orchestrator import Gateway
from arkagent.store import GatewayStore
from test_gateway import FakeArk, message


def test_output_storage_requires_bucket_prefix_and_trailing_slash():
    assert build_output_storage("b", "x/") == {"bucket": "b", "prefix": "x/"}
    for bucket, prefix in (("", "x/"), ("b", ""), ("b", "x")):
        with pytest.raises(ValueError):
            build_output_storage(bucket, prefix)


def test_scope_isolates_by_user_and_topic():
    base = {"bucket": "b", "prefix": "ws/"}
    a1 = scope_output_storage(base, user="ou_a", topic="omt_1")
    assert a1 == {"bucket": "b", "prefix": "ws/users/ou_a/omt_1/"}
    assert scope_output_storage(base, user="ou_a", topic="omt_1") == a1  # 稳定可复现
    prefixes = {
        scope_output_storage(base, user=u, topic=t)["prefix"]
        for u in ("ou_a", "ou_b") for t in ("omt_1", "omt_2")
    }
    assert len(prefixes) == 4


@pytest.mark.parametrize("user,topic", [("", "t"), ("u", ""), ("..", "t"), ("u", " ")])
def test_scope_rejects_empty_identity(user, topic):
    with pytest.raises(ValueError):
        scope_output_storage({"bucket": "b", "prefix": "ws/"}, user=user, topic=topic)


def test_scope_cannot_escape_via_separators():
    out = scope_output_storage({"bucket": "b", "prefix": "ws/"}, user="../x", topic="a/b")
    assert out["prefix"] == "ws/users/.._x/a_b/"


async def _create(**gw_kwargs):
    ark = FakeArk()

    async def reply(chat_id, text):
        pass

    gw = Gateway(
        GatewayStore(":memory:"), ark, reply,
        agent_id="a", environment_id="e", vault_id="v", timeout_ms=5_000, **gw_kwargs,
    )
    return gw, ark


async def test_gateway_passes_unscoped_output_tos_by_default():
    gw, ark = await _create(output_tos={"bucket": "b", "prefix": "out/"})
    gw.accept(message())
    await asyncio.sleep(0.05)
    assert ark.last_output_tos == {"bucket": "b", "prefix": "out/"}


async def test_gateway_scopes_output_by_user_and_thread():
    gw, ark = await _create(output_tos={"bucket": "b", "prefix": "out/"}, scope_output_by_user_topic=True)
    gw.accept(message(thread_id="omt_9"))
    await asyncio.sleep(0.05)
    assert ark.last_output_tos == {"bucket": "b", "prefix": "out/users/user-1/omt_9/"}
