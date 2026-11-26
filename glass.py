"""Windows glue for the sidebar: real acrylic blur behind a window, no taskbar button, theme and work area.
Uses SetWindowCompositionAttribute (Windows 10 1803+; also works on 11)."""
import ctypes
import winreg
from ctypes import wintypes

user32 = ctypes.windll.user32
ACRYLIC, CLEAR = 4, 2  # ACCENT_ENABLE_ACRYLICBLURBEHIND, ACCENT_ENABLE_TRANSPARENTGRADIENT


class _Accent(ctypes.Structure):
    _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int), ("color", ctypes.c_uint), ("anim", ctypes.c_int)]


class _Data(ctypes.Structure):
    _fields_ = [("attr", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]


def dark_mode():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def work_area_height(screen_height):
    """Usable screen height above the taskbar, in pywebview's logical pixels.
    Windows reports scaled or physical pixels depending on the process's DPI awareness at call time,
    so convert by ratio against the screen height reported in the same units."""
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return int(r.bottom * screen_height / user32.GetSystemMetrics(1))  # SM_CYSCREEN


def set_size(title, width, height, scale):
    """Exact size in logical pixels. pywebview subtracts a title-bar/border allowance even for frameless
    windows, and clamps to Windows' minimum window width, so the arrow came out 117px wide."""
    user32.SetWindowPos(user32.FindWindowW(None, title), 0, 0, 0, round(width * scale), round(height * scale),
                        0x0002 | 0x0004 | 0x0010)  # SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE


def apply(window, title, accent):
    """Make `window` see-through to a blur (ACRYLIC) or fully clear (CLEAR), and keep it off the taskbar."""
    from System import Action
    from System.Drawing import Color
    # GDI black is what DWM composites as transparent; the page's own rgba colours then sit on the blur.
    window.native.Invoke(Action(lambda: setattr(window.native, "BackColor", Color.Black)))
    hwnd = user32.FindWindowW(None, title)
    tint = (0x99201C1C if dark_mode() else 0x66F4F2F2) if accent == ACRYLIC else 0  # 0xAABBGGRR
    a = _Accent(accent, 2, tint, 0)
    d = _Data(19, ctypes.cast(ctypes.pointer(a), ctypes.c_void_p), ctypes.sizeof(a))  # WCA_ACCENT_POLICY
    user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(d))
    ex = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE: tool window = no taskbar button, not in Alt+Tab
    user32.SetWindowLongW(hwnd, -20, (ex | 0x80) & ~0x40000)
    # The taskbar only reads the style when a window is shown, so hide and re-show to drop the button.
    visible = user32.IsWindowVisible(hwnd)
    user32.ShowWindow(hwnd, 0)  # SW_HIDE
    if visible:
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
