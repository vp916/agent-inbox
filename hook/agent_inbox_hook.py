#!/usr/bin/python3
"""Claude Code hook: forward the event to the agent-inbox daemon and exit.

Must never slow or block the agent: stdlib only, 1 s socket timeout,
every error swallowed, always exits 0.

PermissionRequest is the one event that waits: the daemon may send back a decision
made in the overlay. Claude Code shows its own prompt at the same time, so the
terminal stays usable; the daemon closes the connection once it is answered there.
"""
import json
import os
import socket
import sys
import time

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-inbox.sock"
MAX_STR = 2000
ASK_WAIT = 300  # s to wait for an answer from the overlay


def trim(v):
    if isinstance(v, str):
        return v if len(v) <= MAX_STR else v[:MAX_STR] + "…"
    if isinstance(v, dict):
        return {k: trim(x) for k, x in v.items()}
    if isinstance(v, list):
        return [trim(x) for x in v[:50]]
    return v


def claude_pid():
    """Nearest ancestor process that is Claude Code itself."""
    pid = os.getppid()
    for _ in range(8):
        if pid <= 1:
            break
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().split(b"\0")
            with open(f"/proc/{pid}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
        if any(b"claude" in os.path.basename(a) for a in cmd[:2]):
            return pid
        pid = ppid
    return None


def main():
    ev = json.load(sys.stdin)
    ev.pop("tool_response", None)
    ev = trim(ev)
    env_pid = os.environ.get("CLAUDE_PID", "")
    ev["_pid"] = int(env_pid) if env_pid.isdigit() else claude_pid()
    ev["_entry"] = os.environ.get("CLAUDE_CODE_ENTRYPOINT") or os.environ.get("TERM_PROGRAM") or ""
    ev["_project_dir"] = os.environ.get("CLAUDE_PROJECT_DIR", "")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    ask = ev.get("hook_event_name") == "PermissionRequest"
    s.sendall((json.dumps({"kind": "ask" if ask else "event", "event": ev}) + "\n").encode())
    if ask:
        s.settimeout(ASK_WAIT)
        reply = s.makefile().readline()
        decision = json.loads(reply).get("decision") if reply.strip() else None
        if decision:
            out = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
            sys.stdout.write(json.dumps(out))
            sys.stdout.flush()
    s.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
