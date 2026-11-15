#!/usr/bin/python3
"""Claude Code status line: prints model, context and plan usage, and passes the
plan usage on to the agent-inbox daemon (the status line is the only place Claude
Code exposes it).
"""
import json
import os
import socket
import sys

SOCK = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}") + "/agent-inbox.sock"


def main():
    d = json.load(sys.stdin)
    limits = d.get("rate_limits") or {}
    ctx = (d.get("context_window") or {}).get("used_percentage")
    parts = [(d.get("model") or {}).get("display_name") or "Claude"]
    if ctx is not None:
        parts.append(f"ctx {ctx:.0f}%")
    for key, name in (("five_hour", "5h"), ("seven_day", "7d")):
        pct = (limits.get(key) or {}).get("used_percentage")
        if pct is not None:
            parts.append(f"{name} {pct:.0f}%")
    print(" · ".join(parts), flush=True)

    status = {"session_id": d.get("session_id"), "rate_limits": limits, "ctx_pct": ctx}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(SOCK)
    s.sendall((json.dumps({"kind": "status", "status": status}) + "\n").encode())
    s.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
