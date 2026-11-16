#!/usr/bin/python3
"""Agent hook: forward one hook event to the agent-inbox daemon and exit.

Usage: agent_inbox_hook.py [agent] [event]
  agent = claude (default) | codex | copilot | antigravity
  event = only for agents whose payload does not name the event (antigravity)

Every agent's payload is translated here into one common shape (Claude Code's), so the
daemon does not need to know which agent it is talking to.

Must never slow or block the agent: stdlib only, 1 s socket timeout, every error
swallowed, always exits 0.

A permission request is the one event that waits: the daemon may send back a decision
made in the overlay. Claude Code shows its own prompt at the same time, so either side can
answer. Codex and Copilot hold their prompt until the hook returns, so for them the wait
is short (ASK_WAIT) and the overlay offers "answer there", which releases the hook.

Copilot inside VS Code never sends a permission request, only "about to run a tool". With
copilot_gate on (config), shell commands that are not plainly read-only are therefore
offered to the overlay first: approve runs the command without VS Code asking, deny blocks
it, and no answer leaves the decision to VS Code as usual.

Antigravity works the same way with antigravity_gate: its PreToolUse hook (registered for
run_command only, and only while the gate is on) must always print a decision, so the
answer is allow, deny, or "ask", which is Antigravity's own prompt.
"""
import json
import os
import re
import socket
import sys

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-inbox.sock"
MAX_STR = 2000
# s to wait for an answer from the overlay, per agent
ASK_WAIT = {"claude": 300, "codex": 60, "copilot": 60}


CONFIG = (os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) + "/agent-inbox/config.json"
# commands that only look at things; never worth interrupting for
READ_ONLY = re.compile(
    r"^(cd|ls|pwd|cat|head|tail|wc|echo|printf|grep|rg|find|which|file|stat|tree|date|true"
    r"|git\s+(--no-pager\s+)?(status|diff|log|show|branch|remote|ls-files|rev-parse))(\s|$)"
)


def config():
    try:
        with open(CONFIG) as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def read_only(command):
    if not isinstance(command, str) or re.search(r"[>`]|\$\(|\bsudo\b|\brm\b", command):
        return False
    parts = [p.strip() for p in re.split(r"&&|\|\||[;|\n]", command) if p.strip()]
    return bool(parts) and all(READ_ONLY.match(p) for p in parts)


def exchange(kind, ev, wait=None):
    """Send one message to the daemon; with `wait`, block for its reply (a decision or None)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    s.sendall((json.dumps({"kind": kind, "event": ev}) + "\n").encode())
    decision = None
    if wait:
        s.settimeout(wait)
        reply = s.makefile().readline()
        decision = json.loads(reply).get("decision") if reply.strip() else None
    s.close()
    return decision


def trim(v):
    if isinstance(v, str):
        return v if len(v) <= MAX_STR else v[:MAX_STR] + "…"
    if isinstance(v, dict):
        return {k: trim(x) for k, x in v.items()}
    if isinstance(v, list):
        return [trim(x) for x in v[:50]]
    return v


def ancestors():
    """[(pid, argv)] from our parent upwards. One of them is the agent, one owns the window."""
    out, pid = [], os.getppid()
    while pid > 1 and len(out) < 12:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
            with open(f"/proc/{pid}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
        out.append((pid, argv))
        pid = ppid
    return out


def normalize(agent, ev, event):
    """Translate an agent's payload into the common event shape."""
    if agent == "antigravity":
        call = ev.get("toolCall") or {}
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        paths = ev.get("workspacePaths") or [""]
        out = {"session_id": ev.get("conversationId"), "cwd": paths[0], "model": ev.get("modelName")}
        if event == "PreInvocation":  # fires for every model call of a turn
            out.update(hook_event_name="UserPromptSubmit", prompt=ev.get("lastUserInput"), _repeat=True)
        elif event in ("PreToolUse", "PostToolUse"):
            command = args.get("CommandLine") or args.get("command")
            # Without the gate a tool call is only reported after it ran, and is shown as the
            # current action. With the gate, commands are reported before and after.
            after = event == "PostToolUse" and command and config().get("antigravity_gate")
            out.update(hook_event_name="PostToolUse" if after else "PreToolUse",
                       tool_name="Bash" if command else call.get("name"),
                       tool_input={"command": command} if command else args)  # fmt: skip
        elif event == "Stop" and ev.get("error"):
            out.update(hook_event_name="StopFailure", error=str(ev["error"]))
        else:
            out["hook_event_name"] = event
        return out
    if ev.get("hook_event_name") == "ErrorOccurred":  # copilot
        err = ev.get("error")
        ev.update(hook_event_name="StopFailure", error=err.get("message") if isinstance(err, dict) else str(err))
    return ev


def main():
    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    ev = normalize(agent, json.load(sys.stdin), sys.argv[2] if len(sys.argv) > 2 else "")
    ev.pop("tool_response", None)
    ev.pop("tool_result", None)
    ev = trim(ev)

    chain = ancestors()
    env = os.environ
    env_pid = env.get("CLAUDE_PID", "") if agent == "claude" else ""
    ev["_agent"] = agent
    # the agent's own process (so a session can be stopped and noticed when it exits);
    # absent for agents that live inside an editor. Codex runs hooks from its `app-server`
    # background process, which is not the session: stopping it only disconnects the TUI.
    ev["_pid"] = int(env_pid) if env_pid.isdigit() else next(
        (pid for pid, argv in chain
         if any(agent.encode() in os.path.basename(a) for a in argv[:2]) and b"app-server" not in argv),
        None,
    )
    ev["_chain"] = [pid for pid, _ in chain]  # for bringing its window to the front
    in_vscode = (
        env.get("TERM_PROGRAM") == "vscode"
        or any(k.startswith("VSCODE_") for k in env)
        or any(b"/code/" in argv[0] or b"copilot-sdk" in argv[0] for _, argv in chain)
    )
    ev["_entry"] = (
        (agent == "claude" and env.get("CLAUDE_CODE_ENTRYPOINT"))
        or ("ide" if agent == "antigravity" else "vscode" if in_vscode else "cli")
    )
    ev["_project_dir"] = env.get("CLAUDE_PROJECT_DIR", "")

    name = ev.get("hook_event_name")
    if agent == "antigravity":
        gate = len(sys.argv) > 2 and sys.argv[2] == "PreToolUse"
        reply = {"decision": "ask"} if gate else {}  # "ask" = Antigravity's own prompt
        try:
            exchange("event", ev)
            cfg = config()
            if gate and cfg.get("antigravity_gate") and not read_only(ev["tool_input"].get("command")):
                wait = cfg.get("antigravity_wait")
                decision = exchange("ask", dict(ev, hook_event_name="PermissionRequest"), wait if isinstance(wait, int) else 30)
                if decision:
                    reply = {"decision": decision["behavior"],
                             "reason": decision.get("message") or "Approved by the user in the agent-inbox overlay"}
        finally:
            sys.stdout.write(json.dumps(reply))  # Antigravity expects JSON back from every hook
            sys.stdout.flush()
        return
    if name == "PermissionRequest" and agent in ASK_WAIT:
        decision = exchange("ask", ev, ASK_WAIT[agent])
        if decision:
            out = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
            if agent == "copilot":  # Copilot reads the decision from the top level
                out = {**decision, **out}
            sys.stdout.write(json.dumps(out))
            sys.stdout.flush()
        return
    exchange("event", ev)

    command = (ev.get("tool_input") or {}).get("command") if isinstance(ev.get("tool_input"), dict) else None
    if agent == "copilot" and name == "PreToolUse" and ev.get("tool_name") == "Bash" and not read_only(command):
        cfg = config()
        if cfg.get("copilot_gate"):
            wait = cfg.get("copilot_wait")
            decision = exchange("ask", dict(ev, hook_event_name="PermissionRequest"), wait if isinstance(wait, int) else 30)
            if decision:
                verdict = {
                    "permissionDecision": decision["behavior"],
                    "permissionDecisionReason": decision.get("message") or "Approved by the user in the agent-inbox overlay",
                }
                out = {**verdict, "hookSpecificOutput": {"hookEventName": "PreToolUse", **verdict}}
                sys.stdout.write(json.dumps(out))
                sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
