from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import resolve_config_path


REMOTE_STATUS_CONFIG_PATH = resolve_config_path("remote_status.json")


@dataclass(frozen=True)
class ClientStatusConfig:
    enabled: bool
    base_url: str
    api_key: str
    timeout_s: float
    heartbeat_interval_s: float
    stale_after_s: float


def _to_bool(value, default=False):
    if value is None:
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value, default):
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data if isinstance(data, dict) else {}


def load_client_status_config() -> ClientStatusConfig:
    data = _load_json(REMOTE_STATUS_CONFIG_PATH)

    enabled = _to_bool(data.get("enabled", os.getenv("REMOTE_STATUS_ENABLED")), default=False)
    base_url = str(data.get("base_url", os.getenv("REMOTE_STATUS_BASE_URL", ""))).strip().rstrip("/")
    api_key = str(data.get("api_key", os.getenv("REMOTE_STATUS_API_KEY", ""))).strip()
    timeout_s = _to_float(data.get("timeout_s", os.getenv("REMOTE_STATUS_TIMEOUT_S", 1.5)), 1.5)
    heartbeat_interval_s = _to_float(
        data.get("heartbeat_interval_s", os.getenv("REMOTE_STATUS_HEARTBEAT_S", 2.0)),
        2.0,
    )
    stale_after_s = _to_float(
        data.get("stale_after_s", os.getenv("REMOTE_STATUS_STALE_AFTER_S", 10.0)),
        10.0,
    )

    if not enabled or not base_url:
        return ClientStatusConfig(False, "", "", timeout_s, heartbeat_interval_s, stale_after_s)

    return ClientStatusConfig(True, base_url, api_key, timeout_s, heartbeat_interval_s, stale_after_s)
