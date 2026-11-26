import os
import sqlite3
from pathlib import Path

DB = Path(os.getenv("CONVOY_DB", Path(__file__).with_name("convoy.db")))

SCHEMA = """
create table if not exists activity(id integer primary key, ts real, app text, title text, secs real);
create index if not exists activity_ts on activity(ts);
create table if not exists notes(id integer primary key, ts real, text text, tags text);
-- outbox status: draft -> opened (in Gmail, you send it) | rejected. Convoy never sends.
create table if not exists outbox(id integer primary key, to_addr text, subject text, body text,
                                  send_at real, status text default 'draft', error text);
create table if not exists kv(k text primary key, v text);
"""


def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def kv_get(k):
    with conn() as c:
        row = c.execute("select v from kv where k=?", (k,)).fetchone()
    return row["v"] if row else None


def kv_set(k, v):
    with conn() as c:
        c.execute("insert or replace into kv values(?,?)", (k, v))
