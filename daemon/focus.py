"""Bring the terminal (or editor) window that runs a Claude Code session to the front.

Wayland has no general "activate another app's window" call, so this asks the compositor:
KWin through a one-off script, Hyprland through hyprctl, Sway through swaymsg.
Konsole is also told to switch to the right tab.
"""
import json
import os
import shutil
import subprocess

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
KWIN_SCRIPT = """
const pids = %s, hint = %s;
const ws = workspace.windowList().filter(w => w.normalWindow && pids.includes(w.pid));
const w = ws.find(w => w.caption.includes(hint)) || ws[0];
if (w) workspace.activeWindow = w;
"""


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None


def ancestors(pid):
    """pid and its parents, nearest first. One of them owns the window."""
    out = []
    while pid and pid > 1 and len(out) < 20:
        out.append(pid)
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return out


def konsole_tab(pid):
    """Konsole puts its D-Bus address in the shell's environment; use it to select the tab."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = dict(v.split(b"=", 1) for v in f.read().split(b"\0") if b"=" in v)
        service = env[b"KONSOLE_DBUS_SERVICE"].decode()
        window = env[b"KONSOLE_DBUS_WINDOW"].decode()
        session = int(env[b"KONSOLE_DBUS_SESSION"].decode().rsplit("/", 1)[1])
    except (OSError, KeyError, ValueError, IndexError):
        return
    run("busctl", "--user", "call", service, window, "org.kde.konsole.Window", "setCurrentSession", "i", str(session))


def kwin(pids, hint):
    up = run("busctl", "--user", "status", "org.kde.KWin")
    if not up or up.returncode:
        return False
    path, name = f"{RUNTIME}/agent-inbox-focus.js", "agent-inbox-focus"
    with open(path, "w") as f:
        f.write(KWIN_SCRIPT % (json.dumps(pids), json.dumps(hint)))
    scripting = ("busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")
    run(*scripting, "unloadScript", "s", name)
    loaded = run(*scripting, "loadScript", "ss", path, name)
    if not loaded or loaded.returncode:
        return False
    script_id = loaded.stdout.split()[-1]
    run("busctl", "--user", "call", "org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script", "run")
    run(*scripting, "unloadScript", "s", name)
    return True


def focus(pids, hint=""):
    """pids: the session's process chain, nearest first. Returns False if no supported compositor was found."""
    pids = [p for p in pids if os.path.exists(f"/proc/{p}")]
    if not pids:
        return False
    pids += [p for p in ancestors(pids[-1]) if p not in pids]
    konsole_tab(pids[0])
    if kwin(pids, hint):
        return True
    for tool, make in (
        ("hyprctl", lambda p: ("hyprctl", "dispatch", "focuswindow", f"pid:{p}")),
        ("swaymsg", lambda p: ("swaymsg", f"[pid={p}]", "focus")),
    ):
        if shutil.which(tool):
            for p in pids:
                r = run(*make(p))
                if r and r.returncode == 0 and "no such window" not in r.stdout.lower():
                    return True
    return False
