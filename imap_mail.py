"""Second inbox over IMAP (any provider: Titan, GoDaddy, Zoho, Outlook...). Read-only: the mailbox is opened read-only and
messages are fetched with BODY.PEEK, so nothing is marked read, moved, deleted or sent."""
import email
import imaplib
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header


def account():
    return os.getenv("IMAP_USER", "").strip()


def configured():
    return all(os.getenv(k, "").strip() for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"))


def _h(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # malformed encoded header: show it raw rather than fail the whole inbox
        return v or ""


def _snippet(msg, n=300):
    for part in msg.walk():
        kind = part.get_content_type()
        if kind in ("text/plain", "text/html") and not part.get_filename():
            try:
                text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
            if kind == "text/html":
                text = re.sub(r"(?s)<(style|script).*?</\1>|<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text).strip()[:n]
    return ""


def parse(raw: bytes, meta: bytes):
    """One fetched message -> same shape as google_api.search_emails, plus the account it came from."""
    msg = email.message_from_bytes(raw)
    return {"account": account(), "from": _h(msg["From"]), "to": _h(msg["To"]), "subject": _h(msg["Subject"]),
            "date": msg["Date"] or "", "snippet": _snippet(msg), "unread": b"\\Seen" not in meta}


def search_emails(days=1, unread_only=False, limit=15):
    if not configured():
        raise RuntimeError("Second inbox not set up: fill IMAP_HOST, IMAP_USER and IMAP_PASSWORD in convoy\\.env")
    with imaplib.IMAP4_SSL(os.getenv("IMAP_HOST").strip(), 993, timeout=30) as m:
        m.login(account(), os.getenv("IMAP_PASSWORD"))
        m.select("INBOX", readonly=True)
        since = (date.today() - timedelta(days=max(days, 1))).strftime("%d-%b-%Y")
        ids = m.search(None, "SINCE", since, *(["UNSEEN"] if unread_only else []))[1][0].split()
        out = []
        for i in reversed(ids[-limit:]):  # newest first
            # First 64 KB only: headers and the start of the text, never whole attachments.
            data = m.fetch(i, "(FLAGS BODY.PEEK[]<0.65536>)")[1]
            raw = next((p[1] for p in data if isinstance(p, tuple)), b"")
            meta = b" ".join(p[0] if isinstance(p, tuple) else p for p in data if p)
            out.append(parse(raw, meta))
        return out
