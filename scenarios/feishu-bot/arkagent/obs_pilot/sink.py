"""方案 B 的上报出口：把规范记录追加写入本机 Pilot 的 claude-code 输入目录。

Pilot 的 hook-jsonl 输入只轮询固定路径 `$PILOT_DATA/logs/<agent-id>/<prefix>-YYYY-MM-DD.jsonl`，
按字节偏移增量读取。本模块只负责「把转好的记录落到那个目录」，不做转换（转换见 converter.py）。

前提（部署侧）：
  - Pilot 以 `deployMode: detection-only` 定义 claude-code，只读文件、不往 Agent 配置注入 hook；
  - 数据目录由 `$PILOT_DATA` 指定，默认 `~/.loongsuite-pilot`；
  - 单写者：一个网关进程独占写入，不并发抢同一文件。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

AGENT_ID = "claude-code"
FILE_PREFIX = "claude-code"
_RETENTION_DAYS = 2  # 只清自己写的、超过这个天数的旧文件；Pilot 自己也有 retention


def pilot_data_dir() -> Path:
    """Pilot 数据目录。与 Pilot 服务读的 `$PILOT_DATA`/`~/.loongsuite-pilot` 保持一致。"""
    raw = (os.environ.get("LOONGSUITE_PILOT_DATA_DIR") or "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".loongsuite-pilot"


def input_dir() -> Path:
    return pilot_data_dir() / "logs" / AGENT_ID


def _prune(directory: Path, keep_days: int) -> None:
    cutoff = datetime.now().timestamp() - keep_days * 86400
    for path in directory.glob(f"{FILE_PREFIX}-*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass  # 清理失败不影响上报


def write_records(records: Iterable[dict], *, data_dir: Optional[Path] = None) -> int:
    """追加写入当天文件，返回写入条数。空列表直接返回 0，不创建文件。"""
    records = list(records)
    if not records:
        return 0
    directory = Path(data_dir) / "logs" / AGENT_ID if data_dir else input_dir()
    directory.mkdir(parents=True, exist_ok=True)
    _prune(directory, _RETENTION_DAYS)
    target = directory / f"{FILE_PREFIX}-{datetime.now().date().isoformat()}.jsonl"
    with target.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)
