"""Logs the active window every few seconds (Windows only, stdlib ctypes). Nothing leaves the laptop."""
import ctypes
import os
import time
from collections import Counter
from ctypes import wintypes
from datetime import date, datetime, timedelta

import db

INTERVAL = 5
IDLE_AFTER = 300  # no keyboard/mouse for 5 min -> stop counting
EXCLUDE_APPS = {a.strip().lower() for a in os.getenv(
    "EXCLUDE_APPS", "keepass.exe,1password.exe,bitwarden.exe,lockapp.exe").split(",") if a.strip()}
PRIVATE_MARKERS = ("inprivate", "incognito", "private browsing")

user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_secs():
    li = _LastInput(ctypes.sizeof(_LastInput))
    user32.GetLastInputInfo(ctypes.byref(li))
    return (kernel32.GetTickCount() - li.dwTime) / 1000


def active_window():
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, title, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        size = wintypes.DWORD(260)
        path = ctypes.create_unicode_buffer(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(size)):
            exe = os.path.basename(path.value)
        kernel32.CloseHandle(h)
    return exe.lower(), title.value


def should_log(app, title):
    return bool(app) and app not in EXCLUDE_APPS and not any(m in title.lower() for m in PRIVATE_MARKERS)


def run():
    last_key, last_id = None, None
    while True:
        time.sleep(INTERVAL)
        if idle_secs() > IDLE_AFTER:
            last_key = None
            continue
        app, title = active_window()
        if not should_log(app, title):
            last_key = None
            continue
        with db.conn() as c:
            if (app, title) == last_key:  # same window as last tick: extend the row instead of adding one
                c.execute("update activity set secs = secs + ? where id = ?", (INTERVAL, last_id))
            else:
                last_id = c.execute("insert into activity(ts, app, title, secs) values(?,?,?,?)",
                                    (time.time(), app, title, INTERVAL)).lastrowid
                last_key = (app, title)


def day_rows(day: date):
    start = datetime.combine(day, datetime.min.time()).timestamp()
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "select app, title, sum(secs) as secs from activity where ts >= ? and ts < ? "
            "group by app, title order by secs desc", (start, start + 86400))]


def summarize_rows(rows, top=40):
    """Compact text of a day's activity for the LLM: time per app, then the longest windows."""
    if not rows:
        return "No activity recorded."
    per_app = Counter()
    for r in rows:
        per_app[r["app"]] += r["secs"]
    total = sum(per_app.values())
    lines = [f"Active time: {total / 3600:.1f}h",
             "Per app: " + ", ".join(f"{a} {s / 60:.0f}m" for a, s in per_app.most_common(10))]
    lines += [f"- {r['app']}: {r['title'][:120]} ({r['secs'] / 60:.0f}m)" for r in rows[:top] if r["secs"] >= 60]
    return "\n".join(lines)


def yesterday():
    return date.today() - timedelta(days=1)
