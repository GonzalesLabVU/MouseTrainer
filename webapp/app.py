from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

try:
    from .config import PUBLIC_DIR, get_stale_after_seconds, get_status_api_key, load_clients_config, load_ui_config
    from .status_store import build_status_store
except ImportError:
    from config import PUBLIC_DIR, get_stale_after_seconds, get_status_api_key, load_clients_config, load_ui_config
    from status_store import build_status_store


class TrialDisplayModel(BaseModel):
    labels: list[str] = Field(default_factory=list)
    columns: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, object] = Field(default_factory=dict)
    rows: list[dict[str, str]] = Field(default_factory=list)


class SessionModel(BaseModel):
    session_id: str = ""
    animal_id: str = ""
    phase_id: str = ""
    date: str = ""
    imaging_active: bool = False
    t_start_ms: int | None = None
    t_stop_ms: int | None = None
    duration_sec: int | None = None


class ClientStatusUpdate(BaseModel):
    client_id: str
    session_active: bool
    started: bool = False
    note: str = ""
    published_at: str
    stale_after_s: float | None = None
    session: SessionModel
    trial_display: TrialDisplayModel | None = None


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()


def _read_public_asset(filename: str, fallback: str) -> str:
    asset_path = Path(PUBLIC_DIR) / filename
    try:
        return asset_path.read_text(encoding="utf-8")
    except OSError:
        return fallback


INDEX_HTML = _read_public_asset(
    "index.html",
    """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gonzales Lab Behavior Training</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <main class="page">
    <header class="hero">
      <div class="hero-row">
        <h1 id="site-title">Gonzales Lab Behavior Training</h1>
        <div class="hero-status" aria-live="polite">
          <p class="subtitle-key">Last active session:</p>
          <p id="site-subtitle" class="subtitle-value">--</p>
        </div>
      </div>
    </header>

    <section class="panel">
      <div class="panel-header">
        <div class="panel-session-meta">
          <div class="session-feature">
            <div class="session-feature-heading">
              <p class="session-feature-label">Animal</p>
              <button
                id="session-animal-arrow"
                class="session-feature-arrow"
                type="button"
                aria-haspopup="listbox"
                aria-expanded="false"
                aria-controls="session-animal-menu"
                aria-label="Select animal"
              >
                &#9662;
              </button>
            </div>
            <p id="session-animal" class="session-feature-value">-</p>
            <div id="session-animal-menu" class="session-dropdown" role="listbox" hidden></div>
          </div>

          <div class="session-feature">
            <div class="session-feature-heading">
              <p class="session-feature-label">Phase</p>
              <button
                id="session-phase-arrow"
                class="session-feature-arrow"
                type="button"
                aria-haspopup="listbox"
                aria-expanded="false"
                aria-controls="session-phase-menu"
                aria-label="Select phase"
              >
                &#9662;
              </button>
            </div>
            <p id="session-phase" class="session-feature-value">-</p>
            <div id="session-phase-menu" class="session-dropdown" role="listbox" hidden></div>
          </div>

          <div class="session-feature">
            <div class="session-feature-heading">
              <p class="session-feature-label">Date</p>
              <button
                id="session-date-arrow"
                class="session-feature-arrow"
                type="button"
                aria-haspopup="listbox"
                aria-expanded="false"
                aria-controls="session-date-menu"
                aria-label="Select date"
              >
                &#9662;
              </button>
            </div>
            <p id="session-date" class="session-feature-value">-</p>
            <div id="session-date-menu" class="session-dropdown" role="listbox" hidden></div>
          </div>

          <div id="session-client-feature" class="session-feature" hidden>
            <div class="session-feature-heading">
              <p class="session-feature-label">Client</p>
            </div>
            <p id="session-client" class="session-feature-value">-</p>
          </div>
        </div>

        <div id="tab-list" class="tabs" role="tablist" aria-label="Training setups"></div>
      </div>

      <div class="panel-body">
        <p id="panel-empty-state" class="panel-empty">No active sessions</p>

        <div id="session-view" class="session-view" hidden>
          <div class="session-meta">
            <div class="session-time" aria-live="polite">
              <p class="session-time-label">Time Elapsed</p>
              <p id="session-time-elapsed" class="session-time-value">--</p>
            </div>
          </div>

          <div class="table-subpanel">
            <div class="plot-grid">
              <section class="plot-panel">
                <div class="plot-header">
                  <p class="plot-title">Trial Outcomes</p>
                  <p id="plot-mode-outcome" class="plot-mode">Last 10 Trials</p>
                </div>
                <div class="plot-frame">
                  <svg
                    id="plot-outcome"
                    class="plot-svg"
                    role="img"
                    aria-label="Trial outcomes plot"
                  ></svg>
                </div>
              </section>

              <section class="plot-panel">
                <div class="plot-header">
                  <p class="plot-title">Trial Durations</p>
                  <p id="plot-mode-duration" class="plot-mode">Last 10 Trials</p>
                </div>
                <div class="plot-frame">
                  <svg
                    id="plot-duration"
                    class="plot-svg"
                    role="img"
                    aria-label="Trial durations plot"
                  ></svg>
                </div>
              </section>

              <section class="plot-panel">
                <div class="plot-header">
                  <p class="plot-title">Net Success Rate</p>
                  <p id="plot-mode-rate" class="plot-mode">Last 10 Trials</p>
                </div>
                <div class="plot-frame">
                  <svg
                    id="plot-rate"
                    class="plot-svg"
                    role="img"
                    aria-label="Net success rate plot"
                  ></svg>
                </div>
              </section>
            </div>
            <p id="table-placeholder" class="table-placeholder" hidden>Waiting for trial data</p>
          </div>
        </div>
      </div>
    </section>
  </main>

  <script src="/app.js" defer></script>
</body>
</html>
""",
)

APP_JS = _read_public_asset(
    "app.js",
    """async function bootstrap(){const el=document.getElementById("panel-empty-state");if(el){el.textContent="Frontend asset load failed";}}bootstrap();""",
)

APP_CSS = _read_public_asset(
    "app.css",
    """body{font-family:Georgia,serif;padding:24px;}""",
)


app = FastAPI(title="MouseTrainer Status Web App")
store = build_status_store()


@app.get("/")
async def index():
    return HTMLResponse(INDEX_HTML)


@app.get("/static/index.html", include_in_schema=False)
async def static_index():
    return HTMLResponse(INDEX_HTML)


@app.get("/app.js", include_in_schema=False)
async def app_javascript():
    return Response(content=APP_JS, media_type="application/javascript; charset=utf-8")


@app.get("/static/app.js", include_in_schema=False)
async def static_app_javascript():
    return Response(content=APP_JS, media_type="application/javascript; charset=utf-8")


@app.get("/app.css", include_in_schema=False)
async def app_stylesheet():
    return Response(content=APP_CSS, media_type="text/css; charset=utf-8")


@app.get("/static/app.css", include_in_schema=False)
async def static_app_stylesheet():
    return Response(content=APP_CSS, media_type="text/css; charset=utf-8")


@app.get("/api/bootstrap")
async def bootstrap():
    return {
        "ui": load_ui_config(),
        "clients": load_clients_config(),
    }


@app.get("/api/status")
async def status():
    configured_clients = load_clients_config()
    configured_by_id = {str(item.get("client_id", "")).strip(): item for item in configured_clients}
    snapshot = await store.snapshot(list(configured_by_id))
    state = snapshot.get("states") or {}
    history_sessions = snapshot.get("sessions") or []

    clients = []
    active_session_ids = set()
    for client_id, config in configured_by_id.items():
        current = dict(state.get(client_id, {}))
        stale_after = float(current.get("stale_after_s", get_stale_after_seconds()))
        is_stale = (time.time() - float(current.get("received_at_s", 0.0))) > stale_after if current else True
        session_active = bool(current.get("session_active")) and not is_stale
        session = dict(current.get("session") or {})
        session_id = str(session.get("session_id") or "").strip()
        if session_active and session_id:
            active_session_ids.add(session_id)

        clients.append({
            "client_id": client_id,
            "label": str(config.get("label") or client_id),
            "description": str(config.get("description") or ""),
            "session_active": session_active,
            "is_stale": is_stale,
            "started": bool(current.get("started")),
            "note": str(current.get("note") or ""),
            "published_at": current.get("published_at"),
            "session": session,
            "trial_display": current.get("trial_display"),
        })

    for client_id, current in state.items():
        if client_id in configured_by_id:
            continue

        stale_after = float(current.get("stale_after_s", get_stale_after_seconds()))
        is_stale = (time.time() - float(current.get("received_at_s", 0.0))) > stale_after
        session = dict(current.get("session") or {})
        session_id = str(session.get("session_id") or "").strip()
        session_active = bool(current.get("session_active")) and not is_stale
        if session_active and session_id:
            active_session_ids.add(session_id)

        clients.append({
            "client_id": client_id,
            "label": client_id,
            "description": "Discovered from client publisher",
            "session_active": session_active,
            "is_stale": is_stale,
            "started": bool(current.get("started")),
            "note": str(current.get("note") or ""),
            "published_at": current.get("published_at"),
            "session": session,
            "trial_display": current.get("trial_display"),
        })

    client_labels = {
        str(client.get("client_id") or "").strip(): str(client.get("label") or client.get("client_id") or "").strip()
        for client in clients
    }
    sessions = []
    for item in history_sessions:
        if not isinstance(item, dict):
            continue

        session = dict(item.get("session") or {})
        client_id = str(item.get("client_id") or "").strip()
        session_id = str(item.get("session_id") or session.get("session_id") or "").strip()
        if not session_id:
            continue

        sessions.append({
            "session_id": session_id,
            "client_id": client_id,
            "client_label": client_labels.get(client_id, client_id),
            "session_active": session_id in active_session_ids,
            "started": bool(item.get("started")),
            "note": str(item.get("note") or ""),
            "published_at": item.get("published_at"),
            "session": session,
            "trial_display": item.get("trial_display"),
        })

    return {
        "clients": clients,
        "sessions": sessions,
    }


@app.post("/api/client-status")
async def client_status_update(
    payload: ClientStatusUpdate,
    x_status_api_key: str | None = Header(default=None),
):
    expected = get_status_api_key()
    if expected and x_status_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        await store.update({
            "client_id": payload.client_id,
            "session_active": bool(payload.session_active),
            "started": bool(payload.started),
            "note": payload.note,
            "published_at": payload.published_at,
            "stale_after_s": float(payload.stale_after_s or get_stale_after_seconds()),
            "session": _model_to_dict(payload.session),
            "trial_display": None if payload.trial_display is None else _model_to_dict(payload.trial_display),
        })
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"ok": True}
