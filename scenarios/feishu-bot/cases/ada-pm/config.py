"""ada-pm case 的配置:飞书凭据 + Ada PM(pm) Agent/Environment + 5 个只读知识库 + BYOK 鉴权头。"""
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
    "ADA_PM_AGENT_ID",
    "ADA_PM_ENVIRONMENT_ID",
]


@dataclass(frozen=True)
class AdaPmConfig:
    ark_api_key: str
    ark_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    agent_id: str          # pm（main）的 MA Agent ID
    environment_id: str
    # 挂载的知识库：(store_id, access)，全部 read_only；pm 与 4 个子 Agent 在会话里共享只读读取。
    memory_stores: tuple[tuple[str, str], ...]
    # 产物存储基础位置（会话级覆写 config.tos）：bucket + prefix；None 表示沿用 Environment 配置。
    # 实际落盘在 base prefix 下再按 users/<open_id>/<topic>/ 拆，见 scope_output_storage。
    output_tos: Optional[dict]
    authorized_open_ids: tuple[str, ...]
    # BYOK Direct：按请求以 X-User-Model-Header-{name} 附加；两者均为空则不附加。
    model_auth_header_name: str = ""
    model_auth_header_value: str = ""

    @property
    def extra_headers(self) -> Optional[dict]:
        if self.model_auth_header_name and self.model_auth_header_value:
            return {f"X-User-Model-Header-{self.model_auth_header_name}": self.model_auth_header_value}
        return None


def load_case_config(env: Optional[Mapping[str, str]] = None) -> AdaPmConfig:
    environ = os.environ if env is None else env
    missing = [k for k in REQUIRED_KEYS if not (environ.get(k) or "").strip()]
    if missing:
        raise RuntimeError(f"缺少环境变量:{', '.join(missing)}")
    try:
        memory_stores = parse_memory_stores(environ.get("ADA_PM_MEMORY_STORES") or "")
    except ValueError as error:
        raise RuntimeError(f"ADA_PM_MEMORY_STORES 配置错误:{error}") from error
    out_bucket = (environ.get("ADA_PM_OUTPUT_TOS_BUCKET") or "").strip()
    out_prefix = (environ.get("ADA_PM_OUTPUT_TOS_PREFIX") or "").strip()
    output_tos = None
    if out_bucket or out_prefix:
        try:
            output_tos = build_output_storage(out_bucket, out_prefix)
        except ValueError as error:
            raise RuntimeError(f"ADA_PM_OUTPUT_TOS_* 配置错误:{error}") from error
    header_name = (environ.get("BYOK_MODEL_AUTH_HEADER_NAME") or "").strip()
    header_value = (environ.get("BYOK_MODEL_AUTH_HEADER_VALUE") or "").strip()
    if bool(header_name) != bool(header_value):
        raise RuntimeError("BYOK_MODEL_AUTH_HEADER_NAME 与 BYOK_MODEL_AUTH_HEADER_VALUE 必须同时填写或同时留空")
    return AdaPmConfig(
        ark_api_key=environ["ARK_API_KEY"],
        ark_base_url=(environ.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
        feishu_app_id=environ["FEISHU_APP_ID"],
        feishu_app_secret=environ["FEISHU_APP_SECRET"],
        agent_id=environ["ADA_PM_AGENT_ID"].strip(),
        environment_id=environ["ADA_PM_ENVIRONMENT_ID"].strip(),
        memory_stores=memory_stores,
        output_tos=output_tos,
        authorized_open_ids=tuple(
            i.strip()
            for i in (environ.get("AUTHORIZED_OPEN_IDS") or "").replace(",", " ").split()
            if i.strip()
        ),
        model_auth_header_name=header_name,
        model_auth_header_value=header_value,
    )