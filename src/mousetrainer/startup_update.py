from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from .paths import CONFIG_DIR, RUNTIME_ROOT, resolve_config_path
from .version import APP_NAME, APP_VERSION


UPDATE_CONFIG_PATH = resolve_config_path("update.json")
UPDATES_DIR = RUNTIME_ROOT / ".updates"
STATE_PATH = UPDATES_DIR / "state.json"
APP_DIR = RUNTIME_ROOT / "app"
VERSIONS_DIR = APP_DIR / "versions"
ACTIVE_RELEASE_PATH = APP_DIR / "active.json"
SENSITIVE_CONFIG_NAMES = {".env", "credentials.json"}
DEFAULT_LAUNCH_EXE = "MouseTrainerClient.exe"
RELEASE_METADATA_NAME = ".release.json"


@dataclass(frozen=True)
class UpdateSettings:
    enabled: bool
    manifest_url: str
    timeout_s: float
    channel: str
    sync_config: bool
    allow_app_update: bool
    allow_launcher_update: bool
    allow_sensitive_config_sync: bool
    retain_versions: int


@dataclass(frozen=True)
class LaunchTarget:
    version: str
    release_dir: Path
    executable_path: Path
    runtime_root: Path
    launch_env: dict[str, str]


@dataclass(frozen=True)
class LaunchPreparation:
    launch_target: LaunchTarget | None
    should_exit: bool = False


@dataclass(frozen=True)
class AppReleaseSpec:
    version: str
    package_url: str
    package_sha256: str
    launch_exe: str
    bundle_dir: str


def _report(status: str, detail: str | None = None, report_status=None) -> None:
    if report_status is None:
        return

    try:
        report_status(str(status), None if detail is None else str(detail))
    except Exception:
        return


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _log(message: str) -> None:
    print(f"[startup-update] {message}")


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    # Accept UTF-8 files with or without a BOM because PowerShell-authored
    # metadata files may be emitted with BOM markers on Windows.
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    return data if isinstance(data, dict) else {}


def load_update_settings() -> UpdateSettings:
    data = _load_json_file(UPDATE_CONFIG_PATH)

    return UpdateSettings(
        enabled=_to_bool(data.get("enabled"), default=False),
        manifest_url=str(data.get("manifest_url", "")).strip(),
        timeout_s=_to_float(data.get("timeout_s"), 5.0),
        channel=str(data.get("channel", "stable")).strip() or "stable",
        sync_config=_to_bool(data.get("sync_config"), default=True),
        allow_app_update=_to_bool(data.get("allow_app_update"), default=True),
        allow_launcher_update=_to_bool(data.get("allow_launcher_update"), default=True),
        allow_sensitive_config_sync=_to_bool(data.get("allow_sensitive_config_sync"), default=False),
        retain_versions=max(1, _to_int(data.get("retain_versions"), 2)),
    )


def _ensure_updates_dir() -> None:
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _write_state(**fields: Any) -> None:
    _ensure_updates_dir()
    state = _load_json_file(STATE_PATH)
    state.update(fields)
    state["updated_at"] = _utc_now()

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json, */*",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            "Cache-Control": "no-cache",
        },
    )


def _download_json(url: str, timeout_s: float) -> dict[str, Any]:
    req = _request(url)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = resp.read().decode("utf-8")

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("update manifest must be a JSON object")

    return data


def _download_to_file(url: str, destination: Path, timeout_s: float) -> str:
    req = _request(url)
    digest = hashlib.sha256()

    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        with open(destination, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                f.write(chunk)

    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def _normalize_sha256(value: Any) -> str:
    return str(value or "").strip().lower()


def _select_manifest_channel(manifest: dict[str, Any], channel: str) -> dict[str, Any]:
    channels = manifest.get("channels")
    if not isinstance(channels, dict):
        return manifest

    selected = channels.get(channel) or channels.get("default")
    if not isinstance(selected, dict):
        raise ValueError(f"manifest channel '{channel}' is missing or invalid")

    merged = dict(manifest)
    merged.update(selected)
    merged.pop("channels", None)
    return merged


def _parse_version(value: str) -> tuple[int, ...]:
    parts = [part for part in re.split(r"[^0-9]+", value) if part]
    return tuple(int(part) for part in parts)


def _is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = _parse_version(candidate)
    current_parts = _parse_version(current)
    if candidate_parts and current_parts:
        return candidate_parts > current_parts

    return candidate.strip() != current.strip()


def _safe_config_destination(path_value: str) -> Path:
    relative_path = Path(path_value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"invalid config path in manifest: {path_value}")

    destination = (CONFIG_DIR / relative_path).resolve()
    config_root = CONFIG_DIR.resolve()
    if not destination.is_relative_to(config_root):
        raise ValueError(f"config path escapes config directory: {path_value}")

    return destination


def _safe_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    sanitized = sanitized.strip(".-")
    if not sanitized:
        raise ValueError(f"invalid release name: {value!r}")

    return sanitized


def _safe_relative_dir(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"invalid bundle directory: {value}")

    return relative


def _active_release_payload(version: str, directory_name: str, launch_exe: str, package_sha256: str = "") -> dict[str, str]:
    return {
        "version": version,
        "directory": directory_name,
        "launch_exe": launch_exe,
        "package_sha256": package_sha256,
        "activated_at": _utc_now(),
    }


def _write_active_release(version: str, directory_name: str, launch_exe: str, package_sha256: str = "") -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACTIVE_RELEASE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            _active_release_payload(version, directory_name, launch_exe, package_sha256),
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")


def _write_release_metadata(release_dir: Path, version: str, launch_exe: str, package_sha256: str = "") -> None:
    payload = {
        "version": version,
        "launch_exe": launch_exe,
        "package_sha256": package_sha256,
        "installed_at": _utc_now(),
    }
    with open(release_dir / RELEASE_METADATA_NAME, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _read_release_metadata(release_dir: Path) -> dict[str, Any]:
    return _load_json_file(release_dir / RELEASE_METADATA_NAME)


def _read_active_release() -> dict[str, Any]:
    data = _load_json_file(ACTIVE_RELEASE_PATH)
    if not data:
        return {}

    directory = str(data.get("directory", "")).strip()
    version = str(data.get("version", "")).strip()
    launch_exe = str(data.get("launch_exe", "")).strip() or DEFAULT_LAUNCH_EXE
    if not directory or not version:
        return {}

    return {
        "version": version,
        "directory": directory,
        "launch_exe": launch_exe,
        "package_sha256": _normalize_sha256(data.get("package_sha256")),
    }


def _resolve_active_release() -> LaunchTarget | None:
    active = _read_active_release()
    if active:
        release_dir = (VERSIONS_DIR / active["directory"]).resolve()
        executable_path = release_dir / active["launch_exe"]
        if release_dir.exists() and executable_path.exists():
            return LaunchTarget(
                version=active["version"],
                release_dir=release_dir,
                executable_path=executable_path,
                runtime_root=RUNTIME_ROOT.resolve(),
                launch_env=dict(os.environ),
            )

    installed: list[tuple[tuple[int, ...], Path]] = []
    for child in VERSIONS_DIR.iterdir() if VERSIONS_DIR.exists() else []:
        if not child.is_dir():
            continue
        executable_path = child / DEFAULT_LAUNCH_EXE
        if not executable_path.exists():
            continue
        installed.append((_parse_version(child.name), child.resolve()))

    if not installed:
        return None

    installed.sort(key=lambda item: item[0] or (0,), reverse=True)
    release_dir = installed[0][1]
    version = release_dir.name
    _write_active_release(version=version, directory_name=release_dir.name, launch_exe=DEFAULT_LAUNCH_EXE)
    return LaunchTarget(
        version=version,
        release_dir=release_dir,
        executable_path=release_dir / DEFAULT_LAUNCH_EXE,
        runtime_root=RUNTIME_ROOT.resolve(),
        launch_env=dict(os.environ),
    )


def _apply_config_updates(manifest: dict[str, Any], settings: UpdateSettings, report_status=None) -> list[str]:
    config_section = manifest.get("config")
    if not isinstance(config_section, dict):
        return []

    files = config_section.get("files")
    if not isinstance(files, list):
        return []

    updated_files: list[str] = []
    config_version = str(config_section.get("version", "")).strip()

    for entry in files:
        if not isinstance(entry, dict):
            continue

        relative_path = str(entry.get("path", "")).strip()
        url = str(entry.get("url", "")).strip()
        expected_sha = _normalize_sha256(entry.get("sha256"))
        if not relative_path or not url:
            continue

        destination = _safe_config_destination(relative_path)
        relative_name = Path(relative_path).name.lower()
        if relative_name in SENSITIVE_CONFIG_NAMES and not settings.allow_sensitive_config_sync:
            _log(f"skipping sensitive config sync for {relative_path}")
            _report("Updating Files", f"Skipping local-only file {relative_path}.", report_status)
            continue

        if destination.exists() and expected_sha and _hash_file(destination) == expected_sha:
            continue

        _report("Updating Files", f"Updating file {relative_path}...", report_status)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=destination.stem + "-",
            suffix=".download",
            dir=str(destination.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)

        try:
            actual_sha = _download_to_file(url, temp_path, settings.timeout_s)
            if expected_sha and actual_sha != expected_sha:
                raise ValueError(f"sha256 mismatch for {relative_path}")

            os.replace(temp_path, destination)
            updated_files.append(relative_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    if updated_files:
        _log(f"applied config update {config_version or '(unversioned)'}: {', '.join(updated_files)}")
        _report("Updating Files", f"Applied config update {config_version or 'latest'}.", report_status)
    else:
        _report("Updating Files", "Configuration files are already current.", report_status)

    return updated_files


def _extract_release_spec(manifest: dict[str, Any]) -> AppReleaseSpec | None:
    app_section = manifest.get("app")
    if not isinstance(app_section, dict):
        return None

    version = str(app_section.get("version", "")).strip()
    package_url = str(app_section.get("package_url", "")).strip()
    package_sha256 = _normalize_sha256(app_section.get("package_sha256"))
    launch_exe = str(app_section.get("launch_exe", "")).strip() or DEFAULT_LAUNCH_EXE
    bundle_dir = str(app_section.get("bundle_dir", "")).strip() or version
    if not version or not package_url:
        return None

    return AppReleaseSpec(
        version=version,
        package_url=package_url,
        package_sha256=package_sha256,
        launch_exe=launch_exe,
        bundle_dir=bundle_dir,
    )


def _stage_launcher_update(manifest: dict[str, Any], settings: UpdateSettings, report_status=None) -> bool:
    if not settings.allow_launcher_update or not getattr(sys, "frozen", False):
        return False

    launcher_section = manifest.get("launcher")
    if not isinstance(launcher_section, dict):
        return False

    target_version = str(launcher_section.get("version", "")).strip()
    launcher_url = str(launcher_section.get("url", "")).strip()
    expected_sha = _normalize_sha256(launcher_section.get("sha256"))
    if not target_version or not launcher_url:
        return False

    current_exe = Path(sys.executable).resolve()
    current_matches_target = bool(expected_sha) and current_exe.exists() and _hash_file(current_exe) == expected_sha
    if current_matches_target:
        return False

    if not _is_newer_version(target_version, APP_VERSION):
        return False

    _report("Updating Launcher", f"Downloading launcher update {target_version}...", report_status)
    _ensure_updates_dir()
    download_path = UPDATES_DIR / f"{current_exe.stem}-{target_version}.launcher.download"
    actual_sha = _download_to_file(launcher_url, download_path, settings.timeout_s)
    if expected_sha and actual_sha != expected_sha:
        download_path.unlink(missing_ok=True)
        raise ValueError("downloaded launcher update failed sha256 validation")

    script_path = UPDATES_DIR / "apply_launcher_update.ps1"
    backup_path = UPDATES_DIR / f"{current_exe.stem}.previous.exe"
    launch_args = ", ".join(_ps_quote(arg) for arg in sys.argv[1:])
    launch_args_literal = "@(" + launch_args + ")" if launch_args else "@()"

    script_text = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$parentPid = {os.getpid()}",
            f"$sourceExe = {_ps_quote(str(download_path))}",
            f"$targetExe = {_ps_quote(str(current_exe))}",
            f"$backupExe = {_ps_quote(str(backup_path))}",
            f"$launchArgs = {launch_args_literal}",
            "$deadline = (Get-Date).AddSeconds(90)",
            "while ((Get-Date) -lt $deadline) {",
            "    if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) {",
            "        break",
            "    }",
            "    Start-Sleep -Milliseconds 400",
            "}",
            "for ($attempt = 0; $attempt -lt 40; $attempt++) {",
            "    try {",
            "        if (Test-Path $backupExe) { Remove-Item -Force $backupExe }",
            "        if (Test-Path $targetExe) { Move-Item -Force $targetExe $backupExe }",
            "        Move-Item -Force $sourceExe $targetExe",
            "        if (Test-Path $backupExe) { Remove-Item -Force $backupExe }",
            "        Start-Process -FilePath $targetExe -ArgumentList $launchArgs",
            "        exit 0",
            "    } catch {",
            "        Start-Sleep -Milliseconds 500",
            "    }",
            "}",
            "exit 1",
            "",
        ]
    )

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_text)

    creationflags = 0
    for flag_name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= getattr(subprocess, flag_name, 0)

    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=str(RUNTIME_ROOT),
        creationflags=creationflags,
        close_fds=True,
    )
    _log(f"staged launcher update to version {target_version}; restarting")
    _report("Restarting Process", "Restarting to apply the downloaded launcher update.", report_status)
    _write_state(
        last_manifest_url=settings.manifest_url,
        last_launcher_update_version=target_version,
        last_launcher_update_sha256=expected_sha,
    )
    return True


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _extract_zip_archive(zip_path: Path, destination_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination_dir)


def _resolve_staged_release_dir(staging_root: Path, bundle_dir: str) -> Path:
    requested = _safe_relative_dir(bundle_dir)
    candidate = (staging_root / requested).resolve()
    if candidate.exists():
        return candidate

    discovered = [child for child in staging_root.iterdir() if child.is_dir()]
    if len(discovered) == 1:
        return discovered[0].resolve()

    raise ValueError(f"bundle directory '{bundle_dir}' was not found in downloaded package")


def _activate_release(spec: AppReleaseSpec, staged_release_dir: Path) -> LaunchTarget:
    safe_dir_name = _safe_name(spec.version)
    target_release_dir = (VERSIONS_DIR / safe_dir_name).resolve()
    temp_release_dir = target_release_dir.with_name(target_release_dir.name + ".incoming")

    if temp_release_dir.exists():
        shutil.rmtree(temp_release_dir, ignore_errors=True)
    if temp_release_dir.exists():
        raise OSError(f"could not remove temp release dir: {temp_release_dir}")

    shutil.move(str(staged_release_dir), str(temp_release_dir))
    if target_release_dir.exists():
        shutil.rmtree(target_release_dir, ignore_errors=True)
    if target_release_dir.exists():
        raise OSError(f"could not replace existing release dir: {target_release_dir}")

    os.replace(temp_release_dir, target_release_dir)

    executable_path = target_release_dir / spec.launch_exe
    if not executable_path.exists():
        raise ValueError(f"release bundle missing launch executable: {spec.launch_exe}")

    _write_release_metadata(target_release_dir, spec.version, spec.launch_exe, spec.package_sha256)
    _write_active_release(
        version=spec.version,
        directory_name=safe_dir_name,
        launch_exe=spec.launch_exe,
        package_sha256=spec.package_sha256,
    )

    return LaunchTarget(
        version=spec.version,
        release_dir=target_release_dir,
        executable_path=executable_path,
        runtime_root=RUNTIME_ROOT.resolve(),
        launch_env=dict(os.environ),
    )


def _prune_old_releases(active_directory: str, retain_versions: int) -> None:
    releases: list[tuple[tuple[int, ...], Path]] = []
    for child in VERSIONS_DIR.iterdir() if VERSIONS_DIR.exists() else []:
        if not child.is_dir():
            continue
        if child.name.endswith(".incoming") or child.name.endswith(".extract"):
            continue
        releases.append((_parse_version(child.name), child))

    releases.sort(key=lambda item: item[0] or (0,), reverse=True)
    kept = 0
    for _, release_dir in releases:
        if release_dir.name == active_directory:
            kept += 1
            continue
        if kept < retain_versions:
            kept += 1
            continue
        shutil.rmtree(release_dir, ignore_errors=True)


def _ensure_latest_release(
    manifest: dict[str, Any],
    settings: UpdateSettings,
    current_target: LaunchTarget | None,
    report_status=None,
) -> LaunchTarget | None:
    if not settings.allow_app_update:
        return current_target

    spec = _extract_release_spec(manifest)
    if spec is None:
        return current_target

    current_version = current_target.version if current_target is not None else ""
    if current_target is not None and not _is_newer_version(spec.version, current_version):
        if spec.package_sha256:
            active = _read_active_release()
            if active.get("package_sha256") == spec.package_sha256:
                return current_target
        else:
            return current_target

    safe_dir_name = _safe_name(spec.version)
    release_dir = (VERSIONS_DIR / safe_dir_name).resolve()
    executable_path = release_dir / spec.launch_exe
    if release_dir.exists() and executable_path.exists():
        metadata = _read_release_metadata(release_dir)
        installed_sha = _normalize_sha256(metadata.get("package_sha256"))
        if not spec.package_sha256 or installed_sha == spec.package_sha256:
            _write_active_release(spec.version, safe_dir_name, spec.launch_exe, spec.package_sha256)
            _prune_old_releases(active_directory=safe_dir_name, retain_versions=settings.retain_versions)
            return LaunchTarget(
                version=spec.version,
                release_dir=release_dir,
                executable_path=executable_path,
                runtime_root=RUNTIME_ROOT.resolve(),
                launch_env=dict(os.environ),
            )

        shutil.rmtree(release_dir, ignore_errors=True)
        if release_dir.exists():
            raise OSError(f"could not remove stale release dir: {release_dir}")

    _report("Updating Application", f"Downloading application bundle {spec.version}...", report_status)
    _ensure_updates_dir()
    archive_name = _safe_name(f"{spec.version}.zip")
    archive_path = UPDATES_DIR / archive_name
    actual_sha = _download_to_file(spec.package_url, archive_path, settings.timeout_s)
    if spec.package_sha256 and actual_sha != spec.package_sha256:
        archive_path.unlink(missing_ok=True)
        raise ValueError("downloaded application bundle failed sha256 validation")

    extract_root = VERSIONS_DIR / (safe_dir_name + ".extract")
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    try:
        _report("Updating Application", f"Installing application bundle {spec.version}...", report_status)
        _extract_zip_archive(archive_path, extract_root)
        staged_release_dir = _resolve_staged_release_dir(extract_root, spec.bundle_dir)
        activated = _activate_release(spec, staged_release_dir)
    finally:
        archive_path.unlink(missing_ok=True)
        shutil.rmtree(extract_root, ignore_errors=True)

    _log(f"activated application bundle {spec.version}")
    _report("Updating Application", f"Activated application bundle {spec.version}.", report_status)
    _prune_old_releases(active_directory=activated.release_dir.name, retain_versions=settings.retain_versions)
    return activated


def prepare_client_launch(report_status=None) -> LaunchPreparation:
    _ensure_updates_dir()
    settings = load_update_settings()
    current_target = _resolve_active_release()

    if not settings.enabled or not settings.manifest_url:
        if current_target is None:
            _report("Checking For Updates", "No update manifest configured; using installed bundle only.", report_status)
        else:
            _report("Checking For Updates", "Startup updates are disabled; using installed bundle.", report_status)
        return LaunchPreparation(launch_target=current_target, should_exit=False)

    try:
        _report("Checking For Updates", "Checking update manifest...", report_status)
        manifest = _download_json(settings.manifest_url, settings.timeout_s)
        manifest = _select_manifest_channel(manifest, settings.channel)
        _report("Checking For Updates", "Update manifest loaded.", report_status)

        updated_files = _apply_config_updates(manifest, settings, report_status) if settings.sync_config else []
        launcher_restart_required = _stage_launcher_update(manifest, settings, report_status)
        if launcher_restart_required:
            _write_state(
                last_check_at=_utc_now(),
                last_manifest_url=settings.manifest_url,
                last_channel=settings.channel,
                last_config_updates=updated_files,
                last_error="",
            )
            return LaunchPreparation(launch_target=None, should_exit=True)

        current_target = _ensure_latest_release(manifest, settings, current_target, report_status)
        _write_state(
            last_check_at=_utc_now(),
            last_manifest_url=settings.manifest_url,
            last_channel=settings.channel,
            last_config_updates=updated_files,
            last_release_version=current_target.version if current_target else "",
            last_error="",
        )
        return LaunchPreparation(launch_target=current_target, should_exit=False)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        _log(f"startup updates skipped: {exc}")
        _report("Checking For Updates", f"Startup update check skipped: {exc}", report_status)
        _write_state(
            last_check_at=_utc_now(),
            last_manifest_url=settings.manifest_url,
            last_channel=settings.channel,
            last_error=str(exc),
        )
        return LaunchPreparation(launch_target=current_target, should_exit=False)
