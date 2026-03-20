from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    from .config import (
        get_redis_key_prefix,
        get_redis_rest_token,
        get_redis_rest_url,
        get_redis_timeout_seconds,
        get_session_history_ttl_seconds,
        get_status_ttl_seconds,
    )
except ImportError:
    from config import (
        get_redis_key_prefix,
        get_redis_rest_token,
        get_redis_rest_url,
        get_redis_timeout_seconds,
        get_session_history_ttl_seconds,
        get_status_ttl_seconds,
    )


SESSION_HISTORY_LIMIT_PER_ANIMAL = 5


def _parse_timestamp_s(value) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return 0.0

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return float(parsed.timestamp())


def _build_session_id(client_id: str, session: dict) -> str:
    explicit = str(session.get("session_id") or "").strip()
    if explicit:
        return explicit

    animal_id = str(session.get("animal_id") or "").strip() or "UNKNOWN_ANIMAL"
    phase_id = str(session.get("phase_id") or "").strip() or "UNKNOWN_PHASE"
    date = str(session.get("date") or "").strip() or "UNKNOWN_DATE"
    t_start_ms = session.get("t_start_ms")
    if t_start_ms not in {None, ""}:
        return f"{client_id}:{animal_id}:{phase_id}:{date}:{t_start_ms}"

    return f"{client_id}:{animal_id}:{phase_id}:{date}"


def _normalize_session_dict(client_id: str, session: dict | None) -> dict:
    session_dict = dict(session or {})
    return {
        "session_id": _build_session_id(client_id, session_dict),
        "animal_id": str(session_dict.get("animal_id") or "").strip(),
        "phase_id": str(session_dict.get("phase_id") or "").strip(),
        "date": str(session_dict.get("date") or "").strip(),
        "imaging_active": bool(session_dict.get("imaging_active")),
        "t_start_ms": session_dict.get("t_start_ms"),
        "t_stop_ms": session_dict.get("t_stop_ms"),
        "duration_sec": session_dict.get("duration_sec"),
    }


def _normalize_state(payload: dict) -> dict:
    client_id = str(payload.get("client_id") or "").strip()
    if not client_id:
        raise ValueError("client_id is required")

    return {
        "client_id": client_id,
        "session_active": bool(payload.get("session_active")),
        "started": bool(payload.get("started")),
        "note": str(payload.get("note") or ""),
        "published_at": payload.get("published_at"),
        "received_at_s": float(time.time()),
        "stale_after_s": float(payload.get("stale_after_s") or 10.0),
        "session": _normalize_session_dict(client_id, payload.get("session")),
        "trial_display": payload.get("trial_display"),
    }


def _merge_dict(existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value is None or value == "":
            continue
        merged[key] = value

    return merged


def _should_track_history(state: dict) -> bool:
    session = state.get("session") or {}
    if not str(session.get("animal_id") or "").strip():
        return False
    if not str(session.get("phase_id") or "").strip():
        return False
    if not str(session.get("date") or "").strip():
        return False

    return bool(
        state.get("started")
        or state.get("session_active")
        or state.get("trial_display")
        or session.get("t_start_ms") is not None
        or session.get("duration_sec") is not None
    )


def _normalize_history_entry(state: dict) -> dict | None:
    if not _should_track_history(state):
        return None

    session = dict(state.get("session") or {})
    return {
        "session_id": str(session.get("session_id") or "").strip(),
        "client_id": str(state.get("client_id") or "").strip(),
        "session_active": bool(state.get("session_active")),
        "started": bool(state.get("started")),
        "note": str(state.get("note") or ""),
        "published_at": state.get("published_at"),
        "received_at_s": float(state.get("received_at_s") or time.time()),
        "session": session,
        "trial_display": state.get("trial_display"),
    }


def _merge_history_entry(existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    merged["session_id"] = str(incoming.get("session_id") or existing.get("session_id") or "").strip()
    merged["client_id"] = str(incoming.get("client_id") or existing.get("client_id") or "").strip()
    merged["session_active"] = bool(incoming.get("session_active"))
    merged["started"] = bool(incoming.get("started") or existing.get("started"))
    merged["note"] = str(incoming.get("note") or existing.get("note") or "")
    merged["published_at"] = incoming.get("published_at") or existing.get("published_at")
    merged["received_at_s"] = float(incoming.get("received_at_s") or existing.get("received_at_s") or time.time())
    merged["session"] = _merge_dict(existing.get("session") or {}, incoming.get("session") or {})
    merged["trial_display"] = incoming.get("trial_display")
    if merged["trial_display"] is None:
        merged["trial_display"] = existing.get("trial_display")

    return merged


def _sort_history_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda item: (
            1 if item.get("session_active") else 0,
            _parse_timestamp_s(item.get("published_at")),
            float(item.get("received_at_s") or 0.0),
        ),
        reverse=True,
    )


def _upsert_history_entries(entries: list[dict], incoming: dict) -> list[dict]:
    merged_entries: list[dict] = []
    seen = False

    for item in entries:
        if str(item.get("session_id") or "") == str(incoming.get("session_id") or ""):
            merged_entries.append(_merge_history_entry(item, incoming))
            seen = True
        else:
            merged_entries.append(item)

    if not seen:
        merged_entries.append(incoming)

    return _sort_history_entries(merged_entries)[:SESSION_HISTORY_LIMIT_PER_ANIMAL]


def _flatten_history(history_by_animal: dict[str, list[dict]]) -> list[dict]:
    sessions = []
    for entries in history_by_animal.values():
        sessions.extend(entries)

    return _sort_history_entries(sessions)


def _decode_json_list(raw_value) -> list[dict]:
    if not isinstance(raw_value, str) or not raw_value:
        return []

    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    if not isinstance(decoded, list):
        return []

    return [item for item in decoded if isinstance(item, dict)]


class InMemoryStatusStore:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._states: dict[str, dict] = {}
        self._history_by_animal: dict[str, list[dict]] = {}

    async def update(self, payload: dict):
        state = _normalize_state(payload)
        history_entry = _normalize_history_entry(state)

        async with self._lock:
            self._states[state["client_id"]] = state

            if history_entry is not None:
                animal_id = str(history_entry["session"].get("animal_id") or "").strip()
                current_entries = list(self._history_by_animal.get(animal_id, []))
                self._history_by_animal[animal_id] = _upsert_history_entries(current_entries, history_entry)

    async def snapshot(self, client_ids: list[str] | None = None):
        async with self._lock:
            return {
                "states": dict(self._states),
                "sessions": _flatten_history(dict(self._history_by_animal)),
            }


class UpstashRedisClient:
    def __init__(self, base_url: str, token: str, timeout_s: float):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s

    def _request(self, path: str, payload) -> object:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Upstash request failed with HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Upstash request failed: {exc}") from exc

    def command(self, *parts: object):
        response = self._request("", list(parts))
        if isinstance(response, dict) and "error" in response:
            raise RuntimeError(str(response["error"]))
        return response

    def pipeline(self, commands: list[list[object]]):
        response = self._request("/pipeline", commands)
        if not isinstance(response, list):
            raise RuntimeError(f"Unexpected Upstash pipeline response: {response!r}")
        return response


class RedisStatusStore:
    def __init__(self):
        key_prefix = get_redis_key_prefix()
        self._client = UpstashRedisClient(
            base_url=get_redis_rest_url(),
            token=get_redis_rest_token(),
            timeout_s=get_redis_timeout_seconds(),
        )
        self._client_set_key = f"{key_prefix}:clients"
        self._status_key_prefix = f"{key_prefix}:client:"
        self._history_animals_key = f"{key_prefix}:history:animals"
        self._history_key_prefix = f"{key_prefix}:history:animal:"
        self._ttl_s = get_status_ttl_seconds()
        self._history_ttl_s = get_session_history_ttl_seconds()

    def _status_key(self, client_id: str) -> str:
        return f"{self._status_key_prefix}{client_id}"

    def _history_key(self, animal_id: str) -> str:
        return f"{self._history_key_prefix}{animal_id}"

    async def update(self, payload: dict):
        state = _normalize_state(payload)
        client_id = state["client_id"]
        commands = [
            ["SET", self._status_key(client_id), json.dumps(state), "EX", self._ttl_s],
            ["SADD", self._client_set_key, client_id],
        ]

        history_entry = _normalize_history_entry(state)
        if history_entry is not None:
            animal_id = str(history_entry["session"].get("animal_id") or "").strip()
            existing_response = self._client.command("GET", self._history_key(animal_id))
            existing_entries = []
            if isinstance(existing_response, dict):
                existing_entries = _decode_json_list(existing_response.get("result"))

            merged_entries = _upsert_history_entries(existing_entries, history_entry)
            history_set_command = ["SET", self._history_key(animal_id), json.dumps(merged_entries)]
            if self._history_ttl_s > 0:
                history_set_command.extend(["EX", self._history_ttl_s])

            commands.extend([
                history_set_command,
                ["SADD", self._history_animals_key, animal_id],
            ])

        self._client.pipeline(commands)

    async def snapshot(self, client_ids: list[str] | None = None):
        configured_ids = {
            str(client_id).strip()
            for client_id in (client_ids or [])
            if str(client_id).strip()
        }

        known_response = self._client.command("SMEMBERS", self._client_set_key)
        known_ids = set()
        if isinstance(known_response, dict):
            known_ids = {
                str(item).strip()
                for item in (known_response.get("result") or [])
                if str(item).strip()
            }

        all_ids = sorted(configured_ids | known_ids)
        states: dict[str, dict] = {}
        if all_ids:
            results = self._client.pipeline([["GET", self._status_key(client_id)] for client_id in all_ids])
            for client_id, item in zip(all_ids, results):
                if not isinstance(item, dict) or item.get("result") in {None, ""}:
                    continue

                raw_state = item["result"]
                if not isinstance(raw_state, str):
                    continue

                try:
                    decoded = json.loads(raw_state)
                except json.JSONDecodeError:
                    continue

                if isinstance(decoded, dict):
                    states[client_id] = decoded

        history_animals_response = self._client.command("SMEMBERS", self._history_animals_key)
        animal_ids = []
        if isinstance(history_animals_response, dict):
            animal_ids = sorted(
                str(item).strip()
                for item in (history_animals_response.get("result") or [])
                if str(item).strip()
            )

        history_by_animal: dict[str, list[dict]] = {}
        if animal_ids:
            results = self._client.pipeline([["GET", self._history_key(animal_id)] for animal_id in animal_ids])
            for animal_id, item in zip(animal_ids, results):
                if not isinstance(item, dict) or item.get("result") in {None, ""}:
                    continue
                history_by_animal[animal_id] = _decode_json_list(item.get("result"))

        return {
            "states": states,
            "sessions": _flatten_history(history_by_animal),
        }


def build_status_store():
    if get_redis_rest_url() and get_redis_rest_token():
        return RedisStatusStore()

    return InMemoryStatusStore()
