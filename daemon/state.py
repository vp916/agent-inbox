"""Session state machine: one hook event in, updated Session out. No I/O."""
import os
from dataclasses import dataclass, field, fields
from urllib.parse import urlparse

# attention kinds: permission, question, plan (agent is blocked on the user),
# done, error (agent stopped)
BLOCKED = ("permission", "question", "plan")
DONE_MIN_TURN = 30  # a finished turn only counts as "needs you" if it ran this long (s)
RECENT = 6


def short(s, n=72):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def base(p):
    return os.path.basename(str(p or "").rstrip("/")) or "?"


def describe(tool, inp):
    inp = inp if isinstance(inp, dict) else {}
    if tool == "Bash":
        return "$ " + short(inp.get("command"), 64)
    if tool == "Read":
        return "Reading " + base(inp.get("file_path"))
    if tool in ("Edit", "MultiEdit", "NotebookEdit"):
        return "Editing " + base(inp.get("file_path") or inp.get("notebook_path"))
    if tool == "Write":
        return "Writing " + base(inp.get("file_path"))
    if tool == "Grep":
        return "Searching " + short(inp.get("pattern"), 50)
    if tool == "Glob":
        return "Finding " + short(inp.get("pattern"), 50)
    if tool == "WebFetch":
        return "Fetching " + (urlparse(str(inp.get("url", ""))).netloc or "page")
    if tool == "WebSearch":
        return "Web search: " + short(inp.get("query"), 50)
    if tool in ("Agent", "Task"):
        return "Agent: " + short(inp.get("description"), 55)
    if tool == "AskUserQuestion":
        qs = inp.get("questions") or [{}]
        return "Asking: " + short(qs[0].get("question"), 60)
    if tool == "ExitPlanMode":
        return "Plan ready for review"
    if tool == "Skill":
        return "Skill: " + short(inp.get("skill"), 40)
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return f"{parts[1]} · {parts[-1]}"
    return tool or "Working"


@dataclass
class Session:
    id: str
    cwd: str = ""
    project: str = "?"
    state: str = "idle"  # idle | working
    action: str = "Ready"
    since: float = 0  # when `action` started
    last: float = 0  # last event seen
    task: str = ""  # current prompt, shortened
    turn_start: float = 0
    recent: list = field(default_factory=list)  # [[ts, text], ...] newest last
    # {"kind", "text", "ts", "call"?, "questions"?, "detail"?, "answerable"?}
    attention: dict | None = None
    quiet: bool = False  # user dismissed: ignore reminder notifications until the agent moves on
    pid: int | None = None
    entry: str = ""  # cli, claude-vscode, ...
    model: str = ""
    subagents: int = 0
    ctx_tokens: int = 0  # size of the context sent with the latest request
    out_tokens: int = 0  # output tokens over the whole session
    ended: bool = False

    @classmethod
    def load(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def apply(s: Session, ev: dict, now: float):
    """Update `s` for one hook event. Returns the attention kind if a new one was raised."""
    name = ev.get("hook_event_name", "")
    tool = ev.get("tool_name", "")
    inp = ev.get("tool_input") or {}
    was = s.attention

    s.last = now
    if ev.get("_pid"):
        s.pid = ev["_pid"]
    if ev.get("_entry"):
        s.entry = ev["_entry"]
    if ev.get("model"):
        s.model = str(ev["model"])
    proj = ev.get("_project_dir") or ("" if s.cwd else ev.get("cwd"))
    if proj:
        s.cwd, s.project = proj, base(proj)

    def act(state, action, log=False):
        s.state, s.action, s.since = state, action, now
        if log:
            s.recent = (s.recent + [[now, action]])[-RECENT:]

    def attend(kind, text, **extra):
        s.attention = {"kind": kind, "text": short(text, 160), "ts": now, **extra}

    def block():
        """PreToolUse and PermissionRequest describe the same call and can arrive in either order."""
        call = describe(tool, inp)
        if was and was["kind"] in BLOCKED and was.get("call") == call:
            return
        if tool == "AskUserQuestion":
            qs = inp.get("questions") or [{}]
            questions = [
                {
                    "q": short(q.get("question"), 200),
                    "options": [short(o.get("label"), 40) for o in q.get("options") or []],
                    "multi": bool(q.get("multiSelect")),
                }
                for q in qs
            ]
            attend("question", qs[0].get("question"), call=call, questions=questions)
        elif tool == "ExitPlanMode":
            attend("plan", call, call=call, detail=str(inp.get("plan") or "")[:1500])
        elif name == "PermissionRequest":
            attend("permission", call, call=call)
        else:
            s.attention = None  # an ordinary tool started: the agent moved on

    if name == "SessionStart":
        if ev.get("source") in (None, "startup", "resume"):
            act("idle", "Ready")
            s.attention = None
    elif name == "UserPromptSubmit":
        s.task = short(ev.get("prompt"), 120)
        s.turn_start, s.attention, s.quiet = now, None, False
        act("working", "Thinking")
    elif name == "PreToolUse":
        s.quiet = False
        block()
        act("working", ("↳ " if ev.get("agent_id") else "") + describe(tool, inp), log=True)
    elif name == "PermissionRequest":
        s.quiet = False
        block()
    elif name in ("PostToolUse", "PostToolUseFailure", "PermissionDenied"):
        if was and was["kind"] in BLOCKED:
            s.attention = None
        act("working", "Thinking")
    elif name == "Notification":
        kind = ev.get("notification_type", "")
        if not was and not s.quiet:
            if kind == "permission_prompt":
                attend("permission", ev.get("message"))
            elif kind in ("agent_needs_input", "elicitation_dialog"):
                attend("question", ev.get("message"))
    elif name == "Stop":
        act("idle", "Finished")
        s.attention = None
        if now - s.turn_start >= DONE_MIN_TURN:
            attend("done", ev.get("last_assistant_message") or "Finished")
    elif name == "StopFailure":
        act("idle", "Stopped on error")
        attend("error", ev.get("error") or ev.get("message") or "Turn failed")
    elif name == "SubagentStart":
        s.subagents += 1
    elif name == "SubagentStop":
        s.subagents = max(0, s.subagents - 1)
    elif name == "PreCompact":
        act("working", "Compacting context")
    elif name == "SessionEnd":
        s.ended = True

    if s.attention and s.attention is not was:
        return s.attention["kind"]
    return None
