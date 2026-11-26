"""Tool-choice eval: does the agent pick the right tool with the right arguments?
Run: python evals/tool_eval.py   (uses your Gemini key; calls no tools, so nothing is read or sent)"""
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from google.genai import types  # noqa: E402

import agent  # noqa: E402
import tools  # noqa: E402

TOMORROW = str(date.today() + timedelta(days=1))
YESTERDAY = str(date.today() - timedelta(days=1))

# (prompt, expected tool or None for "should ask / answer directly", check on args)
CASES = [
    ("What did I work on yesterday?", "get_activity", lambda a: a.get("day", "") in ("", YESTERDAY)),
    (f"How much time did I spend in VS Code on {YESTERDAY}?", "get_activity", lambda a: a.get("day") == YESTERDAY),
    ("Any unread emails?", "get_emails", lambda a: "unread" in a.get("query", "")),
    ("Did Priya email me this week?", "get_emails", lambda a: "priya" in a.get("query", "").lower()),
    ("What's on my calendar today?", "get_events", lambda a: True),
    ("Do I have meetings in the next 3 days?", "get_events", lambda a: a.get("hours", 0) >= 72),
    ("Note: call the plumber on Friday about the leak", "add_note", lambda a: "plumber" in a.get("text", "").lower()),
    ("What did I write down about the plumber?", "search_notes", lambda a: "plumber" in a.get("query", "").lower()),
    ("Email rahul@example.com saying the report is ready", "draft_email", lambda a: a.get("to") == "rahul@example.com"),
    ("Write an email to rahul@example.com: the deck is attached", "draft_email",
     lambda a: "deck" in a.get("body", "").lower()),
    ("Send an email to Rahul about lunch", None, None),  # no address -> must ask, not guess
    ("Hi! What can you do?", None, None),
]


def gemini_call(prompt):
    r = agent.client().models.generate_content(
        model=agent.MODEL, contents=agent.stamp(prompt),
        config=types.GenerateContentConfig(
            system_instruction=agent.SYSTEM, tools=tools.TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    calls = r.function_calls or []
    return (calls[0].name, dict(calls[0].args or {})) if calls else (None, {})


def claude_call(prompt):  # one request, tools not executed: we only check what Claude *would* call
    r = agent.claude().beta.messages.create(**agent._claude_args("low"), system=agent.SYSTEM,
                                            tools=[t.to_dict() for t in agent.CLAUDE_TOOLS],
                                            messages=[{"role": "user", "content": agent.stamp(prompt)}])
    calls = [b for b in r.content if b.type == "tool_use"]
    return (calls[0].name, dict(calls[0].input)) if calls else (None, {})


def run(name, model, first_call, pause):
    print(f"\n=== {name} ({model}) ===")
    passed, total_s = 0, 0.0
    for prompt, want, check in CASES:
        t = time.time()
        try:
            got, args = first_call(prompt)
            ok = got == want and (check is None or check(args))
        except Exception as e:
            got, args, ok = f"error: {e}"[:70], {}, False
        total_s += time.time() - t
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {time.time() - t:4.1f}s  {prompt[:50]:50}  -> {got} {args if args else ''}")
        time.sleep(pause)  # stay under free-tier requests-per-minute limits
    return name, model, passed, total_s / len(CASES)


results = [run("Gemini", agent.MODEL, gemini_call, 6)]
if os.getenv("ANTHROPIC_API_KEY"):
    results.append(run("Claude", agent.CLAUDE_MODEL, claude_call, 2))

print("\n| Provider | Model | Correct | Avg latency |\n|---|---|---|---|")
for name, model, passed, avg in results:
    print(f"| {name} | {model} | {passed}/{len(CASES)} ({passed / len(CASES):.0%}) | {avg:.1f}s |")
