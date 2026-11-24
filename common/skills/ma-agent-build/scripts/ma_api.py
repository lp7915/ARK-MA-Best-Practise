#!/usr/bin/env python3
"""方舟 Managed Agents HTTP 封装（供 build.py 与 reconcile/* 共用）。

只做三件事：鉴权、请求、分页列表。不含任何业务逻辑，便于单测与复用。
环境变量：ARK_API_KEY（必填）、ARK_BASE_URL（默认北京区）。
"""
from __future__ import annotations

import json
import os
import sys

import requests

_raw_base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
BASE_URL = _raw_base if _raw_base.endswith("/api/v3") else f"{_raw_base}/api/v3"
ARK_BETA = "agentic-2026-06-01"


def auth_headers() -> dict:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ARK_API_KEY")
    return {"Authorization": f"Bearer {api_key}", "X-Ark-Beta": ARK_BETA, "Accept": "application/json"}


def ark_get(path: str) -> dict:
    """GET；HTTP 4xx/5xx 不抛异常，返回 {"_err": 状态码, "_body": 片段}，由调用方判断（如资源不存在）。"""
    r = requests.get(BASE_URL + path, headers=auth_headers(), timeout=90)
    if r.status_code >= 400:
        return {"_err": r.status_code, "_body": r.text[:300]}
    return r.json()


def ark_post(path: str, body: dict) -> dict:
    r = requests.post(
        BASE_URL + path,
        headers=auth_headers(),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=120,
    )
    if r.status_code >= 400:
        print(f"  [HTTP {r.status_code}] POST {path}: {r.text[:500]}", file=sys.stderr)
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


def ark_delete(path: str) -> None:
    r = requests.delete(BASE_URL + path, headers=auth_headers(), timeout=60)
    if r.status_code >= 400:
        print(f"  [HTTP {r.status_code}] DELETE {path}: {r.text[:300]}", file=sys.stderr)
        raise RuntimeError(f"HTTP {r.status_code}")


def unwrap_id(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return str(data.get("id") or data.get("agent_id") or data.get("environment_id") or "")


def unwrap_data(payload: dict) -> dict:
    """响应体里的资源对象（兼容 {"data": {...}} 与直接返回对象两种形态）。"""
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def payload_to_items(payload: dict) -> list:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(payload.get("items"), list):
        return payload["items"]
    return payload if isinstance(payload, list) else []


def list_all(collection: str, extra_query: str = "") -> list[dict]:
    """分页拉取某集合全量（如 agents / environments / vaults / memory_stores）。失败返回已拉取部分。"""
    out: list[dict] = []
    page = ""
    while True:
        q = "?page_size=200" + (f"&{extra_query}" if extra_query else "") + (f"&page={page}" if page else "")
        body = ark_get(f"/{collection}{q}")
        if isinstance(body, dict) and "_err" in body:
            break
        out.extend(payload_to_items(body))
        nxt = body.get("next_page") if isinstance(body, dict) else None
        if not nxt:
            break
        page = nxt
    return out


def find_by_name(collection: str, name: str) -> str | None:
    """按 name / display_name 精确匹配，返回资源 ID。MA 的列表接口不支持 metadata 过滤，只能全量比对。"""
    for it in list_all(collection):
        if it.get("name") == name or it.get("display_name") == name:
            return str(it.get("id") or "")
    return None
