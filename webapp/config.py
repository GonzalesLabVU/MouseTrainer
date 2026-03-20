from __future__ import annotations

import json
import os
from pathlib import Path


WEBAPP_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = WEBAPP_ROOT / "config"
PUBLIC_DIR = WEBAPP_ROOT / "public"

CLIENTS_CONFIG_PATH = CONFIG_DIR / "clients.json"
CLIENTS_EXAMPLE_PATH = CONFIG_DIR / "clients.example.json"
UI_CONFIG_PATH = CONFIG_DIR / "ui.json"
UI_EXAMPLE_PATH = CONFIG_DIR / "ui.example.json"


def _load_json(path: Path, fallback: Path | None = None) -> dict:
    target = path if path.exists() else fallback
    if target is None or not target.exists():
        return {}

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data if isinstance(data, dict) else {}


def load_clients_config() -> list[dict]:
    data = _load_json(CLIENTS_CONFIG_PATH, CLIENTS_EXAMPLE_PATH)
    clients = data.get("clients", [])
    return clients if isinstance(clients, list) else []


def load_ui_config() -> dict:
    data = _load_json(UI_CONFIG_PATH, UI_EXAMPLE_PATH)
    return {
        "site_title": str(data.get("site_title", "Behavioral Training")),
        "site_subtitle": str(data.get("site_subtitle", "Live session status across training setups")),
        "refresh_ms": int(data.get("refresh_ms", 1000)),
    }


def get_status_api_key() -> str:
    return str(os.getenv("WEBAPP_STATUS_API_KEY", "")).strip()


def get_stale_after_seconds(default=10.0) -> float:
    try:
        return float(os.getenv("WEBAPP_STATUS_STALE_AFTER_S", default))
    except Exception:
        return float(default)


def get_redis_rest_url() -> str:
    return str(
        os.getenv("KV_REST_API_URL")
        or os.getenv("UPSTASH_REDIS_REST_URL")
        or ""
    ).strip().rstrip("/")


def get_redis_rest_token() -> str:
    return str(
        os.getenv("KV_REST_API_TOKEN")
        or os.getenv("UPSTASH_REDIS_REST_TOKEN")
        or ""
    ).strip()


def get_redis_timeout_seconds(default=2.0) -> float:
    try:
        return float(os.getenv("WEBAPP_REDIS_TIMEOUT_S", default))
    except Exception:
        return float(default)


def get_status_ttl_seconds(default=86400) -> int:
    try:
        return max(60, int(float(os.getenv("WEBAPP_STATUS_TTL_S", default))))
    except Exception:
        return int(default)


def get_session_history_ttl_seconds(default=0) -> int:
    try:
        return max(0, int(float(os.getenv("WEBAPP_SESSION_HISTORY_TTL_S", default))))
    except Exception:
        return int(default)


def get_redis_key_prefix() -> str:
    return str(os.getenv("WEBAPP_REDIS_KEY_PREFIX", "mousetrainer:status")).strip().strip(":")
