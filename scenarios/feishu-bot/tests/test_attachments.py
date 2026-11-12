import asyncio

from arkagent.attachments import build_attachment_note, mount_message_attachments
from arkagent.feishu import ResourceRef
from arkagent.gateway import should_handle_message
from arkagent.store import GatewayStore
from test_gateway import FakeArk, _gateway, message


class AttachmentArk(FakeArk):
    def __init__(self, fail_upload_for=()):
        super().__init__()
        self.uploads = []
        self.mounts = []
        self.last_text = None
        self._fail_upload_for = set(fail_upload_for)

    async def upload_file(self, name, mime, data):
        if name in self._fail_upload_for:
            raise RuntimeError("上传被拒")
        self.uploads.append((name, mime, data))
        return f"file-{len(self.uploads)}"

    async def add_session_file(self, session_id, file_id, mount_path):
        self.mounts.append((session_id, file_id, mount_path))

    async def run(self, session_id, text, timeout_ms, **kwargs):
        self.last_text = text
        return await super().run(session_id, text, timeout_ms, **kwargs)


def _ref(key, name, type="file"):
    return ResourceRef(file_key=key, file_name=name, type=type, message_id="om-1")


def _download(message_id, file_key, resource_type):
    return f"bytes-of-{file_key}".encode()


def test_attachment_only_message_is_handled():
    # 回归:纯文件/图片消息没有正文,曾因 text 为空被直接丢弃。
    assert should_handle_message(message(text="", resources=(_ref("fk-1", "a.pdf"),))) is True
    assert should_handle_message(message(text="", resources=())) is False


async def test_mount_uploads_and_mounts_each_attachment():
    ark = AttachmentArk()
    msg = message(resources=(_ref("fk-1", "a.pdf"), _ref("fk-2", "b.png", "image")))

    paths, notices = await mount_message_attachments(ark, _download, "sess-1", msg)

    assert notices == []
    assert [u[0] for u in ark.uploads] == ["a.pdf", "b.png"]
    assert ark.uploads[0][1] == "application/pdf"
    assert [m[0] for m in ark.mounts] == ["sess-1", "sess-1"]
    assert all(p.startswith("/mnt/session/uploads/") for p in paths)
    assert paths[0].endswith("/a.pdf") and paths[1].endswith("/b.png")


async def test_one_failed_attachment_does_not_block_others():
    ark = AttachmentArk(fail_upload_for={"bad.pdf"})
    msg = message(resources=(_ref("fk-1", "bad.pdf"), _ref("fk-2", "ok.pdf")))

    paths, notices = await mount_message_attachments(ark, _download, "sess-1", msg)

    assert len(paths) == 1 and paths[0].endswith("/ok.pdf")
    assert len(notices) == 1 and "bad.pdf" in notices[0] and "上传被拒" in notices[0]


def test_safe_filename_blocks_path_traversal():
    from arkagent.attachments import _safe_filename

    assert "/" not in _safe_filename("../../etc/passwd", 0)
    assert not _safe_filename("../x", 0).startswith(".")
    assert _safe_filename("", 2) == "attachment-3"


def test_note_lists_paths_and_failures():
    note = build_attachment_note(["/mnt/session/uploads/h/a.pdf"], ["附件「b」未能处理：x"])
    assert "/mnt/session/uploads/h/a.pdf" in note and "附件「b」未能处理：x" in note
    assert build_attachment_note([], []) == ""


async def test_gateway_mounts_attachment_and_tells_agent_the_path():
    store = GatewayStore(":memory:")
    ark = AttachmentArk()
    replies: list[str] = []
    gw = _gateway(store, ark, replies, download_resource=_download)

    gw.accept(message(text="帮我看下这个文件", resources=(_ref("fk-1", "a.pdf"),)))
    await asyncio.sleep(0.1)

    assert len(ark.mounts) == 1
    assert ark.mounts[0][0] == "session-1"  # 挂到刚创建的 Session
    assert ark.last_text.startswith("帮我看下这个文件")
    assert "/mnt/session/uploads/" in ark.last_text and "a.pdf" in ark.last_text


async def test_gateway_handles_attachment_only_message():
    store = GatewayStore(":memory:")
    ark = AttachmentArk()
    replies: list[str] = []
    gw = _gateway(store, ark, replies, download_resource=_download)

    assert gw.accept(message(text="", resources=(_ref("fk-1", "a.pdf"),))) is True
    await asyncio.sleep(0.1)

    assert ark.runs == 1
    assert "a.pdf" in ark.last_text
    # 只有附件时由 Agent 结合上文判断意图;判断不出来就只确认并询问下一步,不解读文件。
    assert "结合本会话之前的对话判断" in ark.last_text
    assert "不要读取、解析或总结文件内容" in ark.last_text
    assert "询问接下来要基于这些文件做什么" in ark.last_text


async def test_gateway_does_not_suppress_reading_when_user_gave_instruction():
    store = GatewayStore(":memory:")
    ark = AttachmentArk()
    gw = _gateway(store, ark, [], download_resource=_download)

    gw.accept(message(text="总结这个文件", resources=(_ref("fk-1", "a.pdf"),)))
    await asyncio.sleep(0.1)

    assert "不要读取" not in ark.last_text
    assert "请按需读取" in ark.last_text


async def test_gateway_without_downloader_ignores_attachment_only_message():
    # 其它 case(如 ada-pm)没配下载器:纯附件消息没有可发给 Agent 的内容,保持原行为不处理。
    store = GatewayStore(":memory:")
    ark = AttachmentArk()
    gw = _gateway(store, ark, [])

    assert gw.accept(message(text="", resources=(_ref("fk-1", "a.pdf"),))) is False
    assert ark.runs == 0
