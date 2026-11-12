"""analyst case 的配置:飞书凭据 + 分析师 Agent/Environment/Vault/Memory + 产物存储 + BYOK 鉴权头。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from arkagent.memory_mounts import parse_memory_stores
from arkagent.tos_mounts import build_output_storage

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
    # 挂载的 Memory Store：(store_id, access)，逐个配置，未写权限的默认 read_only。
    memory_stores: tuple[tuple[str, str], ...]
    # 产物存储基础位置（覆写 config.tos）：bucket + prefix；None 表示沿用 Environment 的配置。
    # 实际写入 users/<分析师>/<Topic>/ 子前缀，见 scope_output_storage。
    output_tos: Optional[dict]
    authorized_open_ids: tuple[str, ...]
    # BYOK Direct：按请求以 X-User-Model-Header-{name} 附加；两者均为空则不附加。
    model_auth_header_name: str = ""
    model_auth_header_value: str = ""
    # 方案 B 观测上报开关：开启后每轮结束把 Session 事件流转成 Pilot 记录，落到本机 Pilot 输入目录。
    obs_pilot_enabled: bool = False

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
    try:
        memory_stores = parse_memory_stores(environ.get("ANALYST_MEMORY_STORES") or "")
    except ValueError as error:
        raise RuntimeError(f"ANALYST_MEMORY_STORES 配置错误:{error}") from error
    out_bucket = (environ.get("ANALYST_OUTPUT_TOS_BUCKET") or "").strip()
    out_prefix = (environ.get("ANALYST_OUTPUT_TOS_PREFIX") or "").strip()
    output_tos = None
    if out_bucket or out_prefix:
        try:
            output_tos = build_output_storage(out_bucket, out_prefix)
        except ValueError as error:
            raise RuntimeError(f"ANALYST_OUTPUT_TOS_* 配置错误:{error}") from error
    header_name = (environ.get("BYOK_MODEL_AUTH_HEADER_NAME") or "").strip()
    header_value = (environ.get("BYOK_MODEL_AUTH_HEADER_VALUE") or "").strip()
    if bool(header_name) != bool(header_value):
        raise RuntimeError("BYOK_MODEL_AUTH_HEADER_NAME 与 BYOK_MODEL_AUTH_HEADER_VALUE 必须同时填写或同时留空")
    return AnalystConfig(
        ark_api_key=environ["ARK_API_KEY"],
        ark_base_url=(environ.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
        feishu_app_id=environ["FEISHU_APP_ID"],
        feishu_app_secret=environ["FEISHU_APP_SECRET"],
        agent_id=environ["ANALYST_AGENT_ID"].strip(),
        environment_id=environ["ANALYST_ENVIRONMENT_ID"].strip(),
        vault_id=(environ.get("ANALYST_VAULT_ID") or "").strip(),
        memory_stores=memory_stores,
        output_tos=output_tos,
        authorized_open_ids=tuple(
            i.strip()
            for i in (environ.get("AUTHORIZED_OPEN_IDS") or "").replace(",", " ").split()
            if i.strip()
        ),
        model_auth_header_name=header_name,
        model_auth_header_value=header_value,
        obs_pilot_enabled=(environ.get("OBS_PILOT_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on"),
    )
