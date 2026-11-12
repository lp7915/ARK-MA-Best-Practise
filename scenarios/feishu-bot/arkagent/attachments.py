"""飞书附件 → 方舟 Files API → Session 沙箱挂载(/mnt/session/uploads/)。

通用 Gateway 用：逐个下载消息里的图片/文件，上传方舟拿 file_id，再挂到已存在的 Session。
单个附件失败只产出一条可读提示，不影响其余附件和本轮对话。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .ark import ArkClient
    from .feishu import IncomingMessage

logger = logging.getLogger(__name__)

SESSION_UPLOAD_ROOT = "/mnt/session/uploads"
# 单轮附件总字节上限(下载 + 挂载)，超限的后续附件降级为提示；与 digital-employee 保持一致。
MAX_TOTAL_BYTES = 40 * 1024 * 1024

# (message_id, file_key, resource_type) -> bytes，同步阻塞，在线程池里执行。
Downloader = Callable[[str, str, str], bytes]


def _safe_filename(name: str, index: int) -> str:
    """去掉路径分隔符/控制字符/前导点并截断到 120 字符；清完为空则回退 attachment-N。"""
    cleaned = "".join(
        "_" if (ch in "\\/" or ord(ch) < 0x20 or ord(ch) == 0x7F) else ch for ch in (name or "")
    ).lstrip(".").strip()[:120]
    return cleaned or f"attachment-{index + 1}"


def _mount_path(file_key: str, name: str) -> str:
    """`{file_key 短哈希}/{文件名}`：同名不同文件落在不同目录，不会互相覆盖。"""
    return f"{hashlib.sha256(file_key.encode()).hexdigest()[:16]}/{name}"


async def mount_message_attachments(
    ark: "ArkClient", download: Downloader, session_id: str, message: "IncomingMessage"
) -> tuple[list[str], list[str]]:
    """把 message.resources 全部下载、上传并挂到 session_id。

    返回 (沙箱内可读路径列表, 失败提示列表)；本函数不抛异常。
    """
    loop = asyncio.get_running_loop()
    paths: list[str] = []
    notices: list[str] = []
    total = 0
    for index, ref in enumerate(message.resources):
        name = _safe_filename(ref.file_name, index)
        try:
            if total >= MAX_TOTAL_BYTES:
                raise ValueError("单轮附件总量已达 40 MB，请分批发送")
            data = await loop.run_in_executor(
                None, download, ref.message_id or message.message_id, ref.file_key, ref.type
            )
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("单轮附件总量超过 40 MB，请分批发送")
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            file_id = await ark.upload_file(name, mime, data)
            mount_path = _mount_path(ref.file_key, name)
            await ark.add_session_file(session_id, file_id, mount_path)
            paths.append(f"{SESSION_UPLOAD_ROOT}/{mount_path}")
        except Exception as error:  # noqa: BLE001 - 单个附件失败降级为提示，不拖垮本轮
            logger.warning(
                "附件处理失败 session=%s message_id=%s name=%s",
                session_id, message.message_id, name, exc_info=True,
            )
            notices.append(f"附件「{name}」未能处理：{str(error)[:120]}")
    return paths, notices


def build_attachment_note(paths: list[str], notices: list[str], *, attachments_only: bool = False) -> str:
    """拼成追加到用户消息末尾的说明，告诉 Agent 文件挂在哪、哪些没成功。

    attachments_only=True 表示用户这条消息只有附件、没有文字指令：由 Agent 结合本会话上文判断
    用户想做什么。上文已明确意图就直接处理；判断不出来时不读取、不解析文件，只简短确认收到并
    询问下一步，避免用户还没说要做什么就先输出一大段文件解读。
    """
    lines: list[str] = []
    if paths and attachments_only:
        lines.append("[用户只上传了附件，这条消息本身没有文字指令。附件已挂载到沙箱：")
        lines.extend(f"- {path}" for path in paths)
        lines.append(
            "请结合本会话之前的对话判断用户想基于这些文件做什么：上文已经明确说明意图的"
            "(例如用户先说过“我发你文档，帮我……”)，直接按该意图处理；无法确定时，"
            "不要读取、解析或总结文件内容，只用一两句话回复已收到(可列出文件名)，"
            "并询问接下来要基于这些文件做什么。]"
        )
    elif paths:
        lines.append("[用户随消息上传了附件，已挂载到沙箱，请按需读取：")
        lines.extend(f"- {path}" for path in paths)
        lines.append("]")
    lines.extend(f"[{notice}]" for notice in notices)
    return "\n".join(lines)
