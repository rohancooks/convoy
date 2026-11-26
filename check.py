"""Offline self-check (no API key, no Google account). Run: python check.py"""
import os
import tempfile
import time
from datetime import date
from pathlib import Path

os.environ["CONVOY_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import db  # noqa: E402
import google_api  # noqa: E402
import tools  # noqa: E402
import tracker  # noqa: E402

db.init()

# Activity summary groups by app and skips windows under a minute.
rows = [{"app": "code.exe", "title": "app.py", "secs": 3600}, {"app": "chrome.exe", "title": "Gmail", "secs": 1800},
        {"app": "code.exe", "title": "ui.html", "secs": 30}]
s = tracker.summarize_rows(rows)
assert "Active time: 1.5h" in s and "code.exe 60m" in s and "ui.html" not in s, s
assert tracker.summarize_rows([]) == "No activity recorded."

# Private windows and password managers are never logged.
assert not tracker.should_log("chrome.exe", "Bank - Incognito")
assert not tracker.should_log("keepass.exe", "Vault")
assert tracker.should_log("code.exe", "app.py")

# Email: Convoy can't send at all (no send permission, no send code); drafts open in Gmail for the user to send.
assert not any("send" in s for s in google_api.SCOPES) and not hasattr(google_api, "send_email")
assert tools.draft_email("Rahul", "Hi", "x").startswith("Error")
tools.draft_email("Rahul <rahul@example.com>", "Report & update", "It's ready.")
d = tools.drafts()[0]
assert d["status"] == "draft" and d["to_addr"] == "rahul@example.com"
url = tools.open_draft(d["id"])
assert url.startswith("https://mail.google.com/mail/?view=cm") and "su=Report+%26+update" in url, url
assert tools.drafts() == [] and tools.open_draft(d["id"]) == ""  # opened once, then gone from the sidebar
tools.draft_email("a@b.com", "Bye", "x")
tools.discard(tools.drafts()[0]["id"])
assert tools.drafts() == []

# Second inbox (IMAP): encoded headers decoded, HTML stripped to a snippet, unread read from the flags.
import imap_mail  # noqa: E402

raw = (b"From: =?utf-8?b?UHJpeWEgU2hhcm1h?= <priya@example.com>\r\nTo: contact@example.com\r\n"
       b"Subject: =?utf-8?q?Website_quote_=E2=82=B9?=\r\nDate: Tue, 25 Nov 2026 10:00:00 +0530\r\n"
       b"Content-Type: text/html; charset=utf-8\r\n\r\n<style>p{}</style><p>Can you  share\r\n the quote?</p>")
e = imap_mail.parse(raw, b"1 (FLAGS () BODY[]<0> {300}")
assert e["from"] == "Priya Sharma <priya@example.com>" and e["subject"] == "Website quote ₹", e
assert e["snippet"] == "Can you share the quote?" and e["unread"] is True, e
assert imap_mail.parse(raw, b"1 (FLAGS (\\Seen) BODY[]<0> {300}")["unread"] is False

# Gemini quota: a model whose daily quota is spent is skipped; other errors (per-minute limits, bugs) still raise.
import agent  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def day_limit(m):
    if m == agent.MODELS[0]:
        raise genai_errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message":
                                       "quota", "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}})
    return m


assert agent._with_model(day_limit) == agent.MODELS[1] and agent._with_model(lambda m: m) == agent.MODELS[1]
agent._spent.clear()
try:
    agent._with_model(lambda m: (_ for _ in ()).throw(genai_errors.ClientError(429, {"error": {"message": "PerMinute"}})))
    raise AssertionError("per-minute 429 must not switch models")
except genai_errors.ClientError:
    pass

# Notes search matches any word.
tools.add_note("Call the plumber on Friday", "home")
assert len(tools.search_notes("plumber")) == 1 and tools.search_notes("dentist") == []

# Obsidian export: off when unset; notes, briefs and meetings land as linked pages; nothing gets overwritten.
import vault  # noqa: E402

assert vault.save_note("x") is None  # OBSIDIAN_VAULT unset -> export off
v = os.environ["OBSIDIAN_VAULT"] = tempfile.mkdtemp()
p = vault.save_note("- Call the plumber: Friday?", ["Home Repair", ""])
assert p.parent.name == "Notes" and "Call the plumber Friday" in p.name, p.name
body = p.read_text(encoding="utf-8")
assert "tags: [note, home-repair]" in body and "From [[" in body, body
assert vault.save_note("- Call the plumber: Friday?") != p  # same minute, same title -> new file, not overwrite
vault.add_to_daily("Morning brief", "## Yesterday\n- coded")
daily = (Path(v) / "Daily" / f"{date.today()}.md").read_text(encoding="utf-8")
assert "### Yesterday" in daily and f"[[Notes/{p.stem}]]" in daily, daily
m = vault.save_meeting({"title": "Design: sync?", "start": "2026-10-21T10:00:00+05:30",
                        "attendees": ["priya@example.com"]}, "## Agenda\n- ship")
assert m.name == "2026-10-21 Design sync.md" and "[[priya@example.com]]" in m.read_text(encoding="utf-8")
# Journal tasks: only marked lines, newest page first, done items skipped, diary text never picked up.
(Path(v) / "Journal").mkdir()
(Path(v) / "Journal" / "2026-11-23 journal.md").write_text("Day 8\n- [ ] book flights\n", encoding="utf-8")
(Path(v) / "Journal" / "2026-11-24 journal.md").write_text(
    "Rested all day, todo list was long.\nTODO: follow up with Angad\n- [x] sent invite\n* [ ] ask about phone\n",
    encoding="utf-8")
assert vault.journal_tasks() == [{"day": "2026-11-24", "task": "follow up with Angad"},
                                 {"day": "2026-11-24", "task": "ask about phone"},
                                 {"day": "2026-11-23", "task": "book flights"}], vault.journal_tasks()
assert [t["day"] for t in vault.journal_tasks(1)] == ["2026-11-24", "2026-11-24"]
os.environ["OBSIDIAN_VAULT"] = str(Path(v) / "nul" / "<bad>")  # broken path must not raise
assert vault.save_note("still fine") is None

print("All checks passed.")
