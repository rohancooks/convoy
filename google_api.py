"""Gmail + Google Calendar. First call opens a browser for Google sign-in; token.json is reused after that."""
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

HERE = Path(__file__).parent
# Read-only on purpose: read mail, read calendar. Convoy can never send, delete or edit anything.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/calendar.readonly"]


def connected():
    """Signed in (`python google_api.py`). Until then, background checks skip quietly instead of erroring."""
    return (HERE / "token.json").exists()


_lock = threading.Lock()  # first sign-in opens a browser; don't let two threads open two


def _creds():
    with _lock:
        return _load_creds()


def _load_creds(interactive=False):
    token = HERE / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # apps in "Testing" mode get refresh tokens that expire after 7 days
            creds = None
    if not creds or not creds.valid:
        if not interactive:  # the app must never wait on a browser sign-in: it froze the brief all morning
            raise RuntimeError("Gmail/Calendar not connected (or sign-in expired). Sign in once with: "
                               ".venv\\Scripts\\python.exe google_api.py (in the convoy folder)")
        creds = InstalledAppFlow.from_client_secrets_file(str(HERE / "credentials.json"), SCOPES).run_local_server(port=0)
    token.write_text(creds.to_json())
    return creds


if __name__ == "__main__":  # python google_api.py -> Google sign-in in your browser, saves token.json
    import os
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # accept a partial grant (e.g. send unticked): reading still works
    print("Signed in as", build("gmail", "v1", credentials=_load_creds(interactive=True))
          .users().getProfile(userId="me").execute()["emailAddress"])


# Built per call: googleapiclient services aren't thread-safe and the app calls from several threads.
def _gmail():
    return build("gmail", "v1", credentials=_creds())


def _calendar():
    return build("calendar", "v3", credentials=_creds())


def search_emails(query="in:inbox newer_than:1d", limit=15):
    g = _gmail()
    ids = g.users().messages().list(userId="me", q=query, maxResults=limit).execute().get("messages", [])
    out = []
    for m in ids:
        msg = g.users().messages().get(userId="me", id=m["id"], format="metadata",
                                       metadataHeaders=["From", "To", "Subject", "Date"]).execute()
        h = {x["name"].lower(): x["value"] for x in msg["payload"]["headers"]}
        out.append({"from": h.get("from", ""), "to": h.get("to", ""), "subject": h.get("subject", ""),
                    "date": h.get("date", ""), "snippet": msg.get("snippet", ""),
                    "unread": "UNREAD" in msg.get("labelIds", [])})
    return out


def upcoming_events(hours=24):
    now = datetime.now(timezone.utc)
    items = _calendar().events().list(
        calendarId="primary", timeMin=now.isoformat(), timeMax=(now + timedelta(hours=hours)).isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=20).execute().get("items", [])
    return [{"id": e["id"], "title": e.get("summary", "(no title)"),
             "start": e["start"].get("dateTime", e["start"].get("date")),
             "end": e["end"].get("dateTime", e["end"].get("date")),
             "attendees": [a["email"] for a in e.get("attendees", []) if not a.get("self")],
             "location": e.get("location", ""), "description": (e.get("description") or "")[:500]}
            for e in items]
