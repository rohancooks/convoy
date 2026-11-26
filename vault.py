"""Obsidian export: Convoy writes Markdown into your vault, so notes, briefs and meetings become linked pages.
Set OBSIDIAN_VAULT in .env (the folder that contains .obsidian). Unset = export off."""
import functools
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path

_lock = threading.RLock()


def root():
    v = os.getenv("OBSIDIAN_VAULT", "").strip()
    return Path(v) if v else None


def _quiet(fn):
    """A broken vault path must never break the brief or lose a note (it's already in SQLite)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not root():
            return None
        try:
            with _lock:
                return fn(*args, **kwargs)
        except OSError as e:
            print("obsidian export:", e)
    return wrapper


def _name(s, n=60):
    s = re.sub(r'[\\/:*?"<>|#^\[\]`*>•\n\r]', " ", s)
    return re.sub(r"\s+", " ", s).strip(" -.")[:n].strip() or "Untitled"


def _demote(md):  # the brief's own "## " sections nest under the daily note's "## " heading
    return re.sub(r"^(#{1,5}) ", r"#\1 ", md.strip(), flags=re.M)


# Only lines you mark are tasks; the rest of the journal is never read by the AI.
_TASK = re.compile(r"^\s*(?:[-*]\s*\[ \]|todo:)\s*(.+)", re.I)


def journal_tasks(entries=7):
    """Lines starting with `TODO:` or `- [ ]` in your last `entries` journal pages (Journal/), newest first.
    Parsed locally; `- [x]` (done) lines are skipped."""
    folder = root() / "Journal" if root() else None
    if not folder or not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.glob("????-??-?? journal.md"), reverse=True)[:entries]:
        for line in f.read_text(encoding="utf-8").splitlines():
            if m := _TASK.match(line):
                out.append({"day": f.name[:10], "task": m.group(1).strip()})
    return out


def _tags(tags):
    return [re.sub(r"[^\w/-]+", "-", t.strip().lower()).strip("-") for t in tags if t.strip()]


def _write_new(path: Path, text):  # never overwrite a page you may have edited
    path.parent.mkdir(parents=True, exist_ok=True)
    stem, i = path.stem, 2
    while path.exists():
        path, i = path.with_name(f"{stem} {i}.md"), i + 1
    path.write_text(text, encoding="utf-8")
    return path


def _daily(day: date):
    path = root() / "Daily" / f"{day}.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\ntags: [daily]\n---\n# {day:%A, %d %B %Y}\n", encoding="utf-8")
    return path


@_quiet
def add_to_daily(heading, body, day=None):
    with _daily(day or date.today()).open("a", encoding="utf-8") as f:
        f.write(f"\n## {heading} · {datetime.now():%H:%M}\n{_demote(body)}\n")


@_quiet
def save_note(text, tags=()):
    now = datetime.now()
    tags = ["note", *_tags(tags)]
    p = _write_new(root() / "Notes" / f"{now:%Y-%m-%d %H%M} {_name(' '.join(text.split()[:8]))}.md",
                   f"---\ncreated: {now:%Y-%m-%dT%H:%M}\ntags: [{', '.join(tags)}]\n---\n"
                   f"{text.strip()}\n\nFrom [[{now:%Y-%m-%d}]]\n")
    add_to_daily("Note", f"[[Notes/{p.stem}]]")
    return p


@_quiet
def save_meeting(event, brief):
    day = event["start"][:10]
    people = "\n".join(f"- [[{a}]]" for a in event["attendees"]) or "- (just you)"
    p = _write_new(root() / "Meetings" / f"{day} {_name(event['title'])}.md",
                   f"---\ndate: {day}\ntags: [meeting]\n---\n# {event['title']}\n"
                   f"**When:** {event['start']}  \nFrom [[{day}]]\n\n## Attendees\n{people}\n\n"
                   f"## Prep\n{_demote(brief)}\n\n## Notes\n\n")
    add_to_daily("Meeting", f"[[Meetings/{p.stem}]]", date.fromisoformat(day))
    return p
