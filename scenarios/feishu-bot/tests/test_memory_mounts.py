import pytest

from arkagent.memory_mounts import build_memory_resources, parse_memory_stores


def test_parse_defaults_to_read_only_per_store():
    raw = "mem-1, mem-2:read_write\nmem-3:read_only"
    assert parse_memory_stores(raw) == (("mem-1", "read_only"), ("mem-2", "read_write"), ("mem-3", "read_only"))
    assert parse_memory_stores("") == ()


@pytest.mark.parametrize("raw", [":read_only", "mem-1:rw", "mem-1:", "mem-1:read_only,mem-1:read_write"])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_memory_stores(raw)


def test_parse_dedupes_identical_entries():
    assert parse_memory_stores("mem-1:read_only,mem-1:read_only") == (("mem-1", "read_only"),)


def test_build_resources_always_carries_explicit_access():
    assert build_memory_resources((("mem-1", "read_only"), ("mem-2", "read_write"))) == [
        {"type": "memory_store", "memory_store_id": "mem-1", "access": "read_only"},
        {"type": "memory_store", "memory_store_id": "mem-2", "access": "read_write"},
    ]
