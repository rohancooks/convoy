"""Convoy: a personal AI sidebar. Run `python app.py`. A small arrow sits on the right edge of the screen;
click it (or press Ctrl+Alt+Space) and the glass sidebar slides in. Nothing ever pops up on its own."""
import ctypes
import io
import json
import os
import threading
import time
import wave
import webbrowser
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)  # .env wins over stale Windows env vars

import keyboard  # noqa: E402  (after load_dotenv so modules see the env)
import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402
import webview  # noqa: E402

import agent  # noqa: E402
import db  # noqa: E402
import glass  # noqa: E402
import google_api  # noqa: E402
import tools  # noqa: E402
import tracker  # noqa: E402

HOTKEY = os.getenv("HOTKEY", "ctrl+alt+space")
WIDTH, HANDLE_W, HANDLE_H = 400, 22, 72
RATE = 16000
win = handle = None
geo = {}  # screen width / height in pywebview's logical pixels, filled in main()
_open = {"now": False}
_slide_lock = threading.Lock()  # arrow, hotkey and Esc can all fire at once
_rec = {"stream": None, "frames": []}


def _place(panel_x):
    win.move(panel_x, 0)
    handle.move(panel_x - HANDLE_W, (geo["h"] - HANDLE_H) // 2)


def toggle(show=None):
    """Slide the sidebar in or out from the right edge, with the arrow riding along its left side."""
    with _slide_lock:
        show = (not _open["now"]) if show is None else show
        if show == _open["now"]:
            return
        _open["now"] = show
        sw, frames = geo["w"], 12
        if show:
            win.show()
            win.evaluate_js("onOpen()")
            handle.evaluate_js("setOpen(true)")
        for i in range(1, frames + 1):
            e = 1 - (1 - i / frames) ** 3  # ease-out cubic
            _place(int(sw - WIDTH * (e if show else 1 - e)))
            time.sleep(0.012)
        if not show:
            win.hide()
            handle.evaluate_js("setOpen(false)")


def result(fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception as e:
        msg = str(e)
        if "API key not valid" in msg or "API_KEY_INVALID" in msg:
            msg = ("Your Gemini API key isn't valid any more. Create a new one at aistudio.google.com/apikey, "
                   "paste it after GEMINI_API_KEY= in convoy\\.env, then restart Convoy.")
        elif "429" in msg and "RESOURCE_EXHAUSTED" in msg:
            msg = "Gemini's free daily limit is used up. Try again later, or tomorrow."
        elif "503" in msg:
            msg = "Gemini is busy right now. Wait a minute and press Refresh."
        return {"ok": False, "error": msg[:400]}


def cached(key, fn, refresh):
    if not refresh and (v := db.kv_get(key)):
        return v
    v = fn()
    db.kv_set(key, v)
    return v


def _wav(frames):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(np.concatenate(frames).tobytes() if frames else b"")
    return buf.getvalue()


class Api:
    """Everything the sidebar's JavaScript can call (window.pywebview.api.*)."""

    def brief(self, refresh=False):
        return result(lambda: cached(f"brief:{date.today()}", agent.morning_brief, refresh))

    def digest(self, refresh=False):
        return result(lambda: cached(f"digest:{date.today()}", agent.news_digest, refresh))

    def chat(self, msg):
        return result(lambda: agent.chat(msg))

    def drafts(self):
        return result(tools.drafts)

    def open_draft(self, draft_id):  # opens Gmail's compose window; you press Send there
        def go():
            if url := tools.open_draft(int(draft_id)):
                webbrowser.open(url)
            return tools.drafts()
        return result(go)

    def discard(self, draft_id):
        return result(lambda: (tools.discard(int(draft_id)), tools.drafts())[1])

    def save_note(self, text):  # typed in the box while on the Notes tab
        return result(lambda: tools.add_note(str(text).strip()))

    def notes(self, query=""):
        return result(lambda: tools.search_notes(query, 50))

    def record_start(self):
        def start():
            _rec["frames"] = []
            _rec["stream"] = sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                                            callback=lambda data, *_: _rec["frames"].append(data.copy()))
            _rec["stream"].start()
        return result(start)

    def record_stop(self):
        def stop():
            s, _rec["stream"] = _rec["stream"], None
            if s:
                s.stop()
                s.close()
            if sum(len(f) for f in _rec["frames"]) < RATE // 2:
                raise ValueError("Recording too short.")
            return agent.voice_note(_wav(_rec["frames"]))
        return result(stop)

    def open_link(self, url):
        if url.startswith(("https://", "http://")):
            webbrowser.open(url)

    def toggle(self):  # the edge arrow
        threading.Thread(target=toggle, daemon=True).start()

    def hide(self):  # close button / Esc
        threading.Thread(target=toggle, args=(False,), daemon=True).start()


def background():
    """Make the windows glass, then every minute: prepare a brief 10 min before each meeting
    (shown as a dot on the arrow, never a popup)."""
    win.events.loaded.wait()
    handle.events.loaded.wait()
    glass.apply(win, "Convoy", glass.ACRYLIC)
    glass.apply(handle, "Convoy handle", glass.CLEAR)
    glass.set_size("Convoy", WIDTH, geo["h"], geo["scale"])
    glass.set_size("Convoy handle", HANDLE_W, HANDLE_H, geo["scale"])
    if not _open["now"]:
        win.hide()  # pywebview shows transparent windows once loaded, even when created hidden
    briefed = set()
    while True:
        try:
            for ev in google_api.upcoming_events(1) if google_api.connected() else []:
                if "T" not in ev["start"] or ev["id"] in briefed:  # skip all-day events
                    continue
                start = datetime.fromisoformat(ev["start"])
                if 0 < (start - datetime.now(start.tzinfo)).total_seconds() <= 600:
                    briefed.add(ev["id"])
                    text = agent.meeting_brief(ev)
                    win.evaluate_js(f"showMeetingBrief({json.dumps(ev['title'])}, {json.dumps(text)})")
                    if not _open["now"]:
                        handle.evaluate_js("setDot(true)")
        except Exception as e:
            print("meeting brief:", e)
        time.sleep(60)


def main():
    global win
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY missing: copy .env.example to .env and paste your key (see README step 1).")
    if ctypes.windll.user32.FindWindowW(None, "Convoy handle"):  # already running: open it, don't start twice
        keyboard.send(HOTKEY)
        return
    db.init()
    # Own taskbar identity, so Windows shows convoy.ico instead of grouping us under pythonw.exe's icon.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Convoy.Sidebar")
    threading.Thread(target=tracker.run, daemon=True).start()
    global handle
    screen = webview.screens[0]
    geo.update(w=screen.width, h=glass.work_area_height(screen.height), scale=screen.scale)
    ui, api = Path(__file__).with_name("ui"), Api()
    # Starts hidden, off-screen to the right; the arrow is the only thing you see until you click it.
    win = webview.create_window("Convoy", str(ui / "index.html"), js_api=api, width=WIDTH, height=geo["h"],
                                x=geo["w"], y=0, frameless=True, easy_drag=False, on_top=True,
                                transparent=True, hidden=True, shadow=False)
    handle = webview.create_window("Convoy handle", str(ui / "handle.html"), js_api=api, width=HANDLE_W,
                                   height=HANDLE_H, x=geo["w"] - HANDLE_W, y=(geo["h"] - HANDLE_H) // 2,
                                   min_size=(HANDLE_W, HANDLE_H),  # default minimum is 200x100
                                   frameless=True, easy_drag=False, on_top=True, transparent=True,
                                   focus=False, shadow=False)
    keyboard.add_hotkey(HOTKEY, lambda: threading.Thread(target=toggle, daemon=True).start())
    webview.start(background, icon=str(Path(__file__).with_name("convoy.ico")))


if __name__ == "__main__":
    main()
