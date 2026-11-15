"""Run: python3 tests/test_state.py  (or pytest)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "daemon"))
from state import Session, apply, describe  # noqa: E402


def ev(name, **kw):
    return {"hook_event_name": name, "session_id": "s1", "cwd": "/home/u/proj", **kw}


def run(events, s=None):
    s = s or Session(id="s1")
    kinds = [apply(s, e, t) for t, e in events]
    return s, kinds


def test_describe():
    assert describe("Bash", {"command": "npm  test\n"}) == "$ npm test"
    assert describe("Edit", {"file_path": "/a/b/state.py"}) == "Editing state.py"
    assert describe("WebFetch", {"url": "https://example.com/x"}) == "Fetching example.com"
    assert describe("mcp__easel__chart", {}) == "easel · chart"
    assert describe("Unknown", None) == "Unknown"


def test_working_turn():
    s, kinds = run([
        (0, ev("SessionStart", source="startup")),
        (1, ev("UserPromptSubmit", prompt="fix the bug")),
        (2, ev("PreToolUse", tool_name="Read", tool_input={"file_path": "/x/a.py"})),
        (3, ev("PostToolUse", tool_name="Read")),
    ])  # fmt: skip
    assert s.project == "proj" and s.state == "working" and s.action == "Thinking"
    assert s.task == "fix the bug" and s.recent == [[2, "Reading a.py"]]
    assert kinds == [None] * 4 and s.attention is None


def test_permission_raised_then_answered():
    bash = {"tool_name": "Bash", "tool_input": {"command": "rm -rf dist"}}
    s, kinds = run([
        (1, ev("UserPromptSubmit", prompt="clean")),
        (2, ev("PreToolUse", **bash)),
        (3, ev("PermissionRequest", **bash)),
        (3.1, ev("Notification", notification_type="permission_prompt", message="Claude needs your permission")),
    ])  # fmt: skip
    assert kinds == [None, None, "permission", None]
    assert s.attention == {"kind": "permission", "text": "$ rm -rf dist", "ts": 3, "call": "$ rm -rf dist"}
    apply(s, ev("PostToolUse", **bash), 9)
    assert s.attention is None and s.action == "Thinking"


def test_question_and_plan():
    q = {"questions": [{"question": "Which framework?", "options": [{"label": "React"}, {"label": "Vue"}]}]}
    s, kinds = run([(1, ev("PreToolUse", tool_name="AskUserQuestion", tool_input=q))])
    assert kinds == ["question"] and s.attention["text"] == "Which framework?"
    assert s.attention["options"] == ["React", "Vue"]
    assert apply(s, ev("PermissionRequest", tool_name="AskUserQuestion", tool_input=q), 2) is None
    assert s.attention["kind"] == "question" and s.attention["ts"] == 1
    multi = {"questions": [{"question": "a?", "multiSelect": True, "options": [{"label": "x"}]}]}
    s, _ = run([(1, ev("PermissionRequest", tool_name="AskUserQuestion", tool_input=multi))])
    assert s.attention["kind"] == "question" and "options" not in s.attention
    s, kinds = run([(1, ev("PreToolUse", tool_name="ExitPlanMode", tool_input={}))])
    assert kinds == ["plan"]


def test_permission_before_pretooluse():
    bash = {"tool_name": "Bash", "tool_input": {"command": "make"}}
    s, kinds = run([(1, ev("PermissionRequest", **bash)), (1.1, ev("PreToolUse", **bash))])
    assert kinds == ["permission", None] and s.attention["ts"] == 1
    apply(s, ev("PreToolUse", tool_name="Read", tool_input={"file_path": "a"}), 2)
    assert s.attention is None


def test_done_only_after_long_turn():
    s, kinds = run([(100, ev("UserPromptSubmit", prompt="hi")), (105, ev("Stop", last_assistant_message="hello"))])
    assert kinds == [None, None] and s.attention is None and s.state == "idle"
    s, kinds = run([(100, ev("UserPromptSubmit", prompt="hi")), (200, ev("Stop", last_assistant_message="all done"))])
    assert kinds == [None, "done"] and s.attention["text"] == "all done"
    assert apply(s, ev("UserPromptSubmit", prompt="next"), 300) is None and s.attention is None


def test_dismiss_stays_quiet_until_agent_moves_on():
    s = Session(id="s1", quiet=True)
    assert apply(s, ev("Notification", notification_type="permission_prompt", message="m"), 1) is None
    apply(s, ev("PreToolUse", tool_name="Read", tool_input={}), 2)
    assert s.quiet is False
    assert apply(s, ev("Notification", notification_type="permission_prompt", message="m"), 3) == "permission"


def test_misc():
    s, kinds = run([
        (1, ev("SubagentStart")),
        (2, ev("PreToolUse", tool_name="Grep", tool_input={"pattern": "foo"}, agent_id="a1")),
        (3, ev("SubagentStop")),
        (4, ev("StopFailure", error="rate limit")),
        (5, ev("SessionEnd", reason="other")),
    ])  # fmt: skip
    assert s.recent[-1][1] == "↳ Searching foo" and s.subagents == 0
    assert kinds[3] == "error" and s.ended
    s = Session.load({"id": "x", "unknown_field": 1, "project": "p"})
    assert s.project == "p"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
