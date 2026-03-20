from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from .client_status_config import ClientStatusConfig, load_client_status_config


@dataclass
class _PublishEnvelope:
    payload: dict


class NullRemoteStatusPublisher:
    enabled = False

    def publish_session(self, **kwargs):
        return None

    def close(self):
        return None


def _resolve_duration_sec(session_data, session_active):
    if session_data is None:
        return None

    try:
        duration_sec = session_data.meta.get("duration_sec")
        if duration_sec is not None:
            return max(0, int(duration_sec))

        if session_active:
            t_start_epoch_s = session_data.meta.get("t_start_epoch_s")
            if t_start_epoch_s is not None:
                return max(0, int(time.time() - float(t_start_epoch_s)))
    except Exception:
        return None

    return None


class RemoteStatusPublisher:
    def __init__(self, client_id: str, config: ClientStatusConfig):
        self.enabled = bool(config.enabled)
        self.client_id = str(client_id).strip() or "UNKNOWN_CLIENT"
        self.config = config
        self._latest = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._has_pending = threading.Event()
        self._worker = threading.Thread(target=self._loop, name="remote-status-publisher", daemon=True)
        self._worker.start()

    def publish_session(self, session_data, session_active, started, current_trial, note):
        if not self.enabled or session_data is None:
            return

        payload = {
            "client_id": self.client_id,
            "session_active": bool(session_active),
            "started": bool(started),
            "note": str(note),
            "published_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "stale_after_s": float(self.config.stale_after_s),
            "session": {
                "session_id": str(session_data.meta.get("session_id") or ""),
                "animal_id": str(session_data.meta.get("animal") or ""),
                "phase_id": str(session_data.meta.get("phase") or ""),
                "date": str(session_data.meta.get("date") or ""),
                "imaging_active": bool(session_data.meta.get("imaging_active")),
                "t_start_ms": session_data.meta.get("t_start"),
                "t_stop_ms": session_data.meta.get("t_stop"),
                "duration_sec": _resolve_duration_sec(session_data, session_active),
            },
            "trial_display": current_trial,
        }

        with self._lock:
            self._latest = _PublishEnvelope(payload=payload)

        self._has_pending.set()

    def _loop(self):
        next_heartbeat = 0.0

        while not self._stop.is_set():
            triggered = self._has_pending.wait(timeout=0.25)
            now = time.monotonic()
            should_heartbeat = now >= next_heartbeat

            if not triggered and not should_heartbeat:
                continue

            with self._lock:
                envelope = self._latest

            if envelope is None:
                continue

            if triggered:
                self._has_pending.clear()

            if self._post(envelope.payload):
                next_heartbeat = time.monotonic() + max(0.5, self.config.heartbeat_interval_s)
            else:
                next_heartbeat = time.monotonic() + max(1.0, self.config.heartbeat_interval_s)

    def _post(self, payload: dict) -> bool:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.config.base_url}/api/client-status",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Status-Api-Key": self.config.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def close(self):
        if not self.enabled:
            return

        with self._lock:
            envelope = self._latest

        if envelope is not None:
            self._post(envelope.payload)

        self._stop.set()
        self._has_pending.set()
        self._worker.join(timeout=1.5)


def build_remote_status_publisher(client_id: str):
    config = load_client_status_config()
    if not config.enabled:
        return NullRemoteStatusPublisher()

    return RemoteStatusPublisher(client_id=client_id, config=config)
