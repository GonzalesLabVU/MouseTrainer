from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

from .version import APP_NAME, APP_VERSION


LRESULT = ctypes.c_ssize_t
WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
SS_LEFT = 0x00000000
SW_SHOW = 5
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SETFONT = 0x0030
WM_TIMER = 0x0113
IDC_ARROW = 32512
COLOR_WINDOW = 5
HWND_TOPMOST = -1
MINIMUM_SPLASH_SECONDS = 3.0
MINIMUM_STATUS_SECONDS = 1.0


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROCTYPE),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class StartupSplash:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._close_requested = threading.Event()
        self._lock = threading.Lock()
        self._title = APP_NAME
        self._lines = ["Starting up...", "Preparing update and runtime checks."]
        self._opened = False
        self._opened_at = time.monotonic()
        self._shown_at: float | None = None
        self._last_change_at: float | None = None
        self._hwnd = None
        self._title_hwnd = None
        self._body_hwnd = None
        self._footer_hwnd = None
        self._font_title = None
        self._font_body = None
        self._class_name = f"MouseTrainerSplash_{os.getpid()}"
        self._wndproc = None
        self._user32 = ctypes.windll.user32 if os.name == "nt" else None
        self._gdi32 = ctypes.windll.gdi32 if os.name == "nt" else None

    @classmethod
    def open(cls) -> "StartupSplash":
        splash = cls()
        if os.name != "nt" or not getattr(sys, "frozen", False):
            return splash

        try:
            splash._thread = threading.Thread(target=splash._run_message_loop, name="startup-splash", daemon=True)
            splash._thread.start()
            splash._ready.wait(timeout=0.35)
        except Exception:
            return cls()

        return splash

    def _center_window(self, width: int, height: int) -> tuple[int, int]:
        screen_w = self._user32.GetSystemMetrics(0)
        screen_h = self._user32.GetSystemMetrics(1)
        return max(0, (screen_w - width) // 2), max(0, (screen_h - height) // 2)

    def _refresh_labels(self) -> None:
        if not self._opened:
            return

        with self._lock:
            title = self._title
            body = "\r\n".join(self._lines)

        self._user32.SetWindowTextW(self._title_hwnd, title)
        self._user32.SetWindowTextW(self._body_hwnd, body)

    def _run_message_loop(self) -> None:
        user32 = self._user32
        gdi32 = self._gdi32
        kernel32 = ctypes.windll.kernel32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = ctypes.c_uint16
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = LRESULT
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.SetWindowTextW.restype = wintypes.BOOL

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_TIMER:
                self._refresh_labels()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROCTYPE(wndproc)
        hinstance = kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = self._wndproc
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = self._class_name
        wndclass.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        wndclass.hbrBackground = ctypes.c_void_p(COLOR_WINDOW + 1)

        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            self._ready.set()
            return

        width, height = 560, 250
        left, top = self._center_window(width, height)
        self._hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            self._class_name,
            APP_NAME,
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
            left,
            top,
            width,
            height,
            None,
            None,
            hinstance,
            None,
        )
        if not self._hwnd:
            self._ready.set()
            return

        self._title_hwnd = user32.CreateWindowExW(
            0,
            "STATIC",
            APP_NAME,
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            24,
            24,
            500,
            38,
            self._hwnd,
            None,
            hinstance,
            None,
        )
        self._body_hwnd = user32.CreateWindowExW(
            0,
            "STATIC",
            "\r\n".join(self._lines),
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            24,
            78,
            500,
            112,
            self._hwnd,
            None,
            hinstance,
            None,
        )
        self._footer_hwnd = user32.CreateWindowExW(
            0,
            "STATIC",
            f"Version {APP_VERSION}",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            24,
            188,
            500,
            24,
            self._hwnd,
            None,
            hinstance,
            None,
        )

        self._font_title = gdi32.CreateFontW(-24, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, "Segoe UI")
        self._font_body = gdi32.CreateFontW(-18, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, "Segoe UI")
        user32.SendMessageW(self._title_hwnd, WM_SETFONT, self._font_title, 1)
        user32.SendMessageW(self._body_hwnd, WM_SETFONT, self._font_body, 1)
        user32.SendMessageW(self._footer_hwnd, WM_SETFONT, self._font_body, 1)

        user32.ShowWindow(self._hwnd, SW_SHOW)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        user32.SetTimer(self._hwnd, 1, 120, None)
        self._opened = True
        self._shown_at = time.monotonic()
        self._last_change_at = self._shown_at
        self._ready.set()
        self._refresh_labels()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._font_title:
            gdi32.DeleteObject(self._font_title)
        if self._font_body:
            gdi32.DeleteObject(self._font_body)

    def _wait_for_current_display_minimum(self) -> None:
        if not self._opened:
            return

        changed_at = self._last_change_at or self._shown_at or self._opened_at
        elapsed = time.monotonic() - changed_at
        if elapsed < MINIMUM_STATUS_SECONDS:
            time.sleep(MINIMUM_STATUS_SECONDS - elapsed)

    def update(self, *lines: str, title: str | None = None) -> None:
        rendered_lines = [str(line).strip() for line in lines if str(line).strip()]
        if not rendered_lines:
            rendered_lines = ["Starting up..."]

        target_title = title or APP_NAME
        with self._lock:
            if self._title == target_title and self._lines == rendered_lines:
                return

        self._wait_for_current_display_minimum()

        with self._lock:
            self._title = target_title
            self._lines = rendered_lines
            if self._opened:
                self._last_change_at = time.monotonic()

    def status_callback(self, status: str, detail: str | None = None) -> None:
        if detail:
            self.update(detail, title=status)
            return

        self.update(title=status)

    def close(self) -> None:
        self._close_requested.set()

        if self._thread is None:
            return

        if not self._opened:
            self._ready.wait(timeout=1.5)
            if not self._opened:
                self._thread.join(timeout=2.0)
                return

        shown_at = self._shown_at or self._opened_at
        total_elapsed = time.monotonic() - shown_at
        if total_elapsed < MINIMUM_SPLASH_SECONDS:
            time.sleep(MINIMUM_SPLASH_SECONDS - total_elapsed)

        self._wait_for_current_display_minimum()

        try:
            self._user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass

        self._thread.join(timeout=2.0)

    def __enter__(self) -> "StartupSplash":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
