from arkagent.store import ConversationKey, GatewayStore


def _key(user="ou-user"):
    return ConversationKey(tenant_key="tenant", chat_id="chat", thread_id="", user_open_id=user)


def _store():
    return GatewayStore(":memory:")


def test_conversation_key_includes_all_identity_fields():
    store = _store()
    # tenant_key 已降级为归属属性，不再进会话键（chat_id 全局唯一）。
    key = ConversationKey(tenant_key="t", chat_id="c", thread_id="th", user_open_id="ou")
    assert store.conversation_key(key) == "c:th:ou"
    empty = ConversationKey(tenant_key="t", chat_id="c", thread_id="", user_open_id="")
    assert store.conversation_key(empty) == "c:-:-"


def test_session_roundtrip_and_reset():
    store = _store()
    key = _key()
    assert store.get_session(key) is None
    store.save_session(key, "sess-1", "agent-1", "v1")
    assert store.get_session(key) == "sess-1"
    store.reset_session(key)
    assert store.get_session(key) is None


def test_reset_all_sessions_returns_row_count():
    store = _store()
    store.save_session(_key("ou-a"), "s1", "agent-1")
    store.save_session(_key("ou-b"), "s2", "agent-1")
    assert store.reset_all_sessions() == 2


def test_claim_event_is_idempotent():
    store = _store()
    assert store.claim_event("evt-1") is True
    assert store.claim_event("evt-1") is False


def test_role_cache_upsert_and_injection_flags():
    store = _store()
    assert store.get_role("ou-1") is None
    row = store.upsert_role("ou-1", {"title": "销售经理"}, refreshed_at=1000)
    assert row.role == {"title": "销售经理"}
    assert row.injected_for_session is None

    store.mark_injected("ou-1", "sess-9")
    assert store.get_role("ou-1").injected_for_session == "sess-9"

    store.clear_injection("ou-1")
    assert store.get_role("ou-1").injected_for_session is None


def test_memory_store_mapping_roundtrip():
    store = _store()
    assert store.get_memory_store_id("ou-1") is None
    store.save_memory_store_id("ou-1", "mem-1")
    assert store.get_memory_store_id("ou-1") == "mem-1"
    store.save_memory_store_id("ou-1", "mem-2")
    assert store.get_memory_store_id("ou-1") == "mem-2"


def test_team_store_mapping_roundtrip():
    store = _store()
    store.save_team_store_id("销售", "team-1")
    assert store.get_team_store_id("销售") == "team-1"


def _identity(store, key):
    return store._db.execute(
        "SELECT user_id, chat_type, created_at FROM conversations WHERE conversation_key = ?",
        (store.conversation_key(key),),
    ).fetchone()


def test_save_session_records_user_id_and_chat_type():
    store = _store()
    key = _key()
    store.save_session(key, "sess-1", "agent-1", user_id="u_alice", chat_type="p2p")
    assert _identity(store, key) == ("u_alice", "p2p", _identity(store, key)[2])  # created_at 非空
    assert _identity(store, key)[2] != ""


def test_resave_without_identity_does_not_wipe_existing_user_id():
    store = _store()
    key = _key()
    store.save_session(key, "sess-1", "agent-1", user_id="u_alice", chat_type="p2p")
    store.save_session(key, "sess-1", "agent-1")  # 同 session 重复保存、不带身份:不能清掉已记录的
    assert _identity(store, key)[:2] == ("u_alice", "p2p")


def test_resave_with_new_identity_updates_it():
    store = _store()
    key = _key()
    store.save_session(key, "sess-1", "agent-1", user_id="u_alice", chat_type="p2p")
    store.save_session(key, "sess-2", "agent-1", user_id="u_bob", chat_type="group")  # 换 session 了
    assert _identity(store, key)[:2] == ("u_bob", "group")


def test_created_at_is_stable_across_resave_of_same_session():
    store = _store()
    key = _key()
    store.save_session(key, "sess-1", "agent-1")
    before = _identity(store, key)[2]
    store.save_session(key, "sess-1", "agent-1")  # 同 session 再存:created_at 不变
    assert _identity(store, key)[2] == before


def test_legacy_table_without_new_columns_is_migrated():
    import sqlite3

    store = _store()
    # 模拟老库:删掉迁移补的列
    store._db.execute("ALTER TABLE conversations DROP COLUMN user_id")
    store._db.execute("ALTER TABLE conversations DROP COLUMN chat_type")
    store._db.execute("ALTER TABLE conversations DROP COLUMN created_at")
    store._db.commit()
    # 重新打开同一 :memory: 不可行,这里只验证迁移逻辑在初始化时执行——用一个真实文件库验证
    import tempfile, pathlib

    path = str(pathlib.Path(tempfile.mkdtemp()) / "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE conversations (conversation_key TEXT PRIMARY KEY, session_id TEXT NOT NULL,"
        " agent_id TEXT NOT NULL, agent_version TEXT, updated_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO conversations VALUES ('chat:-:ou-user', 'sesn-legacy', 'agent-1', NULL, '2026-01-01')")
    conn.commit()
    conn.close()
    migrated = GatewayStore(path)
    cols = {r[1] for r in migrated._db.execute("PRAGMA table_info(conversations)").fetchall()}
    assert {"user_id", "chat_type", "created_at"} <= cols
    assert migrated.get_session(_key()) == "sesn-legacy"  # 老数据仍可读
