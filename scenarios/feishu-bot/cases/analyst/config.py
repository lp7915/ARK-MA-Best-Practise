"""analyst case 的配置:飞书凭据 + 分析师 Agent/Environment/Vault/Memory + TOS 挂载 + BYOK 鉴权头。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from arkagent.tos_mounts import parse_tos_mounts

REQUIRED_KEYS = [
    "ARK_API_KEY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "ANALYST_AGENT_ID",
    "ANALYST_ENVIRONMENT_ID",
]


@dataclass(frozen=True)
class AnalystConfig:
    ark_api_key: str
    ark_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    agent_id: str
    environment_id: str
    vault_id: str
    memory_store_id: str
    # 所有用户、所有 Session 一致的 TOS 目录 (bucket, key)，沙箱内见 /mnt/session/storage/。
    tos_mounts: tuple[tuple[str, str], ...]
    authorized_open_ids: tuple[str, ...]
    session_timeout_ms: int
    # BYOK Direct：按请求以 X-User-Model-Header-{name} 附加；两者均为空则不附加。
    model_auth_header_name: str = ""
    model_auth_header_value: str = ""

    @property
    def extra_headers(self) -> Optional[dict]:
        if self.model_auth_header_name and self.model_auth_header_value:
            return {f"X-User-Model-Header-{self.model_auth_header_name}": self.model_auth_header_value}
        return None


def load_case_config(env: Optional[Mapping[str, str]] = None) -> AnalystConfig:
    environ = os.environ if env is None else env
    missing = [k for k in REQUIRED_KEYS if not (environ.get(k) or "").strip()]
    if missing:
        raise RuntimeError(f"缺少环境变量:{', '.join(missing)}")
    header_name = (environ.get("BYOK_MODEL_AUTH_HEADER_NAME") or "").strip()
    header_value = (environ.get("BYOK_MODEL_AUTH_HEADER_VALUE") or "").strip()
    if bool(header_name) != bool(header_value):
        raise RuntimeError("BYOK_MODEL_AUTH_HEADER_NAME 与 BYOK_MODEL_AUTH_HEADER_VALUE 必须同时填写或同时留空")
    timeout_ms = int(environ.get("ANALYST_SESSION_TIMEOUT_MS") or "600000")
    if timeout_ms <= 0:
        raise RuntimeError("ANALYST_SESSION_TIMEOUT_MS 必须大于 0")
    try:
        tos_mounts = parse_tos_mounts(environ.get("ANALYST_TOS_MOUNTS") or "")
    except ValueError as error:
        raise RuntimeError(f"ANALYST_TOS_MOUNTS 配置错误:{error}") from error
    return AnalystConfig(
        ark_api_key=environ["ARK_API_KEY"],
        ark_base_url=(environ.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
        feishu_app_id=environ["FEISHU_APP_ID"],
        feishu_app_secret=environ["FEISHU_APP_SECRET"],
        agent_id=environ["ANALYST_AGENT_ID"].strip(),
        environment_id=environ["ANALYST_ENVIRONMENT_ID"].strip(),
        vault_id=(environ.get("ANALYST_VAULT_ID") or "").strip(),
        memory_store_id=(environ.get("ANALYST_MEMORY_STORE_ID") or "").strip(),
        tos_mounts=tos_mounts,
        authorized_open_ids=tuple(
            i.strip()
            for i in (environ.get("AUTHORIZED_OPEN_IDS") or "").replace(",", " ").split()
            if i.strip()
        ),
        session_timeout_ms=timeout_ms,
        model_auth_header_name=header_name,
        model_auth_header_value=header_value,
    )
