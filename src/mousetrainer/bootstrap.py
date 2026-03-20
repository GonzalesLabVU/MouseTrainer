from __future__ import annotations

import ctypes
import subprocess
import sys

from .startup_splash import StartupSplash
from .startup_update import prepare_client_launch
from .version import APP_NAME


def _show_error_dialog(message: str) -> None:
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.user32.MessageBoxW(None, str(message), APP_NAME, 0x10)
    except Exception:
        return


def _launch_client(target) -> int:
    if not target.executable_path.exists():
        _show_error_dialog(f"Required file not found:\n{target.executable_path.name}")
        return 1

    env = dict(target.launch_env)
    env.update(
        {
            "MOUSETRAINER_RUNTIME_ROOT": str(target.runtime_root),
            "MOUSETRAINER_BUNDLE_ROOT": str(target.release_dir),
            "MOUSETRAINER_APP_VERSION": target.version,
        }
    )
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        [str(target.executable_path), *sys.argv[1:]],
        cwd=str(target.runtime_root),
        env=env,
        creationflags=creationflags,
        close_fds=True,
    )
    return 0


def main() -> int:
    if not getattr(sys, "frozen", False):
        from .console_entry import main as console_main

        return console_main()

    with StartupSplash.open() as splash:
        splash.update("Initializing startup tasks.", title="Starting Process")

        preparation = prepare_client_launch(report_status=splash.status_callback)
        if preparation.should_exit:
            splash.update("Restarting to apply the launcher update.", title="Restarting Process")
            return 0

        if preparation.launch_target is None:
            splash.update("No runnable application bundle is installed.", title="Startup Failed")
            _show_error_dialog(
                "MouseTrainer could not find an installed client bundle.\n"
                "Rebuild and redistribute the packaged app folder."
            )
            return 1

        splash.update(
            f"Launching MouseTrainer client version {preparation.launch_target.version}.",
            title="Opening Console",
        )

    return _launch_client(preparation.launch_target)
