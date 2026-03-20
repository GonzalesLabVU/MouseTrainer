from __future__ import annotations

import ctypes
import os
import sys

from .version import APP_NAME


STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
ATTACH_PARENT_PROCESS = -1
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def _reopen_stdio() -> None:
    stdin = open("CONIN$", "r", encoding="utf-8", errors="replace", buffering=1)
    stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
    stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)

    sys.stdin = stdin
    sys.stdout = stdout
    sys.stderr = stderr
    sys.__stdin__ = stdin
    sys.__stdout__ = stdout
    sys.__stderr__ = stderr


def _enable_virtual_terminal_processing(kernel32) -> None:
    handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    if handle in (0, -1):
        return

    mode = ctypes.c_uint()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return

    kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)


def ensure_runtime_console() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    kernel32 = ctypes.windll.kernel32
    if kernel32.GetConsoleWindow():
        return

    attached = bool(kernel32.AttachConsole(ATTACH_PARENT_PROCESS))
    if not attached and not kernel32.AllocConsole():
        return

    _reopen_stdio()
    _enable_virtual_terminal_processing(kernel32)
    kernel32.SetConsoleTitleW(APP_NAME)
